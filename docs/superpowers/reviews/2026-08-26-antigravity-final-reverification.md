# Antigravity Backend Final Re-verification Report

Date: 2026-08-26
Branch: `feature/antigravity-backend`
Committed HEAD reviewed: `869f49b2ce416800ff7254e65b885858d40518ac`
Current worktree: Dirty and syntactically invalid
Decision: Core transport works; remaining lifecycle work blocks deployment

## Primary Development Plan

Developers must execute the remaining work from this plan:

- Absolute path:
  `F:\Documents\Project\hermes-agent\.worktrees\antigravity-backend\docs\superpowers\plans\2026-08-26-antigravity-repair-plan.md`
- Repository-relative path:
  `docs/superpowers/plans/2026-08-26-antigravity-repair-plan.md`

The plan contains exact file scopes, failing tests, minimal implementation
steps, verification commands, commit boundaries, and final smoke criteria.

Supporting documents:

- Approved architecture:
  `docs/superpowers/specs/2026-08-23-antigravity-agent-backend-design.md`
- Previous verification:
  `docs/superpowers/reviews/2026-08-26-antigravity-repair-verification.md`
- Original completion review:
  `docs/superpowers/reviews/2026-08-25-antigravity-completion-review.md`
- Phase 1 plan:
  `docs/superpowers/plans/2026-08-23-antigravity-core-cli.md`
- Phase 2 plan:
  `docs/superpowers/plans/2026-08-23-antigravity-interactive-surfaces.md`

If older documents conflict, follow the 2026-08-26 repair plan and this
report.

## Executive Summary

Five additional repair commits completed most of Tasks 3-6:

```text
c58f67bb6b fix: scope Antigravity routers to dynamic request profiles
fa4a9e5045 fix: enforce strict pool close tracking and error recovery
dbc9d5225f fix: wire production interrupt chokepoints and enforce transport budgets
cccefcfdbe fix: inject validated media paths and guarantee session invariants
869f49b2ce fix: polish pool error handling syntax and trim EOF blank line
```

The committed backend now passes focused tests and a real local `agy`
two-turn NDJSON smoke test. The core adapter is operational. Deployment is
still blocked by incomplete Gateway interrupt wiring, restart/resume state,
some pool failure tracking, and the current uncommitted syntax damage.

Estimated completion:

- Committed feature implementation: 92-95%.
- Deployment readiness: not ready.

## Current Worktree Blocker

The only uncommitted file at review time was:

```text
agent/backends/pool.py
```

Its uncommitted diff removes parts of the fatal recovery condition,
`close_session()` control flow, and the `shutdown()` declaration. Fresh
`py_compile` fails:

```text
IndentationError: unexpected indent
agent/backends/pool.py:85
```

Do not commit this diff. Coordinate with its owner and preserve it before
returning to the clean committed implementation at `869f49b2ce` or applying a
corrected replacement.

## Verified Completed Work

### Official Setup Contract

- Installer URLs use `https://antigravity.google/cli/install.ps1` and `.sh`.
- Setup prompts for proxy before download/install.
- Installer, version, auth, and model probe use the environment allowlist.
- `agy models` parses only the model slug token.
- Empty/failed model catalog cancels setup with no fallback model.
- Authenticated proxy values are stored through the `.env` reference path.

### setup-only `hermes model` Action

- Antigravity is not a canonical model provider.
- Google submenu adds an `antigravity-cli` setup-only action.
- Antigravity selection is excluded from native provider cleanup.
- Native Hermes model configuration remains available for switch-back.

### Profile-aware Router Ownership

- Gateway consumes `TurnContext.user_config` instead of converting
  `GatewayConfig` Enum-key dictionaries.
- Gateway routers are stored by dynamic request profile.
- TUI owns its router on the session.
- `/message` loads profile-scoped config and requires API key authorization
  before Antigravity spawn.

### Transport and Session Behavior

- Official NDJSON event structure is parsed.
- `agy` processes are long-lived per backend session.
- stdout queue is bounded.
- per-turn event and byte budgets exist.
- URL credentials are redacted.
- process trees are terminated cross-platform.
- CLI and TUI interrupt support exists.
- safe media paths are appended to the Antigravity text prompt.
- Gateway two-turn tests prove one user/assistant pair per turn.
- SessionDB stores backend and conversation ID.

## Remaining Blocking Tasks

The exact execution steps are in the primary repair plan. Remaining work maps
to these tasks.

### Repair Plan Task 4: Finish Pool Failure Tracking

Current committed `close_session()` removes the entry only after direct close
success, but idle cleanup, fatal release, recovery failure, and shutdown still
contain paths that remove/clear entries before a confirmed close and swallow
termination errors.

Required implementation method:

1. Add red tests where `AntigravitySession.close()` remains alive and raises.
2. Assert the pool retains the entry/PID for operator retry.
3. Apply the same close-then-CAS-remove helper to explicit close, idle cleanup,
   fatal release, recovery cleanup, eviction, and shutdown.
4. Never hold the global pool lock while waiting for process termination.
5. Run pool + transport tests and commit this task alone.

### Repair Plan Task 5: Wire Gateway Interrupt Chokepoint

`interrupt_gateway_turn()` exists but no production Gateway stop/interrupt
handler invokes it. CLI and TUI are wired; Gateway remains helper-only.

Required implementation method:

1. Add an E2E through the actual Gateway `/stop` or active-turn interrupt
   dispatch, not a direct helper call.
2. Resolve the active session/profile/platform from the same turn context used
   by `run_gateway_interactive_turn()`.
3. Call router interrupt for Antigravity and preserve native AIAgent interrupt
   unchanged for Hermes.
4. Prove the fake `agy` process tree exits and no orphan remains.

### Repair Plan Task 6: Restore Persisted Conversation on Restart/Resume

Committed code persists `backend_conversation_id` but a newly constructed
router/pool does not read that value before creating `AntigravitySession`.
After CLI/TUI/Gateway restart, the first new `agy` process therefore starts a
fresh conversation instead of adding `--conversation <stored-id>`.

Required implementation method:

1. Add restart/resume E2E: complete a turn, destroy router/pool, construct a
   new router against the same SessionDB, submit another turn.
2. Assert fake `agy` argv includes the stored conversation ID.
3. Load backend override and conversation ID at pool entry creation.
4. Keep transcript persistence single-owner; assert no duplicate messages.
5. Verify `/new` closes the old process and intentionally starts without the
   old conversation ID while inheriting platform/global backend default.

### Repair Plan Task 7: Complete Final Validation and Deployment Smoke

No deployment is allowed until this task passes.

Required work:

- Desktop TypeScript typecheck.
- Real CLI and TUI multi-turn tests.
- Real Gateway/QQBot/Telegram message test.
- Real `/message` 401 and authenticated two-turn test.
- Gateway restart/resume test.
- Local and host 130 process cleanup check.
- Two-stage specification and code quality review.
- Clean worktree and local/remote SHA verification.

## Automated Verification Evidence

Committed HEAD was tested in a separate detached audit worktree.

Focused suites:

```text
460 passed, 2 skipped in 214.65s
```

Cross-surface regression:

```text
660 passed, 2 failed
```

The two failures are the existing `peer_messaging` toolset expectation in
`tests/test_tui_gateway_server.py`; the Antigravity commits do not modify that
toolset. Reproduce against the feature base before classifying them as
unrelated in final sign-off.

Desktop slash command tests:

```text
27 passed
```

Python `compileall` and committed-range `git diff --check` passed.

Desktop TypeScript typecheck remains outstanding.

## Real `agy` Verification Evidence

Local installation:

```text
agy version: 1.1.20
model catalog: 14 model slugs
```

Official one-shot Headless request:

```json
{
  "status": "SUCCESS",
  "response": "OK\n",
  "conversation_id": "569ecfe4-bfed-4bfc-8040-f294af5c1819"
}
```

Hermes `AntigravitySession` real two-turn NDJSON smoke:

```text
turn 1: ONE
turn 2: TWO
conversation ID identical across both turns
same live PID during turns
PID after close: None
```

This proves the core transport, official event parser, model selection,
multi-turn process reuse, and normal close path work against real `agy`.

It does not prove Gateway interrupt, persisted restart/resume, messaging
platform delivery, authenticated `/message`, or host 130 behavior.

## Required Development Workflow

Use the primary repair plan and Superpowers discipline:

1. Preserve and resolve the current dirty `pool.py`; never reset someone else's
   work without approval.
2. One remaining task at a time.
3. Write a production-path failing test first.
4. Run and record the red failure.
5. Implement the smallest shared fix.
6. Run focused and sibling green tests.
7. Commit only that task.
8. Run specification compliance review.
9. Run code quality/security/concurrency review.
10. Resolve all Critical/Important findings before continuing.

Tests must use real `GatewayConfig`, `TurnContext`, SessionDB, profile scope,
and subprocess protocol where those boundaries are under test. Do not replace
the exact failing boundary with an incompatible dict or MagicMock.

## Final Acceptance Commands

Focused suites:

```powershell
python -m pytest tests/agent/backends tests/cli/test_antigravity_backend.py tests/tui_gateway/test_antigravity_backend.py tests/gateway/test_antigravity_backend.py tests/gateway/test_antigravity_message_auth.py tests/hermes_cli/test_antigravity_setup.py tests/hermes_cli/test_model_provider_persistence.py tests/test_hermes_state.py -q
```

Cross-surface suites:

```powershell
python -m pytest tests/hermes_cli/test_commands.py tests/cli/test_cli_retry.py tests/test_tui_gateway_server.py tests/gateway/test_stream_events.py tests/gateway/test_turn_lease.py tests/agent/backends/test_noninteractive_isolation.py -q
```

Static/Desktop:

```powershell
python -m compileall -q agent/backends tui_gateway gateway hermes_cli cli.py hermes_state.py
git diff --check
npx vitest run apps/desktop/src/lib/desktop-slash-commands.test.ts
npm --prefix apps/desktop install
npm --prefix apps/desktop run typecheck
```

Real smoke checklist:

1. CLI two turns and interrupt.
2. TUI two turns and interrupt.
3. QQBot/Telegram allowed-user turn with safe file/image.
4. `/message` without key returns 401 before spawn.
5. `/message` with key keeps two-turn context.
6. `/new` starts a fresh conversation.
7. Gateway restart resumes stored conversation ID.
8. `/backend hermes` restores native behavior and config.
9. All shutdown paths leave no orphan `agy`.
10. Repeat on Windows local and host 130.

## Branch State

At report time:

- Local committed HEAD: `869f49b2ce416800ff7254e65b885858d40518ac`.
- Local branch is 24 commits ahead of fork.
- `agent/backends/pool.py` has one uncommitted, syntactically invalid diff.
- Latest commits are not pushed to the fork.

Do not push or deploy until the dirty pool file is resolved, Tasks 4-7 pass,
both review gates approve, and the complete real smoke checklist succeeds.
