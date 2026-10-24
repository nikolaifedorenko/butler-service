"""Ревью этапа 4: строки старой группы, двойное покрытие, бюджет шахматки с «сегодня»,
список подмены пакетно, «добавить смену» не затирает существующую."""
from __future__ import annotations

import datetime as dt

from .helpers import API, create_res, make_category, make_guest


def _card(c, rid):
    return c.get(f"{API}/reservations/{rid}/card").json()


def _group_pair(sup, mgr, butlers, nights_a=4, nights_b=2):
    cat = make_category(sup, n_units=2)
    gid = mgr.post(f"{API}/groups", json={"title": "Г"}).json()["id"]
    d0 = butlers["days"][2]
    ga, gb = make_guest(mgr), make_guest(mgr)
    a = create_res(mgr, cat, d0.isoformat(), (d0 + dt.timedelta(days=nights_a)).isoformat(),
                   [(ga["id"], "main", None, None)], group_id=gid)
    b = create_res(mgr, cat, d0.isoformat(), (d0 + dt.timedelta(days=nights_b)).isoformat(),
                   [(gb["id"], "main", None, None)], group_id=gid)
    return cat, gid, d0, a, b, ga, gb


def test_group_lines_cleaned_when_member_leaves(manager_role_client, manager_client, butlers, db):
    """I1: бронь ушла из группы — строки группы на её дни снимаются."""
    cat, gid, d0, a, b, ga, gb = _group_pair(manager_role_client, manager_client, butlers)
    r = manager_client.post(f"{API}/coverage/template", json={
        "group_id": gid, "kind": "single", "butlers": [butlers["a"]], "first": d0.isoformat(),
        "last": (d0 + dt.timedelta(days=3)).isoformat()})
    assert r.status_code == 200 and r.json()["result"]["written"] == 4
    cur = manager_client.get(f"{API}/reservations/{a['id']}").json()
    body = {**{k: cur[k] for k in ("number", "check_in", "check_out", "category_id")}, "group_id": None,
            "occupants": cur["occupants"], "version": cur["version"]}
    assert manager_client.put(f"{API}/reservations/{a['id']}", json=body).status_code == 200
    days_b = [d["day"] for d in _card(manager_client, b["id"])["coverage"] if d["butlers"]]
    assert days_b == [d0.isoformat(), (d0 + dt.timedelta(days=1)).isoformat()]
    from sqlalchemy import select

    from app.modules.stays.adapters.orm import CoverageLine
    db.expire_all()
    left = sorted(d.isoformat() for d in db.scalars(select(CoverageLine.day).where(CoverageLine.group_id == gid)))
    assert left == days_b                             # строки группы на дни 3–4 сняты


def test_template_skips_days_covered_by_group_line(manager_role_client, manager_client, butlers):
    """I2: шаблон по брони не дублирует день, уже покрытый строкой группы."""
    cat, gid, d0, a, b, ga, gb = _group_pair(manager_role_client, manager_client, butlers, 2, 2)
    manager_client.put(f"{API}/coverage/day", json={"day": d0.isoformat(), "group_id": gid,
                                                    "employee_id": butlers["a"]})
    r = manager_client.post(f"{API}/coverage/template", json={
        "reservation_id": a["id"], "kind": "single", "butlers": [butlers["b"]], "first": d0.isoformat(),
        "last": (d0 + dt.timedelta(days=1)).isoformat()})
    assert r.json()["result"]["written"] == 1
    first_day = _card(manager_client, a["id"])["coverage"][0]
    assert [x["employee_id"] for x in first_day["butlers"]] == [butlers["a"]]


def test_set_day_refuses_double_whole_cover(manager_role_client, manager_client, butlers):
    cat, gid, d0, a, b, ga, gb = _group_pair(manager_role_client, manager_client, butlers, 2, 2)
    manager_client.put(f"{API}/coverage/day", json={"day": d0.isoformat(), "group_id": gid,
                                                    "employee_id": butlers["a"]})
    r = manager_client.put(f"{API}/coverage/day", json={"day": d0.isoformat(), "reservation_id": a["id"],
                                                        "employee_id": butlers["b"]})
    assert r.status_code == 422 and r.json()["detail"] == "Гостей в этот день уже ведёт другая строка — измените её"
    r = manager_client.put(f"{API}/coverage/day", json={"day": d0.isoformat(), "reservation_id": a["id"],
                                                        "guest_ids": [ga["id"]], "employee_id": butlers["b"]})
    assert r.status_code == 200                       # явный гость сильнее «всей группы» — это не дубль


def test_board_budget_with_today_in_window(manager_client, big_fund, sql_counter, monkeypatch):
    """I3: шахматка за период с «сегодня» — тоже не больше 30 запросов."""
    from app.modules.stays.application import views
    monkeypatch.setattr(views, "local_date", lambda: dt.date(2029, 6, 15))
    with sql_counter() as c:
        r = manager_client.get(f"{API}/board/units", params=big_fund)
    assert r.status_code == 200
    assert c["total"] <= 30, sorted(c["by_statement"].items(), key=lambda x: -x[1])[:3]


def test_replacements_constant_queries(manager_role_client, manager_client, butlers, db, sql_counter):
    """I4: список «нужна подмена» не растёт по запросам с числом предупреждений."""
    from sqlalchemy import select

    from app.modules.timesheet.application.catalog import TabelDay
    a = butlers["a"]
    days = butlers["days"][8:12]
    cat = make_category(manager_role_client, n_units=4)
    for _ in range(3):
        g = make_guest(manager_client)
        r = create_res(manager_client, cat, days[0].isoformat(), (days[-1] + dt.timedelta(days=1)).isoformat(),
                       [(g["id"], "main", None, None)])
        manager_client.post(f"{API}/coverage/template", json={"reservation_id": r["id"], "kind": "single",
                                                              "butlers": [a], "first": days[0].isoformat(),
                                                              "last": days[-1].isoformat()})
    rows = list(db.scalars(select(TabelDay).where(TabelDay.employee_id == a, TabelDay.date.in_(days))))
    old = {t.id: t.code for t in rows}
    try:
        for t in rows:
            t.code = "ОТ"
        db.commit()
        with sql_counter() as c:
            got = manager_client.get(f"{API}/coverage/replacements", params={
                "first": days[0].isoformat(), "last": days[-1].isoformat()}).json()
        assert len([x for x in got if x["employee_id"] == a]) >= len(rows) * 3
        assert c["total"] <= 40, sorted(c["by_statement"].items(), key=lambda x: -x[1])[:3]
    finally:
        for t in rows:
            t.code = old[t.id]
        db.commit()


def test_add_shift_refuses_when_shift_exists(manager_client, butlers, db):
    """M7→Important: «Добавить смену» не затирает существующую смену дня."""
    from sqlalchemy import select

    from app.modules.timesheet.application.catalog import ShiftType
    a = butlers["a"]
    on = next(d for d in butlers["days"] if butlers["on"](a, d))
    kind = db.scalar(select(ShiftType).where(ShiftType.kind == "work").order_by(ShiftType.id))
    r = manager_client.post(f"{API}/coverage/add-shift", json={"employee_id": a, "day": on.isoformat(),
                                                                 "shift_type_id": kind.id})
    assert r.status_code == 422 and r.json()["detail"] == "У сотрудника уже есть смена в этот день"
