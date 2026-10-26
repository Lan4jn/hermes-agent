import json
from typing import Any
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from tools.hermes_message_tool import (
    _MAX_RESPONSE_BYTES,
    _normalize_target_url,
    check_requirements,
    send_hermes_message,
)


class _FakeResponse:
    def __init__(self, payload: Any, status: int = 200, raw_bytes: bytes | None = None):
        self._payload = payload
        self.status = status
        self._raw_bytes = raw_bytes

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size: int | None = None):
        if self._raw_bytes is not None:
            if size is not None:
                return self._raw_bytes[:size]
            return self._raw_bytes
        data = json.dumps(self._payload).encode("utf-8")
        if size is not None:
            return data[:size]
        return data


def _config_with_peer():
    return {
        "platforms": {
            "api_server": {
                "enabled": True,
                "extra": {
                    "message_api": {
                        "enabled": True,
                        "peers": [
                            {
                                "name": "130",
                                "url": "http://192.168.31.130:8642/message",
                            }
                        ],
                    }
                },
            }
        }
    }


def test_normalize_target_url():
    url, err = _normalize_target_url("http://192.168.1.100:8642")
    assert err is None
    assert url == "http://192.168.1.100:8642/message"

    url, err = _normalize_target_url("https://example.com/prefix/message")
    assert err is None
    assert url == "https://example.com/prefix/message"

    url, err = _normalize_target_url("http://example.com:8642/foo/?query=1#frag")
    assert err is None
    assert url == "http://example.com:8642/foo/message"

    url, err = _normalize_target_url("ftp://example.com")
    assert err is not None

    url, err = _normalize_target_url("")
    assert err is not None


def test_send_hermes_message_posts_to_configured_peer():
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeResponse({"reply": "received", "session_id": "s1"})

    with (
        patch("hermes_cli.config.load_config", return_value=_config_with_peer()),
        patch("tools.hermes_message_tool.urlopen", side_effect=fake_urlopen),
    ):
        raw = send_hermes_message(
            peer="130",
            message="hello",
            session_id="s1",
            sender_id="local",
            sender_display_name="Local Hermes",
        )

    result = json.loads(raw)
    assert result["success"] is True
    assert result["reply"] == "received"
    assert result["peer"] == "130"
    assert captured["url"] == "http://192.168.31.130:8642/message"
    assert captured["body"]["message"] == "hello"
    assert captured["body"]["session_id"] == "s1"
    assert captured["timeout"] == 180


def test_send_hermes_message_posts_to_base_url():
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["headers"] = dict(req.headers)
        return _FakeResponse({"reply": "ok", "session_id": "s2"})

    with patch("tools.hermes_message_tool.urlopen", side_effect=fake_urlopen):
        raw = send_hermes_message(
            base_url="http://10.0.0.5:9000",
            message="ping",
            command="uptime",
            api_key="secret-k",
            exec_token="tok-123",
        )

    result = json.loads(raw)
    assert result["success"] is True
    assert result["reply"] == "ok"
    assert captured["url"] == "http://10.0.0.5:9000/message"
    assert captured["body"]["message"] == "ping"
    assert captured["body"]["command"] == "uptime"
    assert captured["body"]["api_key"] == "secret-k"
    assert captured["body"]["exec_token"] == "tok-123"
    assert captured["headers"].get("X-hermes-api-key") == "secret-k"
    assert captured["headers"].get("X-hermes-exec-token") == "tok-123"


def test_send_hermes_message_rejects_unconfigured_peer():
    with patch("hermes_cli.config.load_config", return_value=_config_with_peer()):
        raw = send_hermes_message(peer="unknown", message="hello")

    result = json.loads(raw)
    assert result["success"] is False
    assert "not configured" in result["error"]


def test_send_hermes_message_rejects_both_peer_and_base_url():
    raw = send_hermes_message(peer="130", base_url="http://1.2.3.4:8642", message="hi")
    result = json.loads(raw)
    assert result["success"] is False
    assert "not both" in result["error"]


def test_send_hermes_message_rejects_neither_peer_nor_base_url():
    raw = send_hermes_message(message="hi")
    result = json.loads(raw)
    assert result["success"] is False
    assert "required" in result["error"]


def test_send_hermes_message_rejects_empty_payload():
    raw = send_hermes_message(base_url="http://1.2.3.4:8642")
    result = json.loads(raw)
    assert result["success"] is False
    assert "At least one of" in result["error"]


def test_send_hermes_message_handles_http_error():
    err_body = json.dumps({"error": "unauthorized", "code": 401}).encode("utf-8")
    fp = MagicMock()
    fp.read.return_value = err_body
    http_err = HTTPError("http://1.2.3.4:8642/message", 401, "Unauthorized", {}, fp)

    with patch("tools.hermes_message_tool.urlopen", side_effect=http_err):
        raw = send_hermes_message(base_url="http://1.2.3.4:8642", command="ls")

    result = json.loads(raw)
    assert result["success"] is False
    assert result["status"] == 401
    assert result["error"] == "unauthorized"


def test_send_hermes_message_handles_network_error():
    with patch("tools.hermes_message_tool.urlopen", side_effect=URLError("Connection refused")):
        raw = send_hermes_message(base_url="http://1.2.3.4:8642", message="ping")

    result = json.loads(raw)
    assert result["success"] is False
    assert "Connection refused" in result["error"]


def test_send_hermes_message_truncates_giant_response():
    giant_text = "x" * (_MAX_RESPONSE_BYTES + 500)
    fake_resp = _FakeResponse({}, raw_bytes=giant_text.encode("utf-8"))

    with patch("tools.hermes_message_tool.urlopen", return_value=fake_resp):
        raw = send_hermes_message(base_url="http://1.2.3.4:8642", message="ping")

    result = json.loads(raw)
    assert result["success"] is True
    assert result["_truncated"] is True
    assert "Response exceeded" in result["_truncated_note"]


def test_check_requirements():
    with patch("hermes_cli.config.load_config", return_value=_config_with_peer()):
        assert check_requirements() is True

    with patch("hermes_cli.config.load_config", return_value={}):
        assert check_requirements() is False
