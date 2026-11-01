"""Ревью этапа 5: шаблон по гостям поверх «вся бронь», шаблон группы без двойного «целиком»,
правка по дням пакетом, скорость шахматки батлеров, бюджет табло со строками покрытия."""
from __future__ import annotations

import datetime as dt

from .helpers import API, create_res, make_category, make_guest


def _card(c, rid):
    return c.get(f"{API}/reservations/{rid}/card").json()


def _tpl(c, **body):
    return c.post(f"{API}/coverage/template", json={"kind": "single", "replace": False, **body})


def test_template_for_guest_over_whole_booking(manager_role_client, manager_client, butlers):
    """I1: разделить гостей шаблоном — явный гость поверх «вся бронь» записывается."""
    a, b = butlers["a"], butlers["b"]
    d0 = butlers["days"][3]
    cat = make_category(manager_role_client)
    g1, g2 = make_guest(manager_client), make_guest(manager_client)
    r = create_res(manager_client, cat, d0.isoformat(), (d0 + dt.timedelta(days=2)).isoformat(),
                   [(g1["id"], "main", None, None), (g2["id"], "guest", None, None)])
    span = {"first": d0.isoformat(), "last": (d0 + dt.timedelta(days=1)).isoformat()}
    assert _tpl(manager_client, reservation_id=r["id"], butlers=[a], **span).json()["result"]["written"] == 2
    got = _tpl(manager_client, reservation_id=r["id"], butlers=[b], guest_ids=[g2["id"]], **span)
    assert got.json()["result"]["written"] == 2
    pairs = {(x["employee_id"], tuple(x["guest_ids"])) for x in _card(manager_client, r["id"])["coverage"][0]["butlers"]}
    assert pairs == {(a, (g1["id"],)), (b, (g2["id"],))}


def test_group_template_skips_partially_covered_day(manager_role_client, manager_client, butlers):
    """I2: у брони A день уже покрыт её строкой — шаблон группы не добавляет второго «целиком»."""
    a, b = butlers["a"], butlers["b"]
    d0 = butlers["days"][4]
    cat = make_category(manager_role_client)
    gid = manager_client.post(f"{API}/groups", json={"title": "Г"}).json()["id"]
    ra = create_res(manager_client, cat, d0.isoformat(), (d0 + dt.timedelta(days=1)).isoformat(),
                    [(make_guest(manager_client)["id"], "main", None, None)], group_id=gid)
    create_res(manager_client, cat, d0.isoformat(), (d0 + dt.timedelta(days=1)).isoformat(),
               [(make_guest(manager_client)["id"], "main", None, None)], group_id=gid)
    manager_client.put(f"{API}/coverage/day", json={"day": d0.isoformat(), "reservation_id": ra["id"], "employee_id": a})
    got = _tpl(manager_client, group_id=gid, butlers=[b], first=d0.isoformat(), last=d0.isoformat())
    assert got.json()["result"]["written"] == 0
    assert [x["employee_id"] for x in _card(manager_client, ra["id"])["coverage"][0]["butlers"]] == [a]


def test_double_whole_cover_warns():
    """I2: два батлера «целиком» у одного гостя — предупреждение double_cover."""
    from datetime import date

    from app.modules.stays.domain.coverage import resolve_day
    from app.modules.stays.domain.types import Line, StayDay
    d = date(2030, 1, 1)
    s = StayDay(d, 10, 7, 100, "1", 4.0, True, False, {50: "regular"})
    cover = resolve_day([s], [Line(1, d, 1, 10, None, frozenset(), "manual", False),
                              Line(2, d, 2, None, 7, frozenset(), "manual", False)])
    assert cover.double == [(10, 50, (1, 2))]


def test_set_days_batch_with_preview(manager_role_client, manager_client, butlers):
    """I3: правка по дням — одна операция с предпросмотром: батлер на день или «нет»."""
    a, b = butlers["a"], butlers["b"]
    d0 = butlers["days"][5]
    cat = make_category(manager_role_client)
    r = create_res(manager_client, cat, d0.isoformat(), (d0 + dt.timedelta(days=2)).isoformat(),
                   [(make_guest(manager_client)["id"], "main", None, None)])
    body = {"reservation_id": r["id"], "days": [{"day": d0.isoformat(), "employee_id": a},
                                                {"day": (d0 + dt.timedelta(days=1)).isoformat(), "employee_id": b}]}
    pv = manager_client.put(f"{API}/coverage/days", params={"preview": 1}, json=body).json()
    assert {c["employee_id"] for c in pv["diff"]["coverage_changes"]} == {a, b}
    sv = manager_client.put(f"{API}/coverage/days", json=body).json()
    assert sv["diff"] == pv["diff"]
    cov = _card(manager_client, r["id"])["coverage"]
    assert [[x["employee_id"] for x in d["butlers"]] for d in cov] == [[a], [b]]
    body["days"] = [{"day": d0.isoformat(), "employee_id": None}]
    assert manager_client.put(f"{API}/coverage/days", json=body).status_code == 200
    assert _card(manager_client, r["id"])["coverage"][0]["butlers"] == []


def test_butlers_board_memoizes_days(monkeypatch, db):
    """I4: контекст считает stays_on и warnings один раз на день, а не на каждого батлера."""
    from app.core.time import local_date
    from app.modules.stays.adapters.duty_timesheet import TimesheetDuty
    from app.modules.stays.application import context as ctxmod
    from app.modules.stays.application.boards import butlers_board
    calls = {"n": 0}
    orig = ctxmod.StaysContext._stays_on

    def counted(self, day):
        calls["n"] += 1
        return orig(self, day)
    monkeypatch.setattr(ctxmod.StaysContext, "_stays_on", counted)
    first = local_date()
    body = butlers_board(db, first, first + dt.timedelta(days=6), TimesheetDuty(db))
    assert len(body["rows"]) >= 5
    assert calls["n"] <= 7 * 2


def test_day_board_budget_with_coverage(manager_client, sql_counter):
    """I5: табло дня полного уровня со строками покрытия и дырами — не больше 32 запросов (30 + один
    на семейные связи: родственники среди проживающих, addendum §4, + один на OOO дня — часть 2 §6)."""
    from app.core.time import local_date
    day = local_date() + dt.timedelta(days=3)          # демо-данные: батлеры, строки, дыры
    with sql_counter() as c:
        r = manager_client.get(f"{API}/day", params={"date": day.isoformat()})
    assert r.status_code == 200 and r.json()["totals"]["covered"] > 0 and r.json()["totals"]["uncovered"] > 0
    assert c["total"] <= 32, sorted(c["by_statement"].items(), key=lambda x: -x[1])[:5]


def test_butlers_board_budget_with_coverage(manager_client, sql_counter):
    from app.core.time import local_date
    first = local_date()
    with sql_counter() as c:
        r = manager_client.get(f"{API}/board/butlers", params={"first": first.isoformat(),
                                                                "last": (first + dt.timedelta(days=13)).isoformat()})
    assert r.status_code == 200 and any(cell["units"] for row in r.json()["rows"] for cell in row["cells"])
    assert c["total"] <= 30, sorted(c["by_statement"].items(), key=lambda x: -x[1])[:5]
