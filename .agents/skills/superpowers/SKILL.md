---
name: superpowers
description: >-
  Superpowers Software Engineering Suite: Rigorous, disciplined engineering workflows including
  Test-Driven Development (TDD), Systematic Debugging, Architecture Planning, Code Review,
  and Subagent Orchestration (adapted from obra/superpowers).
  Use whenever the user asks for superpowers, rigorous engineering, TDD, systematic debugging,
  or disciplined code implementation.
---

# Superpowers Engineering Suite

The Superpowers Suite enforces professional software engineering discipline across all coding tasks:

## Core Workflows

### 1. Test-Driven Development (TDD)
- **Red**: Write a minimal failing test asserting required behavior or invariant before writing implementation.
- **Green**: Implement the simplest working code that makes the test pass.
- **Refactor**: Clean up implementation without altering behavior, preserving 100% test pass rate.

### 2. Systematic Debugging
- **Isolate & Reproduce**: Confirm reproduction with minimal command/script.
- **Formulate Hypotheses**: Trace root cause down to exact line/boundary before editing.
- **Verify Fix**: Ensure fix eliminates the entire bug class without collateral damage.
- **Regression Prevention**: Add tests to ensure bug never re-occurs.

### 3. Implementation Planning
- **Design Intent**: Document problem, trade-offs, architecture decisions.
- **Incremental Steps**: Break complex work into verifiable milestones.
- **Pre-execution Verification**: Verify assumptions against codebase before writing code.

### 4. Code Review & Verification
- **Behavior Contracts**: Assert data relationships and invariants.
- **Security Boundaries**: Validate input sanitization, error propagation, resource leaks.
- **Cache & Performance**: Preserve performance properties and prompt caching.
