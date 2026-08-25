"""Bridge between shared BackendRouter and TUI Gateway prompt execution."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from agent.backends.base import BackendEvent, BackendTurnRequest
from agent.backends.router import BackendRouter

logger = logging.getLogger(__name__)

_shared_tui_router: BackendRouter | None = None


def get_tui_backend_router(
    config: dict | None = None, session_db: Any = None
) -> BackendRouter:
    global _shared_tui_router
    if _shared_tui_router is None:
        _shared_tui_router = BackendRouter(
            config=config or {}, session_db=session_db
        )
    return _shared_tui_router


def run_interactive_backend_turn(
    session: dict,
    sid: str,
    run_message: Any,
    stream_cb: Callable[[str], None],
    emit_fn: Callable[[str, str, dict], None],
    history: list[dict],
    user_text: str = "",
) -> dict | None:
    """Dispatches a prompt turn to Antigravity if configured; returns None for Hermes."""
    agent = session.get("agent")
    user_config = getattr(agent, "user_config", None) or {}
    session_db = getattr(agent, "_session_db", None)
    router = get_tui_backend_router(user_config, session_db=session_db)

    platform = session.get("platform") or "tui"
    session_override = session.get("agent_backend_override")
    selection = router.resolve(
        platform=platform, session_override=session_override
    )

    if selection.name == "hermes":
        return None

    # Handle Antigravity turn
    session_key = session.get("session_key") or sid
    profile = session.get("profile") or "default"
    principal_id = session.get("user_id") or "local_user"
    trusted = router.config.permission_mode == "trusted"

    if not isinstance(run_message, str):
        prompt_text = str(run_message)
    else:
        prompt_text = run_message

    req = BackendTurnRequest(
        session_id=session_key,
        profile=profile,
        platform=platform,
        principal_id=principal_id,
        text=prompt_text,
        cwd=os.getcwd(),
        trusted=trusted,
    )

    def _events_sink(ev: BackendEvent):
        if ev.kind == "message_delta" and ev.text:
            stream_cb(ev.text)
        elif ev.kind == "tool":
            payload = {"name": ev.tool_name or "", "args": ev.tool_args or {}}
            if ev.state == "DONE":
                payload["result"] = ev.tool_result or ""
                emit_fn("tool.complete", sid, payload)
            else:
                emit_fn("tool.start", sid, payload)
        elif ev.kind == "status":
            emit_fn("status.update", sid, {"status": ev.status or ""})

    turn_res = router.run_turn(
        req, _events_sink, session_override=session_override
    )

    user_entry = {"role": "user", "content": user_text or prompt_text}
    asst_entry = {"role": "assistant", "content": turn_res.response}
    updated_messages = list(history) + [user_entry, asst_entry]

    if session_db is not None and session_key:
        try:
            session_db.append_message(session_key, user_entry)
            session_db.append_message(session_key, asst_entry)
            session_db.set_session_agent_backend(
                session_key, "antigravity", turn_res.conversation_id or ""
            )
        except Exception:
            logger.debug(
                "failed to append messages to session db in tui turn",
                exc_info=True,
            )

    return {
        "final_response": turn_res.response,
        "messages": updated_messages,
        "api_calls": 1,
        "completed": (turn_res.status == "SUCCESS"),
        "failed": (turn_res.status != "SUCCESS"),
        "usage": turn_res.usage,
    }
