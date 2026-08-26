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
            if getattr(entry.session, "resume_safe", False) and not entry.recovered:
                self._resume_entry_before_turn(key, entry, request)
            try:
                result = entry.session.run_turn(request, events)
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
            entry = self._entries.get(key)
        if entry is not None:
            if not self._close_and_remove(key, entry):
                raise RuntimeError(f"failed to close Antigravity session {key}")

    def shutdown(self) -> list[_PoolKey]:
        """Shut down the pool, terminate all child processes, and release resources."""
        with self._lock:
            self._closed = True
            entries = list(self._entries.items())
        failed_keys: list[_PoolKey] = []
        for key, entry in entries:
            if not self._close_and_remove(key, entry, interrupt=True):
                failed_keys.append(key)
        return failed_keys

    def cleanup_idle(self) -> None:
        """Close sessions that have been idle longer than the timeout."""
        now = time.monotonic()
        candidates: list[tuple[_PoolKey, _PoolEntry]] = []
        with self._lock:
            for key, entry in self._entries.items():
                if (
                    entry.leases == 0
                    and (now - entry.last_used) >= self._config.idle_timeout_seconds
                ):
                    candidates.append((key, entry))
        for key, entry in candidates:
            self._close_and_remove(key, entry)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def has_entry(self, profile: str, platform: str, session_id: str) -> bool:
        key = (profile, platform, session_id)
        with self._lock:
            return key in self._entries

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

    def _close_and_remove(
        self,
        key: _PoolKey,
        entry: _PoolEntry,
        *,
        interrupt: bool = False,
    ) -> bool:
        """Close entry session safely and remove from pool only upon verified success."""
        if interrupt:
            try:
                entry.session.interrupt()
            except Exception:
                pass

        entry.lock.acquire()
        try:
            entry.session.close()
        except Exception:
            logger.warning(
                "failed to close Antigravity session %s; retaining in tracking",
                key,
                exc_info=True,
            )
            return False
        finally:
            entry.lock.release()

        with self._lock:
            if self._entries.get(key) is entry and entry.leases == 0:
                self._entries.pop(key, None)
                return True
        return False

    def _acquire(self, key: _PoolKey, request: BackendTurnRequest) -> _PoolEntry:
        while True:
            evict_candidate: tuple[_PoolKey, _PoolEntry] | None = None
            with self._lock:
                if self._closed:
                    raise RuntimeError("session pool is shut down")
                entry = self._entries.get(key)
                if entry is not None:
                    entry.leases += 1
                    entry.last_used = time.monotonic()
                    return entry

                if len(self._entries) < self._config.max_sessions:
                    cwd = request.cwd or self._cwd
                    conv_id = request.conversation_id or ""
                    session = AntigravitySession(
                        self._config, cwd, conversation_id=conv_id
                    )
                    new_entry = _PoolEntry(session)
                    new_entry.leases = 1
                    self._entries[key] = new_entry
                    return new_entry

                # Need eviction: find candidate inside lock
                oldest_key: _PoolKey | None = None
                oldest_time = float("inf")
                for k, e in self._entries.items():
                    if e.leases == 0 and e.last_used < oldest_time:
                        oldest_time = e.last_used
                        oldest_key = k
                if oldest_key is not None:
                    evict_candidate = (oldest_key, self._entries[oldest_key])
                else:
                    raise RuntimeError(
                        "all backend sessions are busy — capacity exhausted"
                    )

            # Evict outside global lock
            if evict_candidate is not None:
                cand_key, cand_entry = evict_candidate
                if not self._close_and_remove(cand_key, cand_entry):
                    raise RuntimeError(
                        f"failed to evict idle session {cand_key} — capacity exhausted"
                    )

    def _release(self, key: _PoolKey, entry: _PoolEntry, failed: bool = False) -> None:
        should_close = False
        with self._lock:
            entry.leases = max(0, entry.leases - 1)
            entry.last_used = time.monotonic()
            if failed:
                entry.marked_fatal = True
            if entry.leases == 0 and entry.marked_fatal:
                should_close = True

        if should_close:
            self._close_and_remove(key, entry)

    def _resume_entry_before_turn(
        self,
        key: _PoolKey,
        entry: _PoolEntry,
        request: BackendTurnRequest,
    ) -> None:
        """Resume a dead session between turns using ``--conversation`` before running."""
        conv_id = entry.session.conversation_id
        if not conv_id:
            return

        logger.info(
            "resuming dead Antigravity session between turns for %s with conversation %s",
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
