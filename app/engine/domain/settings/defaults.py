"""Стартовое наполнение справочников Т1–Т7, Т9, Т-Группы.

Единственное место домена (кроме тестов), где допустимы литералы бизнес-кодов (12.4).
"""
from __future__ import annotations

from .types import Category, DayCodePolicy, Group, PlacementPolicy, Settings, Window

H = 60


def _p(code, hours, accepts, counts, auto, review, title):
    return DayCodePolicy(code, hours, accepts, counts, auto, review, title)


DAY_CODES = {p.code: p for p in (
    _p("Я", True, True, True, False, False, "Явка (дневная работа)"),
    _p("Н", True, True, True, False, False, "Ночная работа"),
    _p("К", True, True, True, True, False, "Командировка"),
    _p("В", False, True, True, False, False, "Выходной"),
    _p("ДО", False, False, True, False, True, "Отпуск без сохранения"),
    _p("ОТ", False, False, True, False, True, "Ежегодный отпуск"),
    _p("ОВ", False, False, True, False, True, "Оплачиваемый выходной"),
    _p("Б", False, False, False, False, True, "Больничный"),
    _p("НБ", False, False, False, False, True, "Неоплачиваемый больничный"),
    _p("НН", False, False, False, False, True, "Неявка по невыясненным причинам"),
)}


def _w(code, hours, *segments):
    return Window(code, hours * H, tuple((a * H, b * H) for a, b in segments))


WINDOWS = {f"{w.code} {w.plan_minutes // H}": w for w in (
    _w("Я", 12, (8, 20)), _w("Я", 9, (9, 18)), _w("Я", 8, (9, 17)),
    _w("К", 12, (8, 20)), _w("К", 9, (9, 18)), _w("К", 8, (9, 17)),
    _w("Н", 4, (20, 24)), _w("Н", 8, (0, 8)), _w("Н", 12, (0, 8), (20, 24)),
)}

CATEGORIES = (
    Category("ДЯ", ((6 * H, 22 * H),), {1: "ДЯ", 2: "ДЯ 2"}),
    Category("ДН", ((0, 6 * H), (22 * H, 24 * H)), {1: "ДН", 2: "ДН 2"}),
)

WEIGHTS = {"ДЯ": 1, "ДН": 1, "ДЯ 2": 2, "ДН 2": 2}
CASCADE = ("ДЯ", "ДН", "ДЯ 2", "ДН 2")
PLACEMENT = PlacementPolicy(("ДЯ", "ДН", "ДЯ 2", "ДН 2"))

GROUPS = {g.name: g for g in (
    Group("Смена 1", False, "Первая смена"),
    Group("Смена 2", False, "Вторая смена"),
    Group("Пятидневка", True, "Пятидневная рабочая неделя"),
    Group("Другие смены", False, "Индивидуальные графики"),
)}


def default_settings() -> Settings:
    return Settings(day_codes=DAY_CODES, windows=WINDOWS, categories=CATEGORIES,
                    weights=WEIGHTS, cascade_order=CASCADE, placement=PLACEMENT,
                    groups=GROUPS, versions=("defaults",))
