"""Codec TVP/1 e delimitação do fluxo reservados.

TODO[EP-REDE]: ASCII estrito, campos separados por barra vertical, terminação
LF e no máximo 512 bytes incluindo LF. Rejeitar CR, campos extras, tokens
desconhecidos, direções/estados inválidos e prefixos incompatíveis. Acumular
leituras parciais, extrair todas as linhas completas, guardar os bytes restantes
e rejeitar fragmentos excessivos antes de LF. Consultar a gramática completa
em 00-contexto-geral.md.
"""

from .models import Command, OutboundEvent


def encode(event: OutboundEvent) -> bytes:
    """TODO[EP-REDE]: converter um evento de saída em uma linha completa de bytes TVP/1."""
    raise NotImplementedError('TODO[EP-REDE]: encode TVP/1 bytes')


def decode(frame: bytes) -> Command:
    """TODO[EP-REDE]: validar um quadro completo e produzir um comando local."""
    raise NotImplementedError('TODO[EP-REDE]: validate and decode a TVP/1 frame')


class StreamParser:
    def feed(self, data: bytes) -> tuple[Command, ...]:
        """TODO[EP-REDE]: guardar fragmentos e decodificar cada linha completa terminada em LF."""
        raise NotImplementedError('TODO[EP-REDE]: byte buffering and LF framing')
