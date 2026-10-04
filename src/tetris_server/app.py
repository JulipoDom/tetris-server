"""Sequential local dispatcher and in-memory output queues.

Callbacks consume Python objects. This module performs no network I/O.
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
        """Prepare a controller, per-session output queues, and local logs."""
        self.controller = controller if controller is not None else MatchController()
        self.outboxes: dict[Hashable, list[OutboundEvent]] = {}
        self.logs: list[LocalRecord] = []

    def process(self, command: Command) -> tuple[OutboundEvent, ...]:
        """Process one fact completely before the caller supplies the next."""
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
        """Queue effects, replacing only older unconsumed board snapshots."""
        for event in events:
            queue = self.outboxes.setdefault(event.recipient, [])
            if event.kind == MessageType.BOARD:
                # Remove the stale visual and append its replacement at the
                # current position, preserving intervening attacks and GO.
                queue[:] = [pending for pending in queue if pending.kind != MessageType.BOARD]
            queue.append(event)
            self.logs.append(LocalRecord(self.controller.state, event.recipient,
                                         event.kind.value))

    def deliver(self, sender: Callable[[OutboundEvent], None]) -> None:
        """Drain local queues; callback failure becomes a disconnect fact.

        The controller has already recorded any result before delivery starts.
        A callback returning normally consumes the event; it promises no wire
        delivery. A failed recipient's remaining local outputs are cleared.
        """
        # A disconnect can enqueue a result for a recipient already visited.
        # Continue until those newly generated outputs are consumed as well.
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
