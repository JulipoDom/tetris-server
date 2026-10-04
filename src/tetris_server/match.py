"""Sequential two-slot domain; no sockets, timers, or client physics."""

import re
from collections.abc import Hashable, Sequence
from dataclasses import replace

from tetris_shared.models import (
    EndReason, GameOver, MatchResult, MatchState, MessageType,
    Outcome, OutboundEvent, Player, Snapshot,
)
from tetris_shared.rules import (
    ATTACK_QUANTITIES, BOARD_COLUMNS, BOARD_ROWS, KO_CAUSES,
    MAX_CELL, MIN_CELL, NICKNAME_PATTERN,
)


class DomainError(ValueError):
    """An invalid local operation, for the adapter to handle."""


class MatchController:
    """Call from one sequential dispatcher; each call returns all its effects."""

    def __init__(self):
        """Create two empty player slots with no final decision."""
        self._state = MatchState.WAITING
        self._result: MatchResult | None = None
        self._players: list[Player | None] = [None, None]

    @property
    def state(self) -> MatchState:
        """Expose the current phase without allowing external assignment."""
        return self._state

    @property
    def result(self) -> MatchResult | None:
        """Return the fixed final decision, or None while unfinished."""
        return self._result

    @property
    def player1(self) -> Player | None:
        """Return the first slot's immutable participant record."""
        return self._players[0]

    @property
    def player2(self) -> Player | None:
        """Return the second slot's immutable participant record."""
        return self._players[1]

    @staticmethod
    def _validate_session(session):
        """Require a session token usable as an outbox dictionary key."""
        try:
            hash(session)
        except TypeError as error:
            raise DomainError("Session must be hashable") from error

    def _index(self, session) -> int:
        """Find the registered slot; reject unknown participant sessions."""
        self._validate_session(session)
        for index, player in enumerate(self._players):
            if player is not None and player.session == session:
                return index
        raise DomainError("Unknown participant session")

    def _require_playing(self):
        """Prevent gameplay effects before both players have started."""
        if self.state != MatchState.PLAYING:
            raise DomainError("Operation requires an active match")

    def join(self, session: Hashable, nickname: str) -> tuple[OutboundEvent, ...]:
        """Register a player and emit MATCH when both slots are occupied."""
        self._validate_session(session)
        if self.state == MatchState.FINISHED:
            raise DomainError("This execution's match is finished")
        if any(p is not None and p.session == session for p in self._players):
            raise DomainError("Session is already identified")
        if not isinstance(nickname, str) or re.fullmatch(NICKNAME_PATTERN, nickname) is None:
            raise DomainError("Nickname must contain 1-20 ASCII letters, digits, or underscores")
        if all(p is not None for p in self._players):
            raise DomainError("The two participant positions are occupied")
        index = 0 if self.player1 is None else 1
        self._players[index] = Player(session, nickname)
        if self.player2 is None:
            return ()
        self._state = MatchState.PREPARING
        return (
            OutboundEvent(self.player1.session, MessageType.MATCH, self.player2.nickname),
            OutboundEvent(self.player2.session, MessageType.MATCH, self.player1.nickname),
        )

    def ready(self, session: Hashable) -> tuple[OutboundEvent, ...]:
        """Mark readiness and emit one GO per player when both are ready."""
        index = self._index(session)
        if self.state in (MatchState.FINISHED, MatchState.PLAYING):
            return ()
        if self.state != MatchState.PREPARING:
            raise DomainError("Readiness requires both identified participants")
        self._players[index] = replace(self._players[index], ready=True)
        if not all(player.ready for player in self._players):
            return ()
        self._state = MatchState.PLAYING
        return tuple(OutboundEvent(p.session, MessageType.READY, "GO") for p in self._players)

    def attack(self, session: Hashable, quantity: int) -> tuple[OutboundEvent, ...]:
        """Validate garbage quantity and forward it unchanged to the opponent."""
        index = self._index(session)
        if self.state == MatchState.FINISHED:
            return ()
        self._require_playing()
        if type(quantity) is not int or quantity not in ATTACK_QUANTITIES:
            raise DomainError("Attack quantity must be integer 1, 2, or 4")
        return (OutboundEvent(self._players[1 - index].session, MessageType.ATTACK, quantity),)

    @staticmethod
    def _snapshot(cells) -> Snapshot:
        """Validate the 20x10 board and copy its cells into immutable rows."""
        if not isinstance(cells, Sequence) or isinstance(cells, (str, bytes)) or len(cells) != BOARD_ROWS:
            raise DomainError("Board must have 20 rows")
        rows = []
        for row in cells:
            if not isinstance(row, Sequence) or isinstance(row, (str, bytes)) or len(row) != BOARD_COLUMNS:
                raise DomainError("Each board row must have 10 cells")
            if any(type(cell) is not int or not MIN_CELL <= cell <= MAX_CELL for cell in row):
                raise DomainError("Board cells must be integers from 0 through 8")
            rows.append(tuple(row))
        return tuple(rows)

    def board(self, session: Hashable, cells) -> tuple[OutboundEvent, ...]:
        """Store the sender's latest fixed board and emit it to the opponent."""
        index = self._index(session)
        if self.state == MatchState.FINISHED:
            return ()
        self._require_playing()
        snapshot = self._snapshot(cells)
        self._players[index] = replace(self._players[index], snapshot=snapshot)
        return (OutboundEvent(self._players[1 - index].session, MessageType.BOARD, snapshot),)

    def _finish(self, reason: EndReason, outcomes, recipients) -> tuple[OutboundEvent, ...]:
        """Record the decision before producing each recipient's GAMEOVER."""
        # Commit the decision before constructing any output for the adapter.
        self._result = MatchResult(reason, tuple(outcomes))
        self._state = MatchState.FINISHED
        return tuple(OutboundEvent(session, MessageType.GAMEOVER,
                                   GameOver(self.result.outcome_for(session), reason))
                     for session in recipients)

    def ko(self, session: Hashable, cause: str) -> tuple[OutboundEvent, ...]:
        """Finalize a local loss; a KO before play becomes a protocol failure."""
        index = self._index(session)
        if self.state == MatchState.FINISHED:
            return ()
        if not isinstance(cause, str) or cause not in KO_CAUSES:
            raise DomainError("KO cause must be SPAWN or OVERFLOW")
        if self.state != MatchState.PLAYING:
            return self.failure(session, EndReason.PROTOCOL)
        opponent = self._players[1 - index].session
        return self._finish(EndReason.KO,
                            ((opponent, Outcome.WIN), (session, Outcome.LOSE)),
                            (opponent, session))

    def failure(self, session: Hashable, reason: EndReason) -> tuple[OutboundEvent, ...]:
        """Cancel before play or award the opponent a win for a failure fact."""
        index = self._index(session)
        if self.state == MatchState.FINISHED:
            return ()
        try:
            reason = EndReason(reason)
        except (ValueError, TypeError) as error:
            raise DomainError("Invalid participant failure reason") from error
        if reason not in (EndReason.DISCONNECT, EndReason.TIMEOUT, EndReason.PROTOCOL):
            raise DomainError("Invalid participant failure reason")
        opponent = self._players[1 - index]
        if self.state == MatchState.PLAYING:
            outcomes = ((opponent.session, Outcome.WIN), (session, Outcome.LOSE))
        else:
            outcomes = tuple((p.session, Outcome.CANCEL) for p in self._players if p is not None)
        recipients = (opponent.session,) if opponent is not None else ()
        return self._finish(reason, outcomes, recipients)

    def stop(self) -> tuple[OutboundEvent, ...]:
        """Cancel a running execution without replacing an existing result."""
        if self.state == MatchState.FINISHED:
            return ()
        sessions = tuple(p.session for p in self._players if p is not None)
        return self._finish(EndReason.SERVER_STOP,
                            ((session, Outcome.CANCEL) for session in sessions), sessions)
