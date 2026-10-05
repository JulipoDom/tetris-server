"""Ponto de entrada do servidor local; o modo de rede real permanece pendente."""

import argparse
import sys

from .network import NetworkServer
from .network_diagnostic import run_network_test
from .simulation import run_simulations


def main(argv: list[str] | None = None) -> int:
    """Executa cenários locais ou informa que a rede real continua pendente."""
    parser = argparse.ArgumentParser(description='Tetris Versus single-match server boilerplate')
    parser.add_argument('--mode', choices=('simulated', 'network', 'network-test'), default='simulated')
    parser.add_argument('--port', type=int, default=5000,
                        help='Porta TCP do diagnóstico local; 0 escolhe uma porta livre')
    args = parser.parse_args(argv)
    if args.mode == 'network-test':
        try:
            report = run_network_test(args.port)
        except (OSError, ValueError) as error:
            print(f'Falha no diagnóstico de rede: {error}', file=sys.stderr)
            return 2
        print(f'Diagnóstico TCP em 127.0.0.1:{report.port}: '
              f'{len(report.received)}/{sum(map(len, report.sent))} bytes recebidos; '
              f'{len(report.sent)} blocos enviados')
        print(f'  Fluxo recebido: {report.received!r}')
        return 0
    if args.mode == 'network':
        try:
            NetworkServer().run()
        except NotImplementedError as error:
            print(str(error), file=sys.stderr)
            return 2
        return 0
    for report in run_simulations():
        print(f'Scenario: {report.name} state={report.state.value}')
        for record in report.logs:
            print(f'  state={record.state.value} participant={record.participant} '
                  f'occurrence={record.occurrence} reason={record.reason or "-"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
