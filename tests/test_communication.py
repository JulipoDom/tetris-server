"""Testes da comunicação com threads e despacho sequencial."""

import threading
import unittest

from tetris_server.app import ServerApp
from tetris_server.communication import CommunicationThreads
from tetris_server.network import NetworkServer
from tetris_shared.models import Command, EndReason, MatchState, MessageType, Outcome


class CommunicationTests(unittest.TestCase):
    def test_network_prepares_workers_without_starting_tcp(self):
        server = NetworkServer()
        communication = server.prepare_communication()
        self.assertIs(communication.app, server.app)
        self.assertTrue(all(worker.ident is None for worker in communication.workers))
        for action in (lambda: server.receive_command(threading.Event()),
                       lambda: server.send_event(None)):
            with self.assertRaisesRegex(NotImplementedError, r'TODO\[EP-REDE\]'):
                action()

    def execute(self, commands, sender=None):
        """Execute comandos locais e registre as threads de cada operação."""
        commands = iter(commands)
        received_on = []
        delivered = []
        sent_on = []

        def receive(stop):
            received_on.append(threading.get_ident())
            return next(commands, None)

        def send(event):
            sent_on.append(threading.get_ident())
            if sender is not None:
                sender(event)
            delivered.append(event)

        app = ServerApp()
        dispatcher_on = []
        original = app.process

        def process(command):
            dispatcher_on.append(threading.get_ident())
            return original(command)

        app.process = process
        communication = CommunicationThreads(receive, send, app)
        communication.run()
        self.assertEqual(set(dispatcher_on), {threading.get_ident()})
        self.assertNotIn(threading.get_ident(), received_on)
        self.assertNotIn(threading.get_ident(), sent_on)
        self.assertFalse(any(worker.is_alive() for worker in communication.workers))
        return app, delivered, communication

    def commands(self):
        """Monte uma partida com ataque e dois encerramentos próximos."""
        return [Command('join', 'a', 'Ana'), Command('join', 'b', 'Bia'),
                Command('ready', 'a'), Command('ready', 'b'),
                Command('attack', 'a', 2), Command('ko', 'a', 'SPAWN'),
                Command('ko', 'b', 'OVERFLOW')]

    def test_lifecycle_order_and_thread_ownership(self):
        app, delivered, communication = self.execute(self.commands())
        self.assertEqual(app.controller.state, MatchState.FINISHED)
        self.assertEqual(app.controller.result.outcome_for('b'), Outcome.WIN)
        self.assertEqual([event.kind for event in delivered],
                         [MessageType.MATCH, MessageType.MATCH,
                          MessageType.READY, MessageType.READY,
                          MessageType.ATTACK, MessageType.GAMEOVER, MessageType.GAMEOVER])
        with self.assertRaises(RuntimeError):
            communication.run()

    def test_send_failure_becomes_sequential_disconnect(self):
        def send(event):
            if event.kind == MessageType.ATTACK:
                raise OSError('Destinatário indisponível')

        app, delivered, _ = self.execute(self.commands(), send)
        self.assertEqual(app.controller.result.reason, EndReason.DISCONNECT)
        self.assertEqual(app.controller.result.outcome_for('a'), Outcome.WIN)
        self.assertEqual(delivered[-1].kind, MessageType.GAMEOVER)

    def test_final_delivery_failure_preserves_ko(self):
        def send(event):
            if event.kind == MessageType.GAMEOVER and event.recipient == 'a':
                raise OSError('Falha após o resultado')

        app, delivered, _ = self.execute(self.commands(), send)
        self.assertEqual(app.controller.result.reason, EndReason.KO)
        self.assertEqual(app.controller.result.outcome_for('b'), Outcome.WIN)
        self.assertEqual(sum(event.kind == MessageType.GAMEOVER for event in delivered), 1)

    def test_end_of_input_cancels_and_invalid_command_is_logged(self):
        app, _, _ = self.execute([Command('join', 'a', 'Ana'),
                                 Command('attack', 'desconhecido', True)])
        self.assertEqual(app.controller.result.reason, EndReason.SERVER_STOP)
        self.assertTrue(any(record.occurrence == 'rejected' for record in app.logs))

    def test_receive_exception_is_propagated_and_workers_stop(self):
        def receive(stop):
            raise OSError('Falha da fonte de comandos')

        communication = CommunicationThreads(receive, lambda event: None)
        with self.assertRaisesRegex(OSError, 'Falha da fonte'):
            communication.run()
        self.assertFalse(any(worker.is_alive() for worker in communication.workers))


if __name__ == '__main__':
    unittest.main()
