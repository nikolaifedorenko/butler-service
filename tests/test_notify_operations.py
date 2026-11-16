"""Настройки доставки — операции прикладного слоя (ADR-0013, раздел 4): типизированные
отказы, отказ внешнего сервиса, запись аудита."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core import errors
from app.core.audit import AuditLog
from app.modules.notify.application import settings
from app.modules.notify.application.catalog import NotifyDispatch
from app.modules.notify.ports.transports import TransportError


@pytest.fixture()
def admin(db):
    from app.core.auth import Principal
    from app.core.identity import User

    return Principal(db.scalar(select(User).where(User.username == "admin")), None)


def _audits(db, action: str) -> int:
    db.rollback()
    return db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == action))


def test_transport_failure_is_upstream_error_without_audit(db, admin, monkeypatch):
    """Бот отказал: 502 с его текстом, в журнал аудита проверка не попадает."""
    def refuse(url, payload, files, timeout):
        raise TransportError("Telegram отклонил токен (401)")

    monkeypatch.setattr("app.modules.notify.adapters.transports.telegram.http_sender", refuse)
    before = _audits(db, "notify_telegram_check")
    with pytest.raises(errors.UpstreamError, match="отклонил токен") as exc:
        settings.check_bot(db, admin, "1234567890:AAEtestTESTtestTESTtestTESTtestTEST")
    assert exc.value.status_code == 502
    assert _audits(db, "notify_telegram_check") == before


def test_successful_check_is_audited(db, admin, monkeypatch):
    monkeypatch.setattr("app.modules.notify.adapters.transports.telegram.http_sender",
                        lambda url, payload, files, timeout: {"ok": True, "result": {"id": 5, "username": "probe_bot"}})
    before = _audits(db, "notify_telegram_check")
    assert settings.check_bot(db, admin, "1234567890:AAEtestTESTtestTESTtestTESTtestTEST") == {
        "username": "probe_bot", "first_name": "", "id": 5}
    assert _audits(db, "notify_telegram_check") == before + 1


@pytest.mark.parametrize("call, error, text", [
    (lambda db, p: settings.save(db, p, {"notify_smtp_security": "что-то"}), errors.Rejected, "none, starttls или ssl"),
    (lambda db, p: settings.send_test_email(db, p, "без собаки"), errors.Rejected, "корректный адрес"),
    (lambda db, p: settings.save_template_text(db, p, "нет", "x"), errors.NotFound, "Неизвестный раздел"),
    (lambda db, p: settings.save_template_text(db, p, "night", "{datte}"), errors.Rejected, "Неизвестные плейсхолдеры"),
    (lambda db, p: settings.preview_template("нет", ""), errors.NotFound, "Неизвестный раздел"),
    (lambda db, p: settings.resend(db, p, 10**9), errors.NotFound, "Запись журнала не найдена"),
])
def test_refusal_is_typed_error(db, admin, call, error, text):
    with pytest.raises(error, match=text):
        call(db, admin)


def test_resend_takes_failed_row_only_once(db, admin, monkeypatch):
    """Повтор берёт строку журнала в отправку до сети: отправленную повторно не отправит."""
    sent = []
    monkeypatch.setattr("app.modules.notify.application.dispatch.deliver",
                        lambda **kw: sent.append(kw["target"]) or "777")
    row = NotifyDispatch(domain="night", ref_id=1, channel="telegram", target="-100500", message="проба",
                         status="failed", attempts=1)
    db.add(row)
    db.commit()
    try:
        before = _audits(db, "notify_dispatch_resend")
        done = settings.resend(db, admin, row.id)
        assert (done["status"], done["attempts"], done["can_retry"]) == ("sent", 2, False)
        assert sent == ["-100500"] and _audits(db, "notify_dispatch_resend") == before + 1
        with pytest.raises(errors.Conflict, match="уже отправлена"):
            settings.resend(db, admin, row.id)
        assert sent == ["-100500"]
    finally:
        db.rollback()
        db.delete(db.get(NotifyDispatch, row.id))
        db.commit()


def test_preview_renders_sample_data():
    assert settings.preview_template("night", "Служба {service}, {time}") == "Служба Техническая служба, 02:48"
    assert settings.unknown_placeholders("night", "{date} {datte} {items}") == ["datte"]
