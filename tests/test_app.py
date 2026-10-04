import contextlib
import io
import unittest

from tetris_server.app import ServerApp
from tetris_server.__main__ import main
from tetris_server.match import DomainError
from tetris_server.network import NetworkServer
from tetris_server.simulation import run_simulations
from tetris_shared.models import Command, EndReason, MatchState, MessageType, Outcome
from tetris_shared.protocol import StreamParser, decode, encode


class AppTests(unittest.TestCase):
    def start(self):
        app = ServerApp()
        app.process(Command('join', 'a', 'Alice'))
        app.process(Command('join', 'b', 'Bob'))
        app.process(Command('ready', 'a'))
        app.process(Command('ready', 'b'))
        return app

    def test_start_is_queued_before_game_forwarding(self):
        app = self.start()
        app.process(Command('attack', 'a', 2))
        self.assertEqual([event.kind for event in app.outboxes['b']],
                         [MessageType.MATCH, MessageType.READY, MessageType.ATTACK])
        self.assertEqual(app.outboxes['b'][1].payload, 'GO')

    def test_coalescing_keeps_attacks_and_latest_board_in_order(self):
        app = self.start()
        board = [[0] * 10 for _ in range(20)]
        app.process(Command('board', 'a', board))
        app.process(Command('attack', 'a', 4))
        board[19][0] = 8
        app.process(Command('board', 'a', board))
        app.process(Command('ko', 'a', 'SPAWN'))
        events = app.outboxes['b']
        self.assertEqual([event.kind for event in events],
                         [MessageType.MATCH, MessageType.READY, MessageType.ATTACK,
                          MessageType.BOARD, MessageType.GAMEOVER])
        self.assertEqual(events[2].payload, 4)
        self.assertEqual(events[3].payload[19][0], 8)
        self.assertEqual(events[4].payload.outcome, Outcome.WIN)

    def test_failed_delivery_after_ko_preserves_result_and_other_notification(self):
        app = self.start()
        app.deliver(lambda event: None)
        app.process(Command('ko', 'a', 'SPAWN'))
        result = app.controller.result
        delivered = []

        def send(event):
            if event.recipient == 'a':
                raise OSError('simulated unavailable recipient')
            delivered.append(event)

        app.deliver(send)
        self.assertIs(app.controller.result, result)
        self.assertEqual(app.controller.state, MatchState.FINISHED)
        self.assertEqual(len(delivered), 1)
        self.assertEqual(delivered[0].payload.outcome, Outcome.WIN)
        self.assertTrue(any(record.occurrence == 'delivery_failure' for record in app.logs))
        app.deliver(send)
        self.assertEqual(len(delivered), 1)

    def test_delivery_failure_during_play_ends_with_disconnect(self):
        for failed, survivor in (('a', 'b'), ('b', 'a')):
            with self.subTest(failed=failed):
                app = self.start()
                delivered = []

                def send(event):
                    if event.recipient == failed:
                        raise OSError('offline')
                    delivered.append(event)

                app.deliver(send)
                self.assertEqual(app.controller.result.reason, EndReason.DISCONNECT)
                self.assertEqual(app.controller.result.outcome_for(survivor), Outcome.WIN)
                self.assertEqual(delivered[-1].kind, MessageType.GAMEOVER)
                self.assertEqual(delivered[-1].recipient, survivor)
                self.assertTrue(all(not queue for queue in app.outboxes.values()))

    def test_rejected_command_is_logged_and_preserves_state(self):
        app = self.start()
        with self.assertRaises(DomainError):
            app.process(Command('attack', 'unknown', 2))
        self.assertEqual(app.controller.state, MatchState.PLAYING)
        self.assertEqual(app.logs[-1].occurrence, 'rejected')
        with self.assertRaises(ValueError):
            app.process(Command('invented_operation', 'a'))

    def test_delivery_failure_before_play_notifies_survivor_of_cancellation(self):
        for failed, survivor in (('a', 'b'), ('b', 'a')):
            with self.subTest(failed=failed):
                app = ServerApp()
                app.process(Command('join', 'a', 'Alice'))
                app.process(Command('join', 'b', 'Bob'))
                delivered = []

                def send(event):
                    if event.recipient == failed:
                        raise OSError('offline')
                    delivered.append(event)

                app.deliver(send)
                self.assertEqual(delivered[-1].recipient, survivor)
                self.assertEqual(delivered[-1].payload.outcome, Outcome.CANCEL)
                self.assertEqual(delivered[-1].payload.reason, EndReason.DISCONNECT)
                self.assertTrue(all(not queue for queue in app.outboxes.values()))

    def test_both_delivery_failures_preserve_the_first_decision(self):
        app = self.start()
        results_at_failure = []

        def unavailable(event):
            results_at_failure.append(app.controller.result)
            raise OSError('offline')

        app.deliver(unavailable)
        result = app.controller.result
        self.assertEqual(result.outcome_for('a'), Outcome.LOSE)
        self.assertEqual(result.outcome_for('b'), Outcome.WIN)
        self.assertIsNone(results_at_failure[0])
        self.assertIs(results_at_failure[1], result)
        self.assertTrue(all(not queue for queue in app.outboxes.values()))

    def test_failures_and_stop_dispatch_as_domain_facts(self):
        for reason in (EndReason.DISCONNECT, EndReason.TIMEOUT, EndReason.PROTOCOL):
            with self.subTest(reason=reason):
                app = self.start()
                app.process(Command('failure', 'a', reason))
                self.assertEqual(app.controller.result.reason, reason)
        app = self.start()
        app.process(Command('stop'))
        self.assertEqual(app.controller.result.outcome_for('a'), Outcome.CANCEL)

    def test_simulations_complete_and_report_local_records(self):
        reports = run_simulations()
        self.assertGreaterEqual(len(reports), 6)
        self.assertTrue(all(report.logs for report in reports))
        self.assertTrue(all(report.state == MatchState.FINISHED for report in reports))
        self.assertTrue(any(report.name == 'delivery_failure' for report in reports))

    def test_simulated_cli_runs_without_network(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main(['--mode', 'simulated'])
        self.assertEqual(status, 0)
        self.assertIn('FINISHED', output.getvalue())
        self.assertIn('delivery_failure', output.getvalue())

    def test_network_cli_explicitly_fails(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            status = main(['--mode', 'network'])
        self.assertNotEqual(status, 0)
        self.assertIn('TODO[EP-REDE]', output.getvalue())

    def test_network_and_codec_stubs_remain_unimplemented(self):
        for action in (NetworkServer().run, lambda: encode(None),
                       lambda: decode(b'TVP/1|KEEPALIVE\n'),
                       lambda: StreamParser().feed(b'partial')):
            with self.subTest(action=action):
                with self.assertRaisesRegex(NotImplementedError, r'TODO\[EP-REDE\]'):
                    action()


if __name__ == '__main__':
    unittest.main()
