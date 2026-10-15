"""Цвета кодов Табеля (day_code_policy): формат #rgb/#rrggbb на записи версии настроек.

Дополнение батча «Быстрые правки безопасности» (PR #25), покрывшего цвета сотрудников
и типов смен: цвета кодов правятся в экспертном редакторе настроек и попадают во
фронтенде в атрибут style="…" (пилюли кодов, таймлайн, ячейки Табеля/УТ) —
произвольная строка там была бы HTML/CSS-инъекцией. Бэкенд отвергает не-hex при
записи (422) и канонизует регистр; фронтенд страхует cssColor() на выходе
v4CodeColor()/settingsCodeColor() даже для уже лежащих в БД некорректных значений.
"""
from __future__ import annotations

import datetime as dt
import json

import pytest


def _current_payload(admin_client) -> dict:
    return admin_client.get("/api/engine-settings").json()["active"]["payload"]


def _put(admin_client, payload):
    # valid_from — в будущее: новая версия не подменяет активную для текущего
    # периода; ряды версий за тестом всё равно убираются (_delete_version),
    # т.к. тестовая БД общая, и test_timesheet_norm вставляет свою «последнюю»
    return admin_client.put("/api/engine-settings",
                            json={"valid_from": (dt.date.today() + dt.timedelta(days=45)).isoformat(),
                                  "payload": payload, "note": "тест цветов кодов"})


def _with_color(payload, color):
    codes = payload.setdefault("day_code_policy", {})
    code = next(iter(codes)) if codes else "Я"
    codes[code] = {**(codes.get(code) or {}), "color": color}
    return payload, code


def _delete_version(app_stack, version_id: int) -> None:
    from app.db import SessionLocal
    from app.models import EngineSettingsVersion

    db = SessionLocal()
    try:
        row = db.get(EngineSettingsVersion, version_id)
        if row is not None:
            db.delete(row)
            db.commit()
    finally:
        db.close()


@pytest.mark.parametrize("bad", ['red"><a href=//evil>x</a>', "url(//evil/x.png)",
                                 "#12345", "#gggggg", "javascript:alert(1)"])
def test_code_color_bad_rejected(admin_client, bad):
    payload, _code = _with_color(_current_payload(admin_client), bad)
    r = _put(admin_client, payload)
    assert r.status_code == 422, r.text
    assert "Цвет кода Табеля" in r.json()["detail"]


def test_code_color_valid_normalized_to_lowercase(admin_client, app_stack):
    from app.db import SessionLocal
    from app.models import EngineSettingsVersion

    payload, code = _with_color(_current_payload(admin_client), "#AABB00")
    r = _put(admin_client, payload)
    assert r.status_code == 200, r.text
    vid = r.json()["id"]
    db = SessionLocal()
    try:
        row = db.get(EngineSettingsVersion, vid)
        saved = json.loads(row.payload_json)
        assert saved["day_code_policy"][code]["color"] == "#aabb00", \
            "цвет сохраняется канонизованным (нижний регистр)"
    finally:
        db.close()
        _delete_version(app_stack, vid)


def test_code_color_empty_not_touched(admin_client, app_stack):
    payload, _code = _with_color(_current_payload(admin_client), "")
    r = _put(admin_client, payload)
    assert r.status_code == 200, r.text
    _delete_version(app_stack, r.json()["id"])
