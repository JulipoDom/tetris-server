# Tetris Versus server

A Python 3.12+ server boilerplate for a terminal Tetris game with two players.
The local match logic, simulations, and tests work. Real TCP networking is
reserved for manual implementation with `TODO[EP-REDE]` stubs.

## General idea

Each client runs its own Tetris board: pieces, gravity, collisions, line clears,
score, garbage application, and local defeat detection. Multiple line clears
produce garbage attacks for the opponent. The server identifies the two players,
waits for both to be ready, forwards attacks and fixed-board snapshots, and
records one final result. It trusts cooperative clients and does not simulate
physics or prove that an attack came from a real line clear.

The intended network server handles **exactly two players and one match per
execution**, then exits. Another match requires restarting. Rooms, matchmaking,
accounts, rankings, reconnection, and databases are outside the scope. The client
engine and terminal UI are not included in this repository.

## Run locally

Use Python 3.12 or newer, with the same minor version across the team. The domain
and tests use only the standard library. From the repository root:

```bash
PYTHONPATH=src python -m tetris_server --mode simulated
```

This runs eight scripted scenarios, prints their local logs, and exits. Omitting
`--mode` also selects `simulated`. It does not wait for real clients or open a port.
`PYTHONPATH=src` makes the uninstalled packages in `src/` available to Python.

Run the tests:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The current suite contains **30 tests**, covering lifecycle, validation,
forwarding order, immutable snapshots/results, cancellation, delivery failures,
simulations, and the explicit network stubs.

Network mode is currently pending:

```bash
PYTHONPATH=src python -m tetris_server --mode network
```

It prints `TODO[EP-REDE]: TCP listener, sessions, I/O, buffers, and timers` to
stderr and exits with status **2**. There is no silent fallback to simulation.

### Optional installation

An editable install enables module commands without `PYTHONPATH` and the
`tetris_server` console command. Installation uses setuptools as a build tool;
there are no third-party runtime dependencies.

```bash
python -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m tetris_server --mode simulated
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/tetris_server --mode simulated
```

## How execution works

`__main__.py` selects the mode. Simulated mode calls `run_simulations()`; network
mode calls the pending `NetworkServer.run()`.

The implemented local processing path is:

```text
Command → ServerApp.process() → MatchController
        → OutboundEvent → per-session outbox
                        → optional local delivery callback
```

`ServerApp.process()` dispatches one command completely before the next. The
controller owns the two player slots and transitions:

```text
WAITING → PREPARING → PLAYING → FINISHED
```

The first join stays in WAITING. The second join emits MATCH with the opponent's
nickname and enters PREPARING. Both players becoming ready emits one READY/GO
per player and enters PLAYING. An ending event records the result before queuing
GAMEOVER. Identified-player failure or planned stop can also end before play.

Sessions are stable, hashable identity tokens; equal nicknames are allowed.
The opponent always comes from the other slot, not a client-supplied target.
Known participants' late game events do not create new effects after FINISHED.

## What is implemented

| Feature | How it works | Location |
| --- | --- | --- |
| Shared typed objects | Enums plus frozen player, command, event, and result dataclasses. | [models.py](src/tetris_shared/models.py) |
| Two-player admission | Validates nicknames, rejects duplicate sessions and a third participant without replacing the original pair. | `MatchController.join()` in [match.py](src/tetris_server/match.py) |
| Readiness | Repetition is idempotent; both ready players receive exactly one GO before game effects. | `MatchController.ready()` |
| Attack forwarding | Validates integer garbage quantity 1, 2, or 4, rejects booleans, and forwards unchanged. | `MatchController.attack()` |
| Board forwarding | Validates 20×10 integer cells from 0–8, stores an immutable copy, and forwards to the opponent. | `MatchController.board()` |
| Final result | First valid ending wins processing order; later KO or delivery failure cannot revise the result. | `ko()`, `_finish()`, and `MatchResult` |
| Failure policy | Before play, identified failure cancels; during play, the opponent wins. Planned stop always cancels an unfinished match. | `failure()` and `stop()` |
| Output queues and logs | Queue Python events per recipient; only stale unconsumed BOARD events can be replaced. Attacks and results are preserved. | [app.py](src/tetris_server/app.py) |
| Local callback delivery | Callback exceptions become disconnect facts; newly queued survivor notifications are also drained. | `ServerApp.deliver()` |
| Local scenarios and tests | Exercise the domain without sockets, byte serialization, UI, or real timers. | [simulation.py](src/tetris_server/simulation.py), [tests](tests) |

Every function in `src/` has a short explanatory docstring. Common board rules,
validation values, and reserved network defaults live in
[rules.py](src/tetris_shared/rules.py). `.gitignore` excludes Python outputs,
virtual environments, caches, environment files, and local agent/credential
folders.

## How the simulation works

Every scenario creates a fresh `ServerApp` and `MatchController`. Strings such
as `player1` and `player2` stand in for sessions. Scripted `Command` objects pass
through the real dispatcher; resulting `OutboundEvent` objects remain in local
outboxes or are consumed by a callback. No real Tetris client is running.

The normal scenario performs two joins, two readiness commands, an attack of
2 garbage lines, a board snapshot, then player1 KO/SPAWN. The final result is
player2 WIN/KO and player1 LOSE/KO. The server only forwards the attack; it does
not apply garbage to a simulated game board.

| Scenario | Behavior exercised |
| --- | --- |
| `complete_match` | Identification, readiness, attack, snapshot, and KO. |
| `third_participant_refused` | Rejecting a third participant while preserving the original pair. |
| `first_ko_player1` | Duplicate readiness and player1's KO taking effect first. |
| `first_ko_player2` | The reverse KO order; the first processed result stays fixed. |
| `departure_before_play` | Disconnect during preparation produces cancellation. |
| `departure_during_play` | Disconnect during play gives the opponent a win. |
| `invalid_inputs` | Invalid board, boolean attack, and unknown session are rejected; planned stop cancels. |
| `delivery_failure` | An injected callback failure after finalization preserves the recorded result. |

Running eight independent fixtures demonstrates behavior; it is not a production
server that hosts multiple matches. Most scenarios inspect queued effects without
calling delivery for every event. The final scenario explicitly uses callbacks.

A heading such as `Scenario: complete_match state=FINISHED` shows the final state.
Following records show the state at each command or queued output, the participant,
occurrence, and optional reason. For a command, participant is the sender; for an
output, it is the intended recipient. An output log means **queued in memory**,
not delivered over TCP. `reason=-` means the log record has no reason field;
GAMEOVER's outcome/reason are stored in its payload and the final match result.

See [IMPLEMENTS.md](IMPLEMENTS.md) for a step-by-step trace and a runnable example
that prints an outbox and the result directly.

## Where manual implementation is needed

Four executable entry points currently raise `NotImplementedError`:

| Entry point | Work to implement |
| --- | --- |
| `NetworkServer.run()` in [network.py](src/tetris_server/network.py) | TCP listener, sequential nonblocking event loop, two connection reservations, trusted session association, input/output buffers, partial writes, failure detection, timers, final drain, and socket closure. |
| `encode(event)` in [protocol.py](src/tetris_shared/protocol.py) | Serialize outgoing events into ASCII TVP/1 lines ending in LF. Flatten BOARD into exactly 200 digits. |
| `decode(frame)` in [protocol.py](src/tetris_shared/protocol.py) | Validate exact grammar/fields and translate accepted client input into local commands. The adapter must bind the actual sender session and handle message direction/state. |
| `StreamParser.feed(data)` in [protocol.py](src/tetris_shared/protocol.py) | Keep a buffer per connection, extract all complete LF-delimited messages, retain fragments, and reject oversized input even before LF arrives. |

Implement the codec/framing first, then connection admission, dispatch integration,
output buffers, timers, shutdown, and real TCP integration tests. The detailed
manual checklist is in [IMPLEMENTS.md](IMPLEMENTS.md).

### Protocol and adapter requirements

Exactly eight wire types are reserved: `HELLO`, `MATCH`, `READY`, `BOARD`, `ATTACK`,
`KO`, `GAMEOVER`, and `KEEPALIVE`. The planned format is ASCII `TVP/1|...` with LF
termination. The existing enums/events are not a working codec.

The adapter maps HELLO to `join`, READY/PLAYER to `ready`, BOARD to `board`, ATTACK
to `attack`, and KO to `ko`. KEEPALIVE belongs to adapter activity bookkeeping;
it must not be echoed or dispatched as a new gameplay operation. Socket failure,
timeout, and protocol violation become internal `failure` commands. The adapter
must handle logged/re-raised domain errors according to the protocol policy.

| Pending rule | Default |
| --- | --- |
| Admitted connections, including those awaiting HELLO | At most 2; immediately close a third. |
| First valid HELLO deadline | 5 seconds after acceptance. |
| KEEPALIVE schedule | Every 5 seconds after HELLO, even with other traffic. |
| Inactivity timeout | 15 seconds since the last complete valid message. |
| Maximum complete line | 512 bytes including LF; also bound incomplete fragments. |
| Maximum pending output | 4096 bytes per connection. |
| Final notification drain | At most 1 second, then close and exit. |

These values are declared/documented but no network timers or byte buffers run
yet. Unidentified failures free their reservation without canceling an identified
player; identified players cannot be replaced. TCP reads/writes can be partial,
so preserve remaining bytes. Only snapshots not yet serialized may be coalesced.
The local callback `deliver()` does not implement socket writes or confirm wire
delivery. Record the result once and never change it because a notification fails.

Real networking will require new tests for framing, byte validation, partial I/O,
connection admission, deadlines, and end-to-end peers. Replace current tests that
expect stub failures when those stubs are implemented; preserve domain regressions.

## Project documents

| Document | Purpose |
| --- | --- |
| [00-contexto-geral.md](00-contexto-geral.md) | Source of truth for rules, protocol grammar, directions, state restrictions, and failure policy. |
| [02-boilerplate-servidor.md](02-boilerplate-servidor.md) | Server scope, structure, scenarios, and acceptance criteria. |
| [IMPLEMENTS.md](IMPLEMENTS.md) | Feature-to-function map, manual implementation checklist, and simulation walkthrough. |
| [AGENTS.md](AGENTS.md) | Repository guidance and constraints for future changes. |
| [Implementation plan](docs/superpowers/plans/2026-10-04-server-boilerplate.md) | Completed boilerplate plan and execution/verification record. |
