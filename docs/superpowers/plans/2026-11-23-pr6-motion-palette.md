# Motion Tokens and Command Palette Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make motion tokens authoritative and command-palette behavior race-free, single-owner, and module-decoupled.

**Architecture:** CSS has one easing token definition. App-level shortcut ownership opens the palette. Feature modules register palette providers through the registry instead of being imported by the palette.

**Tech Stack:** CSS custom properties, JavaScript modules/lit-html, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-23-pr224-238-remediation-design.md`

## Global Constraints

- Reduced-motion behavior remains intact.
- `Ctrl/Cmd+K` has exactly one owner.
- Palette core must not import stays forms or hard-code stays permissions/API paths.

## Review Focus

- Computed transition timing uses the new tokens, not the overwritten legacy value.
- Reduced-motion eliminates nonessential animation.
- Settings plus `Ctrl/Cmd+K` opens only the palette.
- Clearing/reopening a query cannot restore a stale response.
- Palette still works when no guest provider is registered.

---

### Task 1: Normalize motion tokens

**Files:**
- Modify: `static/css/tokens.css`
- Modify: `static/css/components.css`
- Modify: `static/css/app.css`
- Modify: `tests/test_design_tokens.py`
- Modify: `e2e/design.spec.mjs`

**Interfaces:**
- Produces: one `--ease` definition and token-based transition durations/easing.

- [ ] Add static/computed-style tests for one easing definition, intended durations, reduced motion, shimmer, palette, buttons, and today-stat numeric style.
- [ ] Run tests and confirm legacy `--ease: .18s ease-out` wins today.
- [ ] Remove the duplicate token and correct dependent transitions/typography.
- [ ] Run targeted tests and confirm PASS.
- [ ] Commit with `fix(ui): make motion tokens authoritative`.

### Task 2: Palette providers and shortcut ownership

**Files:**
- Modify: `static/js/registry.js`
- Modify: `static/js/ui/palette.js`
- Modify: `static/js/app.js`
- Modify: `static/js/modules/settings.js`
- Modify: `static/js/modules/stays_guests.js`
- Modify: `e2e/palette.spec.mjs`

**Interfaces:**
- Produces: `registerPaletteProvider({ id, search(query, signal), activate(item) })`; palette consumes registered providers and the complete `visibleTabs()` list including Today.

- [ ] Add tests for Today navigation, one shortcut owner, provider absence, aborted/stale searches, and reopen-after-clear.
- [ ] Run tests and confirm failures.
- [ ] Add provider registration, move guest search/activation into the stays module, and remove the settings shortcut listener/direct stays imports.
- [ ] Use `AbortController` plus generation validation when closing or replacing a query.
- [ ] Run `npm run lint` and targeted Playwright tests; confirm PASS.
- [ ] Commit with `refactor(palette): register feature search providers`.

## PR Completion Gate

- [ ] Run repository baseline checks required by CI, push the branch, and open the PR with computed-style/palette evidence.
- [ ] Wait for every required CI check; diagnose and fix failures on the same branch.
- [ ] Merge only when CI is green, then update from main before starting PR 7.

