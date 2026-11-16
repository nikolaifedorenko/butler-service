"""Прикладной слой фонда (шаг 4е-1): статусы отказов задают классы, запись — одна транзакция,
предпросмотр ничего не сохраняет."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.audit import AuditLog
from app.core.errors import Conflict, Forbidden, NotFound, Validation
from app.modules.stays.adapters.orm import FundVersion, UnitFlag
from app.modules.stays.application import fund_drafts as fd
from app.modules.stays.application.blocks import BlockNotFound
from app.modules.stays.application.coverage import CoverageForbidden
from app.modules.stays.application.fund import FundConflict, FundError
from app.modules.stays.application.fund_xlsx import FileError
from app.modules.stays.application.mine import MineForbidden
from app.modules.stays.application.ooo import OooConflict, OooNotFound
from app.modules.stays.application.previewed import discarded
from app.modules.stays.application.reservations import ReservationConflict, ReservationInvalid

from .helpers import API, uniq
from .test_fund_versions_api import _clean  # noqa: F401 — autouse: снять версии и сущности теста


@pytest.mark.parametrize(("error", "status"), [
    (FundError, 422), (FundConflict, 409), (ReservationInvalid, 422), (ReservationConflict, 409),
    (CoverageForbidden, 403), (MineForbidden, 403), (OooNotFound, 404), (BlockNotFound, 404),
    (OooConflict, 409),
])
def test_status_is_a_property_of_the_error_class(error, status):
    assert error("текст").status_code == status


def test_fund_errors_are_service_errors():
    assert issubclass(FundError, Validation)
    assert issubclass(CoverageForbidden, FundError)
    assert not issubclass(FundConflict, Forbidden | NotFound)
    assert not issubclass(FundConflict, Conflict)       # статус 409 задан классом, а не родителем


def test_file_error_body_is_list_of_errors():
    body = fd.FundFileError([FileError("Объекты", 3, "нет вида"), FileError("", 0, "пустой файл")]).body
    assert body == {"errors": [{"sheet": "Объекты", "row": 3, "message": "нет вида"},
                               {"sheet": "", "row": 0, "message": "пустой файл"}]}


def test_discarded_rolls_back_everything_it_wrote(db):
    title = "апи-флаг-" + uniq()
    result = discarded(db, lambda: {"id": fd.save_flag(db, {"title": title, "color": "#112233",
                                                            "sort_order": 1}, None)})
    assert result["id"]
    assert db.scalar(select(UnitFlag).where(UnitFlag.title == title)) is None


def test_flag_write_and_audit_are_one_transaction(admin_client, db, monkeypatch):
    """Сбой журнала откатывает и запись флага: «записалось всё или ничего»."""
    from app.modules.stays.application import fund_dictionaries

    def broken(*_a, **_k):
        raise RuntimeError("журнал недоступен")
    monkeypatch.setattr(fund_dictionaries, "audit", broken)
    title = "апи-флаг-" + uniq()
    with pytest.raises(RuntimeError):
        admin_client.post(f"{API}/fund/flags", json={"title": title, "color": "#112233"})
    db.rollback()
    assert db.scalar(select(UnitFlag).where(UnitFlag.title == title)) is None


def test_import_with_bad_file_leaves_no_draft_and_no_audit(admin_client, db):
    before = db.scalar(select(AuditLog.id).order_by(AuditLog.id.desc()).limit(1)) or 0
    r = admin_client.post(f"{API}/fund/import", data={"valid_from": "2091-01-01"},
                          files={"file": ("a.xlsx", b"not a workbook", "application/octet-stream")})
    assert r.status_code == 422
    assert set(r.json()) == {"errors"}
    assert r.json()["errors"][0].keys() == {"sheet", "row", "message"}
    db.rollback()
    assert fd.current_draft(db) is None
    assert db.scalar(select(AuditLog.id).where(AuditLog.id > before, AuditLog.action == "stays_fund_import")) is None


def test_preview_delete_keeps_draft_and_real_delete_removes_it(admin_client, db):
    opened = admin_client.post(f"{API}/fund/draft", json={"valid_from": "2092-01-01"}).json()
    r = admin_client.delete(f"{API}/fund/versions/{opened['id']}", params={"preview": 1})
    assert r.status_code == 200 and r.json()["preview"] is True and r.json()["overbook_refused"] is None
    db.rollback()
    assert db.get(FundVersion, opened["id"]) is not None
    r = admin_client.delete(f"{API}/fund/versions/{opened['id']}")
    assert r.status_code == 200 and r.json()["preview"] is False
    db.rollback()
    assert db.get(FundVersion, opened["id"]) is None


def test_draft_write_returns_new_rev_and_stale_rev_is_409(admin_client):
    d = admin_client.post(f"{API}/fund/draft", json={"valid_from": "2093-01-01"}).json()
    moved = admin_client.patch(f"{API}/fund/draft", json={"rev": d["rev"], "valid_from": "2093-02-01"}).json()
    assert moved["rev"] == d["rev"] + 1
    stale = admin_client.patch(f"{API}/fund/draft", json={"rev": d["rev"], "valid_from": "2093-03-01"})
    assert stale.status_code == 409
    admin_client.delete(f"{API}/fund/versions/{d['id']}")
