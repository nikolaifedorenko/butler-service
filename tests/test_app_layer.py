"""Каркас прикладного слоя (ADR-0013, раздел 4): транзакция операции, ошибки, модели ответа."""
from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core import errors
from app.core.audit import AuditLog
from app.core.db import transaction, transactional
from app.core.schemas import ApiModel, Ok
from app.core.time import now

ACTION = "app_layer_probe"


def _add(db, target: str) -> None:
    db.add(AuditLog(actor_name="t", action=ACTION, target=target, ts=now()))
    db.flush()


def _targets(app_stack) -> list[str]:
    with app_stack["SessionLocal"]() as other:        # другая сессия видит только зафиксированное
        return sorted(other.scalars(select(AuditLog.target).where(AuditLog.action == ACTION)))


@pytest.fixture()
def probe(app_stack, db):
    yield
    db.rollback()
    for row in db.scalars(select(AuditLog).where(AuditLog.action == ACTION)):
        db.delete(row)
    db.commit()


def test_transaction_commits_on_success(app_stack, db, probe):
    with transaction(db):
        _add(db, "a")
        assert _targets(app_stack) == []              # до выхода из блока ничего не зафиксировано
    assert _targets(app_stack) == ["a"]


def test_transaction_rolls_back_everything_on_error(app_stack, db, probe):
    with pytest.raises(errors.Rejected), transaction(db):
        _add(db, "a")
        raise errors.Rejected("нельзя")
    assert _targets(app_stack) == []
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == ACTION)) == 0


def test_nested_transaction_is_a_savepoint(app_stack, db, probe):
    """Операция внутри операции: её отказ отменяет только её записи, фиксирует всё внешняя."""
    with transaction(db):
        _add(db, "outer")
        with pytest.raises(errors.Conflict), transaction(db):
            _add(db, "inner-failed")
            raise errors.Conflict("занято")
        with transaction(db):
            _add(db, "inner-ok")
        assert _targets(app_stack) == []              # вложенный блок сам ничего не фиксирует
    assert _targets(app_stack) == ["inner-ok", "outer"]
    assert db.info["transaction_depth"] == 0


def test_transactional_wraps_operation(app_stack, db, probe):
    @transactional
    def operation(session, target: str, *, fail: bool = False) -> str:
        """Описание операции."""
        _add(session, target)
        if fail:
            raise errors.NotFound("нет")
        return target

    assert operation(db, "kept") == "kept"
    with pytest.raises(errors.NotFound):
        operation(db, "dropped", fail=True)
    assert _targets(app_stack) == ["kept"]
    assert operation.__name__ == "operation" and operation.__doc__ == "Описание операции."


@pytest.mark.parametrize("cls, status", [
    (errors.ServiceError, 400), (errors.Rejected, 400), (errors.Forbidden, 403), (errors.NotFound, 404),
    (errors.Conflict, 409), (errors.Gone, 410), (errors.PayloadTooLarge, 413), (errors.Validation, 422),
    (errors.UpstreamError, 502), (errors.Unauthorized, 401), (errors.TooManyRequests, 429),
    (errors.NotSupported, 501)])
def test_service_error_becomes_http_response(cls, status):
    from app.main import _service_error_handler

    response = asyncio.run(_service_error_handler(None, cls("Текст для пользователя")))
    assert response.status_code == status
    assert json.loads(response.body) == {"detail": "Текст для пользователя"}


def test_module_error_sets_its_own_status_and_detail():
    from app.main import _service_error_handler
    from app.modules.cars.application.cars import CarConflict, CarInterceptAssigned, CarOpError

    assert issubclass(CarConflict, CarOpError) and issubclass(CarOpError, errors.ServiceError)
    assert (CarOpError("x").status_code, CarConflict("x").status_code) == (400, 409)
    response = asyncio.run(_service_error_handler(None, CarInterceptAssigned("Иванов И.")))
    assert response.status_code == 409
    assert json.loads(response.body) == {
        "detail": {"interception": True, "message": "Закреплён за Иванов И.. Всё равно взять?"}}


def test_response_model_rejects_unknown_field():
    """Поле, которого нет в модели ответа, — ошибка: данные не отбрасываются молча."""
    class Sample(ApiModel):
        id: int

    assert Sample.model_validate({"id": 1}).id == 1
    with pytest.raises(ValidationError):
        Sample.model_validate({"id": 1, "extra": 2})
    assert Ok().model_dump() == {"ok": True}
