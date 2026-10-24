"""Отрицательный limit в списках (рецензия аудита 22.10.2026, P2).

`min(limit, 500)` без нижней границы: limit=-1 на SQLite — «без ограничения» (вся история
кара, весь архив ночных отчётов одним ответом), на PostgreSQL — ошибка запроса. Остальные
списки (уведомления, аудит) уже клампят снизу `max(1, …)`.
"""
from __future__ import annotations

from sqlalchemy import func, select


def test_car_history_negative_limit_is_clamped(manager_client, db):
    import datetime as dt

    from sqlalchemy import delete

    from app.modules.cars.application.catalog import Car, CarHistory

    car_id = db.scalar(select(Car.id).order_by(Car.id).limit(1))
    db.add_all([CarHistory(car_id=car_id, ts=dt.datetime(2029, 1, 1, 9, m), action="status",
                           actor_name="тест limit", details_json="{}") for m in (1, 2)])
    db.commit()
    try:
        assert db.scalar(select(func.count()).where(CarHistory.car_id == car_id)) > 1
        r = manager_client.get(f"/api/cars/{car_id}/history", params={"limit": -1})
        assert r.status_code == 200, r.text
        body = r.json()
        rows = body if isinstance(body, list) else body.get("history", body.get("items", []))
        assert len(rows) == 1, len(rows)
    finally:
        db.execute(delete(CarHistory).where(CarHistory.actor_name == "тест limit"))
        db.commit()


def test_night_reports_negative_limit_is_clamped(manager_client, open_shift):
    with open_shift():
        r = manager_client.get("/api/night/reports", params={"limit": -1})
        assert r.status_code == 200, r.text
        body = r.json()
        rows = body if isinstance(body, list) else body.get("reports", [])
        assert len(rows) <= 1, len(rows)
