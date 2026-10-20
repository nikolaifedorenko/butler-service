"""Стартовое наполнение справочников CFG-* (раздел 5).

Единственное место домена (кроме тестов), где допустимы литералы бизнес-кодов (12.4).
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

from .types import (
    PEF_NO,
    Category,
    DayCodePolicy,
    GlobalDefaults,
    Group,
    Settings,
    Window,
)

H = 60


def _policy(carries: bool, accepts: bool, counts: bool, auto: bool) -> DayCodePolicy:
    return DayCodePolicy(carries, accepts, counts, auto)


DAY_CODES = {code: _policy(*row) for code, row in (
    ("Я", (True, True, True, False)),
    ("К", (True, True, True, True)),    # «План=Факт Авто = Да» — единственный источник «Авто» (v7/R19)
    ("В", (False, True, True, False)),
    ("ДО", (False, False, True, False)),
    ("ОТ", (False, False, True, False)),
    ("ОВ", (False, False, True, False)),
    ("Б", (False, False, False, False)),
    ("НН", (False, False, False, False)),
)}
# «НБ» (неоплачиваемый больничный) в справочнике НЕ существует — артефакт старого
# наполнения, исключён решением владельца от 16.10.2026 (см. REMOVED_DAY_CODES
# в app/engine_bootstrap.py: из сохранённых версий код изымает strip_removed_day_codes).

WINDOWS = {key: Window(start * H, end * H) for key, start, end in (
    ("Я 12", 8, 20), ("Я 9", 9, 18), ("Я 8", 9, 17),
    ("К 12", 8, 20), ("К 9", 9, 18), ("К 8", 9, 17),
)}

CATEGORIES = (
    Category("ДЯ", 6 * H, 22 * H),      # дневные 06:00–22:00
    Category("ДН", 22 * H, 6 * H),      # ночные 22:00–06:00 (end <= start — через полночь)
)

WEIGHTS = {"ДЯ": 1, "ДН": 1, "ДЯ2": 2, "ДН2": 2}
CASCADE = ("ДЯ", "ДН", "ДЯ2", "ДН2")
PLACEMENT = ("ДЯ", "ДН", "ДЯ2", "ДН2")

GROUPS = {name: Group() for name in ("Смена 1", "Смена 2", "Пятидневка")}

GLOBAL_DEFAULTS = GlobalDefaults(double_overtime=False, pays_overtime=True, plan_equals_fact=PEF_NO)


def default_settings() -> Settings:
    """Стартовый неизменяемый набор конфигурации (3.5)."""
    return Settings(
        tz=ZoneInfo("Europe/Moscow"),
        step_minutes=60,
        late_limit_minutes=5,
        day_limit_minutes=24 * H,
        day_code_policy=DAY_CODES,
        windows=WINDOWS,
        categories=CATEGORIES,
        weights=WEIGHTS,
        cascade_order=CASCADE,
        placement_order=PLACEMENT,
        groups=GROUPS,
        global_defaults=GLOBAL_DEFAULTS,
        versions=("defaults-v7.1",),
    )
