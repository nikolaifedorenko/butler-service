"""Обозначения объектов на дату события при двух версиях фонда (stays-fund-versions §3.1):
объект переименован 4003 → 4103 с даты D — до границы видно старое, после — новое."""
from __future__ import annotations

from .helpers import API, create_res, make_category, make_guest

T, D = "2034-01-10", "2034-02-10"          # «сегодня» модуля и дата новой версии


def test_unit_label_follows_fund_version_by_date(manager_role_client, manager_client, today):
    today(T)
    cat = make_category(manager_role_client, n_units=1)
    unit = cat["units"][0]
    g = make_guest(manager_client)
    # два сегмента вокруг D: переезд 11.02 в ту же категорию — единственный объект остаётся тем же
    r = create_res(manager_client, cat, "2034-02-08", "2034-02-13", [(g["id"], "main", None, None)],
                   moves=[{"move_date": "2034-02-11", "category_id": cat["id"]}])
    opened = manager_role_client.post(f"{API}/fund/draft", json={"valid_from": D})
    assert opened.status_code == 200, opened.text
    renamed = cat["code"] + "-нов"
    put = manager_role_client.put(f"{API}/fund/draft/units/{unit['id']}", json={
        "rev": opened.json()["rev"], "label": renamed, "category_id": cat["id"]})
    assert put.status_code == 200, put.text
    assert manager_role_client.post(f"{API}/fund/draft/publish",
                                    json={"rev": put.json()["rev"]}).status_code == 200

    card = manager_client.get(f"{API}/reservations/{r['id']}/card").json()
    assert [(s["start"], s["unit_id"], s["unit"]) for s in card["segments"]] == [
        ("2034-02-08", unit["id"], unit["label"]), ("2034-02-11", unit["id"], renamed)]   # на начало сегмента

    def day_unit(day: str) -> str:
        rows = manager_client.get(f"{API}/day", params={"date": day}).json()["in_house"]
        return next(x["unit"] for x in rows if x["reservation_id"] == r["id"])
    assert day_unit("2034-02-09") == unit["label"]            # ночь до границы — прежняя версия
    assert day_unit("2034-02-12") == renamed                  # после границы — новая

    stays = manager_client.get(f"{API}/guests/{g['id']}/card").json()["stays"]
    assert next(s for s in stays if s["reservation_id"] == r["id"])["units"] == [unit["label"]]   # на дату записи
