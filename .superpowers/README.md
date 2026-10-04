# Skills do Superpowers

As skills do Superpowers orientam o trabalho do agente: entendimento dos
requisitos, planejamento, implementação, testes, diagnóstico e revisão. Elas
estão disponíveis no ambiente usado nesta sessão pelo plugin Superpowers 6.4.2.
São instruções de desenvolvimento para o agente; o servidor Python não depende
delas para executar. Clonar este repositório não instala o plugin automaticamente.

| Skill | Quando usar no projeto |
| --- | --- |
| `superpowers:using-superpowers` | No início do trabalho, para identificar e aplicar as skills relevantes. |
| `superpowers:brainstorming` | Antes de criar funcionalidades ou alterar comportamentos, para esclarecer objetivo, requisitos e desenho da solução. |
| `superpowers:writing-plans` | Para transformar a especificação em tarefas, interfaces e verificações antes de implementar. |
| `superpowers:executing-plans` | Quando o próprio agente executa um plano na sessão atual. |
| `superpowers:subagent-driven-development` | Quando agentes separados implementam e revisam as tarefas de um plano. |
| `superpowers:dispatching-parallel-agents` | Para distribuir tarefas independentes entre agentes sem disputar os mesmos arquivos. |
| `superpowers:test-driven-development` | Para escrever um teste que falha antes da implementação e verificar que passa depois. |
| `superpowers:systematic-debugging` | Para reproduzir uma falha, investigar sua causa e só então corrigir. |
| `superpowers:requesting-code-review` | Para solicitar uma revisão independente da implementação e dos requisitos. |
| `superpowers:receiving-code-review` | Para verificar tecnicamente os apontamentos de revisão antes de aplicar mudanças. |
| `superpowers:verification-before-completion` | Para executar as verificações e conferir os resultados antes de declarar o trabalho concluído. |
| `superpowers:using-git-worktrees` | Quando o trabalho precisa de isolamento em um repositório Git utilizável. |
| `superpowers:finishing-a-development-branch` | Após concluir a implementação e passar nas verificações, para organizar a integração da branch. |
| `superpowers:writing-skills` | Para criar, editar ou validar instruções de skills, quando isso fizer parte da tarefa. |
| `superpowers:diagnosing-superpowers` | Para investigar problemas no próprio fluxo do Superpowers, como repetição de trabalho ou planos ignorados. |

### Aplicação à próxima etapa de rede

1. Ler os documentos de contexto e o checklist em [IMPLEMENTS.md](../IMPLEMENTS.md).
2. Usar `brainstorming` e `writing-plans` para definir as interfaces do codec,
   parser e adaptador TCP, respeitando os oito tipos de mensagem.
3. Executar o plano com `executing-plans` ou `subagent-driven-development`,
   conforme a forma de trabalho escolhida. Aplicar `test-driven-development`
   aos comportamentos de rede e manter os testes existentes do domínio.
4. Usar `systematic-debugging` ao encontrar falhas, `requesting-code-review`
   para revisão e `receiving-code-review` para avaliar os apontamentos.
5. Aplicar `verification-before-completion` aos testes e cenários reais antes
   de afirmar que o servidor TCP funciona.

As skills não substituem a implementação manual descrita no [README do projeto](../README.md) nem
comprovam comunicação de rede: os pontos `TODO[EP-REDE]` continuam pendentes.

## Plano da estrutura inicial

O [plano concluído](plans/2026-10-04-server-boilerplate.md) registra as tarefas
e verificações da implementação local.
