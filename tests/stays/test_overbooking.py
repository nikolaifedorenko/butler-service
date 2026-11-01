"""Шахматка, часть 2: овербукинг под правом stays.overbook (§7), бронь без объекта для батлеров
(§2, ответ 11), прошлое под OOO (§4.5), предпросмотр ≡ сохранение с блоками и OOO, бюджет SQL."""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import delete, select

from .helpers import API, create_res, make_category, make_guest, res_body
from .test_preview import _put_body, dump


@pytest.fixture()
def no_overbook_client(app_stack):
    """Правка шахматки (stays.edit, stays.view) без права «Овербукинг»."""
    from app.core.db import SessionLocal
    from app.core.identity import AccessGrant, Role

    from .conftest import _role_user

    with SessionLocal() as s:
        if s.get(Role, "stays_no_overbook") is None:
            s.add(Role(code="stays_no_overbook", title="Правка без овербукинга", rank=20, max_assignable_rank=-1,
                       builtin=False))
            s.add_all(AccessGrant(role="stays_no_overbook", permission=p, effect="allow")
                      for p in ("stays.view", "stays.edit"))
            s.commit()
    return _role_user(app_stack, "stays_no_overbook_user", "stays_no_overbook")


@pytest.fixture()
def blocks():
    """Блоки, заведённые тестом напрямую в БД (API блоков — Task 4); удаляются после теста."""
    from app.core.db import SessionLocal
    from app.modules.stays.adapters.orm import Block, BlockNight

    made: list[int] = []

    def add(title: str, grid: dict[tuple[int, dt.date], int]) -> int:
        nights = [n for _c, n in grid]
        with SessionLocal() as s:
            b = Block(title=title, start=min(nights), end=max(nights) + dt.timedelta(days=1))
            s.add(b)
            s.flush()
            s.add_all(BlockNight(block_id=b.id, category_id=c, night=n, quantity=q) for (c, n), q in grid.items())
            s.commit()
            made.append(b.id)
            return b.id
    yield add
    with SessionLocal() as s:
        s.execute(delete(BlockNight).where(BlockNight.block_id.in_(made)))
        s.execute(delete(Block).where(Block.id.in_(made)))
        s.commit()


def _nights(first: str, n: int) -> list[dt.date]:
    d = dt.date.fromisoformat(first)
    return [d + dt.timedelta(days=i) for i in range(n)]


def test_overbook_needs_perm_409(manager_role_client, manager_client, no_overbook_client, db):
    cat = make_category(manager_role_client, n_units=1)
    create_res(manager_client, cat, "2036-02-10", "2036-02-14")
    body = res_body(cat, "2036-02-11", "2036-02-13", number="881")
    before = dump(db)
    r = no_overbook_client.post(f"{API}/reservations", json=body)
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["overbook"] is True
    assert detail["message"] == (f"Нет объекта: Бронь 881: нет свободных объектов категории {cat['code']} на "
                                 f"11.02–13.02. Сохранить с овербукингом может сотрудник с правом «Овербукинг»")
    assert [w["kind"] for w in detail["diff"]["warnings_added"] if w["day"] is None] == ["overbooked"]
    assert dump(db) == before                                 # ничего не записано
    pv = no_overbook_client.post(f"{API}/reservations", params={"preview": 1}, json=body)
    assert pv.status_code == 200 and pv.json()["overbook_refused"] == detail["message"]
    assert pv.json()["diff"] == detail["diff"]


def test_overbook_with_perm_saves_with_warning(manager_role_client, manager_client):
    cat = make_category(manager_role_client, n_units=1)
    create_res(manager_client, cat, "2036-03-10", "2036-03-14")
    r = manager_client.post(f"{API}/reservations", json=res_body(cat, "2036-03-11", "2036-03-13", number="882"))
    assert r.status_code == 200, r.text
    assert "overbook_refused" not in r.json()
    res = r.json()["result"]
    assert res["segments"][0]["unit_id"] is None
    assert res["warnings"] == [f"Бронь 882: нет свободных объектов категории {cat['code']} на 11.03–13.03"]


def test_existing_overbook_does_not_block_other_edits(manager_role_client, manager_client, no_overbook_client):
    cat = make_category(manager_role_client, n_units=1)
    a = create_res(manager_client, cat, "2036-04-10", "2036-04-14")
    b = create_res(manager_client, cat, "2036-04-11", "2036-04-13")
    assert b["segments"][0]["unit_id"] is None
    for res in (a, b):
        r = no_overbook_client.put(f"{API}/reservations/{res['id']}", json=_put_body(res, note="правка"))
        assert r.status_code == 200, r.text


def test_overbook_check_by_identity_not_count(manager_role_client, manager_client, no_overbook_client):
    """Правка убирает овербукинг B и создаёт овербукинг C той же длины: число ночей без объекта
    не выросло, но овербукинг новый — 409 (Review Focus 4)."""
    cat = make_category(manager_role_client, n_units=1)
    a = create_res(manager_client, cat, "2036-05-10", "2036-05-12", number="1")
    b = create_res(manager_client, cat, "2036-05-10", "2036-05-12", number="2")
    c = create_res(manager_client, cat, "2036-05-20", "2036-05-22", number="3")
    assert [x["segments"][0]["unit_id"] for x in (a, b, c)] == [cat["units"][0]["id"], None, cat["units"][0]["id"]]
    body = _put_body(a, check_in="2036-05-20", check_out="2036-05-22")
    pv = manager_client.put(f"{API}/reservations/{a['id']}", params={"preview": 1}, json=body).json()
    gone = {w["reservation_id"] for w in pv["diff"]["warnings_removed"] if w["kind"] == "overbooked"}
    came = {w["reservation_id"] for w in pv["diff"]["warnings_added"] if w["kind"] == "overbooked"}
    assert gone == {b["id"]} and came == {c["id"]}             # B получает объект, C его теряет
    r = no_overbook_client.put(f"{API}/reservations/{a['id']}", json=body)
    assert r.status_code == 409 and "Бронь 3: нет свободных объектов" in r.json()["detail"]["message"]


def test_overbooked_booking_has_hole_and_load(manager_role_client, manager_client, butlers):
    """Бронь без объекта для батлеров — как обычная: дыра по правилам сопровождения, нагрузка с
    весом категории брони, «Требуют внимания» на табло дня (ответ владельца 11)."""
    d = butlers["days"][0]
    d1 = d + dt.timedelta(days=1)
    cat = make_category(manager_role_client, n_units=1, weight=4)
    ga, gb = make_guest(manager_client), make_guest(manager_client)
    # одинаковые даты — порядок по номеру: A получает объект, B остаётся без объекта
    a = create_res(manager_client, cat, d.isoformat(), (d + dt.timedelta(days=2)).isoformat(),
                   [(ga["id"], "main", None, None)], number="1")
    b = create_res(manager_client, cat, d.isoformat(), (d + dt.timedelta(days=2)).isoformat(),
                   [(gb["id"], "main", None, None)], number="2")
    assert a["segments"][0]["unit_id"] == cat["units"][0]["id"] and b["segments"][0]["unit_id"] is None
    def cell():
        board = manager_client.get(f"{API}/board/butlers", params={"first": d.isoformat(), "last": d.isoformat()})
        return next(row for row in board.json()["rows"] if row["employee_id"] == butlers["a"])["cells"][0]

    load0 = cell()["load"]
    r = manager_client.put(f"{API}/coverage/day", json={"day": d.isoformat(), "reservation_id": b["id"],
                                                        "employee_id": butlers["a"]})
    assert r.status_code == 200, r.text
    now = cell()
    # вес категории брони; нагрузка в ответе округлена до сотых — сравнение с допуском округления
    assert now["load"] == pytest.approx(load0 + 4.0, abs=0.011)
    assert "без объекта" in {u["label"] for u in now["units"]}
    day = manager_client.get(f"{API}/day", params={"date": d.isoformat()}).json()
    row_b = next(x for x in day["in_house"] if x["reservation_id"] == b["id"])
    assert row_b["unit"] == "без объекта" and row_b["overbooked"] is True and row_b["cover_status"] == "covered"
    assert {x["reservation_id"] for x in day["attention"]} >= {a["id"], b["id"]}     # A — дыра, B — овербукинг
    nxt = manager_client.get(f"{API}/day", params={"date": d1.isoformat()}).json()
    assert next(x for x in nxt["in_house"] if x["reservation_id"] == b["id"])["cover_status"] == "uncovered"
    card = manager_client.get(f"{API}/reservations/{b['id']}/card").json()
    assert [w["text"] for w in card["coverage"][1]["warnings"]] == ["без объекта: гости без батлера"]


def _bars(client, cat, rid, first, last):
    board = client.get(f"{API}/board/units", params={"first": first, "last": last, "category_ids": cat["id"]}).json()
    return ([(b["unit_id"], b["start"], b["end"]) for b in board["bars"] if b["reservation_id"] == rid],
            [w["text"] for w in board["warnings"] if rid in w["reservation_ids"]])


def test_past_ooo_edit_does_not_move_past_pieces(manager_role_client, manager_client, today):
    """Review Focus 3: OOO продлили назад на 3 дня, когда в эти дни жил гость, — прошлые части не
    переселяются, за прошлые дни — предупреждение о наложении; будущее уходит с OOO."""
    today("2034-06-01")
    cat = make_category(manager_role_client, n_units=2)
    u1, u2 = (u["id"] for u in cat["units"])
    a = create_res(manager_client, cat, "2034-06-01", "2034-06-10", number="6")
    st = manager_client.post(f"{API}/reservations/{a['id']}/status", json={"status": "in_house", "version": a["version"]})
    assert st.status_code == 200
    today("2034-06-05")
    hold = manager_client.post(f"{API}/holds", json={"unit_id": u1, "start": "2034-06-07", "end": "2034-06-08",
                                                     "kind": "ooo", "title": "Ремонт"}).json()["result"]
    r = manager_client.put(f"{API}/holds/{hold['id']}", json={"unit_id": u1, "start": "2034-06-02",
                                                              "end": "2034-06-08", "kind": "ooo", "title": "Ремонт"})
    assert r.status_code == 200, r.text
    bars, warns = _bars(manager_client, cat, a["id"], "2034-06-01", "2034-06-12")
    assert bars == [(u1, "2034-06-01", "2034-06-05"), (u2, "2034-06-05", "2034-06-10")]
    assert f"Бронь 6: объект {cat['units'][0]['label']} в OOO «Ремонт» 02.06–05.06 — прошлые дни проживания " \
           f"не переселяются" in warns


def test_in_house_pin_moves_with_guest(manager_role_client, manager_client, today):
    """Закреплённый заселённый гость под OOO: переезд с ночи OOO, закрепление — на новом объекте."""
    today("2034-07-01")
    cat = make_category(manager_role_client, n_units=2)
    u1, u2 = (u["id"] for u in cat["units"])
    a = create_res(manager_client, cat, "2034-07-01", "2034-07-10", number="7", pins={"0": u1})
    st = manager_client.post(f"{API}/reservations/{a['id']}/status", json={"status": "in_house", "version": a["version"]})
    assert st.status_code == 200
    today("2034-07-05")
    r = manager_client.post(f"{API}/holds", json={"unit_id": u1, "start": "2034-07-07", "end": "2034-07-08",
                                                  "kind": "ooo", "title": "Ремонт"})
    assert r.status_code == 200
    assert [w["text"] for w in r.json()["diff"]["warnings_added"] if w["kind"] == "pin_conflict"] == [
        f"Бронь 7: закреплённый объект {cat['units'][0]['label']} занят «Ремонт» — бронь перенесена вместе с "
        f"закреплением"]
    got = manager_client.get(f"{API}/reservations/{a['id']}").json()
    assert got["segments"][0]["pinned"] is True and got["segments"][0]["unit_id"] == u2
    assert got["warnings"] == []          # закрепление уже на новом объекте — конфликта больше нет
    # пересчёт без изменений ничего не двигает
    again = manager_client.put(f"{API}/reservations/{a['id']}", json=_put_body(got, note="x", pins={"0": u2}))
    assert again.status_code == 200 and again.json()["diff"]["moved"] == []
    assert again.json()["result"]["warnings"] == []


@pytest.mark.parametrize("name", ["create", "add_ooo"])
def test_preview_equals_save_with_blocks_and_ooo(manager_role_client, manager_client, db, today, blocks, name):
    today("2036-06-01")
    cat = make_category(manager_role_client, n_units=2)
    u1 = cat["units"][0]["id"]
    blocks("Гендир", {(cat["id"], n): 1 for n in _nights("2036-06-11", 2)})
    a = create_res(manager_client, cat, "2036-06-10", "2036-06-14")
    if name == "create":
        method, url, body = "POST", f"{API}/reservations", res_body(cat, "2036-06-12", "2036-06-16")
    else:
        method, url, body = "POST", f"{API}/holds", {"unit_id": u1, "start": "2036-06-12", "end": "2036-06-12",
                                                     "kind": "ooo", "title": "Ремонт"}
    before = dump(db)
    pv = manager_client.request(method, url, params={"preview": 1}, json=body)
    assert pv.status_code == 200, pv.text
    assert dump(db) == before
    sv = manager_client.request(method, url, json=body)
    assert sv.status_code == 200, sv.text
    assert pv.json()["diff"] == sv.json()["diff"]
    added = {(w["kind"], w["reservation_id"]) for w in sv.json()["diff"]["warnings_added"] if w["day"] is None}
    # блок главнее подтверждённой брони: без объекта остаётся бронь, блок не уменьшается
    assert ("overbooked", a["id"] if name == "add_ooo" else None) in added
    assert not any(k == "block_short" for k, _r in added)


def test_block_short_shown_on_board(manager_role_client, manager_client, today, blocks):
    """Нехватка блока (ключ ("b", id), piece_index — ночь) не ломает предпросмотр и шахматку."""
    today("2036-07-01")
    cat = make_category(manager_role_client, n_units=1)
    blocks("Свадьба", {(cat["id"], n): 2 for n in _nights("2036-07-10", 2)})
    r = manager_client.post(f"{API}/reservations", params={"preview": 1},
                            json=res_body(cat, "2036-07-20", "2036-07-21"))
    assert r.status_code == 200
    board = manager_client.get(f"{API}/board/units", params={"first": "2036-07-01", "last": "2036-07-31",
                                                             "category_ids": cat["id"]}).json()
    assert {"kind": "block_short", "reservation_ids": [],
            "text": f"Блок Свадьба: не хватает 1 {cat['code']} на 10–11.07"} in board["warnings"]


def test_board_query_budget_with_blocks(manager_client, big_fund, sql_counter, blocks):
    """Шахматка 440 × 31 с блоками и OOO — не больше 30 запросов."""
    from app.core.db import SessionLocal
    from app.modules.stays.adapters.orm import CategoryState, Ooo, Unit

    with SessionLocal() as s:
        cats = list(s.scalars(select(CategoryState.category_id).where(CategoryState.code.in_(("BIGDLX", "BIGSTE", "BIGVIL")))
                              .distinct()))
        units = list(s.scalars(select(Unit.id).order_by(Unit.id).limit(5)))
    for i, cid in enumerate(cats):
        blocks(f"Большой{i}", {(cid, n): 3 for n in _nights("2029-06-05", 10)})
    with SessionLocal() as s:
        oo = [Ooo(unit_id=u, start=dt.date(2029, 6, 3 + i), end=dt.date(2029, 6, 6 + i), start_half="PM",
                  end_half="AM", reason=f"ремонт {i}") for i, u in enumerate(units)]
        s.add_all(oo)
        s.commit()
        ids = [o.id for o in oo]
    try:
        with sql_counter() as c:
            r = manager_client.get(f"{API}/board/units", params=big_fund)
        assert r.status_code == 200
        assert c["total"] <= 30, sorted(c["by_statement"].items(), key=lambda x: -x[1])[:3]
    finally:
        with SessionLocal() as s:
            s.execute(delete(Ooo).where(Ooo.id.in_(ids)))
            s.commit()


def test_pinned_booking_without_unit_keeps_pin(manager_role_client, manager_client, today, db):
    """OOO на закреплённый объект, другого свободного нет (§4.4): овербукинг, закрепление сохранено;
    OOO сняли — бронь возвращается в свой объект."""
    today("2036-08-01")
    cat = make_category(manager_role_client, n_units=1)
    u1 = cat["units"][0]["id"]
    a = create_res(manager_client, cat, "2036-08-10", "2036-08-14", number="9", pins={"0": u1})
    r = manager_client.post(f"{API}/holds", json={"unit_id": u1, "start": "2036-08-11", "end": "2036-08-11",
                                                  "kind": "ooo", "title": "Ремонт"})
    assert r.status_code == 200, r.text
    got = manager_client.get(f"{API}/reservations/{a['id']}").json()
    assert got["segments"][0]["pinned"] is True and got["segments"][0]["unit_id"] == u1
    assert f"Бронь 9: закреплённый объект {cat['units'][0]['label']} занят «Ремонт» — свободного объекта нет: " \
           f"бронь без объекта, закрепление сохранено" in got["warnings"]
    card = manager_client.get(f"{API}/reservations/{a['id']}/card").json()
    assert card["segments"][0]["unit_id"] is None                       # фактически — без объекта
    gone = manager_client.delete(f"{API}/holds/{r.json()['result']['id']}")
    assert gone.status_code == 200, gone.text
    back = manager_client.get(f"{API}/reservations/{a['id']}").json()
    assert back["segments"][0]["pinned"] is True and back["segments"][0]["unit_id"] == u1
    assert manager_client.get(f"{API}/reservations/{a['id']}/card").json()["segments"][0]["unit_id"] == u1
    assert back["warnings"] == []


def test_category_missing_needs_perm(manager_role_client, no_overbook_client):
    """Бронь в категории без объектов в фонде — тоже новая бронь без объекта: без права — 409."""
    cat = make_category(manager_role_client, n_units=0)
    r = no_overbook_client.post(f"{API}/reservations", json=res_body(cat, "2036-09-10", "2036-09-12", number="991"))
    assert r.status_code == 409, r.text
    assert f"Бронь 991: категории {cat['code']} нет в фонде" in r.json()["detail"]["message"]


def test_change_window_covers_old_and_new_dates():
    from app.modules.stays.application.preview import change_window

    d = dt.date
    assert change_window((d(2036, 1, 10), d(2036, 1, 12))) == (d(2035, 11, 9), d(2036, 3, 14))
    lo, hi = change_window((d(2036, 6, 1), d(2036, 6, 3)), (d(2036, 1, 10), d(2036, 1, 12)))
    assert lo == d(2035, 11, 9) and hi >= d(2036, 6, 3)                  # перенос OOO январь → июнь
    lo, hi = change_window((d(2036, 1, 1), d(2036, 12, 31)))
    assert (hi - lo).days == 62 + 124 + 62                               # длинное изменение — окно ограничено


def test_block_short_board_filters(manager_role_client, manager_client, today, blocks):
    """Нехватку блока шахматка показывает только за ночи периода и в категориях фильтра."""
    today("2036-10-01")
    cat = make_category(manager_role_client, n_units=1)
    other = make_category(manager_role_client, n_units=1)
    blocks("Форум", {(cat["id"], n): 2 for n in _nights("2036-10-10", 2)})

    def shorts(first, last, cid):
        board = manager_client.get(f"{API}/board/units", params={"first": first, "last": last,
                                                                 "category_ids": cid}).json()
        return [w["text"] for w in board["warnings"] if w["kind"] == "block_short"]

    text = f"Блок Форум: не хватает 1 {cat['code']} на 10–11.10"
    assert shorts("2036-10-01", "2036-10-31", cat["id"]) == [text]
    assert shorts("2036-10-12", "2036-10-31", cat["id"]) == []           # после последней ночи блока
    assert shorts("2036-10-01", "2036-10-09", cat["id"]) == []
    assert shorts("2036-10-01", "2036-10-31", other["id"]) == []         # другая категория
