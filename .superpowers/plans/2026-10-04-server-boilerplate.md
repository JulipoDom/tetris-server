# Server Boilerplate Implementation Plan

> **For agentic workers:** Use Superpowers TDD and verification-before-completion. The user requested agents and authorized implementation from the supplied specification.

**Goal:** Deliver the documented local server and repository guidance.

**Architecture:** Frozen shared events and results, a two-slot domain controller, and a sequential application dispatcher. Simulations exchange Python objects; network and protocol adapters raise `NotImplementedError`.

**Tech Stack:** Python >=3.12, standard library, unittest; src packages.

**Spec:** `00-contexto-geral.md` and `02-boilerplate-servidor.md` (user-supplied design).

## Global constraints

Exactly two participants and one match per execution. Eight message types only. No physics, sockets, codec, database, or third-party runtime dependency. Networking stays `TODO[EP-REDE]`. The directory is not a usable Git checkout; do not create worktrees or commits.

## Interfaces

Shared models: `MessageType`, `MatchState`, `Outcome`, `EndReason`, `GameOver(outcome, reason)`, `OutboundEvent(recipient, kind, payload)`, `Command(operation, session=None, payload=None)`, frozen `MatchResult` with per-session outcomes. Sessions are opaque hashable tokens. BOARD payloads are tuples of tuples.

`MatchController`: read-only `state`, `result`, `player1`, `player2`; methods `join(session, nickname)`, `ready(session)`, `attack(session, quantity)`, `board(session, cells)`, `ko(session, cause)`, `failure(session, reason)`, `stop()` return tuples of `OutboundEvent`. Invalid inputs raise `DomainError`; final-state known-participant events return no effects.

`ServerApp.process(command)` dispatches those methods, records local logs and outboxes, and returns outputs. `deliver(sender)` drains outboxes via a callback and records delivery failures without changing a finalized result; a delivery failure before finalization becomes a DISCONNECT fact. No hidden fake fallback.

## Review focus

- Boolean and noninteger board/attack inputs must fail validation.
- Mutable caller boards must not mutate emitted snapshots.
- Unknown sessions and duplicate HELLO cannot replace participants.
- Initial GO events must precede forwarded game events, including snapshot coalescing.
- Delivery failure after a terminal decision cannot create a second result.

## Tasks

### 1. Shared models and domain (agent)

- [x] Write lifecycle, validation, forwarding, and failure tests in `tests/test_server.py`; run to observe missing implementation.
- [x] Implement `src/tetris_shared/{__init__,models,rules}.py` and `src/tetris_server/{__init__,match}.py` against the interfaces above.
- [x] Run `PYTHONPATH=src python -m unittest discover -s tests -p test_server.py -v`; expect all domain tests to pass.

### 2. Application, simulations, stubs, and CLI (root)

- [x] Write `tests/test_app.py` for sequential outputs, delivery failures, snapshot coalescing, simulations, and explicit network/codec failure. Observe failures before implementing.
- [x] Implement `app.py`, `simulation.py`, `network.py`, `__main__.py`, and `tetris_shared/protocol.py`.
- [x] Add `pyproject.toml`, README commands, `.gitignore`; configure package discovery with standard packaging metadata and document PYTHONPATH execution without installation.
- [x] Run all tests and both CLI modes; simulated succeeds, network exits nonzero with `TODO[EP-REDE]`.

### 3. Review and final context

- [x] Obtain an independent read-only code review against both source specifications.
- [x] Resolve material findings with regression tests and rerun the suite.
- [x] Update `AGENTS.md` to describe actual implementation and verify documented commands.

## Execution record

- User supplied the complete design and explicitly selected guidance plus implementation; proceed without repeating scope approval.
- Git is unavailable in this directory; changes are made in place, without commits/worktree operations.

- Task 1: complete; 18 domain tests observed red before implementation, then green.
- Task 2: complete; application imports failed before implementation; initial full suite passed 28 tests.
- Review finding: second-recipient delivery failure stranded the survivor result. A symmetric regression failed before the queue-drain fix, then passed.
- Task 3: complete; independent review approved local scope. Final suite: 30 tests pass on Python 3.14.8. Eight simulated CLI scenarios finish; network CLI exits 2 with TODO[EP-REDE].
- Editable installation and Python 3.12 execution were not exercised; direct source execution was verified.
