"""Resolve configurable Gemini CLI OAuth and Code Assist endpoints."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

__all__ = [
    "GeminiEndpointConfigError",
    "GeminiOAuthEndpoints",
    "resolve_gemini_oauth_endpoints",
]


_DEFAULT_ENDPOINTS = {
    "oauth_authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
    "oauth_token_url": "https://oauth2.googleapis.com/token",
    "oauth_userinfo_url": "https://www.googleapis.com/oauth2/v1/userinfo",
    "code_assist_base_url": "https://cloudcode-pa.googleapis.com",
}
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class GeminiEndpointConfigError(ValueError):
    """Raised when a configured Gemini endpoint is unsafe or malformed."""


@dataclass(frozen=True)
class GeminiOAuthEndpoints:
    oauth_authorize_url: str
    oauth_token_url: str
    oauth_userinfo_url: str
    code_assist_base_url: str
    custom_code_assist: bool


def _normalize_endpoint(field: str, value: object, default: str) -> tuple[str, bool]:
    if value is None or value == "":
        return default, False
    if not isinstance(value, str):
        raise GeminiEndpointConfigError(f"{field}: must be a URL string")
    if value != value.strip():
        raise GeminiEndpointConfigError(
            f"{field}: surrounding whitespace is not allowed"
        )
    if any(ord(char) < 0x20 or ord(char) == 0x7F or char.isspace() for char in value):
        raise GeminiEndpointConfigError(
            f"{field}: whitespace and control characters are not allowed"
        )

    candidate = value
    if "?" in candidate:
        raise GeminiEndpointConfigError(f"{field}: query strings are not allowed")
    if "#" in candidate:
        raise GeminiEndpointConfigError(f"{field}: fragments are not allowed")

    try:
        parsed = urlsplit(candidate)
        hostname = parsed.hostname
        parsed.port  # Validate malformed and out-of-range ports.
    except ValueError:
        raise GeminiEndpointConfigError(f"{field}: malformed URL") from None

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise GeminiEndpointConfigError(f"{field}: scheme must be https")
    if not hostname:
        raise GeminiEndpointConfigError(f"{field}: URL must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise GeminiEndpointConfigError(f"{field}: credentials are not allowed")
    if parsed.query:
        raise GeminiEndpointConfigError(f"{field}: query strings are not allowed")
    if parsed.fragment:
        raise GeminiEndpointConfigError(f"{field}: fragments are not allowed")
    if scheme == "http" and hostname.lower() not in _LOOPBACK_HOSTS:
        raise GeminiEndpointConfigError(
            f"{field}: http is allowed only for loopback hosts"
        )

    normalized = urlunsplit(
        (scheme, parsed.netloc, parsed.path.rstrip("/"), "", "")
    )
    return normalized, True


def resolve_gemini_oauth_endpoints(
    config: Mapping[str, Any] | None = None,
) -> GeminiOAuthEndpoints:
    """Resolve Gemini endpoints from the active profile or an explicit config."""
    if config is None:
        from hermes_cli.config import load_config

        config = load_config()

    providers = config.get("providers", {}) if isinstance(config, Mapping) else {}
    if not isinstance(providers, Mapping):
        providers = {}
    provider_config = providers.get("google-gemini-cli", {})
    if not isinstance(provider_config, Mapping):
        provider_config = {}

    resolved: dict[str, str] = {}
    explicit: dict[str, bool] = {}
    for field, default in _DEFAULT_ENDPOINTS.items():
        resolved[field], explicit[field] = _normalize_endpoint(
            field, provider_config.get(field), default
        )

    return GeminiOAuthEndpoints(
        **resolved,
        custom_code_assist=(
            explicit["code_assist_base_url"]
            and resolved["code_assist_base_url"]
            != _DEFAULT_ENDPOINTS["code_assist_base_url"]
        ),
    )
