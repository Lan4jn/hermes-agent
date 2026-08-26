"""Session pool for Antigravity backend processes.

Manages a bounded set of long-lived ``AntigravitySession`` instances keyed
by ``(profile, platform, session_id)``.  Provides per-session turn
serialization, LRU idle eviction at capacity, idle-timeout cleanup, and
one-time crash recovery via ``--conversation``.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from .antigravity import AntigravitySession
from .base import BackendEventSink, BackendTurnRequest, BackendTurnResult
from .config import AntigravityConfig

logger = logging.getLogger(__name__)

_PoolKey = tuple[str, str, str]  # (profile, platform, session_id)


class _PoolEntry:
    """Mutable bookkeeping for one pooled session."""

    __slots__ = ("session", "lock", "last_used", "leases", "recovered", "marked_fatal")

    def __init__(self, session: AntigravitySession) -> None:
        self.session = session
        self.lock = threading.Lock()
        self.last_used = time.monotonic()
        self.leases = 0
        self.recovered = False
        self.marked_fatal = False

    @property
    def busy(self) -> bool:
        return self.leases > 0


class AntigravitySessionPool:
    """Bounded pool of ``AntigravitySession`` instances.

    * **Composite key** ``(profile, platform, session_id)`` — each triple
      gets its own ``agy`` process.
    * **Per-session lock** — concurrent turns on the *same* key are
      serialized; different keys may run in parallel.
    * **LRU idle eviction** — when ``max_sessions`` is reached, the
      least-recently-used *idle* entry is closed. Busy entries are never
      evicted; if every slot is busy the new turn is rejected.
    * **Idle timeout** — ``cleanup_idle()`` closes sessions that have been
      idle longer than ``idle_timeout_seconds``.
    * **One-time crash recovery** — if the ``agy`` process exits between
      turns, the pool creates a fresh session with
      ``--conversation <saved_id>`` and retries once. A second crash is
      surfaced as an error.
    """

    def __init__(self, config: AntigravityConfig, cwd: str | None = None) -> None:
        self._config = config
        self._cwd = cwd or "."
        self._lock = threading.Lock()
        self._entries: dict[_PoolKey, _PoolEntry] = {}
        self._closed = False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run_turn(
        self, request: BackendTurnRequest, events: BackendEventSink
    ) -> BackendTurnResult:
        key = (request.profile, request.platform, request.session_id)
        entry = self._acquire(key, request)
        failed = False
        entry.lock.acquire()
        try:
            try:
                result = entry.session.run_turn(request, events)
            except (RuntimeError, OSError):
                # Process may have died — attempt one-time recovery if dead
                if not entry.session.is_alive():
                    result = self._try_recovery(key, entry, request, events)
                else:
                    failed = True
                    raise
            except Exception:
                failed = True
                raise
            return result
        finally:
            entry.lock.release()
            self._release(key, entry, failed=failed)

    def interrupt(self, profile: str, platform: str, session_id: str) -> bool:
        key = (profile, platform, session_id)
        with self._lock:
            entry = self._entries.get(key)
        if entry is None:
            return False
        return entry.session.interrupt()

    def close_session(self, profile: str, platform: str, session_id: str) -> None:
        key = (profile, platform, session_id)
        with self._lock:
            entry = self._entries.pop(key, None)
        if entry is not None:
            try:
                entry.session.close()
            except Exception:
                logger.debug("error closing session %s", key, exc_info=True)

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            entries = list(self._entries.values())
            self._entries.clear()
        for entry in entries:
            try:
                entry.session.interrupt()
            except Exception:
                pass
            try:
                entry.session.close()
            except Exception:
                logger.debug("error during pool shutdown", exc_info=True)

    def cleanup_idle(self) -> None:
        """Close sessions that have been idle longer than the timeout."""
        now = time.monotonic()
        to_close: list[tuple[_PoolKey, _PoolEntry]] = []
        with self._lock:
            for key, entry in list(self._entries.items()):
                if (
                    entry.leases == 0
                    and (now - entry.last_used) >= self._config.idle_timeout_seconds
                ):
                    self._entries.pop(key, None)
                    to_close.append((key, entry))
        for key, entry in to_close:
            try:
                entry.session.close()
            except Exception:
                logger.debug("error closing idle session %s", key, exc_info=True)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def session_pid(self, profile: str, platform: str, session_id: str) -> int | None:
        key = (profile, platform, session_id)
        with self._lock:
            entry = self._entries.get(key)
        if entry is None:
            return None
        return entry.session.pid

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._entries)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _acquire(self, key: _PoolKey, request: BackendTurnRequest) -> _PoolEntry:
        with self._lock:
            if self._closed:
                raise RuntimeError("session pool is shut down")
            entry = self._entries.get(key)
            if entry is None:
                if len(self._entries) >= self._config.max_sessions:
                    self._evict_lru_idle_locked()
                if len(self._entries) >= self._config.max_sessions:
                    raise RuntimeError(
                        "all backend sessions are busy — capacity exhausted"
                    )
                cwd = request.cwd or self._cwd
                session = AntigravitySession(self._config, cwd)
                entry = _PoolEntry(session)
                self._entries[key] = entry
            entry.leases += 1
            entry.last_used = time.monotonic()
            return entry

    def _release(self, key: _PoolKey, entry: _PoolEntry, failed: bool = False) -> None:
        session_to_close = None
        with self._lock:
            entry.leases = max(0, entry.leases - 1)
            entry.last_used = time.monotonic()
            if failed:
                entry.marked_fatal = True
            if entry.leases == 0 and entry.marked_fatal:
                if self._entries.get(key) is entry:
                    self._entries.pop(key, None)
                session_to_close = entry.session

        if session_to_close is not None:
            try:
                session_to_close.close()
            except Exception:
                pass

    def _evict_lru_idle_locked(self) -> None:
        """Evict the least-recently-used idle entry. Caller holds ``_lock``."""
        oldest_key: _PoolKey | None = None
        oldest_time = float("inf")
        for key, entry in self._entries.items():
            if entry.leases == 0 and entry.last_used < oldest_time:
                oldest_time = entry.last_used
                oldest_key = key
        if oldest_key is not None:
            entry = self._entries.pop(oldest_key)
            try:
                entry.session.close()
            except Exception:
                logger.debug(
                    "error evicting idle session %s", oldest_key, exc_info=True
                )

    def _try_recovery(
        self,
        key: _PoolKey,
        entry: _PoolEntry,
        request: BackendTurnRequest,
        events: BackendEventSink,
    ) -> BackendTurnResult:
        """Attempt one-time crash recovery using ``--conversation``."""
        conv_id = entry.session.conversation_id
        if not conv_id or entry.recovered:
            # No conversation to resume or already recovered once.
            with self._lock:
                if self._entries.get(key) is entry:
                    self._entries.pop(key, None)
            try:
                entry.session.close()
            except Exception:
                pass
            raise RuntimeError(
                "Antigravity session terminated and cannot be recovered"
            )

        logger.info(
            "recovering Antigravity session %s with conversation %s",
            key,
            conv_id,
        )
        try:
            entry.session.close()
        except Exception:
            pass

        cwd = request.cwd or self._cwd
        new_session = AntigravitySession(
            self._config, cwd, conversation_id=conv_id
        )
        entry.session = new_session
        entry.recovered = True

        try:
            return new_session.run_turn(request, events)
        except Exception:
            with self._lock:
                if self._entries.get(key) is entry:
                    self._entries.pop(key, None)
            try:
                entry.session.close()
            except Exception:
                pass
            raise RuntimeError(
                "Antigravity session recovery failed — "
                "use /new to start a fresh session"
            )
