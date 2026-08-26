"""Bridge between shared BackendRouter and Messaging Gateway turn execution."""

from __future__ import annotations

import dataclasses
import logging
import os
from typing import Any, Callable, List, Mapping, Optional

from agent.backends.base import BackendEvent, BackendTurnRequest, BackendTurnResult
from agent.backends.router import BackendRouter
from gateway.platforms.base import validate_media_delivery_path

logger = logging.getLogger(__name__)


def resolve_runner_raw_config(runner: Any, ctx: Any = None) -> Mapping[str, Any]:
    """Resolve a profile-aware dictionary/Mapping from TurnContext or GatewayRunner."""
    if ctx is not None and isinstance(getattr(ctx, "user_config", None), Mapping):
        return ctx.user_config

    if runner is None:
        return {}

    # Check direct dictionary attributes
    if isinstance(getattr(runner, "user_config", None), Mapping):
        return runner.user_config

    if isinstance(getattr(runner, "raw_config", None), Mapping):
        return runner.raw_config

    if isinstance(getattr(runner, "config", None), Mapping):
        return runner.config

    # Load from config path
    config_path = getattr(runner, "_config_path", None)
    if config_path:
        try:
            from gateway.run import _load_gateway_config

            loaded = _load_gateway_config(config_path)
            if isinstance(loaded, Mapping):
                return loaded
        except Exception:
            logger.debug("Failed to load gateway config from %s", config_path, exc_info=True)

    return {}


def get_gateway_backend_router(
    runner: Any, profile: str = "default", raw_config: Mapping[str, Any] = None
) -> BackendRouter:
    """Obtain or initialize the persistent BackendRouter for a GatewayRunner and profile."""
    if runner is None:
        return BackendRouter(config=raw_config or {})

    routers = getattr(runner, "_backend_routers", None)
    if routers is None:
        routers = {}
        single_router = getattr(runner, "_backend_router", None)
        if single_router is not None:
            routers[profile] = single_router
        try:
            runner._backend_routers = routers
        except Exception:
            pass

    if profile in routers:
        return routers[profile]

    if raw_config is None:
        raw_config = resolve_runner_raw_config(runner)

    session_db = getattr(getattr(runner, "_session_db", None), "_db", getattr(runner, "_session_db", None))
    router = BackendRouter(config=raw_config, session_db=session_db)
    routers[profile] = router
    try:
        runner._backend_router = router
    except Exception:
        pass
    return router


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

    profile = (
        getattr(ctx, "profile", None)
        or (hasattr(ctx, "source") and getattr(ctx.source, "profile", None))
        or getattr(runner, "profile_name", "default")
        or "default"
    )
    raw_cfg = resolve_runner_raw_config(runner, ctx=ctx)
    router = get_gateway_backend_router(runner, profile=profile, raw_config=raw_cfg)
    session_db = getattr(getattr(runner, "_session_db", None), "_db", getattr(runner, "_session_db", None))

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

    # Filter safe media paths using Hermes canonical validator
    safe_media: list[str] = []
    if media_paths:
        for raw_path in media_paths:
            safe = validate_media_delivery_path(raw_path)
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
        profile=profile,
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

    user_entry = {
        "role": "user",
        "content": ctx.message if hasattr(ctx, "message") else prompt_text,
    }
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


def interrupt_gateway_turn(
    runner: Any,
    session_id: str,
    platform: str,
    profile: str = "default",
) -> bool:
    """Interrupt an in-flight Antigravity turn for the given session."""
    router = get_gateway_backend_router(runner, profile=profile)
    return router.interrupt(profile=profile, platform=platform, session_id=session_id)
