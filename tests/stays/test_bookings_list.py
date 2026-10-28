"""Вкладка «Брони» (спецификация фонда по версиям §8): режимы попадания в период, сортировка,
пагинация, уровни видимости, поиск по телефону, фильтры §7, бюджет SQL, выгрузка в Excel."""
from __future__ import annotations

import io
import json

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from app.core.audit import AuditLog
from app.modules.stays.domain.allocate import natural_key

from .helpers import API, create_res, make_category, make_guest, uniq
from .test_board_filters import _flag, _groups, _set_flag

URL = f"{API}/bookings"


def _get(c, **params) -> dict:
    r = c.get(URL, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _numbers(c, **params) -> list[str]:
    return [row["number"] for row in _get(c, **params)["rows"]]


def test_modes_stay_checkin_checkout_created(manager_role_client, manager_client, db):
    from datetime import datetime

    from app.modules.stays.adapters.orm import Reservation
    cat = make_category(manager_role_client, n_units=4)
    a = create_res(manager_client, cat, "2038-03-01", "2038-03-05", number="A" + uniq())     # внутри окна
    b = create_res(manager_client, cat, "2038-02-25", "2038-03-03", number="B" + uniq())     # заехала до, выезд в окне
    c = create_res(manager_client, cat, "2038-03-08", "2038-03-12", number="C" + uniq())     # заезд после окна
    d = create_res(manager_client, cat, "2038-02-20", "2038-03-20", number="D" + uniq())     # накрывает окно
    for r, day in ((a, datetime(2038, 1, 5, 10)), (b, datetime(2038, 3, 4, 9)), (c, datetime(2038, 3, 4, 23, 59)),
                   (d, datetime(2038, 3, 5, 0, 0))):
        db.get(Reservation, r["id"]).created_at = day
    db.commit()
    win = {"first": "2038-03-02", "last": "2038-03-04", "category_ids": cat["id"]}
    n = lambda *rs: sorted(r["number"] for r in rs)             # noqa: E731
    assert sorted(_numbers(manager_client, **win)) == n(a, b, d)                    # по умолчанию — проживание
    assert _numbers(manager_client, **win, mode="stay") == _numbers(manager_client, **win)
    assert _numbers(manager_client, **win, mode="check_in") == []
    assert _numbers(manager_client, first="2038-03-01", last="2038-03-01", category_ids=cat["id"],
                    mode="check_in") == [a["number"]]
    assert _numbers(manager_client, **win, mode="check_out") == [b["number"]]
    assert sorted(_numbers(manager_client, **win, mode="created")) == n(b, c)
    assert _numbers(manager_client, **{**win, "first": "2038-03-05", "last": "2038-03-05"}, mode="created") == [d["number"]]


def test_sort_each_column_both_directions(manager_role_client, manager_client, db):
    from datetime import datetime

    from app.modules.stays.adapters.orm import Reservation
    cat = make_category(manager_role_client, n_units=3)
    other = make_category(manager_role_client, n_units=1)
    gs = [make_guest(manager_client, last) for last in ("Яблоков", "Абрамов", "Мышкин")]
    specs = [("N10", "2039-05-03", "2039-05-04", cat, 0), ("N9", "2039-05-01", "2039-05-06", cat, 1),
             ("N100", "2039-05-02", "2039-05-09", other, 2)]
    made = {}
    for i, (num, ci, co, ct, gi) in enumerate(specs):
        r = create_res(manager_client, ct, ci, co, [(gs[gi]["id"], "main", None, None)], number=num)
        db.get(Reservation, r["id"]).created_at = datetime(2039, 4, 10 + i, 12)
        made[num] = r
    db.commit()
    assert manager_client.post(f"{API}/reservations/{made['N9']['id']}/status",
                               json={"status": "cancelled", "version": made["N9"]["version"]}).status_code == 200
    win = {"first": "2039-05-01", "last": "2039-05-09", "category_ids": [cat["id"], other["id"]]}
    asc_orders = {
        "number": ["N9", "N10", "N100"],
        "guest": ["N9", "N100", "N10"],                 # Абрамов, Мышкин, Яблоков
        "check_in": ["N9", "N100", "N10"],
        "check_out": ["N10", "N9", "N100"],
        "nights": ["N10", "N9", "N100"],
        "status": ["N9", "N10", "N100"],                # cancelled < confirmed; равные — по номеру
        "created_at": ["N10", "N9", "N100"],
    }
    for col, order in asc_orders.items():
        assert _numbers(manager_client, **win, sort=col, dir="asc") == order, col
    # при равном ключе вторичный порядок (номер) не переворачивается
    assert _numbers(manager_client, **win, sort="status", dir="desc") == ["N10", "N100", "N9"]
    for col, order in asc_orders.items():
        if col != "status":
            assert _numbers(manager_client, **win, sort=col, dir="desc") == order[::-1], col
    codes = {r["number"]: r["category"] for r in _get(manager_client, **win)["rows"]}
    by_cat = [r["number"] for r in _get(manager_client, **win, sort="category")["rows"]]
    assert [codes[n] for n in by_cat] == sorted(codes.values(), key=str.lower)
    by_cat_desc = [r["number"] for r in _get(manager_client, **win, sort="category", dir="desc")["rows"]]
    assert [codes[n] for n in by_cat_desc] == sorted(codes.values(), key=str.lower, reverse=True)
    units = {r["number"]: r["unit"] for r in _get(manager_client, **win)["rows"]}
    assert units["N9"] == ""                                   # отменённая — без объекта
    by_unit = [units[n] for n in _numbers(manager_client, **win, sort="unit")]
    assert by_unit[-1] == ""                                  # без объекта — в конце
    # метки объектов случайные — сравниваем тем же натуральным ключом, что и сервер
    assert by_unit[:-1] == sorted(by_unit[:-1], key=natural_key)
    # вторичный ключ — номер по возрастанию в любом направлении
    for n in ("S3", "S1", "S2"):
        create_res(manager_client, cat, "2039-06-01", "2039-06-03", number=n)
    w2 = {"first": "2039-06-01", "last": "2039-06-02", "category_ids": cat["id"]}
    for d in ("asc", "desc"):
        assert _numbers(manager_client, **w2, dir=d) == ["S1", "S2", "S3"]
    assert manager_client.get(URL, params={**win, "sort": "phone"}).status_code == 422


def test_pagination_200_and_total(manager_client, big_fund):
    win = {"first": "2029-06-01", "last": "2029-06-30"}
    p1 = _get(manager_client, **win)
    assert p1["total"] >= 300 and len(p1["rows"]) == 200
    p2 = _get(manager_client, **win, offset=200)
    assert p2["total"] == p1["total"] and len(p2["rows"]) == p1["total"] - 200
    ids = [r["id"] for r in p1["rows"] + p2["rows"]]
    assert len(set(ids)) == len(ids) == p1["total"]
    assert len(_get(manager_client, **win, limit=7)["rows"]) == 7
    assert manager_client.get(URL, params={**win, "limit": 201}).status_code == 422
    assert manager_client.get(URL, params={**win, "limit": 0}).status_code == 422
    assert manager_client.get(URL, params={**win, "offset": -1}).status_code == 422
    assert manager_client.get(URL, params={"first": "2029-06-30", "last": "2029-06-01"}).status_code == 422


def test_occupancy_level_403(occupancy_client):
    win = {"first": "2038-03-01", "last": "2038-03-02"}
    assert occupancy_client.get(URL, params=win).status_code == 403
    assert occupancy_client.get(f"{URL}/export", params=win).status_code == 403


def test_phone_search_requires_guests(manager_role_client, manager_client, names_client):
    cat = make_category(manager_role_client, n_units=1)
    last = "Телефонов" + uniq()
    g = manager_client.post(f"{API}/guests", json={"last_name": last, "phone": "+7 916 555-12-34"}).json()
    r = create_res(manager_client, cat, "2038-07-01", "2038-07-03", [(g["id"], "main", None, None)])
    win = {"first": "2038-07-01", "last": "2038-07-02", "category_ids": cat["id"]}
    for phone in ("79165551234", "+7 (916) 555-12-34", "8 916 555 12 34", "555-12-34"):
        assert _numbers(manager_client, **win, q=phone) == [r["number"]], phone      # stays.guests
        assert _numbers(names_client, **win, q=phone) == [], phone                    # только stays.view
    # поиск по фамилии и номеру доступен обоим
    assert _numbers(names_client, **win, q=last.lower()) == [r["number"]]
    assert _numbers(names_client, **win, q=r["number"]) == [r["number"]]
    body = _get(names_client, **win)
    assert "+7" not in json.dumps(body, ensure_ascii=False) and "5551234" not in json.dumps(body)


def test_filters_reuse_board_semantics(manager_role_client, manager_client):
    corp, villas = _groups(manager_role_client, "Корпус", "Виллы")
    rooms = make_category(manager_role_client, n_units=2, kind="room", group_id=corp)
    vil = make_category(manager_role_client, n_units=2, kind="villa", group_id=villas)
    sea, view = _flag(manager_role_client), _flag(manager_role_client)
    _set_flag(manager_role_client, sea, [vil["units"][0]["id"], rooms["units"][0]["id"]])
    _set_flag(manager_role_client, view, [vil["units"][0]["id"]])
    day = {"first": "2038-09-01", "last": "2038-09-03"}
    by_cat = {}
    for cat in (rooms, vil):
        by_cat[cat["code"]] = [create_res(manager_client, cat, "2038-09-01", "2038-09-03")["number"] for _ in range(2)]
    both = set(by_cat[rooms["code"]]) | set(by_cat[vil["code"]])
    scope = {"category_ids": [rooms["id"], vil["id"]]}
    assert set(_numbers(manager_client, **day, **scope, group_ids=[corp, villas])) == both            # узлы — «или»
    assert set(_numbers(manager_client, **day, group_ids=[corp])) >= set(by_cat[rooms["code"]])
    assert not set(_numbers(manager_client, **day, group_ids=[corp])) & set(by_cat[vil["code"]])
    assert set(_numbers(manager_client, **day, **scope, kinds=["villa"])) == set(by_cat[vil["code"]])
    only_sea = _get(manager_client, **day, **scope, flag_ids=[sea])["rows"]
    units_sea = {r["unit"] for r in only_sea}
    assert units_sea == {vil["units"][0]["label"], rooms["units"][0]["label"]}
    both_flags = _get(manager_client, **day, **scope, flag_ids=[sea, view])["rows"]            # флаги — «и»
    assert {r["unit"] for r in both_flags} == {vil["units"][0]["label"]}


def test_status_label_unassigned_vip_filters(manager_role_client, manager_client):
    cat = make_category(manager_role_client, n_units=1)
    vip = make_guest(manager_client, "Випов" + uniq(), level="vip")
    a = create_res(manager_client, cat, "2038-10-01", "2038-10-03", [(vip["id"], "main", None, None)])
    b = create_res(manager_client, cat, "2038-10-01", "2038-10-03")              # объект один — вторая без объекта
    win = {"first": "2038-10-01", "last": "2038-10-02", "category_ids": cat["id"]}
    rows = {r["number"]: r for r in _get(manager_client, **win)["rows"]}
    assert rows[a["number"]]["level"] == "vip" and rows[a["number"]]["main_guest"].startswith("Випов")
    assert _numbers(manager_client, **win, vip=1) == [a["number"]]
    # объект один: какая из двух броней его получила, решает распределение — вторая без объекта
    loose = _numbers(manager_client, **win, unassigned=1)
    assert len(loose) == 1 and loose[0] in (a["number"], b["number"])
    assert [n for n, r in rows.items() if r["unit"] == ""] == loose
    assert _numbers(manager_client, **win, statuses=["cancelled"]) == []
    assert manager_client.get(URL, params={**win, "statuses": "bogus"}).status_code == 422


def test_move_and_butlers_columns(manager_role_client, manager_client, db):
    """Переезд — «A → B» в колонках категории и объекта; батлер — по строке покрытия на ночи брони."""
    import datetime as dt

    from app.modules.employees.application.catalog import Employee
    from app.modules.stays.adapters.orm import CoverageLine
    a, b = make_category(manager_role_client, n_units=1), make_category(manager_role_client, n_units=1)
    r = create_res(manager_client, a, "2038-12-01", "2038-12-06", number="M" + uniq(),
                   moves=[{"move_date": "2038-12-04", "category_id": b["id"]}])
    emp = db.scalar(select(Employee).where(Employee.full_name.like("Иванов%")))
    db.add(CoverageLine(day=dt.date(2038, 12, 2), employee_id=emp.id, reservation_id=r["id"]))
    db.commit()
    row = _get(manager_client, first="2038-12-01", last="2038-12-05", category_ids=[a["id"], b["id"]])["rows"][0]
    assert row["category"] == f"{a['code']} → {b['code']}"
    assert row["unit"] == f"{a['units'][0]['label']} → {b['units'][0]['label']}"
    assert row["butlers"] == [emp.short_name or emp.full_name]
    assert _numbers(manager_client, first="2038-12-01", last="2038-12-05", employee_id=emp.id) == [r["number"]]
    assert _numbers(manager_client, first="2038-12-01", last="2038-12-05", category_ids=b["id"]) == [r["number"]]


def test_bookings_query_budget(manager_client, big_fund, sql_counter):
    win = {"first": "2029-06-01", "last": "2029-06-30"}
    with sql_counter() as c:
        r = manager_client.get(URL, params={**win, "kinds": ["room"], "q": "большой"})
    assert r.status_code == 200 and r.json()["total"] > 0
    with sql_counter() as c:
        r = manager_client.get(URL, params=win)
    assert r.status_code == 200 and r.json()["total"] >= 300
    assert c["total"] <= 12, list(c["by_statement"].items())


def test_export_audited(manager_role_client, manager_client, db):
    cat = make_category(manager_role_client, n_units=1)
    g = make_guest(manager_client, "Выгрузков" + uniq())
    r = create_res(manager_client, cat, "2038-11-01", "2038-11-04", [(g["id"], "main", None, None)],
                   number="=CMD" + uniq())
    win = {"first": "2038-11-01", "last": "2038-11-03", "category_ids": cat["id"], "sort": "number", "dir": "desc"}
    assert manager_client.get(f"{URL}/export", params=win).status_code == 403          # нет stays.export
    resp = manager_role_client.get(f"{URL}/export", params=win)
    assert resp.status_code == 200 and "spreadsheetml" in resp.headers["content-type"]
    wb = load_workbook(io.BytesIO(resp.content))
    assert wb.sheetnames == ["Бронирования"]
    rows = list(wb.active.iter_rows(values_only=True))
    assert rows[0][0] == "Номер" and len(rows) == 2
    assert rows[1][0].startswith("'") or not rows[1][0].startswith("=")                # формула экранирована
    assert g["last_name"][:6] in rows[1][1] and rows[1][5] == 3
    row = db.scalars(select(AuditLog).where(AuditLog.action == "stays_export").order_by(AuditLog.id.desc())).first()
    p = json.loads(row.payload_json)
    assert row.target == "export:bookings" and p["kind"] == "bookings" and p["rows"] == 1
    assert p["first"] == "2038-11-01" and p["sort"] == "number" and p["dir"] == "desc" and p["category_ids"] == [cat["id"]]
    assert r["id"]


@pytest.mark.parametrize("bad", [{"mode": "x"}, {"dir": "up"}])
def test_bad_params_422(manager_client, bad):
    assert manager_client.get(URL, params={"first": "2038-01-01", "last": "2038-01-02", **bad}).status_code == 422
