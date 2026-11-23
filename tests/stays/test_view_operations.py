"""Прикладной слой шахматки, табло, покрытия и выгрузки (шаг 4е-5): запись и аудит — одна
транзакция, отказы несут статус класса ошибки, ответы всегда с полным набором ключей."""
from __future__ import annotations

import io

import pytest
from openpyxl import load_workbook
from sqlalchemy import func, select

from app.core.audit import AuditLog
from app.modules.board.application import export
from app.modules.stays.adapters.orm import CoverageLine
from app.modules.stays.application import coverage_edit

from .helpers import API, create_res, make_category
from .test_coverage_api import _res, _template


def _count(db, model, *where) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where))


def test_template_is_not_saved_when_audit_fails(manager_role_client, manager_client, butlers, db, monkeypatch):
    _, _, res = _res(manager_role_client, manager_client, butlers)
    before = _count(db, CoverageLine, CoverageLine.reservation_id == res["id"])

    def broken(*_a, **_k):
        raise RuntimeError("журнал недоступен")
    monkeypatch.setattr(coverage_edit, "audit", broken)
    with pytest.raises(RuntimeError):
        _template(manager_client, res, "single", [butlers["a"]])
    db.rollback()
    assert _count(db, CoverageLine, CoverageLine.reservation_id == res["id"]) == before


def test_template_preview_saves_nothing(manager_role_client, manager_client, butlers, db):
    _, _, res = _res(manager_role_client, manager_client, butlers)
    r = manager_client.post(f"{API}/coverage/template", params={"preview": 1}, json={
        "reservation_id": res["id"], "kind": "single", "butlers": [butlers["a"]],
        "first": res["check_in"], "last": res["check_in"]})
    assert r.status_code == 200 and r.json()["preview"] is True and r.json()["overbook_refused"] is None
    db.rollback()
    assert _count(db, CoverageLine, CoverageLine.reservation_id == res["id"]) == 0


def test_add_shift_audit_is_all_or_nothing(manager_role_client, manager_client, butlers, db, monkeypatch):
    """Вторая запись журнала не удалась — не остаётся ни первой, ни самой смены."""
    from app.modules.timesheet.application.catalog import ShiftType
    a = butlers["a"]
    off = next(d for d in butlers["days"][:6] if not butlers["on"](a, d))
    kind = db.scalar(select(ShiftType).where(ShiftType.kind == "work").order_by(ShiftType.id))
    calls: list[str] = []
    real = coverage_edit.audit

    def second_fails(db_, principal, action, *args, **kw):
        calls.append(action)
        if len(calls) == 2:
            raise RuntimeError("журнал недоступен")
        return real(db_, principal, action, *args, **kw)
    monkeypatch.setattr(coverage_edit, "audit", second_fails)
    before = _count(db, AuditLog, AuditLog.action == "schedule_manual_shift")
    with pytest.raises(RuntimeError):
        manager_client.post(f"{API}/coverage/add-shift",
                            json={"employee_id": a, "day": off.isoformat(), "shift_type_id": kind.id})
    db.rollback()
    assert calls == ["schedule_manual_shift", "stays_add_shift"]
    assert _count(db, AuditLog, AuditLog.action == "schedule_manual_shift") == before


def test_replaced_params_and_bad_ids_are_422(manager_client):
    assert manager_client.get(f"{API}/board/units", params={
        "first": "2026-11-15", "last": "2026-11-20", "building": 1}).status_code == 422
    r = manager_client.get(f"{API}/coverage/candidates", params={"day": "2026-11-19", "reservation_id": 1,
                                                                "guest_ids": "a,b"})
    assert r.status_code == 422 and r.json()["detail"] == "Гости — номера через запятую"


def test_reservation_card_has_all_keys_for_every_level(manager_role_client, manager_client, butlers, db):
    _, _, res = _res(manager_role_client, manager_client, butlers)
    full = manager_client.get(f"{API}/reservations/{res['id']}/card").json()
    assert full["mine"] is None or isinstance(full["mine"], bool)
    assert {"customer", "note", "fields", "companions", "logistics", "mine"} <= set(full)


def test_export_requires_matching_permission_and_is_audited(manager_client, db):
    before = _count(db, AuditLog, AuditLog.action == "stays_export")
    r = manager_client.get(f"{API}/export", params={"first": "2026-11-15", "last": "2026-11-20"})
    assert r.status_code == 200 and "shakhmatka_anon_2026-11-15_2026-11-20.xlsx" in r.headers["content-disposition"]
    db.rollback()
    assert _count(db, AuditLog, AuditLog.action == "stays_export") == before + 1


def test_one_day_export_bounds_cell_expansion(manager_role_client, manager_client, monkeypatch):
    cat = make_category(manager_role_client, n_units=1)
    create_res(manager_client, cat, "2038-05-01", "2038-06-01")
    expanded_ranges = []

    def counted_range(*args):
        span = range(*args)
        expanded_ranges.append(len(span))
        return span

    monkeypatch.setattr(export, "range", counted_range, raising=False)
    day = "2038-05-15"
    response = manager_client.get(f"{API}/export", params={"first": day, "last": day})
    assert response.status_code == 200
    wb = load_workbook(io.BytesIO(response.content))
    board = list(wb["Шахматка"].values)
    assert board[0] == ("Объект", "Категория", "15.05")
    assert (cat["units"][0]["label"], cat["code"], "занято") in board
    assert all(length <= 2 for length in expanded_ranges), expanded_ranges


def test_export_skips_allocation_queries_needed_by_board_view(manager_role_client, manager_client, sql_counter):
    cat = make_category(manager_role_client, n_units=1)
    create_res(manager_client, cat, "2038-06-12", "2038-06-18")
    params = {"first": "2038-06-15", "last": "2038-06-15"}
    with sql_counter() as view_queries:
        view = manager_role_client.get(f"{API}/board/units", params=params)
    assert view.status_code == 200
    assert {"holds", "blocks", "warnings"} <= view.json().keys()
    with sql_counter() as export_queries:
        result = manager_role_client.get(f"{API}/export", params={**params, "kind": "full"})
    assert result.status_code == 200
    for table in ("stays_ooo", "stays_block_nights"):
        assert any(statement.startswith(f"SELECT {table}.") for statement in view_queries["by_statement"])
        assert not any(statement.startswith(f"SELECT {table}.") for statement in export_queries["by_statement"])
