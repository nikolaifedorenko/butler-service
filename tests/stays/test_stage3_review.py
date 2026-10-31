"""Ревью этапа 3: заморозка при сохранении формы, история по уровням, деактивация объекта,
группа от нового члена, название блока без персональных данных."""
from __future__ import annotations

from .helpers import API, FundDraft, create_res, make_category, make_guest, units_of


def _get(c, rid):
    return c.get(f"{API}/reservations/{rid}").json()


def _body(res, **ch):
    return {**{k: res[k] for k in ("number", "check_in", "check_out", "category_id", "early", "late",
                                   "group_id", "note", "declined_butler")},
            "moves": res["moves"], "occupants": res["occupants"], "companions": res["companions"],
            "logistics": res["logistics"], "version": res["version"], **ch}


def test_form_auto_pin_keeps_in_house_unit(manager_role_client, manager_client, today):
    """C1: «Авто» в форме не стирает объект заселённой брони."""
    today("2033-01-05")
    cat = make_category(manager_role_client, n_units=2)
    blocker = create_res(manager_client, cat, "2033-01-03", "2033-01-04")
    a = create_res(manager_client, cat, "2033-01-03", "2033-01-09", pins={"0": cat["units"][1]["id"]})
    manager_client.post(f"{API}/reservations/{a['id']}/status", json={"status": "in_house", "version": a["version"]})
    manager_client.post(f"{API}/reservations/{blocker['id']}/status", json={"status": "cancelled",
                                                                            "version": blocker["version"]})
    cur = _get(manager_client, a["id"])
    r = manager_client.put(f"{API}/reservations/{a['id']}", json=_body(cur, note="правка", pins={"0": None}))
    assert r.status_code == 200
    assert units_of(_get(manager_client, a["id"])) == [cat["units"][1]["id"]]


def test_history_hides_full_fields_for_names(manager_role_client, manager_client, names_client):
    """I1: в ленте изменений уровня «с фамилиями» нет примечаний, заказчика и id гостей."""
    cat = make_category(manager_role_client)
    g = make_guest(manager_client, "Историков")
    res = create_res(manager_client, cat, "2033-02-01", "2033-02-03", [(g["id"], "main", None, None)],
                     note="СекретнаяЗаметка", customer="ТайныйЗаказчик")
    body = names_client.get(f"{API}/reservations/{res['id']}/history").text
    assert "СекретнаяЗаметка" not in body and "ТайныйЗаказчик" not in body and '"note"' not in body
    assert "Историков" in body                      # состав — короткими именами
    full = manager_client.get(f"{API}/reservations/{res['id']}/history").text
    assert "СекретнаяЗаметка" in full


def test_deactivate_unit_keeps_past_segment(manager_role_client, manager_client, today):
    """I2: вывод объекта из фонда не переписывает прошедшие ночи брони."""
    cat = make_category(manager_role_client, n_units=2)
    a = create_res(manager_client, cat, "2033-03-01", "2033-03-20",
                   moves=[{"move_date": "2033-03-05", "category_id": cat["id"]}])
    u_past = units_of(_get(manager_client, a["id"]))[0]
    today("2033-03-10")
    d = FundDraft(manager_role_client)                 # версия с «сегодня» 10.03 без объекта
    d.call("DELETE", f"units/{u_past}")
    d.publish()
    assert units_of(_get(manager_client, a["id"]))[0] == u_past


def test_new_group_member_adopts_group_moves(manager_role_client, manager_client):
    """I4: новичок группы получает её переезды, а не стирает их."""
    cat = make_category(manager_role_client, n_units=3)
    gid = manager_client.post(f"{API}/groups", json={"title": "Г"}).json()["id"]
    mv = [{"move_date": "2033-04-05", "category_id": cat["id"]}]
    a = create_res(manager_client, cat, "2033-04-01", "2033-04-09", group_id=gid, moves=mv)
    b = create_res(manager_client, cat, "2033-04-01", "2033-04-09", group_id=gid)
    assert _get(manager_client, a["id"])["moves"] == mv
    assert b["moves"] == mv


def test_hold_title_hidden_for_occupancy(manager_role_client, manager_client, occupancy_client):
    cat = make_category(manager_role_client, n_units=1)
    manager_client.post(f"{API}/holds", json={"unit_id": cat["units"][0]["id"], "start": "2033-05-01",
                                              "end": "2033-05-03", "kind": "ooo", "title": "Под Иванова"})
    q = {"first": "2033-05-01", "last": "2033-05-05", "category_ids": cat["id"]}
    assert "Под Иванова" not in occupancy_client.get(f"{API}/board/units", params=q).text
    assert "Под Иванова" in manager_client.get(f"{API}/board/units", params=q).text
