# Antigravity Backend Repair Verification Report

Date: 2026-08-26
Branch: `feature/antigravity-backend`
Committed HEAD reviewed: `4e1cd4edd036499cd5612a39f534cb9b09511503`
Current worktree status: Dirty; not runnable
Decision: Not complete; do not deploy

## Required Reading and Execution Plan

The primary development plan is:

- Absolute path:
  `F:\Documents\Project\hermes-agent\.worktrees\antigravity-backend\docs\superpowers\plans\2026-08-26-antigravity-repair-plan.md`
- Repository-relative path:
  `docs/superpowers/plans/2026-08-26-antigravity-repair-plan.md`

Developers must execute that plan in task order. It defines the exact files,
red tests, minimal fixes, green tests, commit boundaries, final smoke test, and
completion criteria.

Supporting documents:

- Approved design:
  `docs/superpowers/specs/2026-08-23-antigravity-agent-backend-design.md`
- Original Phase 1 plan:
  `docs/superpowers/plans/2026-08-23-antigravity-core-cli.md`
- Original Phase 2 plan:
  `docs/superpowers/plans/2026-08-23-antigravity-interactive-surfaces.md`
- Previous completion review:
  `docs/superpowers/reviews/2026-08-25-antigravity-completion-review.md`
- Earlier handoff:
  `docs/superpowers/handoffs/2026-08-24-antigravity-backend-handoff.md`

If this report and an older document disagree, follow the 2026-08-26 repair
plan and this report.

## Executive Summary

Six repair commits substantially improved the implementation:

```text
d21965c2b5 fix: honor official Antigravity setup contract
27dfca00d4 fix: expose Antigravity as a setup-only model action
7a5402f3ab fix: enforce profile-aware config and router isolation across gateway surfaces
5066cc11b4 fix: refactor AntigravitySessionPool with leases counter and robust lifecycle
4e1cd4edd0 fix: bound transport queues and wire interrupt across gateway and tui
```

The committed HEAD passes the Antigravity focused suites, but important
lifecycle and session-invariant work remains. The active worktree contains four
uncommitted edits that currently break Python import, so the current filesystem
state is worse than the committed HEAD.

Estimated status:

- Planned code/surface coverage: 80-85%.
- Production readiness: not ready.
- Safe deployment readiness: 0% until all completion criteria pass.

## Current Worktree Blocker

Uncommitted files at review time:

```text
agent/backends/setup.py
tests/gateway/test_antigravity_backend.py
tests/tui_gateway/test_antigravity_backend.py
tui_gateway/interactive_backend.py
```

`agent/backends/setup.py` has an `IndentationError` around line 161. The
uncommitted diff also removed `build_setup_env()` and the
`install_antigravity()` function declaration while leaving their bodies.

Fresh test command against the active worktree failed during collection:

```text
IndentationError: unexpected indent
agent/backends/setup.py:161
```

Do not discard these edits without coordinating with their owner. Preserve
them in a WIP commit or patch, then continue from a clean worktree based on
`4e1cd4edd0` or the corrected WIP commit.

## Verification Evidence for Committed HEAD

The committed HEAD was tested in a separate detached audit worktree so the
dirty feature worktree was not modified.

Focused Antigravity suites:

```text
452 passed, 2 skipped in 206.91s
```

Covered:

- core backend config/transport/pool
- classic CLI
- TUI gateway bridge
- messaging gateway bridge
- `/message` auth/dispatch
- setup and model picker
- SessionDB migration/state

Cross-surface regression:

```text
660 passed, 2 failed
```

The two failures are the existing `peer_messaging` toolset expectation in
`tests/test_tui_gateway_server.py`; the Antigravity diff does not modify that
toolset. Reproduce on the base commit before marking them unrelated in final
verification.

Desktop slash command tests:

```text
27 passed
```

Python `compileall` passed. `git diff --check 1294af2ed0..HEAD` still reports
one trailing blank line in `tests/test_hermes_state.py`. Desktop TypeScript
typecheck has not been completed because `tsc` dependencies were not installed
in the checkout.

No real `agy` installation, Google AI Pro login, authenticated proxy, multi-turn
chat, QQBot/Telegram run, `/message` run, or host 130 smoke test has passed yet.

## Confirmed Repairs

The following previous blockers are fixed in committed code:

- Official installer URLs use `https://antigravity.google/cli/install.*`.
- `agy models` parsing extracts only the first model slug token.
- Empty/failed model catalog does not fall back to hardcoded models.
- Setup uses an allowlisted environment and asks for proxy before installation.
- Antigravity appears as a setup-only Google action in `hermes model` without
  becoming a canonical model provider.
- Antigravity selection is excluded from native provider cleanup.
- Gateway uses `TurnContext.user_config` when present and stores routers by
  profile.
- TUI stores a router on its session instead of a process-global singleton.
- `/message` performs API key gating and actually dispatches Antigravity turns.
- Gateway `/backend` reaches its canonical handler.
- Gateway media input uses the canonical media path validator.
- SessionDB migration test now creates a real legacy schema.
- Pool uses leases instead of a single `busy` boolean.
- Transport stdout queue is bounded and the stdout line limit permits large
  official result records.
- Router shutdown is connected to Gateway shutdown.

## Remaining Blocking Findings

### 1. Media Paths Never Reach `agy`

Gateway validates and stores paths in `BackendTurnRequest.media_paths`, but
`AntigravitySession.run_turn()` sends only `request.text`. The file/image paths
are never rendered into the NDJSON user content.

Required repair-plan task: **Task 6**.

Required behavior: append only canonical-policy-approved paths as a bounded
text attachment list. Rejected paths must not appear in prompt or logs.

### 2. Interrupt Helpers Are Not Connected to Production Chokepoints

`interrupt_tui_interactive_backend_turn()` and `interrupt_gateway_turn()`
exist, but committed CLI/TUI/Gateway interrupt handlers do not call them.
Direct helper tests pass while real interrupt still targets only AIAgent.

Required repair-plan task: **Task 5**.

Required behavior: resolve the effective backend at the existing interrupt
chokepoint, route Antigravity to the owning router/pool, and preserve native
Hermes behavior unchanged.

### 3. Pool Close Failures Still Lose Tracking

Leases fixed active/waiter eviction, but `close_session()` and idle/shutdown
cleanup still remove entries before close success and swallow close errors.
Failed process-tree termination can therefore leave an untracked `agy`.

Required repair-plan task: **Task 4**.

Required behavior: remove the entry only after confirmed close. On failure,
retain the entry and return/raise an actionable safe error.

### 4. Recovery Is Still Too Broad

`run_turn()` catches `RuntimeError`/`OSError` and recovers whenever the session
reports dead. Provider/protocol failures can also mark the session dead after
the user event was accepted, so replay may submit the same turn twice.

Required repair-plan task: **Task 4**.

Required behavior: recover only a classified confirmed transport-death state;
never retry permission, model, protocol, or terminal-result errors.

### 5. Gateway Profile Identity Is Incomplete

Gateway now accepts `ctx.user_config`, but the router key still derives profile
from `runner.profile_name`, which is not a reliable per-turn identity in a
multiplexed gateway. Two profiles may share the `default` key even when their
configs differ.

Required repair-plan task: **Task 3**.

Required behavior: derive the key from the turn/request profile already stamped
on the source/context and prove two profiles receive different router/pool
instances.

### 6. Transport Resource and Redaction Work Is Partial

The stdout queue is bounded, but:

- stderr writes can still block on a full queue;
- queue-full error delivery can fail silently and degrade to timeout;
- no aggregate per-turn event/byte budget exists;
- the common redactor is not called with URL credential redaction enabled.

Required repair-plan task: **Task 5**.

### 7. Session/Transcript/Resume Invariants Are Not Complete

There is no complete E2E proof that each Antigravity turn writes exactly one
user and assistant message, resumes the persisted backend conversation ID,
uses the session cwd, closes the old process on `/new`, and inherits the
platform/global default for the new session.

Required repair-plan task: **Task 6**.

## Task Status Against Repair Plan

Primary plan:
`docs/superpowers/plans/2026-08-26-antigravity-repair-plan.md`

| Task | Status | Required next action |
|---|---|---|
| 1. Official setup contract | Committed and focused tests pass | Preserve; include in real installer/login smoke |
| 2. setup-only model action | Committed and focused tests pass | Preserve; verify real interactive picker |
| 3. profile-aware config | Partial | Fix per-turn profile identity and two-profile E2E |
| 4. pool lifecycle | Partial | Retain failed closes; classify recovery |
| 5. transport/interrupt | Partial | Connect real interrupt; add budgets and URL redaction |
| 6. media/transcript/resume | Not complete | Implement all invariants and E2E |
| 7. final validation/smoke | Not started | Run only after Tasks 3-6 pass review |

## Required Development Method

For each remaining task:

1. Start from a clean, preserved worktree.
2. Write a failing test that reproduces the production object/call path.
3. Run it and record the expected red failure.
4. Implement the smallest shared fix; do not add another router/provider/helper
   when an existing owner can be corrected.
5. Run focused green tests and sibling regressions.
6. Commit only that task.
7. Run specification compliance review.
8. Run code quality/security/concurrency review.
9. Resolve all Critical and Important findings before the next task.

Do not accept tests that replace `GatewayConfig`, `TurnContext`, profile scope,
or API adapter construction with incompatible dict/MagicMock shapes when the
bug concerns those exact boundaries.

## Final Acceptance Commands

Focused suites:

```powershell
python -m pytest tests/agent/backends tests/cli/test_antigravity_backend.py tests/tui_gateway/test_antigravity_backend.py tests/gateway/test_antigravity_backend.py tests/gateway/test_antigravity_message_auth.py tests/hermes_cli/test_antigravity_setup.py tests/hermes_cli/test_model_provider_persistence.py tests/test_hermes_state.py -q
```

Cross-surface regression:

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

1. Official installer through configured forward proxy.
2. AI Pro `agy auth login` and `agy models` with no fallback.
3. CLI and TUI two-turn PID/conversation reuse.
4. Interrupt and `/new` process-tree cleanup.
5. Safe QQBot/Telegram file and image references visible to Antigravity.
6. `/message` unauthenticated 401 before spawn; authenticated two-turn context.
7. `/backend hermes` switch-back with native model config intact.
8. Gateway restart/resume with persisted conversation ID.
9. No orphan `agy` after CLI/TUI/Gateway shutdown.
10. Repeat on Windows local host and host 130 before deployment approval.

## Branch State

At report time:

- Local committed HEAD: `4e1cd4edd036499cd5612a39f534cb9b09511503`.
- Local branch is 18 commits ahead of fork.
- Four additional files are dirty and currently break setup import.
- None of these latest commits/fixes have been pushed to the fork.

Do not push or deploy until the dirty worktree is resolved, Tasks 3-6 are
complete, both review gates pass, and the real smoke checklist succeeds.
