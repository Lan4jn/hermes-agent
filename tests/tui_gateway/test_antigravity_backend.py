"""Tests for Antigravity backend routing in TUI gateway with real types."""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.backends.base import BackendTurnRequest
from agent.backends.config import AntigravityConfig
from agent.backends.pool import AntigravitySessionPool
from agent.backends.router import BackendRouter
from hermes_state import SessionDB
from run_agent import AIAgent
from tui_gateway.interactive_backend import get_tui_backend_router, run_interactive_backend_turn


@pytest.fixture
def fake_agy_config():
    fake_script = str(
        Path(__file__).resolve().parents[1] / "fixtures" / "fake_agy.py"
    )
    return AntigravityConfig(
        enabled=True,
        command=f'"{sys.executable}" "{fake_script}"',
        model="gemini-3.7-flash-high",
        effort="high",
        permission_mode="strict",
    )


@pytest.fixture
def session_db(tmp_path):
    db_path = tmp_path / "test_sessions.db"
    return SessionDB(db_path)


def test_tui_interactive_backend_returns_none_for_hermes():
    # Use real AIAgent without synthetic user_config attribute
    real_agent = AIAgent(
        model="gemini-2.5-flash",
        api_key="fake-key",
        base_url="http://localhost:8000/v1",
        quiet_mode=True,
        skip_context_files=True,
        skip_memory=True,
    )
    session = {
        "agent": real_agent,
        "platform": "tui",
        "agent_backend_override": "hermes",
    }
    result = run_interactive_backend_turn(
        session=session,
        sid="ui-sid-1",
        run_message="hello",
        stream_cb=lambda s: None,
        emit_fn=lambda t, s, p: None,
        history=[],
    )
    assert result is None


def test_tui_interactive_backend_routes_to_antigravity(tmp_path, fake_agy_config, session_db):
    pool = AntigravitySessionPool(fake_agy_config, cwd=str(tmp_path))
    router = BackendRouter(
        config={"agent_backends": {"default": "hermes", "antigravity": {"enabled": True}}},
        session_db=session_db,
        pool=pool,
    )

    # Real AIAgent instance
    real_agent = AIAgent(
        model="gemini-2.5-flash",
        api_key="fake-key",
        base_url="http://localhost:8000/v1",
        quiet_mode=True,
        skip_context_files=True,
        skip_memory=True,
    )
    real_agent._session_db = session_db

    session_db.create_session("gw-session-1", source="tui", model="test-model")

    session = {
        "agent": real_agent,
        "session_key": "gw-session-1",
        "platform": "tui",
        "agent_backend_override": "antigravity",
        "profile": "default",
        "history_lock": threading.Lock(),
        "_backend_router": router,
    }

    emitted_events = []
    streamed_text = []

    def mock_stream(delta):
        streamed_text.append(delta)

    def mock_emit(event_type, sid, payload):
        emitted_events.append((event_type, sid, payload))

    result = run_interactive_backend_turn(
        session=session,
        sid="ui-sid-1",
        run_message="hello from tui",
        stream_cb=mock_stream,
        emit_fn=mock_emit,
        history=[],
        user_text="hello from tui",
    )

    assert result is not None
    assert result["completed"] is True
    assert result["final_response"] == "reply:hello from tui"
    assert "".join(streamed_text) == "reply:hello from tui"
    assert len(result["messages"]) == 2

    # Verify session db
    row = session_db.get_session("gw-session-1")
    assert row["agent_backend"] == "antigravity"
    assert row["backend_conversation_id"] == "fake-conversation-1"

    pool.shutdown()


def test_tui_interactive_backend_interrupt(tmp_path, fake_agy_config, session_db):
    from tui_gateway.interactive_backend import interrupt_tui_interactive_backend_turn

    pool = AntigravitySessionPool(fake_agy_config, cwd=str(tmp_path))
    router = BackendRouter(
        config={"agent_backends": {"antigravity": {"enabled": True}}},
        session_db=session_db,
        pool=pool,
    )
    session_db.create_session("gw-session-intr", source="tui", model="test-model")

    session = {
        "session_id": "gw-session-intr",
        "platform": "tui",
        "agent_backend_override": "antigravity",
        "profile": "default",
        "history_lock": threading.Lock(),
        "_backend_router": router,
    }

    # Start a turn in background thread
    def _run_slow():
        try:
            run_interactive_backend_turn(
                session=session,
                sid="ui-sid-intr",
                run_message="TIMEOUT",
                stream_cb=lambda s: None,
                emit_fn=lambda t, s, p: None,
                history=[],
            )
        except Exception:
            pass

    t = threading.Thread(target=_run_slow, daemon=True)
    t.start()
    import time
    time.sleep(0.5)

    # Interrupt
    ok = interrupt_tui_interactive_backend_turn(session, "ui-sid-intr")
    assert ok is True
    t.join(timeout=2.0)
    pool.shutdown()
