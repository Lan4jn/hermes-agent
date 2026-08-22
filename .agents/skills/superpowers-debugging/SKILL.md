---
name: superpowers-debugging
description: >-
  Systematic Debugging workflow from Superpowers (obra/superpowers).
  Disciplined root-cause diagnosis, reproducible test cases, hypothesis testing, and regression-proof fixes.
  Use whenever diagnosing unexpected failures, crashes, test breaks, or race conditions.
---

# Superpowers: Systematic Debugging

Avoid trial-and-error shotgun debugging. Follow an evidence-based, hypothesis-driven workflow.

## 4-Step Systematic Process

### 1. Reproduce & Isolate
- Create a minimal reproduction script, test case, or command line.
- Confirm the bug reproduces deterministically on current `main`.
- Isolate whether the failure is environmental, configuration-based, or logic-driven.

### 2. Formulate & Test Hypotheses
- Trace the data flow to the exact line where the invariant breaks.
- State a testable hypothesis: *"The symptom occurs because function X assumes Y when Z happens."*
- Inspect stack traces, variables, or logs to validate the hypothesis before editing.

### 3. Apply Minimal & General Fix
- Address the root cause for the entire bug class, not just the single manifestation point.
- Avoid workarounds that hide symptoms or disable existing capabilities.

### 4. Verify & Prevent Regressions
- Run unit/integration tests to confirm the fix works.
- Add an automated regression test covering this specific failure mode and sibling branches.
