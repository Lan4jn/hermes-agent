# Antigravity Interactive Agent Backend Design

Date: 2026-08-23
Status: Approved design

## Objective

Add Google Antigravity CLI as an optional interactive agent backend so users
can use Google AI Pro through the official `agy` Headless protocol while
retaining Hermes as the transport, session store, and management layer.

The backend is available to every interactive chat surface:

- Classic CLI.
- TUI.
- Electron desktop.
- Dashboard embedded TUI.
- QQBot, Telegram, and other messaging gateway adapters.
- The API server `/message` endpoint.

Cron and batch processing remain on the native Hermes agent in the first
release. They must not inherit an Antigravity default implicitly.

## Why This Is an Agent Backend

Antigravity CLI is a complete agent, not a raw model API. It has its own system
instructions, tools, permissions, subagents, and conversation state. It does
not expose OpenAI-compatible native tool calls or a raw inference endpoint.

Hermes therefore must not impersonate Antigravity's private HTTP client or
pretend `agy` is a normal model provider. Instead, interactive hosts route a
whole turn to one of two explicit backends:

- `hermes`: the existing `AIAgent` loop, unchanged.
- `antigravity`: the official long-lived `agy` stdin/stdout Headless protocol.

This keeps the core model tool schema narrow and avoids an unreliable
JSON-schema emulation of OpenAI tool calls.

## Architecture

Create a focused shared package under `agent/backends/`:

- `base.py`: `InteractiveAgentBackend` protocol and backend result/event types.
- `hermes.py`: adapter around the existing native turn runner.
- `antigravity.py`: `agy` process/session implementation.
- `router.py`: configuration, session overrides, authorization, and backend
  selection.
- `setup.py`: executable detection, installer invocation, login/model probes,
  and config persistence.

The router is shared by the classic CLI, `tui_gateway`, and messaging gateway.
No chat surface reimplements the Antigravity transport.

The backend interface owns these operations:

```python
class InteractiveAgentBackend(Protocol):
    def run_turn(self, request: BackendTurnRequest, events: BackendEventSink) -> BackendTurnResult: ...
    def interrupt(self, session_id: str) -> bool: ...
    def close_session(self, session_id: str) -> None: ...
    def shutdown(self) -> None: ...
```

`BackendTurnRequest` carries the Hermes session ID, profile, platform,
authorized principal, text, safe media paths, and working directory. It does
not carry credentials from the Antigravity keyring.

`BackendEventSink` emits the existing Hermes presentation events for message
deltas, tool progress, status, and completion. TUI, desktop, dashboard, and
gateway adapters continue consuming their current event protocol.

## Configuration

Behavioral settings live in `config.yaml`:

```yaml
agent_backends:
  default: antigravity
  antigravity:
    enabled: true
    command: agy
    model: gemini-3.7-flash-high
    effort: high
    permission_mode: trusted
    proxy_url: http://192.168.31.130:7890
    max_sessions: 8
    idle_timeout_seconds: 1800

platforms:
  qqbot:
    extra:
      agent_backend: antigravity
  telegram:
    extra:
      agent_backend: hermes
  api_server:
    extra:
      agent_backend: antigravity
```

Resolution order for interactive turns is:

1. Explicit per-session `/backend` override.
2. `platforms.<platform>.extra.agent_backend`.
3. `agent_backends.default`.
4. `hermes`.

Invalid or unavailable backend values fail closed with an actionable error.
They never silently select a paid fallback provider.

The existing `model.provider`, `model.default`, fallback models, auxiliary
models, and model credentials are not changed when Antigravity is selected.
They remain the native Hermes configuration used after switching back.

## `hermes model` UX

The Google provider group presents:

```text
Google Gemini
  Google AI Studio API Key
  Google Gemini CLI OAuth (Standard/Enterprise)
  Google Antigravity CLI (AI Pro)
```

Selecting Antigravity starts its setup flow rather than writing a fake
`model.provider`:

1. Detect or install `agy`.
2. Verify `agy --version`.
3. Guide the user through official account login.
4. Run `agy models` and select a real model slug dynamically.
5. Configure an optional standard forward proxy.
6. Configure `strict`, `sandbox`, or `trusted` permissions.
7. Select the global default and optional platform overrides.
8. Confirm all settings before saving.

The final screen states that Antigravity is an agent backend and that the
native Hermes model configuration remains available.

## Backend Commands

Add one command to the central slash command registry:

```text
/backend
/backend hermes
/backend antigravity
```

`/backend` displays the effective backend and its source (session, platform,
global, or built-in default). A successful switch applies only to the current
Hermes session and is persisted. `/new` creates a new session that inherits
the platform/global default rather than carrying the previous session
override.

The same command works in classic CLI, TUI, desktop, dashboard, and gateways.
Desktop command curation must continue allowing this built-in command.

Add a host-side setup command for explicit administration:

```bash
hermes gateway backend setup antigravity
hermes gateway backend status antigravity
```

The setup command is the only path that installs software. Gateway startup and
ordinary chat turns never execute a remote installer automatically.

## Installation and Authentication

Detection order is:

1. Explicit `agent_backends.antigravity.command` path.
2. `agy` on `PATH`.
3. Official per-user install locations:
   - Windows: `%LOCALAPPDATA%\agy\bin\agy.exe`.
   - Linux/macOS: `~/.local/bin/agy`.

When `agy` is absent, interactive setup shows the official source URL and asks
for confirmation before invoking Google's installer:

- Windows: `https://antigravity.google/cli/install.ps1`.
- Linux/macOS: `https://antigravity.google/cli/install.sh`.

Installer execution uses an argument array or downloaded script file, not a
shell command assembled from user input. Windows subprocesses use the shared
hidden-window compatibility helper.

After installation, setup launches official `agy` login. Local hosts may open
a browser. SSH sessions display Antigravity's manual URL and authorization-code
flow. Hermes never reads, copies, logs, or stores Antigravity OAuth tokens;
credentials stay in the operating-system keyring managed by `agy`.

`agy models` is the login and catalog probe. Setup fails without writing an
Antigravity default if the command reports authentication failure or returns no
models.

## Forward Proxy

Account-mode Antigravity does not expose an official custom API base URL. The
feature supports a standard network forward proxy only. It does not rewrite
Google/Antigravity hosts and does not use `GOOGLE_GEMINI_BASE_URL`, which is for
Gemini API-key mode rather than AI Pro account sessions.

`proxy_url` accepts only `http://` and `https://` URLs with a host. It rejects
userinfo, query strings, fragments, control characters, and surrounding
whitespace. A configured value is injected only into the child environment as:

- `HTTP_PROXY`
- `HTTPS_PROXY`
- `http_proxy`
- `https_proxy`

Hermes process-global environment, Telegram proxy settings, provider clients,
and other tools are unchanged. Installer downloads use the same proxy during
the explicit setup command.

An authenticated proxy URL is a secret and must not be stored literally in
`config.yaml`. Setup stores it as `ANTIGRAVITY_PROXY_URL` in the profile-local
`.env` through the existing secret persistence path, then writes
`proxy_url: ${ANTIGRAVITY_PROXY_URL}` in `config.yaml`. The existing config
expansion mechanism resolves it at runtime. Logs redact proxy credentials and
never print the expanded URL. If both a literal URL and this environment value
are present, the explicit `proxy_url` config value wins after expansion; setup
writes only one form.

## Antigravity Process Protocol

Each active Hermes session maps to one long-lived process:

```bash
agy \
  --input-format stream-json \
  --output-format stream-json \
  --model <model> \
  --effort <effort>
```

The process receives one NDJSON user event per turn:

```json
{"event":"user","message":{"content":"..."}}
```

The adapter parses bounded NDJSON lines:

- `init`: record `conversation_id` and effective runtime metadata.
- `step_update` with `agent_response`: emit message deltas.
- `step_update` with `tool`: emit sanitized Hermes tool progress.
- `result`: finish the turn and return response plus usage.

Only `result.status == "SUCCESS"` is success. `ERROR`, `CANCELED`,
`INTERRUPTED`, `INVALID`, `WAITING`, and `RUNNING` become structured backend
errors.

The process environment is built from an allowlisted copy of the host
environment plus proxy settings. No API-server caller data becomes an
environment variable. Stderr is drained concurrently into a bounded,
redacted tail so a noisy process cannot deadlock or leak credentials.

## Permissions and Host Control

Permission modes map as follows:

- `strict`: no skip flag; headless actions requiring approval are denied.
- `sandbox`: add `--sandbox`.
- `trusted`: add `--dangerously-skip-permissions` only after Hermes has
  authenticated the initiating principal.

Trusted messaging principals are the existing platform allowlist identities.
An allowlisted QQBot or Telegram user may use a trusted Antigravity backend.
Untrusted platform users cannot select or invoke it.

For `/message`, every Antigravity turn requires a valid `API_SERVER_KEY`
bearer/header/body credential or an unexpired token derived from that key,
regardless of Antigravity permission mode. `strict` can still allow workspace
file operations, so it is not a safe substitute for caller authentication. An
unauthenticated text message receives 401 before a process is started. The
existing explicit command-execution gate remains unchanged.

The Antigravity child inherits the gateway service account. On host 130 that
currently means root. Setup and status output must warn explicitly when trusted
mode will run as root or an elevated Windows user.

## Session State and Lifecycle

Extend persisted session metadata with:

- `agent_backend`: `hermes` or `antigravity`.
- `backend_conversation_id`: the opaque Antigravity conversation ID.

Schema reconciliation adds the fields without rewriting existing transcripts.
Existing sessions have an empty backend and resolve through normal defaults.

The process pool key includes profile, platform, and Hermes session ID. A
per-session lock permits only one in-flight turn. Different sessions may run
concurrently up to `max_sessions`.

When the limit is reached, only the least-recently-used idle process is closed.
Busy sessions are never evicted. If every process is busy, the new turn fails
with a capacity message rather than killing work.

Idle cleanup closes stdin, waits briefly for a clean exit, then terminates and
kills only if necessary. `/new`, session deletion, profile shutdown, and
application shutdown call `close_session` or `shutdown`.

After a gateway/app restart, the first turn for a persisted Antigravity session
starts `agy` with `--conversation <backend_conversation_id>` and the streaming
flags. If resume fails, Hermes reports it and offers `/new`; it does not silently
create a contextless continuation.

## Surface Integration

### Classic CLI

The prompt handler dispatches through the shared router. Native Hermes remains
the unchanged path. Antigravity events render through existing activity and
response primitives. Interrupt requests stop the active Antigravity turn.

### TUI, Desktop, and Dashboard

`tui_gateway` dispatches through the shared router and maps backend events to
its existing JSON-RPC event catalog. The desktop consumes those events without
a second Antigravity implementation. Dashboard chat embeds the TUI and inherits
the behavior automatically.

### Messaging Gateway

The gateway routing chokepoint selects the backend after platform authorization
and command handling, but before constructing or invoking `AIAgent`. Platform
adapters, reply routing, delivery ledgers, message formatting, and transcript
persistence remain unchanged.

### `/message`

The API adapter applies the trusted-backend auth gate before dispatch. Session
IDs continue using the existing `/message` namespace, so conversation history
and Web UI inspection remain available.

### Cron and Batch

Cron, batch runner, auxiliary tasks, title generation, compression helpers, and
subagent calls remain native Hermes. They ignore `agent_backends.default` in the
first release. No unattended Antigravity execution is introduced.

## Files and Images

Messaging adapters keep downloading media through their existing validated
paths. The backend request receives only paths that passed Hermes media-policy
and credential-path checks. The text prompt includes normalized file
references, allowing Antigravity's own tools to inspect the local copies.

The streaming stdin protocol accepts text blocks only. Hermes does not inline
arbitrary image bytes or unsupported block types into the Antigravity stream.
If a file is unavailable or outside allowed media/workspace roots, the prompt
contains a safe unavailable-file note rather than the path.

## Error Handling

- Missing executable: point to the setup command.
- Authentication required: instruct the user to run interactive `agy` login.
- Unknown model: show the configured slug and suggest rerunning setup.
- Proxy failure: identify the proxy connection failure without printing
  credentials.
- Malformed or oversized NDJSON: terminate the affected process and fail the
  turn.
- Timeout: interrupt, then terminate/kill after bounded grace periods.
- Unexpected process exit: restart and resume once; a second failure ends the
  turn.
- Capacity exhausted: reject without evicting busy sessions.
- Backend unavailable: do not silently fall back or incur another provider's
  cost. The user may explicitly switch to Hermes.

Errors are surfaced through each host's existing error event/message path.
Partial assistant text is not persisted as a successful final response.

## Testing

Tests use a small fake `agy` executable that speaks real stdin/stdout NDJSON.
No CI test requires Google credentials or network access.

Coverage includes:

- Multi-turn process reuse and conversation ID persistence.
- Profile/platform/session isolation.
- Resume after process restart.
- Streaming assistant and tool events.
- Interrupt, timeout, malformed JSON, early exit, and bounded stderr.
- LRU idle eviction, busy-session protection, and shutdown cleanup.
- Windows hidden subprocess flags and POSIX signal cleanup.
- Proxy child-environment isolation and credential redaction.
- Installer detection, explicit confirmation, and platform command selection.
- Setup cancellation and no-write behavior.
- Dynamic model catalog selection from fake `agy models` output.
- `strict`, `sandbox`, and authorized `trusted` argument construction.
- QQBot/Telegram allowlist authorization.
- `/message` 401 before process creation without `API_SERVER_KEY`, in every
  Antigravity permission mode.
- Backend resolution order and `/backend` persistence.
- Classic CLI, TUI gateway, desktop command discovery, and gateway dispatch.
- Native Hermes behavior remains unchanged when Hermes is effective.
- Cron and batch ignore the Antigravity interactive default.

Focused tests are followed by gateway, TUI gateway, model setup, session-schema,
and subprocess regression suites. Deployment validation installs `agy` through
the official flow on Windows and host 130, performs account login manually on
each host, checks proxy connectivity, runs one multi-turn chat per surface, and
verifies process cleanup and source/version parity.

## Non-Goals

- Reverse engineering or impersonating Antigravity private HTTP APIs.
- Extracting OAuth credentials from the Antigravity keyring.
- Exposing Antigravity as an OpenAI-compatible public API.
- Replacing Hermes model providers, tools, memory, or cron engine.
- Automatic installer execution during gateway startup or an ordinary turn.
- Custom reverse-proxy origins for AI Pro account mode.
- Antigravity-backed cron, batch, auxiliary, compression, or subagent tasks in
  the first release.
