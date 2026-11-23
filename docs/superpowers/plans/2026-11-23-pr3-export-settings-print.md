# Export, Settings, and Print Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct chessboard export aggregation, engine-step validation, print cleanup, and add chessboard printing.

**Architecture:** Exports aggregate all visible overlaps per cell in deterministic order. Settings reject non-integral steps at the boundary. Printing continues through `/api/docs/print`, with source-validated completion messages and a chessboard-specific HTML builder.

**Tech Stack:** Python/FastAPI, openpyxl, JavaScript/lit-html, Playwright/Chromium.

**Spec:** `docs/superpowers/specs/2026-11-23-pr224-238-remediation-design.md`

## Global Constraints

- Printed/exported content must respect the caller's existing visibility level.
- Requested date bounds limit both queries and expanded cells.
- Print iframe cleanup must work under CSP.

## Review Focus

- Two overlapping reservations appear in deterministic aggregate form.
- Reservation spans outside the requested interval do not expand work/output.
- JSON `15.9` is rejected, never stored as raw `15.9` and decoded as `15`.
- A forged message from another frame cannot remove a print frame.
- Occupancy-level chessboard printing contains no names, reservation numbers, or VIP data.

---

### Task 1: Aggregate chessboard export cells

**Files:**
- Modify: `app/modules/board/application/export.py`
- Modify: `tests/board/test_export.py`
- Modify: `tests/stays/test_view_operations.py`

**Interfaces:**
- Produces: `_bar_index(...) -> dict[(unit_id, day), tuple[bar, ...]]` with stable ordering and clipped date iteration.

- [ ] Add tests for overlapping/group reservations, stable ordering, complete booking sheets, and clipping to a one-day request.
- [ ] Run targeted tests and confirm the current single-value index fails.
- [ ] Change the index and cell formatter to aggregate every visible entry without overwriting.
- [ ] Run `pytest tests/board/test_export.py tests/stays/test_view_operations.py -q` and confirm PASS.
- [ ] Commit with `fix(board): aggregate overlapping export entries`.

### Task 2: Enforce integral engine steps

**Files:**
- Modify: `app/modules/timesheet/domain/settings/validate.py`
- Modify: `app/modules/timesheet/adapters/settings_codec.py`
- Modify: `app/modules/timesheet/application/texts.py`
- Modify: `tests/engine/test_validation.py`
- Modify: `tests/test_engine_api.py`

**Interfaces:**
- Produces: validation that accepts integer JSON numbers only and reports the actual representable/divisor rule.

- [ ] Add domain/API tests for `15.9`, numeric strings, booleans, valid `3/6/12/15/30/60`, and rejected divisor-only values.
- [ ] Run tests and confirm fractional input is persisted/truncated today.
- [ ] Validate type/integrality before arithmetic and remove silent `int()` coercion from the codec.
- [ ] Align user-facing error text with accepted values.
- [ ] Run targeted tests and confirm PASS.
- [ ] Commit with `fix(engine): reject fractional step settings`.

### Task 3: Repair print completion protocol

**Files:**
- Modify: `static/js/print-page.js`
- Modify: `static/js/modules/docs.js`
- Modify: `app/modules/docs/application/print_page.py`
- Modify: `e2e/scenarios/norms.mjs`
- Modify: `docs/openapi.json`

**Interfaces:**
- Produces: completion payload containing a per-frame nonce; parent accepts only `event.source === iframe.contentWindow` and matching nonce.

- [ ] Add a Chromium test asserting the iframe disappears after `afterprint` and a forged message is ignored.
- [ ] Run the scenario and confirm the iframe survives because `srcdoc` origin is `null`.
- [ ] Add `nonce` to `PrintIn`, render it as inert document data, post it to `'*'`, and validate source, nonce, and payload in the parent.
- [ ] Declare the HTML response media type in OpenAPI.
- [ ] Run the print scenario and confirm PASS.
- [ ] Commit with `fix(print): authenticate iframe completion messages`.

### Task 4: Add chessboard print action

**Files:**
- Modify: `static/js/modules/stays.js`
- Create: `static/js/modules/stays_print.js`
- Modify: `static/sw.js`
- Modify: `e2e/stays-core.spec.mjs`
- Modify: `e2e/scenarios/stays.mjs`

**Interfaces:**
- Produces: `printStaysBoard(data, fund, filters, visibility, monthLabel) -> Promise<void>` using `printWindow`.

- [ ] Add Playwright tests for the button, selected month/filter labels, full/names/occupancy redaction, and iframe cleanup.
- [ ] Run tests and confirm no print action exists.
- [ ] Build printable HTML from already authorized board data and place `Печать` beside exports.
- [ ] Add the new module to the service-worker shell/version.
- [ ] Run targeted Playwright scenarios and confirm PASS.
- [ ] Commit with `feat(stays): print current chessboard view`.

## PR Completion Gate

- [ ] Run repository baseline checks required by CI, push the branch, and open the PR with export/settings/Chromium evidence.
- [ ] Wait for every required CI check; diagnose and fix failures on the same branch.
- [ ] Merge only when CI is green, then update from main before starting PR 4.

