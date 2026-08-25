"""Tests for Antigravity backend routing in Hermes CLI."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.backends.base import BackendTurnRequest, BackendTurnResult
from agent.backends.config import AntigravityConfig
from agent.backends.pool import AntigravitySessionPool
from agent.backends.router import BackendRouter
from cli import HermesCLI
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


def test_backend_command_shows_status(tmp_path):
    cli = HermesCLI.__new__(HermesCLI)
    cli.config = {"agent_backends": {"default": "hermes"}}
    cli._session_backend_override = None
    cli._backend_router = None
    cli._session_db = None
    cli.session_id = "test-session-1"

    with patch("cli._cprint") as mock_cprint:
        cli.process_command("/backend")

    output = " ".join(call.args[0] for call in mock_cprint.call_args_list)
    assert "hermes" in output
    assert "global" in output or "built-in" in output


def test_backend_command_switches_session_backend(tmp_path, session_db):
    cli = HermesCLI.__new__(HermesCLI)
    cli.config = {"agent_backends": {"default": "hermes"}}
    cli._session_backend_override = None
    cli._backend_router = None
    cli._session_db = session_db
    cli.session_id = "test-session-1"
    session_db.create_session("test-session-1", source="cli", model="test-model")

    with patch("cli._cprint") as mock_cprint:
        cli.process_command("/backend antigravity")

    assert cli._session_backend_override == "antigravity"
    row = session_db.get_session("test-session-1")
    assert row["agent_backend"] == "antigravity"
    output = " ".join(call.args[0] for call in mock_cprint.call_args_list)
    assert "Switched backend to antigravity" in output

    with patch("cli._cprint") as mock_cprint:
        cli.process_command("/backend hermes")

    assert cli._session_backend_override == "hermes"
    row = session_db.get_session("test-session-1")
    assert row["agent_backend"] == "hermes"


def test_backend_command_rejects_invalid_backend():
    cli = HermesCLI.__new__(HermesCLI)
    cli.config = {}
    cli._session_backend_override = None
    cli._backend_router = None
    cli._session_db = None
    cli.session_id = "test-session-1"

    with patch("cli._cprint") as mock_cprint:
        cli.process_command("/backend invalid_name")

    output = " ".join(call.args[0] for call in mock_cprint.call_args_list)
    assert "Invalid backend" in output or "hermes" in output
    assert cli._session_backend_override is None


def test_cli_turn_routes_to_antigravity(tmp_path, fake_agy_config, session_db):
    pool = AntigravitySessionPool(fake_agy_config, cwd=str(tmp_path))
    router = BackendRouter(
        config={"agent_backends": {"default": "hermes", "antigravity": {"enabled": True}}},
        session_db=session_db,
        pool=pool,
    )

    cli = HermesCLI.__new__(HermesCLI)
    cli.config = {"agent_backends": {"default": "hermes"}}
    cli._backend_router = router
    cli._session_backend_override = "antigravity"
    cli._session_db = session_db
    cli.session_id = "test-session-cli-1"
    cli.profile_name = "default"
    cli.conversation_history = []
    cli.agent = MagicMock()
    session_db.create_session("test-session-cli-1", source="cli", model="test-model")

    streamed_deltas = []

    def mock_stream_callback(delta):
        streamed_deltas.append(delta)

    # Simulate turn execution in CLI
    selection = router.resolve(platform="cli", session_override="antigravity")
    assert selection.name == "antigravity"

    req = BackendTurnRequest(
        session_id=cli.session_id,
        profile=cli.profile_name,
        platform="cli",
        principal_id="local_user",
        text="hello",
        cwd=str(tmp_path),
    )

    result = router.run_turn(
        req,
        events=lambda ev: mock_stream_callback(ev.text) if ev.kind == "message_delta" and ev.text else None,
        session_override="antigravity",
    )

    assert result.status == "SUCCESS"
    assert result.response == "reply:hello"
    assert "".join(streamed_deltas) == "reply:hello"
    cli.agent.run_conversation.assert_not_called()

    # SessionDB recorded
    row = session_db.get_session("test-session-cli-1")
    assert row["agent_backend"] == "antigravity"
    assert row["backend_conversation_id"] == "fake-conversation-1"

    pool.shutdown()


def test_new_session_resets_backend_override(tmp_path, session_db):
    cli = HermesCLI.__new__(HermesCLI)
    cli.config = {"agent_backends": {"default": "hermes"}}
    cli._session_backend_override = "antigravity"
    cli._session_db = session_db
    cli.session_id = "old-session"
    cli.agent = None
    cli.conversation_history = []
    cli.profile_name = "default"
    cli._backend_router = MagicMock()

    cli.new_session(silent=True)

    assert cli._session_backend_override is None
    assert cli.session_id != "old-session"
    cli._backend_router.close_session.assert_called_once_with(
        profile="default", platform="cli", session_id="old-session"
    )
