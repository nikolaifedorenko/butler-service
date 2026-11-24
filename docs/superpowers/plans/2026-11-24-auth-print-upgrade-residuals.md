# Auth Print Upgrade Residuals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the two load-bearing residuals from the auth-print final review without weakening the strict session-bound print lifecycle.

**Architecture:** The print child protocol gets a versioned script URL shared by server HTML and the service-worker shell; an old worker has no matching cache entry and must fetch the new handshake script. Successful same-identity password rotation explicitly reloads the active view after publishing the replacement context, so Today captures the new auth snapshot and reinstalls its data and poller.

**Tech Stack:** JavaScript ES modules, service worker Cache API, FastAPI/Python HTML generation, Playwright/Chromium, pytest.

**Spec:** `docs/superpowers/specs/2026-11-24-cross-tab-print-auth-design.md` plus the load-bearing rulings in `.superpowers/sdd/auth-print-context/progress.md`.

## Global Constraints

- `auth_context` and its readable companion remain correlation data only and are never accepted as authentication.
- Native printing may begin only after the current parent job authorizes the exact child window through the readiness handshake.
- The versioned child URL must be identical in server-generated HTML and the service-worker shell and must not resolve to the pre-handshake cache key.
- An already-open pre-fix parent may require reload; safety takes precedence over silently falling back to unverified printing.
- Password rotation keeps the same user signed in, publishes the replacement context, and restores the active view under that new context without duplicating pollers.
- Do not weaken CSP, origin/source checks, server revalidation, or idempotent print cleanup.

## Review Focus

- An old service worker with `/static/js/print-page.js` cached must miss the new versioned child URL and fetch the handshake-capable script.
- Server HTML, service-worker shell, and static version checks must agree on the exact child URL.
- The new parent must never authorize a pre-handshake child script, even during upgrade skew.
- After password rotation on Today, punch works without manually reopening the view and foreground/poll refresh resumes once.
- The peer tab must still invalidate its old print and reconcile to the replacement context.

---

### Task 1: Version the print-child protocol across service-worker upgrades

**Files:**
- Modify: `app/modules/docs/application/print_page.py`
- Modify: `static/sw.js`
- Modify: `static/index.html`
- Modify: `e2e/auth-print-context.spec.mjs`
- Modify: `tests/test_static_cache.py`
- Modify: `tests/test_print_page.py`

**Interfaces:**
- Produces: one exact versioned child URL `/static/js/print-page.js?v=2026-11-24b` in print HTML and `SHELL`.
- Preserves: `butler_print_ready` / `butler_print_done` parent protocol and existing CSP.

- [ ] Add a pytest contract asserting `print_page()` emits exactly the versioned URL and the service-worker shell contains that same URL but not the unversioned cache key.
- [ ] Add a Chromium upgrade regression that installs/uses an old cache entry for the unversioned child, requests a new print, and proves the old script cannot invoke native print while the versioned script completes the readiness handshake.
- [ ] Run the focused tests on `ea1c917` and record RED from the unversioned URL/cache hit.
- [ ] Change the server HTML and `SHELL` to the exact versioned URL; bump the shell release once from `2026-11-24a` to `2026-11-24b` using the repository version tool and refresh the digest.
- [ ] Run the upgrade regression, existing child-readiness/exact-child tests, static-cache/print-page tests, API/OpenAPI/version checks, ESLint and Node syntax; record GREEN.
- [ ] Commit with subject `fix(print): version child handshake protocol`.

### Task 2: Rebind Today after same-identity password rotation

**Files:**
- Modify: `static/js/app.js`
- Modify: `e2e/auth-print-context.spec.mjs`
- Modify: `e2e/today.spec.mjs` only if the shared Today fixture is the clearer owner.
- Modify: `tests/test_frontend_guards.py` only for a complementary contract, not as a substitute for Chromium behavior.

**Interfaces:**
- Consumes: `publishAuthContext(res.auth_context)` and existing `navigate(view)` same-view reload semantics.
- Produces: successful password rotation reloads `state.view` immediately under the replacement auth snapshot, leaving one active Today poller.

- [ ] Extend the real password-rotation Chromium flow: open Today, retain a visible punch action, rotate the password, then without manually navigating assert a punch POST succeeds and a foreground signal causes a new status read; assert no duplicate polling/requests.
- [ ] Run that test on the Task 1 head and record RED: zero punch and refresh requests because the Today owner snapshot is retired.
- [ ] After publishing the replacement context, close the modal and re-run the current view through `navigate(state.view)`; keep the same user shell and peer invalidation behavior unchanged.
- [ ] Run the password/Today regression plus existing password publication, peer cleanup, Today punch and poller tests; record GREEN.
- [ ] Run focused Python/static contracts, ESLint, Node syntax, API/OpenAPI/version checks.
- [ ] Commit with subject `fix(auth): rebind view after password rotation`.

## Completion gate

- [ ] Request a fresh review after each task and a whole-branch review for `30ddaa2..HEAD` with the prior residual findings explicitly named.
- [ ] Run full Python, Ruff, mypy, import contracts, API/OpenAPI/version/static checks, ESLint, and the complete three-project Playwright matrix.
- [ ] Push and create the prerequisite PR only after the final reviewer is clean and every local gate passes; monitor all CI jobs and merge only when green.
