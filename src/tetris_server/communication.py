"""Threads de comunicação por callbacks, sem sockets ou protocolo de bytes.

O recebimento produz comandos tipados. O envio consome eventos imutáveis.
Somente a thread que chama run() acessa a aplicação e altera a partida.
"""

from collections.abc import Callable
from concurrent.futures import Future
from queue import Queue
from threading import Event, Thread

from tetris_shared.models import Command, MatchState, OutboundEvent
from .app import ServerApp
from .match import DomainError


class CommunicationThreads:
    """Separe recebimento e envio do dispatcher de uma única partida.

    receive(stop) deve retornar um Command, ou None ao encerrar sua fonte.
    O callback precisa observar stop e interromper esperas para permitir join.
    send(event) deve terminar ou levantar uma exceção; não pode bloquear
    indefinidamente. O futuro adaptador TCP implementará esses contratos.
    """

    def __init__(self, receive: Callable[[Event], Command | None],
                 send: Callable[[OutboundEvent], None], app: ServerApp | None = None):
        """Prepare filas de objetos e sinal de parada, sem iniciar as threads."""
        self.app = app if app is not None else ServerApp()
        self._receive = receive
        self._send = send
        self._stop = Event()
        self._incoming: Queue = Queue(maxsize=64)
        self._outgoing: Queue = Queue()
        self._used = False
        self.workers = (
            Thread(target=self._reader, name='tetris-recebimento'),
            Thread(target=self._writer, name='tetris-envio'),
        )

    def _put_input(self, item) -> None:
        """Aplique contrapressão e permita interromper uma fila cheia."""
        from queue import Full

        while not self._stop.is_set():
            try:
                self._incoming.put(item, timeout=0.05)
                return
            except Full:
                continue

    def _reader(self) -> None:
        """Produza comandos na fila sem acessar o controlador da partida."""
        try:
            while not self._stop.is_set():
                command = self._receive(self._stop)
                self._put_input(command)
                if command is None:
                    return
        except Exception as error:
            self._put_input(error)

    def _writer(self) -> None:
        """Execute envios e devolva o resultado ao dispatcher pelo Future."""
        while True:
            item = self._outgoing.get()
            if item is None:
                return
            event, completion = item
            try:
                self._send(event)
            except Exception as error:
                completion.set_exception(error)
            else:
                completion.set_result(None)

    def _deliver(self, event: OutboundEvent) -> None:
        """Aguarde cada callback para preservar ordem e política de falhas."""
        completion = Future()
        self._outgoing.put((event, completion))
        completion.result()

    def run(self) -> None:
        """Despache sequencialmente uma partida e encerre as duas threads."""
        if self._used:
            raise RuntimeError('Cada execução de comunicação atende apenas uma partida')
        self._used = True
        for worker in self.workers:
            worker.start()
        try:
            while self.app.controller.state != MatchState.FINISHED:
                command = self._incoming.get()
                if isinstance(command, Exception):
                    raise command
                if command is None:
                    self.app.process(Command('stop'))
                else:
                    try:
                        self.app.process(command)
                    except DomainError:
                        # A aplicação já registrou a rejeição do comando local.
                        continue
                self.app.deliver(self._deliver)
        finally:
            self._stop.set()
            self._outgoing.put(None)
            for worker in self.workers:
                worker.join()
