"""Шахматка, задача 14: покрытие батлерами — шаблоны, ручная правка, предупреждения против
актуального Графика, «добавить смену», подбор, чистка строк, дельта в предпросмотре."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select

from app.core.audit import AuditLog

from .helpers import API, create_res, make_category, make_guest


def _res(sup, mgr, butlers, nights=6, guests=1, **kw):
    cat = make_category(sup, n_units=2)
    gs = [make_guest(mgr) for _ in range(guests)]
    ci, co = butlers["days"][0], butlers["days"][0] + dt.timedelta(days=nights)
    occ = [(gs[0]["id"], "main", None, None)] + [(g["id"], "guest", None, None) for g in gs[1:]]
    return cat, gs, create_res(mgr, cat, ci.isoformat(), co.isoformat(), occ, **kw)


def _template(c, res, kind, emps, nights=6, **kw):
    first = dt.date.fromisoformat(res["check_in"])
    body = {"reservation_id": res["id"], "kind": kind, "butlers": emps, "first": first.isoformat(),
            "last": (first + dt.timedelta(days=nights - 1)).isoformat(), "replace": False, **kw}
    return c.post(f"{API}/coverage/template", json=body)


def _card(c, rid):
    return c.get(f"{API}/reservations/{rid}/card").json()


def _kinds(card, day):
    row = next(d for d in card["coverage"] if d["day"] == day.isoformat())
    return {w["kind"] for w in row["warnings"]}


def test_template_pair_by_schedule(manager_role_client, manager_client, butlers):
    _, _, res = _res(manager_role_client, manager_client, butlers)
    a, b = butlers["a"], butlers["b"]
    r = _template(manager_client, res, "pair", [a, b])
    assert r.status_code == 200, r.text
    cov = {d["day"]: [x["employee_id"] for x in d["butlers"]] for d in _card(manager_client, res["id"])["coverage"]}
    for d in butlers["days"][:6]:
        want = a if butlers["on"](a, d) else b if butlers["on"](b, d) else None
        assert cov[d.isoformat()] == ([want] if want else []), d


def test_template_requires_escort(manager_role_client, manager_client, butlers, db):
    from app.modules.employees.application.catalog import Employee
    _, _, res = _res(manager_role_client, manager_client, butlers)
    stranger = db.scalar(select(Employee.id).where(Employee.full_name.like("Соколова%")))
    r = _template(manager_client, res, "single", [stranger])
    assert r.status_code == 422 and r.json()["detail"] == "Батлер не в списке «Сопровождают гостей»"


def test_hole_without_butler(manager_role_client, manager_client, butlers):
    _, _, res = _res(manager_role_client, manager_client, butlers, nights=2)
    assert "hole" in _kinds(_card(manager_client, res["id"]), butlers["days"][0])


def test_off_shift_warning_and_add_shift(manager_role_client, manager_client, butlers, db):
    from app.modules.timesheet.application.catalog import ShiftType, TabelDay
    a = butlers["a"]
    _, _, res = _res(manager_role_client, manager_client, butlers)
    assert _template(manager_client, res, "single", [a]).status_code == 200
    off = [d for d in butlers["days"][:6] if not butlers["on"](a, d)]
    assert off, "в 2/2 за 6 дней есть выходные"
    card = _card(manager_client, res["id"])
    assert all("off_shift" in _kinds(card, d) for d in off)
    kind = db.scalar(select(ShiftType).where(ShiftType.kind == "work").order_by(ShiftType.id))
    tabel_before = db.scalar(select(func.count(TabelDay.id)))
    r = manager_client.post(f"{API}/coverage/add-shift", json={"employee_id": a, "day": off[0].isoformat(),
                                                                 "shift_type_id": kind.id})
    assert r.status_code == 200, r.text
    card = _card(manager_client, res["id"])
    assert "off_shift" not in _kinds(card, off[0])
    assert db.scalar(select(func.count(TabelDay.id))) == tabel_before          # Табель не тронут
    actions = set(db.scalars(select(AuditLog.action).order_by(AuditLog.id.desc()).limit(2)))
    assert actions == {"schedule_manual_shift", "stays_add_shift"}
    # «актуальность»: смену в Графике сняли — следующее чтение снова «вне смены»
    assert manager_client.delete("/api/schedule/shift", params={"employee_id": a, "date": off[0].isoformat()}).status_code == 200
    assert "off_shift" in _kinds(_card(manager_client, res["id"]), off[0])


def test_add_shift_requires_schedule_edit(assign_only_client, butlers):
    r = assign_only_client.post(f"{API}/coverage/add-shift", json={"employee_id": butlers["a"],
                                                                     "day": butlers["days"][0].isoformat(),
                                                                     "shift_type_id": 1})
    assert r.status_code == 403 and r.json()["detail"] == "Нужно право на правку Графика"


def test_vacation_in_schedule_gives_replacement(manager_role_client, manager_client, butlers, db):
    """«На что смотреть» №3: отпуск поставили после назначения — «нужна подмена»."""
    from app.modules.timesheet.application.catalog import TabelDay
    a = butlers["a"]
    _, _, res = _res(manager_role_client, manager_client, butlers, nights=2)
    assert _template(manager_client, res, "single", [a], nights=2).status_code == 200
    day = butlers["days"][0]
    row = db.scalar(select(TabelDay).where(TabelDay.employee_id == a, TabelDay.date == day))
    old = row.code
    try:
        row.code = "ОТ"
        db.commit()
        kinds = _kinds(_card(manager_client, res["id"]), day)
        assert "need_replacement" in kinds and "off_shift" not in kinds
        repl = manager_client.get(f"{API}/coverage/replacements", params={"first": day.isoformat(),
                                                                           "last": day.isoformat()}).json()
        assert any(x["reservation_id"] == res["id"] and x["employee_id"] == a for x in repl)
    finally:
        row.code = old
        db.commit()


def test_explicit_guest_split(manager_role_client, manager_client, butlers):
    a, b = butlers["a"], butlers["b"]
    _, gs, res = _res(manager_role_client, manager_client, butlers, nights=1, guests=2)
    day = butlers["days"][0].isoformat()
    for emp, guests in ((a, []), (b, [gs[1]["id"]])):
        r = manager_client.put(f"{API}/coverage/day", json={"day": day, "reservation_id": res["id"],
                                                             "guest_ids": guests, "employee_id": emp})
        assert r.status_code == 200, r.text
    row = _card(manager_client, res["id"])["coverage"][0]
    pairs = {(x["employee_id"], tuple(x["guest_ids"])) for x in row["butlers"]}
    assert pairs == {(a, (gs[0]["id"],)), (b, (gs[1]["id"],))}


def test_cleanup_on_early_checkout(manager_role_client, manager_client, butlers, db):
    _, _, res = _res(manager_role_client, manager_client, butlers, nights=4)
    assert _template(manager_client, res, "single", [butlers["a"]], nights=4).status_code == 200
    full = manager_client.get(f"{API}/reservations/{res['id']}").json()
    new_out = dt.date.fromisoformat(res["check_in"]) + dt.timedelta(days=2)
    body = {**{k: full[k] for k in ("number", "check_in", "category_id")}, "check_out": new_out.isoformat(),
            "occupants": [{**o, "date_to": new_out.isoformat()} for o in full["occupants"]], "version": full["version"]}
    assert manager_client.put(f"{API}/reservations/{res['id']}", json=body).status_code == 200
    days = [d["day"] for d in _card(manager_client, res["id"])["coverage"] if d["butlers"]]
    assert len(days) == 2
    row = db.scalars(select(AuditLog).where(AuditLog.action == "stays_coverage_cleanup",
                                            AuditLog.target == f"reservation:{res['id']}")).first()
    assert row is not None and '"days"' in row.payload_json


def test_no_show_removes_coverage(manager_role_client, manager_client, butlers, today):
    _, _, res = _res(manager_role_client, manager_client, butlers, nights=2)
    assert _template(manager_client, res, "single", [butlers["a"]], nights=2).status_code == 200
    today(res["check_in"])
    r = manager_client.post(f"{API}/reservations/{res['id']}/status", json={"status": "no_show", "version": res["version"]})
    assert r.status_code == 200
    assert all(not d["butlers"] for d in _card(manager_client, res["id"])["coverage"])


def test_preview_equals_save_coverage_ops(manager_role_client, manager_client, butlers):
    a, b = butlers["a"], butlers["b"]
    _, gs, res = _res(manager_role_client, manager_client, butlers, nights=3)
    assert _template(manager_client, res, "single", [a], nights=3).status_code == 200
    body = {"reservation_id": res["id"], "kind": "single", "butlers": [b], "first": res["check_in"],
            "last": (dt.date.fromisoformat(res["check_in"]) + dt.timedelta(days=2)).isoformat(), "replace": True}
    pv = manager_client.post(f"{API}/coverage/template", params={"preview": 1}, json=body).json()
    lost = {(c["day"], c["employee_id"]) for c in pv["diff"]["coverage_changes"] if c["lost"]}
    gained = {(c["day"], c["employee_id"]) for c in pv["diff"]["coverage_changes"] if c["gained"]}
    assert {e for _, e in lost} == {a} and {e for _, e in gained} == {b} and len(lost) == len(gained) == 3
    assert {c["employee_id"] for c in pv["diff"]["load_changes"]} == {a, b}
    assert all(c["employee_id"] == a for c in _card(manager_client, res["id"])["coverage"][0]["butlers"])
    sv = manager_client.post(f"{API}/coverage/template", json=body).json()
    assert sv["diff"] == pv["diff"]
    day = res["check_in"]
    line = _card(manager_client, res["id"])["coverage"][0]["butlers"][0]
    for params in ({"preview": 1}, {}):
        r = manager_client.delete(f"{API}/coverage/{line['line_id']}", params=params)
        assert r.status_code == 200
    assert not next(d for d in _card(manager_client, res["id"])["coverage"] if d["day"] == day)["butlers"]


def test_candidates_known_guest_first(manager_role_client, manager_client, butlers):
    a, b = butlers["a"], butlers["b"]
    late = butlers["days"][7:]                      # брони других тестов живут в первую неделю окна
    day = next((d for d in late if butlers["on"](a, d) and butlers["on"](b, d)), None)
    if day is None:
        day = next(d for d in late if butlers["on"](a, d) or butlers["on"](b, d))
    cat = make_category(manager_role_client)
    g = make_guest(manager_client)
    past = create_res(manager_client, cat, "2026-01-05", "2026-01-07", [(g["id"], "main", None, None)])
    manager_client.put(f"{API}/coverage/day", json={"day": "2026-01-05", "reservation_id": past["id"],
                                                    "guest_ids": [], "employee_id": b})
    res = create_res(manager_client, cat, day.isoformat(), (day + dt.timedelta(days=1)).isoformat(),
                     [(g["id"], "main", None, None)])
    got = manager_client.get(f"{API}/coverage/candidates", params={"day": day.isoformat(),
                                                                   "reservation_id": res["id"]}).json()
    on_shift = [x for x in (a, b) if butlers["on"](x, day)]
    assert [c["employee_id"] for c in got if c["employee_id"] in (a, b)][:len(on_shift)] == sorted(
        on_shift, key=lambda e: e != b)
    if b in on_shift:
        assert next(c for c in got if c["employee_id"] == b)["knows_guest"] is True
