"""Справочники ночного обхода — операции прикладного слоя (ADR-0013, раздел 4): правка и
запись аудита — одна транзакция; отказ посреди операции не оставляет следов."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core import errors
from app.core.audit import AuditLog
from app.modules.night.application import dictionaries as dicts
from app.modules.night.application.catalog import NightArea, NightZone

NAME = "Проверка транзакции справочника"


@pytest.fixture()
def admin(db):
    from app.core.auth import Principal
    from app.core.identity import User

    return Principal(db.scalar(select(User).where(User.username == "admin")), None)


@pytest.fixture()
def cleanup(db):
    yield
    db.rollback()
    for model in (NightArea, NightZone):
        for row in db.scalars(select(model).where(model.name.like(f"{NAME}%"))):
            db.delete(row)
    db.commit()


def _count(app_stack, model, *where) -> int:
    with app_stack["SessionLocal"]() as other:        # другая сессия видит только зафиксированное
        return other.scalar(select(func.count()).select_from(model).where(*where))


def test_operation_commits_change_together_with_audit(app_stack, db, admin, cleanup):
    audits = _count(app_stack, AuditLog, AuditLog.action == "night_zone_create")
    zone = dicts.create_zone(db, admin, dicts.ZoneIn(name=NAME))
    assert _count(app_stack, NightZone, NightZone.id == zone["id"]) == 1
    assert _count(app_stack, AuditLog, AuditLog.action == "night_zone_create") == audits + 1


def test_failure_after_writes_leaves_nothing(app_stack, db, admin, cleanup, monkeypatch):
    """Аудит — последний шаг операции: если он не записался, не записано и изменение."""
    def broken_audit(*args, **kwargs):
        raise RuntimeError("журнал недоступен")

    monkeypatch.setattr(dicts, "audit", broken_audit)
    with pytest.raises(RuntimeError):
        dicts.create_areas_bulk(db, admin, dicts.AreaBulkIn(prefix=f"{NAME} ", start=1, count=3))
    assert _count(app_stack, NightArea, NightArea.name.like(f"{NAME}%")) == 0
    assert db.scalar(select(func.count()).select_from(NightArea).where(NightArea.name.like(f"{NAME}%"))) == 0


@pytest.mark.parametrize("call, error, text", [
    (lambda db, p: dicts.create_zone(db, p, dicts.ZoneIn(name="  ")), errors.Rejected, "Введите название зоны"),
    (lambda db, p: dicts.update_zone(db, p, 10**9, dicts.ZoneIn(name="x")), errors.NotFound, "Зона не найдена"),
    (lambda db, p: dicts.create_area(db, p, dicts.AreaIn(name="x", zone_id=10**9)), errors.Rejected,
     "Зона обхода не найдена"),
    (lambda db, p: dicts.create_service(db, p, dicts.ServiceIn(name=NAME)), errors.Rejected, "хотя бы один канал"),
    (lambda db, p: dicts.area_checklist(db, 10**9), errors.NotFound, "Область не найдена"),
])
def test_refusal_is_typed_error(db, admin, call, error, text):
    with pytest.raises(error, match=text):
        call(db, admin)


def test_duplicate_zone_is_conflict(db, admin, cleanup):
    dicts.create_zone(db, admin, dicts.ZoneIn(name=NAME))
    with pytest.raises(errors.Conflict) as exc:
        dicts.create_zone(db, admin, dicts.ZoneIn(name=NAME))
    assert exc.value.status_code == 409
