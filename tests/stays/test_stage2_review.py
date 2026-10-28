"""Ревью этапа 2: окно распределения, замок модуля, группы, ошибки ввода."""
from __future__ import annotations

from .helpers import API, FundDraft, create_res, make_category, make_guest, res_body, units_of


def _body(res, **ch):
    return {**{k: res[k] for k in ("number", "check_in", "check_out", "category_id", "early", "late",
                                   "group_id", "note", "declined_butler")},
            "moves": res["moves"], "occupants": res["occupants"], "companions": res["companions"],
            "logistics": res["logistics"], "version": res["version"], **ch}


def _get(c, rid):
    return c.get(f"{API}/reservations/{rid}").json()


def test_in_house_not_moved_by_new_pin(manager_role_client, manager_client, today):
    """C1: заселённого гостя распределение не переставляет."""
    today("2031-01-05")
    cat = make_category(manager_role_client, n_units=2)
    a = create_res(manager_client, cat, "2031-01-03", "2031-01-09")
    st = manager_client.post(f"{API}/reservations/{a['id']}/status", json={"status": "in_house", "version": a["version"]})
    assert st.status_code == 200
    pv = manager_client.post(f"{API}/reservations", params={"preview": 1}, json=res_body(
        cat, "2031-01-05", "2031-01-07", pins={"0": cat["units"][0]["id"]})).json()
    assert all(m["reservation_id"] != a["id"] for m in pv["diff"]["moved"])
    assert [w["kind"] for w in pv["diff"]["warnings_added"] if w["day"] is None] == ["pin_conflict"]


def test_past_segment_frozen(manager_role_client, manager_client, today):
    """C1: прошедший сегмент брони остаётся в своём объекте, даже если появилось закрепление."""
    today("2031-02-10")
    cat = make_category(manager_role_client, n_units=2)
    a = create_res(manager_client, cat, "2031-02-01", "2031-02-20",
                   moves=[{"move_date": "2031-02-05", "category_id": cat["id"]}])
    before = units_of(_get(manager_client, a["id"]))
    create_res(manager_client, cat, "2031-02-01", "2031-02-04", pins={"0": before[0]})
    assert units_of(_get(manager_client, a["id"]))[0] == before[0]


def test_compute_scope_ignores_past(manager_role_client, manager_client, today, db):
    """C1: в расчёт попадают только брони с выездом не раньше сегодня."""
    from app.modules.stays.application import allocation
    cat = make_category(manager_role_client, n_units=1)
    old = create_res(manager_client, cat, "2031-03-01", "2031-03-03")
    today("2031-03-10")
    allocation_state = allocation.compute(db)
    assert (old["id"], 0) not in allocation_state.units


def test_group_pin_by_any_member(manager_role_client, manager_client):
    """I2: закрепление любого члена группы переносит всю группу."""
    cat = make_category(manager_role_client, n_units=2)
    gid = manager_client.post(f"{API}/groups", json={"title": "Г"}).json()["id"]
    a = create_res(manager_client, cat, "2031-04-01", "2031-04-05", group_id=gid,
                   pins={"0": cat["units"][0]["id"]})
    b = create_res(manager_client, cat, "2031-04-01", "2031-04-05", group_id=gid)
    r = manager_client.put(f"{API}/reservations/{b['id']}", json=_body(_get(manager_client, b["id"]),
                                                                       pins={"0": cat["units"][1]["id"]}))
    assert r.status_code == 200
    assert units_of(_get(manager_client, a["id"])) == units_of(_get(manager_client, b["id"])) == [cat["units"][1]["id"]]


def test_group_move_applies_to_all_members(manager_role_client, manager_client):
    """I3: переезд одной брони группы переносится на остальных."""
    cat = make_category(manager_role_client, n_units=3)
    gid = manager_client.post(f"{API}/groups", json={"title": "Г"}).json()["id"]
    a = create_res(manager_client, cat, "2031-05-01", "2031-05-09", group_id=gid)
    b = create_res(manager_client, cat, "2031-05-01", "2031-05-09", group_id=gid)
    mv = [{"move_date": "2031-05-05", "category_id": cat["id"]}]
    r = manager_client.put(f"{API}/reservations/{a['id']}", json=_body(_get(manager_client, a["id"]), moves=mv))
    assert r.status_code == 200, r.text
    b2 = _get(manager_client, b["id"])
    assert b2["moves"] == mv and b2["version"] == b["version"] + 1
    assert units_of(b2) == units_of(_get(manager_client, a["id"]))


def test_group_move_outside_member_dates_refused(manager_role_client, manager_client):
    cat = make_category(manager_role_client, n_units=2)
    gid = manager_client.post(f"{API}/groups", json={"title": "Г"}).json()["id"]
    a = create_res(manager_client, cat, "2031-06-01", "2031-06-09", group_id=gid)
    b = create_res(manager_client, cat, "2031-06-01", "2031-06-04", number="SHORT", group_id=gid)
    r = manager_client.put(f"{API}/reservations/{a['id']}", json=_body(
        _get(manager_client, a["id"]), moves=[{"move_date": "2031-06-06", "category_id": cat["id"]}]))
    assert r.status_code == 422 and r.json()["detail"] == "Переезд группы вне дат брони SHORT"
    assert b


def test_bad_custom_field_is_422(manager_role_client, manager_client):
    """I4: неизвестное поле брони — 422 и в предпросмотре, а не 500."""
    cat = make_category(manager_role_client)
    for params in ({"preview": 1}, {}):
        r = manager_client.post(f"{API}/reservations", params=params,
                                json=res_body(cat, "2031-07-01", "2031-07-03", fields={"nope": "x"}))
        assert r.status_code == 422 and r.json()["detail"] == "Неизвестное поле: nope"


def test_unit_deactivation_reallocates(manager_role_client, manager_client):
    """I5: объект вывели из фонда — бронь переходит на другой."""
    cat = make_category(manager_role_client, n_units=2)
    a = create_res(manager_client, cat, "2031-08-01", "2031-08-05")
    u0 = cat["units"][0]
    assert units_of(a) == [u0["id"]]
    d = FundDraft(manager_role_client)                 # объект выводится из фонда с сегодня
    d.call("DELETE", f"units/{u0['id']}")
    d.publish()
    assert units_of(_get(manager_client, a["id"])) == [cat["units"][1]["id"]]


def test_new_unit_takes_unassigned(manager_role_client, manager_client):
    cat = make_category(manager_role_client, n_units=1)
    create_res(manager_client, cat, "2031-09-01", "2031-09-05")
    b = create_res(manager_client, cat, "2031-09-02", "2031-09-04")
    assert units_of(b) == [None]
    d = FundDraft(manager_role_client)
    u = d.call("POST", "units", label=cat["code"] + "-new", category_id=cat["id"])
    d.publish()
    assert units_of(_get(manager_client, b["id"])) == [u["id"]]


def test_no_show_return_earlier_refused(manager_role_client, manager_client, today):
    """M1→Important: вернуть из no-show на дату раньше прежнего заезда нельзя."""
    cat = make_category(manager_role_client)
    g = make_guest(manager_client)
    a = create_res(manager_client, cat, "2031-10-10", "2031-10-14", [(g["id"], "main", None, None)])
    today("2031-10-10")
    r = manager_client.post(f"{API}/reservations/{a['id']}/status", json={"status": "no_show", "version": 1}).json()
    back = manager_client.post(f"{API}/reservations/{a['id']}/status", json={
        "status": "confirmed", "version": r["result"]["version"], "new_check_in": "2031-10-05"})
    assert back.status_code == 422 and back.json()["detail"] == "Новая дата заезда — не раньше прежней"


def test_no_show_return_drops_guest_without_nights(manager_role_client, manager_client, today):
    cat = make_category(manager_role_client)
    a_g, b_g = make_guest(manager_client), make_guest(manager_client)
    a = create_res(manager_client, cat, "2031-11-10", "2031-11-18", [
        (a_g["id"], "main", "2031-11-10", "2031-11-14"), (b_g["id"], "main", "2031-11-14", "2031-11-18")])
    today("2031-11-10")
    r = manager_client.post(f"{API}/reservations/{a['id']}/status", json={"status": "no_show", "version": 1}).json()
    back = manager_client.post(f"{API}/reservations/{a['id']}/status", json={
        "status": "confirmed", "version": r["result"]["version"], "new_check_in": "2031-11-15"})
    assert back.status_code == 200, back.text
    assert [(o["guest_id"], o["date_from"]) for o in back.json()["result"]["occupants"]] == [(b_g["id"], "2031-11-15")]


def test_pin_to_missing_unit_is_422(manager_role_client, manager_client):
    """M2→Important: закрепление на несуществующий объект или сегмент — 422 на любой СУБД."""
    cat = make_category(manager_role_client)
    r = manager_client.post(f"{API}/reservations", json=res_body(cat, "2031-12-01", "2031-12-03", pins={"0": 999999}))
    assert r.status_code == 422 and r.json()["detail"] == "Объект закрепления не найден"
    r = manager_client.post(f"{API}/reservations", json=res_body(cat, "2031-12-01", "2031-12-03",
                                                                 pins={"3": cat["units"][0]["id"]}))
    assert r.status_code == 422 and r.json()["detail"] == "Закрепление для несуществующего сегмента"


def test_module_lock_taken_on_write(manager_role_client, manager_client, sql_counter):
    """I1: запись берёт замок модуля до чтения состояния."""
    cat = make_category(manager_role_client)
    with sql_counter() as c:
        create_res(manager_client, cat, "2032-01-01", "2032-01-03")
    first_write = next(k for k in c["by_statement"] if k.startswith(("SELECT pg_advisory_xact_lock",
                                                                    "UPDATE stays_settings")))
    assert first_write
