---
name: superpowers-review
description: >-
  Systematic Code Review & Verification workflow from Superpowers (obra/superpowers).
  Examines correctness, invariant preservation, API contracts, security boundaries, and cache preservation.
  Use whenever reviewing PRs, diffs, or validating changes before merge.
---

# Superpowers: Code Review & Verification

Rigorous checklist to verify code changes against system contracts and invariants.

## Review Dimensions

### 1. Intent & Premise Verification
- Does the change solve the actual reported problem, or is it built on a mistaken assumption?
- Is an intentional design pattern or isolation boundary being compromised?

### 2. Behavioral Invariants
- Are message role alternation, prompt caching, and session contexts preserved?
- Are error states handled gracefully without swallowing exceptions or corrupting shared state?

### 3. Footprint & Cleanliness
- Does the change follow the Footprint Ladder (least surface area)?
- Are mocks limited to I/O boundaries while exercising real resolution paths?

### 4. Cross-Platform Compatibility
- Does it work reliably across Windows (`cmd`/`pwsh`/locking) and POSIX (Linux/macOS)?
- Are paths, process lifecycle, signal handling, and file encodings handled portably?
