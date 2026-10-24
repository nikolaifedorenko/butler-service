"""Шахматка, задача 10: карточки, лента изменений брони, история проживаний гостя."""
from __future__ import annotations

from .helpers import API, create_res, make_category, make_guest


def test_history_shows_field_diff(manager_role_client, manager_client):
    cat = make_category(manager_role_client)
    res = create_res(manager_client, cat, "2029-03-01", "2029-03-05")
    body = {**{k: res[k] for k in ("number", "check_in", "category_id")}, "check_out": "2029-03-07",
            "version": res["version"]}
    assert manager_client.put(f"{API}/reservations/{res['id']}", json=body).status_code == 200
    hist = manager_client.get(f"{API}/reservations/{res['id']}/history").json()
    assert [h["action"] for h in hist] == ["stays_reservation", "stays_reservation"]
    assert hist[0]["diff"]["check_out"] == ["2029-03-05", "2029-03-07"]       # новые сверху
    assert hist[0]["title"] == "Шахматка: бронь" and hist[0]["actor"]


def test_reservation_card_levels(names_client, mgmt_client, occupancy_client, demo_small):
    rid = demo_small.res[3]["id"]
    card = names_client.get(f"{API}/reservations/{rid}/card").json()
    assert [(o["guest"], o["date_from"], o["role"]) for o in card["occupants"]] == [
        (demo_small.guests[4]["last_name"], "2029-02-02", "main"),
        (demo_small.guests[5]["last_name"], "2029-02-03", "main")]
    assert "logistics" not in card and "phone" not in str(card)
    full = mgmt_client.get(f"{API}/reservations/{rid}/card").json()
    assert full["logistics"][0]["description"].startswith("SU")
    assert occupancy_client.get(f"{API}/reservations/{rid}/card").status_code == 403


def test_guest_stays_across_reservations(manager_role_client, manager_client):
    cat = make_category(manager_role_client)
    g = make_guest(manager_client)
    a = create_res(manager_client, cat, "2029-04-01", "2029-04-05", [(g["id"], "main", None, None)])
    host = make_guest(manager_client)
    b = create_res(manager_client, cat, "2029-05-01", "2029-05-03",
                   [(host["id"], "main", None, None), (g["id"], "guest", None, None)])
    card = manager_client.get(f"{API}/guests/{g['id']}/card").json()
    assert [(s["reservation_id"], s["role"], s["date_from"]) for s in card["stays"]] == [
        (b["id"], "guest", "2029-05-01"), (a["id"], "main", "2029-04-01")]
    assert card["stays"][1]["units"] == [cat["units"][0]["label"]]
