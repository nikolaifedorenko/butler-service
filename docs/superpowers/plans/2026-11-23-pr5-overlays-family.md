# Overlay Ownership and Family Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure Escape closes one topmost overlay and current/former family relationships are deterministic.

**Architecture:** Core owns an explicit overlay stack with close and focus-return callbacks. Kinship candidate ranking prefers active paths; former-only paths remain displayable but are excluded from active composition.

**Tech Stack:** JavaScript/lit-html, Python domain functions, pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-23-pr224-238-remediation-design.md`

## Global Constraints

- One Escape closes exactly one overlay.
- Former relatives remain in family history but not active booking composition.
- Current relation paths always outrank former-only alternatives.

## Review Focus

- Modal → drawer → Escape leaves modal open and restores focus correctly.
- Modal → palette behaves the same way.
- Direct former spouse/partner is marked `via_former=True`.
- Current and former routes to one person select the current title/path.
- A former spouse's relatives cannot be added through active-family composition.

---

### Task 1: Central overlay stack

**Files:**
- Modify: `static/js/core.js`
- Modify: `static/js/ui/palette.js`
- Modify: `static/js/modules/stays_forms.js`
- Modify: `e2e/stays-forms.spec.mjs`
- Modify: `e2e/palette.spec.mjs`

**Interfaces:**
- Produces: `pushOverlay(id, close, returnFocus)`, `removeOverlay(id)`, and one document Escape handler that closes only the stack top.

- [ ] Add modal/drawer/palette nesting tests with repeated Escape and focus restoration.
- [ ] Run tests and reproduce simultaneous modal/drawer closure.
- [ ] Implement stack registration for modal, drawer, and palette; remove competing Escape handlers.
- [ ] Run targeted Playwright tests and confirm PASS.
- [ ] Commit with `fix(ui): close only the topmost overlay`.

### Task 2: Deterministic former/current kinship

**Files:**
- Modify: `app/modules/guests/domain/kinship.py`
- Modify: `app/modules/guests/application/family.py`
- Modify: `tests/guests/test_kinship.py`
- Modify: `tests/guests/test_guests_api.py`
- Modify: `tests/stays/test_mine_edit.py`

**Interfaces:**
- Produces: candidate ordering `(degree, via_former, path_length, person_id)` with active paths before former paths; `relatives_among` excludes former-only results.

- [ ] Add domain tests for direct former spouse/partner, current+former alternate paths, and correct spouse-vs-partner labels.
- [ ] Change the contradictory composition test to expect former-only rejection.
- [ ] Run tests and confirm current failures.
- [ ] Update candidate construction/ranking and active-composition filtering without removing former history from family output.
- [ ] Run `pytest tests/guests/test_kinship.py tests/guests/test_guests_api.py tests/stays/test_mine_edit.py -q` and confirm PASS.
- [ ] Commit with `fix(guests): prefer active family relationships`.

## PR Completion Gate

- [ ] Run repository baseline checks required by CI, push the branch, and open the PR with overlay/kinship evidence.
- [ ] Wait for every required CI check; diagnose and fix failures on the same branch.
- [ ] Merge only when CI is green, then update from main before starting PR 6.

