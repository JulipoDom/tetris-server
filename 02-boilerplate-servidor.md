# Boilerplate do servidor - partida única

## Estado atual e extensão posterior ao boilerplate

A implementação local atende o domínio e prepara threads de comunicação.
A thread chamadora despacha comandos sequencialmente; uma thread recebe
comandos por callback e outra envia eventos por callback. A comunicação TCP
da partida continua pendente. O modo `network-test` é um diagnóstico separado,
com TCP mínimo em loopback, autorizado posteriormente: não usa TVP/1 nem
implementa jogadores ou políticas da partida. As instruções abaixo de manter
sockets pendentes continuam aplicadas ao transporte do jogo e às simulações.

## 1. Instrução para gerar o código

Ler junto de `00-contexto-geral.md`. Criar o domínio de um servidor Python para **exatamente dois jogadores em uma única partida por execução**. Implementar o ciclo local em memória e os testes. Deixar comunicação real em `TODO[EP-REDE]` com `NotImplementedError`.

Não criar gerenciador de salas, matchmaking, fila de jogadores, múltiplas partidas, IDs de partida, reconexão, histórico persistente ou banco de dados. Um terceiro participante é recusado sem interferir nos dois aceitos.

O servidor é autoridade do início e do resultado, mas não roda a física e não verifica se o cliente realmente limpou linhas. Cliente informa uma quantidade de ataque permitida e a própria derrota; o modelo é cooperativo.

## 2. Estrutura pequena

| Arquivo | Responsabilidade |
| --- | --- |
| `src/tetris_server/__main__.py` | Modos simulated, network pendente e network-test de diagnóstico TCP. |
| `src/tetris_server/match.py` | Dois participantes, prontidão, estado e resultado único. |
| `src/tetris_server/app.py` | Processar comandos locais sequencialmente e registrar saídas. |
| `src/tetris_server/simulation.py` | Cenários com participantes e conexões fictícias. |
| `src/tetris_server/network.py` | Stubs de listener, recebimento e envio TCP; monta o coordenador de threads. |
| `src/tetris_server/communication.py` | Threads de recebimento e envio por callbacks, filas e dispatcher na thread chamadora. |
| `src/tetris_server/network_diagnostic.py` | Diagnóstico TCP local separado, com uma thread de envio e outra de recebimento. |
| `src/tetris_shared/models.py` | Tipos internos compartilhados. |
| `src/tetris_shared/rules.py` | Quantidades permitidas e constantes. |
| `src/tetris_shared/protocol.py` | Stubs do codec/parser/framing. |
| `tests/test_server.py` | Testes de ciclo de vida e efeitos do jogo. |

Pacote compartilhado único, usado pelos dois executáveis. O servidor não importa `curses` ou o motor do cliente.

## 3. Estado mínimo

Um `MatchController` com duas posições (`player1`, `player2`), estado `WAITING`, `PREPARING`, `PLAYING` ou `FINISHED`, prontidão de cada um e resultado opcional imutável.

Cada jogador guarda apelido e referência opaca da sessão. A sessão define a identidade: apelido igual é permitido; não confiar num alvo indicado pelo cliente. O adversário é sempre a outra posição.

O adaptador futuro reserva no máximo duas conexões, inclusive durante a espera por HELLO. A validação do primeiro HELLO cria a participação no domínio. Conexões ainda não identificadas podem ser descartadas e substituídas; um jogador já identificado que sai cancela/encerra a execução conforme o contexto.

Nenhum serviço aceita um participante que não esteja nas duas posições. Estados e resultado só mudam no dispatcher sequencial, não em threads que alterem a partida livremente.

## 4. Operações prontas no boilerplate

### A. Identificar os dois jogadores

Receber uma sessão fictícia e apelido válido. Preencher a primeira posição livre. Se uma sessão já registrada tentar se identificar de novo, informar falha de domínio ao adaptador. Se já houver dois participantes, recusar o terceiro sem mudar a partida.

Com um jogador, permanecer em WAITING. Com dois, mudar para PREPARING e emitir um evento para cada um contendo somente o apelido do seu oponente. Esse evento será traduzido em MATCH na implementação futura.

### B. Esperar os dois ficarem prontos

Registrar prontidão individual em PREPARING. Repetição não duplica efeitos. Ao ter ambos prontos, mudar uma única vez para PLAYING e produzir autorização de início para os dois. A autorização futura é READY com GO; não criar outro tipo de mensagem.

Prontidão repetida já em PLAYING é ignorada, sem reiniciar. Prontidão antes de existir a dupla é inválida. Enfileirar a autorização para ambos antes de processar eventos de jogo.

### C. Encaminhar ATTACK e BOARD

Com partida ativa, aceitar ataque somente com inteiro 1, 2 ou 4; rejeitar booleanos como inteiros. Encaminhar o mesmo número ao único oponente. A quantidade já representa lixo calculado pelo cliente; não converter novamente como se fosse linhas limpas.

Aceitar tabuleiro somente com 20×10 células no intervalo 0 a 8. Fazer cópia imutável e encaminhar ao oponente. Não incluir peça ativa, recalcular física ou inferir KO a partir da matriz. Score não precisa chegar ao servidor.

No domínio/fake, é suficiente guardar o último snapshot por jogador. Eventos visuais ainda não consumidos podem ser substituídos pela versão mais recente. Ataques e resultado não podem ser descartados ou substituídos.

### D. Encerrar uma vez

Ao processar KO válido em PLAYING:

1. Verificar participante e estado.
2. Registrar resultado imutável e mudar para FINISHED.
3. Emitir WIN/KO para o outro e LOSE/KO para o remetente.
4. Rejeitar efeitos de jogo posteriores, sem recalcular resultado.

Duas derrotas quase simultâneas são resolvidas pela ordem do dispatcher. O primeiro encerramento válido ganha a disputa de processamento; isso não representa a ordem real das perdas na rede. Testar as duas ordens possíveis.

GAMEOVER é a única mensagem futura de resultado ou cancelamento. Falhar ao entregar não modifica a decisão armazenada. Em FINISHED, eventos tardios não geram nova finalização.

### E. Saída e falhas

O domínio recebe fatos internos de desconexão, timeout, violação do protocolo e parada planejada. Não implementa sockets ou detectores de tempo. Usar a tabela do contexto geral:

- Antes do início, perda de jogador identificado cancela sem vencedor.
- Durante o jogo, perda/timeout/infração de um jogador dá vitória ao outro.
- Parada planejada cancela sem vencedor, independentemente de ter iniciado.
- Falha abrupta do processo não promete notificação.
- Recusar um terceiro ou descartar uma conexão que nunca enviou HELLO válido não cancela a partida existente.

Após o evento final, o domínio não admite novos jogadores. O adaptador futuro tenta escoar notificações por até 1 segundo, fecha tudo e termina. Outra partida usa uma nova execução do processo.

## 5. Oito mensagens, nenhum handler de rede pronto

| Mensagem | Uso futuro no servidor |
| --- | --- |
| HELLO | Validar primeira identificação e registrar participante. |
| MATCH | Informar o oponente após as duas identificações. |
| READY | Receber PLAYER; quando ambos estiverem prontos, emitir GO. |
| BOARD | Validar matriz recebida e encaminhar ao oponente. |
| ATTACK | Validar 1, 2 ou 4 e encaminhar ao oponente. |
| KO | Converter derrota local em encerramento único. |
| GAMEOVER | Notificar resultado individual ou cancelamento. |
| KEEPALIVE | Atualizar atividade no adaptador, sem tocar no jogo. |

Em `network.py` e `protocol.py`, deixar reservados: abertura e aceitação de sockets, limite de conexões, associação da sessão, escrita parcial, buffers, validação de bytes, fechamento, HELLO em até 5 s, KEEPALIVE a cada 5 s e perda após 15 s sem mensagem válida. Esses números são os mesmos do contexto geral.

Não criar mensagens de erro, confirmação, saída ou início fora desse catálogo. Erros seguem o fechamento e a política de GAMEOVER definida no contexto. O modelo do domínio pode ter erros internos tipados sem virarem um novo tipo de mensagem de rede.

## 6. Simulação local

O fake usa objetos e callbacks em memória, com caixa de saída por participante. Não serializar texto para simular protocolo e não abrir socket. Injetar as falhas diretamente como fatos de domínio.

Cenários mínimos:

1. Duas identificações, duas prontidões, um ataque, um snapshot e um KO.
2. Terceiro participante recusado, com os dois originais preservados.
3. Prontidão repetida e dois KOs em ordens diferentes.
4. Saída antes e depois do início.
5. Snapshot inválido, ataque inválido e sessão desconhecida.
6. Falha de entrega depois de registrar resultado; estado permanece FINISHED.

Comandos esperados após geração:

```bash
PYTHONPATH=src python -m tetris_server --mode simulated
PYTHONPATH=src python -m tetris_server --mode network
PYTHONPATH=src python -m tetris_server --mode network-test --port 5000
PYTHONPATH=src python -m unittest discover -s tests -v
```

O modo network ainda falha explicitamente com `TODO[EP-REDE]`. Logs locais mostram estado, participante, ocorrência e motivo, sem fingir bytes, ping ou conexões reais.

O diagnóstico abre `127.0.0.1:5000` por padrão; `--port 0` escolhe uma porta
livre. Envia três blocos e confere o fluxo de 54 bytes, preservando leituras
parciais. Termina após a verificação; erros retornam 2. Não representa uma partida
TCP funcional. Os testes de integração são ignorados se sockets forem proibidos.

## 7. Aceite

- [ ] Há um controlador com duas posições e nenhum gerenciador de salas.
- [ ] Prontidão dupla produz exatamente uma autorização por jogador.
- [ ] ATTACK leva quantidade de lixo e é encaminhado sem reconversão.
- [ ] BOARD é validado e copiado, sem simulação de física.
- [ ] KO e falhas produzem uma decisão imutável.
- [ ] Terceiro participante não altera o jogo existente.
- [ ] Encerramento não abre outra partida na mesma execução.
- [ ] Testes funcionam sem TUI ou rede; stubs continuam pendentes.

Não chamar esta etapa de servidor TCP funcional. Ela entrega a lógica necessária para a equipe preencher a comunicação.
