"""Tests for message keys dashboard management endpoints."""

from pathlib import Path
import pytest
from starlette.testclient import TestClient

from hermes_cli.web_server import app, _SESSION_HEADER_NAME, _SESSION_TOKEN
from gateway.platforms import message_api_keys


@pytest.fixture
def auth_client(_isolate_hermes_home):
    client = TestClient(app)
    client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN
    return client


@pytest.fixture
def unauth_client(_isolate_hermes_home):
    return TestClient(app)


def test_message_keys_endpoints_require_auth(unauth_client):
    assert unauth_client.get("/api/message/keys").status_code == 401
    assert unauth_client.post("/api/message/keys", json={"name": "router"}).status_code == 401
    assert unauth_client.delete("/api/message/keys/some-id").status_code == 401
    assert unauth_client.get("/api/message/keys/policy").status_code == 401
    assert unauth_client.put("/api/message/keys/policy", json={"require_chat_key": True}).status_code == 401


def test_message_keys_lifecycle_and_one_time_plaintext(auth_client, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    # Initial policy is false
    pol_resp = auth_client.get("/api/message/keys/policy")
    assert pol_resp.status_code == 200
    assert pol_resp.headers.get("cache-control") == "no-store"
    assert pol_resp.json() == {"require_chat_key": False}

    # Initial list is empty
    list_resp = auth_client.get("/api/message/keys")
    assert list_resp.status_code == 200
    assert list_resp.headers.get("cache-control") == "no-store"
    assert list_resp.json() == []

    # Create a key
    create_resp = auth_client.post("/api/message/keys", json={"name": "router-1"})
    assert create_resp.status_code == 200
    assert create_resp.headers.get("cache-control") == "no-store"
    created = create_resp.json()
    assert created["name"] == "router-1"
    assert created["key"].startswith("hmmsg_")
    key_id = created["id"]
    plaintext_key = created["key"]

    # Key is valid
    assert message_api_keys.validate_key(plaintext_key) is True

    # List contains key metadata but NOT the plaintext key
    list_after = auth_client.get("/api/message/keys").json()
    assert len(list_after) == 1
    assert list_after[0]["id"] == key_id
    assert list_after[0]["name"] == "router-1"
    assert "key" not in list_after[0]

    # Toggle policy to True
    put_pol = auth_client.put("/api/message/keys/policy", json={"require_chat_key": True})
    assert put_pol.status_code == 200
    assert put_pol.headers.get("cache-control") == "no-store"
    assert put_pol.json() == {"require_chat_key": True}
    assert message_api_keys.get_policy()["require_chat_key"] is True

    # Invalid policy input
    assert auth_client.put("/api/message/keys/policy", json={"require_chat_key": "not-bool"}).status_code == 400
    assert auth_client.put("/api/message/keys/policy", json={}).status_code == 400

    # Revoke key
    del_resp = auth_client.delete(f"/api/message/keys/{key_id}")
    assert del_resp.status_code == 200
    assert del_resp.headers.get("cache-control") == "no-store"
    assert del_resp.json().get("ok") is True

    # After revocation, key is no longer valid
    assert message_api_keys.validate_key(plaintext_key) is False
    assert auth_client.get("/api/message/keys").json() == []

    # Toggle policy back to False
    put_pol_back = auth_client.put("/api/message/keys/policy", json={"require_chat_key": False})
    assert put_pol_back.status_code == 200
    assert put_pol_back.json() == {"require_chat_key": False}
    assert message_api_keys.get_policy()["require_chat_key"] is False


def test_message_keys_profile_isolation(auth_client, tmp_path, monkeypatch):
    a = tmp_path / "default"
    b = tmp_path / "other"
    a.mkdir()
    b.mkdir()

    monkeypatch.setenv("HERMES_HOME", str(a))
    monkeypatch.setattr("hermes_cli.profiles.get_profile_dir", lambda p: a if p in (None, "default") else b)
    monkeypatch.setattr("hermes_cli.profiles.profile_exists", lambda p: p in ("default", "other"))

    # Non-existent profile fails closed with 404
    assert auth_client.get("/api/message/keys?profile=ghost").status_code == 404

    # Create key in default profile
    resp_a = auth_client.post("/api/message/keys", json={"name": "node-key"})
    assert resp_a.status_code == 200
    key_a = resp_a.json()["id"]

    # Create key in other profile
    resp_b = auth_client.post("/api/message/keys?profile=other", json={"name": "node-key"})
    assert resp_b.status_code == 200
    key_b = resp_b.json()["id"]

    # Verify lists are isolated
    list_a = auth_client.get("/api/message/keys").json()
    list_b = auth_client.get("/api/message/keys?profile=other").json()

    assert len(list_a) == 1 and list_a[0]["id"] == key_a
    assert len(list_b) == 1 and list_b[0]["id"] == key_b
    assert key_a != key_b
