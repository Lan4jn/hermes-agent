"""Tests for Antigravity backend routing in Messaging Gateway with real runtime types."""

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
from gateway.config import GatewayConfig
from gateway.interactive_backend import get_gateway_backend_router, run_gateway_interactive_turn
from gateway.platforms.base import MessageEvent, Platform, validate_media_delivery_path
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
        command=f'"{sys.executable}" "{fake_script}"',
        model="gemini-3.7-flash-high",
        effort="high",
        permission_mode="strict",
    )


@pytest.fixture
def session_db(tmp_path):
    db_path = tmp_path / "test_sessions.db"
    return SessionDB(db_path)


def test_validate_media_delivery_path_security(tmp_path, monkeypatch):
    """Hermes canonical media delivery validator protects sensitive system files."""
    import gateway.platforms.base as base

    hermes_home = tmp_path / "hermes_home"
    hermes_home.mkdir()
    monkeypatch.setattr(base, "_HERMES_HOME", hermes_home)
    monkeypatch.setattr(base, "_HERMES_ROOT", hermes_home)

    # Allowed: normal staging media in tmp or workspace
    safe_media = tmp_path / "photo.jpg"
    safe_media.write_text("fake image content")
    assert validate_media_delivery_path(str(safe_media)) == str(safe_media.resolve())

    # Denied: Hermes home secrets and credentials (.env, google_token.json, etc.)
    env_file = hermes_home / ".env"
    env_file.write_text("SECRET=1")
    assert validate_media_delivery_path(str(env_file)) is None

    token_file = hermes_home / "google_token.json"
    token_file.write_text("token")
    assert validate_media_delivery_path(str(token_file)) is None


def test_gateway_multiturn_reuses_pool_and_process(tmp_path, fake_agy_config, session_db):
    """GatewayRunner persists BackendRouter and reuses agy process across multiple turns."""
    pool = AntigravitySessionPool(fake_agy_config, cwd=str(tmp_path))
    session_db.create_session("gw-tg-1", source="telegram", model="test-model")

    # Real GatewayConfig instance (dataclass, not dict)
    runner = SimpleNamespace(
        config=GatewayConfig(),
        raw_config={"platforms": {"telegram": {"extra": {"agent_backend": "antigravity"}}}},
        _session_db=session_db,
        profile_name="default",
        _backend_router=BackendRouter(
            config={"platforms": {"telegram": {"extra": {"agent_backend": "antigravity"}}}},
            session_db=session_db,
            pool=pool,
        ),
    )

    source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="123456",
        user_id="user-1",
    )

    ctx = SimpleNamespace(
        source=source,
        session_id="gw-tg-1",
        message="first turn",
    )

    # Turn 1
    res1 = run_gateway_interactive_turn(
        runner=runner,
        ctx=ctx,
        api_run_message="first turn",
    )
    assert res1 is not None
    assert res1["completed"] is True
    assert res1["final_response"] == "reply:first turn"

    pid1 = pool.session_pid("default", "telegram", "gw-tg-1")
    assert pid1 is not None

    # Turn 2 on same session
    ctx.message = "second turn"
    res2 = run_gateway_interactive_turn(
        runner=runner,
        ctx=ctx,
        api_run_message="second turn",
    )
    assert res2 is not None
    assert res2["completed"] is True
    assert res2["final_response"] == "reply:second turn"

    pid2 = pool.session_pid("default", "telegram", "gw-tg-1")
    assert pid1 == pid2  # Long-lived process was preserved across turns!

    pool.shutdown()


@pytest.mark.asyncio
async def test_gateway_slash_backend_command_dispatch(tmp_path, session_db):
    """Gateway slash handler /backend queries and updates SessionDB override."""
    class DummyGateway(GatewaySlashCommandsMixin):
        def __init__(self):
            self.config = GatewayConfig()
            self.raw_config = {"agent_backends": {"default": "hermes"}}
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

    # 1. Query current backend
    reply = await gw._handle_backend_command(event)
    assert "hermes" in reply

    # 2. Switch to antigravity
    event.text = "/backend antigravity"
    event.raw_message = "/backend antigravity"
    reply = await gw._handle_backend_command(event)
    assert "Switched backend to antigravity" in reply

    row = session_db.get_session(session_key)
    assert row["agent_backend"] == "antigravity"

    # 3. Query reflects session override
    event.text = "/backend"
    event.raw_message = "/backend"
    reply = await gw._handle_backend_command(event)
    assert "antigravity" in reply
    assert "session" in reply


def test_gateway_interactive_turn_interrupt(tmp_path, fake_agy_config, session_db):
    import threading
    import time
    from gateway.interactive_backend import interrupt_gateway_turn

    pool = AntigravitySessionPool(fake_agy_config, cwd=str(tmp_path))
    session_db.create_session("gw-intr-1", source="telegram", model="test-model")

    runner = SimpleNamespace(
        config=GatewayConfig(),
        raw_config={"platforms": {"telegram": {"extra": {"agent_backend": "antigravity"}}}},
        _session_db=session_db,
        profile_name="default",
        _backend_router=BackendRouter(
            config={"platforms": {"telegram": {"extra": {"agent_backend": "antigravity"}}}},
            session_db=session_db,
            pool=pool,
        ),
    )

    ctx = SimpleNamespace(
        source=SessionSource(platform=Platform.TELEGRAM, chat_id="123", user_id="u1"),
        session_id="gw-intr-1",
        message="TIMEOUT",
    )

    def _run_slow():
        try:
            run_gateway_interactive_turn(runner=runner, ctx=ctx, api_run_message="TIMEOUT")
        except Exception:
            pass

    t = threading.Thread(target=_run_slow, daemon=True)
    t.start()
    time.sleep(0.5)

    ok = interrupt_gateway_turn(runner, session_id="gw-intr-1", platform="telegram", profile="default")
    assert ok is True
    t.join(timeout=2.0)
    pool.shutdown()
