"""Шахматка, задача 15: шахматка батлеров — фон дня по Графику, объекты, нагрузка, красное."""
from __future__ import annotations

import datetime as dt

from .helpers import API, create_res, make_category, make_guest


def _board(c, butlers, days):
    return c.get(f"{API}/board/butlers", params={"first": days[0].isoformat(), "last": days[-1].isoformat()})


def _cell(body, emp, day):
    row = next(r for r in body["rows"] if r["employee_id"] == emp)
    return next(c for c in row["cells"] if c["day"] == day.isoformat())


def test_butlers_board_shift_background(manager_client, butlers):
    days = butlers["days"][7:]
    body = _board(manager_client, butlers, days).json()
    for d in days:
        cell = _cell(body, butlers["a"], d)
        assert cell["duty"] == ("shift" if butlers["on"](butlers["a"], d) else "off"), d


def test_butlers_board_units_and_overload(manager_role_client, manager_client, butlers):
    a = butlers["a"]
    day = butlers["days"][9]
    cat = make_category(manager_role_client, n_units=3)
    for _ in range(3):
        g = make_guest(manager_client)
        r = create_res(manager_client, cat, day.isoformat(), (day + dt.timedelta(days=1)).isoformat(),
                       [(g["id"], "main", None, None)])
        resp = manager_client.put(f"{API}/coverage/day", json={"day": day.isoformat(), "reservation_id": r["id"],
                                                                "employee_id": a})
        assert resp.status_code == 200, resp.text
    cell = _cell(_board(manager_client, butlers, [day]).json(), a, day)
    assert {u["label"] for u in cell["units"]} >= {u["label"] for u in cat["units"]}
    assert cell["load"] >= 12 and "overload" in cell["warnings"]


def test_butlers_board_forbidden_for_occupancy(occupancy_client, butlers):
    assert _board(occupancy_client, butlers, butlers["days"][:2]).status_code == 403


def test_butlers_board_query_budget(manager_client, big_fund, sql_counter):
    with sql_counter() as c:
        r = manager_client.get(f"{API}/board/butlers", params=big_fund)
    assert r.status_code == 200
    assert c["total"] <= 30, sorted(c["by_statement"].items(), key=lambda x: -x[1])[:3]
