"""Вкладка «График» (16.3): просмотр ShiftEntry, ручная смена дня (якорь — день начала,
accepts_ut = Да), удаление ручной смены, перегенерация из Табеля по окнам CFG-WINDOWS
(значение с часами → смена = окно целиком в локальном tz, сохранённое в UTC).
Логический «разрез» — записи согласованных отсутствий (save_absence/drop_absence)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Iterable, Sequence

from ..domain.day_card.accepts_ut import accepts_ut
from ..domain.day_card.window_of_day import window_of_day
from ..domain.settings.types import Settings
from ..domain.types.entities import Day, Period, Shift, ShiftEntry
from .context import EnginePorts
from .errors import ScheduleDayNotEditableError
from .months import month_period, period_containing


def _settings_for(day: dt.date, ports: EnginePorts) -> Settings:
    return ports.settings.load(period_containing(day, "month"))


def _row(employee_id: str, day: dt.date, ports: EnginePorts) -> Day | None:
    rows = ports.timesheet.days(employee_id, Period(day, day))
    return next((r for r in rows if r.day == day), None)


def day_editable(employee_id: str, day: dt.date, ports: EnginePorts) -> bool:
    row = _row(employee_id, day, ports)
    return row is not None and accepts_ut(row, _settings_for(day, ports))


def save_schedule_day(employee_id: str, day: dt.date, shifts: Sequence[Shift],
                      ports: EnginePorts) -> None:
    if not day_editable(employee_id, day, ports):
        raise ScheduleDayNotEditableError(employee_id, day)
    # ручная смена ЗАМЕЩАЕТ генерацию дня целиком (16.3): generated-строки дня
    # убираются сразу, иначе в ячейке соседствуют оба интервала (дефект 16.10.2026:
    # «Я 12 08:00–20:00» не пропадала после ручной 09:00–18:00)
    ports.schedule_store.replace_generated(employee_id, Period(day, day), ())
    ports.schedule_store.save_manual(employee_id, day, shifts)


def drop_manual_day(employee_id: str, day: dt.date, ports: EnginePorts) -> None:
    ports.schedule_store.drop_manual(employee_id, day)


def save_absence(employee_id: str, day: dt.date, start_hhmm: str, end_hhmm: str,
                 end_next_day: bool, ports: EnginePorts) -> int:
    """Кнопка «пропуск/отлучка» (16.3): запись согласованного отсутствия, в том числе
    через полночь; хранимая смена физически не делится (v7/R17)."""
    return ports.schedule_store.save_absence(employee_id, day, start_hhmm, end_hhmm,
                                             end_next_day)


def drop_absence(absence_id: int, ports: EnginePorts) -> None:
    ports.schedule_store.drop_absence(absence_id)


def generated_entry(row: Day, st: Settings) -> ShiftEntry | None:
    window = window_of_day(row, st)
    if window is None:
        return None
    midnight = dt.datetime.combine(row.day, dt.time(0), st.tz)
    start = (midnight + dt.timedelta(minutes=window.start_minute)).astimezone(dt.timezone.utc)
    end = (midnight + dt.timedelta(minutes=window.end_minute)).astimezone(dt.timezone.utc)
    return ShiftEntry(Shift(row.employee_id, start, end), "generated")


@dataclass(frozen=True)
class RebuildOutcome:
    generated: int
    manual_dropped: tuple[dt.date, ...]     # ручные смены, удалённые из-за нередактируемости


def rebuild_generated_schedule(employee_id: str, period: Period,
                               ports: EnginePorts) -> RebuildOutcome:
    """Перегенерация Графика из Табеля (16.3): generated-записи заменяются, КРОМЕ
    дней с ручной сменой — она замещает генерацию дня целиком и восстанавливается
    только явным удалением (drop_manual_day); manual сохраняются, если код дня
    остаётся редактируемым, и удаляются, если стал нередактируемым (UI показывает
    уведомление)."""
    st = ports.settings.load(period)
    rows = ports.timesheet.days(employee_id, period)
    # якорные дни ручных смен — одним чтением периода (без N+1 по дням)
    manual_days = {e.shift.start_utc.astimezone(st.tz).date()
                   for e in ports.schedule_store.load_entries(employee_id, period)
                   if e.source == "manual"}
    entries = []
    for row in rows:
        if row.day in manual_days:
            continue                      # день закрыт ручной сменой (16.3)
        entry = generated_entry(row, st)
        if entry is not None:
            entries.append(entry)
    ports.schedule_store.replace_generated(employee_id, period, entries)
    dropped = tuple(row.day for row in rows
                    if not accepts_ut(row, st) and row.day in manual_days)
    for day in dropped:
        ports.schedule_store.drop_manual(employee_id, day)
    return RebuildOutcome(len(entries), dropped)


def rebuild_generated_for_days(employee_id: str, days: Iterable[dt.date],
                               ports: EnginePorts) -> RebuildOutcome:
    """Пакетная перегенерация Графика после МАССОВОЙ записи Табеля (P0-3).

    `days` — дни, которые операция действительно записала. Вместо перегенерации на
    каждую ячейку (DELETE+INSERT generated-строк на каждый день) — один проход на
    каждый затронутый месяц. Результат тот же: `rebuild_generated_schedule` заменяет
    generated-строки периода целиком и не трогает дни с ручной сменой (16.3), а
    повторный вызов идемпотентен.

    Соседние дни за границей записи не перегенерируются: их строки Табеля не менялись,
    а generated-строки дня D пересоздаются вместе с месяцем D.
    """
    generated, dropped = 0, set()
    for year, month in sorted({(d.year, d.month) for d in days}):
        out = rebuild_generated_schedule(employee_id, month_period(year, month), ports)
        generated += out.generated
        dropped.update(out.manual_dropped)
    return RebuildOutcome(generated, tuple(sorted(dropped)))
