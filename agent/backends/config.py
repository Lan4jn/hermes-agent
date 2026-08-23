"""Configuration parsing for interactive agent backends."""

import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlsplit


_BACKENDS = ("hermes", "antigravity")
_PERMISSION_MODES = ("strict", "sandbox", "trusted")
_MAX_PROXY_URL_CHARS = 4096


@dataclass(frozen=True)
class BackendSelection:
    name: str
    source: str


@dataclass(frozen=True)
class AntigravityConfig:
    enabled: bool = False
    command: str = "agy"
    model: str = ""
    effort: str = "high"
    permission_mode: str = "strict"
    proxy_url: str = ""
    proxy_display: str = ""
    max_sessions: int = 8
    idle_timeout_seconds: int = 1800


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _validate_backend(value: Any) -> str:
    if not isinstance(value, str) or value not in _BACKENDS:
        raise ValueError(
            "Backend must be one of hermes, antigravity; set agent_backend "
            "in config.yaml or use /backend hermes."
        )
    return value


def resolve_backend(
    config: Mapping[str, Any], *, platform: str, session_override: str | None = None
) -> BackendSelection:
    if session_override is not None:
        return BackendSelection(_validate_backend(session_override), "session")

    platform_config = _mapping(_mapping(config.get("platforms")).get(platform))
    extra = _mapping(platform_config.get("extra"))
    if "agent_backend" in extra:
        return BackendSelection(
            _validate_backend(extra["agent_backend"]), "platform"
        )

    agent_backends = _mapping(config.get("agent_backends"))
    if "default" in agent_backends:
        return BackendSelection(
            _validate_backend(agent_backends["default"]), "global"
        )
    return BackendSelection("hermes", "built-in")


def _validate_proxy_url(value: Any) -> tuple[str, str]:
    if value in (None, ""):
        return "", ""
    if not isinstance(value, str):
        raise ValueError("proxy_url: must be a URL string")
    if len(value) > _MAX_PROXY_URL_CHARS:
        raise ValueError("proxy_url: URL is too long")
    if value != value.strip():
        raise ValueError("proxy_url: surrounding whitespace is not allowed")
    if any(
        ord(char) < 0x20
        or ord(char) == 0x7F
        or char.isspace()
        or unicodedata.category(char) == "Cc"
        for char in value
    ):
        raise ValueError(
            "proxy_url: whitespace and control characters are not allowed"
        )
    if "\\" in value:
        raise ValueError("proxy_url: backslashes are not allowed")
    if "?" in value:
        raise ValueError("proxy_url: query strings are not allowed")
    if "#" in value:
        raise ValueError("proxy_url: fragments are not allowed")

    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        parsed.port  # Validate malformed and out-of-range ports.
    except ValueError:
        raise ValueError("proxy_url: malformed URL") from None

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError("proxy_url: scheme must be http or https")
    if not hostname:
        raise ValueError("proxy_url: URL must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("proxy_url: credentials are not allowed")
    return value, f"{scheme}://{parsed.netloc}"


def parse_antigravity_config(config: Mapping[str, Any]) -> AntigravityConfig:
    raw = _mapping(_mapping(config.get("agent_backends")).get("antigravity"))
    permission_mode = raw.get("permission_mode", "strict")
    if permission_mode not in _PERMISSION_MODES:
        raise ValueError(
            "permission_mode must be one of: strict, sandbox, trusted"
        )
    proxy_url, proxy_display = _validate_proxy_url(raw.get("proxy_url", ""))
    return AntigravityConfig(
        enabled=raw.get("enabled", False),
        command=raw.get("command", "agy"),
        model=raw.get("model", ""),
        effort=raw.get("effort", "high"),
        permission_mode=permission_mode,
        proxy_url=proxy_url,
        proxy_display=proxy_display,
        max_sessions=raw.get("max_sessions", 8),
        idle_timeout_seconds=raw.get("idle_timeout_seconds", 1800),
    )
