"""Domínio sequencial com duas posições, sem sockets, temporizadores ou física do cliente."""

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
    """Uma operação local inválida, a ser tratada pelo adaptador."""


class MatchController:
    """Deve ser chamado por um dispatcher sequencial; cada chamada retorna todos os seus efeitos."""

    def __init__(self):
        """Cria duas posições vazias de jogador, sem decisão final."""
        self._state = MatchState.WAITING
        self._result: MatchResult | None = None
        self._players: list[Player | None] = [None, None]

    @property
    def state(self) -> MatchState:
        """Expõe a fase atual sem permitir atribuição externa."""
        return self._state

    @property
    def result(self) -> MatchResult | None:
        """Retorna a decisão final imutável, ou None enquanto não houver encerramento."""
        return self._result

    @property
    def player1(self) -> Player | None:
        """Retorna o registro imutável do participante da primeira posição."""
        return self._players[0]

    @property
    def player2(self) -> Player | None:
        """Retorna o registro imutável do participante da segunda posição."""
        return self._players[1]

    @staticmethod
    def _validate_session(session):
        """Exige uma referência de sessão utilizável como chave do dicionário de saídas."""
        try:
            hash(session)
        except TypeError as error:
            raise DomainError("Sessão deve permitir identificação por chave") from error

    def _index(self, session) -> int:
        """Localiza a posição registrada; rejeita sessões de participantes desconhecidas."""
        self._validate_session(session)
        for index, player in enumerate(self._players):
            if player is not None and player.session == session:
                return index
        raise DomainError("Sessão de participante desconhecida")

    def _require_playing(self):
        """Impede efeitos de jogo antes do início autorizado para ambos os jogadores."""
        if self.state != MatchState.PLAYING:
            raise DomainError("Operação exige uma partida ativa")

    def _playing_index(self, session: Hashable) -> int | None:
        """Valida o participante e ignora efeitos tardios sem reabrir a partida."""
        index = self._index(session)
        if self.state == MatchState.FINISHED:
            return None
        self._require_playing()
        return index

    def join(self, session: Hashable, nickname: str) -> tuple[OutboundEvent, ...]:
        """Registra um jogador e emite MATCH quando ambas as posições estão ocupadas."""
        self._validate_session(session)
        if self.state == MatchState.FINISHED:
            raise DomainError("A partida atual já está encerrada")
        if any(p is not None and p.session == session for p in self._players):
            raise DomainError("Sessão já está identificada")
        if not isinstance(nickname, str) or re.fullmatch(NICKNAME_PATTERN, nickname) is None:
            raise DomainError("Apelido deve ter 1 a 20 letras ASCII, números ou underscore")
        if all(p is not None for p in self._players):
            raise DomainError("As duas posições de jogadores estão ocupadas")
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
        """Registra prontidão e emite um GO por jogador quando ambos estão prontos."""
        index = self._index(session)
        if self.state in (MatchState.FINISHED, MatchState.PLAYING):
            return ()
        if self.state != MatchState.PREPARING:
            raise DomainError("Prontidão exige os dois participantes identificados")
        self._players[index] = replace(self._players[index], ready=True)
        if not all(player.ready for player in self._players):
            return ()
        self._state = MatchState.PLAYING
        return tuple(OutboundEvent(p.session, MessageType.READY, "GO") for p in self._players)

    def attack(self, session: Hashable, quantity: int) -> tuple[OutboundEvent, ...]:
        """Valida a quantidade de lixo e a encaminha sem alteração ao oponente."""
        index = self._playing_index(session)
        if index is None:
            return ()
        if type(quantity) is not int or quantity not in ATTACK_QUANTITIES:
            raise DomainError("Quantidade de ataque deve ser o inteiro 1, 2 ou 4")
        return (OutboundEvent(self._players[1 - index].session, MessageType.ATTACK, quantity),)

    @staticmethod
    def _snapshot(cells) -> Snapshot:
        """Valida o tabuleiro 20x10 e copia suas células para linhas imutáveis."""
        if not isinstance(cells, Sequence) or isinstance(cells, (str, bytes)) or len(cells) != BOARD_ROWS:
            raise DomainError("Tabuleiro deve ter 20 linhas")
        rows = []
        for row in cells:
            if not isinstance(row, Sequence) or isinstance(row, (str, bytes)) or len(row) != BOARD_COLUMNS:
                raise DomainError("Cada linha do tabuleiro deve ter 10 células")
            if any(type(cell) is not int or not MIN_CELL <= cell <= MAX_CELL for cell in row):
                raise DomainError("Células do tabuleiro devem ser inteiros entre 0 e 8")
            rows.append(tuple(row))
        return tuple(rows)

    def board(self, session: Hashable, cells) -> tuple[OutboundEvent, ...]:
        """Armazena o tabuleiro fixo mais recente do remetente e o emite ao oponente."""
        index = self._playing_index(session)
        if index is None:
            return ()
        snapshot = self._snapshot(cells)
        self._players[index] = replace(self._players[index], snapshot=snapshot)
        return (OutboundEvent(self._players[1 - index].session, MessageType.BOARD, snapshot),)

    def _finish(self, reason: EndReason, outcomes, recipients) -> tuple[OutboundEvent, ...]:
        """Registra a decisão antes de produzir GAMEOVER para cada destinatário."""
        # Registra a decisão antes de construir qualquer saída para o adaptador.
        self._result = MatchResult(reason, tuple(outcomes))
        self._state = MatchState.FINISHED
        return tuple(OutboundEvent(session, MessageType.GAMEOVER,
                                   GameOver(self.result.outcome_for(session), reason))
                     for session in recipients)

    def ko(self, session: Hashable, cause: str) -> tuple[OutboundEvent, ...]:
        """Finaliza uma derrota local; KO antes do jogo vira falha de protocolo."""
        index = self._index(session)
        if self.state == MatchState.FINISHED:
            return ()
        if not isinstance(cause, str) or cause not in KO_CAUSES:
            raise DomainError("Causa de nocaute deve ser SPAWN, OVERFLOW ou INACTIVITY")
        if self.state != MatchState.PLAYING:
            return self.failure(session, EndReason.PROTOCOL)
        opponent = self._players[1 - index].session
        return self._finish(EndReason.KO,
                            ((opponent, Outcome.WIN), (session, Outcome.LOSE)),
                            (opponent, session))

    def failure(self, session: Hashable, reason: EndReason) -> tuple[OutboundEvent, ...]:
        """Cancela antes do jogo ou concede vitória ao oponente diante de um fato de falha."""
        index = self._index(session)
        if self.state == MatchState.FINISHED:
            return ()
        try:
            reason = EndReason(reason)
        except (ValueError, TypeError) as error:
            raise DomainError("Motivo de falha do participante inválido") from error
        if reason not in (EndReason.DISCONNECT, EndReason.TIMEOUT, EndReason.PROTOCOL):
            raise DomainError("Motivo de falha do participante inválido")
        opponent = self._players[1 - index]
        if self.state == MatchState.PLAYING:
            outcomes = ((opponent.session, Outcome.WIN), (session, Outcome.LOSE))
        else:
            outcomes = tuple((p.session, Outcome.CANCEL) for p in self._players if p is not None)
        recipients = (opponent.session,) if opponent is not None else ()
        return self._finish(reason, outcomes, recipients)

    def stop(self) -> tuple[OutboundEvent, ...]:
        """Cancela uma execução em andamento sem substituir um resultado existente."""
        if self.state == MatchState.FINISHED:
            return ()
        sessions = tuple(p.session for p in self._players if p is not None)
        return self._finish(EndReason.SERVER_STOP,
                            ((session, Outcome.CANCEL) for session in sessions), sessions)
