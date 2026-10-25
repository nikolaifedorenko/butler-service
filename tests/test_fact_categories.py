"""Категории времени в Факте — из настроек периода (рецензия аудита 22.10.2026, P2).

Диаграмма «Месяц» и легенда рисовали ночь как 22:00–06:00 из констант интерфейса, а
границы задаются в настройках (CFG-CATEGORIES): после их правки расчёт был верным, а
картинка — нет. Теперь категории периода приходят в ответе /api/fact/month.
"""
from __future__ import annotations

import dataclasses

from app.core.time import local_date
from app.modules.timesheet.domain.settings.defaults import default_settings
from app.modules.timesheet.domain.settings.types import Category
from app.modules.timesheet.interface.fact_api import categories_out


def test_categories_follow_settings_order_and_bounds():
    st = dataclasses.replace(default_settings(), categories=(
        Category("ДЯ", 7 * 60, 23 * 60), Category("ДН", 23 * 60, 7 * 60)))
    assert categories_out(st) == [
        {"code": "ДЯ", "start": "07:00", "end": "23:00", "crosses_midnight": False},
        {"code": "ДН", "start": "23:00", "end": "07:00", "crosses_midnight": True}]


def test_fact_month_returns_period_categories(manager_client):
    today = local_date()
    r = manager_client.get("/api/fact/month", params={"year": today.year, "month": today.month})
    assert r.status_code == 200, r.text
    cats = r.json()["categories"]
    assert [c["code"] for c in cats] == ["ДЯ", "ДН"]          # демо — значения по умолчанию
    assert {c["code"]: (c["start"], c["end"]) for c in cats} == {
        "ДЯ": ("06:00", "22:00"), "ДН": ("22:00", "06:00")}
