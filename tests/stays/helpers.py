"""Помощники тестов «Шахматки»: своя категория с объектами на каждый тест — распределение
по объектам глобально, а отдельная категория изолирует тесты друг от друга."""
from __future__ import annotations

import uuid

API = "/api/stays"


def uniq() -> str:
    return uuid.uuid4().hex[:6].upper()


def make_category(setup_client, n_units: int = 2, kind: str = "villa", escorted: bool = True,
                  weight: float = 4, building: str = "1") -> dict:
    code = "T" + uniq()
    cat = setup_client.post(f"{API}/categories", json={"code": code, "title": code, "kind": kind,
                                                       "escorted": escorted, "weight": weight}).json()
    cat["units"] = [setup_client.post(f"{API}/units", json={
        "label": f"{code}-{i + 1}", "category_id": cat["id"], "building": building}).json()
        for i in range(n_units)]
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
