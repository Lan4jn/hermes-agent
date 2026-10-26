# Upstream sync: personalized feature port

## Objective

Bring fork `main` at `47316a9d1b` onto `NousResearch/hermes-agent` `upstream/main`
at `7b761da2de` without regressing the fork's working message API, QQBot,
Gemini/custom-provider setup, Chinese dashboard, dual-stack binding, or Windows
behavior. Do not merge, push, or deploy until the functional gates below pass.

## Baseline and risk

- Merge base: `bc86ff6c4ac8785016d0023f37ad8b119ed120de`.
- Fork-only delta: 57 commits, 115 files, about 36.7k added lines.
- Upstream-only delta: 9,161 commits, over 10k changed files.
- A normal merge reports 35 conflicted files. `-X ours` drops extracted upstream
  auth symbols (11 test setup errors); `-X theirs` creates a syntactically invalid
  auth file. Neither auto-merge candidate is safe.
- The original `main` has uncommitted edits in `gateway/platforms/api_server.py`,
  `tests/gateway/test_api_server.py`, `package-lock.json`, and API-server docs,
  plus unrelated untracked files. Never reset or overwrite those edits.

## Port order

1. Establish a clean upstream baseline and runnable test environment. Keep the
   old fork and working tree untouched. Verify upstream imports and targeted
   tests before adding local behavior; if PM downloads fail, record the network
   error and use the existing Python only for smoke tests, not GO evidence.
2. Inventory each fork-only behavior against the upstream implementation. For
   extracted facades (especially `hermes_cli/auth.py`, `gateway/run.py`, and
   `hermes_cli/update_cmd_deps.py`), port behavior into the new owning module,
   not an obsolete compatibility copy. Mark superseded fixes with an upstream
   test or runtime-path explanation.
3. Port the message API, authentication modes, remote access controls, and
   dual-stack listener. Preserve the existing host-command authorization
   contract. Verify authenticated and unauthenticated `/message` requests,
   session routing, IPv4, and IPv6 with real imports and isolated state.
4. Port QQBot document/image handling and native execution-approval buttons.
   Verify private/group ingress, safe document extraction, attachment delivery,
   and both button and text approval paths. Do not disturb deployed bot tokens.
5. Port Gemini OAuth proxy, re-login, model picker, custom-provider routing,
   and corresponding credential persistence into the upstream provider/profile
   architecture. Verify endpoint/key isolation and a mocked end-to-end
   resolution chain; do not log or copy live secrets.
6. Port Chinese dashboard strings and Windows process behavior against the
   upstream TUI/dashboard contract. Keep upstream version stamping (`0.0.0`
   package placeholder and lazy CLI version) and PM update model intact.
7. Reconcile the four original uncommitted files with their owner in the main
   checkout. Rebuild lockfiles using the upstream tooling only after source
   requirements are final. Run `scripts/run_tests.sh` on the relevant suites,
   dashboard typecheck/test/build, `git diff --check`, import probes, and
   compatibility checks. Review diff against BOTH fork `main` and upstream
   before a final merge commit.

## Exit criteria

- Every fork-specific behavior above has a source path and passing behavior test
  or a documented, equivalent upstream implementation.
- The merged source imports and the focused suites pass in the project's
  supported, isolated environment; a syntax check alone is insufficient.
- The original uncommitted user changes remain intact, and no remote service
  or `main` branch was modified during integration.
- Only after review: fast-forward/merge into local `main`, then separately ask
  for push or deployment if desired.
