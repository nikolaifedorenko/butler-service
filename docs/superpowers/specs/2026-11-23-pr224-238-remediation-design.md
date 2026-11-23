# PR 224–238 remediation design

## Intent

Bring the implementation promised by PRs 224–238 into agreement with their descriptions, close the edge cases found by the audit, restore the missing chessboard print workflow, and release the changes in reviewable increments. Each increment must be safe to merge independently, must add regression coverage for the defect it closes, and must leave the main branch deployable.

## Goals

- Preserve every legitimate deferred carry block and make repeated period closing idempotent.
- Make chessboard exports deterministic when several reservations occupy the same unit and bound export work to the requested interval.
- Reject non-integral engine step values before persistence and keep error messages aligned with the actual rule.
- Make browser print documents clean themselves up under CSP, and add a printable chessboard view for the selected month, active filters, and the caller's visibility level.
- Make encrypted backups work both with a remote SSH destination and in local-only mode while the container remains non-root.
- Align menu visibility, guest creation, and guest-directory API authorization.
- Fix mobile/menu accessibility and overlay ownership across car menus, filters, FABs, modals, drawers, and the command palette.
- Make current/former family semantics deterministic and exclude former-only relations from active composition.
- Remove motion-token conflicts and command-palette races/coupling.
- Prove the result with unit, integration, contract, security, and full Playwright coverage.

## Non-goals

- Redesigning the chessboard information architecture beyond the fixes below.
- Changing role names or the overall permission model.
- Replacing the existing print endpoint, lit-html stack, backup encryption scheme, or deployment platform.
- Automatically deploying to production without a verified backup, healthy CI, an identified target, and an available rollback procedure.

## Constraints and safety

- Existing production data must not be discarded by a migration. Migration code must preserve distinct deferred blocks and may only collapse exact duplicates when that is demonstrably safe.
- The repository's current uncommitted user changes, if any appear, must be preserved.
- Every product-code fix starts from a failing regression test.
- Each PR must pass its targeted suite plus repository lint/type/contract checks. The final PR must pass the entire Playwright suite against real Chromium.
- Merge only after required CI checks succeed. Deployment follows the documented tag/compose flow and begins with a fresh encrypted backup and restore verification where the environment permits it.

## Approaches considered

### Chosen: sequential thematic PRs

Group tightly related defects, merge them one at a time, and keep each PR independently releasable. This minimizes migration and UI risk, makes CI failures attributable, and provides useful rollback boundaries.

### Rejected: one large remediation PR

This reduces coordination overhead but mixes schema, backup, permissions, and UI behavior into a review and rollback unit that is too large.

### Rejected: isolated symptom patches

This produces smaller diffs but leaves mismatched invariants in the permission, family, and overlay systems and would require repeated fixes.

## Delivery sequence

### PR 1 — Deferred carry integrity (PR 225)

- Replace the incorrect `employee_id + period_start` uniqueness invariant with an identity that permits multiple distinct blocks for a period while rejecting exact duplicate rows.
- Update replacement persistence so a close writes the complete set atomically and remains safe under concurrent attempts. The existing employee lock remains the serialization boundary: a recalculation that starts later replaces the whole set with its newly computed result; partial merging is forbidden.
- Add an Alembic migration that preserves distinct existing blocks and only removes exact duplicates.
- Cover multiple tariffs/source days, exact duplicates, repeated saves, and concurrent/conflicting writes.

### PR 2 — Non-root backups (PR 231)

- Do not require or copy SSH material when `BACKUP_REMOTE` is empty.
- For remote mode, consume credentials in a way the non-root user can actually read. The supported deployment contract will mount files readable by the container backup user; the entrypoint will validate them, copy them into its home, set strict destination permissions, and fail with a precise diagnostic when the source is unreadable.
- Update deployment documentation without suppressing ownership failures.
- Add container-level smoke coverage for local-only mode, readable remote credentials, and unreadable credentials.

### PR 3 — Export, settings, and print correctness (PRs 227, 229, 230)

- Make chessboard export cells aggregate every visible overlapping reservation instead of choosing a winner. Order entries deterministically by segment start, reservation number/ID, and guest; retain all booking rows without silent overwrite.
- Restrict expansion and queries to the requested export interval.
- Require engine step to be an integer before divisor/multiple validation; correct allowed-value guidance and verify raw stored JSON agrees with decoded settings.
- Change print completion messaging so a `srcdoc` document can notify its same-page parent under CSP, while the parent validates the message source and payload and always cleans up the iframe.
- Add a chessboard `Печать` action beside exports. It prints the currently selected month and filters, uses the same visibility as the rendered board, includes no data the caller cannot view, and uses the existing server print endpoint.
- Add Chromium tests for successful print invocation and cleanup, including the chessboard view.

### PR 4 — Navigation, permissions, and responsive controls (PRs 232–234)

- Measure car popup geometry only after it is renderable; keep it within the viewport and avoid closing it because its own contents scroll.
- Add keyboard semantics and test the open menu with accessibility tooling.
- Use `currentTarget`/closest-button ownership for filter chips and compute counts from the filtered visibility model.
- Remove rendered template comments and keep the mobile FAB clear of the tab bar/safe area.
- Define explicit shared capabilities for the standalone Guests section. `stays.guests` grants the full directory without an additional `stays.view` requirement. `stays.edit` or `stays.mine_guest_edit` grants guest creation; the latter is restricted by the existing application rule to the caller's own guest and limited fields. The menu appears when either full-directory or create capability exists. Full-directory controls require `stays.guests`; create controls require either create permission. A user must never see an action the API rejects, nor lose an action the API permits.
- Guard guest-search responses with request generations/abort semantics.
- Replace legacy tests that rely on the removed chessboard Guests tab and update API descriptions from “tab” to “section”.

### PR 5 — Overlay ownership and family semantics (PRs 235–236)

- Introduce explicit topmost-overlay ownership so one Escape closes exactly one layer. Opening a drawer or palette from a modal must have a deterministic stacking and return-focus policy.
- Test modal + guest drawer, modal + palette, focus restoration, mobile width, and repeated Escape.
- Represent current and former family paths with deterministic precedence: an active relation wins over a former-only path; direct former relations are marked former; labels preserve the actual relation kind.
- Exclude former-only relatives from active booking composition while retaining them in the guest's history/family display.
- Replace the contradictory test expectation and add direct former, current+former alternate path, and former-spouse/partner cases.

### PR 6 — Motion and command palette (PRs 237–238)

- Remove the duplicate `--ease` definition and make duration/easing tokens the sole transition source; retain reduced-motion behavior and intended numeric typography.
- Make one application-level owner for `Ctrl/Cmd+K`; settings must not open a second modal beneath the palette.
- Build palette navigation from the same complete visible-menu source as the sidebar, including Today.
- Prevent stale guest-search responses from repopulating cleared or reopened palettes.
- Move guest search/action registration behind a registry/provider interface so the palette does not import stays forms or hard-code stays permissions/API paths.
- Add timing-token assertions and Playwright coverage for shortcut conflicts, stale responses, and provider absence.

### PR 7 — Release verification and hardening

- Run Ruff, mypy, ESLint, unit/integration/security/contract tests, migration tests, compose validation, and the full Playwright matrix.
- Verify a clean repository and inspect the rendered desktop/mobile flows for all relevant roles.
- Update version/service-worker shell only once all fixes are merged, then run the final cache/update smoke test.
- Create a release tag only after CI is green.
- Before production deployment, identify the target, create a fresh encrypted backup, confirm restore-check/rollback readiness, deploy the tag with the documented compose workflow, and verify health plus representative authenticated flows. If credentials or target access are unavailable, stop after the release artifact and report the exact handoff commands.

## PR and CI workflow

For each delivery item: branch from current main, write failing tests, implement the narrow fix, run targeted and baseline checks, commit, push, open a PR with audit evidence, wait for required CI, diagnose and fix failures on the same branch, request/perform review, merge through the repository's supported method, then update from main before starting the next item. No later PR depends on unmerged workspace state.

## Acceptance criteria

- All audit reproductions from PRs 225 and 227–238 are converted to passing automated tests or, where environment-specific, documented container/browser smoke checks.
- PRs 224, 226, and 228 remain green without behavioral regressions.
- A clean Chromium session shows icons for Chessboard/My Guests, the standalone Guests section for every authorized role, and a working chessboard print action.
- Full CI and Playwright pass on the release commit.
- Production is changed only after the release commit/tag, backup, target, and rollback path have all been explicitly verified.

## Builder discretion

- Exact helper/function names and internal module boundaries, provided the permission and dependency directions above are preserved.
- Whether stale async searches use `AbortController`, monotonically increasing generations, or both.
- The visual details of the print stylesheet, provided it is readable, fits the selected month, and does not reveal unauthorized data.
