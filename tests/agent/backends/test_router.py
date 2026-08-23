from dataclasses import FrozenInstanceError, fields

import pytest

from agent.backends import (
    BackendEvent,
    BackendTurnRequest,
    BackendTurnResult,
    HermesBackend,
    parse_antigravity_config,
    resolve_backend,
)
from hermes_cli.config import load_config
from hermes_cli.config_defaults import DEFAULT_CONFIG


def test_backend_resolution_order():
    cfg = {
        "agent_backends": {"default": "antigravity"},
        "platforms": {"telegram": {"extra": {"agent_backend": "hermes"}}},
    }

    session = resolve_backend(
        cfg, platform="telegram", session_override="antigravity"
    )
    platform = resolve_backend(cfg, platform="telegram")
    global_default = resolve_backend(cfg, platform="qqbot")
    built_in = resolve_backend({}, platform="cli")

    assert (session.name, session.source) == ("antigravity", "session")
    assert (platform.name, platform.source) == ("hermes", "platform")
    assert (global_default.name, global_default.source) == (
        "antigravity",
        "global",
    )
    assert (built_in.name, built_in.source) == ("hermes", "built-in")


@pytest.mark.parametrize("value", ["", "native", "ANTIGRAVITY", 7, None])
def test_backend_resolution_rejects_invalid_values(value):
    with pytest.raises(ValueError, match=r"hermes.*antigravity.*agent_backend"):
        resolve_backend({"agent_backends": {"default": value}}, platform="cli")


def test_default_config_selects_hermes():
    assert DEFAULT_CONFIG["agent_backends"]["default"] == "hermes"
    assert resolve_backend(DEFAULT_CONFIG, platform="cli").name == "hermes"


@pytest.mark.parametrize("permission_mode", ["strict", "sandbox", "trusted"])
def test_antigravity_permission_modes(permission_mode):
    parsed = parse_antigravity_config(
        {"agent_backends": {"antigravity": {"permission_mode": permission_mode}}}
    )

    assert parsed.permission_mode == permission_mode


@pytest.mark.parametrize("permission_mode", ["", "unrestricted", "TRUSTED", None])
def test_antigravity_rejects_invalid_permission_mode(permission_mode):
    with pytest.raises(
        ValueError, match=r"permission_mode.*strict.*sandbox.*trusted"
    ):
        parse_antigravity_config(
            {
                "agent_backends": {
                    "antigravity": {"permission_mode": permission_mode}
                }
            }
        )


@pytest.mark.parametrize(
    "proxy_url",
    [
        "ftp://proxy.example:21",
        "http:///missing-host",
        "http://user:password@proxy.example:8080",
        "http://proxy.example:8080?token=secret",
        "http://proxy.example:8080#fragment",
        "http://proxy.example?",
        "http://proxy.example#",
        "http://proxy.example:bad",
        "http://proxy.example:99999",
        "http://proxy host.example:8080",
        "http://proxy.example\\path",
        "http://proxy.example:8080\nheader: injected",
        "http://proxy.example:\x80",
        "http://proxy\u2003.example:8080",
        "http://[malformed:8080",
        " http://proxy.example:8080",
        "http://proxy.example:8080 ",
    ],
)
def test_antigravity_rejects_unsafe_proxy_urls(proxy_url):
    with pytest.raises(ValueError, match="proxy_url"):
        parse_antigravity_config(
            {"agent_backends": {"antigravity": {"proxy_url": proxy_url}}}
        )


def test_antigravity_rejects_overlong_proxy_url():
    proxy_url = "https://proxy.example/" + "a" * 4096

    with pytest.raises(ValueError, match="proxy_url.*too long"):
        parse_antigravity_config(
            {"agent_backends": {"antigravity": {"proxy_url": proxy_url}}}
        )


def test_antigravity_accepts_proxy_url_at_length_limit():
    prefix = "https://proxy.example/"
    proxy_url = prefix + "a" * (4096 - len(prefix))

    parsed = parse_antigravity_config(
        {"agent_backends": {"antigravity": {"proxy_url": proxy_url}}}
    )

    assert parsed.proxy_url == proxy_url


@pytest.mark.parametrize(
    "proxy_url", ["http://proxy.example:8080", "https://proxy.example"]
)
def test_antigravity_accepts_http_proxy_with_host(proxy_url):
    parsed = parse_antigravity_config(
        {"agent_backends": {"antigravity": {"proxy_url": proxy_url}}}
    )

    assert parsed.proxy_url == proxy_url
    assert parsed.proxy_display == proxy_url


def test_proxy_display_omits_path_that_may_contain_credentials():
    parsed = parse_antigravity_config(
        {
            "agent_backends": {
                "antigravity": {
                    "proxy_url": "https://proxy.example:8443/tenant-secret"
                }
            }
        }
    )

    assert parsed.proxy_url == "https://proxy.example:8443/tenant-secret"
    assert parsed.proxy_display == "https://proxy.example:8443"


def test_proxy_env_secret_is_rejected_without_log_or_error_leak(
    tmp_path, monkeypatch, caplog
):
    secret_marker = "ANTIGRAVITY_PROXY_SECRET_7f31"
    proxy_url = f"https://proxy-user:{secret_marker}@proxy.internal.example:8443"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "agent_backends:\n"
        "  antigravity:\n"
        "    proxy_url: ${ANTIGRAVITY_PROXY_URL}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIGRAVITY_PROXY_URL", proxy_url)

    loaded = load_config()
    with pytest.raises(ValueError) as exc_info:
        parse_antigravity_config(loaded)

    assert loaded["agent_backends"]["antigravity"]["proxy_url"] == proxy_url
    assert "${ANTIGRAVITY_PROXY_URL}" in config_path.read_text(encoding="utf-8")
    assert secret_marker not in str(exc_info.value)
    assert secret_marker not in caplog.text


def test_backend_contracts_are_immutable_and_contain_only_transport_facts():
    request = BackendTurnRequest(
        session_id="session-1",
        profile="work",
        platform="telegram",
        principal_id="user-7",
        text="hello",
        cwd="/workspace",
        media_paths=("/tmp/image.png",),
        trusted=True,
    )
    result = BackendTurnResult(
        response="hi",
        conversation_id="conversation-2",
        usage={"input_tokens": 3, "output_tokens": 1},
        status="SUCCESS",
    )

    assert {field.name for field in fields(request)} == {
        "session_id",
        "profile",
        "platform",
        "principal_id",
        "text",
        "cwd",
        "media_paths",
        "trusted",
    }
    assert {field.name for field in fields(result)} == {
        "response",
        "conversation_id",
        "usage",
        "status",
    }
    assert {field.name for field in fields(BackendEvent)} == {
        "kind",
        "text",
        "tool_name",
        "status",
    }
    assert [BackendEvent(kind=kind).kind for kind in ("message_delta", "tool", "status")] == [
        "message_delta",
        "tool",
        "status",
    ]
    with pytest.raises(ValueError, match="event kind"):
        BackendEvent(kind="render_spinner")
    with pytest.raises(FrozenInstanceError):
        request.text = "changed"


def test_hermes_backend_calls_injected_native_turn_once():
    calls = []
    expected = BackendTurnResult(
        response="native response",
        conversation_id="session-1",
        usage={},
        status="SUCCESS",
    )

    def native_turn(request, events):
        calls.append((request, events))
        return expected

    request = BackendTurnRequest(
        session_id="session-1",
        profile="default",
        platform="cli",
        principal_id="local",
        text="hello",
        cwd=None,
    )
    events = lambda event: None

    result = HermesBackend(native_turn).run_turn(request, events)

    assert result is expected
    assert calls == [(request, events)]
