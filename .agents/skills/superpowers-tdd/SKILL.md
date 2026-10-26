---
name: superpowers-tdd
description: >-
  Test-Driven Development (TDD) workflow from Superpowers (obra/superpowers).
  Enforces writing tests first (Red), passing minimal code (Green), and refactoring cleanly (Refactor).
  Use whenever adding new features, fixing bugs, or implementing robust invariants.
---

# Superpowers: Test-Driven Development (TDD)

Strict, disciplined Test-Driven Development ensures high correctness, prevents regressions, and produces modular code.

## The TDD Iron Law

> **Never write implementation code without a failing test first.**

## The 3-Phase Loop

### Phase 1: Red (Write Failing Test)
1. Identify the exact requirement, invariant, or bug.
2. Write a minimal, focused test expressing the expected contract.
3. Run the test to confirm it fails for the **exact expected reason** (not due to syntax error or wrong import).

### Phase 2: Green (Make It Pass)
1. Write the simplest possible implementation that satisfies the test.
2. Run the test suite to verify it turns green.
3. Keep the change narrow and directly traced to the test requirement.

### Phase 3: Refactor (Clean and Generalize)
1. Clean up code duplication, improve readability, modularize.
2. Rerun the full test suite to guarantee zero regression.
3. Verify edge cases (empty inputs, timeouts, concurrency, boundary conditions).
