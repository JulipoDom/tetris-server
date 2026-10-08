# Tetris Versus — servidor

Servidor TCP em Python 3.12+ e somente biblioteca padrão. Admite dois clientes,
valida TVP/1, encaminha tabuleiros e ataques e registra resultado único.
Atende rodadas sequenciais, com uma partida ativa por vez. Física e interface
ficam em [tetris-interface](https://github.com/JulipoDom/tetris-interface).

## Abrir o servidor

Na raiz do repositório:

```bash
./server
```

Escuta em todas as interfaces IPv4 (0.0.0.0), porta padrão 8765. Depois de
abrir a escuta, mostra o endereço/porta e os IPs locais para os clientes.
Consulta hostname -I (I maiúsculo); se indisponível, usa ip -4 -o addr show up.
Se nenhuma consulta funcionar, informa a limitação e o endereço de loopback.
Ctrl+C encerra o servidor e solicita cancelamento da partida ativa.

```bash
./server --port 9000
./server --host 127.0.0.1
PYTHONPATH=src python3 -m tetris_server --mode network --host 0.0.0.0 --port 8765
```

O módulo, sem opções, usa simulated; --mode network usa loopback por padrão.
O atalho ./server seleciona rede e 0.0.0.0 automaticamente. --port 0 permite
porta efêmera; a porta efetiva aparece na abertura da escuta.

Instalação opcional: python3 -m venv .venv e .venv/bin/pip install -e .;
depois .venv/bin/tetris_server --mode network --host 0.0.0.0. Use ambientes
separados do cliente para evitar colisão dos pacotes compartilhados.

## Conectar dois jogadores

Na raiz de tetris-interface, em duas máquinas ou terminais:

```bash
./client --mode network --host 192.168.1.10 --port 8765 --nickname Ana
./client --mode network --host 192.168.1.10 --port 8765 --nickname Bia
```

Substitua o IP pelo endereço mostrado pelo servidor; para jogar na mesma
máquina use 127.0.0.1. Cada jogador pressiona Enter para ficar pronto.
Após KO, ambos têm 10 s para pressionar R e iniciar revanche na mesma conexão.
Sem dois votos, a dupla é liberada e outra partida pode começar.

O cliente perde após mais de 20 s sem tecla; ./client --no-timeout desativa
somente essa regra. Pela Tailscale, compartilhe o IPv4 Tailscale e a porta:
ambos precisam ter acesso à máquina pela tailnet/compartilhamento, com TCP
8765 permitido pelas regras de acesso e pelo firewall.

## Contrato e estrutura

[PROTOCOLO_TCP.md](docs/PROTOCOLO_TCP.md) descreve oito mensagens: HELLO,
MATCH, READY, BOARD, ATTACK, KO, GAMEOVER e KEEPALIVE. Frames ASCII/LF de até
512 bytes; HELLO em até 5 s, KEEPALIVE a cada 5 s e timeout de rede em 15 s.
A fila de saída é limitada a 4096 bytes por conexão. Resultados comuns têm
até 1 s para drenagem; KO conserva as conexões pela janela de revanche de
10 s. O primeiro encerramento válido determina o resultado.

match.py contém o domínio; app.py despacha comandos; network.py faz TCP com
selectors; communication.py oferece coordenação por callbacks. O servidor
não calcula score/física e não infere KO pela imagem do tabuleiro. Não há
salas, contas, ranking, reconexão, banco de dados ou partidas simultâneas.
Spins e combos são locais; ataques chegam em quantidades de 1, 2 ou 4.

## Modos auxiliares e documentação

```bash
PYTHONPATH=src python3 -m tetris_server --mode simulated
PYTHONPATH=src python3 -m tetris_server --mode network-test --port 0
```

simulated executa cenários em memória; network-test é um diagnóstico TCP
local, sem TVP/1 nem partida. Esses modos permanecem como recursos de execução.
Todos os arquivos de testes automatizados foram removidos a pedido do
proprietário; os relatórios Markdown foram mantidos.

Veja [estado atual](docs/STATUS_TCP.md), [regras](docs/REGRAS_JOGO.md),
[estilo](docs/ESTILO_AUTOR.md) e [validação](docs/RELATORIO_VALIDACAO.md).
