# Tetris server: repository guidance

## Repository remote

- GitHub repository: `JulipoDom/tetris-server`.
- SSH remote: `git@github.com:JulipoDom/tetris-server.git`; remote name: `origin`.
- Default branch: `main`. Preserve existing remote history when publishing changes.

## Read first

- Read `00-contexto-geral.md` and `02-boilerplate-servidor.md` before changing the server.
- `00-contexto-geral.md` is the source of truth for shared rules and the initial protocol. `02-boilerplate-servidor.md` defines the server boilerplate and its acceptance criteria.
- These documents supplied the initial design. `docs/PROTOCOLO_TCP.md` is the detailed TVP/1 contract, and `README.md` documents the current execution. `pyproject.toml` defines package discovery and the server console entry point.
- The client, roadmap, and PDF mentioned in the general context are not present here. Do not assume their contents or create client scope as part of server work.

## Scope and dependencies

- Use Python 3.12 or newer and the standard library; coordinate the same Python minor version across the team. No automated test files are currently distributed; preserve Markdown validation reports.
- Each match handles exactly two players. The server handles matches sequentially in one process after cleaning each round; never run concurrent matches.
- Do not add rooms, matchmaking, player queues, match IDs, concurrent matches, accounts, rankings, reconnection, persistence, or a database.
- Preserve the domain, sequential application dispatcher, in-memory simulations, TCP transport. Automated test files were removed at the owner’s request.
- Network mode uses direct TCP sockets and never falls back to simulation. `network-test` is a separate local diagnostic that does not use TVP/1 or begin a match.
- The server must not import the client engine or `curses`. Keep shared models and rules independent of networking and UI.
- Keep direct TCP sockets. Do not replace them with HTTP, WebSocket, RPC, or a multiplayer framework.

## Structure

| Path | Responsibility |
| --- | --- |
| `src/tetris_server/__main__.py` | CLI with `simulated`, `network` and `network-test` modes. |
| `src/tetris_server/match.py` | `MatchController`, two participants, readiness, state, immutable result. |
| `src/tetris_server/app.py` | Sequential dispatch of local commands and recorded outputs. |
| `src/tetris_server/simulation.py` | Scenarios using objects, callbacks, and per-participant outboxes in memory. |
| `src/tetris_server/network.py` | TCP listener, connection admission, framing, I/O, buffers and timers with sequential dispatch. |
| `src/tetris_server/communication.py` | Receive/send callback threads and object queues; caller thread dispatches commands sequentially. |
| `src/tetris_server/network_diagnostic.py` | Standalone minimal TCP loopback diagnostics, with receive/send threads. |
| `src/tetris_shared/models.py` | Shared internal typed models. |
| `src/tetris_shared/rules.py` | Allowed attack quantities and common constants. |
| `src/tetris_shared/protocol.py` | Shared TVP/1 encoder, parser, and framing. |

Keep the two repository copies of `tetris_shared/protocol.py` identical. Run each executable with its own `PYTHONPATH=src` to avoid package collisions. Maintain package discovery for the `src/` layout so documented commands actually run.

## Domain invariants

- Use states `WAITING`, `PREPARING`, `PLAYING`, and `FINISHED`. Only the sequential dispatcher changes match state or result.
- Only the sequential dispatcher changes the match. The TCP server uses `selectors` in one thread; the callback communication coordinator remains for local use and tests.
- A participant has an opaque session reference and a nickname. The session identifies the participant; equal nicknames are valid. Derive the opponent from the other position, never from a client-supplied target.
- Nicknames contain 1–20 characters from `[A-Za-z0-9_]`. A registered session cannot identify itself again. Unknown sessions cannot perform participant operations.
- One identified player remains in `WAITING`. Two identifications enter `PREPARING` and emit the opponent nickname to each participant.
- Reject a third participant without changing the original pair or the match. Admit the next pair only after draining and cleaning the finalized round.
- Readiness is valid only after the pair exists. Repeated readiness is idempotent during preparation and ignored during play. Both ready players produce exactly one start authorization each, queued before any game forwarding.
- Accept attacks only during play and only for integers `1`, `2`, or `4`; reject booleans. The quantity already means garbage lines: forward it unchanged to the opponent.
- Accept boards only during play: 20 rows × 10 cells with integer values `0`–`8`. Validate and copy into an immutable snapshot. Do not include the active piece, simulate physics, infer KO from the board, or transmit score.
- The latest unconsumed visual snapshot may replace an older snapshot. Never discard or replace attacks or results.
- Valid KO causes are `SPAWN`, `OVERFLOW`, and `INACTIVITY`, accepted only during play. Record the immutable result and enter `FINISHED` before emitting WIN/KO and LOSE/KO.
- The first valid ending event processed determines the result. Late events and delivery failures must not change it or produce another finalization. No game forwarding occurs after finalization.

## Failure policy

The domain receives failure facts; it does not detect socket failures or run network timers.

| Fact | Before play | During play |
| --- | --- | --- |
| Identified participant disconnects | CANCEL / DISCONNECT | Opponent WIN / DISCONNECT |
| Identified participant times out | CANCEL / TIMEOUT | Opponent WIN / TIMEOUT |
| Identified participant violates protocol | CANCEL / PROTOCOL | Opponent WIN / PROTOCOL |
| Planned server stop | CANCEL / SERVER_STOP | CANCEL / SERVER_STOP |

Keep the absent or offending participant's outcome internally, without promising delivery. KO before play is a protocol violation. A discarded connection without a valid HELLO releases its reservation and does not cancel an identified participant's match. An abrupt process failure cannot promise notifications.

## Protocol boundary

- Exactly eight wire types: `HELLO`, `MATCH`, `READY`, `BOARD`, `ATTACK`, `KO`, `GAMEOVER`, `KEEPALIVE`. Internal commands and typed errors must not become extra wire types.
- `HELLO` identifies a client; `MATCH` supplies the opponent nickname; `READY|PLAYER` confirms readiness and `READY|GO` authorizes play.
- `BOARD` carries exactly 200 digits from `0`–`8`, row by row. `ATTACK` carries `1`, `2`, or `4`. `KO` carries `SPAWN`, `OVERFLOW`, or `INACTIVITY`. After KO, both connected players may vote `READY|REMATCH` within 10 seconds; two votes start a new sequential round on the same connections with `READY|GO`.
- `GAMEOVER` carries WIN, LOSE, or CANCEL and the reason defined in the source documents. KEEPALIVE has no application fields and is never immediately echoed.
- Framing is ASCII `TVP/1|...` terminated by LF, with at most 512 bytes including LF. Preserve partial receives and partial writes; TCP does not preserve message boundaries.
- Reserve at most two admitted connections, including those awaiting HELLO. Reject a third connection without an extra message type.
- Defaults: HELLO deadline 5 seconds, KEEPALIVE every 5 seconds after HELLO, inactivity timeout 15 seconds since the last complete valid message, output limit 4096 bytes per connection, final notification drain at most 1 second.
- Read the complete grammar and direction/state restrictions in `docs/PROTOCOLO_TCP.md`. Keep the in-memory fake free of serialized wire text.

## Validation

Run from the repository root without installing:

```bash
PYTHONPATH=src python -m tetris_server --mode simulated
PYTHONPATH=src python -m tetris_server --mode network
PYTHONPATH=src python -m tetris_server --mode network-test --port 0
python3 -m compileall -q src
```

Simulation must run without sockets or TUI. Network mode listens on TCP and returns status 2 if startup fails. An editable install as documented in README enables module commands without `PYTHONPATH`.

Cover the complete lifecycle, third-player refusal, duplicate readiness, both KO orders, departures before and after play, timeout/protocol/server-stop policies, invalid boards and attacks (including booleans), unknown sessions, immutable snapshots, and delivery failure after finalization. Confirm start outputs precede game effects and late events preserve the final result.

Logs describe local state, participant, occurrence, and reason. Do not describe simulations as transmitted bytes, measured ping, real connections, or evidence of a functional TCP server.

The diagnostic mode requires local sockets. Past integration tests skipped when the environment denied sockets; they have been removed and their results are recorded in docs/RELATORIO_VALIDACAO.md. Do not claim real TCP validation from simulated execution. Keep comments and docstrings in Portuguese.
