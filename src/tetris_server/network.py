"""Servidor TCP TVP/1 para uma partida ativa e partidas sequenciais."""

import selectors
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Event

from tetris_shared.models import Command, EndReason, MatchState, MessageType, OutboundEvent
from tetris_shared.protocol import Framer, encode, parse

from .app import ServerApp
from .match import DomainError


HELLO_SECONDS = 5
IDLE_SECONDS = 15
KEEPALIVE_SECONDS = 5
DRAIN_SECONDS = 1
REMATCH_SECONDS = 10
OUTPUT_LIMIT = 4096
ACCEPTS_PER_CYCLE = 32


def command_from_frame(session, kind: MessageType, fields: tuple[str, ...]) -> Command | None:
    """Converte uma mensagem do cliente em ação do domínio, sem aceitar direção inversa."""
    if kind == MessageType.HELLO:
        return Command('join', session, fields[0])
    if kind == MessageType.READY and fields == ('PLAYER',):
        return Command('ready', session)
    if kind == MessageType.BOARD:
        cells = fields[0]
        return Command('board', session, [list(map(int, cells[i:i + 10]))
                                          for i in range(0, 200, 10)])
    if kind == MessageType.ATTACK:
        return Command('attack', session, int(fields[0]))
    if kind == MessageType.KO:
        return Command('ko', session, fields[0])
    if kind == MessageType.KEEPALIVE:
        return None
    raise ValueError('Mensagem não permitida do cliente para o servidor')


def event_frame(event: OutboundEvent) -> bytes:
    """Codifica eventos do controlador com os campos definidos no TVP/1."""
    if event.kind in (MessageType.MATCH, MessageType.READY):
        fields = (event.payload,)
    elif event.kind == MessageType.BOARD:
        fields = (''.join(str(cell) for row in event.payload for cell in row),)
    elif event.kind == MessageType.ATTACK:
        fields = (str(event.payload),)
    elif event.kind == MessageType.GAMEOVER:
        fields = (event.payload.outcome.value, event.payload.reason.value)
    else:
        raise ValueError('Evento não permitido do servidor para o cliente')
    return encode(event.kind, fields)


class PendingOutput:
    """Guarda bytes ainda não enviados e preserva a ordem em escritas parciais."""

    def __init__(self):
        """Prepara o estado local sem abrir sockets."""
        self.pending = bytearray()

    def queue(self, data: bytes) -> None:
        """Acumula bytes de saída respeitando o limite por conexão."""
        if len(self.pending) + len(data) > OUTPUT_LIMIT:
            raise OverflowError('Fila de saída TCP excedeu 4096 bytes')
        self.pending.extend(data)

    def flush(self, connection: socket.socket) -> None:
        """Envia parcialmente e conserva os bytes que ainda faltam."""
        if not self.pending:
            return
        sent = connection.send(self.pending)
        if sent == 0:
            raise OSError('Conexão fechada durante envio')
        del self.pending[:sent]


@dataclass
class _Connection:
    sock: socket.socket
    accepted_at: float
    last_valid: float
    last_keepalive: float
    identified: bool = False
    framer: Framer = field(default_factory=Framer)
    output: PendingOutput = field(default_factory=PendingOutput)


class NetworkServer:
    """Despacha todos os fatos de rede numa só thread e conserva uma decisão por partida."""

    def __init__(self, app: ServerApp | None = None, host: str = '127.0.0.1',
                 port: int = 8765):
        """Prepara o estado local sem abrir sockets."""
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError('Porta TCP deve estar entre 0 e 65535')
        self.app = app if app is not None else ServerApp()
        self.host = host
        self.port = port
        self.bound_port: int | None = None
        self.listening = Event()
        self.start_error: OSError | None = None
        self._stop = Event()
        self._selector: selectors.BaseSelector | None = None
        self._listener: socket.socket | None = None
        self._clients: dict[socket.socket, _Connection] = {}
        self._drain_deadline: float | None = None
        self._rematch_deadline: float | None = None
        self._rematch_votes: set[socket.socket] = set()

    def stop(self) -> None:
        """Solicita encerramento planejado; o laço fecha os sockets após o escoamento."""
        self._stop.set()

    def _close(self, connection: _Connection) -> None:
        """Remove a conexão do seletor e libera o socket."""
        self._clients.pop(connection.sock, None)
        try:
            self._selector.unregister(connection.sock)
        except (KeyError, ValueError, OSError):
            pass
        connection.sock.close()

    def _fail(self, connection: _Connection, reason: EndReason) -> None:
        """Fecha a conexão e informa a falha ao despacho sequencial."""
        identified = connection.identified
        self._close(connection)
        if self.app.controller.state == MatchState.FINISHED:
            self._rematch_deadline = None
            self._rematch_votes.clear()
            self._drain_deadline = time.monotonic() + DRAIN_SECONDS
        if identified and self.app.controller.state != MatchState.FINISHED:
            self.app.process(Command('failure', connection.sock, reason))
            self._deliver()

    def _queue(self, connection: _Connection, data: bytes) -> None:
        """Agenda bytes e habilita a escrita no seletor."""
        connection.output.queue(data)
        self._selector.modify(connection.sock, selectors.EVENT_READ | selectors.EVENT_WRITE,
                              connection)

    def _queue_event(self, event: OutboundEvent) -> None:
        """Localiza o destinatário e transforma o evento em frame TCP."""
        connection = self._clients.get(event.recipient)
        if connection is None:
            raise OSError('Destinatário desconectado')
        try:
            self._queue(connection, event_frame(event))
        except (OSError, OverflowError):
            self._close(connection)
            raise

    def _deliver(self) -> None:
        """Escoa eventos e inicia o prazo de revanche ou de fechamento."""
        self.app.deliver(self._queue_event)
        if self.app.controller.state == MatchState.FINISHED and self._drain_deadline is None:
            now = time.monotonic()
            self._drain_deadline = now + DRAIN_SECONDS
            if (not self._stop.is_set() and len(self._clients) == 2
                    and self.app.controller.result.reason == EndReason.KO):
                self._rematch_deadline = now + REMATCH_SECONDS

    def _request_rematch(self, connection: _Connection) -> None:
        """Reinicia apenas com dois votos no prazo, preservando sockets e apelidos."""
        if (self._rematch_deadline is None or time.monotonic() >= self._rematch_deadline
                or self._stop.is_set()):
            return
        self._rematch_votes.add(connection.sock)
        if len(self._rematch_votes) != 2:
            return
        players = (self.app.controller.player1, self.app.controller.player2)
        self.app = ServerApp()
        for player in players:
            self.app.process(Command('join', player.session, player.nickname))
        # A dupla já se conhece; somente GO é necessário para a nova rodada.
        self.app.outboxes.clear()
        for player in players:
            self.app.process(Command('ready', player.session))
        self._drain_deadline = None
        self._rematch_deadline = None
        self._rematch_votes.clear()
        self._deliver()

    def _accept(self) -> None:
        # Uma rajada de tentativas não deve monopolizar o dispatcher da partida.
        """Admite até dois sockets sem deixar uma rajada bloquear o jogo."""
        for _ in range(ACCEPTS_PER_CYCLE):
            if self._stop.is_set():
                return
            try:
                sock, _ = self._listener.accept()
            except BlockingIOError:
                return
            except OSError:
                if self._stop.is_set():
                    return
                raise
            if len(self._clients) >= 2 or self.app.controller.state == MatchState.FINISHED:
                sock.close()
                continue
            sock.setblocking(False)
            now = time.monotonic()
            connection = _Connection(sock, now, now, now)
            self._clients[sock] = connection
            self._selector.register(sock, selectors.EVENT_READ, connection)

    def _handle_line(self, connection: _Connection, line: bytes) -> None:
        """Valida identificação, direção e escolha de revanche antes do despacho."""
        try:
            kind, fields = parse(line)
            if not connection.identified and kind != MessageType.HELLO:
                raise ValueError('HELLO deve ser a primeira mensagem')
            if connection.identified and kind == MessageType.HELLO:
                raise ValueError('HELLO duplicado')
            if kind == MessageType.READY and fields == ('REMATCH',):
                if self.app.controller.state != MatchState.FINISHED:
                    raise ValueError('Revanche exige uma partida encerrada')
                self._request_rematch(connection)
                connection.last_valid = time.monotonic()
                return
            command = command_from_frame(connection.sock, kind, fields)
            if command is not None:
                self.app.process(command)
                if command.operation == 'join':
                    connection.identified = True
                    connection.last_keepalive = time.monotonic()
            connection.last_valid = time.monotonic()
            self._deliver()
        except (ValueError, DomainError):
            self._fail(connection, EndReason.PROTOCOL)

    def _read(self, connection: _Connection) -> None:
        """Preserva fragmentos TCP e processa cada linha completa em ordem."""
        try:
            data = connection.sock.recv(4096)
        except BlockingIOError:
            return
        except OSError:
            self._fail(connection, EndReason.DISCONNECT)
            return
        if not data:
            self._fail(connection, EndReason.DISCONNECT)
            return
        start = 0
        while start < len(data):
            newline = data.find(b'\n', start)
            end = len(data) if newline == -1 else newline + 1
            try:
                lines = connection.framer.feed(data[start:end])
            except ValueError:
                self._fail(connection, EndReason.PROTOCOL)
                return
            for line in lines:
                self._handle_line(connection, line)
                if connection.sock not in self._clients:
                    return
            start = end

    def _write(self, connection: _Connection) -> None:
        """Retoma envios parciais e desabilita escrita quando a fila esvazia."""
        try:
            connection.output.flush(connection.sock)
            if not connection.output.pending:
                self._selector.modify(connection.sock, selectors.EVENT_READ, connection)
        except BlockingIOError:
            pass
        except OSError:
            self._fail(connection, EndReason.DISCONNECT)

    def _tick(self) -> None:
        """Aplica os prazos de identificação, conexão e encerramento da rodada."""
        now = time.monotonic()
        for connection in tuple(self._clients.values()):
            if connection.sock not in self._clients:
                continue
            if self.app.controller.state == MatchState.FINISHED:
                continue
            if not connection.identified:
                if now - connection.accepted_at >= HELLO_SECONDS:
                    self._fail(connection, EndReason.TIMEOUT)
                continue
            if now - connection.last_valid >= IDLE_SECONDS:
                self._fail(connection, EndReason.TIMEOUT)
            elif now - connection.last_keepalive >= KEEPALIVE_SECONDS:
                try:
                    self._queue(connection, encode(MessageType.KEEPALIVE, ()))
                    connection.last_keepalive = now
                except (OSError, OverflowError):
                    self._fail(connection, EndReason.DISCONNECT)
        if self.app.controller.state == MatchState.FINISHED:
            if self._drain_deadline is None:
                self._drain_deadline = now + DRAIN_SECONDS
            waiting = self._rematch_deadline is not None and not self._stop.is_set()
            expired = now >= (self._rematch_deadline if waiting else self._drain_deadline)
            if expired or (not waiting and all(not c.output.pending for c in self._clients.values())):
                for connection in tuple(self._clients.values()):
                    self._close(connection)
                if not self._stop.is_set():
                    self.app = ServerApp()
                    self._drain_deadline = None
                    self._rematch_deadline = None
                    self._rematch_votes.clear()

    def _serve_once(self, selector: selectors.BaseSelector, listener: socket.socket) -> bool:
        """Processa uma rodada de temporizadores e E/S; retorna True ao encerrar."""
        if self._stop.is_set() and self.app.controller.state != MatchState.FINISHED:
            self.app.process(Command('stop'))
            self._deliver()
        self._tick()
        if self._stop.is_set() and not self._clients:
            return True
        for key, mask in selector.select(0.1):
            if key.fileobj is listener:
                self._accept()
                continue
            connection = key.data
            if connection.sock not in self._clients:
                continue
            if mask & selectors.EVENT_READ:
                self._read(connection)
            if mask & selectors.EVENT_WRITE and connection.sock in self._clients:
                self._write(connection)
        return False

    def run(self, *, on_listening: Callable[[str, int], None] | None = None) -> None:
        """Escuta TCP até stop() ou KeyboardInterrupt, com uma partida ativa por vez."""
        try:
            with selectors.DefaultSelector() as selector, socket.socket() as listener:
                self._selector = selector
                self._listener = listener
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener.bind((self.host, self.port))
                listener.listen()
                listener.setblocking(False)
                self.bound_port = listener.getsockname()[1]
                selector.register(listener, selectors.EVENT_READ)
                self.listening.set()
                if on_listening is not None:
                    on_listening(listener.getsockname()[0], self.bound_port)
                while True:
                    try:
                        if self._serve_once(selector, listener):
                            return
                    except KeyboardInterrupt:
                        self.stop()
        except OSError as error:
            if not self.listening.is_set():
                self.start_error = error
                self.listening.set()
            raise
        finally:
            for connection in tuple(self._clients.values()):
                self._close(connection)
            self._selector = None
            self._listener = None
