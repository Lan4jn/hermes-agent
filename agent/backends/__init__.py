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
from .pool import AntigravitySessionPool

__all__ = [
    "AntigravityConfig",
    "AntigravitySession",
    "AntigravitySessionPool",
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
