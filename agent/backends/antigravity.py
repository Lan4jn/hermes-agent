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

from agent.deadline import kill_process_tree
from agent.redact import redact_sensitive_text
from hermes_cli._subprocess_compat import split_command_line, windows_hide_flags

from .base import BackendEvent, BackendEventSink, BackendTurnRequest, BackendTurnResult
from .config import AntigravityConfig


_STDOUT_LINE_LIMIT = 10_485_760
_STDERR_LINE_LIMIT = 65_536
_TOOL_PART_LIMIT = 1_000
MAX_TURN_EVENTS = 2_000
MAX_TURN_BYTES = 52_428_800
_FAILED_STATUSES = {"ERROR", "CANCELED", "INTERRUPTED", "INVALID", "WAITING", "RUNNING"}
_TERMINAL_STATUSES = _FAILED_STATUSES | {"SUCCESS"}
_CHILD_ENV_ALLOWLIST = {
    "PATH",
    "HOME",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "LOCALAPPDATA",
    "APPDATA",
    "XDG_CONFIG_HOME",
    "XDG_CACHE_HOME",
    "XDG_DATA_HOME",
    "XDG_RUNTIME_DIR",
    "DBUS_SESSION_BUS_ADDRESS",
    "TMP",
    "TEMP",
    "TMPDIR",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "SHELL",
    "USER",
    "USERNAME",
    "LOGNAME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "COLORTERM",
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "SSH_CONNECTION",
    "SSH_CLIENT",
    "SSH_TTY",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "NO_PROXY",
    "no_proxy",
}
_OAUTH_SECRET_RE = re.compile(
    r"(?i)(\boauth[_-]?(?:(?:access|refresh)[_-]?)?token\b\s*(?:=|:\s*)[\"']?)[^\s,\"'}]+"
)


def _redact_process_text(value: str) -> str:
    redacted = redact_sensitive_text(
        value,
        force=True,
        code_file=False,
        redact_url_credentials=True,
    )
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
        self._stdout_events: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1024)
        self._stderr_tail: deque[str] = deque(maxlen=40)
        self._stderr_lock = threading.Lock()
        self._turn_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._effective_metadata: dict[str, Any] = {}
        self._reader_threads: list[threading.Thread] = []
        self._started = False
        self._fatal = False
        self._closed = False

    @property
    def pid(self) -> int | None:
        with self._state_lock:
            process = self._process
            return process.pid if process is not None and process.poll() is None else None

    @property
    def alive(self) -> bool:
        with self._state_lock:
            return self._process is not None and self._process.poll() is None

    @property
    def fatal(self) -> bool:
        with self._state_lock:
            return self._fatal

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
            with self._state_lock:
                if self._fatal or self._closed:
                    raise self._error("terminated Antigravity session cannot be reused")
            deadline = time.monotonic() + self._timeout_seconds
            try:
                process = self._ensure_process(deadline)
                content_text = request.text
                if request.media_paths:
                    attachments_block = "\n\nAttached local files validated by Hermes:\n" + "\n".join(
                        f"- {p}" for p in request.media_paths
                    )
                    content_text = f"{content_text}{attachments_block}"
                payload = {
                    "event": "user",
                    "message": {"content": content_text},
                }
                assert process.stdin is not None
                process.stdin.write(
                    (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
                )
                process.stdin.flush()
                return self._read_turn(events, deadline)
            except (BrokenPipeError, OSError):
                self._mark_fatal()
                message = self._failure_message("Antigravity transport failed")
                self._abort_process()
                raise RuntimeError(message) from None
            except Exception:
                self._mark_fatal()
                self._abort_process()
                raise

    def is_alive(self) -> bool:
        """Return True if the underlying process is currently running."""
        with self._state_lock:
            return (
                not self._fatal
                and not self._closed
                and self._process is not None
                and self._process.poll() is None
            )

    def _ensure_process(self, deadline: float) -> subprocess.Popen[bytes]:
        with self._state_lock:
            if self._fatal or self._closed:
                raise self._error("terminated Antigravity session cannot be reused")
            if self._process is not None:
                if self._process.poll() is None:
                    return self._process
                self._process = None
                self._fatal = True
                raise self._error("terminated Antigravity session cannot be reused")
            if self._started:
                self._fatal = True
                raise self._error("terminated Antigravity session cannot be reused")

            argv = split_command_line(self._config.command)
            argv.extend(
                [
                    "--input-format",
                    "stream-json",
                    "--output-format",
                    "stream-json",
                ]
            )
            if self._config.model:
                argv.extend(["--model", self._config.model])
            if self._config.effort:
                argv.extend(["--effort", self._config.effort])
            if self._config.permission_mode == "sandbox":
                argv.append("--sandbox")
            elif self._config.permission_mode == "trusted":
                argv.append("--dangerously-skip-permissions")
            if self._conversation_id:
                argv.extend(["--conversation", self._conversation_id])

            env = {
                key: os.environ[key]
                for key in _CHILD_ENV_ALLOWLIST
                if key in os.environ
            }
            if self._config.proxy_url:
                for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
                    env[key] = self._config.proxy_url
            self._stdout_events = queue.Queue(maxsize=1024)
            with self._stderr_lock:
                self._stderr_tail.clear()
            popen_kwargs: dict[str, Any] = {
                "cwd": self._cwd,
                "env": env,
                "stdin": subprocess.PIPE,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
            }
            if os.name == "nt":
                popen_kwargs["creationflags"] = windows_hide_flags() | 0x00000200
            else:
                popen_kwargs["start_new_session"] = True

            self._process = subprocess.Popen(argv, **popen_kwargs)
            process = self._process
            self._started = True

        self._start_readers(process)
        init = self._next_json(deadline)
        self._record_init(init)
        return process

    def _record_init(self, payload: dict[str, Any]) -> None:
        if payload.get("event") != "init":
            raise self._error("Antigravity protocol did not begin with init")
        conversation_id = payload.get("conversation_id")
        if not isinstance(conversation_id, str) or not conversation_id:
            raise self._error("Antigravity init omitted conversation_id")
        metadata = payload.get("init")
        if not isinstance(metadata, dict):
            raise self._error("Antigravity init omitted init payload")
        self._conversation_id = conversation_id
        self._effective_metadata = dict(metadata)

    def _start_readers(self, process: subprocess.Popen[bytes]) -> None:
        assert process.stdout is not None and process.stderr is not None
        t1 = threading.Thread(
            target=self._read_stdout,
            args=(process.stdout,),
            name=f"antigravity-stdout-{process.pid}",
            daemon=True,
        )
        t2 = threading.Thread(
            target=self._read_stderr,
            args=(process.stderr,),
            name=f"antigravity-stderr-{process.pid}",
            daemon=True,
        )
        self._reader_threads = [t1, t2]
        t1.start()
        t2.start()

    def _read_stdout(self, pipe: Any) -> None:
        try:
            while True:
                raw = pipe.readline(_STDOUT_LINE_LIMIT + 1)
                if not raw:
                    try:
                        self._stdout_events.put(("eof", None), timeout=5.0)
                    except Exception:
                        pass
                    return
                if len(raw) > _STDOUT_LINE_LIMIT or not raw.endswith(b"\n"):
                    try:
                        self._stdout_events.put(("error", "Antigravity stdout line exceeded limit"), timeout=5.0)
                    except Exception:
                        pass
                    return
                try:
                    text = raw.decode("utf-8").rstrip("\r\n")
                except UnicodeDecodeError:
                    try:
                        self._stdout_events.put(("error", "Antigravity stdout was not valid UTF-8"), timeout=5.0)
                    except Exception:
                        pass
                    return
                if len(text) > _STDOUT_LINE_LIMIT:
                    try:
                        self._stdout_events.put(("error", "Antigravity stdout line exceeded limit"), timeout=5.0)
                    except Exception:
                        pass
                    return
                try:
                    self._stdout_events.put(("line", text), timeout=5.0)
                except queue.Full:
                    try:
                        self._stdout_events.put(("error", "Antigravity stdout queue exceeded limit"), timeout=1.0)
                    except Exception:
                        pass
                    return
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
                try:
                    safe_text = _redact_process_text(text)[:_STDERR_LINE_LIMIT]
                except Exception:
                    safe_text = "[stderr redaction failed]"
                with self._stderr_lock:
                    self._stderr_tail.append(safe_text)
        finally:
            pipe.close()

    def _next_json(self, deadline: float) -> dict[str, Any]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise self._error("Antigravity turn timed out")
        try:
            kind, value = self._stdout_events.get(timeout=remaining)
        except queue.Empty:
            raise self._error("Antigravity turn timed out") from None
        if kind == "error":
            raise self._error(value)
        if kind == "eof":
            raise self._error("Antigravity process exited early")
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            raise self._error("Antigravity emitted malformed JSON") from None
        if not isinstance(payload, dict):
            raise self._error("Antigravity protocol event must be an object")
        return payload

    def _read_turn(self, events: BackendEventSink, deadline: float) -> BackendTurnResult:
        response_parts: list[str] = []
        turn_events_count = 0
        turn_bytes_count = 0
        while True:
            payload = self._next_json(deadline)
            turn_events_count += 1
            turn_bytes_count += len(json.dumps(payload, ensure_ascii=False))
            if turn_events_count > MAX_TURN_EVENTS:
                raise self._error("Antigravity turn event count exceeded limit")
            if turn_bytes_count > MAX_TURN_BYTES:
                raise self._error("Antigravity turn byte budget exceeded limit")
            event_type = payload.get("event")
            if event_type == "step_update":
                step = payload.get("step_update")
                if not isinstance(step, dict):
                    continue
                step_type = step.get("step_type")
                if step_type == "agent_response":
                    delta = step.get("text_delta", "")
                    if not isinstance(delta, str):
                        continue
                    state = step.get("state")
                    if delta:
                        response_parts.append(delta)
                        events(
                            BackendEvent(
                                kind="message_delta",
                                text=delta,
                                status=state if isinstance(state, str) else "",
                            )
                        )
                elif step_type == "tool":
                    events(self._tool_event(step))
                continue
            if event_type != "result":
                continue

            result = payload.get("result")
            if not isinstance(result, dict):
                raise self._error("Antigravity result omitted result payload")
            status = result.get("status")
            if not isinstance(status, str) or status not in _TERMINAL_STATUSES:
                raise self._error("Antigravity invalid terminal status")
            if status != "SUCCESS":
                raise self._error(f"Antigravity result status {status}")
            response = result.get("response", "".join(response_parts))
            usage = result.get("usage", {})
            if not isinstance(response, str) or not isinstance(usage, dict):
                raise self._error("Antigravity SUCCESS result had invalid fields")
            return BackendTurnResult(
                response=response,
                conversation_id=self._conversation_id,
                usage=usage,
                status=status,
            )

    @staticmethod
    def _tool_event(step: dict[str, Any]) -> BackendEvent:
        def safe_part(value: Any) -> str:
            try:
                raw = json.dumps(value, ensure_ascii=False, sort_keys=True) if not isinstance(value, str) else value
                redacted = _redact_process_text(raw)
            except Exception:
                return "[redaction failed]"
            return redacted[:_TOOL_PART_LIMIT]

        tool_info = step.get("tool_info")
        if not isinstance(tool_info, dict):
            tool_info = {}
        detail = (
            f"parameters={safe_part(tool_info.get('parameters', {}))} "
            f"output={safe_part(tool_info.get('output', ''))} "
            f"error={safe_part(tool_info.get('error', ''))}"
        )
        tool_name = step.get("tool_name", tool_info.get("name", ""))
        state = step.get("state", "")
        return BackendEvent(
            kind="tool",
            text=detail,
            tool_name=str(tool_name)[:200],
            status=str(state)[:100],
        )

    def _failure_message(self, reason: str) -> str:
        with self._stderr_lock:
            tail = "\n".join(self._stderr_tail)
        if not tail:
            return reason
        return f"{reason}; stderr tail: {tail[:4096]}"

    def _error(self, reason: str) -> RuntimeError:
        return RuntimeError(self._failure_message(reason))

    def interrupt(self) -> bool:
        with self._state_lock:
            process = self._process
        if process is None:
            return False
        if process.poll() is not None:
            self._clear_exited_process(process)
            self._mark_fatal()
            return False
        self._mark_fatal()
        self._abort_process()
        return True

    def close(self) -> None:
        with self._state_lock:
            self._closed = True
            process = self._process
        if process is None:
            return
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        self._finish_process(process, wait_first=True)

    def _abort_process(self) -> None:
        self._mark_fatal()
        with self._state_lock:
            process = self._process
        if process is None:
            return
        self._finish_process(process, wait_first=False)

    def _finish_process(
        self, process: subprocess.Popen[bytes], *, wait_first: bool
    ) -> None:
        pid = process.pid
        if wait_first and self._wait_for_exit(process):
            if pid:
                try:
                    kill_process_tree(pid)
                except Exception:
                    pass
            self._clear_exited_process(process)
            self._join_readers()
            return

        if pid:
            import signal as _signal

            try:
                kill_process_tree(
                    pid, sig=getattr(_signal, "SIGTERM", None)
                )
            except Exception:
                pass
        if process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

        if self._wait_for_exit(process):
            if pid:
                try:
                    kill_process_tree(pid)
                except Exception:
                    pass
            self._clear_exited_process(process)
            self._join_readers()
            return

        if pid:
            try:
                kill_process_tree(pid)
            except Exception:
                pass
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass

        if self._wait_for_exit(process):
            if pid:
                try:
                    kill_process_tree(pid)
                except Exception:
                    pass
            self._clear_exited_process(process)
            self._join_readers()
            return
        if process.poll() is None:
            raise self._error("Antigravity process could not be terminated")
        self._clear_exited_process(process)
        self._join_readers()

    def _join_readers(self) -> None:
        for thread in getattr(self, "_reader_threads", []):
            if thread is not threading.current_thread() and thread.is_alive():
                thread.join(timeout=1.0)

    @staticmethod
    def _wait_for_exit(process: subprocess.Popen[bytes]) -> bool:
        try:
            process.wait(timeout=0.5)
        except (OSError, subprocess.TimeoutExpired):
            return process.poll() is not None
        return process.poll() is not None

    def _clear_exited_process(self, process: subprocess.Popen[bytes]) -> None:
        if process.poll() is None:
            raise self._error("Antigravity process is still running")
        with self._state_lock:
            if self._process is process:
                self._process = None

    def _mark_fatal(self) -> None:
        with self._state_lock:
            self._fatal = True
