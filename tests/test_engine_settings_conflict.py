"""Две вкладки редактора настроек расчёта (аудит 21.10.2026, CONC-03).

Каждая публикация — новая версия с полным payload черновика: вторая вкладка, открытая
от той же версии, молча затирала правки первой. Теперь редактор присылает
`base_version_id` (latest_id из GET), и сервер отвечает 409, если с тех пор вышла версия.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import delete

NOTE = "CONC-03 guard"


def test_second_publish_from_same_version_is_409(admin_client, db):
    from app.modules.timesheet.application.catalog import EngineSettingsVersion

    got = admin_client.get("/api/engine-settings").json()
    body = {"valid_from": (dt.date.today() + dt.timedelta(days=400)).isoformat(),
            "payload": got["active"]["payload"], "note": NOTE, "base_version_id": got["latest_id"]}
    try:
        first = admin_client.put("/api/engine-settings", json=body)
        assert first.status_code == 200, first.text
        second = admin_client.put("/api/engine-settings", json=body)     # вторая вкладка
        assert second.status_code == 409, second.text
        assert f"#{first.json()['id']}" in second.json()["detail"]
        again = admin_client.get("/api/engine-settings").json()
        assert again["latest_id"] == first.json()["id"]
        ok = admin_client.put("/api/engine-settings", json=body | {"base_version_id": again["latest_id"]})
        assert ok.status_code == 200, ok.text                            # после обновления — можно
    finally:
        db.execute(delete(EngineSettingsVersion).where(EngineSettingsVersion.note == NOTE))
        db.commit()


def test_tz_other_than_app_tz_is_422(admin_client, db):
    """HARD-01 (В-10): пояс расчёта — только APP_TZ. Чужой пояс отклоняется, пустой
    заполняется поясом объекта."""
    from app.core.config import settings
    from app.modules.timesheet.application.catalog import EngineSettingsVersion

    payload = admin_client.get("/api/engine-settings").json()["active"]["payload"]
    body = {"valid_from": (dt.date.today() + dt.timedelta(days=400)).isoformat(), "note": NOTE}
    try:
        r = admin_client.put("/api/engine-settings",
                             json=body | {"payload": payload | {"tz": "Asia/Yekaterinburg"}})
        assert r.status_code == 422 and settings.app_tz in r.json()["detail"], r.text
        r = admin_client.put("/api/engine-settings", json=body | {"payload": payload | {"tz": ""}})
        assert r.status_code == 200, r.text
        saved = db.get(EngineSettingsVersion, r.json()["id"])
        assert f'"tz": "{settings.app_tz}"' in saved.payload_json
    finally:
        db.execute(delete(EngineSettingsVersion).where(EngineSettingsVersion.note == NOTE))
        db.commit()
