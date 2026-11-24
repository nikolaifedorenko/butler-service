# Cross-tab print authorization design

## Intent

Prevent a prepared or already-mounted print document from surviving an authentication-context change. A logout, expired session, password/session revocation, or impersonation transition must invalidate print work in every same-origin tab. A delayed response created under one server session must never mount under another.

This is a prerequisite PR from `main`. The chessboard-print branch will be updated onto it only after this PR is green and merged.

## Goals

- Treat the server session as the authority for the identity that prepared a print document.
- Abort pending print requests and remove mounted print iframes, message listeners, timers, and validation polling when auth context changes.
- Propagate normal application auth transitions immediately across same-origin tabs.
- Detect a missed browser event before mounting a response and while a print frame remains alive.
- Cover logout, 401/session expiry, impersonation start/stop, delayed responses, mounted frames, and two-tab behavior in real Chromium.

## Non-goals

- Change roles, permissions, document contents, or the `/api/docs/print` request body.
- Add realtime infrastructure for arbitrary cross-device UI logout. Server revocation remains authoritative; active print jobs revalidate it while alive.
- Replace the existing iframe print flow or CSP model.

## Approaches considered

### Chosen: server-bound context plus persisted browser invalidation

Every authenticated session exposes a non-secret opaque context fingerprint. The print response carries the context that authorized it. The browser broadcasts auth transitions through persisted same-origin storage, revalidates with the server before mounting, and continues lightweight validation while a frame is alive.

This closes both sides of the race: browser events remove existing work immediately, while server comparison rejects delayed responses even when the event was missed.

### Rejected: `BroadcastChannel` only

It is simple and fast, but a suspended or newly restored tab can miss a non-persisted message. It also does not independently prove that a delayed response belongs to the current server session.

### Rejected: server context comparison only

It can reject a delayed response, but it cannot immediately remove an already-mounted iframe in another tab without polling or a browser-side signal.

## Server contract

- Derive `auth_context` as a namespaced SHA-256 fingerprint of the random session cookie token. It is an equality/correlation value only, never accepted as authentication and never usable to reconstruct the token.
- Return `auth_context` from session-establishing JSON responses and `/api/auth/me`.
- Add a lightweight authenticated `GET /api/auth/context` response containing only `auth_context`.
- Add `X-Butler-Auth-Context` to successful `/api/docs/print` responses.
- A revoked or expired cookie returns 401 from the context endpoint, as it does for other authenticated endpoints.
- Keep the existing print HTML body, CSP, authorization dependency, and status behavior unchanged.

## Browser contract

- Core state stores the current `auth_context` and the most recent persisted auth-event ID.
- Auth transitions publish a versioned event to a fixed `localStorage` key and invalidate the current tab synchronously. Events include a unique event ID and the new context (or `null` for logout/401); they contain no token or personal data.
- Other tabs handle the `storage` event synchronously: print jobs are invalidated first. A logout shows login; a non-null changed context reloads so identity, permissions, and caches come from the server.
- Login/boot initializes local state without broadcasting merely because a new tab opened.
- Logout, common 401 handling, password session rotation, and impersonation start/stop publish the new context. Publishing and local invalidation occur before privileged UI is reused.

## Print lifecycle

For each `printWindow` call:

1. Capture the current browser auth context and auth-event ID.
2. Start the print POST with its own `AbortController` and register the job.
3. Require a successful response header equal to the captured context.
4. Call `GET /api/auth/context`; require the same context and confirm that no persisted auth event changed during the request.
5. Only then create and mount the iframe.
6. While the frame is alive, revalidate the lightweight context periodically and when the document returns to the foreground. A mismatch or 401 uses the same idempotent cleanup path.
7. Auth events abort pending requests and invoke cleanup for every mounted job. Cleanup removes the iframe, message listener, fallback timeout, validation timer, and registry entry.

Normal `afterprint`, authenticated completion-message, timeout, request failure, insertion failure, and auth invalidation all converge on that cleanup path.

## Failure behavior

- A context mismatch is treated as cancellation, not as a printable document. No stale HTML is mounted.
- Authentication failure invokes the application's normal login transition without leaving print artifacts.
- Network failure during periodic validation removes the print frame conservatively; it does not retain privileged material while authorization is uncertain.
- Cleanup is idempotent so simultaneous storage, polling, and completion events are safe.

## Tests

- Python/API tests: context fingerprint is stable for one session, rotates on impersonation/session replacement, is absent as an authentication mechanism, `/api/auth/context` returns 401 after revocation, and print response header matches the authorizing session.
- JavaScript/unit-contract tests: registry cleanup releases all resources and a mismatched/missing response context never mounts.
- Real Chromium with two pages in one browser context:
  - mounted and delayed print jobs in page A disappear when page B logs out;
  - impersonation start and stop rotate context, clean page A, and reload it with the new identity;
  - an auth change performed without the browser broadcast is still caught by server revalidation before delayed mount;
  - a mounted frame is removed by periodic/foreground validation after a missed event;
  - ordinary printing and cleanup remain green.

## Integration and rollout

- This PR receives its own static/service-worker version bump and CI/Playwright gate.
- After merge, rebase/update the chessboard-print branch onto the new `main`, resolve generated OpenAPI/static-version conflicts, rerun its final review and full branch gate, then open its PR.
