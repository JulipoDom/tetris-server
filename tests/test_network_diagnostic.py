"""Testes de diagnóstico TCP local, separado do transporte do jogo."""

import contextlib
import io
import socket
import threading
import unittest

from tetris_server.__main__ import main
from tetris_server.network_diagnostic import run_network_test


class DiagnosticTests(unittest.TestCase):
    def require_tcp(self):
        """Ignore integração somente quando o ambiente proíbe sockets locais."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind(('127.0.0.1', 0))
        except PermissionError as error:
            self.skipTest(f'Sockets locais bloqueados pelo ambiente: {error}')

    def test_local_packets_are_received_and_threads_terminate(self):
        self.require_tcp()
        before = set(threading.enumerate())
        report = run_network_test(port=0)
        self.assertGreater(report.port, 0)
        self.assertEqual(report.received, b''.join(report.sent))
        self.assertEqual(len(report.sent), 3)
        self.assertEqual(set(threading.enumerate()), before)

    def test_requested_port_is_used_and_released(self):
        self.require_tcp()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        self.assertEqual(run_network_test(port=port).port, port)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(('127.0.0.1', port))

    def test_cli_reports_tcp_and_byte_count(self):
        self.require_tcp()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = main(['--mode', 'network-test', '--port', '0'])
        self.assertEqual(status, 0)
        self.assertIn('TCP', output.getvalue())
        self.assertIn('54/54 bytes', output.getvalue())

    def test_busy_port_fails_explicitly(self):
        self.require_tcp()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
            occupied.bind(('127.0.0.1', 0))
            output = io.StringIO()
            with contextlib.redirect_stderr(output):
                status = main(['--mode', 'network-test', '--port',
                               str(occupied.getsockname()[1])])
        self.assertEqual(status, 2)
        self.assertIn('Falha', output.getvalue())

    def test_invalid_port_is_rejected(self):
        for port in (-1, 65536, True):
            with self.subTest(port=port):
                with self.assertRaises(ValueError):
                    run_network_test(port=port)


if __name__ == '__main__':
    unittest.main()
