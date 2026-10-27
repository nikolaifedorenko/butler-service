"""API версий фонда: снимок на дату, черновик, публикация, справочник флагов."""
from __future__ import annotations

import pytest
from sqlalchemy import delete, func, select, update

from app.modules.stays.adapters.orm import (
    Category,
    CategoryState,
    FundGroup,
    FundVersion,
    GroupState,
    Unit,
    UnitFlag,
    UnitLineage,
    UnitState,
    UnitStateFlag,
)
from app.modules.stays.application import fund_drafts as fd

from .helpers import API, make_category, uniq

pytestmark = pytest.mark.usefixtures("no_allocation")


@pytest.fixture(autouse=True)
def _clean(db):
    """Версии, созданные тестом (черновик и опубликованные), снимаются: схемные тесты миграции
    не терпят лишних версий в общей базе."""
    before = set(db.scalars(select(FundVersion.id)))
    top = {m: db.scalar(select(func.coalesce(func.max(m.id), 0))) for m in (Unit, Category, FundGroup)}
    yield
    db.rollback()
    ids = [i for i in db.scalars(select(FundVersion.id)) if i not in before]
    db.execute(update(FundVersion).where(FundVersion.base_version_id.in_(ids)).values(base_version_id=None))
    db.execute(delete(UnitLineage).where(UnitLineage.version_id.in_(ids)))
    for model in (UnitStateFlag, UnitState, GroupState, CategoryState):
        db.execute(delete(model).where(model.version_id.in_(ids)))
    db.execute(delete(FundVersion).where(FundVersion.id.in_(ids)))
    db.execute(delete(UnitFlag).where(UnitFlag.title.like("апи-флаг-%")))
    for model, last in top.items():
        db.execute(delete(model).where(model.id > last))
    db.commit()


def _today(db) -> str:
    return fd.local_date().isoformat()


def test_setup_required_for_draft_writes(names_client, manager_client):
    for c in (names_client, manager_client):            # только просмотр / старший батлер без stays.setup
        assert c.post(f"{API}/fund/draft", json={"valid_from": "2090-01-01"}).status_code == 403
        assert c.post(f"{API}/fund/draft/categories", json={"rev": 1}).status_code == 403
        assert c.post(f"{API}/fund/draft/publish", json={"rev": 1}).status_code == 403
        assert c.post(f"{API}/fund/flags", json={"title": "x"}).status_code == 403
        assert c.delete(f"{API}/fund/versions/1").status_code == 403


def test_snapshot_readable_by_occupancy(occupancy_client, manager_role_client, db):
    cat = make_category(manager_role_client, n_units=1)
    r = occupancy_client.get(f"{API}/fund/snapshot", params={"date": _today(db)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert {"version", "categories", "groups", "units", "flags"} <= set(body)
    assert {"id", "valid_from", "status", "rev"} <= set(body["version"])
    assert cat["id"] in [c["id"] for c in body["categories"]]
    unit = next(u for u in body["units"] if u["id"] == cat["units"][0]["id"])
    assert unit["flags"] == [] and unit["path"] == []
    assert occupancy_client.get(f"{API}/fund/snapshot").status_code == 422        # ни date, ни version_id
    assert occupancy_client.get(f"{API}/fund/versions").status_code == 200


def test_old_crud_endpoints_gone(manager_role_client):
    assert manager_role_client.post(f"{API}/categories", json={"code": "X"}).status_code in (404, 405)
    assert manager_role_client.put(f"{API}/categories/1", json={}).status_code in (404, 405)
    assert manager_role_client.delete(f"{API}/categories/1").status_code in (404, 405)
    assert manager_role_client.post(f"{API}/units", json={"label": "X"}).status_code in (404, 405)
    assert manager_role_client.put(f"{API}/units/1", json={}).status_code in (404, 405)
    assert manager_role_client.delete(f"{API}/units/1").status_code in (404, 405)


def test_publish_flow_via_api(manager_role_client, db):
    c = manager_role_client
    opened = c.post(f"{API}/fund/draft", json={"valid_from": _today(db), "note": "тест"})
    assert opened.status_code == 200, opened.text
    rev = opened.json()["rev"]
    assert c.post(f"{API}/fund/draft", json={"valid_from": _today(db)}).status_code == 409   # черновик один
    code = "T" + uniq()
    cat = c.post(f"{API}/fund/draft/categories", json={"rev": rev, "code": code, "title": code,
                                                       "kind": "villa", "weight": 3})
    assert cat.status_code == 200, cat.text
    rev = cat.json()["rev"]
    assert rev == opened.json()["rev"] + 1
    unit = c.post(f"{API}/fund/draft/units", json={"rev": rev, "label": code + "-1",
                                                   "category_id": cat.json()["id"]})
    assert unit.status_code == 200, unit.text
    rev = unit.json()["rev"]
    stale = c.put(f"{API}/fund/draft/units/{unit.json()['id']}", json={
        "rev": rev - 1, "label": code + "-2", "category_id": cat.json()["id"]})
    assert stale.status_code == 409
    diff = c.get(f"{API}/fund/draft/diff").json()
    assert [e["id"] for e in diff["units"]] == [unit.json()["id"]] and diff["units"][0]["kind"] == "added"
    assert c.post(f"{API}/fund/draft/publish", json={"rev": rev - 1}).status_code == 409
    pub = c.post(f"{API}/fund/draft/publish", json={"rev": rev})
    assert pub.status_code == 200, pub.text
    snap = c.get(f"{API}/fund/snapshot", params={"date": _today(db)}).json()
    assert unit.json()["id"] in [u["id"] for u in snap["units"]]
    assert snap["version"]["status"] == "published"
    assert c.get(f"{API}/fund/draft/diff").status_code == 422                     # черновика больше нет
    assert not [v for v in c.get(f"{API}/fund/versions").json() if v["status"] == "draft"]


def test_group_split_merge_and_flags_via_api(manager_role_client, db):
    c = manager_role_client
    rev = c.post(f"{API}/fund/draft", json={"valid_from": _today(db)}).json()["rev"]

    def call(method, path, **body):
        nonlocal rev
        r = c.request(method, f"{API}/fund/draft/{path}", json={"rev": rev, **body})
        assert r.status_code == 200, r.text
        rev = r.json()["rev"]
        return r.json()

    code = "T" + uniq()
    cat = call("POST", "categories", code=code, title=code, kind="room", weight=1)["id"]
    grp = call("POST", "groups", title="Корпус " + code)["id"]
    u = call("POST", "units", label=code + "-A", category_id=cat, group_id=grp, floor="2")["id"]
    parts = call("POST", f"units/{u}/split", parts=[{"label": code + "-B"}, {"label": code + "-C"}])["ids"]
    assert len(parts) == 2
    merged = call("POST", "units/merge", unit_ids=parts, label=code + "-D")["id"]
    flag = c.post(f"{API}/fund/flags", json={"title": "апи-флаг-" + uniq()}).json()["id"]
    call("PUT", "flags", flag_id=flag, unit_ids=[merged], value=True)
    draft_id = next(v["id"] for v in c.get(f"{API}/fund/versions").json() if v["status"] == "draft")
    snap = c.get(f"{API}/fund/snapshot", params={"version_id": draft_id}).json()
    unit = next(x for x in snap["units"] if x["id"] == merged)
    assert unit["flags"] == [flag] and unit["path"] == [grp] and unit["floor"] == "2"
    assert next(g for g in snap["groups"] if g["id"] == grp)["path"] == [grp]
    # устаревший rev в DELETE (query) — 409; актуальный — выводит объект
    assert c.delete(f"{API}/fund/draft/units/{merged}", params={"rev": rev - 1}).status_code == 409
    r = c.delete(f"{API}/fund/draft/units/{merged}", params={"rev": rev})
    assert r.status_code == 200 and r.json()["rev"] == rev + 1
    assert c.patch(f"{API}/fund/draft", json={"rev": rev + 1, "valid_from": "2000-01-01"}).status_code == 422
    assert c.patch(f"{API}/fund/draft", json={"rev": rev + 1, "valid_from": "2090-01-01"}).status_code == 200


def test_validation_errors(manager_role_client, db):
    c = manager_role_client
    assert c.post(f"{API}/fund/draft/categories", json={"rev": 1, "code": "X", "title": "x", "kind": "room",
                                                        "weight": 1, "sort_order": 3_000_000_000}).status_code == 422
    assert c.post(f"{API}/fund/draft/categories", json={"rev": 1, "code": "X", "title": "x", "kind": "castle",
                                                        "weight": 1}).status_code == 422
    assert c.post(f"{API}/fund/draft/units", json={"rev": 1, "label": "U", "category_id": 1}).status_code == 422  # черновика нет
    assert c.post(f"{API}/fund/draft/units/1/split", json={"rev": 1, "parts": [{"label": "a"}]}).status_code == 422


def test_delete_version_rules(manager_role_client, db):
    first = min(v["valid_from"] for v in manager_role_client.get(f"{API}/fund/versions").json())
    vid = next(v["id"] for v in manager_role_client.get(f"{API}/fund/versions").json()
               if v["valid_from"] == first)
    assert manager_role_client.delete(f"{API}/fund/versions/{vid}").status_code == 409     # исходная
    assert manager_role_client.delete(f"{API}/fund/versions/999999").status_code == 422


def test_flag_dictionary_crud(manager_role_client, db):
    c = manager_role_client
    title = "апи-флаг-" + uniq()
    r = c.post(f"{API}/fund/flags", json={"title": title, "color": "#112233"})
    assert r.status_code == 200, r.text
    fid = r.json()["id"]
    assert c.post(f"{API}/fund/flags", json={"title": title}).status_code == 409           # дубль
    assert c.post(f"{API}/fund/flags", json={"title": "x", "color": "red"}).status_code == 422
    assert c.put(f"{API}/fund/flags/{fid}", json={"title": title + "!", "color": "#445566"}).status_code == 200
    flags = c.get(f"{API}/fund/snapshot", params={"date": _today(db)}).json()["flags"]
    row = next(f for f in flags if f["id"] == fid)
    assert row["title"] == title + "!" and row["color"] == "#445566" and row["archived"] is False
    assert c.put(f"{API}/fund/flags/{fid}/archive", json={"archived": True}).status_code == 200
    flags = c.get(f"{API}/fund/snapshot", params={"date": _today(db)}).json()["flags"]
    assert next(f for f in flags if f["id"] == fid)["archived"] is True
    assert c.delete(f"{API}/fund/flags/{fid}").status_code == 200
    assert db.scalar(select(UnitFlag.id).where(UnitFlag.id == fid)) is None
    assert c.delete(f"{API}/fund/flags/{fid}").status_code == 422
