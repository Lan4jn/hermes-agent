"""The opt-in command and default-open chat surface of the API server."""

import asyncio
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timezone

from aiohttp import web

from gateway.platforms import message_api_keys


logger = logging.getLogger(__name__)
_PREFIX = "message_api:"


def _timestamp(value):
    try:
        return datetime.fromtimestamp(float(value), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OverflowError):
        return ""


class _MessageTokenStore:
    def __init__(self):
        self._tokens = {}

    def issue(self, home, ttl):
        now = time.time()
        self._tokens = {key: expiry for key, expiry in self._tokens.items() if expiry > now}
        token = secrets.token_urlsafe(36)
        expiry = now + ttl
        self._tokens[(home, token)] = expiry
        return token, expiry

    def validate(self, home, token):
        return bool(token) and self._tokens.get((home, token), 0) > time.time()


class MessageAPIMixin:
    @staticmethod
    def _parse_legacy_keys(raw):
        if isinstance(raw, str):
            raw = [raw]
        return [
            str(item.get("key") if isinstance(item, dict) else item).strip()
            for item in raw if item
        ] if isinstance(raw, (list, tuple, set)) else []

    def _init_message_api(self, raw):
        cfg = raw if isinstance(raw, dict) else {}
        self._message_api_enabled = bool(cfg.get("enabled", True))
        self._message_api_webui_history_enabled = bool(cfg.get("webui_history_enabled", False))
        self._message_api_allow_command_execution = bool(cfg.get("allow_command_execution", False))
        self._message_api_shared_memory_notes_enabled = bool(cfg.get("shared_memory_notes_enabled", False))
        self._message_api_session_history_delivery = bool(cfg.get("session_history_delivery", False))
        self._message_api_keys = self._parse_legacy_keys(cfg.get("api_keys"))
        try:
            ttl = int(cfg.get("token_ttl_seconds", 3600))
        except (TypeError, ValueError):
            ttl = 3600
        self._message_api_token_ttl_seconds = ttl if ttl > 0 else 3600
        self._message_token_store = _MessageTokenStore()

    async def _message_legacy_keys_for_request(self):
        from gateway.platforms.api_server import _api_request_profile
        profile = _api_request_profile.get()
        if not profile or profile == "default":
            return self._message_api_keys
        from hermes_constants import get_hermes_home
        from gateway.run import _load_gateway_config
        config = await asyncio.to_thread(_load_gateway_config, get_hermes_home() / "config.yaml")
        try:
            return self._parse_legacy_keys(config["platforms"]["api_server"]["message_api"].get("api_keys"))
        except (KeyError, TypeError, AttributeError):
            return []

    def _message_bearer_authorized(self, request):
        # _check_auth deliberately permits missing keys for tests; this surface requires a real key.
        key = self._expected_api_key()
        header = request.headers.get("Authorization", "")
        return bool(key and header.startswith("Bearer ") and
                    hmac.compare_digest(header[7:].strip().encode(), key.encode()))

    def _message_admin_auth(self, request):
        return None if self._message_bearer_authorized(request) else self._auth_failed_response()

    @staticmethod
    def _message_session_key(session_id):
        return _PREFIX + session_id

    async def _message_existing_session(self, identity):
        # A returned transcript id may be passed back as session_id. Accept it only
        # if it belongs to this surface, then keep its original declared peer key.
        db = await self._ensure_session_db_async()
        if db is not None:
            row = await asyncio.to_thread(db.get_session, identity)
            if row and self._is_message_session(row):
                key = row["session_key"]
                return key, (await asyncio.to_thread(self._declared_conversation_session, key)) or identity
        key = self._message_session_key(identity)
        return key, await asyncio.to_thread(self._declared_conversation_session, key)

    @staticmethod
    def _is_message_session(row):
        return (isinstance(row, dict) and row.get("source") == "api_server"
                and str(row.get("session_key") or "").startswith(_PREFIX))

    async def _handle_message_api(self, request):
        from gateway.platforms.api_server import _api_agent_request_reservation, _release_pending_api_work
        draining = self._draining_response()
        if draining is not None:
            return draining
        reservation = {"active": True}
        token = _api_agent_request_reservation.set(reservation)
        self._pending_agent_requests += 1
        try:
            return await self._handle_message_api_body(request)
        finally:
            _release_pending_api_work(self, reservation)
            _api_agent_request_reservation.reset(token)

    async def _handle_message_api_body(self, request):
        if not self._message_api_enabled:
            return web.json_response({"error": "message api is disabled"}, status=404)
        try:
            body = await request.json()
        except (ValueError, web.HTTPException):
            return web.json_response({"error": "invalid JSON"}, status=400)
        if not isinstance(body, dict):
            return web.json_response({"error": "invalid JSON"}, status=400)
        for field in ("message", "command", "session_id", "sender_id", "sender_display_name",
                      "api_key", "chat_key", "exec_token", "agent_mode"):
            if body.get(field) is not None and not isinstance(body[field], str):
                return web.json_response({"error": f"{field} must be a string"}, status=400)

        raw_agent_mode = body.get("agent_mode")
        agent_mode = str(raw_agent_mode or "default").strip().lower()
        if agent_mode not in ("default", "direct"):
            return web.json_response(
                {"error": f"invalid agent_mode: {raw_agent_mode}"},
                status=400,
            )

        message = (body.get("message") or "").strip()
        command = (body.get("command") or "").strip()
        legacy_key = (body.get("api_key") or request.headers.get("X-Hermes-Api-Key")
                      or request.headers.get("X-Api-Key") or request.headers.get("api-key") or "").strip()
        chat_key = (body.get("chat_key") or request.headers.get("X-Hermes-Message-Key") or legacy_key).strip()
        exec_token = (body.get("exec_token") or request.headers.get("X-Hermes-Exec-Token")
                      or request.headers.get("X-Exec-Token") or "").strip()
        if not any((message, command, legacy_key, chat_key, exec_token)):
            return web.json_response({"error": "message, command, api_key, or exec_token is required"}, status=400)
        session_id_field = body.get("session_id")
        sender_id_field = body.get("sender_id")
        raw_session_id = session_id_field.strip() if isinstance(session_id_field, str) else ""
        raw_sender_id = sender_id_field.strip() if isinstance(sender_id_field, str) else ""
        if raw_session_id:
            identity = raw_session_id
        elif raw_sender_id:
            identity = raw_sender_id
        else:
            identity = f"anon-{secrets.token_urlsafe(24)}"
        if len(identity) > self._MAX_SESSION_HEADER_LEN or any(c in identity for c in "\r\n\x00"):
            return web.json_response({"error": "invalid session id"}, status=400)

        # Keep the same reservation/cap mechanism as the other API agent routes,
        # without their mandatory Bearer precondition.
        from gateway.platforms.api_server import _api_agent_request_reservation, _release_pending_api_work
        reservation = _api_agent_request_reservation.get()
        owns_reservation = reservation is None
        if owns_reservation:
            reservation = {"active": True}
            self._pending_agent_requests += 1
        try:
            draining = self._draining_response()
            if draining is not None:
                return draining
            limited = self._concurrency_limited_response() if message or command else None
            if limited is not None:
                return limited
            if command and not self._message_api_allow_command_execution:
                return web.json_response({
                    "session_id": identity, "command": {
                        "requested": True, "authorized": False, "executed": False,
                        "error": "command execution is disabled for /message on this Hermes instance",
                    }}, status=403)
            home = self._message_home()
            bearer = self._message_bearer_authorized(request)
            legacy_keys = await self._message_legacy_keys_for_request()
            legacy_authorized = bool(legacy_key and not legacy_key.startswith("hmmsg_")
                                     and len(legacy_key) <= 1024 and any(
                hmac.compare_digest(legacy_key.encode(), key.encode()) for key in legacy_keys))
            command_authorized = bearer or legacy_authorized or self._message_token_store.validate(home, exec_token)
            if message:
                try:
                    required = (await asyncio.to_thread(message_api_keys.get_policy))["require_chat_key"]
                    chat_authorized = bearer or legacy_authorized or (
                        required and await asyncio.to_thread(message_api_keys.validate_key, chat_key))
                    if required and not chat_authorized:
                        return web.json_response({"error": "chat key required"}, status=401)
                except Exception:
                    logger.warning("Message API chat policy unavailable", exc_info=True)
                    return web.json_response({"error": "chat authorization unavailable"}, status=503)
            payload = {"session_id": identity, "command": {
                "requested": bool(command), "authorized": bool(command and command_authorized), "executed": False}}
            session_key, session_id = await self._message_existing_session(identity)
            if legacy_authorized:
                issued, expiry = self._message_token_store.issue(home, self._message_api_token_ttl_seconds)
                payload.update(exec_token=issued, exec_token_expires_at=_timestamp(expiry))

            if message:
                try:
                    history = await self._conversation_history_for_session(session_id) if session_id else []
                    sender = (raw_sender_id or ("remote-peer" if raw_session_id else identity)).strip()[:200]
                    sender_name = (body.get("sender_display_name") or "").strip()[:200]
                    result, _usage = await self._run_agent(
                        user_message=message, conversation_history=history, session_id=session_id,
                        gateway_session_key=session_key, bind_declared_conversation=True,
                        turn_author={"id": _PREFIX + sender, "name": sender_name or sender, "is_bot": False},
                        session_history_delivery="1" if self._message_api_session_history_delivery else "",
                        agent_mode=agent_mode)
                    payload["reply"] = str(result.get("final_response") or "")
                    payload["session_id"] = result.get("session_id") or session_id or identity
                    if self._message_api_shared_memory_notes_enabled and payload["reply"] and agent_mode != "direct":
                        try:
                            self._record_message_note(
                                payload["session_id"], sender, sender_name, message, payload["reply"])
                        except Exception:
                            logger.warning("Message API shared note could not be recorded", exc_info=True)
                except Exception:
                    logger.exception("Message API agent turn failed")
                    payload["error"] = "message processing failed"
                    return web.json_response(payload, status=500)

            if command:
                if not command_authorized:
                    payload["command"]["error"] = "command execution requires authorization"
                    return web.json_response(payload, status=200 if message else 401)
                try:
                    from gateway.platforms.api_server import _api_request_profile, _reserve_pending_api_work
                    request_profile = _api_request_profile.get()

                    def _run_command():
                        from gateway.session_context import clear_session_vars
                        with self._profile_scope(request_profile):
                            tokens = self._bind_api_server_session(
                                chat_id=session_id or "", session_key=session_key,
                                session_id=session_id or "", profile=request_profile or "")
                            try:
                                return self._execute_message_api_command(command, session_key)
                            finally:
                                clear_session_vars(tokens)

                    with _reserve_pending_api_work(self) as command_reservation:
                        loop = asyncio.get_running_loop()
                        worker = loop.run_in_executor(None, _run_command)

                        def _finished(done):
                            _release_pending_api_work(self, command_reservation)
                            if not done.cancelled():
                                done.exception()

                        worker.add_done_callback(_finished)
                        command_reservation["detached"] = True
                        raw = await asyncio.shield(worker)
                    output = json.loads(raw) if isinstance(raw, str) else raw
                    if not isinstance(output, dict):
                        output = {"output": str(output)}
                    payload["command"].update(executed=True, output=str(output.get("output") or "").strip(),
                                              is_error=bool(output.get("error") or
                                                            output.get("status") in {"blocked", "error"} or
                                                            output.get("exit_code", 0) != 0))
                    if output.get("error"):
                        payload["command"]["error"] = str(output["error"])
                except Exception:
                    logger.exception("Message API command failed")
                    payload["command"]["error"] = "command execution failed"
                    return web.json_response(payload, status=500)
            return web.json_response(payload)
        finally:
            if owns_reservation:
                _release_pending_api_work(self, reservation)

    @staticmethod
    def _message_home():
        from hermes_constants import get_hermes_home
        return str(get_hermes_home())

    def _record_message_note(self, session_id, sender, sender_name, message, reply):
        from hermes_constants import get_hermes_home
        path = get_hermes_home() / "memories" / "node_messages"
        path.mkdir(parents=True, exist_ok=True)
        with (path / (datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".md")).open("a", encoding="utf-8") as file:
            file.write(f"\n### Node Message Turn\n- Session: {session_id[:200]}\n"
                       f"- Sender: {(sender_name or sender)[:200]}\n"
                       f"- Request: {message[:300]}\n- Response: {reply[:500]}\n")

    @staticmethod
    def _execute_message_api_command(command, session_key):
        from tools.terminal_tool import terminal_tool
        return terminal_tool(command=command, task_id=session_key, force=True)

    async def _handle_list_message_sessions(self, request):
        auth = self._message_admin_auth(request)
        if auth is not None:
            return auth
        if not self._message_api_enabled or not self._message_api_webui_history_enabled:
            return web.json_response({"error": "message api is disabled"}, status=404)
        db = await self._ensure_session_db_async()
        if db is None:
            return web.json_response([])
        rows = await asyncio.to_thread(db.list_sessions_rich, source="api_server", limit=200,
                                       order_by_last_active=True)
        return web.json_response([{
            "id": row["id"], "title": row.get("title") or row["id"],
            "preview": row.get("preview", ""), "message_count": int(row.get("message_count") or 0),
            "created": _timestamp(row.get("started_at")),
            "updated": _timestamp(row.get("last_active") or row.get("started_at")),
        } for row in rows if self._is_message_session(row)])

    async def _handle_get_message_session(self, request):
        auth = self._message_admin_auth(request)
        if auth is not None:
            return auth
        if not self._message_api_enabled or not self._message_api_webui_history_enabled:
            return web.json_response({"error": "message api is disabled"}, status=404)
        session_id = request.match_info.get("session_id", "")
        db = await self._ensure_session_db_async()
        row = await asyncio.to_thread(db.get_session, session_id) if db is not None else None
        if not self._is_message_session(row):
            return web.json_response({"error": "message session not found"}, status=404)
        history = await self._conversation_history_for_session(session_id)
        return web.json_response({
            "id": session_id,
            "messages": [{"role": msg["role"], "content": str(msg.get("content") or "")}
                         for msg in history if msg.get("role") in {"user", "assistant"}],
            "summary": row.get("title") or "", "created": _timestamp(row.get("started_at")),
            "updated": _timestamp(row.get("last_active") or row.get("started_at")),
        })
