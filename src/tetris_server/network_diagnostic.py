"""Diagnóstico TCP em loopback, separado do transporte do jogo e de TVP/1."""

from dataclasses import dataclass
from queue import Queue
import socket
from threading import Event, Thread


@dataclass(frozen=True)
class DiagnosticReport:
    """Registre a porta efetiva, os envios e o fluxo de bytes recebido."""

    port: int
    sent: tuple[bytes, ...]
    received: bytes


def run_network_test(port: int = 5000) -> DiagnosticReport:
    """Abra uma porta TCP local, envie três blocos e confira o fluxo recebido.

    A porta zero deixa o sistema escolher uma porta livre. Os prazos abaixo
    limitam somente este diagnóstico; não são timers de sessão do jogo.
    TCP pode unir ou dividir os blocos enviados; a comparação usa todos os bytes.
    """
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError('A porta deve ser um inteiro de 0 a 65535')
    packets = (b'diagnostico-local-1', b'diagnostico-local-2', b'diagnostico-local-3')
    expected = b''.join(packets)
    received = bytearray()
    errors: Queue = Queue()
    stop = Event()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', port))
        listener.listen(1)
        address = listener.getsockname()
        listener.settimeout(0.1)

        def listen() -> None:
            """Aceite um cliente local e acumule suas leituras parciais."""
            try:
                while not stop.is_set():
                    try:
                        connection, _ = listener.accept()
                    except socket.timeout:
                        continue
                    with connection:
                        connection.settimeout(0.1)
                        while not stop.is_set() and len(received) < len(expected):
                            try:
                                data = connection.recv(len(expected) - len(received))
                            except socket.timeout:
                                continue
                            if not data:
                                return
                            received.extend(data)
                    return
            except Exception as error:
                errors.put(error)

        def send() -> None:
            """Conecte à porta local e envie três blocos de diagnóstico."""
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sender:
                    sender.settimeout(1)
                    sender.connect(address)
                    for packet in packets:
                        sender.sendall(packet)
            except Exception as error:
                errors.put(error)

        receiver = Thread(target=listen, name='diagnostico-recebimento')
        sender = Thread(target=send, name='diagnostico-envio')
        receiver.start()
        sender.start()
        try:
            sender.join()
            receiver.join(timeout=2)
        finally:
            stop.set()
            receiver.join()
        if not errors.empty():
            raise errors.get()
        if bytes(received) != expected:
            raise OSError(f'Diagnóstico incompleto: {len(received)}/{len(expected)} bytes')
        return DiagnosticReport(address[1], packets, bytes(received))
