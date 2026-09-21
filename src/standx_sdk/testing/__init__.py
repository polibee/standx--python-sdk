"""Offline test doubles for SDK consumers and the SDK test suite."""

from .fake_websocket import FakeWebSocketServer, FakeWebSocketTransport

__all__ = ["FakeWebSocketServer", "FakeWebSocketTransport"]
