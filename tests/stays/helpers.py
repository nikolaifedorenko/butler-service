"""Помощники тестов «Шахматки»: своя категория с объектами на каждый тест — распределение
по объектам глобально, а отдельная категория изолирует тесты друг от друга."""
from __future__ import annotations

import uuid

API = "/api/stays"


def uniq() -> str:
    return uuid.uuid4().hex[:6].upper()


def make_category(setup_client, n_units: int = 2, kind: str = "villa", escorted: bool = True,
                  weight: float = 4, group_id: int | None = None) -> dict:
    """Категория с объектами через черновик фонда: открывает черновик на сегодня (или берёт
    существующий), заводит категорию и объекты и публикует. Возвращает {id, code, units: [{id, label}]}."""
    from app.modules.stays.application import fund_drafts

    r = setup_client.post(f"{API}/fund/draft", json={"valid_from": fund_drafts.local_date().isoformat()})
    if r.status_code == 409:                      # черновик уже есть — работаем в нём
        versions = setup_client.get(f"{API}/fund/versions").json()
        draft = next(v for v in versions if v["status"] == "draft")
        rev = setup_client.get(f"{API}/fund/snapshot", params={"version_id": draft["id"]}).json()["version"]["rev"]
    else:
        assert r.status_code == 200, r.text
        rev = r.json()["rev"]

    def post(path: str, body: dict) -> dict:
        nonlocal rev
        resp = setup_client.post(f"{API}/fund/draft/{path}", json={"rev": rev, **body})
        assert resp.status_code == 200, resp.text
        rev = resp.json()["rev"]
        return resp.json()

    code = "T" + uniq()
    cat = {"id": post("categories", {"code": code, "title": code, "kind": kind,
                                     "escorted": escorted, "weight": weight})["id"], "code": code}
    cat["units"] = []
    for i in range(n_units):
        label = f"{code}-{i + 1}"
        body = {"label": label, "category_id": cat["id"]}
        if group_id is not None:
            body["group_id"] = group_id
        cat["units"].append({"id": post("units", body)["id"], "label": label})
    try:
        resp = setup_client.post(f"{API}/fund/draft/publish", json={"rev": rev})
        assert resp.status_code == 200, resp.text
    except BaseException:                         # не оставляем черновик: он заблокировал бы остальные тесты
        draft = next((v for v in setup_client.get(f"{API}/fund/versions").json() if v["status"] == "draft"), None)
        if draft:
            setup_client.delete(f"{API}/fund/versions/{draft['id']}")
        raise
    return cat


def make_guest(client, last: str | None = None, level: str = "regular") -> dict:
    r = client.post(f"{API}/guests", json={"last_name": last or "Гость" + uniq(), "level": level})
    assert r.status_code == 200, r.text
    return r.json()


def res_body(cat: dict, ci: str, co: str, guests=(), **kw) -> dict:
    """guests: [(guest_id, role, date_from, date_to)]; по умолчанию даты — вся бронь."""
    occ = [{"guest_id": g, "role": role, "date_from": f or ci, "date_to": t or co}
           for g, role, f, t in guests]
    return {"number": kw.pop("number", "R" + uniq()), "check_in": ci, "check_out": co,
            "category_id": cat["id"], "occupants": occ, **kw}


def create_res(client, cat: dict, ci: str, co: str, guests=(), **kw) -> dict:
    r = client.post(f"{API}/reservations", json=res_body(cat, ci, co, guests, **kw))
    assert r.status_code == 200, r.text
    return r.json()["result"]


def units_of(res: dict) -> list:
    return [s["unit_id"] for s in res["segments"]]
