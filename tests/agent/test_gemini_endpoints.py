from __future__ import annotations

import json
import traceback
from dataclasses import FrozenInstanceError

import pytest

from agent.gemini_endpoints import (
    GeminiEndpointConfigError,
    GeminiOAuthEndpoints,
    resolve_gemini_oauth_endpoints,
)


DEFAULTS = GeminiOAuthEndpoints(
    oauth_authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    oauth_token_url="https://oauth2.googleapis.com/token",
    oauth_userinfo_url="https://www.googleapis.com/oauth2/v1/userinfo",
    code_assist_base_url="https://cloudcode-pa.googleapis.com",
    custom_code_assist=False,
)


def _config(**overrides: object) -> dict[str, object]:
    return {"providers": {"google-gemini-cli": overrides}}


def test_official_defaults_are_frozen() -> None:
    endpoints = resolve_gemini_oauth_endpoints({})

    assert endpoints == DEFAULTS
    with pytest.raises(FrozenInstanceError):
        endpoints.oauth_token_url = "https://example.test/token"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("oauth_authorize_url", "https://auth.example.test/authorize"),
        ("oauth_token_url", "https://auth.example.test/token"),
        ("oauth_userinfo_url", "https://api.example.test/me"),
        ("code_assist_base_url", "https://code.example.test/api"),
    ],
)
def test_each_endpoint_can_be_configured_independently(
    field: str, value: str
) -> None:
    endpoints = resolve_gemini_oauth_endpoints(_config(**{field: value}))

    for endpoint_field in (
        "oauth_authorize_url",
        "oauth_token_url",
        "oauth_userinfo_url",
        "code_assist_base_url",
    ):
        expected = value if endpoint_field == field else getattr(DEFAULTS, endpoint_field)
        assert getattr(endpoints, endpoint_field) == expected
    assert endpoints.custom_code_assist is (field == "code_assist_base_url")


def test_trailing_slashes_are_removed_without_corrupting_root_urls() -> None:
    endpoints = resolve_gemini_oauth_endpoints(
        _config(
            oauth_authorize_url="https://auth.example.test///",
            oauth_token_url="https://token.example.test/",
            oauth_userinfo_url="https://userinfo.example.test/path///",
            code_assist_base_url="https://cloudcode-pa.googleapis.com/",
        )
    )

    assert endpoints.oauth_authorize_url == "https://auth.example.test"
    assert endpoints.oauth_token_url == "https://token.example.test"
    assert endpoints.oauth_userinfo_url == "https://userinfo.example.test/path"
    assert endpoints.code_assist_base_url == DEFAULTS.code_assist_base_url
    assert endpoints.custom_code_assist is False


@pytest.mark.parametrize("provider_config", [None, [], "invalid"])
def test_non_mapping_google_gemini_cli_config_uses_defaults(
    provider_config: object,
) -> None:
    config = {"providers": {"google-gemini-cli": provider_config}}

    assert resolve_gemini_oauth_endpoints(config) == DEFAULTS


@pytest.mark.parametrize("providers", [None, [], "invalid"])
def test_non_mapping_providers_block_uses_defaults(providers: object) -> None:
    assert resolve_gemini_oauth_endpoints({"providers": providers}) == DEFAULTS


def test_empty_endpoint_values_use_independent_defaults() -> None:
    endpoints = resolve_gemini_oauth_endpoints(
        _config(
            oauth_authorize_url="",
            oauth_token_url="",
            oauth_userinfo_url=None,
            code_assist_base_url="",
        )
    )

    assert endpoints == DEFAULTS


@pytest.mark.parametrize(
    ("field", "url"),
    [
        ("oauth_authorize_url", "http://example.test/authorize"),
        ("oauth_token_url", "ftp://example.test/token"),
        ("oauth_userinfo_url", "/oauth2/userinfo"),
        ("code_assist_base_url", "https:///api"),
        ("oauth_token_url", "https://user:password@example.test/token"),
        ("oauth_token_url", "https://example.test/token?client_secret=hunter2"),
        ("oauth_authorize_url", "https://example.test/auth#access-token"),
    ],
)
def test_invalid_endpoint_matrix_is_rejected(field: str, url: str) -> None:
    with pytest.raises(GeminiEndpointConfigError, match=field):
        resolve_gemini_oauth_endpoints(_config(**{field: url}))


@pytest.mark.parametrize(
    "url",
    [
        "https://example.test/token?",
        "https://example.test/token#",
    ],
)
def test_empty_query_or_fragment_delimiters_are_rejected(url: str) -> None:
    with pytest.raises(GeminiEndpointConfigError) as caught:
        resolve_gemini_oauth_endpoints(_config(oauth_token_url=url))

    assert url not in str(caught.value)


@pytest.mark.parametrize(
    "url",
    [
        " https://example.test/token",
        "https://example.test/token ",
        "ht\ntps://example.test/token",
        "https://exam\tple.test/token",
        "https://example.test/to\rken",
        "https://exam\x00ple.test/token",
        "https://example.test/to\x00ken",
    ],
    ids=[
        "leading-whitespace",
        "trailing-whitespace",
        "newline-in-scheme",
        "tab-in-host",
        "carriage-return-in-path",
        "nul-in-host",
        "nul-in-path",
    ],
)
def test_endpoint_rejects_raw_whitespace_and_control_characters(url: str) -> None:
    with pytest.raises(GeminiEndpointConfigError) as caught:
        resolve_gemini_oauth_endpoints(_config(oauth_token_url=url))

    message = str(caught.value)
    assert "oauth_token_url" in message
    assert url not in message


@pytest.mark.parametrize(
    "character",
    [
        *(chr(code) for code in range(0x20) if code not in {0, 9, 10, 13}),
        "\x7f",
        "\u00a0",
    ],
)
def test_endpoint_rejects_other_c0_del_and_unicode_whitespace(
    character: str,
) -> None:
    url = f"https://example.test/to{character}ken"

    with pytest.raises(GeminiEndpointConfigError) as caught:
        resolve_gemini_oauth_endpoints(_config(oauth_token_url=url))

    message = str(caught.value)
    assert "oauth_token_url" in message
    assert url not in message


@pytest.mark.parametrize(
    ("url", "normalized"),
    [
        ("http://localhost:8080/token/", "http://localhost:8080/token"),
        ("http://127.0.0.1/oauth/", "http://127.0.0.1/oauth"),
        ("http://[::1]:9000/token/", "http://[::1]:9000/token"),
    ],
)
def test_http_is_allowed_only_for_loopback_hosts(url: str, normalized: str) -> None:
    endpoints = resolve_gemini_oauth_endpoints(_config(oauth_token_url=url))

    assert endpoints.oauth_token_url == normalized


def test_errors_do_not_leak_credentials_or_query_values() -> None:
    secret_url = (
        "https://alice:correct-horse@example.test/token"
        "?client_secret=battery-staple"
    )

    with pytest.raises(GeminiEndpointConfigError) as caught:
        resolve_gemini_oauth_endpoints(_config(oauth_token_url=secret_url))

    message = str(caught.value)
    assert "oauth_token_url" in message
    for secret in (secret_url, "alice", "correct-horse", "battery-staple"):
        assert secret not in message


def test_malformed_url_cause_does_not_leak_sensitive_values() -> None:
    with pytest.raises(GeminiEndpointConfigError) as caught:
        resolve_gemini_oauth_endpoints(
            _config(oauth_token_url="https://example.test:super-secret/token")
        )

    rendered_error = "".join(traceback.format_exception(caught.value))
    assert "super-secret" not in rendered_error


def test_explicit_configs_are_resolved_without_shared_state() -> None:
    first = resolve_gemini_oauth_endpoints(
        _config(code_assist_base_url="https://first.example.test")
    )
    second = resolve_gemini_oauth_endpoints(
        _config(code_assist_base_url="https://second.example.test")
    )

    assert first.code_assist_base_url == "https://first.example.test"
    assert second.code_assist_base_url == "https://second.example.test"


def test_none_config_loads_each_active_profile(monkeypatch, tmp_path) -> None:
    first_home = tmp_path / "first"
    second_home = tmp_path / "second"
    first_home.mkdir()
    second_home.mkdir()
    (first_home / "config.yaml").write_text(
        json.dumps(_config(oauth_token_url="https://first.example.test/token")),
        encoding="utf-8",
    )
    (second_home / "config.yaml").write_text(
        json.dumps(_config(oauth_token_url="https://second.example.test/token")),
        encoding="utf-8",
    )

    monkeypatch.setenv("HERMES_HOME", str(first_home))
    first = resolve_gemini_oauth_endpoints()
    monkeypatch.setenv("HERMES_HOME", str(second_home))
    second = resolve_gemini_oauth_endpoints()

    assert first.oauth_token_url == "https://first.example.test/token"
    assert second.oauth_token_url == "https://second.example.test/token"


def test_context_local_home_overrides_resolve_independent_profiles(tmp_path) -> None:
    from hermes_constants import (
        reset_hermes_home_override,
        set_hermes_home_override,
    )

    first_home = tmp_path / "first-override"
    second_home = tmp_path / "second-override"
    first_home.mkdir()
    second_home.mkdir()
    (first_home / "config.yaml").write_text(
        json.dumps(_config(oauth_token_url="https://first.example.test/token")),
        encoding="utf-8",
    )
    (second_home / "config.yaml").write_text(
        json.dumps(_config(oauth_token_url="https://second.example.test/token")),
        encoding="utf-8",
    )

    first_token = set_hermes_home_override(first_home)
    try:
        first = resolve_gemini_oauth_endpoints()
    finally:
        reset_hermes_home_override(first_token)

    second_token = set_hermes_home_override(second_home)
    try:
        second = resolve_gemini_oauth_endpoints()
    finally:
        reset_hermes_home_override(second_token)

    assert first.oauth_token_url == "https://first.example.test/token"
    assert second.oauth_token_url == "https://second.example.test/token"


def test_public_exports_are_explicit() -> None:
    from agent import gemini_endpoints

    required_exports = {
        "GeminiEndpointConfigError",
        "GeminiOAuthEndpoints",
        "resolve_gemini_oauth_endpoints",
    }

    assert required_exports.issubset(gemini_endpoints.__all__)
