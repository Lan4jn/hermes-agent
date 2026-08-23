"""Shared facts and interface for interactive agent backends."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol


@dataclass(frozen=True)
class BackendTurnRequest:
    session_id: str
    profile: str
    platform: str
    principal_id: str
    text: str
    cwd: str | None
    media_paths: tuple[str, ...] = ()
    trusted: bool = False


@dataclass(frozen=True)
class BackendTurnResult:
    response: str
    conversation_id: str
    usage: Mapping[str, Any]
    status: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "usage", MappingProxyType(dict(self.usage)))


@dataclass(frozen=True)
class BackendEvent:
    kind: str
    text: str = ""
    tool_name: str = ""
    status: str = ""

    def __post_init__(self) -> None:
        if self.kind not in {"message_delta", "tool", "status"}:
            raise ValueError(
                "backend event kind must be one of: message_delta, tool, status"
            )


BackendEventSink = Callable[[BackendEvent], None]


class InteractiveAgentBackend(Protocol):
    def run_turn(
        self, request: BackendTurnRequest, events: BackendEventSink
    ) -> BackendTurnResult: ...

    def interrupt(self, session_id: str) -> bool: ...

    def close_session(self, session_id: str) -> None: ...

    def shutdown(self) -> None: ...
