"""Configuration parsing for interactive agent backends."""

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlsplit


_BACKENDS = ("hermes", "antigravity")
_PERMISSION_MODES = ("strict", "sandbox", "trusted")


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
    message = (
        "proxy_url must be an HTTP(S) URL with a host and no userinfo, query, "
        "fragment, control characters, or surrounding whitespace"
    )
    if not isinstance(value, str) or value != value.strip() or any(
        ord(char) < 32 or ord(char) == 127 for char in value
    ):
        raise ValueError(message)
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme in {"http", "https"}
            and parsed.hostname is not None
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(message)
    return value, f"{parsed.scheme}://{parsed.netloc}"


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
