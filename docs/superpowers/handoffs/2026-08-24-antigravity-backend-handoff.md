# Antigravity Backend Development Handoff

Date: 2026-08-24
Branch: `feature/antigravity-backend`
Worktree: `F:\Documents\Project\hermes-agent\.worktrees\antigravity-backend`
Current HEAD: `cd83a24fe46f423228766ab7955000d1b159071e`
Status: In progress; do not deploy

## Objective

Add Google Antigravity CLI as an optional interactive agent backend. Hermes
continues to own CLI/TUI/Desktop/Dashboard/QQBot/Telegram/`/message` transport,
session routing, and management. Antigravity runs through Google's official
long-lived Headless NDJSON protocol and uses AI Pro account authentication.

Cron, batch, auxiliary, compression, and unattended tasks stay on native
Hermes in the first release.

## Source Documents

- Design:
  `docs/superpowers/specs/2026-08-23-antigravity-agent-backend-design.md`
- Phase 1 plan:
  `docs/superpowers/plans/2026-08-23-antigravity-core-cli.md`
- Phase 2 plan:
  `docs/superpowers/plans/2026-08-23-antigravity-interactive-surfaces.md`

The design and both plans are committed. Read them before continuing.

## Approved Product Decisions

- Antigravity is an interactive **agent backend**, not a fake OpenAI model
  provider and not a reverse-engineered Google HTTP client.
- All interactive surfaces eventually support `/backend hermes` and
  `/backend antigravity`.
- `hermes model -> Google Gemini` includes `Google Antigravity CLI (AI Pro)`
  and starts a dedicated setup flow.
- Existing `model.provider` and `model.default` remain untouched and are used
  when switching back to Hermes.
- Hermes may install `agy` only in an explicit interactive setup flow and only
  after confirmation. Ordinary turns and gateway startup never install code.
- AI Pro authentication stays in the `agy`-managed OS keyring. Hermes never
  reads or stores Antigravity OAuth tokens.
- Custom networking uses a standard HTTP/HTTPS **forward proxy**, not a custom
  Antigravity base URL. Proxy env is injected only into the `agy` child.
- QQBot/Telegram require the existing allowlisted identity before trusted
  Antigravity host access.
- Every `/message` Antigravity turn requires valid `API_SERVER_KEY` auth in all
  permission modes and must reject before starting `agy`.
- Permission modes are `strict`, `sandbox`, and `trusted`. `trusted` maps to
  `--dangerously-skip-permissions` only for an authenticated principal.
- Host 130 currently runs Hermes as root, so trusted Antigravity there also
  inherits root. Setup/status must warn explicitly.

## Completed and Accepted Work

### Task 1: Configuration and Backend Contracts

Status: Complete; passed specification and quality review.

Files:

- `agent/backends/__init__.py`
- `agent/backends/base.py`
- `agent/backends/hermes.py`
- `agent/backends/config.py`
- `hermes_cli/config_defaults.py`
- `tests/agent/backends/test_router.py`

Delivered:

- Immutable backend turn request/result/event contracts.
- Native Hermes callable wrapper without copying the `AIAgent` loop.
- Backend resolution order:
  session override > platform override > global default > Hermes.
- Fail-closed backend and permission parsing.
- Strict Antigravity config type/range validation.
- Strict proxy URL validation, including safe DNS/IPv4/IPv6/scoped IPv6.
- JSON-compatible recursively frozen usage values.
- Existing behavior remains `hermes`; Antigravity remains disabled by default.

Final focused evidence: 79 backend tests passed; quality reviewer reported no
Critical or Important findings. One accepted minor remains: `usage` accepts
non-finite float values and cyclic containers currently end in a recursion
error. This does not affect normal usage payloads but can be tightened later.

Task 1 commits:

```text
7d9c6be0f0 feat: define interactive agent backend config
19c4f0fee6 fix: harden Antigravity proxy URL validation
0f5b9f01cb fix: enforce immutable backend config contracts
8d1ab17536 fix: finalize backend data boundary validation
```

## Task 2: Antigravity NDJSON Session

Status: In progress; WIP saved, not accepted.

Files:

- `agent/backends/antigravity.py`
- `tests/fixtures/fake_agy.py`
- `tests/agent/backends/test_antigravity.py`
- export additions in `agent/backends/__init__.py`

Committed history:

```text
5eeda10262 feat: add Antigravity headless transport
069a1fc764 fix: harden Antigravity session protocol
cd83a24fe4 wip: address Antigravity transport review
```

The WIP commit intentionally preserves unfinished work. Do not treat its
presence as completion.

### Problems Found in the First Task 2 Review

These findings were fixed before `069a1fc764` and passed specification
re-review:

- Removed automatic process restart/resume from the session class; pool owns
  recovery in Task 3.
- Removed unreliable prefix-based text-delta guessing.
- Bounded/redacted malicious terminal statuses.
- Redacted stderr before storing it in memory.
- Kept a live process reference and raised when termination could not be
  confirmed.

### Problems Found in the Task 2 Quality Review

The quality reviewer found that the green fake tests did not match the real
official protocol. These findings drove the current WIP:

1. **Critical: official event schema mismatch.**
   Official shapes are:

   ```json
   {"event":"init","conversation_id":"...","init":{}}
   {"event":"step_update","step_update":{"step_index":1,"state":"ACTIVE","step_type":"agent_response","text_delta":"..."}}
   {"event":"result","result":{"status":"SUCCESS","response":"...","usage":{}}}
   ```

   The old fake/parser used invented `step`, `type`, and top-level result
   fields. The WIP rewrites fake and parser to official `step_update`,
   `step_type`, `tool_info`, and nested `result` payloads. Keep an independent
   literal official-doc fixture test so fake and parser cannot drift together.

2. **Critical: child inherited the entire Hermes environment.**
   The WIP introduces an explicit runtime allowlist and adds only the four
   configured proxy variables. Never revert to `os.environ.copy()`: it leaks
   model API keys, messaging tokens, and other Hermes credentials to `agy` and
   its tools.

3. **Important: close/spawn TOCTOU race.**
   Lifecycle checks, spawn assignment, and close need one state lock. A close
   racing first spawn must not leave `_closed=True` with a live child.

4. **Important: terminate the process tree, not only direct `agy`.**
   Antigravity tools may spawn children. Use the repository's cross-platform
   process-tree pattern, a POSIX process group, and Windows process-group/tree
   termination. Reader threads must exit within a bound.

5. **Important: redact URL credentials.**
   Call the common redactor with `redact_url_credentials=True`. A proxy like
   `https://user:PROXY_SECRET_MARKER@host` must never survive stderr/tool/error
   handling.

6. **Important: protocol capacity.**
   A 16 KiB line limit rejects legitimate full result/tool events. The WIP uses
   a much larger bounded line limit plus per-turn byte/event budgets and a
   bounded reader queue. Retain both per-line and aggregate bounds.

7. **Important: every official `text_delta` is incremental.**
   Emit every non-empty fragment exactly once. Do not suppress a DONE fragment
   merely because its text equals an earlier fragment.

8. **Important: omit empty `--model`.**
   Add model/effort argv only when non-empty.

9. **Important: bounded queue and event/byte budgets.**
   Many small events must not grow memory without bound.

10. **Minor: expose read-only `alive` and `fatal` state for Task 3.**

### Current WIP Test State

Fresh command on `cd83a24fe4`:

```powershell
python -m pytest tests/agent/backends/test_antigravity.py tests/agent/backends/test_router.py -q
```

Result:

```text
114 passed, 4 failed
```

Remaining failures:

1. `test_close_is_idempotent_and_reaps_process`
   - Test expects `session._reader_threads`, but implementation currently lacks
     the tracked reader-thread collection/contract.

2. `test_close_retains_live_process_and_raises_when_kill_fails`
   - Expected process-tree helper calls are zero. The helper is not actually
     wired into the termination path.

3. `test_close_terminates_real_parent_and_child_process_tree`
   - Parent exits, spawned fake child remains alive at assertion time. The test
     process later exited, but termination is not deterministic or bounded.

4. `test_windows_hide_flags_passed_at_spawn`
   - Windows creation flags contain hidden-window `0x08000000` but not
     `CREATE_NEW_PROCESS_GROUP` (`0x00000200`).

The interrupted implementation agent stopped because its model endpoint
returned HTTP 503 (`no available account`), not because of a code/design
question.

### Immediate Next Steps for Task 2

1. Read current `antigravity.py` and the four failing tests.
2. Find and reuse the existing repository cross-platform process-tree helper.
   If it cannot satisfy group/tree termination, extend the shared generic
   helper rather than special-casing Antigravity in multiple places.
3. Add POSIX independent process session/group at spawn.
4. Combine Windows `windows_hide_flags()` with
   `CREATE_NEW_PROCESS_GROUP` without removing hidden-window behavior.
5. Track stdout/stderr reader threads and join them with a bounded deadline
   after the full tree exits.
6. Ensure failed tree termination retains the process reference and reports a
   safe error.
7. Run the target suite until all tests pass.
8. Re-run independent specification review and quality review. The prior
   quality review must not be considered passed.

Do not start Task 3 until Task 2 passes both reviews.

## Remaining Phase 1 Work

After Task 2 acceptance, execute in order:

1. Task 3: session pool, capacity, LRU idle eviction, one-time recovery.
2. Task 4: SessionDB `agent_backend` and `backend_conversation_id` fields.
3. Task 5: official installer/login/models/forward-proxy setup and status.
4. Task 6: `hermes model` Google/Antigravity entry without changing native
   model config.
5. Task 7: shared router plus classic CLI `/backend` consumer.
6. Task 8: Phase 1 regression and real Windows smoke test.

Then execute the separate Phase 2 plan for TUI/Desktop/Dashboard/gateway and
`/message` authorization.

## Baseline and Known Unrelated Failures

Before implementation, the focused baseline passed:

```text
332 passed, 2 skipped
```

The broader Windows config suite has existing failures unrelated to this
branch:

- A default Hermes home test expects `~/.hermes`, while current Windows behavior
  uses `%LOCALAPPDATA%\hermes`.
- Some tests read UTF-8 config files using the GBK locale without specifying
  `encoding="utf-8"`.

Do not hide new failures under these known failures. Use precise deselection
only when reproducing the same baseline issue on the unchanged base.

## Verification Commands

Task 2:

```powershell
python -m pytest tests/agent/backends/test_antigravity.py tests/agent/backends/test_router.py -q
python -m compileall -q agent/backends tests/fixtures/fake_agy.py
git diff --check
```

Phase 1 final:

```powershell
python -m pytest tests/agent/backends tests/hermes_cli/test_antigravity_setup.py tests/hermes_cli/test_model_provider_persistence.py tests/cli/test_antigravity_backend.py tests/test_hermes_state.py -q
python -m compileall -q agent/backends hermes_cli cli.py hermes_state.py
git diff --check
```

## Repository State at Handoff

- Feature work is isolated in `.worktrees/antigravity-backend`.
- Main checkout and the existing `.worktrees/hermes-manager` worktree must not
  be modified or cleaned up as part of this task.
- Nothing from this Antigravity branch has been deployed locally or to host
  130.
- The earlier Gemini interactive-proxy feature is a separate deployed branch
  and must not be reverted.
- Push this branch only when the new owner is ready; no Pull Request was
  requested.
