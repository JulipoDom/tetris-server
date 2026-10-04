"""Reserved transport adapter; no sockets are opened by this boilerplate.

TODO[EP-REDE]: Implement a TCP listener, admission of at most two connections
(including pending HELLO), opaque session association, nonblocking I/O,
partial writes and bounded buffers. Discard unrecognized connections without
canceling an identified player. After identification, connection failure is
a domain fact. Reserve HELLO deadline 5 s, KEEPALIVE every 5 s, inactivity
15 s, output cap 4096 bytes, and final drain deadline 1 s. Use monotonic time;
only complete valid messages refresh activity. Never echo KEEPALIVE.
"""


class NetworkServer:
    def run(self) -> None:
        """TODO[EP-REDE]: replace this stub with the real TCP event loop."""
        raise NotImplementedError('TODO[EP-REDE]: TCP listener, sessions, I/O, buffers, and timers')
