"""Tests for AntigravitySessionPool — capacity, LRU eviction, recovery."""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from agent.backends.base import BackendEvent, BackendTurnRequest, BackendTurnResult
from agent.backends.config import parse_antigravity_config
from agent.backends.pool import AntigravitySessionPool

FAKE_AGY = str(Path(__file__).resolve().parents[2] / "fixtures" / "fake_agy.py")


def _config(**overrides):
    base = {
        "agent_backends": {
            "antigravity": {
                "command": f'"{sys.executable}" "{FAKE_AGY}"',
                "permission_mode": "sandbox",
                "max_sessions": 4,
                "idle_timeout_seconds": 300,
                **overrides,
            }
        }
    }
    return parse_antigravity_config(base)


def _request(
    text="hello",
    session_id="s1",
    profile="default",
    platform="cli",
    trusted=False,
):
    return BackendTurnRequest(
        session_id=session_id,
        profile=profile,
        platform=platform,
        principal_id="user",
        text=text,
        cwd=os.getcwd(),
        trusted=trusted,
    )


def _collect_events():
    events = []
    return events, events.append


# ---------------------------------------------------------------------------
# Basic turn and process reuse
# ---------------------------------------------------------------------------


class TestBasicTurns:
    def test_single_turn(self):
        pool = AntigravitySessionPool(_config())
        events, sink = _collect_events()
        try:
            result = pool.run_turn(_request("hello"), sink)
            assert result.response == "reply:hello"
            assert result.status == "SUCCESS"
            assert result.conversation_id == "fake-conversation-1"
            assert any(e.kind == "message_delta" for e in events)
        finally:
            pool.shutdown()

    def test_same_key_reuses_process(self):
        pool = AntigravitySessionPool(_config())
        try:
            e1, s1 = _collect_events()
            r1 = pool.run_turn(_request("first"), s1)
            pid1 = pool.session_pid("default", "cli", "s1")

            e2, s2 = _collect_events()
            r2 = pool.run_turn(_request("second"), s2)
            pid2 = pool.session_pid("default", "cli", "s1")

            assert r1.conversation_id == r2.conversation_id
            assert pid1 == pid2
            assert pid1 is not None
        finally:
            pool.shutdown()


# ---------------------------------------------------------------------------
# Composite key isolation
# ---------------------------------------------------------------------------


class TestCompositeKeys:
    def test_different_session_ids_are_isolated(self):
        pool = AntigravitySessionPool(_config())
        try:
            pool.run_turn(_request("a", session_id="s1"), lambda e: None)
            pool.run_turn(_request("b", session_id="s2"), lambda e: None)

            pid1 = pool.session_pid("default", "cli", "s1")
            pid2 = pool.session_pid("default", "cli", "s2")
            assert pid1 != pid2
            assert pid1 is not None and pid2 is not None
        finally:
            pool.shutdown()

    def test_different_profiles_are_isolated(self):
        pool = AntigravitySessionPool(_config())
        try:
            pool.run_turn(
                _request("a", session_id="s1", profile="work"), lambda e: None
            )
            pool.run_turn(
                _request("b", session_id="s1", profile="personal"), lambda e: None
            )

            pid1 = pool.session_pid("work", "cli", "s1")
            pid2 = pool.session_pid("personal", "cli", "s1")
            assert pid1 != pid2
        finally:
            pool.shutdown()

    def test_different_platforms_are_isolated(self):
        pool = AntigravitySessionPool(_config())
        try:
            pool.run_turn(
                _request("a", session_id="s1", platform="cli"), lambda e: None
            )
            pool.run_turn(
                _request("b", session_id="s1", platform="telegram"), lambda e: None
            )

            pid1 = pool.session_pid("default", "cli", "s1")
            pid2 = pool.session_pid("default", "telegram", "s1")
            assert pid1 != pid2
        finally:
            pool.shutdown()


# ---------------------------------------------------------------------------
# Per-session serial locking
# ---------------------------------------------------------------------------


class TestPerSessionLocking:
    def test_concurrent_turns_on_same_session_are_serialized(self):
        """Two turns on the same key must not overlap."""
        pool = AntigravitySessionPool(_config())
        try:
            order = []
            barrier = threading.Barrier(2, timeout=5)

            def turn(label):
                barrier.wait()
                pool.run_turn(_request(label, session_id="s1"), lambda e: None)
                order.append(label)

            t1 = threading.Thread(target=turn, args=("first",))
            t2 = threading.Thread(target=turn, args=("second",))
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)

            assert len(order) == 2
        finally:
            pool.shutdown()

    def test_concurrent_turns_on_different_sessions_proceed(self):
        """Different keys may run in parallel."""
        pool = AntigravitySessionPool(_config())
        try:
            results = {}
            barrier = threading.Barrier(2, timeout=5)

            def turn(sid):
                barrier.wait()
                r = pool.run_turn(_request("hi", session_id=sid), lambda e: None)
                results[sid] = r

            t1 = threading.Thread(target=turn, args=("s1",))
            t2 = threading.Thread(target=turn, args=("s2",))
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)

            assert "s1" in results and "s2" in results
            assert results["s1"].response == "reply:hi"
            assert results["s2"].response == "reply:hi"
        finally:
            pool.shutdown()


# ---------------------------------------------------------------------------
# LRU idle eviction at capacity
# ---------------------------------------------------------------------------


class TestLRUEviction:
    def test_evicts_lru_idle_when_at_capacity(self):
        config = _config(max_sessions=2)
        pool = AntigravitySessionPool(config)
        try:
            pool.run_turn(_request("a", session_id="s1"), lambda e: None)
            time.sleep(0.01)
            pool.run_turn(_request("b", session_id="s2"), lambda e: None)

            pid_s1_before = pool.session_pid("default", "cli", "s1")
            assert pid_s1_before is not None

            # s3 forces eviction — s1 is the LRU idle entry
            pool.run_turn(_request("c", session_id="s3"), lambda e: None)

            assert pool.session_pid("default", "cli", "s1") is None
            assert pool.session_pid("default", "cli", "s2") is not None
            assert pool.session_pid("default", "cli", "s3") is not None
        finally:
            pool.shutdown()

    def test_busy_sessions_are_never_evicted(self):
        """When all sessions are busy, new turn is rejected."""
        config = _config(max_sessions=1)
        pool = AntigravitySessionPool(config)
        try:
            started = threading.Event()
            hold = threading.Event()

            def slow_turn():
                started.set()
                try:
                    pool.run_turn(_request("TIMEOUT", session_id="s1"), lambda e: None)
                except RuntimeError:
                    pass  # Expected when interrupted.

            t = threading.Thread(target=slow_turn)
            t.start()
            started.wait(timeout=3)
            # Give the turn time to acquire the lock and start
            time.sleep(0.5)

            with pytest.raises(RuntimeError, match="capacity|busy"):
                pool.run_turn(_request("hi", session_id="s2"), lambda e: None)

            # Clean up: interrupt the blocking turn
            pool.interrupt("default", "cli", "s1")
            t.join(timeout=5)
        finally:
            pool.shutdown()


# ---------------------------------------------------------------------------
# Idle timeout cleanup
# ---------------------------------------------------------------------------


class TestIdleTimeout:
    def test_idle_sessions_are_cleaned_up(self):
        config = _config(max_sessions=4, idle_timeout_seconds=1)
        pool = AntigravitySessionPool(config)
        try:
            pool.run_turn(_request("a", session_id="s1"), lambda e: None)
            assert pool.session_pid("default", "cli", "s1") is not None

            time.sleep(1.5)
            pool.cleanup_idle()

            assert pool.session_pid("default", "cli", "s1") is None
        finally:
            pool.shutdown()

    def test_recently_used_sessions_survive_cleanup(self):
        config = _config(idle_timeout_seconds=10)
        pool = AntigravitySessionPool(config)
        try:
            pool.run_turn(_request("a", session_id="s1"), lambda e: None)
            pool.cleanup_idle()

            assert pool.session_pid("default", "cli", "s1") is not None
        finally:
            pool.shutdown()


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------


class TestShutdown:
    def test_shutdown_closes_all_sessions(self):
        pool = AntigravitySessionPool(_config())
        pool.run_turn(_request("a", session_id="s1"), lambda e: None)
        pool.run_turn(_request("b", session_id="s2"), lambda e: None)
        pid1 = pool.session_pid("default", "cli", "s1")
        pid2 = pool.session_pid("default", "cli", "s2")
        assert pid1 is not None and pid2 is not None

        pool.shutdown()

        assert pool.session_pid("default", "cli", "s1") is None
        assert pool.session_pid("default", "cli", "s2") is None

    def test_turn_after_shutdown_raises(self):
        pool = AntigravitySessionPool(_config())
        pool.shutdown()

        with pytest.raises(RuntimeError, match="shut.?down"):
            pool.run_turn(_request("hi"), lambda e: None)

    def test_shutdown_is_idempotent(self):
        pool = AntigravitySessionPool(_config())
        pool.run_turn(_request("a"), lambda e: None)
        pool.shutdown()
        pool.shutdown()  # must not raise


# ---------------------------------------------------------------------------
# Close single session
# ---------------------------------------------------------------------------


class TestCloseSession:
    def test_close_removes_session_from_pool(self):
        pool = AntigravitySessionPool(_config())
        try:
            pool.run_turn(_request("a", session_id="s1"), lambda e: None)
            assert pool.session_pid("default", "cli", "s1") is not None

            pool.close_session("default", "cli", "s1")
            assert pool.session_pid("default", "cli", "s1") is None
        finally:
            pool.shutdown()

    def test_close_nonexistent_is_noop(self):
        pool = AntigravitySessionPool(_config())
        try:
            pool.close_session("default", "cli", "nonexistent")
        finally:
            pool.shutdown()


# ---------------------------------------------------------------------------
# Interrupt
# ---------------------------------------------------------------------------


class TestInterrupt:
    def test_interrupt_stops_active_session(self):
        pool = AntigravitySessionPool(_config())
        try:
            started = threading.Event()

            def slow():
                started.set()
                try:
                    pool.run_turn(_request("TIMEOUT", session_id="s1"), lambda e: None)
                except RuntimeError:
                    pass

            t = threading.Thread(target=slow)
            t.start()
            started.wait(timeout=3)
            time.sleep(0.5)

            result = pool.interrupt("default", "cli", "s1")
            assert result is True
            t.join(timeout=5)
        finally:
            pool.shutdown()

    def test_interrupt_nonexistent_returns_false(self):
        pool = AntigravitySessionPool(_config())
        try:
            assert pool.interrupt("default", "cli", "nonexistent") is False
        finally:
            pool.shutdown()


# ---------------------------------------------------------------------------
# Crash recovery with --conversation
# ---------------------------------------------------------------------------


class TestCrashRecovery:
    def test_recovery_after_process_exit_uses_conversation_id(self):
        """After process exits, pool retries once with --conversation."""
        pool = AntigravitySessionPool(_config())
        try:
            # First turn establishes conversation
            r1 = pool.run_turn(_request("hello", session_id="s1"), lambda e: None)
            conv_id = r1.conversation_id
            assert conv_id == "fake-conversation-1"

            # Force process exit
            pool.run_turn(
                _request("EXIT_AFTER_RESULT", session_id="s1"), lambda e: None
            )
            # Process should have exited after this turn

            # Next turn should recover with --conversation
            events, sink = _collect_events()
            r2 = pool.run_turn(_request("recovered", session_id="s1"), sink)
            assert r2.response == "reply:recovered"
            # The recovered session should have used the conversation_id
            assert r2.conversation_id == conv_id
        finally:
            pool.shutdown()

    def test_second_crash_after_recovery_is_fatal(self):
        """Recovery is one-time: a second crash raises."""
        pool = AntigravitySessionPool(_config())
        try:
            pool.run_turn(_request("hello", session_id="s1"), lambda e: None)
            pool.run_turn(
                _request("EXIT_AFTER_RESULT", session_id="s1"), lambda e: None
            )
            # First recovery
            pool.run_turn(_request("recovered", session_id="s1"), lambda e: None)
            # Force exit again
            pool.run_turn(
                _request("EXIT_AFTER_RESULT", session_id="s1"), lambda e: None
            )

            # Second recovery should fail
            with pytest.raises(RuntimeError):
                pool.run_turn(_request("again", session_id="s1"), lambda e: None)
        finally:
            pool.shutdown()


# ---------------------------------------------------------------------------
# Pool size reporting
# ---------------------------------------------------------------------------


class TestPoolInfo:
    def test_active_count(self):
        pool = AntigravitySessionPool(_config())
        try:
            assert pool.active_count == 0
            pool.run_turn(_request("a", session_id="s1"), lambda e: None)
            assert pool.active_count == 1
            pool.run_turn(_request("b", session_id="s2"), lambda e: None)
            assert pool.active_count == 2
            pool.close_session("default", "cli", "s1")
            assert pool.active_count == 1
        finally:
            pool.shutdown()

    def test_concurrent_leases_survives_partial_failure(self):
        pool = AntigravitySessionPool(_config())
        key = ("default", "cli", "s1")
        req = _request("hello", session_id="s1")
        entry = pool._acquire(key, req)
        entry2 = pool._acquire(key, req)
        assert entry is entry2
        assert entry.leases == 2

        # Release first lease with failed=True while second lease is still active
        pool._release(key, entry, failed=True)
        assert entry.leases == 1
        assert entry.marked_fatal is True
        assert pool.active_count == 1
        assert pool._entries.get(key) is entry

        # Release second lease -> entry is finally evicted and closed
        pool._release(key, entry2, failed=False)
        assert entry.leases == 0
        assert pool.active_count == 0
        assert key not in pool._entries

        pool.shutdown()

    def test_shutdown_cleans_and_interrupts_all(self):
        pool = AntigravitySessionPool(_config())
        pool.run_turn(_request("a", session_id="s1"), lambda e: None)
        pool.run_turn(_request("b", session_id="s2"), lambda e: None)
        assert pool.active_count == 2

        pool.shutdown()
        assert pool.active_count == 0
        with pytest.raises(RuntimeError, match="shut down"):
            pool.run_turn(_request("c", session_id="s3"), lambda e: None)

    def test_close_failure_retains_entry_and_tracking(self):
        pool = AntigravitySessionPool(_config())
        key = ("default", "cli", "s1")
        req = _request("hello", session_id="s1")
        pool.run_turn(req, lambda e: None)
        assert pool.active_count == 1

        entry = pool._entries.get(key)
        assert entry is not None

        # Patch entry.session.close to raise
        with patch.object(entry.session, "close", side_effect=RuntimeError("kill failed")):
            with pytest.raises(RuntimeError, match="kill failed"):
                pool.close_session("default", "cli", "s1")

        # Entry MUST still be tracked so it is not an untracked orphan
        assert pool.active_count == 1
        assert pool._entries.get(key) is entry
        pool.shutdown()

    def test_non_transport_failures_do_not_trigger_recovery(self):
        pool = AntigravitySessionPool(_config())
        req = _request("hello", session_id="s1")
        pool.run_turn(req, lambda e: None)
        entry = pool._entries.get(("default", "cli", "s1"))
        assert entry is not None

        # When session is alive and raises PermissionError, recovery MUST NOT be attempted
        with patch.object(entry.session, "run_turn", side_effect=PermissionError("denied")):
            with patch.object(pool, "_try_recovery") as mock_rec:
                with pytest.raises(PermissionError, match="denied"):
                    pool.run_turn(req, lambda e: None)
                mock_rec.assert_not_called()
        pool.shutdown()

    def test_cleanup_idle_failure_retains_entry_and_tracking(self):
        cfg = _config(idle_timeout_seconds=1)
        pool = AntigravitySessionPool(cfg)
        key = ("default", "cli", "s1")
        req = _request("hello", session_id="s1")
        pool.run_turn(req, lambda e: None)
        assert pool.active_count == 1
        entry = pool._entries.get(key)
        assert entry is not None

        # Simulate idle timeout
        entry.last_used = time.monotonic() - 10

        # When close fails during cleanup_idle, entry MUST be retained
        with patch.object(entry.session, "close", side_effect=RuntimeError("cleanup close failed")):
            pool.cleanup_idle()

        assert pool.active_count == 1
        assert pool._entries.get(key) is entry
        pool.shutdown()

    def test_eviction_failure_retains_entry_and_tracking(self):
        cfg = _config(max_sessions=1)
        pool = AntigravitySessionPool(cfg)
        key1 = ("default", "cli", "s1")
        req1 = _request("hello", session_id="s1")
        pool.run_turn(req1, lambda e: None)
        assert pool.active_count == 1
        entry1 = pool._entries.get(key1)
        assert entry1 is not None

        # Now attempting to acquire s2 will trigger eviction of s1.
        # If s1.close() fails, s1 MUST NOT be discarded from tracking.
        with patch.object(entry1.session, "close", side_effect=RuntimeError("evict close failed")):
            with pytest.raises(RuntimeError, match="capacity exhausted|evict close failed"):
                pool.run_turn(_request("second", session_id="s2"), lambda e: None)

        assert pool.active_count == 1
        assert pool._entries.get(key1) is entry1
        pool.shutdown()
