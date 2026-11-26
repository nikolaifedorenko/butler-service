"""Календарь событий гостя: сроки проживания, доступ и фильтры относятся к гостям события."""
from __future__ import annotations

import datetime as dt

from tests.stays.helpers import API, create_res, make_category, make_code, make_guest, set_guest
from tests.stays.test_mine_ownership import _line, ivanov_grant  # noqa: F401 — фикстура pytest

URL = f"{API}/guest-events"
DAY = dt.date(2071, 9, 15)
MONTH = DAY.replace(day=1).isoformat()


def _calendar(client, **filters):
    res = client.get(URL, params={"month": MONTH, **filters})
    assert res.status_code == 200, res.text
    return res.json()


def _people(event):
    return {g["guest_id"]: g["status"] for g in event["people"]}


def _labels(client, *guests, **filters):
    ids = {g["id"] for g in guests}
    return {(e["kind"], e["title"], tuple(p["guest_id"] for p in e["people"]))
            for e in _calendar(client, **filters)["events"] if ids & _people(e).keys()}


def _spouse(client, a, b, **patch):
    result = client.post(f"{API}/guests/{a['id']}/links", json={
        "kind": "spouse", "guest_id": b["id"], "marriage_start": "2018-09-15", **patch,
    })
    assert result.status_code == 200, result.text


def _reservation(client, cat, guest, start, end, **kw):
    return create_res(client, cat, start, end, [(guest["id"], "main", None, None)], **kw)


def test_calendar_defaults_to_object_local_date_and_rejects_non_month_start(mgmt_client, monkeypatch):
    from app.core.time import TZ

    midnight = dt.datetime(2026, 11, 26, 0, 10, tzinfo=TZ)
    monkeypatch.setattr("app.core.time.local_now", lambda: midnight)
    result = mgmt_client.get(URL)
    assert result.status_code == 200, result.text
    assert (result.json()["month"], result.json()["today"]) == ("2026-11-01", "2026-11-26")
    assert mgmt_client.get(URL, params={"month": "2026-11-02"}).status_code == 422


def test_calendar_excludes_occupancy_and_names_only_roles(occupancy_client, names_client):
    for client in (occupancy_client, names_client):
        assert client.get(URL).status_code == 403


def test_events_do_not_require_stays_and_structured_wedding_replaces_only_its_manual_label(mgmt_client, manager_client):
    a, b, ex, ex_partner = (make_guest(manager_client) for _ in range(4))
    set_guest(a["id"], birth_date=dt.date(1980, 9, 2), special_dates=[
        {"date": "2018-09-15", "what": "  годовщина свадьбы  "}, {"date": "2019-09-16", "what": "Годовщина свадьбы"},
        {"date": "2020-09-15", "what": "Годовщина открытия"},
    ])
    set_guest(ex["id"], special_dates=[{"date": "2018-09-15", "what": "Годовщина свадьбы"}])
    _spouse(manager_client, a, b)
    _spouse(manager_client, ex, ex_partner, former=True)
    result = _calendar(mgmt_client)
    assert result["filters"]["guest_details"] is True
    events = [e for e in result["events"] if (_people(e).keys() & {a["id"], b["id"], ex["id"]})]
    assert [(e["date"], e["kind"], e["title"]) for e in events] == [
        ("2071-09-02", "birthday", "День рождения"),
        ("2071-09-15", "wedding", "Годовщина свадьбы"),
        ("2071-09-15", "special", "Годовщина открытия"),
        ("2071-09-15", "special", "Годовщина свадьбы"),
        ("2071-09-16", "special", "Годовщина свадьбы"),
    ]
    assert _people(events[1]) == {a["id"]: "none", b["id"]: "none"}
    assert not _labels(mgmt_client, a, b, confirmed_only=True)


def test_calendar_status_and_confirmed_presence_filters_use_occupant_dates(
        manager_role_client, manager_client, mgmt_client):
    cat = make_category(manager_role_client, n_units=5)
    guests = {name: make_guest(manager_client) for name in ("staying", "arrival", "checkout", "tentative", "none")}
    for g in guests.values():
        set_guest(g["id"], birth_date=dt.date(1980, 9, 15))
    _reservation(manager_client, cat, guests["staying"], "2071-09-14", "2071-09-17")
    a = create_res(manager_client, cat, "2071-09-14", "2071-09-17", [
        (make_guest(manager_client)["id"], "main", None, None),
        (guests["arrival"]["id"], "guest", "2071-09-15", "2071-09-17")])
    _reservation(manager_client, cat, guests["checkout"], "2071-09-13", "2071-09-15")
    _reservation(manager_client, cat, guests["tentative"], "2071-09-15", "2071-09-17", status="tentative")
    for confirmed in (False, True):
        ids = {g["id"] for g in guests.values()}
        result = _calendar(mgmt_client, kind="birthday", confirmed_only=confirmed)
        actual = {p["guest_id"]: p for e in result["events"] for p in e["people"] if p["guest_id"] in ids}
        expected = {g["id"]: st for st, g in guests.items() if not confirmed or st in ("staying", "arrival", "checkout")}
        assert {key: p["status"] for key, p in actual.items()} == expected
        assert actual[guests["arrival"]["id"]]["unit"] in {u["label"] for u in cat["units"]}
        arrival = actual[guests["arrival"]["id"]]
        assert arrival["reservation_id"] == a["id"]
        assert mgmt_client.get(f"{API}/reservations/{arrival['reservation_id']}/card").status_code == 200
        if not confirmed:
            assert actual[guests["none"]["id"]]["reservation_id"] is None


def test_calendar_mine_limits_names_and_status_to_accessible_people_and_nights(
        manager_role_client, manager_client, butler_client, butlers):
    cat = make_category(manager_role_client, n_units=3)
    own_code, foreign_code = (make_code(manager_role_client) for _ in range(2))
    a = make_guest(manager_client, special=True, vip_code_id=own_code["id"])
    b = make_guest(manager_client, vip_code_id=foreign_code["id"])
    c = make_guest(manager_client)
    set_guest(a["id"], birth_date=dt.date(1980, 9, 16))
    set_guest(b["id"], birth_date=dt.date(1980, 9, 16))
    set_guest(c["id"], birth_date=dt.date(1980, 9, 16))
    _spouse(manager_client, a, b)
    for guest in (a, c):
        r = _reservation(manager_client, cat, guest, "2071-08-10", "2071-08-12")
        _line(butlers["a"], dt.date(2071, 8, 10), r["id"])
    group = manager_client.post(f"{API}/groups", json={"title": "Гости календаря"})
    assert group.status_code == 200, group.text
    gid = group.json()["id"]
    r = _reservation(manager_client, cat, a, "2071-09-15", "2071-09-18", group_id=gid)
    unrelated = make_guest(manager_client)
    _reservation(manager_client, cat, unrelated, "2071-09-15", "2071-09-18", group_id=gid)
    _line(butlers["a"], DAY, group_id=gid)
    _line(butlers["b"], DAY, r["id"], guests=(a["id"],))
    _line(butlers["a"], DAY + dt.timedelta(days=1), group_id=gid)
    result = _calendar(butler_client)
    assert result["filters"]["guest_details"] is True
    options = {option["id"]: option["code"] for option in result["filters"]["vip_codes"]}
    assert options[own_code["id"]] == own_code["code"]
    assert foreign_code["id"] not in options
    wedding = next(e for e in result["events"] if e["kind"] == "wedding" and a["id"] in _people(e))
    assert _people(wedding) == {a["id"]: "unavailable"}
    bride = wedding["people"][0]
    assert bride["unit"] is None and bride["reservation_id"] is None
    assert bride["vip_code"] == own_code["code"]
    assert bride["special"] is True
    people = {p["guest_id"]: p for e in result["events"] if e["kind"] == "birthday" for p in e["people"]}
    assert people[a["id"]]["status"] == "staying"
    assert people[a["id"]]["reservation_id"] == r["id"]
    assert butler_client.get(f"{API}/reservations/{r['id']}/card").status_code == 200
    assert people[c["id"]]["status"] == "unavailable"
    assert b["id"] not in people
    assert not _labels(butler_client, a, b, kind="wedding", confirmed_only=True)
    assert _labels(butler_client, a, b, kind="wedding", vip_code_ids=own_code["id"], special=True)
    assert not _labels(butler_client, a, b, kind="wedding", vip_code_ids=foreign_code["id"])
    assert not _labels(butler_client, c, special=True)


def test_calendar_filters_require_one_matching_spouse_and_allow_any_selected_vip(
        manager_role_client, manager_client, mgmt_client):
    vip_a, vip_b = (make_code(manager_role_client) for _ in range(2))
    cat = make_category(manager_role_client, n_units=1)
    a = make_guest(manager_client, special=True, vip_code_id=vip_a["id"])
    b = make_guest(manager_client, vip_code_id=vip_b["id"])
    _spouse(manager_client, a, b)
    _reservation(manager_client, cat, b, "2071-09-14", "2071-09-17")
    assert _labels(mgmt_client, a, b, kind="wedding", confirmed_only=True, vip_code_ids=[vip_a["id"], vip_b["id"]])
    assert not _labels(mgmt_client, a, b, kind="wedding", confirmed_only=True, vip_code_ids=vip_a["id"])
    assert not _labels(mgmt_client, a, b, kind="wedding", confirmed_only=True, special=True)
    assert not _labels(mgmt_client, a, b, kind="birthday")
    assert _labels(mgmt_client, a, b, kind="wedding", special=True, vip_code_ids=vip_a["id"])


def test_profile_access_does_not_grant_foreign_stays_or_remove_own_stay_access(
        manager_role_client, manager_client, butler_client, butlers, ivanov_grant):
    cat = make_category(manager_role_client, n_units=2)
    owned, foreign = (make_guest(manager_client) for _ in range(2))
    for guest in (owned, foreign):
        set_guest(guest["id"], birth_date=dt.date(1980, 9, 15))
    reservation = _reservation(manager_client, cat, owned, "2071-09-15", "2071-09-17")
    _reservation(manager_client, cat, foreign, "2071-09-15", "2071-09-17")
    _line(butlers["a"], DAY, reservation["id"])
    ivanov_grant("stays.guests", "allow")
    ivanov_grant("stays.view")
    result = _calendar(butler_client, kind="birthday")
    people = {p["guest_id"]: p for e in result["events"] for p in e["people"]}
    assert people[owned["id"]]["status"] == "arrival"
    assert people[owned["id"]]["reservation_id"] is None
    assert butler_client.get(f"{API}/reservations/{reservation['id']}/card").status_code == 403
    assert people[foreign["id"]]["status"] == "unavailable"
    assert people[foreign["id"]]["unit"] is None


def test_birthdays_skip_marriages_and_assignments_for_unrelated_bookings(
        manager_role_client, manager_client, mgmt_client, sql_counter):
    birthday = make_guest(manager_client)
    set_guest(birthday["id"], birth_date=dt.date(1980, 10, 15))
    cat = make_category(manager_role_client, n_units=1)
    _reservation(manager_client, cat, make_guest(manager_client), "2071-10-14", "2071-10-17")
    with sql_counter() as queries:
        response = mgmt_client.get(URL, params={"month": "2071-10-01", "kind": "birthday"})
    assert response.status_code == 200, response.text
    assert any(_people(event) == {birthday["id"]: "none"} for event in response.json()["events"])
    for table in ("guests_links", "stays_assignments"):
        assert not any(table in statement for statement in queries["by_statement"])
