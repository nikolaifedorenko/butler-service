"""Подготовка данных движка v7.1 при старте: стартовая версия справочников
(defaults + группа «Другие смены» из блоков приложения), заполнение Табеля из
циклов и генерация Графика из Табеля (16.3).

Норматив справочника кодов Табеля (решение владельца от 12.10.2026)
-------------------------------------------------------------------
В Табеле нет кодов «Суточная смена» и «Выходной за отработанные часы»:

* **Суточная/ночная смена — графиковая смена.** В Табеле стоит обычная явка с окном,
  начинающимся вместе со сменой (суточные 08:00–08:00 → окно 08:00–20:00), а по факту
  сотрудник работает через полночь. Расчёт сам разделяет присутствие локальными
  полуночами: рабочее время — пересечение с окном своего дня, всё вне окна —
  переработка этого же дня (4.7, RUL-WORK-AND-OVERTIME, RUL-WINDOW-FROM-TIMESHEET).
  Дробить смену на два значения двух дней не нужно: «утро» после полуночи попадает в
  карточку следующего дня, где окна нет, и становится его переработкой.

  Часы в значении Табеля («10,75» у «Я 10,75») — зарплатный атрибут строки: в расчёте
  участвует только окно, план карточки и недостача считаются от него (R34,
  RUL-PLAN-BELOW-WINDOW). Отдельной сущности «зарплатная норма смены» в системе нет.
* **Выходной за ранее отработанные часы — отсутствие в Графике.** В Табеле остаётся
  соответствующая явка («Я» или «К»): отсутствие не влияет на план (RUL-ABSENCE-
  ONLY-FLAGS), возникает недостача, которую при закрытии гасит банк часов — то есть
  ранее накопленные переработки (паттерн EX-29).

Оба случая — данные Графика и банка, а не новые коды первичного документа.
"""
from __future__ import annotations

import datetime as dt
import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings_store import Setting
from app.core.time import local_date
from app.modules.employees.application import Employee

from .adapters.orm import EngineSettingsVersion, TabelDay
from .adapters.settings_codec import to_payload
from .domain.settings.defaults import default_settings

# правила старого движка, которых в v7.1 нет (округление длительностей, ворота, автозакрытие …)
OBSOLETE_RULES = ("round_mode", "count_early_arrival", "count_late_departure", "min_session_min",
                  "auto_close_missing_out", "late_by_raw_time", "night_start", "night_end",
                  "round_step_min", "grace_minutes")

# Коды, исключённые из справочника Табеля решением владельца:
# * 12.10.2026 — «С» (суточная смена, части дня) и «НВ» (выходной за отработанные
#   часы): оба случая оформляются данными Графика, а не кодом первичного документа;
# * 16.10.2026 — «НБ» (неоплачиваемый больничный): такого кода в Т-13 нет,
#   это артефакт старого наполнения справочника.
REMOVED_DAY_CODES = ("С", "НВ", "НБ")

# Цвета кодов Табеля — данные приложения (домен их не знает, 2.4): хранятся в payload
# рядом со строкой CFG-DAY-CODES и читаются интерфейсом (сетка Табеля, легенда).
CODE_COLORS = {
    "Я": "#34a862", "К": "#2b8fb6", "В": "#c3cdd9", "ДО": "#d9822b", "ОТ": "#f0a500",
    "ОВ": "#9b59b6", "Б": "#e05d4b", "НН": "#b03a48",
}

# Строки справочников приложения — данные, добавляемые к стартовому наполнению (раздел 5:
# «коды добавляются строкой»). Единственная добавка — значение для суточной/ночной
# графиковой смены: зарплатная норма 10,75 ч при окне 08:00–20:00 (план строки меньше
# длины окна — RUL-PLAN-BELOW-WINDOW, паттерн EX-15/EX-51).
APP_EXTRA_GROUPS = ("Другие смены",)
# Значение с тем же окном, что у «Я 12», но с меньшим числом часов: часы в значении
# Табеля — зарплатный атрибут строки, в расчёте участвует только окно (R34). Нужно,
# чтобы табельщик мог поставить «Я 10,75» в ячейку суточного дня без ошибки
# CHK-WINDOW-EXISTS; расчёт от выбора «Я 12» или «Я 10,75» не меняется.
APP_EXTRA_WINDOWS = {
    "Я 10,75": {"start_minute": 8 * 60, "end_minute": 20 * 60},
}
# человеческие подписи кодов — данные приложения (домен их не знает); хранятся в payload
CODE_TITLES = {
    "Я": "Явка (дневная работа)", "К": "Командировка", "В": "Выходной",
    "ДО": "Отпуск без сохранения", "ОТ": "Ежегодный отпуск", "ОВ": "Оплачиваемый выходной",
    "Б": "Больничный", "НН": "Неявка по невыясненным причинам",
}

# Режим отметок и заявление — атрибуты КАРТОЧКИ кода Табеля (решение владельца
# 16.10.2026): «пришёл/ушёл» настраиваются у кода, несущего часы, а у кода
# отсутствия вместо них — шаблон заявления. Как и title/color, это данные
# приложения (домен их не знает, 2.4): лежат в строке day_code_policy payload'а.
# Сервер соблюдает punch_in/punch_out при приёме отметок (api/punches.py),
# doc_type — источник заявления для печати по коду Табеля (api/schedule.py::
# absence_period). Значения по умолчанию: отметки разрешены (RUL-ALL-MARKS-
# COUNTED — отметка в день без плана даёт переработку), заявления нет.
CODE_EXTRA = {
    "ОТ": {"punch_in": False, "punch_out": False, "doc_type": "vacation_paid"},
    "ДО": {"punch_in": False, "punch_out": False, "doc_type": "vacation_unpaid"},
}


def code_app_defaults(code: str) -> dict:
    """App-поля строки кода Табеля по умолчанию: отметки, заявление."""
    extra = CODE_EXTRA.get(code, {})
    return {"punch_in": extra.get("punch_in", True),
            "punch_out": extra.get("punch_out", True),
            "doc_type": extra.get("doc_type", "")}


def _initial_payload(db: Session) -> dict:
    payload = to_payload(default_settings())
    payload["groups"] = list(payload["groups"]) + [g for g in APP_EXTRA_GROUPS
                                                   if g not in payload["groups"]]
    payload["windows"] = {**payload["windows"],
                          **{k: v for k, v in APP_EXTRA_WINDOWS.items()
                             if k not in payload["windows"]}}
    for code, row in payload["day_code_policy"].items():
        row.setdefault("title", CODE_TITLES.get(code, ""))
        row.setdefault("color", CODE_COLORS.get(code, ""))
        for key, value in code_app_defaults(code).items():
            row.setdefault(key, value)
    old = {s.key: s.value for s in db.scalars(select(Setting).where(Setting.key.in_(OBSOLETE_RULES)))}
    try:
        step = int(float(old.get("round_step_min", 60)))
        payload["step_minutes"] = step if step > 0 and 60 % step == 0 else 60
        payload["late_limit_minutes"] = int(float(old.get("grace_minutes", 5)))
    except ValueError:
        pass
    return payload


def _used_codes(db: Session) -> set[str]:
    """Коды, которые реально стоят в Табеле: их нельзя изъять из справочника,
    иначе расчёт остановится (UnknownDayCodeError, CHK-KNOWN-DAY-CODES)."""
    from sqlalchemy import inspect

    if not inspect(db.get_bind()).has_table("tabel_days"):
        return set()
    rows = db.execute(select(TabelDay.code).where(TabelDay.code.in_(REMOVED_DAY_CODES))
                      .distinct()).scalars().all()
    return set(rows)


def strip_removed_day_codes(db: Session) -> dict:
    """Убрать исключённые коды и их окна из сохранённых версий справочников.

    Идемпотентно и безопасно: код изымается только если в Табеле нет ни одной строки
    с ним (иначе версия осталась бы невалидной для уже посчитанных периодов) —
    такие коды остаются, а ситуация пишется в лог и видна в selfcheck.
    Окна убираются по префиксу «<код> » (ключ CFG-WINDOWS = «код часы»).
    """
    used = _used_codes(db)
    removed: dict[str, list[str]] = {}
    blocked = sorted(used)
    for ver in db.scalars(select(EngineSettingsVersion)):
        try:
            payload = json.loads(ver.payload_json)
        except (ValueError, TypeError):
            continue
        codes = payload.get("day_code_policy") or {}
        windows = payload.get("windows") or {}
        drop = [c for c in REMOVED_DAY_CODES if c in codes and c not in used]
        if not drop:
            continue
        for code in drop:
            codes.pop(code, None)
            for key in [k for k in windows if k.partition(" ")[0] == code]:
                windows.pop(key, None)
                removed.setdefault(code, []).append(key)
            removed.setdefault(code, [])
        payload["day_code_policy"] = codes
        payload["windows"] = windows
        ver.payload_json = json.dumps(payload, ensure_ascii=False)
    if blocked:
        logging.getLogger("uvicorn.error").warning(
            "Коды Табеля %s исключены из справочника, но используются в Табеле (%s) — "
            "версии справочников не изменены. Замените их в Табеле на явку/отсутствие "
            "и повторите запуск.", ", ".join(f"«{c}»" for c in blocked),
            ", ".join(f"«{c}»" for c in blocked))
    db.flush()
    return {"removed_codes": [c for c in REMOVED_DAY_CODES if c not in used],
            "removed_windows": sorted({k for v in removed.values() for k in v}),
            "blocked_by_timesheet": blocked}


def apply_code_app_defaults(db: Session) -> int:
    """Добрать app-поля строк кодов Табеля (punch_in/punch_out/doc_type) в сохранённых
    версиях справочников — идемпотентно: существующие значения не перезаписываются
    (их правит владелец в карточке кода). Дописаны только недостающие ключи, поэтому
    расчёт закрытых периодов не меняется: домен app-полей не знает (2.4)."""
    patched = 0
    for ver in db.scalars(select(EngineSettingsVersion)):
        try:
            payload = json.loads(ver.payload_json)
        except (ValueError, TypeError):
            continue
        codes = payload.get("day_code_policy") or {}
        changed = False
        for code, row in codes.items():
            if not isinstance(row, dict):
                continue
            for key, value in code_app_defaults(code).items():
                if key not in row:
                    row[key] = value
                    changed = True
        if changed:
            ver.payload_json = json.dumps(payload, ensure_ascii=False)
            patched += 1
    db.flush()
    return patched


def bootstrap_engine(db: Session, first: dt.date | None = None, last: dt.date | None = None) -> None:
    if not db.scalar(select(EngineSettingsVersion.id)):
        db.add(EngineSettingsVersion(valid_from=dt.date(2000, 1, 1), payload_json=json.dumps(
            _initial_payload(db), ensure_ascii=False),
            note="Стартовое наполнение CFG-* (спецификация v7.1)", created_by_name="system"))
        db.flush()
    strip_removed_day_codes(db)
    apply_code_app_defaults(db)
    from sqlalchemy import delete
    db.execute(delete(Setting).where(Setting.key.in_(OBSOLETE_RULES)))
    if not db.scalar(select(TabelDay.id)):
        from .application.tabel_fill import fill_timesheet_from_cycles
        today = local_date()
        fill_timesheet_from_cycles(db, list(db.scalars(select(Employee).where(
            Employee.deleted_at.is_(None)))),
            first or (today.replace(day=1) - dt.timedelta(days=62)).replace(day=1),
            last or (today.replace(day=28) + dt.timedelta(days=40)))
    db.flush()
