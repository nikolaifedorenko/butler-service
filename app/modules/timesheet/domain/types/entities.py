"""Входные доменные сущности и контрактные dataclass'ы (3.2, 7.3, v7.1/F-06)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal, Mapping

Minutes = int                     # целые минуты — длительности (3.1)
MinuteOfDay = int                 # позиция в локальном дне 0..1440 — границы интервалов/окон/категорий
StepMinutes = int                 # шаг расчёта; атомарная гранула кода УТ
DayId = dt.date                   # календарный день в tz настроек
Moment = dt.datetime              # момент UTC, timezone-aware
Mode = Literal["view", "close"]

# допустимый тип значений Reason.data / Flag.data (3.1)
DataValue = (None | bool | int | float | str | dt.date | dt.datetime
             | tuple["DataValue", ...] | Mapping[str, "DataValue"])

KIND_IN = "in"
KIND_OUT = "out"


@dataclass(frozen=True)
class Period:
    """Произвольный непрерывный диапазон дат, включительный (3.3)."""

    start: dt.date
    end: dt.date


@dataclass(frozen=True)
class Day:
    """Строка Табеля (3.2). plan_minutes — информационный (зарплатный) план строки;
    расчётный план карточки — от окна (v7.1/R34)."""

    day: dt.date
    code: str
    plan_minutes: Minutes
    employee_id: str
    group: str


@dataclass(frozen=True)
class Mark:
    """Сырая отметка PWA: момент UTC + тип из источника (3.2)."""

    employee_id: str
    at_utc: dt.datetime
    kind: Literal["in", "out"]


@dataclass(frozen=True)
class CalcMark:
    """Расчётное представление отметки: округлённый момент + связь с исходной (3.2)."""

    source: Mark
    at_calc: dt.datetime


@dataclass(frozen=True)
class Interval:
    """Расчётный интервал [start, end) — границы на сетке шага (3.2)."""

    day: dt.date
    start_minute: MinuteOfDay
    end_minute: MinuteOfDay

    @property
    def length(self) -> Minutes:
        return max(0, self.end_minute - self.start_minute)


@dataclass(frozen=True)
class RawInterval:
    """Исходный интервал присутствия — точные моменты с секундами (3.2, 4.5)."""

    day: dt.date
    start_utc: dt.datetime
    end_utc: dt.datetime


@dataclass(frozen=True)
class Session:
    """Сессия присутствия — результат ядра pair_marks (3.2, 4.3).
    end = None — не закрыта отметкой «ушёл»; потребитель обрезает по своей границе."""

    start: dt.datetime
    end: dt.datetime | None


@dataclass(frozen=True)
class Shift:
    """Смена Графика; может пересекать полночь (3.2)."""

    employee_id: str
    start_utc: dt.datetime
    end_utc: dt.datetime


@dataclass(frozen=True)
class Absence:
    """Согласованное отсутствие: UTC-интервал, может пересекать полночь, ≤ 24 ч (3.2, v7/R17)."""

    employee_id: str
    start_utc: dt.datetime
    end_utc: dt.datetime


@dataclass(frozen=True)
class Adjustment:
    """Ручная корректировка банка (3.2). period — период внесения (RUL-BANK-CONTINUITY);
    reason_code — свободная строка, ядро не интерпретирует (RUL-REASON-CODE-FREE)."""

    amount_minutes: Minutes
    period: Period
    reason_code: str
    note: str | None = None


@dataclass(frozen=True)
class DeferredBlock:
    """Отложенный блок кода УТ (3.2, v7: без reason_code — R1)."""

    source_day: dt.date
    tariff: str
    minutes: Minutes


@dataclass(frozen=True)
class ShiftEntry:
    """Запись хранилища Графика (3.2, 16.3): происхождение — generated | manual."""

    shift: Shift
    source: Literal["generated", "manual"]


@dataclass(frozen=True)
class Employment:
    """Интервал трудоустройства (7.3, v7/R23). end — последний рабочий день включительно;
    None — работает. Контрактный dataclass: доменной логикой не используется."""

    start: dt.date
    end: dt.date | None


@dataclass(frozen=True)
class ClosingInputs:
    """Входной снимок закрытия — основа пересчёта (7.3). Контрактный dataclass."""

    bank_open: Minutes
    deferred_in: tuple[DeferredBlock, ...]
    previous_step_minutes: StepMinutes


@dataclass(frozen=True)
class PeriodState:
    """Состояние периода для оркестрации режимов (7.3, v7/R26, R37). Контрактный dataclass."""

    closed: bool                  # закрыт ли этот период
    previous_closed: bool         # закрыт ли предыдущий период (RUL-SEQUENTIAL-CLOSING)
    next_closed: bool             # закрыт ли следующий период (право на пересчёт, 7.2)
    opening_bank_set: bool        # посеяно ли начальное значение банка (OPENING_SEED, R37)
