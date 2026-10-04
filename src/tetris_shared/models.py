"""Typed Python objects exchanged by the domain and local adapter."""

from collections.abc import Hashable
from dataclasses import dataclass
from enum import StrEnum


class MessageType(StrEnum):
    HELLO = "HELLO"
    MATCH = "MATCH"
    READY = "READY"
    BOARD = "BOARD"
    ATTACK = "ATTACK"
    KO = "KO"
    GAMEOVER = "GAMEOVER"
    KEEPALIVE = "KEEPALIVE"


class MatchState(StrEnum):
    WAITING = "WAITING"
    PREPARING = "PREPARING"
    PLAYING = "PLAYING"
    FINISHED = "FINISHED"


class Outcome(StrEnum):
    WIN = "WIN"
    LOSE = "LOSE"
    CANCEL = "CANCEL"


class EndReason(StrEnum):
    KO = "KO"
    DISCONNECT = "DISCONNECT"
    TIMEOUT = "TIMEOUT"
    PROTOCOL = "PROTOCOL"
    SERVER_STOP = "SERVER_STOP"


Snapshot = tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class Player:
    session: Hashable
    nickname: str
    ready: bool = False
    snapshot: Snapshot | None = None


@dataclass(frozen=True)
class GameOver:
    outcome: Outcome
    reason: EndReason


@dataclass(frozen=True)
class MatchResult:
    reason: EndReason
    outcomes: tuple[tuple[Hashable, Outcome], ...]

    def outcome_for(self, session: Hashable) -> Outcome:
        """Look up a participant's stored outcome; unknown sessions raise KeyError."""
        for participant, outcome in self.outcomes:
            if participant == session:
                return outcome
        raise KeyError(session)


@dataclass(frozen=True)
class OutboundEvent:
    recipient: Hashable
    kind: MessageType
    payload: object = None


@dataclass(frozen=True)
class Command:
    operation: str
    session: Hashable | None = None
    payload: object = None
