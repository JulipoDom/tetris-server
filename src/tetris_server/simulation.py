"""Cenários repetíveis usando somente objetos locais, sem serialização."""

from dataclasses import dataclass

from tetris_shared.models import Command, EndReason, MatchResult, MatchState, Outcome
from .app import LocalRecord, ServerApp
from .match import DomainError


@dataclass(frozen=True)
class ScenarioReport:
    name: str
    state: MatchState
    result: MatchResult | None
    logs: tuple[LocalRecord, ...]


def _pair() -> ServerApp:
    """Cria uma nova partida local com duas identidades de participantes predefinidas."""
    app = ServerApp()
    app.process(Command('join', 'player1', 'Jogador_A'))
    app.process(Command('join', 'player2', 'Jogador_B'))
    return app


def _start(app: ServerApp) -> None:
    """Registra a prontidão de cada participante para autorizar a partida local."""
    app.process(Command('ready', 'player1'))
    app.process(Command('ready', 'player2'))


def _expect_rejection(app: ServerApp, command: Command) -> None:
    """Exige que a entrada inválida do cenário gere o erro de domínio esperado."""
    try:
        app.process(command)
    except DomainError:
        return
    raise AssertionError(f'Scenario expected rejection: {command.operation}')


def _report(name: str, app: ServerApp) -> ScenarioReport:
    """Captura o estado final, o resultado e os registros do cenário."""
    return ScenarioReport(name, app.controller.state, app.controller.result, tuple(app.logs))


def run_simulations() -> tuple[ScenarioReport, ...]:
    """Executa oito cenários predefinidos e isolados pelo dispatcher local real."""
    reports = []

    app = _pair()
    _start(app)
    app.process(Command('attack', 'player1', 2))
    board = [[0] * 10 for _ in range(20)]
    board[19][0] = 8
    app.process(Command('board', 'player1', board))
    app.process(Command('ko', 'player1', 'SPAWN'))
    reports.append(_report('complete_match', app))

    app = _pair()
    _expect_rejection(app, Command('join', 'third', 'Jogador_C'))
    _start(app)
    app.process(Command('ko', 'player2', 'OVERFLOW'))
    reports.append(_report('third_participant_refused', app))

    for loser in ('player1', 'player2'):
        app = _pair()
        app.process(Command('ready', 'player1'))
        app.process(Command('ready', 'player1'))
        app.process(Command('ready', 'player2'))
        app.process(Command('ready', 'player2'))
        app.process(Command('ko', loser, 'SPAWN'))
        result = app.controller.result
        other = 'player2' if loser == 'player1' else 'player1'
        app.process(Command('ko', other, 'OVERFLOW'))
        assert app.controller.result is result
        assert result.outcome_for(loser) == Outcome.LOSE
        reports.append(_report(f'first_ko_{loser}', app))

    for started in (False, True):
        app = _pair()
        if started:
            _start(app)
        app.process(Command('failure', 'player1', EndReason.DISCONNECT))
        reports.append(_report('departure_during_play' if started else 'departure_before_play', app))

    app = _pair()
    _start(app)
    _expect_rejection(app, Command('board', 'player1', [[0] * 10]))
    _expect_rejection(app, Command('attack', 'player1', True))
    _expect_rejection(app, Command('attack', 'unknown', 2))
    app.process(Command('stop'))
    reports.append(_report('invalid_inputs', app))

    app = _pair()
    _start(app)
    app.deliver(lambda event: None)
    app.process(Command('ko', 'player1', 'OVERFLOW'))
    result = app.controller.result

    def unavailable(event):
        """Injeta falha de entrega para player1, permitindo as saídas de player2."""
        if event.recipient == 'player1':
            raise OSError('Simulated local delivery failure')

    app.deliver(unavailable)
    assert app.controller.result is result
    reports.append(_report('delivery_failure', app))
    return tuple(reports)
