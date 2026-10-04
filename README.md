# Tetris Versus server boilerplate

Python 3.12+ local domain for exactly two players and one match per execution.
The server manages readiness, forwards garbage quantities and fixed-board
snapshots, and records one immutable result. Clients own game physics.

Read [the general context](00-contexto-geral.md) and
[the server specification](02-boilerplate-servidor.md) for the rules.
[AGENTS.md](AGENTS.md) contains repository guidance.
[IMPLEMENTS.md](IMPLEMENTS.md) maps implemented features, manual networking tasks,
and the simulation flow to the code.

Run directly from the repository without installing dependencies:

```bash
PYTHONPATH=src python -m tetris_server --mode simulated
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m tetris_server --mode network
```

The simulation runs eight local scenarios and reports state, participant,
occurrence, and reason. The network command deliberately exits with status 2
and `TODO[EP-REDE]`. No sockets, byte serialization, or timers are implemented;
this is not yet a functional TCP server.

Optional editable installation in a virtual environment enables the module
commands without `PYTHONPATH` and the `tetris_server` console command:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m tetris_server --mode simulated
.venv/bin/python -m unittest discover -s tests -v
```

Domain and tests use only the standard library. Installation uses setuptools
as a build tool. Use the same Python minor version across the team.

`MatchController` owns transitions and returns frozen output events.
`ServerApp.process(Command(...))` handles local commands sequentially, logs
effects, and queues outputs by session. Session tokens must be hashable and
stable; nickname equality does not identify a session. `ServerApp.deliver`
accepts a callback consuming Python events. Callback failure becomes a local
disconnect fact and cannot change an already recorded result. Its queues may
replace stale unconsumed board snapshots, but preserve attacks and results.

To complete the EP networking work, implement the marked stubs in
`src/tetris_server/network.py` and `src/tetris_shared/protocol.py` following
the full TVP/1 grammar, direction/state restrictions, connection limits,
partial reads/writes, buffers, and deadlines from the general context.
