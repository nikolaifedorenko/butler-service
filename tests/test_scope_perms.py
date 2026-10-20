"""Ключи скоупа §5.2 (батч 20.10.2026): «менеджерская видимость и действия» —
права каталога, а не роль.

Пять новых ключей (fact.view_all, punches.view_all, punches.punch_for_others,
punches.backfill, schedule.view_all) базово выданы тем же ролям, что и прежнее
`is_manager` (MANAGER_ROLES = admin/manager/supervisor) — поведение ролей по
умолчанию НЕ изменилось. Новое: ключи выдаются/снимаются грантами в «Правах
доступа» — тесты проверяют и дефолтную аудиторию, и управляемость (выдать
батлеру, снять с менеджера).
"""
from __future__ import annotations

import datetime as dt

NEW_KEYS = {
    "fact.view_all": "Факт",
    "punches.view_all": "Отметки",
    "punches.punch_for_others": "Отметки",
    "punches.backfill": "Отметки",
    "schedule.view_all": "График",
}


def _catalog(admin_client):
    return admin_client.get("/api/access").json()


def _user_id(cat, username):
    return next(u for u in cat["users"] if u["username"] == username)["id"]


def _grant(admin_client, uid, grants):
    r = admin_client.put(f"/api/access/users/{uid}/grants", json={"grants": grants})
    assert r.status_code == 200, r.text


def test_klyuchi_v_kataloge_i_defoltnaya_auditoriya(admin_client):
    """Ключи в каталоге; supervisor/manager получают их базово (аудитория
    прежнего is_manager), employee — нет."""
    cat = _catalog(admin_client)
    keys = {p["key"]: p for p in cat["permissions"]}
    for key, section in NEW_KEYS.items():
        assert key in keys, key
        assert keys[key]["section"] == section
    by_name = {u["username"]: u for u in cat["users"]}
    for boss in ("gromova", "smirnov", "admin"):       # supervisor, manager, admin
        assert set(NEW_KEYS) <= set(by_name[boss]["effective"]), boss
    assert not (set(NEW_KEYS) & set(by_name["ivanov"]["effective"]))


def test_fact_sessions_skop(admin_client, employee_client):
    """История сессий: без fact.view_all — только своя (403 на чужую),
    с грантом батлеру — чужая доступна."""
    me = employee_client.get("/api/auth/me").json()["user"]
    emps = admin_client.get("/api/employees").json()
    other = next(e for e in emps if e["id"] != me["employee_id"])
    today = dt.date.today()
    params = {"employee_id": other["id"], "first": today.isoformat(),
              "last": today.isoformat()}
    r = employee_client.get("/api/fact/sessions", params=params)
    assert r.status_code == 403 and "своя история сессий" in r.json()["detail"]

    uid = _user_id(_catalog(admin_client), "ivanov")
    try:
        _grant(admin_client, uid, {"fact.view_all": "allow"})
        r = employee_client.get("/api/fact/sessions", params=params)
        assert r.status_code == 200, r.text
    finally:
        _grant(admin_client, uid, {})


def test_punches_backfill_pravo(admin_client, employee_client):
    """Отметка задним числом — два гейта: punches.manage (гейт эндпоинта для
    ts/чужих) и punches.backfill (бывш. ролевое is_manager, §5.2). Без второго
    даже держатель manage упирается в 403 «задним числом»."""
    ts = (dt.datetime.now() - dt.timedelta(hours=1)).isoformat(timespec="minutes")
    body = {"kind": "IN", "ts": ts}
    r = employee_client.post("/api/punches", json=body)
    assert r.status_code == 403 and "punches.manage" in r.json()["detail"]

    uid = _user_id(_catalog(admin_client), "ivanov")
    punch_id = None
    try:
        _grant(admin_client, uid, {"punches.manage": "allow"})
        r = employee_client.post("/api/punches", json=body)
        assert r.status_code == 403 and "задним числом" in r.json()["detail"], r.text
        _grant(admin_client, uid, {"punches.manage": "allow",
                                   "punches.backfill": "allow"})
        r = employee_client.post("/api/punches", json=body)
        assert not (r.status_code == 403
                    and "задним числом" in r.json().get("detail", "")), r.text
        if r.status_code == 200:
            punch_id = r.json().get("id")
    finally:
        _grant(admin_client, uid, {})
        if punch_id:
            admin_client.delete(f"/api/punches/{punch_id}")


def test_punches_journal_skop(admin_client, employee_client):
    """Журнал отметок: без punches.view_all — только свои; с грантом — видны чужие."""
    me = employee_client.get("/api/auth/me").json()["user"]
    rows = employee_client.get("/api/punches").json()
    assert rows and all(r["employee_id"] == me["employee_id"] for r in rows)

    uid = _user_id(_catalog(admin_client), "ivanov")
    try:
        _grant(admin_client, uid, {"punches.view_all": "allow"})
        rows = employee_client.get("/api/punches").json()
        assert {r["employee_id"] for r in rows} - {me["employee_id"]}, \
            "с грантом punches.view_all журнал обязан показывать и чужие отметки"
    finally:
        _grant(admin_client, uid, {})


def test_schedule_setka_skop_i_readonly(admin_client, employee_client):
    """Сетка Графика: без schedule.view_all ячейки срезаются до плана
    (_strip_to_plan: без заметок и id записей); readonly — по schedule.edit.
    Видимость всех строк даёт schedule.view (базовое) — ключи скоупа её не меняют."""
    def all_shifts(data):
        return [sh for row in data["rows"] for cell in row["cells"].values()
                for sh in cell["shifts"]]

    today = dt.date.today()
    params = {"year": today.year, "month": today.month}
    r = employee_client.get("/api/schedule", params=params)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["readonly"] is True
    shifts = all_shifts(data)
    assert shifts and all("id" not in sh for sh in shifts), "без права ячейки срезаются до плана"

    uid = _user_id(_catalog(admin_client), "ivanov")
    try:
        _grant(admin_client, uid, {"schedule.view_all": "allow",
                                   "schedule.edit": "allow"})
        data = employee_client.get("/api/schedule", params=params).json()
        assert data["readonly"] is False
        assert any("id" in sh for sh in all_shifts(data)), "с правом видны полные данные ячеек"
    finally:
        _grant(admin_client, uid, {})


def test_deny_snimaet_pravo_s_managera(admin_client, manager_role_client):
    """Управляемость в обе стороны: deny-грант снимает punches.backfill
    с менеджера (роль больше не решает)."""
    cat = _catalog(admin_client)
    uid = _user_id(cat, "smirnov")
    ts = (dt.datetime.now() - dt.timedelta(hours=1)).isoformat(timespec="minutes")
    r = manager_role_client.post("/api/punches", json={"kind": "IN", "ts": ts})
    assert not (r.status_code == 403 and "задним числом" in r.json().get("detail", "")), \
        "у менеджера backfill есть базово"
    punch_id = r.json().get("id") if r.status_code == 200 else None
    try:
        _grant(admin_client, uid, {"punches.backfill": "deny"})
        r = manager_role_client.post("/api/punches", json={"kind": "IN", "ts": ts})
        assert r.status_code == 403 and "задним числом" in r.json()["detail"]
    finally:
        _grant(admin_client, uid, {})
        if punch_id:
            admin_client.delete(f"/api/punches/{punch_id}")
