"""Tests for message_keys.* JSON-RPC methods in tui_gateway."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

import tui_gateway.server as server
from gateway.platforms import message_api_keys


def _call(method: str, params: dict, rid: int = 1):
    return server.handle_request({
        "jsonrpc": "2.0",
        "id": rid,
        "method": method,
        "params": params,
    })


def test_message_keys_jsonrpc_lifecycle_and_validation(tmp_path, monkeypatch):
    h = tmp_path / ".hermes"
    h.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(h))

    # Initial policy
    resp = _call("message_keys.get_policy", {})
    assert "error" not in resp, resp
    assert resp["result"] == {"require_chat_key": False}

    # Initial list is empty
    resp = _call("message_keys.list", {})
    assert "error" not in resp, resp
    assert resp["result"] == {"items": []}

    # Validation: empty name
    resp = _call("message_keys.create", {"name": "   "})
    assert "error" in resp
    assert resp["error"]["code"] == 4001

    # Create key
    resp = _call("message_keys.create", {"name": "desktop-key"})
    assert "error" not in resp, resp
    res = resp["result"]
    assert res["name"] == "desktop-key"
    assert res["key"].startswith("hmmsg_")
    key_id = res["id"]
    plaintext_key = res["key"]

    # Key is valid
    assert message_api_keys.validate_key(plaintext_key) is True

    # List has metadata without plaintext key
    resp = _call("message_keys.list", {})
    assert "error" not in resp, resp
    items = resp["result"]["items"]
    assert len(items) == 1
    assert items[0]["id"] == key_id
    assert items[0]["name"] == "desktop-key"
    assert "key" not in items[0]

    # Toggle policy: invalid
    resp = _call("message_keys.set_policy", {"require_chat_key": "true"})
    assert "error" in resp
    assert resp["error"]["code"] == 4003

    # Toggle policy: valid
    resp = _call("message_keys.set_policy", {"require_chat_key": True})
    assert "error" not in resp, resp
    assert resp["result"] == {"require_chat_key": True}
    assert message_api_keys.get_policy()["require_chat_key"] is True

    # Revoke: missing id
    resp = _call("message_keys.revoke", {})
    assert "error" in resp
    assert resp["error"]["code"] == 4002

    # Revoke: success
    resp = _call("message_keys.revoke", {"id": key_id})
    assert "error" not in resp, resp
    assert resp["result"] == {"ok": True, "removed": True}

    # Validate revoked key
    assert message_api_keys.validate_key(plaintext_key) is False

    # List is empty again
    resp = _call("message_keys.list", {})
    assert resp["result"] == {"items": []}


def test_message_keys_jsonrpc_profile_isolation(tmp_path, monkeypatch):
    a = tmp_path / "profiles" / "alpha"
    b = tmp_path / "profiles" / "beta"
    a.mkdir(parents=True)
    b.mkdir(parents=True)

    monkeypatch.setattr(server, "_profile_home", lambda name: str(a) if name == "alpha" else str(b) if name == "beta" else None)

    # Create in alpha
    resp_a = _call("message_keys.create", {"name": "alpha-key", "profile": "alpha"})
    assert "error" not in resp_a, resp_a
    id_a = resp_a["result"]["id"]

    # Create in beta
    resp_b = _call("message_keys.create", {"name": "beta-key", "profile": "beta"})
    assert "error" not in resp_b, resp_b
    id_b = resp_b["result"]["id"]

    # List alpha
    list_a = _call("message_keys.list", {"profile": "alpha"})["result"]["items"]
    # List beta
    list_b = _call("message_keys.list", {"profile": "beta"})["result"]["items"]

    assert len(list_a) == 1 and list_a[0]["id"] == id_a
    assert len(list_b) == 1 and list_b[0]["id"] == id_b
    assert id_a != id_b
