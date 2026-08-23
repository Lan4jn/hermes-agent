"""Configuration parsing for interactive agent backends."""

import ipaddress
import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlsplit


_BACKENDS = ("hermes", "antigravity")
_PERMISSION_MODES = ("strict", "sandbox", "trusted")
_MAX_PROXY_URL_CHARS = 4096
_ANTIGRAVITY_KEY = "agent_backends.antigravity"
_PROXY_KEY = f"{_ANTIGRAVITY_KEY}.proxy_url"


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


def _validate_backend(value: Any, key: str) -> str:
    if not isinstance(value, str) or value not in _BACKENDS:
        raise ValueError(
            f"{key} must be one of: hermes, antigravity"
        )
    return value


def resolve_backend(
    config: Mapping[str, Any], *, platform: str, session_override: str | None = None
) -> BackendSelection:
    if session_override is not None:
        return BackendSelection(
            _validate_backend(session_override, "session backend override"),
            "session",
        )

    platform_config = _mapping(_mapping(config.get("platforms")).get(platform))
    extra = _mapping(platform_config.get("extra"))
    if "agent_backend" in extra:
        return BackendSelection(
            _validate_backend(
                extra["agent_backend"],
                f"platforms.{platform}.extra.agent_backend",
            ),
            "platform",
        )

    agent_backends = _mapping(config.get("agent_backends"))
    if "default" in agent_backends:
        return BackendSelection(
            _validate_backend(
                agent_backends["default"], "agent_backends.default"
            ),
            "global",
        )
    return BackendSelection("hermes", "built-in")


def _validate_proxy_url(value: Any) -> tuple[str, str]:
    if value in (None, ""):
        return "", ""
    if not isinstance(value, str):
        raise ValueError(f"{_PROXY_KEY}: must be a URL string")
    if len(value) > _MAX_PROXY_URL_CHARS:
        raise ValueError(f"{_PROXY_KEY}: URL is too long")
    if value != value.strip():
        raise ValueError(f"{_PROXY_KEY}: surrounding whitespace is not allowed")
    if any(
        ord(char) < 0x20
        or ord(char) == 0x7F
        or char.isspace()
        or unicodedata.category(char) == "Cc"
        for char in value
    ):
        raise ValueError(
            f"{_PROXY_KEY}: whitespace and control characters are not allowed"
        )
    if "\\" in value:
        raise ValueError(f"{_PROXY_KEY}: backslashes are not allowed")
    if "?" in value:
        raise ValueError(f"{_PROXY_KEY}: query strings are not allowed")
    if "#" in value:
        raise ValueError(f"{_PROXY_KEY}: fragments are not allowed")

    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        parsed.port  # Validate malformed and out-of-range ports.
    except ValueError:
        raise ValueError(f"{_PROXY_KEY}: malformed URL") from None

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError(f"{_PROXY_KEY}: scheme must be http or https")
    if not hostname:
        raise ValueError(f"{_PROXY_KEY}: URL must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{_PROXY_KEY}: credentials are not allowed")
    if "%" in hostname:
        if not _valid_scoped_ipv6_host(hostname, parsed.netloc):
            raise ValueError(f"{_PROXY_KEY}: invalid scoped IPv6 host")
    elif "%" in parsed.netloc:
        raise ValueError(f"{_PROXY_KEY}: percent escapes are not allowed in host")
    elif not _valid_proxy_host(hostname):
        raise ValueError(f"{_PROXY_KEY}: host contains invalid characters")
    return value, f"{scheme}://{parsed.netloc}"


def _valid_scoped_ipv6_host(hostname: str, netloc: str) -> bool:
    address, separator, zone = hostname.partition("%25")
    if not netloc.startswith("[") or not separator or not zone or "%" in zone:
        return False
    if not all(char.isascii() and (char.isalnum() or char in "._~-") for char in zone):
        return False
    try:
        ipaddress.IPv6Address(address)
        return True
    except ValueError:
        return False


def _valid_proxy_host(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        pass

    absolute = hostname.endswith(".")
    dns_name = hostname[:-1] if absolute else hostname
    if (
        not dns_name
        or ":" in dns_name
        or not dns_name.isascii()
        or len(dns_name) > 253
    ):
        return False
    if all(char in "0123456789." for char in dns_name):
        return False
    labels = dns_name.split(".")
    return all(
        label
        and len(label) <= 63
        and label[0].isalnum()
        and label[-1].isalnum()
        and all(char.isalnum() or char == "-" for char in label)
        for label in labels
    )


def _require_string(
    raw: Mapping[str, Any], key: str, default: str, *, allow_empty: bool
) -> str:
    value = raw.get(key, default)
    full_key = f"{_ANTIGRAVITY_KEY}.{key}"
    if not isinstance(value, str):
        raise ValueError(f"{full_key}: must be a string")
    if not value.strip() and not (allow_empty and value == ""):
        requirement = (
            "empty or contain non-whitespace characters"
            if allow_empty
            else "contain non-whitespace characters"
        )
        raise ValueError(f"{full_key}: must {requirement}")
    return value


def _require_positive_int(
    raw: Mapping[str, Any], key: str, default: int
) -> int:
    value = raw.get(key, default)
    if type(value) is not int or value <= 0:
        raise ValueError(f"{_ANTIGRAVITY_KEY}.{key}: must be a positive integer")
    return value


def parse_antigravity_config(config: Mapping[str, Any]) -> AntigravityConfig:
    raw = _mapping(_mapping(config.get("agent_backends")).get("antigravity"))
    enabled = raw.get("enabled", False)
    if type(enabled) is not bool:
        raise ValueError(f"{_ANTIGRAVITY_KEY}.enabled: must be a boolean")
    command = _require_string(raw, "command", "agy", allow_empty=False)
    model = _require_string(raw, "model", "", allow_empty=True)
    effort = _require_string(raw, "effort", "high", allow_empty=False)
    permission_mode = raw.get("permission_mode", "strict")
    if permission_mode not in _PERMISSION_MODES:
        raise ValueError(
            f"{_ANTIGRAVITY_KEY}.permission_mode must be one of: "
            "strict, sandbox, trusted"
        )
    proxy_url, proxy_display = _validate_proxy_url(raw.get("proxy_url", ""))
    max_sessions = _require_positive_int(raw, "max_sessions", 8)
    idle_timeout_seconds = _require_positive_int(
        raw, "idle_timeout_seconds", 1800
    )
    return AntigravityConfig(
        enabled=enabled,
        command=command,
        model=model,
        effort=effort,
        permission_mode=permission_mode,
        proxy_url=proxy_url,
        proxy_display=proxy_display,
        max_sessions=max_sessions,
        idle_timeout_seconds=idle_timeout_seconds,
    )
