"""Outbox рассылки (аудит 22.10.2026, CONC-02).

Строка журнала пишется до сети: queued → sending → sent | failed. Здесь закреплено:
  * упал процесс после постановки в очередь — фоновый отправщик доставит один раз;
  * упал посреди доставки (строка в sending) — повторно не шлём, помечаем
    «статус неизвестен» для ручного повтора;
  * строку берёт в отправку только один отправитель (двойной повтор → 409).
Сеть подменяется: deliver перехвачен.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import delete

DOMAIN = "outbox-test"


@pytest.fixture()
def calls(monkeypatch):
    sent: list[str] = []

    def fake_deliver(**kwargs):
        sent.append(kwargs["target"])
        return f"ext-{len(sent)}"

    monkeypatch.setattr("app.modules.notify.application.dispatch.deliver", fake_deliver)
    return sent


@pytest.fixture()
def rows(db):
    from app.modules.notify.adapters.orm import NotifyDispatch

    def make(status: str, **kw) -> int:
        row = NotifyDispatch(domain=DOMAIN, ref_id=1, channel="telegram", target=kw.pop("target", "-1001"),
                             message="Текст", status=status, attempts=kw.pop("attempts", 0), **kw)
        db.add(row)
        db.commit()
        return row.id

    yield make
    db.rollback()
    db.execute(delete(NotifyDispatch).where(NotifyDispatch.domain == DOMAIN))
    db.commit()


def _row(db, row_id):
    from app.modules.notify.adapters.orm import NotifyDispatch

    db.expire_all()
    return db.get(NotifyDispatch, row_id)


def test_queued_after_crash_is_delivered_once_by_background(db, rows, calls):
    from app.modules.notify.application.dispatch import run_outbox

    rid = rows("queued", target="-1002")        # запрос поставил в очередь и упал до сети
    run_outbox(db, ids=None, cfg=object())      # фоновая доотправка
    run_outbox(db, ids=None, cfg=object())      # следующий раунд — уже нечего слать
    assert calls == ["-1002"]
    row = _row(db, rid)
    assert row.status == "sent" and row.attempts == 1 and row.external_id == "ext-1"


def test_stuck_sending_is_not_resent_but_marked_unknown(db, rows, calls):
    from app.core.time import now_local
    from app.modules.notify.application.dispatch import UNKNOWN_DELIVERY, fail_stale_sending, run_outbox

    old = rows("sending", sending_at=now_local() - dt.timedelta(hours=1))   # упал посреди доставки
    fresh = rows("sending", sending_at=now_local())                         # доставка идёт сейчас
    assert fail_stale_sending(db) >= 1
    run_outbox(db, ids=None, cfg=object())
    assert calls == []                                    # дубля службе нет
    row = _row(db, old)
    assert row.status == "failed" and row.error == UNKNOWN_DELIVERY and row.attempts == 1
    assert _row(db, fresh).status == "sending"            # идущую доставку не трогаем


def test_row_is_claimed_by_one_sender_only(db, rows):
    from app.modules.notify.application.dispatch import claim

    rid = rows("queued")
    assert claim(db, rid, "queued") is True
    assert claim(db, rid, "queued") is False              # фон, другой воркер, двойной клик
    assert _row(db, rid).status == "sending" and _row(db, rid).sending_at is not None


def test_resend_twice_second_is_409(admin_client, db, rows, calls):
    rid = rows("failed", attempts=1, error="chat not found")
    first = admin_client.post(f"/api/notify/dispatches/{rid}/resend")
    assert first.status_code == 200 and first.json()["dispatch"]["status"] == "sent", first.text
    assert admin_client.post(f"/api/notify/dispatches/{rid}/resend").status_code == 409
    assert len(calls) == 1
    queued = rows("queued")
    assert admin_client.post(f"/api/notify/dispatches/{queued}/resend").status_code == 409
