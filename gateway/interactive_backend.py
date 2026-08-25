"""Bridge between shared BackendRouter and Messaging Gateway turn execution."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, List, Optional

from agent.backends.base import BackendEvent, BackendTurnRequest, BackendTurnResult
from agent.backends.router import BackendRouter

logger = logging.getLogger(__name__)


def validate_safe_media_path(path_str: str) -> Optional[str]:
    """Validate that a media path is safe to pass to Antigravity.

    Rejects path traversal, denied sensitive files, and non-existent files.
    """
    if not path_str or not isinstance(path_str, str):
        return None
    try:
        p = Path(path_str).resolve()
        if not p.is_file():
            return None
        # Deny sensitive files / patterns
        lower = str(p).lower()
        if any(secret in lower for secret in (".env", "id_rsa", "id_ed25519", "credentials", "config.json")):
            return None
        return str(p)
    except Exception:
        return None


def run_gateway_interactive_turn(
    runner: Any,
    ctx: Any,
    api_run_message: Any,
    stream_consumer: Any = None,
    media_paths: Optional[List[str]] = None,
) -> Optional[dict]:
    """Dispatches a gateway chat turn to Antigravity if configured; returns None for Hermes."""
    platform_key = (
        ctx.source.platform.value
        if hasattr(ctx.source.platform, "value")
        else str(ctx.source.platform)
    )

    session_db = getattr(runner._session_db, "_db", runner._session_db)
    router = BackendRouter(
        config=getattr(runner, "config", None) or {},
        session_db=session_db,
    )

    # Check for session-level override in session_db
    session_override = None
    if session_db and ctx.session_id:
        try:
            row = session_db.get_session(ctx.session_id)
            if row and row["agent_backend"]:
                session_override = row["agent_backend"]
        except Exception:
            pass

    selection = router.resolve(
        platform=platform_key, session_override=session_override
    )

    if selection.name == "hermes":
        return None

    # Filter safe media paths
    safe_media: list[str] = []
    if media_paths:
        for raw_path in media_paths:
            safe = validate_safe_media_path(raw_path)
            if safe:
                safe_media.append(safe)

    prompt_text = (
        api_run_message
        if isinstance(api_run_message, str)
        else str(api_run_message)
    )

    is_trusted = router.config.permission_mode == "trusted"

    req = BackendTurnRequest(
        session_id=ctx.session_id,
        profile=getattr(runner, "profile_name", "default") or "default",
        platform=platform_key,
        principal_id=ctx.source.user_id or "gateway_user",
        text=prompt_text,
        cwd=os.getcwd(),
        media_paths=safe_media,
        trusted=is_trusted,
    )

    def _events_sink(ev: BackendEvent):
        if ev.kind == "message_delta" and ev.text:
            if stream_consumer is not None:
                try:
                    stream_consumer.on_delta(ev.text)
                except Exception:
                    pass

    turn_res = router.run_turn(
        req, _events_sink, session_override=session_override
    )

    user_entry = {"role": "user", "content": ctx.message if hasattr(ctx, "message") else prompt_text}
    asst_entry = {"role": "assistant", "content": turn_res.response}
    updated_messages = [user_entry, asst_entry]

    if session_db is not None and ctx.session_id:
        try:
            session_db.append_message(ctx.session_id, user_entry)
            session_db.append_message(ctx.session_id, asst_entry)
            session_db.set_session_agent_backend(
                ctx.session_id, "antigravity", turn_res.conversation_id or ""
            )
        except Exception:
            logger.debug("failed to record gateway antigravity turn in db", exc_info=True)

    return {
        "final_response": turn_res.response,
        "messages": updated_messages,
        "api_calls": 1,
        "completed": (turn_res.status == "SUCCESS"),
        "failed": (turn_res.status != "SUCCESS"),
        "usage": turn_res.usage,
    }
