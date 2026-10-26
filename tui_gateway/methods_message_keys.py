"""Message API keys JSON-RPC methods for Desktop management."""

from __future__ import annotations

import logging
from typing import Any, Dict

from .method_ctx import HandlerRegistry, bind_module

logger = logging.getLogger(__name__)
_registry = HandlerRegistry()
method = _registry.method
_profile_scoped = _registry.profile_scoped


@method("message_keys.list")
@_profile_scoped
def _(rid, params: dict) -> dict:
    try:
        from gateway.platforms import message_api_keys
        keys = message_api_keys.list_keys()
        return _ok(rid, {"items": keys})
    except Exception as e:
        return _err(rid, 5095, str(e))


@method("message_keys.create")
@_profile_scoped
def _(rid, params: dict) -> dict:
    try:
        from gateway.platforms import message_api_keys
        name = str(params.get("name") or "").strip()
        if not (1 <= len(name) <= 80):
            return _err(rid, 4001, "name must be between 1 and 80 characters")
        item = message_api_keys.create_key(name)
        return _ok(rid, item)
    except Exception as e:
        return _err(rid, 5095, str(e))


@method("message_keys.revoke")
@_profile_scoped
def _(rid, params: dict) -> dict:
    try:
        from gateway.platforms import message_api_keys
        key_id = str(params.get("id") or "").strip()
        if not key_id:
            return _err(rid, 4002, "id is required")
        removed = message_api_keys.revoke_key(key_id)
        return _ok(rid, {"ok": True, "removed": bool(removed)})
    except Exception as e:
        return _err(rid, 5095, str(e))


@method("message_keys.get_policy")
@_profile_scoped
def _(rid, params: dict) -> dict:
    try:
        from gateway.platforms import message_api_keys
        policy = message_api_keys.get_policy()
        return _ok(rid, policy)
    except Exception as e:
        return _err(rid, 5095, str(e))


@method("message_keys.set_policy")
@_profile_scoped
def _(rid, params: dict) -> dict:
    try:
        from gateway.platforms import message_api_keys
        val = params.get("require_chat_key")
        if not isinstance(val, bool):
            return _err(rid, 4003, "require_chat_key must be a boolean")
        message_api_keys.set_policy(val)
        return _ok(rid, message_api_keys.get_policy())
    except Exception as e:
        return _err(rid, 5095, str(e))


def register(server) -> None:
    bind_module(globals(), server, skip=("_",))
