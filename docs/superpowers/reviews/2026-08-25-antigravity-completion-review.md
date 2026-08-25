# Antigravity Backend Completion Review

Date: 2026-08-25
Branch: `feature/antigravity-backend`
Reviewed committed HEAD: `9c3aec3b9947c1f911147e780f7b4f56618bbd67`
Remote fork HEAD at review time: `18ac72ba54c2a0eac494666f700a49fe016e267f`
Conclusion: Not complete; not deployable

## Executive Summary

The branch now contains implementations for the core Antigravity transport,
session pool, SessionDB fields, setup wizard, `hermes model`, classic CLI,
TUI, Desktop command discovery, messaging gateway, and `/message` auth gate.
The committed focused tests are green, but several tests construct simplified
objects that differ from production runtime types. Review of the real call
paths found multiple blockers that prevent Antigravity from working reliably
outside tests.

Estimated completion:

- Surface/code coverage: approximately 85%.
- Production-ready functional completion: approximately 55-60%.
- Deployment readiness: 0%; do not deploy.

The active feature worktree was also dirty during review. In particular,
`agent/backends/router.py` had been truncated to zero bytes by an uncommitted
parallel edit. This review tested the committed HEAD in a separate detached
audit worktree so the in-progress files were not modified.

## Blocking Findings

### 1. Active Worktree Is Not Runnable

At review time the active worktree contained an uncommitted deletion of all
116 lines in `agent/backends/router.py`. Imports of `BackendRouter` fail in
that state. Three other files had uncommitted trailing blank lines.

Do not commit or push the empty router. Coordinate with the active developer
before restoring or replacing their edits.

### 2. Gateway Passes the Wrong Config Type

`gateway/interactive_backend.py` constructs `BackendRouter` with
`runner.config`. In production `GatewayRunner.config` is a `GatewayConfig`
dataclass. `BackendRouter` and `parse_antigravity_config` require a Mapping and
call `.get()`.

Result: an Antigravity gateway turn raises before backend selection. Tests use
a fake runner whose `config` is a dict, so they do not reproduce production.

Required fix: resolve the profile-aware raw/effective config through the
canonical config loader and pass a Mapping. Add an E2E test with a real
`GatewayConfig`/`GatewayRunner` construction path.

### 3. Gateway Creates a New Pool Every Turn

`run_gateway_interactive_turn()` constructs a new `BackendRouter` and therefore
a new `AntigravitySessionPool` for every message. The router is neither stored
on the runner nor shut down.

Consequences:

- No long-lived multi-turn `agy` process.
- Lost Antigravity context/cache between messages.
- Persisted conversation IDs are not used to initialize the next process.
- Potential orphan process and reader-thread leaks.

Required fix: make one router/pool owner per profile-aware gateway runner,
close sessions at `/new`/delete boundaries, and shut down the pool with the
gateway lifecycle.

### 4. TUI Reads a Configuration Attribute That Does Not Exist

`tui_gateway/interactive_backend.py` reads `agent.user_config`. `AIAgent` does
not define that attribute, so the bridge resolves `{}` and selects Hermes by
default. Its singleton router also captures only the first config/profile and
SessionDB supplied to the process.

Required fix: load config through the TUI session's profile scope and own a
router per profile/session domain, not one process-global singleton. Test with
a real agent/session where no synthetic `user_config` attribute is injected.

### 5. `/message` Does Not Dispatch to Antigravity

The API server adds an Antigravity authentication check, then continues through
the existing native `_run_agent()` implementation. No API server call site
invokes `BackendRouter` or the Antigravity pool.

The auth test uses `APIServerAdapter.__new__`, assigns a dict to `server.config`,
and mocks `_run_agent`; it proves only the isolated 401 branch. A real adapter
stores `PlatformConfig`, which also cannot be passed directly to
`resolve_backend`.

Required fix: authenticate before spawning, then call a shared interactive
backend dispatcher with the profile-scoped raw config. Add a real aiohttp
adapter E2E proving fake `agy` starts for an authenticated request and does not
start for an unauthenticated one.

### 6. Gateway `/backend` Handler Is Not Dispatched

`GatewaySlashCommandsMixin._handle_backend_command()` exists, and the central
command registry contains `backend`, but `gateway/run.py` has no
`canonical == "backend"` dispatch branch. The command is recognized and may
emit hooks, but never reaches its handler.

Required fix: wire the canonical command to the handler and add a dispatch E2E,
not only direct handler tests.

### 7. Gateway Media Validation Bypasses Existing Policy

`gateway/interactive_backend.py::validate_safe_media_path()` implements a short
filename substring denylist. It accepts any existing absolute file outside the
intended media/workspace roots unless its name happens to contain one of five
strings. Sensitive files such as `/etc/shadow`, alternate private-key names,
and profile auth files can pass.

Required fix: delete the duplicate validator and reuse Hermes' canonical media
delivery/path policy. Tests must cover allowed staged QQ/Telegram media and
credential/system paths.

## Existing Core Findings Still Open

### Authenticated Forward Proxy Cannot Survive Runtime Parsing

Setup catches a parser rejection for URL userinfo, stores the full proxy in
`ANTIGRAVITY_PROXY_URL`, and writes `${ANTIGRAVITY_PROXY_URL}` to config. On the
next config load the reference expands to the credential-bearing URL, while
`parse_antigravity_config()` rejects all username/password userinfo.

The setup flow also accepts any otherwise-invalid URL if `urlsplit()` finds a
username or password, bypassing scheme, host, port, query, fragment, and
control-character validation.

### Setup Processes Inherit All Hermes Secrets

`verify_antigravity_executable()` and `probe_antigravity_models()` use a full
copy of `os.environ`. The installer subprocess inherits the environment by
default. This exposes model API keys, messaging tokens, and other profile
secrets to third-party executables. The main Antigravity session already uses
an allowlist; setup must reuse the same generic safe environment builder.

### Proxy Is Requested After Installation

When `agy` is missing, setup downloads and executes the installer before asking
for a proxy. Users who require the forward proxy cannot install. The installer
process also does not receive proxy variables.

### Session Pool Has Concurrency and Tracking Races

The pool marks an entry `busy` after releasing the global pool lock. A
concurrent acquisition at capacity can observe the new/active entry as idle,
evict it, and close a process immediately before or during a turn.

`close_session()`, idle cleanup, and shutdown remove entries before confirming
process termination and swallow close errors, so a failed termination can
leave an untracked process.

Recovery catches every `RuntimeError` or `OSError`, including provider,
permission, and protocol errors, and may repeat the same user turn. Recovery
must be limited to a confirmed dead/fatal transport state.

### Antigravity Is Registered as a Model Provider

`hermes_cli/models.py` adds `antigravity-cli` to `CANONICAL_PROVIDERS`. This
exposes it through ordinary provider/model resolution surfaces even though it
is a setup-only agent backend with no model-provider transport.

Selecting it also falls through the normal post-provider cleanup in
`select_provider_and_model()`, which can clear native Hermes
`OPENAI_BASE_URL`. This violates the requirement to preserve the native model
configuration for switching back.

### NDJSON Capacity and Redaction Review Items

The transport still has a 16 KiB stdout line limit despite official result and
tool events being able to contain full responses/large output. Its reader
queue is unbounded and there is no aggregate per-turn byte/event budget.

The common redactor is not called with URL-credential redaction enabled, so a
credential-bearing proxy URL can survive some stderr/tool paths.

## SessionDB Test Gap

The test named `test_old_db_gets_columns_on_reopen` says it strips the new
columns to simulate an old schema, but it only checks that the current schema
already contains them. It does not validate column reconciliation against a
real legacy sessions table.

Create a minimal legacy schema without the two fields, add a session row, then
open the current SessionDB and prove both fields are added without changing the
existing row.

## Verification Evidence

Committed HEAD was tested in an isolated detached worktree.

Python focused suites:

```text
443 passed, 2 skipped in 160.22s
```

Covered:

- `tests/agent/backends`
- classic CLI Antigravity tests
- TUI Antigravity tests
- gateway Antigravity tests
- `/message` auth tests
- setup/model picker tests
- SessionDB tests

Desktop slash command tests:

```text
27 passed
```

Python `compileall` completed successfully.

Desktop TypeScript typecheck was not completed because dependencies were not
installed in the checkout (`tsc` was unavailable). The correct project script
is `npm --prefix apps/desktop run typecheck`.

`git diff --check 1294af2ed0..HEAD` reported trailing blank lines in five
committed files:

- `agent/backends/setup.py`
- `hermes_cli/gateway.py`
- `tests/hermes_cli/test_antigravity_setup.py`
- `tests/hermes_cli/test_model_provider_persistence.py`
- `tests/test_hermes_state.py`

These are minor formatting failures but mean the branch does not pass its own
final static gate.

## Branch and Remote State

At review time:

- Local committed HEAD: `9c3aec3b9947c1f911147e780f7b4f56618bbd67`.
- Fork branch HEAD: `18ac72ba54c2a0eac494666f700a49fe016e267f`.
- Local branch was ahead of the fork by 10 commits.
- Local worktree contained four uncommitted modifications, including an empty
  `agent/backends/router.py`.

Do not push until the active developer resolves the dirty worktree and all
blocking findings above.

## Completion Decision

The code now covers most planned files and surfaces, but the implementation is
not production-functional on several real call paths. Green helper tests do
not offset the production config-type mismatch, missing `/message` dispatch,
dead gateway command handler, weak media boundary, or process ownership leaks.

Final decision: development is not complete and the branch must not be
deployed locally or to host 130.
