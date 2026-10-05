"""Dispatcher local sequencial e filas de saída em memória.

As funções de retorno consomem objetos Python. Este módulo não realiza E/S de rede.
"""

from collections.abc import Callable, Hashable
from dataclasses import dataclass

from tetris_shared.models import Command, EndReason, MatchState, MessageType, OutboundEvent
from .match import DomainError, MatchController


@dataclass(frozen=True)
class LocalRecord:
    state: MatchState
    participant: Hashable | None
    occurrence: str
    reason: str = ''


class ServerApp:
    def __init__(self, controller: MatchController | None = None):
        """Prepara um controlador, filas de saída por sessão e registros locais."""
        self.controller = controller if controller is not None else MatchController()
        self.outboxes: dict[Hashable, list[OutboundEvent]] = {}
        self.logs: list[LocalRecord] = []

    def process(self, command: Command) -> tuple[OutboundEvent, ...]:
        """Processa um fato por completo antes de receber o próximo."""
        operations = {
            'join': lambda: self.controller.join(command.session, command.payload),
            'ready': lambda: self.controller.ready(command.session),
            'attack': lambda: self.controller.attack(command.session, command.payload),
            'board': lambda: self.controller.board(command.session, command.payload),
            'ko': lambda: self.controller.ko(command.session, command.payload),
            'failure': lambda: self.controller.failure(command.session, command.payload),
            'stop': self.controller.stop,
        }
        if command.operation not in operations:
            raise ValueError(f'Unknown local operation: {command.operation}')
        try:
            events = operations[command.operation]()
        except DomainError as error:
            self.logs.append(LocalRecord(self.controller.state, command.session,
                                         'rejected', str(error)))
            raise
        reason = ''
        if self.controller.result is not None:
            reason = self.controller.result.reason.value
        self.logs.append(LocalRecord(self.controller.state, command.session,
                                     command.operation, reason))
        self._enqueue(events)
        return events

    def _enqueue(self, events: tuple[OutboundEvent, ...]) -> None:
        """Enfileira efeitos, substituindo apenas cópias antigas de tabuleiro não consumidas."""
        for event in events:
            queue = self.outboxes.setdefault(event.recipient, [])
            if event.kind == MessageType.BOARD:
                # Remove a imagem antiga e acrescenta sua substituta na
                # posição atual, preservando os ataques intermediários e GO.
                queue[:] = [pending for pending in queue if pending.kind != MessageType.BOARD]
            queue.append(event)
            self.logs.append(LocalRecord(self.controller.state, event.recipient,
                                         event.kind.value))

    def deliver(self, sender: Callable[[OutboundEvent], None]) -> None:
        """Esvazia as filas locais; falha da função de retorno vira um fato de desconexão.

        O controlador já registrou qualquer resultado antes de iniciar a entrega.
        Uma função de retorno que termina normalmente consome o evento; ela não garante
        entrega pela rede. As saídas locais restantes do destinatário com falha são removidas.
        """
        # Uma desconexão pode enfileirar um resultado para um destinatário já visitado.
        # Continua até consumir também essas novas saídas.
        while any(self.outboxes.values()):
            for session, queue in list(self.outboxes.items()):
                while queue:
                    event = queue.pop(0)
                    try:
                        sender(event)
                    except Exception as error:
                        queue.clear()
                        self.logs.append(LocalRecord(self.controller.state, session,
                                                     'delivery_failure', str(error)))
                        self.process(Command('failure', session, EndReason.DISCONNECT))
                        break
