"""Шахматка, задача 17: уровень «загрузка без гостей» не получает ни одного поля гостя ни в одном
GET-ответе модуля (§8, «На что смотреть» №4). Маршруты собираются из приложения."""
from __future__ import annotations

import re

from fastapi.routing import APIRoute

from tests.test_authz_matrix import _flat

from .conftest import assert_no_pd
from .helpers import API, create_res, make_category, make_guest


def test_occupancy_level_never_sees_guests(app_stack, occupancy_client, manager_role_client, manager_client):
    cat = make_category(manager_role_client, n_units=2)
    g = make_guest(manager_client, "Утечкин", level="vvip")
    res = create_res(manager_client, cat, "2038-03-02", "2038-03-05", [(g["id"], "main", None, None)],
                     note="УтечкаЗаметка", customer="УтечкаЗаказчик",
                     logistics=[{"kind": "flight", "date": "2038-03-02", "time": "07:00", "description": "УтечкаРейс"}])
    manager_client.post(f"{API}/ooo", json={"unit_id": cat["units"][1]["id"], "start": "2038-03-01",
                                              "end": "2038-03-02", "start_half": "AM", "end_half": "PM", "reason": "Покраска"})
    words = {"Утечкин", "УтечкаЗаметка", "УтечкаЗаказчик", "УтечкаРейс", res["number"]}
    fill = {"rid": str(res["id"]), "gid": str(g["id"]), "line_id": "1"}
    query = {"first": "2038-03-01", "last": "2038-03-07", "date": "2038-03-03", "day": "2038-03-03",
             "reservation_id": str(res["id"]), "q": "Утечкин", "kind": "anon"}
    checked = 0
    for r in _flat(app_stack["app"].routes):
        if not (isinstance(r, APIRoute) and r.path.startswith(API) and "GET" in r.methods):
            continue
        path = re.sub(r"\{(\w+)\}", lambda m: fill.get(m.group(1), "1"), r.path)
        # kind — параметр выгрузки; видам шахматки прежний одиночный kind — 422 (kind_ids, §7)
        resp = occupancy_client.get(path, params=query if "export" in path else
                                    {k: v for k, v in query.items() if k != "kind"})
        if resp.status_code == 200 and resp.headers["content-type"].startswith("application/json"):
            assert_no_pd(resp.json(), words, path)
            checked += 1
    assert checked >= 4          # шахматка, табло, загрузка, фонд как минимум
