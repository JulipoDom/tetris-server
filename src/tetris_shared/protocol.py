"""Reserved TVP/1 codec and stream framing.

TODO[EP-REDE]: Strict ASCII, pipe-delimited fields, LF termination, at most
512 bytes including LF. Reject CR, extra fields, unknown tokens, invalid
directions/states, and incompatible prefixes. Accumulate partial reads,
extract every complete line, retain remaining bytes and reject oversize
fragments before LF. See 00-contexto-geral.md for the complete grammar.
"""

from .models import Command, OutboundEvent


def encode(event: OutboundEvent) -> bytes:
    """TODO[EP-REDE]: turn an outgoing event into a complete TVP/1 byte line."""
    raise NotImplementedError('TODO[EP-REDE]: encode TVP/1 bytes')


def decode(frame: bytes) -> Command:
    """TODO[EP-REDE]: validate a complete frame and produce a local command."""
    raise NotImplementedError('TODO[EP-REDE]: validate and decode a TVP/1 frame')


class StreamParser:
    def feed(self, data: bytes) -> tuple[Command, ...]:
        """TODO[EP-REDE]: retain fragments and decode every complete LF-ended line."""
        raise NotImplementedError('TODO[EP-REDE]: byte buffering and LF framing')
