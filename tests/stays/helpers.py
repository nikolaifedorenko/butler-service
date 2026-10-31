"""Помощники тестов «Шахматки»: своя категория с объектами на каждый тест — распределение
по объектам глобально, а отдельная категория изолирует тесты друг от друга."""
from __future__ import annotations

import uuid

API = "/api/stays"


def uniq() -> str:
    return uuid.uuid4().hex[:6].upper()


# виды категорий демо-сида: код в тестах → название в справочнике видов
KIND_TITLES = {"villa": "вилла", "estate": "имение", "apartment": "апартаменты", "room": "номер"}


def kind_id(code: str) -> int:
    """id вида демо-справочника по прежнему коду (villa, room…)."""
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.modules.stays.adapters.orm import CategoryKind

    with SessionLocal() as s:
        kid = s.scalar(select(CategoryKind.id).where(CategoryKind.title == KIND_TITLES[code]))
    assert kid is not None, f"нет вида «{KIND_TITLES[code]}» в справочнике"
    return kid


class FundDraft:
    """Черновик фонда через API: открывает черновик на сегодня модуля (или берёт
    существующий), ведёт rev, публикует; при ошибке публикации черновик удаляется —
    иначе он заблокировал бы остальные тесты."""

    def __init__(self, setup_client):
        from app.modules.stays.application import fund_drafts

        self.c = setup_client
        r = setup_client.post(f"{API}/fund/draft", json={"valid_from": fund_drafts.local_date().isoformat()})
        if r.status_code == 409:                  # черновик уже есть — работаем в нём
            versions = setup_client.get(f"{API}/fund/versions").json()
            draft = next(v for v in versions if v["status"] == "draft")
            self.rev = setup_client.get(f"{API}/fund/snapshot",
                                        params={"version_id": draft["id"]}).json()["version"]["rev"]
        else:
            assert r.status_code == 200, r.text
            self.rev = r.json()["rev"]

    def call(self, method: str, path: str, **body) -> dict:
        if method == "DELETE":
            resp = self.c.delete(f"{API}/fund/draft/{path}", params={"rev": self.rev})
        else:
            resp = self.c.request(method, f"{API}/fund/draft/{path}", json={"rev": self.rev, **body})
        assert resp.status_code == 200, resp.text
        self.rev = resp.json()["rev"]
        return resp.json()

    def publish(self) -> None:
        try:
            resp = self.c.post(f"{API}/fund/draft/publish", json={"rev": self.rev})
            assert resp.status_code == 200, resp.text
        except BaseException:
            draft = next((v for v in self.c.get(f"{API}/fund/versions").json() if v["status"] == "draft"), None)
            if draft:
                self.c.delete(f"{API}/fund/versions/{draft['id']}")
            raise


def make_category(setup_client, n_units: int = 2, kind: str = "villa", escorted: bool = True,
                  weight: float = 4, group_id: int | None = None) -> dict:
    """Категория с объектами через черновик фонда (FundDraft) с публикацией.
    Возвращает {id, code, units: [{id, label}]}."""
    d = FundDraft(setup_client)
    code = "T" + uniq()
    cat = {"id": d.call("POST", "categories", code=code, title=code, kind_id=kind_id(kind), escorted=escorted,
                        weight=weight)["id"], "code": code}
    cat["units"] = []
    for i in range(n_units):
        label = f"{code}-{i + 1}"
        body = {"label": label, "category_id": cat["id"]}
        if group_id is not None:
            body["group_id"] = group_id
        cat["units"].append({"id": d.call("POST", "units", **body)["id"], "label": label})
    d.publish()
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
