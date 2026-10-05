# Servidor Tetris Versus

Repositório remoto: [JulipoDom/tetris-server](https://github.com/JulipoDom/tetris-server).
Endereço SSH: `git@github.com:JulipoDom/tetris-server.git`.

Em um checkout Git válido, configure o remoto com:

```bash
git remote add origin git@github.com:JulipoDom/tetris-server.git
```

Se `origin` já existir, use `git remote set-url origin` com o mesmo endereço.

Estrutura inicial de um servidor Python 3.12+ para um jogo de Tetris no terminal
com dois jogadores. A lógica local da partida, as simulações e os testes estão
implementados. A comunicação TCP fica para implementação manual nos pontos
marcados com `TODO[EP-REDE]`.

## Ideia geral

Cada cliente executa seu próprio tabuleiro: peças, gravidade, colisões, remoção
de linhas, pontuação, aplicação de lixo e detecção de derrota local. A remoção
de várias linhas produz ataques de lixo para o adversário. O servidor identifica
os dois jogadores, espera ambos ficarem prontos, encaminha ataques e cópias dos
blocos fixos do tabuleiro e registra um resultado único. Ele confia em clientes
cooperativos: não simula a física nem comprova que um ataque veio de uma jogada.

O servidor de rede previsto atende **exatamente dois jogadores e uma partida por
execução**, encerrando depois do resultado. Outra partida exige reiniciar os
processos. Salas, matchmaking, contas, ranking, reconexão e banco de dados ficam
fora do escopo. O motor do cliente e a interface de terminal não fazem parte
deste repositório.

## Executar localmente

Use Python 3.12 ou superior, com a mesma versão menor entre os integrantes da
equipe. O domínio e os testes usam apenas a biblioteca padrão. Na raiz do
repositório, execute:

```bash
PYTHONPATH=src python -m tetris_server --mode simulated
```

O comando executa oito cenários predefinidos, imprime os registros locais e
termina. Sem `--mode`, o modo padrão também é `simulated`. Ele não espera clientes
reais nem abre uma porta. `PYTHONPATH=src` permite ao Python encontrar os pacotes
em `src/` sem instalar o projeto.

Para executar os testes:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

A suíte contém 41 testes, cobrindo o ciclo da partida, validação,
ordem de encaminhamento, cópias e resultados imutáveis, cancelamento, falhas
de entrega, simulações e os pontos de rede ainda pendentes.

O modo de rede ainda não está implementado:

```bash
PYTHONPATH=src python -m tetris_server --mode network
```

Ele imprime `TODO[EP-REDE]: TCP listener, sessions, I/O, buffers, and timers` na
saída de erro e termina com código **2**. Não muda silenciosamente para a simulação.

### Diagnóstico local de rede com threads

```bash
PYTHONPATH=src python -m tetris_server --mode network-test --port 5000
```

Esse modo abre **TCP somente em 127.0.0.1**, inicia uma thread de recebimento
e outra de envio, aceita um cliente local, envia três blocos de diagnóstico, verifica o fluxo
recebido e termina. Imprime a porta efetiva, a contagem de bytes e o conteúdo.
Leituras parciais são acumuladas; TCP não preserva os limites dos envios.
Use `--port 0` para o sistema escolher uma porta livre. Porta ocupada, inválida,
recebimento incompleto ou restrição de sockets produz erro e código **2**.

O diagnóstico implementa apenas uma troca TCP local de bytes predefinidos,
sem iniciar uma partida ou usar TVP/1. O transporte TCP do jogo permanece
pendente. Testes de integração TCP são ignorados explicitamente quando o ambiente proíbe sockets locais; nesses
ambientes, executar o diagnóstico também falha explicitamente.

### Preparação da comunicação do jogo

[communication.py](src/tetris_server/communication.py) fornece
`CommunicationThreads(receive, send, app)`. `run()` inicia uma thread para
receber comandos tipados e outra para enviar eventos imutáveis. A thread que
chama `run()` executa exclusivamente `ServerApp.process()` e `deliver()`;
as threads de comunicação não acessam o estado da partida.

A fila de entrada aplica contrapressão. Os envios são confirmados pelo callback
antes do próximo despacho, preservando a ordem e permitindo que falhas de envio
sejam processadas sequencialmente pela política existente. Isso não garante
entrega remota. Após o resultado, o coordenador sinaliza parada, conclui os
callbacks de notificações finais e aguarda o encerramento das threads. Fim da
fonte de comandos antes do resultado gera uma parada planejada. Cada coordenador
executa apenas uma vez.

O callback `receive(stop)` retorna `Command` ou `None` ao terminar; deve observar
o `Event` de parada e interromper suas esperas. O callback `send(event)` deve
terminar ou lançar uma exceção, sem bloquear indefinidamente. O adaptador TCP
futuro precisa cumprir esses contratos e implementar seus limites e prazos.
`NetworkServer.prepare_communication()` monta esse coordenador sem iniciar
threads. `receive_command()` e `send_event()` permanecem stubs com
`TODO[EP-REDE]`, assim como `NetworkServer.run()`.

### Instalação opcional

A instalação editável permite usar os comandos de módulo sem `PYTHONPATH` e o
executável `tetris_server`. A instalação usa setuptools como ferramenta de
empacotamento; não há dependências externas durante a execução do servidor.

```bash
python -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m tetris_server --mode simulated
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/tetris_server --mode simulated
```

## Como a execução funciona

`__main__.py` seleciona o modo. O modo simulado chama `run_simulations()` na
thread principal. O modo de rede chama `NetworkServer.run()`, que ainda falha
explicitamente. O modo `network-test` chama `run_network_test()` e inicia duas
threads de diagnóstico. As threads da partida só iniciam ao chamar
`CommunicationThreads.run()`; preparar o coordenador não inicia comunicação.

O processamento local implementado segue este caminho:

```text
Command → ServerApp.process() → MatchController
        → OutboundEvent → caixa de saída por sessão
                        → função opcional de entrega local
```

`ServerApp.process()` processa um comando por completo antes do próximo. O
controlador mantém as duas posições de jogadores e as transições de estado:

```text
WAITING → PREPARING → PLAYING → FINISHED
```

A primeira identificação mantém WAITING (aguardando). A segunda gera MATCH com o
apelido do adversário e entra em PREPARING (preparação). Quando ambos ficam
prontos, o controlador gera um READY/GO por jogador e entra em PLAYING (jogando).
Um evento de encerramento registra o resultado antes de enfileirar GAMEOVER.
Uma falha de participante identificado ou uma parada planejada também pode
encerrar a execução antes de começar o jogo.

As sessões são identificadores estáveis que podem ser usados como chaves de
um dicionário; apelidos iguais são permitidos. O adversário é sempre o jogador
da outra posição, não um alvo informado pelo cliente. Após FINISHED (encerrado),
eventos de jogo tardios de participantes conhecidos não produzem novos efeitos.

## O que está implementado

| Funcionalidade | Como funciona | Localização |
| --- | --- | --- |
| Objetos tipados compartilhados | Enumerações e dataclasses imutáveis para jogador, comando, evento e resultado. | [models.py](src/tetris_shared/models.py) |
| Admissão de dois jogadores | Valida apelidos e recusa sessões duplicadas e um terceiro participante, preservando a dupla original. | `MatchController.join()` em [match.py](src/tetris_server/match.py) |
| Prontidão | Repetições não duplicam efeitos; ambos recebem exatamente um GO antes dos efeitos de jogo. | `MatchController.ready()` |
| Encaminhamento de ataques | Valida a quantidade inteira de lixo 1, 2 ou 4, rejeita booleanos e encaminha o valor sem alteração. | `MatchController.attack()` |
| Encaminhamento de tabuleiro | Valida 20×10 células inteiras de 0 a 8, guarda uma cópia imutável e encaminha ao adversário. | `MatchController.board()` |
| Resultado único | O primeiro encerramento válido processado determina o resultado; KO tardio e falha de entrega não o alteram. | `ko()`, `_finish()` e `MatchResult` |
| Política de falhas | Antes do jogo, falha de participante identificado cancela; durante o jogo, o adversário vence. Parada planejada cancela uma partida ainda não encerrada. | `failure()` e `stop()` |
| Caixas de saída e registros | Enfileiram eventos Python por destinatário; apenas BOARD antigos ainda não consumidos podem ser substituídos. Ataques e resultados são preservados. | [app.py](src/tetris_server/app.py) |
| Entrega local por função | Exceções na função de entrega tornam-se fatos de desconexão; novas notificações ao participante remanescente também são processadas. | `ServerApp.deliver()` |
| Cenários locais e testes | Exercitam o domínio sem sockets, serialização de bytes, interface gráfica ou temporizadores reais. | [simulation.py](src/tetris_server/simulation.py), [testes](tests) |

Cada função em `src/` possui uma docstring curta explicando sua finalidade.
As regras comuns do tabuleiro, os valores de validação e os padrões reservados
para rede estão em [rules.py](src/tetris_shared/rules.py). O `.gitignore` exclui
arquivos gerados pelo Python, ambientes virtuais, caches, arquivos de variáveis
de ambiente e pastas locais de agentes e credenciais.

## Como a simulação funciona

Cada cenário cria um novo `ServerApp` e um novo `MatchController`. Strings como
`player1` e `player2` representam as sessões. Objetos `Command` predefinidos passam
pelo processador real; os objetos `OutboundEvent` resultantes ficam nas caixas
de saída locais ou são consumidos por uma função de entrega. Nenhum cliente
real de Tetris está em execução.

O cenário normal realiza duas identificações, duas confirmações de prontidão,
um ataque de 2 linhas de lixo, uma cópia do tabuleiro e um KO/SPAWN de player1.
O resultado final é player2 WIN/KO e player1 LOSE/KO. O servidor apenas encaminha
o ataque; não aplica lixo a um tabuleiro de jogo simulado.

| Cenário | Comportamento exercitado |
| --- | --- |
| `complete_match` | Identificação, prontidão, ataque, cópia do tabuleiro e KO. |
| `third_participant_refused` | Recusa de um terceiro participante, preservando a dupla original. |
| `first_ko_player1` | Prontidão repetida e KO de player1 processado primeiro. |
| `first_ko_player2` | Ordem inversa dos KOs; o primeiro resultado processado permanece fixo. |
| `departure_before_play` | Desconexão durante a preparação produz cancelamento. |
| `departure_during_play` | Desconexão durante o jogo dá vitória ao adversário. |
| `invalid_inputs` | Tabuleiro inválido, ataque booleano e sessão desconhecida são rejeitados; parada planejada cancela. |
| `delivery_failure` | Falha injetada na função de entrega após o encerramento preserva o resultado registrado. |

As oito execuções independentes demonstram o comportamento da lógica local;
não representam um servidor de produção que hospeda várias partidas. A maioria
dos cenários inspeciona efeitos enfileirados sem chamar a entrega para cada
evento. O último cenário usa explicitamente funções de entrega.

Um cabeçalho como `Scenario: complete_match state=FINISHED` mostra o estado final.
Os registros seguintes mostram o estado em cada comando ou saída enfileirada,
o participante, a ocorrência e o motivo opcional. Em comandos, o participante
é o remetente; em saídas, é o destinatário. Um registro de saída significa
**enfileirado em memória**, não entregue por TCP. `reason=-` indica ausência de
motivo naquele registro; o resultado e o motivo de GAMEOVER ficam em seu objeto
de dados e no resultado final da partida.

Consulte [IMPLEMENTS.md](IMPLEMENTS.md) para acompanhar o fluxo passo a passo e
executar um exemplo que imprime diretamente uma caixa de saída e o resultado.

## Onde é necessária implementação manual

Os seguintes pontos executáveis levantam `NotImplementedError`:

| Ponto de entrada | Trabalho a implementar |
| --- | --- |
| `NetworkServer.run()` em [network.py](src/tetris_server/network.py) | Listener TCP, laço sequencial de eventos com I/O não bloqueante, reserva de duas conexões, associação confiável de sessões, buffers de entrada e saída, escritas parciais, detecção de falhas, temporizadores, escoamento final e fechamento dos sockets. |
| `NetworkServer.receive_command(stop)` | Recebimento TCP, validação, associação de sessão e parada cooperativa da thread. |
| `NetworkServer.send_event(event)` | Integração do encoder, buffers e escritas TCP parciais na thread de envio. |
| `encode(event)` em [protocol.py](src/tetris_shared/protocol.py) | Serializar eventos de saída em linhas ASCII TVP/1 terminadas por LF. Converter BOARD em exatamente 200 dígitos. |
| `decode(frame)` em [protocol.py](src/tetris_shared/protocol.py) | Validar a gramática e os campos exatos e traduzir entradas aceitas do cliente em comandos locais. O adaptador deve associar a sessão real do remetente e validar direção e estado. |
| `StreamParser.feed(data)` em [protocol.py](src/tetris_shared/protocol.py) | Manter um buffer por conexão, extrair todas as mensagens completas delimitadas por LF, guardar fragmentos e rejeitar entradas grandes demais mesmo antes de chegar LF. |

Implemente primeiro a codificação, decodificação e delimitação das mensagens.
Depois, avance para admissão de conexões, integração com o processador de comandos,
buffers de saída, temporizadores, encerramento e testes de integração TCP reais.
A lista detalhada de tarefas manuais está em [IMPLEMENTS.md](IMPLEMENTS.md).

### Requisitos do protocolo e do adaptador

Estão reservados exatamente oito tipos de mensagem: `HELLO`, `MATCH`, `READY`,
`BOARD`, `ATTACK`, `KO`, `GAMEOVER` e `KEEPALIVE`. O formato previsto é ASCII
`TVP/1|...` terminado por LF. As enumerações e os eventos existentes ainda não
implementam a codificação e decodificação do protocolo.

O adaptador traduz HELLO para `join`, READY/PLAYER para `ready`, BOARD para `board`,
ATTACK para `attack` e KO para `ko`. KEEPALIVE serve ao controle de atividade do
adaptador: não deve ser respondido imediatamente nem virar uma nova operação
de jogo. Falha de socket, timeout e violação de protocolo tornam-se comandos
internos `failure`. O adaptador deve tratar os erros de domínio registrados e
relançados conforme a política do protocolo.

| Regra pendente | Valor padrão |
| --- | --- |
| Conexões admitidas, incluindo as que aguardam HELLO | No máximo 2; fechar uma terceira imediatamente. |
| Prazo para o primeiro HELLO válido | 5 segundos após aceitar a conexão. |
| Envio periódico de KEEPALIVE | A cada 5 segundos após HELLO, mesmo com outro tráfego. |
| Timeout de inatividade | 15 segundos desde a última mensagem completa e válida. |
| Tamanho máximo de uma linha completa | 512 bytes incluindo LF; limitar também fragmentos incompletos. |
| Limite de saída pendente | 4096 bytes por conexão. |
| Escoamento das notificações finais | No máximo 1 segundo; depois fechar e encerrar. |

Esses valores estão declarados e documentados, mas ainda não há temporizadores
de rede ou buffers de bytes em execução. Falhas antes da identificação liberam
a reserva sem cancelar a participação de quem já se identificou; participantes
identificados não podem ser substituídos. Leituras e escritas TCP podem ser
parciais, então preserve os bytes restantes. Apenas cópias do tabuleiro ainda
não serializadas podem ser substituídas por versões mais recentes. A função de
entrega local `deliver()` não implementa escritas em sockets nem confirma entrega
pela rede. Registre o resultado uma vez e não o altere por falha de notificação.

A rede real exigirá novos testes de delimitação, validação de bytes, I/O parcial,
admissão de conexões, prazos e comunicação entre participantes reais. Quando os
pontos pendentes forem implementados, substitua os testes que esperam essas
falhas explícitas e preserve os testes de regressão do domínio.

## Documentos do projeto

| Documento | Finalidade |
| --- | --- |
| [00-contexto-geral.md](00-contexto-geral.md) | Fonte única das regras, gramática do protocolo, direções, restrições de estado e política de falhas. |
| [02-boilerplate-servidor.md](02-boilerplate-servidor.md) | Escopo do servidor, estrutura, cenários e critérios de aceite. |
| [IMPLEMENTS.md](IMPLEMENTS.md) | Mapa de funcionalidades e funções, tarefas de implementação manual e explicação da simulação. |
| [AGENTS.md](AGENTS.md) | Orientações do repositório e restrições para alterações futuras. |
