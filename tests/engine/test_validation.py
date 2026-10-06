"""Валидация конфигурации В1–В11, В-Гр — по тесту на правило; все нарушения сообщаются разом."""
from __future__ import annotations

from dataclasses import replace

import pytest

from app.engine.domain.settings.defaults import default_settings
from app.engine.domain.settings.types import Category, DayCodePolicy, PlacementPolicy, Window
from app.engine.domain.settings.validate import validate_settings
from app.engine.domain.types.errors import ConfigError

ST = default_settings()


def codes(st):
    try:
        validate_settings(st)
    except ConfigError as e:
        return {c for c, _ in e.value.violations} if hasattr(e, "value") else {c for c, _ in e.violations}
    return set()


def test_defaults_are_valid():
    assert validate_settings(ST) is ST


def test_v1_code_with_hours_without_window():
    st = replace(ST, day_codes={**ST.day_codes, "Х": DayCodePolicy("Х", True, True, True, False, False)})
    assert "V1" in codes(st)


def test_v2_window_length():
    assert "V2" in codes(replace(ST, windows={**ST.windows, "Я 12": Window("Я", 720, ((480, 840),))}))


def test_v3_empty_or_outside_day():
    assert "V3" in codes(replace(ST, windows={**ST.windows, "Я 1": Window("Я", 0, ())}))
    assert "V3" in codes(replace(ST, windows={**ST.windows, "Я 2": Window("Я", 120, ((1380, 1500),))}))


def test_v4_categories_cover_day():
    cats = (ST.categories[0], Category("ДН", ((0, 300), (1320, 1440)), ST.categories[1].tariffs))
    assert "V4" in codes(replace(ST, categories=cats))


def test_v5_tariff_for_each_weight():
    cats = (Category("ДЯ", ST.categories[0].segments, {1: "ДЯ"}), ST.categories[1])
    assert "V5" in codes(replace(ST, categories=cats))


def test_v6_cascade_complete():
    assert "V6" in codes(replace(ST, cascade_order=("ДЯ", "ДЯ", "ДН 2")))


def test_v7_weights_positive():
    assert "V7" in codes(replace(ST, weights={**ST.weights, "ДЯ": 0}))


def test_v8_step_divides_60():
    assert "V8" in codes(replace(ST, step_minutes=25))


def test_v9_no_window_for_code_without_hours():
    assert "V9" in codes(replace(ST, windows={**ST.windows, "В 8": Window("В", 480, ((540, 1020),))}))


def test_v10_boundaries_on_grid():
    assert "V10" in codes(replace(ST, windows={**ST.windows, "Я 9": Window("Я", 540, ((570, 1110),))}))


def test_v11_placement_complete():
    assert "V11" in codes(replace(ST, placement=PlacementPolicy(("ДЯ",))))


def test_v_gr_groups():
    st = replace(ST, employee_groups={"a": "", "b": "Нет такой"})
    assert {"V_GR1", "V_GR2"} <= codes(st)


def test_all_violations_reported_at_once():
    st = replace(ST, step_minutes=25, placement=PlacementPolicy(("ДЯ",)))
    with pytest.raises(ConfigError) as e:
        validate_settings(st)
    assert {"V8", "V11"} <= {c for c, _ in e.value.violations}
