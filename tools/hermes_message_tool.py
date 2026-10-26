"""Hermes node-to-node messaging tool."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from tools.registry import registry

_MAX_RESPONSE_BYTES = 256 * 1024  # 256 KB


def _message_api_config() -> dict[str, Any]:
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
    except Exception:
        return {}
    platform_cfg = (cfg.get("platforms") or {}).get("api_server") or {}
    extra = platform_cfg.get("extra") or {}
    message_cfg = platform_cfg.get("message_api") or extra.get("message_api") or {}
    return message_cfg if isinstance(message_cfg, dict) else {}


def _configured_peers() -> dict[str, str]:
    peers = _message_api_config().get("peers") or []
    result: dict[str, str] = {}
    if not isinstance(peers, list):
        return result
    for peer in peers:
        if not isinstance(peer, dict):
            continue
        name = str(peer.get("name") or "").strip()
        url = str(peer.get("url") or peer.get("message_url") or "").strip()
        if name and url:
            result[name] = url
    return result


def check_requirements() -> bool:
    """Return True if peer messaging is available (peers configured or message_api enabled)."""
    if bool(_configured_peers()):
        return True
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        plat_cfg = (cfg.get("platforms") or {}).get("api_server") or {}
        extra = plat_cfg.get("extra") or {}
        msg_cfg = plat_cfg.get("message_api") or extra.get("message_api") or {}
        return bool(plat_cfg.get("enabled")) and bool(msg_cfg.get("enabled", True))
    except Exception:
        return False


def _normalize_target_url(raw_url: str) -> tuple[str, str | None]:
    """Validate and normalize a target base_url into a /message endpoint URL."""
    url_str = str(raw_url or "").strip()
    if not url_str:
        return "", "base_url is required"

    try:
        parsed = urlsplit(url_str)
    except Exception as exc:
        return "", f"Invalid base_url: {exc}"

    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        return "", f"Invalid base_url {raw_url!r}: scheme must be http or https with a valid host"

    # Strip query and fragment
    path = parsed.path.rstrip("/")
    if not path.endswith("/message"):
        path = f"{path}/message" if path else "/message"

    normalized = urlunsplit((parsed.scheme.lower(), parsed.netloc, path, "", ""))
    return normalized, None


def send_hermes_message(
    peer: str | None = None,
    base_url: str | None = None,
    message: str | None = None,
    command: str | None = None,
    api_key: str | None = None,
    exec_token: str | None = None,
    session_id: str = "peer-chat",
    sender_id: str = "hermes",
    sender_display_name: str = "Hermes",
    timeout: int = 180,
) -> str:
    """Send a chat message or remote command to a configured Hermes peer or arbitrary base_url."""
    peer_name = str(peer or "").strip() if peer is not None else ""
    target_base = str(base_url or "").strip() if base_url is not None else ""

    # Validate mutual exclusivity: exactly one of peer or base_url is required
    if bool(peer_name) and bool(target_base):
        return json.dumps(
            {"success": False, "error": "Provide either 'peer' or 'base_url', not both."},
            ensure_ascii=False,
        )
    if not bool(peer_name) and not bool(target_base):
        return json.dumps(
            {"success": False, "error": "Either 'peer' or 'base_url' is required."},
            ensure_ascii=False,
        )

    msg_text = str(message or "").strip() if message is not None else ""
    cmd_text = str(command or "").strip() if command is not None else ""
    key_text = str(api_key or "").strip() if api_key is not None else ""
    token_text = str(exec_token or "").strip() if exec_token is not None else ""

    if not any((msg_text, cmd_text, key_text, token_text)):
        return json.dumps(
            {
                "success": False,
                "error": "At least one of 'message', 'command', 'api_key', or 'exec_token' is required.",
            },
            ensure_ascii=False,
        )

    # Resolve target URL
    if peer_name:
        peers = _configured_peers()
        url = peers.get(peer_name)
        if not url:
            return json.dumps(
                {
                    "success": False,
                    "error": f"Hermes peer {peer_name!r} is not configured",
                    "configured_peers": sorted(peers),
                },
                ensure_ascii=False,
            )
        target_url = url
    else:
        norm_url, err = _normalize_target_url(target_base)
        if err or not norm_url:
            return json.dumps({"success": False, "error": err or "Invalid base_url"}, ensure_ascii=False)
        target_url = norm_url

    # Construct request payload
    payload: dict[str, Any] = {
        "session_id": str(session_id or "peer-chat"),
        "sender_id": str(sender_id or "hermes"),
        "sender_display_name": str(sender_display_name or "Hermes"),
    }
    if msg_text:
        payload["message"] = msg_text
    if cmd_text:
        payload["command"] = cmd_text
    if key_text:
        payload["api_key"] = key_text
    if token_text:
        payload["exec_token"] = token_text

    headers = {"Content-Type": "application/json"}
    if key_text:
        headers["X-Hermes-Api-Key"] = key_text
    if token_text:
        headers["X-Hermes-Exec-Token"] = token_text

    data = json.dumps(payload).encode("utf-8")
    req = Request(target_url, data=data, headers=headers, method="POST")

    effective_timeout = max(1, min(int(timeout or 180), 600))

    try:
        with urlopen(req, timeout=effective_timeout) as resp:
            raw_bytes = resp.read(_MAX_RESPONSE_BYTES + 1)
            truncated = len(raw_bytes) > _MAX_RESPONSE_BYTES
            if truncated:
                raw_bytes = raw_bytes[:_MAX_RESPONSE_BYTES]
            body = raw_bytes.decode("utf-8", errors="replace")

            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = {"raw": body}

            result: dict[str, Any] = {
                "success": 200 <= int(getattr(resp, "status", 200)) < 300,
                "url": target_url,
            }
            if peer_name:
                result["peer"] = peer_name
            if truncated:
                result["_truncated"] = True
                result["_truncated_note"] = f"Response exceeded {_MAX_RESPONSE_BYTES} bytes and was capped."

            if isinstance(parsed, dict):
                result.update(parsed)
            else:
                result["data"] = parsed

            return json.dumps(result, ensure_ascii=False, indent=2)

    except HTTPError as exc:
        raw_err = exc.read(_MAX_RESPONSE_BYTES).decode("utf-8", errors="replace")
        try:
            err_json = json.loads(raw_err)
        except json.JSONDecodeError:
            err_json = None

        err_result: dict[str, Any] = {
            "success": False,
            "status": exc.code,
            "url": target_url,
        }
        if peer_name:
            err_result["peer"] = peer_name
        if isinstance(err_json, dict):
            err_result.update(err_json)
        else:
            err_result["error"] = raw_err or str(exc)

        return json.dumps(err_result, ensure_ascii=False, indent=2)

    except (OSError, URLError, ValueError, TimeoutError) as exc:
        err_result = {
            "success": False,
            "url": target_url,
            "error": str(exc),
        }
        if peer_name:
            err_result["peer"] = peer_name
        return json.dumps(err_result, ensure_ascii=False, indent=2)


registry.register(
    name="send_hermes_message",
    toolset="peer_messaging",
    schema={
        "name": "send_hermes_message",
        "description": (
            "Send a chat message or execute a remote command on a configured Hermes peer or remote /message endpoint. "
            "Use this tool for Hermes-to-Hermes node coordination instead of raw shell/curl."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "peer": {
                    "type": "string",
                    "description": "Configured peer name from message_api.peers (e.g. '130'). Mutually exclusive with base_url.",
                },
                "base_url": {
                    "type": "string",
                    "description": "Target base URL (e.g. 'http://192.168.1.50:8642'). Mutually exclusive with peer.",
                },
                "message": {
                    "type": "string",
                    "description": "Message text to send to the remote Hermes instance.",
                },
                "command": {
                    "type": "string",
                    "description": "Terminal command to execute on the remote Hermes instance (requires authorization).",
                },
                "api_key": {
                    "type": "string",
                    "description": "API key for remote command authorization.",
                },
                "exec_token": {
                    "type": "string",
                    "description": "Short-lived execution token for remote command authorization.",
                },
                "session_id": {
                    "type": "string",
                    "description": "Conversation ID to reuse for continuity.",
                    "default": "peer-chat",
                },
                "sender_id": {
                    "type": "string",
                    "description": "Stable sender identifier.",
                    "default": "hermes",
                },
                "sender_display_name": {
                    "type": "string",
                    "description": "Human-readable sender name.",
                    "default": "Hermes",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Request timeout in seconds (default 180).",
                    "default": 180,
                },
            },
        },
    },
    handler=lambda args, **kw: send_hermes_message(
        peer=args.get("peer"),
        base_url=args.get("base_url"),
        message=args.get("message"),
        command=args.get("command"),
        api_key=args.get("api_key"),
        exec_token=args.get("exec_token"),
        session_id=args.get("session_id", "peer-chat"),
        sender_id=args.get("sender_id", "hermes"),
        sender_display_name=args.get("sender_display_name", "Hermes"),
        timeout=args.get("timeout", 180),
    ),
    check_fn=check_requirements,
)
