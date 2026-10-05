# Tetris Versus - contexto geral simplificado

Revisão: 05/10/2026. Uso interno da equipe.

## Estado atual da implementação do servidor

O servidor agora prepara duas threads de comunicação por callbacks: recebimento
e envio. A thread chamadora continua sendo o dispatcher sequencial e a única
que modifica a partida. `NetworkServer.prepare_communication()` apenas monta
essa estrutura; `CommunicationThreads.run()` inicia as threads.

A comunicação TCP da partida, o codec, framing, buffers de bytes e temporizadores
seguem pendentes com `TODO[EP-REDE]`. O modo `network` falha com código 2.
Por solicitação posterior ao boilerplate, existe um modo separado `network-test`
que abre TCP somente em `127.0.0.1`, conecta um cliente local, envia três blocos
predefinidos e verifica 54 bytes. Ele não usa TVP/1 nem inicia partida. Essa é uma
exceção restrita à ferramenta de diagnóstico às instruções originais de não
abrir sockets no boilerplate; não altera a gramática ou as regras do jogo.

Consulte [IMPLEMENTS.md](IMPLEMENTS.md) para os pontos de implementação e
[README.md](README.md) para execução e limites da validação.

## 1. Decisões que valem para todo o projeto

**Dois jogadores, um servidor, uma única partida.** Não criar gerenciador de salas, fila de matchmaking, IDs de partida, ranking, contas ou suporte a partidas simultâneas. Cada execução do servidor conduz uma partida e termina depois do resultado. Para jogar novamente, reiniciar o servidor e os clientes.

O catálogo tem **exatamente oito tipos**: `HELLO`, `MATCH`, `READY`, `BOARD`, `ATTACK`, `KO`, `GAMEOVER` e `KEEPALIVE`. Esta revisão substitui os catálogos e a arquitetura anteriores.

Os arquivos deste conjunto são contextos para gerar os boilerplates, não código já implementado. O domínio e os modos locais devem funcionar; a implementação de rede permanece marcada com `TODO[EP-REDE]` para a equipe. O desenho inicial do protocolo é documentado aqui para orientar esse trabalho.

| Arquivo | Uso |
| --- | --- |
| `00-contexto-geral.md` | Fonte única das regras e do protocolo inicial. Ler junto de cada boilerplate. |
| `01-boilerplate-interface.md` | Criar motor, interface e sessão simulada do cliente. |
| `02-boilerplate-servidor.md` | Criar o controlador da partida única, sem rede real nesta etapa. |
| `03-roadmap-equipe.md` | Escolher três frentes sem nomes atribuídos e seguir quatro etapas. |
| `Roadmap-Visual-Tetris-Versus.pdf` | Resumo visual do projeto, das mensagens e das tarefas. |

As decisões de regras e formato abaixo são padrões iniciais de projeto. A equipe pode ajustá-las em conjunto, mantendo os oito tipos e o escopo de dois jogadores.

## 2. Ideia geral

Tetris casual 1vs1 no terminal. Cada cliente executa peças, gravidade, rotação, colisões, limpeza de linhas e pontuação localmente. Limpezas múltiplas geram linhas de lixo para o oponente. O lixo recebido espera o fim da peça atual para entrar no tabuleiro.

O servidor recebe dois jogadores, espera ambos ficarem prontos, encaminha ataques e representações do tabuleiro e confirma um resultado único. Não simula a física. A imagem do oponente é uma cópia eventual dos blocos fixos; não sincroniza movimentos quadro a quadro.

O servidor confia nos fatos informados por clientes cooperativos. Validar uma quantidade de ataque não comprova que a jogada ocorreu. Antitrapaça, reconexão, espectadores, chat e sincronização competitiva ficam fora do escopo.

## 3. Base técnica

- Python 3.12 ou superior, com a mesma versão menor na equipe.
- `curses` para a interface de terminal; validar a disponibilidade no ambiente Linux ou Linux/WSL escolhido.
- Biblioteca padrão para domínio e testes: `dataclasses`, `enum`, `random`, `time`, `unittest`.
- Futuramente, `socket` com TCP e I/O não bloqueante; `selectors` pode ajudar no processamento das duas conexões.
- Memória para o estado da partida. Sem banco de dados ou framework multiplayer.
- Um repositório com os executáveis `tetris_client` e `tetris_server` e um pequeno pacote `tetris_shared`.

O motor não importa socket ou `curses`. O servidor não importa o motor nem a interface. Usar sockets diretos preserva o acesso aos bytes e ao transporte exigido no EP; não substituir o protocolo por HTTP, WebSocket, RPC ou serviço pronto.

## 4. Regras locais do jogo

### Tabuleiro e peças

Tabuleiro de 10 colunas por 20 linhas, sem linhas ocultas. Origem no canto superior esquerdo; x cresce à direita e y para baixo. A matriz contém somente blocos fixos; a peça ativa fica separada.

Sete peças: I, O, T, S, Z, J e L, em gerador 7-bag independente para cada jogador. Cada coleção embaralhada contém uma ocorrência de cada peça. Injetar RNG e relógio nos testes; não sincronizar sementes entre jogadores.

Gravidade fixa: uma linha a cada 700 ms. Queda suave avança uma linha por ação; queda instantânea vai à última posição válida e fixa. Uma tentativa de descer que colide fixa imediatamente, sem lock delay. Rotação horária simples, sem wall kicks. Não incluir hold, combos, T-spins ou níveis no MVP.

### Pontuação e ataque

| Linhas limpas de uma vez | Pontos | Quantidade em ATTACK |
| --- | ---: | ---: |
| 0 | 0 | Não enviar |
| 1 | 100 | Não enviar |
| 2 | 300 | 1 |
| 3 | 500 | 2 |
| 4 | 800 | 4 |

O cliente calcula o ataque e o servidor valida que a quantidade é 1, 2 ou 4, encaminhando-a ao único oponente. **ATTACK informa lixo a aplicar, não linhas limpas.** Não há pontuação por queda nem cancelamento entre ataques recebidos e enviados.

Cada linha de lixo tem nove blocos e um buraco, cuja coluna é escolhida pelo cliente destinatário. Aplicar no máximo quatro linhas pendentes por fixação; o restante fica para a próxima. Guardar um contador de linhas pendentes, pois os ataques não precisam de identidades individuais. Limite proposto: 40 linhas pendentes; exceder esse limite interrompe a sessão por falha local, sem descartar lixo silenciosamente nem declarar KO falso.

### Ordem da fixação

1. Fixar a peça e remover simultaneamente todas as linhas completas.
2. Atualizar score e produzir a intenção de ataque, se houver.
3. Aplicar até quatro linhas de lixo já pendentes antes deste ciclo.
4. Se o lixo expulsar blocos pelo topo, registrar derrota local.
5. Caso contrário, gerar a próxima peça; se o spawn estiver bloqueado, registrar derrota local.
6. Produzir o snapshot final dos blocos fixos e, se necessário, uma única ocorrência de derrota local.

Ataque e derrota na mesma fixação são permitidos; conservar a ordem ataque, snapshot, derrota ao integrá-los. Novas entradas não interrompem a transação de fixação.

A existência de qualquer bloco na primeira linha não basta para perder. Top out ocorre por spawn bloqueado ou expulsão de blocos pelo lixo. Após perder localmente, o cliente congela a física e aguarda `GAMEOVER`, continuando a processar a conexão. No treino, encerra diretamente sem resultado multiplayer.

## 5. Fluxo da única partida

| Momento | Comportamento |
| --- | --- |
| Servidor iniciado | Duas posições livres para conexões, sem fila de jogadores. |
| Primeiro HELLO válido | Registra o apelido e espera o segundo jogador. O cliente mostra espera localmente. |
| Segundo HELLO válido | Servidor envia MATCH com o apelido do oponente para cada um. |
| Preparação | Cada jogador confirma e envia READY com campo PLAYER. |
| Ambos prontos | Servidor ativa a partida e envia READY com campo GO aos dois. |
| Jogo | Clientes enviam BOARD, ATTACK e, ao perder, KO. |
| Encerramento | Servidor registra a decisão antes de enviar GAMEOVER; não aceita novos efeitos de jogo. |
| Fim do processo | Tenta concluir os envios pendentes por até 1 segundo, fecha conexões e termina. Outra partida exige reinício. |

Os dois clientes começam ao receber a autorização `READY|GO`. Não existe início com relógios sincronizados. O envio dessa autorização deve preceder qualquer ataque ou snapshot encaminhado para aquele cliente.

A primeira ocorrência válida de encerramento processada pelo servidor determina o resultado. Dois KOs próximos não mudam a decisão já registrada. Isso resolve a concorrência; não revela a ordem real das derrotas em computadores diferentes.

## 6. Os oito tipos de mensagem

C = cliente; S = servidor. Direção faz parte da semântica. Mensagens bidirecionais não são automaticamente respondidas ou ecoadas.

| Tipo | Direção | Campos de aplicação | Efeito |
| --- | --- | --- | --- |
| HELLO | C para S | apelido | Primeira mensagem do cliente; identifica a participação. Não tem resposta própria. |
| MATCH | S para C | apelido_oponente | Informa que os dois participantes estão identificados; habilita a confirmação de prontidão. |
| READY | C para S; S para C | PLAYER ou GO | PLAYER confirma prontidão individual. GO autoriza ambos a começar, somente após os dois PLAYER. |
| BOARD | C para S; S para o outro C | celulas | Envia 200 células dos blocos fixos. O servidor valida e encaminha a cópia ao oponente. |
| ATTACK | C para S; S para o outro C | quantidade | Leva 1, 2 ou 4 linhas de lixo. Destinatário é derivado da conexão do remetente. |
| KO | C para S | SPAWN ou OVERFLOW | Avisa derrota local por nascimento bloqueado ou transbordamento causado por lixo. |
| GAMEOVER | S para C | resultado, motivo | Resultado individual WIN, LOSE ou CANCEL; motivo KO, DISCONNECT, TIMEOUT, PROTOCOL ou SERVER_STOP. |
| KEEPALIVE | C para S; S para C | Nenhum | Sinal periódico de atividade da aplicação, sem resposta imediata. |

`BOARD` contém exatamente 200 dígitos, linha por linha: 0 = vazio; 1 = I; 2 = O; 3 = T; 4 = S; 5 = Z; 6 = J; 7 = L; 8 = lixo. Não transmitir peça ativa, cores ou caracteres da TUI. Enviar no início autorizado e após cada fixação, inclusive o estado final de derrota. O score é local e não precisa trafegar.

O cliente que recebe BOARD não o retransmite. O cliente que recebe ATTACK apenas acumula lixo, sem ecoar a mensagem. READY repetido com PLAYER é idempotente na preparação e, se atrasado, não reinicia uma partida ativa. GAMEOVER recebido encerra a partida mesmo que o jogador ainda estivesse jogando.

## 7. Começo do protocolo TVP/1

**Desenho para a equipe implementar depois; não colocar codec ou socket funcional nos boilerplates.** Manter exatamente os oito tipos acima, sem mensagens auxiliares adicionais.

Formato textual inicial: ASCII, `|` separando campos, LF terminando uma mensagem. Exemplos de representação; `\n` abaixo significa um único byte LF, não os dois caracteres barra e n:

```text
TVP/1|HELLO|Jogador_A\n
TVP/1|MATCH|Jogador_B\n
TVP/1|READY|PLAYER\n
TVP/1|READY|GO\n
TVP/1|ATTACK|2\n
TVP/1|KO|SPAWN\n
TVP/1|GAMEOVER|WIN|KO\n
TVP/1|KEEPALIVE\n
```

BOARD usa `TVP/1|BOARD|` seguido dos 200 dígitos e LF. Não precisa de jogador_id, partida_id, sequência ou horário remoto: a conexão identifica o jogador e não é reutilizada em outra partida.

Gramática inicial, em notação EBNF simplificada:

```text
mensagem = "TVP/1|", corpo, LF ;
corpo = "HELLO|", apelido
      | "MATCH|", apelido
      | "READY|", ("PLAYER" | "GO")
      | "BOARD|", celulas
      | "ATTACK|", ("1" | "2" | "4")
      | "KO|", ("SPAWN" | "OVERFLOW")
      | "GAMEOVER|", resultado, "|", motivo
      | "KEEPALIVE" ;
resultado = "WIN" | "LOSE" | "CANCEL" ;
motivo = "KO" | "DISCONNECT" | "TIMEOUT" | "PROTOCOL" | "SERVER_STOP" ;
```

Restrições léxicas: LF é byte 10; `apelido` tem 1 a 20 caracteres de `[A-Za-z0-9_]`; `celulas` tem exatamente 200 caracteres de `[0-8]`. Campos extras, espaços, CR, encoding diferente, prefixo incompatível ou tokens desconhecidos são inválidos. Apelidos iguais são permitidos: não são identidade de sessão. Linha completa limitada a 512 bytes, incluindo LF; estourar esse limite antes de chegar LF também é erro.

O parser futuro precisa acumular bytes por conexão, separar todas as linhas completas e guardar o fragmento restante. TCP não preserva fronteiras de mensagens. Escritas podem ser parciais; manter os bytes ainda não enviados. Limite proposto de saída: 4096 bytes por conexão; ao exceder, tratar como falha de conexão. Não descartar ataques silenciosamente. Apenas snapshots ainda não serializados podem ser substituídos por uma versão mais recente.

### Estados válidos

- HELLO é obrigatório como primeira mensagem, uma única vez, em até 5 segundos após aceitar a conexão.
- MATCH só é produzido após os dois HELLO válidos. READY com PLAYER só é aceito após MATCH; GO só vem do servidor e só é emitido uma vez.
- BOARD, ATTACK e KO só são aceitos pelo servidor com partida ativa. Depois do fim, eventos tardios não produzem efeito nem outro resultado.
- KEEPALIVE é permitido depois do HELLO, durante espera, preparação, jogo e espera por resultado.
- GAMEOVER também pode ocorrer antes do início, com CANCEL; combinações permitidas estão na política de falhas abaixo.

### KEEPALIVE sem complicação

Após HELLO, cada lado envia KEEPALIVE a cada 5 segundos, inclusive se há outros dados. No cliente o agendamento começa após enviar HELLO; no servidor, após validar HELLO. Não responder a KEEPALIVE, para evitar um ciclo infinito de respostas.

Cada lado registra, com seu relógio monotônico, a última mensagem completa e válida recebida. Qualquer mensagem válida renova esse instante; bytes parciais ou inválidos não renovam. Após 15 segundos sem mensagem válida, considerar a conexão perdida. No cliente, a contagem inicial começa ao estabelecer a conexão. Esses valores são defaults para a equipe validar, não temporizadores já implementados nos boilerplates.

## 8. Limite de dois jogadores, falhas e resultado

O servidor mantém no máximo duas conexões admitidas, ainda que uma esteja esperando HELLO. Uma terceira conexão é fechada imediatamente, sem criar tipo extra de mensagem nem alterar a partida. Ela pode aparecer temporariamente como tentativa rejeitada na API de socket; não vira participante. O cliente mostra uma mensagem genérica: “Conexão encerrada; o servidor pode estar ocupado”. Não afirmar uma causa que não recebeu.

Uma conexão sem HELLO válido que fecha, envia dados inválidos ou excede 5 segundos é descartada e libera a posição; não cancela a participação de quem já se identificou. Depois que HELLO foi validado, não substituir esse participante por outro.

| Ocorrência de participante já identificado | Antes do início | Durante o jogo |
| --- | --- | --- |
| Fechamento voluntário ou falha de conexão | CANCEL / DISCONNECT ao remanescente | WIN / DISCONNECT ao oponente; LOSE ao ausente é apenas resultado interno. |
| Timeout de atividade | CANCEL / TIMEOUT | WIN / TIMEOUT ao oponente. |
| Violação do protocolo | CANCEL / PROTOCOL | WIN / PROTOCOL ao oponente; encerrar a conexão infratora. |
| KO válido | Não é permitido; tratar como violação | WIN / KO ao oponente e LOSE / KO ao remetente. |
| Parada planejada do servidor | CANCEL / SERVER_STOP | CANCEL / SERVER_STOP aos dois. |

Em encerramento por falha, guardar internamente o resultado do participante ausente/infrator, sem prometer que ele receberá GAMEOVER. Se os dois caírem, a primeira falha processada decide; o vencedor registrado pode estar desconectado e não receber a decisão. Não alterar a decisão por falha posterior de envio.

Ao sair pelo teclado, o cliente fecha a conexão; não existe mensagem de saída adicional. Se o servidor cair abruptamente, o cliente mostra “Partida interrompida; resultado não confirmado”, sem inventar vitória ou derrota. A falha local por excesso de lixo pendente também fecha a conexão e é observada como abandono pelo servidor.

Todo resultado é gravado uma única vez antes de notificar. Nenhum encaminhamento de jogo ocorre depois disso. Fechar após até 1 segundo de tentativa de escoar as notificações; não afirmar entrega garantida a um cliente inacessível. O treino local não depende dessas regras de rede.

## 9. O que os boilerplates entregam e deixam para depois

**Pronto localmente:** motor, TUI, regras comuns, controlador da partida única, modelos tipados, simulações em memória e testes desses componentes.

**Pendente com TODO[EP-REDE]:** sockets, associação de conexão, encoder, parser, framing, buffers, timers de HELLO/KEEPALIVE, tratamento de bytes e integração real. Métodos executáveis ainda não implementados levantam `NotImplementedError`. Modo rede não pode cair silenciosamente no fake.

Os mocks usam objetos Python em memória, sem serialização ou canal externo. Não representam evidência de comunicação para o EP.

## 10. Encaixe no EP

A proposta é compatível com as regras fornecidas: tema livre, protocolo de aplicação autoral sobre TCP, acesso direto ao transporte e **oito tipos estruturados distintos**, acima do mínimo de cinco. Não é necessário suportar múltiplas partidas para atender às regras transcritas.

A conformidade final depende da implementação, dos testes e da documentação de sintaxe, gramática e semântica pela equipe. Confirmar no enunciado completo se TCP sozinho é aceito ou se ambos os transportes são exigidos. A análise não equivale à aprovação do professor.

Fontes: solicitação e regras do EP fornecidas pelo usuário; PDF inicial como referência da ideia de jogo; revisões desta conversa que definiram dois jogadores e os oito tipos. Referências técnicas: [socket](https://docs.python.org/3/library/socket.html), [Socket Programming HOWTO](https://docs.python.org/3/howto/sockets.html) e [curses](https://docs.python.org/3/library/curses.html). As políticas e números deste documento são escolhas de projeto.
