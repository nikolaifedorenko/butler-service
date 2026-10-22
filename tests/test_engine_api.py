"""Интеграция движка v7.1 с приложением: Табель, УТ (view/close/recalculate — четыре
режима 7.2), последовательное закрытие (RUL-SEQUENTIAL-CLOSING), посев OPENING_SEED
(v7.1/R37), отклонение view при незакрытом предшественнике (RUL-VIEW-AFTER-PREVIOUS),
доска «Отметки», права и аудит."""
from __future__ import annotations

import calendar
import datetime as dt

import pytest

from app.core.time import local_date

TODAY = local_date()
PREV_END = TODAY.replace(day=1) - dt.timedelta(days=1)
PREV = PREV_END.replace(day=1)


@pytest.fixture(scope="module")
def admin(app_stack):
    from fastapi.testclient import TestClient

    c = TestClient(app_stack["app"])
    assert c.post("/api/auth/login", json={"username": "admin", "password": "demo1234"}).status_code == 200
    return c


def _month_days(first: dt.date) -> list[str]:
    last = calendar.monthrange(first.year, first.month)[1]
    return [dt.date(first.year, first.month, d).isoformat() for d in range(1, last + 1)]


@pytest.fixture(scope="module")
def emp(admin):
    """Сотрудник, принятый 1-го числа прошлого месяца: PREV — его ПЕРВЫЙ период
    цепочки (16.1 п.7), начальный банк посеян OPENING_SEED (v7.1/R37)."""
    r = admin.post("/api/employees", json={
        "full_name": "Закрытов Закрыт Закрытович", "position": "Батлер",
        "hired_at": PREV.isoformat(), "schedule_group": "Смена 1"})
    assert r.status_code == 200, r.text
    e = r.json()
    # посев начального банка первого периода (нулевая сумма — «задано ≠ ноль по умолчанию»)
    seed = admin.post(f"/api/employees/{e['id']}/bank-adjust", json={
        "hours": 0, "date": PREV.isoformat(), "note": "начальный банк (посев)",
        "reason_code": "OPENING_SEED"})
    assert seed.status_code == 200, seed.text
    days = _month_days(PREV)
    assert admin.post("/api/tabel/bulk", json={
        "employee_ids": [e["id"]], "dates": days, "code": "В"}).status_code == 200
    d1, d2 = PREV + dt.timedelta(days=1), PREV + dt.timedelta(days=2)
    assert admin.put("/api/tabel/cell", json={"employee_id": e["id"], "date": d1.isoformat(),
                                              "code": "Я", "hours": 12}).status_code == 200
    for day, a, b in ((d1, "08:00", "18:00"), (d2, "20:00", "22:00")):
        for kind, t in (("in", a), ("out", b)):
            r = admin.post("/api/punches", json={"kind": kind, "employee_id": e["id"],
                                                 "ts": f"{day}T{t}"})
            assert r.status_code == 200, r.text
    return {**e, "d1": d1.isoformat(), "d2": d2.isoformat()}


def _row(admin, eid, period=PREV, detail=False):
    data = admin.get("/api/mgmt", params={"year": period.year, "month": period.month,
                                          "employee_id": eid, "detail": detail}).json()
    assert data["rows"], data
    return data["rows"][0]


def test_view_shows_debt_and_codes(admin, emp):
    row = _row(admin, emp["id"])
    assert row["error"] is None, row["error"]
    assert row["source"] == "view"
    # d1: Я 12, 08:00–18:00 → рабочее 10 ч, недостача 2 ч; d2: В, 20:00–22:00 → ДЯ 2 ч
    assert row["debt"]["total"] == 120
    assert row["ut"][emp["d2"]] == {"ДЯ": 120}
    assert row["state"]["closed"] is False
    assert row["state"]["opening_bank_set"] is True
    card1 = next(c for c in row["days"] if c["day"] == emp["d1"])
    assert (card1["plan_minutes"], card1["work_minutes"], card1["debt_minutes"]) == (720, 600, 120)


def test_view_rejected_when_previous_not_closed(admin):
    """RUL-VIEW-AFTER-PREVIOUS: текущий месяц при незакрытом предыдущем и без посева
    отклоняется типизированной ошибкой (в сетке — строка с error)."""
    r = admin.post("/api/employees", json={
        "full_name": "Незакрытов Незакрыт Незакрытович", "position": "Батлер",
        "hired_at": (TODAY.replace(day=1) - dt.timedelta(days=400)).isoformat(),
        "schedule_group": "Смена 1"})
    assert r.status_code == 200, r.text
    eid = r.json()["id"]
    data = admin.get("/api/mgmt", params={"year": TODAY.year, "month": TODAY.month,
                                          "employee_id": eid}).json()
    row = data["rows"][0]
    assert row["error"] is not None
    assert "предыдущий период" in row["error"]


def test_seed_only_first_period(admin, emp):
    """R37: посев OPENING_SEED разрешён только для первого периода сотрудника."""
    r = admin.post(f"/api/employees/{emp['id']}/bank-adjust", json={
        "hours": 3, "date": TODAY.isoformat(), "note": "посев не в первый период",
        "reason_code": "OPENING_SEED"})
    assert r.status_code == 409, r.text
    assert "первого периода" in r.json()["detail"]


def test_close_then_recalculate_last_closed(admin, emp):
    p = {"year": PREV.year, "month": PREV.month, "employee_ids": [emp["id"]]}
    r = admin.post("/api/mgmt/close", json=p).json()
    assert r["errors"] == [] and r["done"][0]["bank_closed"] == 0
    saved = _row(admin, emp["id"])
    assert saved["source"] == "saved" and saved["state"]["closed"]
    # каскад изъял ДЯ 2 ч в погашение недостачи 2 ч → УТ дня d2 пусто
    assert saved["ut"].get(emp["d2"], {}) == {}
    assert saved["debt"]["residual"] == 0
    assert saved["revision"] == 1
    # повторное закрытие невозможно
    again = admin.post("/api/mgmt/close", json=p).json()
    assert again["errors"] and "уже закрыт" in again["errors"][0]["error"]
    # правка последнего закрытого периода — с предупреждением о пересчёте (16.5)
    r = admin.put("/api/tabel/cell", json={"employee_id": emp["id"], "date": emp["d1"],
                                           "code": "В"})
    assert r.status_code == 200 and "пересчёт" in r.json()["warning"]
    r = admin.post("/api/mgmt/recalculate", json=p).json()
    assert r["errors"] == [], r["errors"]
    saved = _row(admin, emp["id"])
    assert saved["revision"] == 2
    # недостачи больше нет → изъятий нет → ДЯ 2 ч вернулся в УТ
    assert saved["ut"][emp["d2"]] == {"ДЯ": 120}
    assert saved["debt"]["total"] == 0


def test_closed_period_reads_saved_without_recalculation(admin, emp):
    """RUL-CLOSED-PERIOD-IMMUTABLE: правка данных после закрытия не меняет показ."""
    r = admin.post("/api/punches", json={"kind": "in", "employee_id": emp["id"],
                                         "ts": f"{emp['d1']}T06:00"})
    assert r.status_code == 200, r.text
    r = admin.post("/api/punches", json={"kind": "out", "employee_id": emp["id"],
                                         "ts": f"{emp['d1']}T07:00"})
    assert r.status_code == 200, r.text
    saved = _row(admin, emp["id"])
    card1 = next(c for c in saved["days"] if c["day"] == emp["d1"])
    # снимок заморожен: живой расчёт дал бы 660 (06:00–18:00), сохранённый — 600 (08:00–18:00)
    assert card1["fact_minutes"] == 600
    # откат: удаляем добавленные отметки (журнал аудита сохраняет след)
    punches = admin.get("/api/punches", params={"employee_id": emp["id"]}).json()
    for p_ in punches:
        if p_["ts"].startswith(emp["d1"]) and p_["ts"][11:16] in ("06:00", "07:00"):
            admin.delete(f"/api/punches/{p_['id']}")
    admin.post("/api/mgmt/recalculate", json={"year": PREV.year, "month": PREV.month,
                                              "employee_ids": [emp["id"]]})


def test_cannot_close_incomplete_period(admin, emp):
    r = admin.post("/api/mgmt/close", json={"year": TODAY.year, "month": TODAY.month,
                                            "employee_ids": [emp["id"]]}).json()
    assert r["done"] == [] and "не завершён" in r["errors"][0]["error"]


def test_tabel_validation_by_domain_checks(admin, emp):
    """16.5/F-16: валидация записи доменными проверками."""
    r = admin.put("/api/tabel/cell", json={"employee_id": emp["id"],
                                           "date": (PREV + dt.timedelta(days=5)).isoformat(),
                                           "code": "Я"})
    assert r.status_code == 422 and "план" in r.json()["detail"].lower()
    r = admin.put("/api/tabel/cell", json={"employee_id": emp["id"],
                                           "date": (PREV + dt.timedelta(days=5)).isoformat(),
                                           "code": "ХХ"})
    assert r.status_code == 422
    r = admin.put("/api/tabel/cell", json={"employee_id": emp["id"],
                                           "date": (PREV + dt.timedelta(days=5)).isoformat(),
                                           "code": "Я", "hours": 8.3333})
    assert r.status_code == 422      # план не кратен 15 минутам


def test_tabel_values_carry_windows(admin, emp):
    """16.5/UI: редактор ячейки собирает значения плашками из справочников —
    GET /api/tabel отдаёт границы окна (HH:MM) для каждого значения CFG-WINDOWS,
    чтобы подсказка показывала окно, а часы вне справочника нельзя было ввести."""
    data = admin.get("/api/tabel", params={"year": PREV.year, "month": PREV.month}).json()
    assert data["values"], data
    assert set(data["windows"]) == set(data["values"])
    for value, win in data["windows"].items():
        assert len(win) == 2, value
        for hm in win:
            hh, mm = hm.split(":")
            assert len(hh) == 2 and len(mm) == 2 and 0 <= int(hh) <= 23 and int(mm) <= 59
        assert win[0] < win[1], value      # окно не пересекает полночь (3.5)


def test_presence_board_contract(admin):
    r = admin.get("/api/presence/board")
    assert r.status_code == 200
    data = r.json()
    assert {"at_work_now", "expected_now", "open_session_cards", "yet_to_come"} <= set(data)
    assert data["at_work_now"] == len(data["open_session_cards"])


def test_fact_sessions_contract(admin, emp):
    r = admin.get("/api/fact/sessions", params={
        "employee_id": emp["id"], "first": PREV.isoformat(), "last": PREV_END.isoformat()})
    assert r.status_code == 200, r.text
    sessions = r.json()["sessions"]
    assert len(sessions) == 2
    assert sessions[0]["minutes"] == 600          # 08:00–18:00, исходные моменты
    assert sessions[1]["minutes"] == 120


def test_individual_deny_and_group_allow(admin):
    from fastapi.testclient import TestClient

    from app.main import app
    cat = admin.get("/api/access").json()
    gromova = next(u for u in cat["users"] if u["username"] == "gromova")
    ivanov = next(u for u in cat["users"] if u["username"] == "ivanov")
    assert "mgmt.close" in gromova["effective"]
    g = TestClient(app)
    g.post("/api/auth/login", json={"username": "gromova", "password": "demo1234"})
    assert admin.put(f"/api/access/users/{gromova['id']}/grants",
                     json={"grants": {"mgmt.close": "deny"}}).status_code == 200
    assert g.post("/api/mgmt/close", json={"year": PREV.year, "month": PREV.month,
                                           "employee_ids": [0]}).status_code == 403
    admin.put(f"/api/access/users/{gromova['id']}/grants", json={"grants": {}})
    i = TestClient(app)
    i.post("/api/auth/login", json={"username": "ivanov", "password": "demo1234"})
    assert i.get("/api/tabel", params={"year": TODAY.year, "month": TODAY.month}).status_code == 403
    gid = admin.post("/api/access/groups", json={"name": "Табельщики"}).json()["id"]
    admin.put(f"/api/access/groups/{gid}/grants", json={"grants": {"tabel.view": "allow"}})
    admin.put(f"/api/access/groups/{gid}/members", json={"user_ids": [ivanov["id"]]})
    assert i.get("/api/tabel", params={"year": TODAY.year, "month": TODAY.month}).status_code == 200
    assert "tabel.view" in i.get("/api/auth/me").json()["permissions"]
    admin.put(f"/api/access/users/{ivanov['id']}/grants", json={"grants": {"tabel.view": "deny"}})
    assert i.get("/api/tabel", params={"year": TODAY.year, "month": TODAY.month}).status_code == 403
    admin.put(f"/api/access/users/{ivanov['id']}/grants", json={"grants": {}})
    assert admin.delete(f"/api/access/groups/{gid}").status_code == 200
    assert i.get("/api/tabel", params={"year": TODAY.year, "month": TODAY.month}).status_code == 403
    assert i.get("/api/access").status_code == 403


def test_role_override(admin):
    from fastapi.testclient import TestClient

    from app.main import app
    i = TestClient(app)
    i.post("/api/auth/login", json={"username": "ivanov", "password": "demo1234"})
    assert i.get("/api/presence/board").status_code == 200
    admin.put("/api/access/roles/employee", json={"grants": {"presence.view": "deny"}})
    assert i.get("/api/presence/board").status_code == 403
    admin.put("/api/access/roles/employee", json={"grants": {}})
    assert i.get("/api/presence/board").status_code == 200


def test_engine_settings_validation(admin):
    """Уровень 1 валидации: все нарушения сообщаются разом (5.3)."""
    r = admin.get("/api/engine-settings")
    assert r.status_code == 200
    payload = r.json()["active"]["payload"]
    payload["step_minutes"] = 45                      # CHK-STEP-DIVIDES-60
    payload["cascade_order"] = ["ДЯ"]                 # CHK-CASCADE-FULL
    bad = {"year": TODAY.year, "month": TODAY.month}
    r = admin.put("/api/engine-settings", json={
        "valid_from": f"{bad['year']}-{bad['month']:02d}-01", "payload": payload, "note": "test"})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "CHK-STEP-DIVIDES-60" in detail and "CHK-CASCADE-FULL" in detail


def test_mgmt_xlsx_export(admin, emp):
    r = admin.get("/api/mgmt/xlsx", params={"year": PREV.year, "month": PREV.month})
    assert r.status_code == 200
    assert r.content[:2] == b"PK"
