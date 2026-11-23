# Deferred Carry Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve multiple legitimate deferred blocks per employee/period while keeping replacement writes atomic and duplicate-free.

**Architecture:** The employee transaction lock remains the serialization boundary. `save_deferred` replaces the complete target-period set; database uniqueness identifies an exact block, not an entire period.

**Tech Stack:** Python, SQLAlchemy, PostgreSQL, Alembic, pytest.

**Spec:** `docs/superpowers/specs/2026-11-23-pr224-238-remediation-design.md`

## Global Constraints

- Preserve distinct production rows; collapse only exact duplicates.
- Write the failing regression before changing product code.
- End with a PR that is independently deployable.

## Review Focus

- Same period with different source days/tariffs/minutes retains every block.
- Exact duplicates are collapsed by migration and rejected afterward.
- Recalculation replaces, rather than appends to, the prior complete set.
- Empty recalculation removes all outgoing carry rows.
- Concurrent closes serialize through the existing employee lock without mixed sets.

---

### Task 1: Correct deferred-row identity

**Files:**
- Create: `app/bootstrap/alembic/versions/0003_deferred_carry_block_unique.py`
- Modify: `app/modules/timesheet/adapters/orm.py`
- Modify: `tests/test_schema_version.py`
- Test: `tests/test_deferred_tariff.py`

**Interfaces:**
- Consumes: `SqlCarryOver.save_deferred(employee_id: str, next_period_: Period, blocks: Sequence[DeferredBlock]) -> None`
- Produces: unique identity `(employee_id, period_start, source_day, tariff, minutes)`.

- [ ] Add tests proving two distinct blocks coexist and an exact duplicate raises `IntegrityError`.
- [ ] Run `pytest tests/test_schema_version.py tests/test_deferred_tariff.py -q` and confirm the new coexistence test fails.
- [ ] Add migration `0003`, drop `uq_deferred_carry_employee_period`, delete only exact duplicates using the smallest `id`, and create `uq_deferred_carry_block` on all five identity columns.
- [ ] Update `DeferredCarry.__table_args__` to the same constraint.
- [ ] Run `pytest tests/test_schema_version.py tests/test_deferred_tariff.py -q` and confirm PASS.
- [ ] Commit with `fix(timesheet): preserve distinct deferred carry blocks`.

### Task 2: Prove atomic replacement behavior

**Files:**
- Modify: `tests/engine/test_application.py`
- Modify: `tests/test_deferred_tariff.py`
- Verify: `app/modules/timesheet/adapters/sql_closings.py`

**Interfaces:**
- Produces: a regression contract for full-set replacement under the existing UoW and employee lock.

- [ ] Add database-backed tests for replacing two old rows with two different rows and for replacing with an empty tuple.
- [ ] Add an application test asserting close/recalculate calls `lock_employee` before `save_deferred` and rollback leaves the old set intact on failure.
- [ ] Run the new tests and confirm they expose any ordering/rollback gap.
- [ ] Make the smallest adapter/UoW change needed; do not merge block sets.
- [ ] Run `pytest tests/engine/test_application.py tests/test_deferred_tariff.py tests/test_schema_version.py -q` and confirm PASS.
- [ ] Run `ruff check app tests && mypy app` and confirm PASS.
- [ ] Commit with `test(timesheet): cover deferred carry replacement`.

## PR Completion Gate

- [ ] Run repository baseline checks required by CI, push the branch, open the PR, and attach the audit reproduction.
- [ ] Wait for every required CI check; diagnose and fix failures on the same branch.
- [ ] Merge only when CI is green, then update from main before starting PR 2.

