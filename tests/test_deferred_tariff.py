"""Перенос по тарифу, которого нет в весах текущих настроек (CHK-DEFERRED-IN).

Тариф блока заморожен прошлым периодом, веса — из настроек текущего. После
переименования категории (ДН → НОЧЬ с согласованными весами, каскадом и размещением)
закрытие следующего периода падало в каскаде KeyError'ом → 500 (рецензия аудита
22.10.2026, §2.2).

Что проверяется:
  * ядро отклоняет такой вход на стадии 1 (InvalidInputDataError, а не KeyError);
  * текст ошибки называет тариф и что делать;
  * версию настроек, убирающую тариф незакрытого переноса, опубликовать нельзя.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

import pytest
from sqlalchemy import delete, select

from app.modules.employees.application import Employee
from app.modules.timesheet.adapters.orm import DeferredCarry
from app.modules.timesheet.application.close_period import close_period
from app.modules.timesheet.domain.types.entities import DeferredBlock
from app.modules.timesheet.domain.types.errors import InvalidInputDataError
from app.modules.timesheet.interface.formatting import error_text
from tests.engine.helpers import EMP, IN, OUT, at, d, day
from tests.engine.test_application import NOV, OCT, _rows_full_month, _stand

NOTE = "deferred tariff guard"


def test_close_with_unknown_deferred_tariff_is_input_error():
    rows = [day(1, "ОТ")] + _rows_full_month("ДО", first=2) + _rows_full_month(month=11)
    db, ports = _stand(rows=rows, marks=[IN(1, 8), OUT(1, 20)])
    assert close_period(EMP, OCT, at(1, 0, month=11), ports).settle.deferred_blocks == (
        DeferredBlock(d(1), "ДЯ", 720),)
    weights = {t: w for t, w in db.settings.weights.items() if t != "ДЯ"}
    db.settings = dataclasses.replace(db.settings, weights=weights)

    with pytest.raises(InvalidInputDataError) as err:
        close_period(EMP, NOV, at(1, 0, month=12), ports)
    assert err.value.code == "CHK-DEFERRED-IN"
    assert err.value.data["unknown_tariffs"] == ("ДЯ",)
    text = error_text(err.value)
    assert "«ДЯ»" in text and "весах" in text


def test_publish_cannot_drop_tariff_of_open_carry(admin_client, db):
    from app.modules.timesheet.application.catalog import EngineSettingsVersion

    emp = next(e for e in db.scalars(select(Employee)) if "Иванов" in e.display_name)
    got = admin_client.get("/api/engine-settings").json()
    payload = got["active"]["payload"]
    first = (dt.date.today().replace(day=1) + dt.timedelta(days=400)).replace(day=1)
    db.add(DeferredCarry(employee_id=emp.id, period_start=first, source_day=first - dt.timedelta(days=3),
                         tariff="СТАРЫЙ", minutes=60))
    db.commit()
    body = {"payload": payload, "note": NOTE, "valid_from": first.isoformat()}
    try:
        r = admin_client.put("/api/engine-settings", json=body)
        assert r.status_code == 422 and "«СТАРЫЙ»" in r.json()["detail"], r.text
        # перенос в период до новой версии считается по прежним весам — не мешает
        later = (first + dt.timedelta(days=40)).replace(day=1)
        r = admin_client.put("/api/engine-settings", json=body | {"valid_from": later.isoformat()})
        assert r.status_code == 200, r.text
    finally:
        db.rollback()
        db.execute(delete(DeferredCarry).where(DeferredCarry.tariff == "СТАРЫЙ"))
        db.execute(delete(EngineSettingsVersion).where(EngineSettingsVersion.note == NOTE))
        db.commit()
