# Password Fixture Settlement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Guarantee that the password-rotation Chromium fixture restores the seeded account even when the page loses the issuer response after dispatch but before the server commits.

**Architecture:** The independent cleanup client treats the rotation result as eventually settled, not as a conclusion derived from one login attempt. It reconciles both candidate credentials until the in-flight issuer can no longer change the observed state, restores from the temporary credential whenever it becomes active, and finishes only after the original credential is verified stable.

**Tech Stack:** Playwright request context, Chromium, existing FastAPI auth endpoints.

**Spec:** `docs/superpowers/specs/2026-11-24-cross-tab-print-auth-design.md` and the residual ruling in `.superpowers/sdd/auth-print-upgrade-residuals/progress.md`.

## Global Constraints

- Test cleanup is independent of the page, its JavaScript context, and its response promise.
- Never add a production test-only endpoint or access the database directly from browser tests.
- Avoid login-rate-limit abuse; use bounded retries and the minimum requests needed to establish a stable final credential.
- Preserve the original scenario error and report cleanup failure separately.
- Production auth behavior and release `2026-11-24c` remain unchanged unless the RED proves a production change is necessary.

## Review Focus

- Page closes after request dispatch but before server commit; cleanup must still restore the original password.
- Server commits temporary password after cleanup first observes the original credential.
- Page closes after a committed response and after a punch; both password and punch state restore.
- Simultaneous scenario and cleanup failures remain visible.
- Repeated execution against one serial demo database does not accumulate rate-limit or punch state.

---

### Task 1: Reconcile a lost password issuer response

**Files:**
- Modify: `e2e/auth-print-context.spec.mjs`
- Modify: a shared E2E helper only if extraction materially reduces duplication.

**Interfaces:**
- Produces: an independent cleanup helper that observes both original and temporary credentials through normal auth APIs and returns only after the original credential is stable.

- [ ] Add a deterministic Chromium RED that dispatches password rotation, closes the page before response/commit observation, delays commit past the cleanup's first original-password probe, and proves the old cleanup leaves the temporary password active.
- [ ] Implement bounded settlement: continue reconciling after an early original-password success; if temporary becomes active, authenticate it, restore the original password through the normal endpoint, then verify original login in a fresh client. Use condition-based waiting rather than a single arbitrary sleep.
- [ ] Re-run the pre-response, post-response and post-punch closure cases twice against one serial database; verify original login and punch journal after every run.
- [ ] Run the auth-print Chromium suite, lint/syntax/version checks and full pytest; commit `test(auth): settle lost password issuer cleanup`.
- [ ] Request task review and whole-branch review, then run the complete Playwright matrix.
