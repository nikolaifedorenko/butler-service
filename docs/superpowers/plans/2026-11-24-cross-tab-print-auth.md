# Cross-tab Print Authorization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind every print job to its authorizing server session and invalidate pending or mounted print work across tabs whenever authentication context changes.

**Architecture:** The server exposes a non-secret fingerprint of the random session token through auth responses and the print response header. Browser core persists versioned auth-context events for cross-tab delivery; the print module maintains an abortable job registry, validates the server context before mount, and revalidates mounted frames until cleanup.

**Tech Stack:** FastAPI/Pydantic, Python session/auth core, JavaScript ES modules, localStorage events, AbortController, Playwright/Chromium.

**Spec:** `docs/superpowers/specs/2026-11-24-cross-tab-print-auth-design.md`

## Global Constraints

- `auth_context` is correlation data only and is never accepted as authentication.
- Existing session cookie security, print authorization, HTML body, CSP, and request body stay unchanged.
- Every cancellation path removes iframe, listener, timeout, validation timer, abort controller, and registry entry idempotently.
- A delayed response is mounted only after its response context and a fresh server context both match the request's starting context.
- Normal auth transitions invalidate same-origin tabs immediately; missed browser events are caught by server revalidation before mount and while a frame lives.

## Review Focus

- A response authorized before logout must not mount after logout completes.
- An already-mounted frame in another tab must disappear on logout and impersonation start/stop.
- A direct cookie-changing request that bypasses browser broadcasting must still be caught by server revalidation.
- A suspended/restored tab must compare the persisted event and server context before retaining a frame.
- Concurrent completion, timeout, storage, visibility, and polling callbacks must not double-clean or leak resources.

---

### Task 1: Server auth-context contract

**Files:**
- Modify: `app/core/sessions.py`
- Modify: `app/core/auth.py`
- Modify: `app/modules/access/interface/schemas.py`
- Modify: `app/modules/access/interface/auth_routes.py`
- Modify: `app/modules/access/application/auth.py`
- Modify: `app/modules/docs/interface/docs_api.py`
- Modify: `docs/openapi.json`
- Modify: `tests/test_user_sessions.py`
- Modify: `tests/test_print_page.py`

**Interfaces:**
- Produces: `session_context(token: str) -> str`, a namespaced SHA-256 hex fingerprint.
- Produces: `Principal.auth_context: str | None`; `current_principal` always supplies it, while application-created principals may remain `None`.
- Produces: top-level `auth_context: str` in login/session, password-change, and `/api/auth/me` responses.
- Produces: `GET /api/auth/context -> {"auth_context": str}`.
- Produces: `X-Butler-Auth-Context` on successful `POST /api/docs/print`.

- [ ] Add tests that one cookie has a stable 64-hex context, a different/replaced session has a different context, and the value is not the cookie token or stored token hash.
- [ ] Add API tests that impersonation start/stop rotate the context and the revoked prior cookie receives 401 from `/api/auth/context`.
- [ ] Add print tests that the response header equals `/api/auth/context`, while anonymous print/context requests remain 401 and existing HTML/CSP assertions stay unchanged.
- [ ] Run the focused tests and confirm RED because no context contract exists.
- [ ] Implement `session_context(token)` and populate `Principal.auth_context` in `current_principal` without changing token lookup or authorization.
- [ ] Extend auth schemas/routes so login, password change, impersonation start/stop, `/me`, and `/context` return the current fingerprint. Keep existing `ok` fields and native form login behavior; form login obtains context through `/me` after redirect.
- [ ] Add the print header from the authenticated principal and regenerate OpenAPI with `tools/export_openapi.py`.
- [ ] Run `pytest tests/test_user_sessions.py tests/test_print_page.py tests/test_session_and_headers.py -q` plus Ruff, mypy, API contract, and OpenAPI checks; confirm PASS.
- [ ] Commit with `feat(auth): expose print session context`.

### Task 2: Cross-tab print lifecycle

**Files:**
- Modify: `static/js/core.js`
- Modify: `static/js/app.js`
- Modify: `static/js/modules/employees.js`
- Modify: `static/js/modules/docs.js`
- Modify: `static/index.html`
- Modify: `static/sw.js`
- Create: `e2e/auth-print-context.spec.mjs`
- Modify: `tests/test_static_cache.py`
- Modify: `tests/test_frontend_guards.py`

**Interfaces:**
- Consumes: Task 1's response/body `auth_context`, `/api/auth/context`, and `X-Butler-Auth-Context`.
- Produces: `adoptAuthContext(context: string | null) -> void` for boot without broadcast.
- Produces: `publishAuthContext(context: string | null) -> void` for logout, 401, password/session rotation, and impersonation changes.
- Produces: `authContextSnapshot() -> { context: string | null, eventId: string }`.
- Produces: `subscribeAuthContext(listener) -> () => void`, where listener receives `{context, eventId, external}`.
- Produces: an internal print-job registry whose cleanup is idempotent and whose jobs own request abort, iframe, message listener, fallback timeout, and server-validation interval.

- [ ] Add Chromium RED coverage with two pages sharing one browser context: page A has one mounted and one delayed print; page B logs out through the UI; both jobs disappear and the delayed response never mounts.
- [ ] Add Chromium RED coverage for impersonation start/stop in page B, verifying page A invalidates before reload and resumes under the new server identity.
- [ ] Add a missed-event RED: change the cookie through a direct API call that bypasses publishing; delayed response is rejected by the fresh `/api/auth/context` comparison and a mounted frame is removed by validation/foreground checks.
- [ ] Add a race RED: completion/timeout and auth invalidation fire together, cleanup runs once, and zero frames/listeners/timers/jobs remain.
- [ ] Run the focused Chromium file and confirm current code leaves or mounts stale frames.
- [ ] Implement persisted versioned auth events in `core.js`. Same-tab publication notifies synchronously; `storage` events mark `external: true`; boot adopts without broadcasting; no token or personal data is stored.
- [ ] Wire common 401, logout, password rotation, impersonation start/stop, and external-context handling. External non-null changes reload after synchronous cleanup; null changes show login after cleanup.
- [ ] Refactor `printWindow` into registered abortable jobs. Require response header, fresh server context, and unchanged snapshot before mount; validate mounted jobs periodically and on foreground; converge every exit on idempotent cleanup.
- [ ] Add static-version/service-worker updates and regenerate the shell once.
- [ ] Run the new Chromium file, existing print/norms scenarios, frontend/static Python contracts, ESLint, Node syntax, API/OpenAPI/version checks; confirm PASS.
- [ ] Commit with `fix(print): invalidate jobs across auth contexts`.

## PR completion gate

- [ ] Run full Python tests, Ruff, mypy, import contracts, API/OpenAPI/version/static checks, ESLint, and the full Playwright matrix.
- [ ] Request task review after each task and a whole-branch review after both tasks.
- [ ] Push `fix/auth-print-context`, create a PR against `main`, wait for every CI job, fix failures on the same branch, and merge only when green.
- [ ] Update the chessboard-print branch from the new `main`, resolve generated OpenAPI/static-version conflicts, rerun its final review and full branch gate before creating its PR.
