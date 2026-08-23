"""Long-lived NDJSON transport for the Antigravity headless CLI."""

from __future__ import annotations

from collections import deque
import json
import os
import queue
import re
import subprocess
import threading
import time
from typing import Any

from agent.redact import redact_sensitive_text
from hermes_cli._subprocess_compat import split_command_line, windows_hide_flags

from .base import BackendEvent, BackendEventSink, BackendTurnRequest, BackendTurnResult
from .config import AntigravityConfig


_STDOUT_LINE_LIMIT = 16_384
_STDERR_LINE_LIMIT = 4_096
_TOOL_PART_LIMIT = 1_000
_FAILED_STATUSES = {"ERROR", "CANCELED", "INTERRUPTED", "INVALID", "WAITING", "RUNNING"}
_OAUTH_SECRET_RE = re.compile(
    r"(?i)(\boauth[_-]?(?:(?:access|refresh)[_-]?)?token\b\s*(?:=|:\s*)[\"']?)[^\s,\"'}]+"
)


def _redact_process_text(value: str) -> str:
    redacted = redact_sensitive_text(value, force=True, code_file=False)
    return _OAUTH_SECRET_RE.sub(r"\1***", redacted)


class AntigravitySession:
    """One serialized conversation over one persistent ``agy`` process."""

    def __init__(
        self,
        config: AntigravityConfig,
        cwd: str,
        conversation_id: str = "",
        *,
        timeout_seconds: float = 120,
    ) -> None:
        self._config = config
        self._cwd = cwd
        self._conversation_id = conversation_id
        self._timeout_seconds = timeout_seconds
        self._process: subprocess.Popen[bytes] | None = None
        self._stdout_events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._stderr_tail: deque[str] = deque(maxlen=40)
        self._turn_lock = threading.Lock()
        self._process_lock = threading.Lock()
        self._effective_metadata: dict[str, Any] = {}
        self._unusable = False

    @property
    def pid(self) -> int | None:
        with self._process_lock:
            process = self._process
            return process.pid if process is not None and process.poll() is None else None

    @property
    def conversation_id(self) -> str:
        return self._conversation_id

    @property
    def effective_metadata(self) -> dict[str, Any]:
        return dict(self._effective_metadata)

    def run_turn(
        self, request: BackendTurnRequest, events: BackendEventSink
    ) -> BackendTurnResult:
        if self._config.permission_mode == "trusted" and not request.trusted:
            raise PermissionError("trusted Antigravity mode requires an authorized request")

        with self._turn_lock:
            if self._unusable:
                raise RuntimeError("terminated Antigravity session cannot be reused")
            deadline = time.monotonic() + self._timeout_seconds
            try:
                process = self._ensure_process(deadline)
                payload = {
                    "event": "user",
                    "message": {"content": request.text},
                }
                assert process.stdin is not None
                process.stdin.write(
                    (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
                )
                process.stdin.flush()
                return self._read_turn(events, deadline)
            except (BrokenPipeError, OSError) as exc:
                self._abort_process()
                raise RuntimeError(self._failure_message(f"Antigravity transport failed: {exc}")) from None
            except Exception:
                self._abort_process()
                raise

    def _ensure_process(self, deadline: float) -> subprocess.Popen[bytes]:
        with self._process_lock:
            if self._process is not None and self._process.poll() is None:
                return self._process

            argv = split_command_line(self._config.command)
            argv.extend(
                [
                    "--input-format",
                    "stream-json",
                    "--output-format",
                    "stream-json",
                    "--model",
                    self._config.model,
                    "--effort",
                    self._config.effort,
                ]
            )
            if self._config.permission_mode == "sandbox":
                argv.append("--sandbox")
            elif self._config.permission_mode == "trusted":
                argv.append("--dangerously-skip-permissions")
            if self._conversation_id:
                argv.extend(["--conversation", self._conversation_id])

            env = os.environ.copy()
            if self._config.proxy_url:
                for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
                    env[key] = self._config.proxy_url
            self._stdout_events = queue.Queue()
            self._stderr_tail.clear()
            self._process = subprocess.Popen(
                argv,
                cwd=self._cwd,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=windows_hide_flags(),
            )
            process = self._process

        self._start_readers(process)
        init = self._next_json(deadline)
        if init.get("event") != "init":
            raise RuntimeError("Antigravity protocol did not begin with init")
        conversation_id = init.get("conversation_id")
        if not isinstance(conversation_id, str) or not conversation_id:
            raise RuntimeError("Antigravity init omitted conversation_id")
        self._conversation_id = conversation_id
        self._effective_metadata = {
            key: value for key, value in init.items() if key not in {"event", "conversation_id"}
        }
        return process

    def _start_readers(self, process: subprocess.Popen[bytes]) -> None:
        assert process.stdout is not None and process.stderr is not None
        threading.Thread(
            target=self._read_stdout,
            args=(process.stdout,),
            name=f"antigravity-stdout-{process.pid}",
            daemon=True,
        ).start()
        threading.Thread(
            target=self._read_stderr,
            args=(process.stderr,),
            name=f"antigravity-stderr-{process.pid}",
            daemon=True,
        ).start()

    def _read_stdout(self, pipe: Any) -> None:
        try:
            while True:
                raw = pipe.readline(_STDOUT_LINE_LIMIT + 1)
                if not raw:
                    self._stdout_events.put(("eof", None))
                    return
                if len(raw) > _STDOUT_LINE_LIMIT or not raw.endswith(b"\n"):
                    self._stdout_events.put(("error", "Antigravity stdout line exceeded limit"))
                    return
                try:
                    text = raw.decode("utf-8").rstrip("\r\n")
                except UnicodeDecodeError:
                    self._stdout_events.put(("error", "Antigravity stdout was not valid UTF-8"))
                    return
                if len(text) > _STDOUT_LINE_LIMIT:
                    self._stdout_events.put(("error", "Antigravity stdout line exceeded limit"))
                    return
                self._stdout_events.put(("line", text))
        finally:
            pipe.close()

    def _read_stderr(self, pipe: Any) -> None:
        try:
            while True:
                raw = pipe.readline(_STDERR_LINE_LIMIT + 1)
                if not raw:
                    return
                if len(raw) > _STDERR_LINE_LIMIT or not raw.endswith(b"\n"):
                    self._stdout_events.put(("error", "Antigravity stderr line exceeded limit"))
                    return
                text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if len(text) > _STDERR_LINE_LIMIT:
                    self._stdout_events.put(("error", "Antigravity stderr line exceeded limit"))
                    return
                self._stderr_tail.append(text)
        finally:
            pipe.close()

    def _next_json(self, deadline: float) -> dict[str, Any]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(self._failure_message("Antigravity turn timed out"))
        try:
            kind, value = self._stdout_events.get(timeout=remaining)
        except queue.Empty:
            raise RuntimeError(self._failure_message("Antigravity turn timed out")) from None
        if kind == "error":
            raise RuntimeError(self._failure_message(value))
        if kind == "eof":
            raise RuntimeError(self._failure_message("Antigravity process exited early"))
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            raise RuntimeError(self._failure_message("Antigravity emitted malformed JSON")) from None
        if not isinstance(payload, dict):
            raise RuntimeError("Antigravity protocol event must be an object")
        return payload

    def _read_turn(self, events: BackendEventSink, deadline: float) -> BackendTurnResult:
        emitted = ""
        while True:
            payload = self._next_json(deadline)
            event_type = payload.get("event")
            if event_type == "step_update":
                step = payload.get("step")
                if not isinstance(step, dict):
                    continue
                step_type = step.get("type")
                if step_type == "agent_response":
                    message = self._message_text(step.get("message"))
                    if message.startswith(emitted):
                        delta = message[len(emitted):]
                        emitted = message
                    elif emitted.startswith(message):
                        delta = ""
                    else:
                        delta = message
                        emitted += message
                    if delta:
                        events(BackendEvent(kind="message_delta", text=delta, status=str(step.get("status", ""))))
                elif step_type == "tool":
                    events(self._tool_event(step))
                continue
            if event_type != "result":
                continue

            status = str(payload.get("status", ""))
            if status != "SUCCESS":
                label = status if status in _FAILED_STATUSES else status or "missing"
                raise RuntimeError(self._failure_message(f"Antigravity result status {label}"))
            response = payload.get("response", emitted)
            usage = payload.get("usage", {})
            if not isinstance(response, str) or not isinstance(usage, dict):
                raise RuntimeError("Antigravity SUCCESS result had invalid fields")
            return BackendTurnResult(
                response=response,
                conversation_id=self._conversation_id,
                usage=usage,
                status=status,
            )

    @staticmethod
    def _message_text(value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, dict) and isinstance(value.get("content"), str):
            return value["content"]
        return ""

    @staticmethod
    def _tool_event(step: dict[str, Any]) -> BackendEvent:
        def safe_part(value: Any) -> str:
            try:
                raw = json.dumps(value, ensure_ascii=False, sort_keys=True) if not isinstance(value, str) else value
                redacted = _redact_process_text(raw)
            except Exception:
                return "[redaction failed]"
            return redacted[:_TOOL_PART_LIMIT]

        detail = f"input={safe_part(step.get('input', {}))} output={safe_part(step.get('output', ''))}"
        return BackendEvent(
            kind="tool",
            text=detail,
            tool_name=str(step.get("name", ""))[:200],
            status=str(step.get("status", ""))[:100],
        )

    def _failure_message(self, reason: str) -> str:
        tail = "\n".join(self._stderr_tail)
        if not tail:
            return reason
        try:
            tail = _redact_process_text(tail)
        except Exception:
            tail = "[stderr redaction failed]"
        return f"{reason}; stderr tail: {tail[:4096]}"

    def interrupt(self) -> bool:
        with self._process_lock:
            process = self._process
        if process is None or process.poll() is not None:
            return False
        self._abort_process()
        return True

    def close(self) -> None:
        self._unusable = True
        with self._process_lock:
            process = self._process
        if process is None:
            return
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        self._finish_process(process)

    def _abort_process(self) -> None:
        self._unusable = True
        with self._process_lock:
            process = self._process
        if process is None:
            return
        if process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
        self._finish_process(process)

    def _finish_process(self, process: subprocess.Popen[bytes]) -> None:
        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            try:
                process.terminate()
                process.wait(timeout=0.5)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                    process.wait(timeout=0.5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        with self._process_lock:
            if self._process is process:
                self._process = None
