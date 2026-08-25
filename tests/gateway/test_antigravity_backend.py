"""Tests for Antigravity backend routing in Messaging Gateway."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.backends.config import AntigravityConfig
from agent.backends.pool import AntigravitySessionPool
from agent.backends.router import BackendRouter
from gateway.interactive_backend import run_gateway_interactive_turn, validate_safe_media_path
from gateway.platforms.base import MessageEvent, Platform
from gateway.session import SessionSource, build_session_key
from gateway.slash_commands import GatewaySlashCommandsMixin
from hermes_state import SessionDB


@pytest.fixture
def fake_agy_config():
    fake_script = str(
        Path(__file__).resolve().parents[1] / "fixtures" / "fake_agy.py"
    )
    return AntigravityConfig(
        enabled=True,
        command=f"{sys.executable} {fake_script}",
        model="gemini-3.7-flash-high",
        effort="high",
        permission_mode="strict",
    )


@pytest.fixture
def session_db(tmp_path):
    db_path = tmp_path / "test_sessions.db"
    return SessionDB(db_path)


def test_validate_safe_media_path(tmp_path):
    safe_file = tmp_path / "photo.png"
    safe_file.write_text("dummy")

    assert validate_safe_media_path(str(safe_file)) == str(safe_file)
    assert validate_safe_media_path(str(tmp_path / "nonexistent.png")) is None

    sensitive_file = tmp_path / ".env"
    sensitive_file.write_text("SECRET=1")
    assert validate_safe_media_path(str(sensitive_file)) is None


def test_gateway_interactive_turn_routes_to_antigravity(tmp_path, fake_agy_config, session_db):
    pool = AntigravitySessionPool(fake_agy_config, cwd=str(tmp_path))
    router = BackendRouter(
        config={"agent_backends": {"default": "hermes", "antigravity": {"enabled": True}}},
        session_db=session_db,
        pool=pool,
    )

    session_db.create_session("gw-tg-1", source="telegram", model="test-model")

    runner = SimpleNamespace(
        config={"platforms": {"telegram": {"extra": {"agent_backend": "antigravity"}}}},
        _session_db=session_db,
        profile_name="default",
    )

    source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="123456",
        user_id="user-1",
    )

    ctx = SimpleNamespace(
        source=source,
        session_id="gw-tg-1",
        message="hello gateway",
    )

    stream_deltas = []
    mock_sc = SimpleNamespace(on_delta=lambda d: stream_deltas.append(d))

    with patch("agent.backends.router.AntigravitySessionPool", return_value=pool):
        result = run_gateway_interactive_turn(
            runner=runner,
            ctx=ctx,
            api_run_message="hello gateway",
            stream_consumer=mock_sc,
        )

    assert result is not None
    assert result["completed"] is True
    assert result["final_response"] == "reply:hello gateway"
    assert "".join(stream_deltas) == "reply:hello gateway"

    row = session_db.get_session("gw-tg-1")
    assert row["agent_backend"] == "antigravity"
    assert row["backend_conversation_id"] == "fake-conversation-1"

    pool.shutdown()


@pytest.mark.asyncio
async def test_gateway_slash_backend_command(tmp_path, session_db):
    class DummyGateway(GatewaySlashCommandsMixin):
        def __init__(self):
            self.config = {"agent_backends": {"default": "hermes"}}
            self._session_db = session_db
            self._config_path = None

    gw = DummyGateway()
    source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="12345",
        user_id="user-1",
    )
    session_key = build_session_key(source)
    session_db.create_session(session_key, source="telegram", model="test-model")

    event = MessageEvent(
        source=source,
        text="/backend",
        raw_message="/backend",
    )

    # 1. Bare /backend shows current
    reply = await gw._handle_backend_command(event)
    assert "hermes" in reply

    # 2. Switch to antigravity
    event.text = "/backend antigravity"
    event.raw_message = "/backend antigravity"
    reply = await gw._handle_backend_command(event)
    assert "Switched backend to antigravity" in reply

    row = session_db.get_session(session_key)
    assert row["agent_backend"] == "antigravity"

    # 3. Bare /backend now reflects session override
    event.text = "/backend"
    event.raw_message = "/backend"
    reply = await gw._handle_backend_command(event)
    assert "antigravity" in reply
    assert "session" in reply
