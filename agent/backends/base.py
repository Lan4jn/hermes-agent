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

    def __post_init__(self) -> None:
        object.__setattr__(self, "media_paths", tuple(self.media_paths))


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class BackendTurnResult:
    response: str
    conversation_id: str
    usage: Mapping[str, Any]
    status: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "usage", _freeze(self.usage))


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
