"""Tests for API key gate on /message when Antigravity backend is active."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web

from gateway.platforms.api_server import APIServerAdapter


@pytest.mark.asyncio
async def test_message_api_rejects_unauthorized_when_antigravity_active():
    server = APIServerAdapter.__new__(APIServerAdapter)
    server._message_api_enabled = True
    server._message_api_keys = ["secret-key-123"]
    server._message_token_store = MagicMock()
    server._message_token_store.validate = AsyncMock(return_value=False)
    server._has_valid_bearer_auth = lambda req: False
    server._message_api_session_id_from_request = lambda body: "msg-sess-1"
    server.config = {
        "platforms": {"api_server": {"extra": {"agent_backend": "antigravity"}}}
    }

    # Unauthorized request (no bearer, no api_key)
    mock_request = MagicMock()
    mock_request.json = AsyncMock(return_value={"message": "hello", "sender_id": "peer-1"})
    mock_request.headers = {}

    response = await server._handle_message_api(mock_request)
    assert response.status == 401
    data = json.loads(response.body.decode("utf-8"))
    assert "Unauthorized" in data.get("error", "")


@pytest.mark.asyncio
async def test_message_api_allows_authorized_when_antigravity_active():
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
    server._run_agent = AsyncMock(return_value=({"final_response": "ok", "session_id": "msg-sess-1"}, {}))
    server.config = {
        "platforms": {"api_server": {"extra": {"agent_backend": "antigravity"}}}
    }

    mock_request = MagicMock()
    mock_request.json = AsyncMock(return_value={"message": "hello", "sender_id": "peer-1"})
    mock_request.headers = {"Authorization": "Bearer valid-token"}

    response = await server._handle_message_api(mock_request)
    assert response.status == 200
    data = json.loads(response.body.decode("utf-8"))
    assert data.get("reply") == "ok"
