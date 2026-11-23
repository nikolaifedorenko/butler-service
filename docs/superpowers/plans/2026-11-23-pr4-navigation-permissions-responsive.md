# Navigation, Permissions, and Responsive Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix responsive menus/filters and make Guests navigation exactly match backend capabilities.

**Architecture:** Geometry is measured after rendering, event ownership uses closest/currentTarget, and guest capabilities are centralized server-side and mirrored in UI predicates.

**Tech Stack:** JavaScript/lit-html, CSS, FastAPI permissions, pytest, Playwright/axe.

**Spec:** `docs/superpowers/specs/2026-11-23-pr224-238-remediation-design.md`

## Global Constraints

- `stays.guests` grants full directory without `stays.view`.
- `stays.edit` or `stays.mine_guest_edit` grants create UI/API.
- Every visible action must be accepted by its endpoint.

## Review Focus

- Car menu near every viewport edge remains reachable.
- Scrolling inside an open menu does not close it.
- Clicking nested chip counts updates the button's ARIA state.
- FAB never covers the mobile tab bar/safe area.
- Custom permission combinations produce consistent menu, controls, and API status.

---

### Task 1: Car menu geometry and accessibility

**Files:**
- Modify: `static/js/modules/cars.js`
- Modify: `static/css/app.css`
- Modify: `e2e/night-cars.spec.mjs`
- Modify: `e2e/a11y.spec.mjs`

**Interfaces:**
- Produces: viewport-clamped popup positioning after visible render and keyboard-operable menu semantics.

- [ ] Add edge-position, internal-scroll, Escape, arrow/tab, and open-state axe tests.
- [ ] Run them and confirm current failures.
- [ ] Implement post-render measurement, scroll ownership, roles/focus, and close behavior.
- [ ] Run targeted Playwright tests and confirm PASS.
- [ ] Commit with `fix(cars): keep action menus accessible onscreen`.

### Task 2: Mobile filters and FAB

**Files:**
- Modify: `static/js/modules/stays_filters.js`
- Modify: `static/js/modules/stays.js`
- Modify: `static/css/components.css`
- Modify: `e2e/stays-core.spec.mjs`
- Modify: `e2e/mobile.spec.mjs`

**Interfaces:**
- Produces: button-owned chip state and safe-area-aware FAB placement.

- [ ] Add tests clicking nested count elements, checking visible-only occupancy counts, absence of rendered comment text, and no FAB/tabbar overlap.
- [ ] Run tests and confirm failures.
- [ ] Use closest/currentTarget for chip state, compute counts from filtered visibility, remove template comments, and offset FAB by tabbar plus `env(safe-area-inset-bottom)`.
- [ ] Run targeted Playwright tests and confirm PASS.
- [ ] Commit with `fix(stays): correct mobile filter controls`.

### Task 3: Unify Guests capabilities

**Files:**
- Modify: `app/modules/stays/manifest.py`
- Modify: `app/modules/board/interface/guests_read_api.py`
- Modify: `app/modules/stays/interface/guests_api.py`
- Modify: `static/js/modules/stays_guests.js`
- Modify: `static/js/modules/stays.js`
- Modify: `tests/stays/test_manifest.py`
- Modify: `tests/stays/test_guests_api.py`
- Modify: `e2e/stays-forms.spec.mjs`
- Modify: `e2e/scenarios/stays.mjs`
- Modify: `docs/openapi.json`

**Interfaces:**
- Produces: full-directory capability `stays.guests`; create capability `stays.edit || stays.mine_guest_edit`; standalone menu visible for either.

- [ ] Add custom-grant API/menu tests for directory-only, create-only, both, and neither.
- [ ] Add a stale-response Playwright test for guest search.
- [ ] Run tests and confirm mismatches.
- [ ] Split directory/search/create authorization accordingly and guard asynchronous results with a request generation.
- [ ] Remove legacy hidden-tab assumptions and rename OpenAPI descriptions to “section”.
- [ ] Run pytest plus targeted Playwright and confirm PASS.
- [ ] Commit with `fix(guests): align section visibility and permissions`.

## PR Completion Gate

- [ ] Run repository baseline checks required by CI, push the branch, and open the PR with role-matrix/mobile evidence.
- [ ] Wait for every required CI check; diagnose and fix failures on the same branch.
- [ ] Merge only when CI is green, then update from main before starting PR 5.

