"""Stable public contract for interactive agent backends."""

from .base import (
    BackendEvent,
    BackendEventSink,
    BackendTurnRequest,
    BackendTurnResult,
    InteractiveAgentBackend,
)
from .antigravity import AntigravitySession
from .config import (
    AntigravityConfig,
    BackendSelection,
    parse_antigravity_config,
    resolve_backend,
)
from .hermes import HermesBackend

__all__ = [
    "AntigravityConfig",
    "AntigravitySession",
    "BackendEvent",
    "BackendEventSink",
    "BackendSelection",
    "BackendTurnRequest",
    "BackendTurnResult",
    "HermesBackend",
    "InteractiveAgentBackend",
    "parse_antigravity_config",
    "resolve_backend",
]
