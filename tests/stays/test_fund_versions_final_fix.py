"""Итоговое ревью версий фонда: член группы с заездом после границы версии читается в своих
частях (I1); заезд в день версии — объект утра по прежней версии во всех читателях (I2)."""
from __future__ import annotations

from sqlalchemy import select

from .helpers import API, create_res, make_category, make_guest


def _version(setup_client, valid_from: str, *edits) -> None:
    r = setup_client.post(f"{API}/fund/draft", json={"valid_from": valid_from})
    assert r.status_code == 200, r.text
    rev = r.json()["rev"]
    for method, path, body in edits:
        if method == "DELETE":
            resp = setup_client.delete(f"{API}/fund/draft/{path}", params={"rev": rev})
        else:
            resp = setup_client.request(method, f"{API}/fund/draft/{path}", json={"rev": rev, **body})
        assert resp.status_code == 200, resp.text
        rev = resp.json()["rev"]
    resp = setup_client.post(f"{API}/fund/draft/publish", json={"rev": rev})
    assert resp.status_code == 200, resp.text


def _rows(db, rid: int) -> dict[int, int | None]:
    from app.modules.stays.adapters.orm import Assignment

    db.expire_all()
    return {a.seg_index: a.unit_id for a in db.scalars(select(Assignment).where(Assignment.reservation_id == rid))}


def _in_house(c, day: str) -> dict[int, str]:
    rows = c.get(f"{API}/day", params={"date": day}).json()["in_house"]
    return {x["reservation_id"]: x["unit"] for x in rows}


def test_group_member_after_boundary_in_own_pieces(manager_role_client, manager_client, today, db):
    """I1: группа A (10.04–15.04) и B (11.04–15.04), версия 11.04 выводит объект группы. У B одна
    часть — после границы: её строка — новый объект, на шахматке и в «Табло дня» B в нём."""
    today("2041-04-01")
    cat = make_category(manager_role_client, n_units=2)
    u1, u2 = (u["id"] for u in cat["units"])
    gid = manager_client.post(f"{API}/groups", json={"title": "Г"}).json()["id"]
    a = create_res(manager_client, cat, "2041-04-10", "2041-04-15", group_id=gid)
    b = create_res(manager_client, cat, "2041-04-11", "2041-04-15", group_id=gid)
    gone = a["segments"][0]["unit_id"]
    stays = u2 if gone == u1 else u1
    _version(manager_role_client, "2041-04-11", ("DELETE", f"units/{gone}", {}))

    assert _rows(db, a["id"]) == {0: gone, 1: stays}
    assert _rows(db, b["id"]) == {0: stays}                  # часть B — своя, после границы
    board = manager_client.get(f"{API}/board/units", params={"first": "2041-04-08", "last": "2041-04-16",
                                                             "category_ids": cat["id"]}).json()
    bars = [(x["unit_id"], x["start"], x["end"]) for x in board["bars"] if x["reservation_id"] == b["id"]]
    assert bars == [(stays, "2041-04-11", "2041-04-15")]
    assert b["id"] in _in_house(manager_client, "2041-04-12")


def test_check_in_on_version_day_readers(manager_role_client, manager_client, today, db):
    """I2: ранний заезд в день версии D, объект выведен с D. Утро D — по прежней версии:
    вкладка «Брони» показывает оба объекта, карточка и журнал — обозначение объекта."""
    today("2041-05-01")
    cat = make_category(manager_role_client, n_units=2)
    g = make_guest(manager_client)
    r = create_res(manager_client, cat, "2041-05-10", "2041-05-14", [(g["id"], "main", None, None)], early=True)
    gone = r["segments"][0]["unit_id"]
    labels = {u["id"]: u["label"] for u in cat["units"]}
    stays = next(u for u in labels if u != gone)
    _version(manager_role_client, "2041-05-10", ("DELETE", f"units/{gone}", {}))
    assert _rows(db, r["id"]) == {0: gone, 1: stays}          # утро D — прежний объект, вечер — новый

    rows = manager_client.get(f"{API}/bookings", params={"first": "2041-05-01", "last": "2041-05-31",
                                                         "q": r["number"]}).json()["rows"]
    assert [x["unit"] for x in rows if x["id"] == r["id"]] == [f"{labels[gone]} → {labels[stays]}"]

    card = manager_client.get(f"{API}/reservations/{r['id']}/card").json()
    assert [s["unit"] for s in card["segments"]] == [labels[gone]]

    from app.modules.stays.adapters.orm import Reservation
    from app.modules.stays.application.reservations import reservation_snapshot
    db.expire_all()
    assert reservation_snapshot(db, db.get(Reservation, r["id"]))["units"] == [labels[gone], labels[stays]]

    guest = manager_client.get(f"{API}/guests/{g['id']}/card").json()["stays"]
    assert next(s for s in guest if s["reservation_id"] == r["id"])["units"] == [labels[gone], labels[stays]]


def test_preview_label_of_morning_piece_on_version_day(manager_role_client, manager_client, today):
    """I2: предпросмотр новой брони с ранним заездом в день версии D, единственный объект
    выведен с D: утро D — в нём (прежняя версия), подпись «куда» — его обозначение."""
    from .helpers import res_body

    today("2041-06-01")
    cat = make_category(manager_role_client, n_units=1)
    unit = cat["units"][0]
    _version(manager_role_client, "2041-06-10", ("DELETE", f"units/{unit['id']}", {}))
    pv = manager_client.post(f"{API}/reservations", params={"preview": 1},
                             json=res_body(cat, "2041-06-10", "2041-06-12", early=True)).json()
    moved = [(m["to_unit"], m["to_label"]) for m in pv["diff"]["moved"] if m["new"]]
    assert moved == [(unit["id"], unit["label"])]
