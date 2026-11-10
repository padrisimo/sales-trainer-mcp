"""Session tokens this server has issued or served, for the WebSocket handshake."""

_TOKENS: set[str] = set()


def register(token: str) -> None:
    # shortcut: one process, one set, no lock; revisit when uvicorn runs several workers.
    if token:
        _TOKENS.add(token)


def is_known(token: str) -> bool:
    return bool(token) and token in _TOKENS
