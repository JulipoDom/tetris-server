"""Local server entry point; real network mode is deliberately pending."""

import argparse
import sys

from .network import NetworkServer
from .simulation import run_simulations


def main(argv: list[str] | None = None) -> int:
    """Run local scenarios or report that real networking is still pending."""
    parser = argparse.ArgumentParser(description='Tetris Versus single-match server boilerplate')
    parser.add_argument('--mode', choices=('simulated', 'network'), default='simulated')
    args = parser.parse_args(argv)
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
