# Tetris server: repository guidance

## Repository remote

- GitHub repository: `JulipoDom/tetris-server`.
- SSH remote: `git@github.com:JulipoDom/tetris-server.git`; remote name: `origin`.
- Default branch: `main`. Preserve existing remote history when publishing changes.

## Read first

- Read `00-contexto-geral.md` and `02-boilerplate-servidor.md` before changing the server.
- `00-contexto-geral.md` is the source of truth for shared rules and the initial protocol. `02-boilerplate-servidor.md` defines the server boilerplate and its acceptance criteria.
- These documents supplied the design for the local implementation now in `src/` and `tests/`. Real networking remains pending. `pyproject.toml` defines package discovery and the server console entry point; `README.md` documents execution.
- The client, roadmap, and PDF mentioned in the general context are not present here. Do not assume their contents or create client scope as part of server work.

## Scope and dependencies

- Use Python 3.12 or newer and the standard library; coordinate the same Python minor version across the team. Use `unittest` for tests.
- Each server execution handles exactly two players and one match, then terminates. Another match requires another execution.
- Do not add rooms, matchmaking, player queues, match IDs, concurrent matches, accounts, rankings, reconnection, persistence, or a database.
- Implement the domain, sequential application dispatcher, in-memory simulations, and their tests.
- Real networking, codecs, parsing, framing, buffers, and timers remain `TODO[EP-REDE]`. Executable unimplemented methods must raise `NotImplementedError` with that marker.
- Network mode must fail explicitly; never fall back to simulation.
- A later user request authorized `network-test`: minimal TCP diagnostics on `127.0.0.1`, separate from the match transport and TVP/1. It sends three predefined blocks, checks the 54-byte stream, and exits. This narrowly scoped diagnostic is the exception to the pending-network rule; do not extend it into game transport.
- The server must not import the client engine or `curses`. Keep shared models and rules independent of networking and UI.
- Future transport uses direct TCP sockets. Do not replace it with HTTP, WebSocket, RPC, or a multiplayer framework.

## Structure

| Path | Responsibility |
| --- | --- |
| `src/tetris_server/__main__.py` | CLI with `simulated` and pending `network` modes. |
| `src/tetris_server/match.py` | `MatchController`, two participants, readiness, state, immutable result. |
| `src/tetris_server/app.py` | Sequential dispatch of local commands and recorded outputs. |
| `src/tetris_server/simulation.py` | Scenarios using objects, callbacks, and per-participant outboxes in memory. |
| `src/tetris_server/network.py` | Pending listener, connection admission, I/O, association, and timers; prepares communication workers. |
| `src/tetris_server/communication.py` | Receive/send callback threads and object queues; caller thread dispatches commands sequentially. |
| `src/tetris_server/network_diagnostic.py` | Standalone minimal TCP loopback diagnostics, with receive/send threads. |
| `src/tetris_shared/models.py` | Shared internal typed models. |
| `src/tetris_shared/rules.py` | Allowed attack quantities and common constants. |
| `src/tetris_shared/protocol.py` | Pending encoder, parser, and framing. |
| `tests/test_server.py` | Domain lifecycle, validation, forwarding, and failure tests. |

Keep a single `tetris_shared` package for eventual use by both executables. Maintain package discovery for the `src/` layout so documented commands actually run.

## Domain invariants

- Use states `WAITING`, `PREPARING`, `PLAYING`, and `FINISHED`. Only the sequential dispatcher changes match state or result.
- Communication workers must never mutate the match: only the calling dispatcher processes commands and delivery failures. Callbacks must terminate cooperatively; receive observes the stop Event.
- A participant has an opaque session reference and a nickname. The session identifies the participant; equal nicknames are valid. Derive the opponent from the other position, never from a client-supplied target.
- Nicknames contain 1–20 characters from `[A-Za-z0-9_]`. A registered session cannot identify itself again. Unknown sessions cannot perform participant operations.
- One identified player remains in `WAITING`. Two identifications enter `PREPARING` and emit the opponent nickname to each participant.
- Reject a third participant without changing the original pair or the match. Do not admit new participants after finalization.
- Readiness is valid only after the pair exists. Repeated readiness is idempotent during preparation and ignored during play. Both ready players produce exactly one start authorization each, queued before any game forwarding.
- Accept attacks only during play and only for integers `1`, `2`, or `4`; reject booleans. The quantity already means garbage lines: forward it unchanged to the opponent.
- Accept boards only during play: 20 rows × 10 cells with integer values `0`–`8`. Validate and copy into an immutable snapshot. Do not include the active piece, simulate physics, infer KO from the board, or transmit score.
- The latest unconsumed visual snapshot may replace an older snapshot. Never discard or replace attacks or results.
- Valid KO causes are `SPAWN` and `OVERFLOW`, accepted only during play. Record the immutable result and enter `FINISHED` before emitting WIN/KO and LOSE/KO.
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

## Protocol boundary for later EP work

- Exactly eight wire types: `HELLO`, `MATCH`, `READY`, `BOARD`, `ATTACK`, `KO`, `GAMEOVER`, `KEEPALIVE`. Internal commands and typed errors must not become extra wire types.
- `HELLO` identifies a client; `MATCH` supplies the opponent nickname; `READY|PLAYER` confirms readiness and `READY|GO` authorizes play.
- `BOARD` carries exactly 200 digits from `0`–`8`, row by row. `ATTACK` carries `1`, `2`, or `4`. `KO` carries `SPAWN` or `OVERFLOW`.
- `GAMEOVER` carries WIN, LOSE, or CANCEL and the reason defined in the source documents. KEEPALIVE has no application fields and is never immediately echoed.
- Future framing is ASCII `TVP/1|...` terminated by LF, with at most 512 bytes including LF. Preserve partial receives and partial writes; TCP does not preserve message boundaries.
- Reserve at most two admitted connections, including those awaiting HELLO. Reject a third connection without an extra message type.
- Future defaults: HELLO deadline 5 seconds, KEEPALIVE every 5 seconds after HELLO, inactivity timeout 15 seconds since the last complete valid message, output limit 4096 bytes per connection, final notification drain at most 1 second.
- Do not implement those mechanisms in this boilerplate or serialize wire text in the fake. Read the complete grammar and direction/state restrictions in `00-contexto-geral.md` when implementing networking later.

## Validation

Run from the repository root without installing:

```bash
PYTHONPATH=src python -m tetris_server --mode simulated
PYTHONPATH=src python -m tetris_server --mode network
PYTHONPATH=src python -m tetris_server --mode network-test --port 0
PYTHONPATH=src python -m unittest discover -s tests -v
```

Simulation must run without sockets or TUI. Network mode must explicitly fail with `TODO[EP-REDE]` and exit status 2; that failure is expected at this stage. An editable install as documented in README enables module commands without `PYTHONPATH`.

Cover the complete lifecycle, third-player refusal, duplicate readiness, both KO orders, departures before and after play, timeout/protocol/server-stop policies, invalid boards and attacks (including booleans), unknown sessions, immutable snapshots, and delivery failure after finalization. Confirm start outputs precede game effects and late events preserve the final result.

Logs describe local state, participant, occurrence, and reason. Do not describe simulations as transmitted bytes, measured ping, real connections, or evidence of a functional TCP server.

The diagnostic mode requires local sockets. Its four integration tests explicitly skip when the environment denies sockets; report those skips without claiming real TCP validation. Keep comments and docstrings in Portuguese.
