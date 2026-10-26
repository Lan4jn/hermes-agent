"""Message API keys management routes for the Dashboard."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, Response

from hermes_cli.web_routers._common import http_failure, require, scoped_to_thread
from gateway.platforms import message_api_keys

log = logging.getLogger("hermes_cli.web_server")
router = APIRouter()


def _set_no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("/api/message/keys")
async def list_message_keys(response: Response, profile: Optional[str] = None) -> List[Dict[str, Any]]:
    _set_no_store(response)
    with http_failure("Failed to list message keys", 500, "message_keys"):
        return await scoped_to_thread(profile, message_api_keys.list_keys)


@router.post("/api/message/keys")
async def create_message_key(
    request: Request, response: Response, profile: Optional[str] = None
) -> Dict[str, Any]:
    _set_no_store(response)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")
    raw_name = body.get("name")
    if not isinstance(raw_name, str):
        raise HTTPException(status_code=400, detail="name must be a string")
    name = raw_name.strip()
    if not (1 <= len(name) <= 80):
        raise HTTPException(status_code=400, detail="name must be between 1 and 80 characters")

    with http_failure("Failed to create message key", 500, "message_keys"):
        return await scoped_to_thread(profile, lambda: message_api_keys.create_key(name))


@router.delete("/api/message/keys/{key_id}")
async def revoke_message_key(
    key_id: str, response: Response, profile: Optional[str] = None
) -> Dict[str, Any]:
    _set_no_store(response)
    clean_id = require(key_id, "Key ID is required")
    with http_failure("Failed to revoke message key", 500, "message_keys"):
        removed = await scoped_to_thread(profile, lambda: message_api_keys.revoke_key(clean_id))
    return {"ok": True, "removed": removed}


@router.get("/api/message/keys/policy")
async def get_message_keys_policy(response: Response, profile: Optional[str] = None) -> Dict[str, Any]:
    _set_no_store(response)
    with http_failure("Failed to get message keys policy", 500, "message_keys"):
        return await scoped_to_thread(profile, message_api_keys.get_policy)


@router.put("/api/message/keys/policy")
async def set_message_keys_policy(
    request: Request, response: Response, profile: Optional[str] = None
) -> Dict[str, Any]:
    _set_no_store(response)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")
    val = body.get("require_chat_key")
    if not isinstance(val, bool):
        raise HTTPException(status_code=400, detail="require_chat_key must be a boolean")

    with http_failure("Failed to update message keys policy", 500, "message_keys"):
        def _update():
            message_api_keys.set_policy(val)
            return message_api_keys.get_policy()

        return await scoped_to_thread(profile, _update)
