# Mapa atual do código

Atualizado em 08/10/2026. O nome deste documento conserva a origem do
projeto; o código atual inclui transporte TCP e não é apenas boilerplate.

- `src/tetris_server/__init__.py`
- `src/tetris_server/__main__.py`
- `src/tetris_server/app.py`
- `src/tetris_server/communication.py`
- `src/tetris_server/match.py`
- `src/tetris_server/network.py`
- `src/tetris_server/network_diagnostic.py`
- `src/tetris_server/simulation.py`
- `src/tetris_shared/__init__.py`
- `src/tetris_shared/models.py`
- `src/tetris_shared/protocol.py`
- `src/tetris_shared/rules.py`

Execução: [README.md](README.md). Regras: [00-contexto-geral.md](00-contexto-geral.md).
Contrato: [docs/PROTOCOLO_TCP.md](docs/PROTOCOLO_TCP.md).
Todos os arquivos de testes automatizados foram removidos; evidências foram
conservadas em [docs/RELATORIO_VALIDACAO.md](docs/RELATORIO_VALIDACAO.md).
