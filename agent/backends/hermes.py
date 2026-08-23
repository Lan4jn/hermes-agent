"""Adapter that keeps the native Hermes agent loop owned by each surface."""

from collections.abc import Callable

from .base import BackendEventSink, BackendTurnRequest, BackendTurnResult


NativeTurn = Callable[[BackendTurnRequest, BackendEventSink], BackendTurnResult]


class HermesBackend:
    def __init__(self, native_turn: NativeTurn) -> None:
        self._native_turn = native_turn

    def run_turn(
        self, request: BackendTurnRequest, events: BackendEventSink
    ) -> BackendTurnResult:
        return self._native_turn(request, events)

    def interrupt(self, session_id: str) -> bool:
        return False

    def close_session(self, session_id: str) -> None:
        return None

    def shutdown(self) -> None:
        return None
