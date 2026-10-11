"""Подготовка данных движка v7.1 при старте: стартовая версия справочников
(defaults + группа «Другие смены» из блоков приложения), заполнение Табеля из
циклов и генерация Графика из Табеля (16.3)."""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .engine.adapters.settings_codec import to_payload
from .engine.domain.settings.defaults import default_settings
from .models import Employee, EngineSettingsVersion, Setting, TabelDay

# правила старого движка, которых в v7.1 нет (округление длительностей, ворота, автозакрытие …)
OBSOLETE_RULES = ("round_mode", "count_early_arrival", "count_late_departure", "min_session_min",
                  "auto_close_missing_out", "late_by_raw_time", "night_start", "night_end",
                  "round_step_min", "grace_minutes")

# Строки справочников приложения — данные, добавляемые к стартовому наполнению (раздел 5:
# «коды добавляются строкой»). Ночная/суточная смена дробится на два значения двух дней
# (4.7, паттерн EX-15): «С 16» — вечерняя часть суток 08:00–24:00, «С 8» — утренняя
# 00:00–08:00, «С 24» — сплошные сутки при подряд идущих сменах. «НВ» — выходной за часы.
APP_EXTRA_GROUPS = ("Другие смены",)
APP_EXTRA_DAY_CODES = {
    "С": {"carries_hours": True, "accepts_ut": True, "counts_in_ut": True,
          "plan_equals_fact_auto": False, "title": "Суточная смена (части дня)"},
    "НВ": {"carries_hours": False, "accepts_ut": False, "counts_in_ut": True,
           "plan_equals_fact_auto": False, "title": "Выходной за отработанные часы"},
}
APP_EXTRA_WINDOWS = {
    "С 16": {"start_minute": 8 * 60, "end_minute": 24 * 60},
    "С 8": {"start_minute": 0, "end_minute": 8 * 60},
    "С 24": {"start_minute": 0, "end_minute": 24 * 60},
}
# человеческие подписи кодов — данные приложения (домен их не знает); хранятся в payload
CODE_TITLES = {
    "Я": "Явка (дневная работа)", "К": "Командировка", "В": "Выходной",
    "ДО": "Отпуск без сохранения", "ОТ": "Ежегодный отпуск", "ОВ": "Оплачиваемый выходной",
    "Б": "Больничный", "НБ": "Неоплачиваемый больничный",
    "НН": "Неявка по невыясненным причинам",
    "С": "Суточная смена (части дня)", "НВ": "Выходной за отработанные часы",
}


def _initial_payload(db: Session) -> dict:
    payload = to_payload(default_settings())
    payload["groups"] = list(payload["groups"]) + [g for g in APP_EXTRA_GROUPS
                                                   if g not in payload["groups"]]
    payload["day_code_policy"] = {**payload["day_code_policy"],
                                  **{k: v for k, v in APP_EXTRA_DAY_CODES.items()
                                     if k not in payload["day_code_policy"]}}
    payload["windows"] = {**payload["windows"],
                          **{k: v for k, v in APP_EXTRA_WINDOWS.items()
                             if k not in payload["windows"]}}
    for code, row in payload["day_code_policy"].items():
        row.setdefault("title", CODE_TITLES.get(code, ""))
    old = {s.key: s.value for s in db.scalars(select(Setting).where(Setting.key.in_(OBSOLETE_RULES)))}
    try:
        step = int(float(old.get("round_step_min", 60)))
        payload["step_minutes"] = step if step > 0 and 60 % step == 0 else 60
        payload["late_limit_minutes"] = int(float(old.get("grace_minutes", 5)))
    except ValueError:
        pass
    return payload


def bootstrap_engine(db: Session, first: dt.date | None = None, last: dt.date | None = None) -> None:
    if not db.scalar(select(EngineSettingsVersion.id)):
        db.add(EngineSettingsVersion(valid_from=dt.date(2000, 1, 1), payload_json=json.dumps(
            _initial_payload(db), ensure_ascii=False),
            note="Стартовое наполнение CFG-* (спецификация v7.1)", created_by_name="system"))
        db.flush()
    from sqlalchemy import delete
    db.execute(delete(Setting).where(Setting.key.in_(OBSOLETE_RULES)))
    if not db.scalar(select(TabelDay.id)):
        from .tabel_fill import fill_timesheet_from_cycles
        today = dt.date.today()
        fill_timesheet_from_cycles(db, list(db.scalars(select(Employee).where(
            Employee.deleted_at.is_(None)))),
            first or (today.replace(day=1) - dt.timedelta(days=62)).replace(day=1),
            last or (today.replace(day=28) + dt.timedelta(days=40)))
    db.flush()
