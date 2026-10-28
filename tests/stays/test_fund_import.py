"""Загрузка файла фонда черновиком с даты (спецификация stays-fund-versions §9.2–9.3)."""
from __future__ import annotations

import io
import json

from openpyxl import load_workbook
from sqlalchemy import func, select

from app.core.audit import AuditLog
from app.modules.stays.adapters.orm import Category, FundVersion, Unit, UnitFlag, UnitLineage
from app.modules.stays.application import fund_drafts as fd
from app.modules.stays.application import fund_xlsx as fx

from .helpers import API, FundDraft, uniq
from .test_fund_versions_api import _clean  # noqa: F401 — autouse: снять версии и сущности теста

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _today() -> str:
    return fd.local_date().isoformat()


def _seed(c) -> dict:
    """Своя категория (дробный вес), два уровня дерева с порядком, два объекта, флаг."""
    d = FundDraft(c)
    code = "T" + uniq()
    cat = d.call("POST", "categories", code=code, title="Кат " + code, kind="villa", weight=1.5,
                 escorted=True, sort_order=7)["id"]
    top = d.call("POST", "groups", title="Корпус " + code, sort_order=3)["id"]
    sub = d.call("POST", "groups", title="Блок", parent_id=top, sort_order=2)["id"]
    u1 = d.call("POST", "units", label=code + "-1", category_id=cat, group_id=sub, floor="2")["id"]
    u2 = d.call("POST", "units", label=code + "-2", category_id=cat)["id"]
    flag = c.post(f"{API}/fund/flags", json={"title": "апи-флаг-" + uniq(), "color": "#112233"}).json()["id"]
    d.call("PUT", "flags", flag_id=flag, unit_ids=[u1], value=True)
    d.publish()
    return {"code": code, "cat": cat, "top": top, "sub": sub, "u1": u1, "u2": u2, "flag": flag}


def _export(c) -> bytes:
    r = c.get(f"{API}/fund/export", params={"date": _today()})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith(XLSX)
    return r.content


def _upload(c, data: bytes, day: str | None = None):
    return c.post(f"{API}/fund/import", data={"valid_from": day or _today()},
                  files={"file": ("fund.xlsx", data, XLSX)})


def _edit(data: bytes, fn) -> bytes:
    wb = load_workbook(io.BytesIO(data))
    fn(wb)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _row(ws, value) -> int:
    """Номер строки, где в колонке ID стоит value."""
    return next(r for r in range(2, ws.max_row + 1) if ws.cell(r, 1).value == value)


def _draft(db) -> FundVersion | None:
    db.expire_all()
    return db.scalar(select(FundVersion).where(FundVersion.status == "draft"))


def _units(diff: dict, kind: str) -> list[int]:
    return [e["id"] for e in diff["units"] if e["kind"] == kind]


def test_roundtrip_is_empty_draft(manager_role_client, db):
    """Выгрузили и загрузили без правок — черновик без единого изменения: веса (float против
    Decimal), порядок дерева и категорий, флаги, этажи и номера."""
    c = manager_role_client
    s = _seed(c)
    r = _upload(c, _export(c))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["diff"] == {"units": [], "categories": [], "groups": [], "flags": []}
    assert body["retired"] == []
    draft = _draft(db)
    assert draft is not None and body["id"] == draft.id and body["rev"] == draft.rev
    mine = c.get(f"{API}/fund/snapshot", params={"version_id": draft.id}).json()
    base = c.get(f"{API}/fund/snapshot", params={"version_id": draft.base_version_id}).json()
    for k in ("categories", "groups", "units", "flags"):
        assert mine[k] == base[k], k
    unit = next(u for u in mine["units"] if u["id"] == s["u1"])
    assert unit["flags"] == [s["flag"]] and unit["floor"] == "2" and unit["path"] == [s["top"], s["sub"]]
    assert next(x for x in mine["categories"] if x["id"] == s["cat"])["weight"] == 1.5
    log = db.scalars(select(AuditLog).where(AuditLog.action == "stays_fund_import")
                     .order_by(AuditLog.id.desc())).first()
    assert log is not None and log.target == f"fund_draft:{draft.id}"
    assert json.loads(log.payload_json)["filename"] == "fund.xlsx"


def test_missing_row_retires(manager_role_client, db):
    c = manager_role_client
    s = _seed(c)
    data = _edit(_export(c), lambda wb: wb["Объекты"].delete_rows(_row(wb["Объекты"], s["u2"])))
    r = _upload(c, data)
    assert r.status_code == 200, r.text
    body = r.json()
    assert _units(body["diff"], "retired") == [s["u2"]]
    assert body["retired"] == [{"entity": "unit", "id": s["u2"], "name": s["code"] + "-2"}]
    assert not _units(body["diff"], "added") and not _units(body["diff"], "changed")


def test_empty_id_creates(manager_role_client, db):
    c = manager_role_client
    s = _seed(c)
    flag_title = "апи-флаг-" + uniq()

    def add(wb):
        ws = wb["Объекты"]
        col = ws.max_column + 1
        ws.cell(1, col, flag_title)                       # новая колонка — новый флаг
        ws.append([None, s["code"] + "-3", s["code"], f"Корпус {s['code']} / Блок", "5", None])
        ws.cell(ws.max_row, col, "да")
        ws = wb["Дерево"]
        ws.append([None, f"Корпус {s['code']} / Флигель", 9])
    r = _upload(c, _edit(_export(c), add))
    assert r.status_code == 200, r.text
    diff = r.json()["diff"]
    added = [e for e in diff["units"] if e["kind"] == "added"]
    assert len(added) == 1 and not _units(diff, "retired")
    new = added[0]
    assert new["after"]["label"] == s["code"] + "-3" and new["after"]["category_id"] == s["cat"]
    assert new["after"]["group_id"] == s["sub"] and new["after"]["floor"] == "5"
    flag_id = db.scalar(select(UnitFlag.id).where(UnitFlag.title == flag_title))
    assert flag_id is not None and new["after"]["flags"] == [flag_id]
    groups = [e for e in diff["groups"] if e["kind"] == "added"]
    assert len(groups) == 1 and groups[0]["after"] == {"parent_id": s["top"], "title": "Флигель", "sort_order": 9}


def test_from_column_lineage(manager_role_client, db):
    """Деление файлом: строка 12134 удалена, добавлены две строки «из 12134»."""
    c = manager_role_client
    s = _seed(c)

    def split(wb):
        ws = wb["Объекты"]
        ws.delete_rows(_row(ws, s["u2"]))
        ws.append([None, s["code"] + "-2a", s["code"], None, None, str(s["u2"])])
        ws.append([None, s["code"] + "-2b", s["code"], None, None, f"{s['u2']}, {s['u1']}"])
    r = _upload(c, _edit(_export(c), split))
    assert r.status_code == 200, r.text
    diff = r.json()["diff"]
    assert _units(diff, "retired") == [s["u2"]]
    new = {e["after"]["label"]: e["id"] for e in diff["units"] if e["kind"] == "added"}
    assert set(new) == {s["code"] + "-2a", s["code"] + "-2b"}
    draft = _draft(db)
    rows = set(db.execute(select(UnitLineage.unit_id, UnitLineage.predecessor_id)
                          .where(UnitLineage.version_id == draft.id)))
    assert rows == {(new[s["code"] + "-2a"], s["u2"]), (new[s["code"] + "-2b"], s["u2"]),
                    (new[s["code"] + "-2b"], s["u1"])}
    shown = {e["after"]["label"]: e.get("from") for e in c.get(f"{API}/fund/draft/diff").json()["units"]
             if e["kind"] == "added"}
    assert shown[s["code"] + "-2a"] == [s["code"] + "-2"]


def test_from_column_unknown_id_422(manager_role_client, db):
    c = manager_role_client
    s = _seed(c)
    data = _edit(_export(c), lambda wb: wb["Объекты"].append(
        [None, s["code"] + "-9", s["code"], None, None, "999999999"]))
    r = _upload(c, data)
    assert r.status_code == 422, r.text
    assert any(e["sheet"] == "Объекты" and "999999999" in e["message"] for e in r.json()["errors"])
    assert _draft(db) is None


def test_unknown_id_422_nothing_applied(manager_role_client, db):
    """Неизвестный ID на каждом из четырёх листов — ошибка с листом и строкой; не применяется
    ничего, даже черновик не остаётся."""
    c = manager_role_client
    _seed(c)
    flag_title = "апи-флаг-" + uniq()
    tops = {m: db.scalar(select(func.max(m.id))) for m in (Category, Unit, UnitFlag)}

    def spoil(wb):
        for name in ("Категории", "Дерево", "Флаги", "Объекты"):
            wb[name].cell(2, 1, 999999999)
        ws = wb["Объекты"]
        ws.cell(1, ws.max_column + 1, flag_title)
        ws.append([None, "NEW-" + uniq(), wb["Категории"].cell(3, 2).value, None, None, None])
    r = _upload(c, _edit(_export(c), spoil))
    assert r.status_code == 422, r.text
    errors = r.json()["errors"]
    assert {e["sheet"] for e in errors} == {"Категории", "Дерево", "Флаги", "Объекты"}
    assert all(e["row"] == 2 and "999999999" in e["message"] for e in errors)
    assert _draft(db) is None
    assert {m: db.scalar(select(func.max(m.id))) for m in tops} == tops
    assert db.scalar(select(UnitFlag.id).where(UnitFlag.title == flag_title)) is None


def test_bad_file_422_no_draft(manager_role_client, db):
    r = _upload(manager_role_client, b"not an xlsx")
    assert r.status_code == 422, r.text
    assert r.json()["errors"][0]["sheet"] == ""
    assert _draft(db) is None


def test_too_big_file_rejected(manager_role_client, db, monkeypatch):
    monkeypatch.setattr(fx, "MAX_FILE_BYTES", 100)
    r = _upload(manager_role_client, b"x" * 101)
    assert r.status_code == 413, r.text
    assert _draft(db) is None


def test_import_with_existing_draft_409(manager_role_client, db):
    c = manager_role_client
    _seed(c)
    data = _export(c)
    d = FundDraft(c)                                      # черновик уже открыт
    r = _upload(c, data)
    assert r.status_code == 409, r.text
    assert _draft(db).rev == d.rev                        # черновик не тронут


def test_code_change_with_same_id_is_rename(manager_role_client, db):
    c = manager_role_client
    s = _seed(c)
    new_code = s["code"] + "X"

    def rename(wb):
        ws = wb["Категории"]
        ws.cell(_row(ws, s["cat"]), 2, new_code)
        ws = wb["Объекты"]
        for uid in (s["u1"], s["u2"]):
            ws.cell(_row(ws, uid), 3, new_code)
    r = _upload(c, _edit(_export(c), rename))
    assert r.status_code == 200, r.text
    diff = r.json()["diff"]
    assert diff["units"] == [] and diff["groups"] == []
    assert [(e["id"], e["kind"], e["before"]["code"], e["after"]["code"]) for e in diff["categories"]] == [
        (s["cat"], "changed", s["code"], new_code)]
    assert r.json()["retired"] == []


def test_import_and_export_require_setup(manager_client, names_client):
    for cl in (manager_client, names_client):
        assert cl.get(f"{API}/fund/export", params={"date": _today()}).status_code == 403
        assert _upload(cl, b"x").status_code == 403
