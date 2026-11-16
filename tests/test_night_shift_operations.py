"""Ход ночной смены — операции прикладного слоя (ADR-0013, раздел 4): подтверждения, отказы,
одна транзакция на операцию."""
from __future__ import annotations

import datetime as dt
from contextlib import contextmanager

import pytest
from sqlalchemy import func, select

from app.core import errors
from app.core.audit import AuditLog
from app.modules.night.application import shift
from app.modules.night.application.catalog import NightAreaSection, NightInterception, NightReport

SHIFT_DAY = dt.date(2026, 4, 20)


@contextmanager
def _open_shift(db, freeze):
    """Открытый отчёт прошедшей смены при замороженных часах; после теста отчёт удаляется."""
    from app.modules.night.application.night import ensure_report

    with freeze(f"{SHIFT_DAY.isoformat()} 23:00:00"):
        rep = ensure_report(db, SHIFT_DAY)
        db.commit()
        try:
            yield rep
        finally:
            db.rollback()
            for row in db.scalars(select(NightInterception).where(NightInterception.report_id == rep.id)):
                db.delete(row)
            db.delete(db.get(NightReport, rep.id))
            db.commit()


def _principal(db, username: str):
    from app.core.auth import Principal
    from app.core.identity import User
    from app.modules.people.application import Employee

    user = db.scalar(select(User).where(User.username == username))
    return Principal(user, db.get(Employee, user.employee_id) if user.employee_id else None)


def _free_section(rep) -> NightAreaSection:
    return next(s for s in rep.areas if s.area_id is not None and s.status == "free" and s.items)


def test_interception_needs_confirmation_and_is_recorded(db, freeze):
    with _open_shift(db, freeze) as rep:
        first, second = _principal(db, "volkov"), _principal(db, "ivanov")
        sec = _free_section(rep)
        assert shift.take_section(db, first, sec.id)["already"] is False
        assert shift.take_section(db, first, sec.id)["already"] is True
        with pytest.raises(errors.ConfirmationRequired) as exc:
            shift.take_section(db, second, sec.id)
        assert exc.value.status_code == 409
        assert exc.value.detail["interception"] is True and "Продолжить?" in exc.value.detail["message"]
        taken = shift.take_section(db, second, sec.id, ack=True)
        assert taken["warning"].startswith("Вы перехватили") and taken["section"]["taken_by"] == second.user.id
        assert db.scalar(select(func.count()).select_from(NightInterception)
                         .where(NightInterception.section_id == sec.id)) == 1


def test_closing_with_unanswered_items_needs_confirmation(db, freeze):
    with _open_shift(db, freeze) as rep:
        who = _principal(db, "volkov")
        sec = _free_section(rep)
        with pytest.raises(errors.ConfirmationRequired) as exc:
            shift.close_section(db, who, sec.id)
        assert exc.value.detail == {"unanswered": len(sec.items), "message": exc.value.message}
        assert shift.close_section(db, who, sec.id, force_unanswered=True)["status"] == "done"
        with pytest.raises(errors.Conflict, match="переоткройте"):
            shift.answer_item(db, who, sec.items[0].id, "ok")


def test_answer_takes_free_section_and_rejects_unknown_answer(db, freeze):
    with _open_shift(db, freeze) as rep:
        who = _principal(db, "volkov")
        sec = _free_section(rep)
        with pytest.raises(errors.Rejected, match="Неизвестный ответ"):
            shift.answer_item(db, who, sec.items[0].id, "может быть")
        assert shift.answer_item(db, who, sec.items[0].id, "bad", "течёт") == {
            "id": sec.items[0].id, "answer": "bad", "comment": "течёт"}
        db.expire_all()
        assert (sec.status, sec.taken_by) == ("taken", who.user.id)


def test_failed_operation_leaves_nothing(app_stack, db, freeze, monkeypatch):
    """Аудит — последний шаг операции: не записался он — не записана и отметка, объект свободен."""
    with _open_shift(db, freeze) as rep:
        who = _principal(db, "volkov")
        sec = _free_section(rep)
        item_id = sec.items[0].id

        def broken_audit(*args, **kwargs):
            raise RuntimeError("журнал недоступен")

        monkeypatch.setattr(shift, "audit", broken_audit)
        with pytest.raises(RuntimeError):
            shift.answer_item(db, who, item_id, "bad", "не должно сохраниться")
        monkeypatch.undo()
        with app_stack["SessionLocal"]() as other:
            assert other.get(NightAreaSection, sec.id).status == "free"
            assert other.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.action == "night_item_answer", AuditLog.target == f"item:{item_id}")) == 0
        assert shift.report(db, rep.id)["progress"]["taken"] == 0


def test_closed_shift_is_read_only_until_reopened(db, freeze):
    with _open_shift(db, freeze) as rep:
        admin, who = _principal(db, "admin"), _principal(db, "volkov")
        sec = _free_section(rep)
        with pytest.raises(errors.ConfirmationRequired, match="Смена будет неполной"):
            shift.close_report(db, admin, rep.id)
        closed = shift.close_report(db, admin, rep.id, force=True)
        assert (closed["status"], closed["result"], closed["close_reason"]) == ("closed", "partial", "manual")
        with pytest.raises(errors.Conflict, match="Отчёт уже закрыт"):
            shift.close_report(db, admin, rep.id, force=True)
        for call in (lambda: shift.take_section(db, who, sec.id),
                     lambda: shift.answer_item(db, who, sec.items[0].id, "ok"),
                     lambda: shift.finish_cars(db, who, rep.id, ack=True)):
            with pytest.raises(errors.Conflict, match="закрыта — правки недоступны"):
                call()
        assert shift.reopen_report(db, admin, rep.id)["status"] == "open"
        with pytest.raises(errors.Conflict, match="переоткрывать нечего"):
            shift.reopen_report(db, admin, rep.id)
        assert shift.take_section(db, who, sec.id)["section"]["status"] == "taken"


@pytest.mark.parametrize("call, text", [
    (lambda db, p: shift.report(db, 10**9), "Отчёт не найден"),
    (lambda db, p: shift.take_section(db, p, 10**9), "Область не найдена"),
    (lambda db, p: shift.answer_item(db, p, 10**9, "ok"), "Пункт не найден"),
    (lambda db, p: shift.export_docx(db, 10**9), "Отчёт не найден"),
    (lambda db, p: shift.cars_state(db, 10**9), "Отчёт не найден"),
])
def test_missing_object_is_not_found(db, call, text):
    with pytest.raises(errors.NotFound, match=text):
        call(db, _principal(db, "admin"))


def test_confirmation_error_carries_data_for_interface():
    exc = errors.ConfirmationRequired("Продолжить?", interception=True, count=2)
    assert isinstance(exc, errors.Conflict) and exc.status_code == 409
    assert exc.detail == {"interception": True, "count": 2, "message": "Продолжить?"}
