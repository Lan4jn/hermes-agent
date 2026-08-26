"""Tests for API key gate and real Antigravity execution on /message."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web

from agent.backends.config import AntigravityConfig
from agent.backends.pool import AntigravitySessionPool
from agent.backends.router import BackendRouter
from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter
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


@pytest.mark.asyncio
async def test_message_api_rejects_unauthorized_when_antigravity_active():
    """Unauthenticated requests on /message return 401 without spawning agy."""
    server = APIServerAdapter.__new__(APIServerAdapter)
    server._message_api_enabled = True
    server._message_api_keys = ["secret-key-123"]
    server._message_token_store = MagicMock()
    server._message_token_store.validate = AsyncMock(return_value=False)
    server._has_valid_bearer_auth = lambda req: False
    server._message_api_session_id_from_request = lambda body: "msg-sess-1"
    server.config = PlatformConfig(extra={"agent_backend": "antigravity"})

    # Unauthorized request (no bearer, no api_key)
    mock_request = MagicMock()
    mock_request.json = AsyncMock(return_value={"message": "hello", "sender_id": "peer-1"})
    mock_request.headers = {}

    response = await server._handle_message_api(mock_request)
    assert response.status == 401
    data = json.loads(response.body.decode("utf-8"))
    assert "Unauthorized" in data.get("error", "")


@pytest.mark.asyncio
async def test_message_api_dispatches_to_antigravity_when_authorized(tmp_path, fake_agy_config):
    """Authorized request on /message executes turn via Antigravity backend."""
    db_path = tmp_path / "api_sessions.db"
    session_db = SessionDB(db_path)
    session_db.create_session("msg-sess-1", source="api_server", model="test-model")
    pool = AntigravitySessionPool(fake_agy_config, cwd=str(tmp_path))
    router = BackendRouter(
        config={"platforms": {"api_server": {"extra": {"agent_backend": "antigravity"}}}},
        session_db=session_db,
        pool=pool,
    )

    server = APIServerAdapter.__new__(APIServerAdapter)
    server._message_api_enabled = True
    server._message_api_keys = ["secret-key-123"]
    server._message_token_store = MagicMock()
    server._message_token_store.validate = AsyncMock(return_value=False)
    server._has_valid_bearer_auth = lambda req: True
    server._message_api_session_id_from_request = lambda body: "msg-sess-1"
    server._message_api_session_key = lambda s: f"api_server:{s}"
    server._message_api_user_marker = lambda u: u
    server._message_api_shared_memory_notes_enabled = False
    server._session_db = session_db
    server._backend_router = router
    server.config = PlatformConfig(extra={"agent_backend": "antigravity"})

    mock_request = MagicMock()
    mock_request.json = AsyncMock(return_value={"message": "hello api server", "sender_id": "peer-1"})
    mock_request.headers = {"Authorization": "Bearer valid-token"}

    response = await server._handle_message_api(mock_request)
    assert response.status == 200
    data = json.loads(response.body.decode("utf-8"))
    assert data.get("reply") == "reply:hello api server"
    assert data.get("session_id") == "msg-sess-1"

    row = session_db.get_session("msg-sess-1")
    assert row["agent_backend"] == "antigravity"

    pool.shutdown()


@pytest.mark.asyncio
async def test_message_api_multi_profile_routers_are_isolated(tmp_path, fake_agy_config):
    """Different profile requests on /message use isolated BackendRouter instances."""
    db_path = tmp_path / "api_sessions.db"
    session_db = SessionDB(db_path)

    server = APIServerAdapter.__new__(APIServerAdapter)
    server._message_api_enabled = True
    server._message_api_keys = ["secret-key-123"]
    server._message_token_store = MagicMock()
    server._message_token_store.validate = AsyncMock(return_value=False)
    server._has_valid_bearer_auth = lambda req: True
    server._message_api_session_id_from_request = lambda body: body.get("session_id", "msg-sess-1")
    server._message_api_session_key = lambda sid: f"msg:{sid}"
    server._message_api_user_marker = lambda uid: f"user:{uid}"
    server._session_db = session_db
    server._raw_config = {
        "agent_backends": {
            "antigravity": {
                "command": fake_agy_config.command,
                "model": fake_agy_config.model,
            }
        },
        "platforms": {"api_server": {"extra": {"agent_backend": "antigravity"}}},
    }
    server._backend_routers = {}

    # Turn 1 with profile 'work'
    server.profile_name = "work"
    mock_request1 = MagicMock()
    mock_request1.json = AsyncMock(return_value={"message": "turn work", "sender_id": "p1", "session_id": "sess-work"})
    mock_request1.headers = {"Authorization": "Bearer secret-key-123"}
    res1 = await server._handle_message_api(mock_request1)
    assert res1.status == 200

    # Turn 2 with profile 'personal'
    server.profile_name = "personal"
    mock_request2 = MagicMock()
    mock_request2.json = AsyncMock(return_value={"message": "turn personal", "sender_id": "p2", "session_id": "sess-personal"})
    mock_request2.headers = {"Authorization": "Bearer secret-key-123"}
    res2 = await server._handle_message_api(mock_request2)
    assert res2.status == 200

    assert "work" in server._backend_routers
    assert "personal" in server._backend_routers
    assert server._backend_routers["work"] is not server._backend_routers["personal"]

    for r in server._backend_routers.values():
        r.shutdown()
