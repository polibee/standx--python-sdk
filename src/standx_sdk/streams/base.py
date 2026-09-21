"""Shared WebSocket stream state and subscription lifecycle."""


class StreamBase:
    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint
        self._closed = False

    def close(self) -> None:
        self._closed = True

    @property
    def closed(self) -> bool:
        return self._closed
