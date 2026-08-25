"""Interactive agent backend router and dispatcher."""

from __future__ import annotations

import logging
from typing import Any, Callable, Mapping

from .base import BackendEventSink, BackendTurnRequest, BackendTurnResult
from .config import (
    AntigravityConfig,
    BackendSelection,
    parse_antigravity_config,
    resolve_backend,
)
from .pool import AntigravitySessionPool

logger = logging.getLogger(__name__)


class BackendRouter:
    """Dispatches interactive turns between Hermes and Antigravity."""

    def __init__(
        self,
        config: Mapping[str, Any] | None = None,
        session_db: Any = None,
        pool: AntigravitySessionPool | None = None,
        cwd: str | None = None,
    ) -> None:
        self._raw_config = config or {}
        self._antigravity_config = parse_antigravity_config(self._raw_config)
        self._session_db = session_db
        self._pool = pool or AntigravitySessionPool(
            self._antigravity_config, cwd=cwd
        )

    @property
    def config(self) -> AntigravityConfig:
        return self._antigravity_config

    @property
    def pool(self) -> AntigravitySessionPool:
        return self._pool

    def resolve(
        self, platform: str, session_override: str | None = None
    ) -> BackendSelection:
        return resolve_backend(
            self._raw_config,
            platform=platform,
            session_override=session_override,
        )

    def run_turn(
        self,
        request: BackendTurnRequest,
        events: BackendEventSink,
        *,
        hermes_runner: (
            Callable[[BackendTurnRequest, BackendEventSink], BackendTurnResult]
            | None
        ) = None,
        session_override: str | None = None,
    ) -> BackendTurnResult:
        selection = self.resolve(
            platform=request.platform, session_override=session_override
        )
        if selection.name == "antigravity":
            result = self._pool.run_turn(request, events)
            if self._session_db is not None and request.session_id:
                try:
                    self._session_db.set_session_agent_backend(
                        request.session_id,
                        "antigravity",
                        result.conversation_id or "",
                    )
                except Exception:
                    logger.debug(
                        "failed to persist antigravity session state",
                        exc_info=True,
                    )
            return result
        elif selection.name == "hermes":
            if hermes_runner is None:
                raise ValueError(
                    "No hermes runner provided for hermes backend turn"
                )
            result = hermes_runner(request, events)
            if self._session_db is not None and request.session_id:
                try:
                    self._session_db.set_session_agent_backend(
                        request.session_id,
                        "hermes",
                        result.conversation_id or "",
                    )
                except Exception:
                    logger.debug(
                        "failed to persist hermes session state", exc_info=True
                    )
            return result
        else:
            raise ValueError(f"Unknown backend: {selection.name}")

    def interrupt(self, profile: str, platform: str, session_id: str) -> bool:
        return self._pool.interrupt(profile, platform, session_id)

    def close_session(
        self, profile: str, platform: str, session_id: str
    ) -> None:
        self._pool.close_session(profile, platform, session_id)

    def cleanup_idle(self) -> None:
        self._pool.cleanup_idle()

    def shutdown(self) -> None:
        self._pool.shutdown()
