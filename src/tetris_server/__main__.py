"""Ponto de entrada dos modos de simulação, diagnóstico e servidor TCP."""

import argparse
from ipaddress import IPv4Address
import subprocess
import sys

from .network import NetworkServer
from .network_diagnostic import run_network_test
from .simulation import run_simulations


def announce_listening(host: str, port: int) -> None:
    """Mostra a escuta aberta e os IPs IPv4 que os clientes podem informar."""
    print(f'Servidor TCP iniciado em {host}:{port}', flush=True)
    if host != '0.0.0.0':
        return
    addresses = set()
    # Algumas versões de hostname não possuem -I; ip lista as interfaces locais.
    commands = (['hostname', '-I'], ['ip', '-4', '-o', 'addr', 'show', 'up'])
    for command in commands:
        try:
            output = subprocess.check_output(command, text=True, timeout=1,
                                             stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            continue
        tokens = output.split()
        if command[0] == 'ip':
            # Apenas o endereço depois de inet interessa; brd é o broadcast.
            tokens = [tokens[i + 1].split('/')[0] for i, token in enumerate(tokens[:-1])
                      if token == 'inet']
        for token in tokens:
            try:
                address = IPv4Address(token)
            except ValueError:
                continue
            if not address.is_loopback and not address.is_unspecified:
                addresses.add(str(address))
        if addresses:
            break
    for address in sorted(addresses):
        print(f'  IP para os clientes: {address}:{port}', flush=True)
    print(f'  Nesta máquina: 127.0.0.1:{port}', flush=True)
    if not addresses:
        print('  IP da rede não detectado; consulte hostname -I ou ip -4 addr.', flush=True)
    print('Ctrl+C para encerrar o servidor.', flush=True)


def main(argv: list[str] | None = None) -> int:
    """Executa cenários locais ou atende partidas sequenciais na rede."""
    parser = argparse.ArgumentParser(description='Servidor Tetris Versus')
    parser.add_argument('--mode', choices=('simulated', 'network', 'network-test'), default='simulated')
    parser.add_argument('--host', default='127.0.0.1', help='Endereço da escuta TCP no modo network')
    parser.add_argument('--port', type=int, default=8765,
                        help='Porta TCP; 0 escolhe uma porta livre')
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
            NetworkServer(host=args.host, port=args.port).run(on_listening=announce_listening)
        except (OSError, ValueError) as error:
            print(f'Falha ao iniciar servidor TCP: {error}', file=sys.stderr)
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
