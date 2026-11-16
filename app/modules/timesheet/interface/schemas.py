"""Модели ответов вкладок «График», «Отметки», «Факт» и «Табель».

Каждый ключ ответа присутствует всегда; значение, которого в данном случае нет, — ``None``.
Модели запросов лежат рядом с операциями прикладного слоя.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from app.core.schemas import ApiModel

JsonDict = dict[str, Any]     # данные расчёта, которые интерфейс показывает как есть

# ── общее ────────────────────────────────────────────────────────────────────


class EmployeeBriefOut(ApiModel):
    """Сотрудник в строке экрана (``engine_common.emp_brief``)."""

    id: int
    full_name: str
    short_name: str
    position: str
    group: str
    color: Optional[str]
    tab_number: str


class DayRefusalOut(ApiModel):
    """Отказ по одному дню массовой правки."""

    employee_id: int
    date: str
    error: str


class PeriodOut(ApiModel):
    start: str
    end: str


# ── График: сетка ────────────────────────────────────────────────────────────


class GridShiftOut(ApiModel):
    source: str               # generated | manual
    anchor: str               # день-якорь смены
    start: str
    end: str
    start_hm: str
    end_hm: str
    note: Optional[str]       # None — у пользователя нет права на полные данные сетки
    id: Optional[int]


class AbsenceKindOut(ApiModel):
    id: int
    code: str
    name: str
    color: Optional[str]
    doc_type: str


class GridAbsenceOut(ApiModel):
    """Согласованное отсутствие в ячейке. Без права на полные данные заполнены только
    ``start_hm``, ``end_hm`` и ``whole_shift``."""

    id: Optional[int]
    start: Optional[str]
    end: Optional[str]
    start_hm: str
    end_hm: str
    note: Optional[str]
    whole_shift: Optional[bool]    # покрывает рабочее окно дня целиком — «выходной за часы»
    kind: Optional[AbsenceKindOut]


class GridTabelOut(ApiModel):
    code: str
    value: str
    hours: float
    source: str
    note: Optional[str]


class GridCellOut(ApiModel):
    tabel: Optional[GridTabelOut]
    shifts: list[GridShiftOut]
    segments: list[list[str]]      # видимые отрезки смены (минус отсутствия)
    absences: list[GridAbsenceOut]
    color: Optional[str]
    planned_hours: float
    employed: bool
    editable: bool                 # ручную смену можно поставить
    is_today: bool
    is_future: bool


class GridEmployeeOut(ApiModel):
    id: int
    full_name: str
    short_name: str
    full_name_genitive: str
    position: Optional[str]
    tab_number: str
    schedule_group: str
    group_color: str
    schedule_pattern: str
    active: bool
    hired_at: Optional[str]
    dismissed_at: Optional[str]


class DateRangeOut(ApiModel):
    start: str
    end: Optional[str]


class GridBlockOut(ApiModel):
    group: Optional[str]
    ranges: list[DateRangeOut]
    pattern_label: str


class EmployedRangeOut(ApiModel):
    start: str
    end: str
    open: bool
    note: str


class GridTotalsOut(ApiModel):
    planned_hours: float
    work_days: int


class GridRowOut(ApiModel):
    employee: GridEmployeeOut
    blocks: list[GridBlockOut]
    employed_ranges: list[EmployedRangeOut]
    cells: dict[str, GridCellOut]      # ключ — дата
    totals: GridTotalsOut


class GridDayOut(ApiModel):
    date: str
    day: int
    weekday: str
    is_weekend: bool
    is_today: bool
    double_scope: str
    double_title: str


class GridColorsOut(ApiModel):
    out_of_block: str
    worked_off: str
    inactive: str


class GridOut(ApiModel):
    year: int
    month: int
    month_name: str
    days: list[GridDayOut]
    rows: list[GridRowOut]
    today: str
    readonly: bool
    colors: GridColorsOut


# ── График: правки ───────────────────────────────────────────────────────────


class AbsenceAddedOut(ApiModel):
    ok: bool
    id: int


class RangeAbsenceOut(ApiModel):
    ok: bool                       # False — не записано ничего, отказы в errors
    written: int
    skipped: int
    errors: list[DayRefusalOut]
    mode: Optional[str]            # schedule_absence — записано в График, а не кодом Табеля


class ResetMonthOut(ApiModel):
    ok: bool
    cleared: int
    absences_cleared: int
    skipped_employees: int


# ── График: заявления ────────────────────────────────────────────────────────


class TimeoffHoursOut(ApiModel):
    employee_id: int
    date: str
    hours: Optional[float]
    hours_source: str              # window_of_day | timesheet_mode | default


class StatementKindOut(ApiModel):
    id: Optional[int]              # None — отсутствие задано кодом Табеля
    code: str
    name: str
    kind: str
    color: Optional[str]
    doc_type: str


class StatementEmployeeOut(ApiModel):
    id: int
    full_name: str
    short_name: str
    full_name_genitive: str
    position: Optional[str]
    tab_number: str
    nationality: str
    subdivision: str
    department: str


class StatementIntervalOut(ApiModel):
    id: int
    start: str
    end: str
    from_time: str
    until_time: str
    hours: Optional[float]
    hours_source: str
    whole_shift: bool
    kind: StatementKindOut
    note: str
    doc_type: str


class StatementPartialOut(ApiModel):
    from_time: str
    until_time: str
    hours: float
    hours_source: str
    kind: StatementKindOut


class AbsencePeriodOut(ApiModel):
    employee: Optional[StatementEmployeeOut]
    source: str                    # schedule_absence | tabel_code
    whole_shift: bool
    doc_type: str
    start: str
    end: str
    days: int
    shift: StatementKindOut
    note: str
    hours: Optional[float]
    hours_source: str
    partial: Optional[StatementPartialOut]             # только для отсутствий Графика
    intervals: Optional[list[StatementIntervalOut]]    # только для отсутствий Графика
    intervals_text: Optional[str]
    notes: list[str]


# ── Отметки ──────────────────────────────────────────────────────────────────


class PlanShiftOut(ApiModel):
    """Смена Графика, по которой сотрудник ожидается (``punch_plan.plan_for_date``)."""

    id: int
    source: str
    start: str
    end: str
    start_hm: str
    end_hm: str
    date: str


class LastPunchOut(ApiModel):
    kind: str
    ts: str
    source: str


class PunchStatusOut(ApiModel):
    now: str
    today: str
    plan_date: str
    punch_in_allowed: bool
    punch_out_allowed: bool
    punch_status_hint: Optional[str]
    shift: Optional[PlanShiftOut]
    planned_start: Optional[str]
    planned_end: Optional[str]
    expected: list[list[str]]          # ожидаемые подинтервалы: [начало, конец]
    on_shift: bool
    session_start: Optional[str]
    elapsed_hours: Optional[float]
    is_late: bool
    last_punch: Optional[LastPunchOut]
    today_hours: float
    balance_hours: float
    balance_period: Optional[PeriodOut]
    balance_note: str


class PunchOut(ApiModel):
    id: int
    kind: str
    ts: str
    source: str


class PunchDoneOut(ApiModel):
    ok: bool
    message: str
    backfill: bool
    plan_date: str
    punch: PunchOut
    warnings: list[str]
    status: PunchStatusOut


class PunchRowOut(ApiModel):
    id: int
    employee_id: int
    employee: str
    position: str
    ts: str
    kind: str
    source: str
    note: Optional[str]
    created_by: Optional[int]


class PunchDeletedOut(ApiModel):
    ok: bool
    warning: Optional[str]


class PunchNoteOut(ApiModel):
    ok: bool
    note: str


# ── Отметки: доска «прямо сейчас» ────────────────────────────────────────────


class BoardEmployeeOut(ApiModel):
    """Сотрудник карточки доски; у записи без сотрудника все поля пусты."""

    id: Optional[int]
    full_name: Optional[str]
    short_name: Optional[str]
    position: Optional[str]
    group: Optional[str]
    color: Optional[str]
    tab_number: Optional[str]
    phone: Optional[str]
    telegram: Optional[str]


class OpenSessionCardOut(ApiModel):
    employee_id: str
    employee: BoardEmployeeOut
    open_since: str
    open_since_hm: str
    minutes_open: int
    hours_open: str
    expected_today: bool
    shift_today: list[list[str]]
    shift_today_hm: list[list[str]]


class YetToComeOut(ApiModel):
    employee_id: str
    employee: BoardEmployeeOut
    expected_at: str
    expected_at_hm: str
    already_started: bool


class PresenceBoardOut(ApiModel):
    now: str
    today: str
    at_work_now: int
    expected_now: int
    open_session_cards: list[OpenSessionCardOut]
    yet_to_come: list[YetToComeOut]


# ── Факт ─────────────────────────────────────────────────────────────────────


class FactEmployeeOut(ApiModel):
    """Сотрудник истории сессий; у неизвестного номера заполнен только ``id``."""

    id: int
    full_name: Optional[str]
    short_name: Optional[str]
    position: Optional[str]
    group: Optional[str]
    color: Optional[str]
    tab_number: Optional[str]


class FactRangeOut(ApiModel):
    model_config = ApiModel.model_config | {"populate_by_name": True}

    from_: str = Field(alias="from")
    to: str
    first: str
    last: str


class FactSessionOut(ApiModel):
    employee_id: str
    start_utc: str
    end_utc: Optional[str]
    open: bool
    started_before_range: bool
    closed_after_range: bool
    start_local: str
    end_local: Optional[str]
    minutes: Optional[int]


class FactSessionsOut(ApiModel):
    employee: FactEmployeeOut
    range: FactRangeOut
    sessions: list[FactSessionOut]


class TimeCategoryOut(ApiModel):
    code: str
    start: str
    end: str
    crosses_midnight: bool


class FactMonthDayOut(ApiModel):
    date: str
    day: int
    weekday: str
    is_weekend: bool
    is_today: bool


class FactBarOut(ApiModel):
    start: str
    end: Optional[str]
    open: bool


class FactMonthCellOut(ApiModel):
    tabel: Optional[str]
    window: Optional[list[str]]
    absences: list[list[str]]
    out_of_staff: bool
    color: Optional[str]


class FactMonthRowOut(ApiModel):
    employee: EmployeeBriefOut
    sessions: list[FactBarOut]
    days: dict[str, FactMonthCellOut]      # ключ — дата


class FactMonthOut(ApiModel):
    year: int
    month: int
    step_minutes: int
    categories: list[TimeCategoryOut]
    days: list[FactMonthDayOut]
    rows: list[FactMonthRowOut]


class FactMarkOut(ApiModel):
    at: str
    kind: str
    rounded: str


class FactSegmentOut(ApiModel):
    start: str
    end: Optional[str]
    open: bool
    crosses_midnight: Optional[bool]       # None — сессия ещё открыта


class FlagOut(ApiModel):
    day: str
    code: str
    title: str
    hint: str
    data: JsonDict                         # параметры флага — как их отдал расчёт


class FactDayCardOut(ApiModel):
    timesheet_value: str
    window: Optional[list[str]]
    plan_minutes: int
    timesheet_plan_minutes: int
    fact_minutes: int
    work_minutes: int
    overtime_minutes: int
    debt_minutes: int
    codes: dict[str, int]
    pays_overtime: bool
    plan_equals_fact: bool
    flags: list[FlagOut]


class FactDayRowOut(ApiModel):
    employee: EmployeeBriefOut
    error: Optional[str]
    out_of_staff: bool
    marks: list[FactMarkOut]
    segments: list[FactSegmentOut]
    card: Optional[FactDayCardOut]


class FactDayOut(ApiModel):
    date: str
    period: PeriodOut
    granularity: str
    step_minutes: int
    tz: str
    all_employees: bool
    rows: list[FactDayRowOut]


# ── Табель ───────────────────────────────────────────────────────────────────


class TabelCellOut(ApiModel):
    code: str
    hours: float
    source: str
    note: Optional[str]
    value: str


class TabelRowOut(ApiModel):
    employee: EmployeeBriefOut
    cells: dict[str, TabelCellOut]         # ключ — дата
    plan_hours: float
    missing_days: list[str]
    lock: str                              # open | last_closed | locked


class TabelCodeOut(ApiModel):
    code: str
    title: str
    carries_hours: bool
    accepts_ut: bool
    counts_in_ut: bool
    plan_equals_fact_auto: bool
    doc_type: str


class TabelOut(ApiModel):
    year: int
    month: int
    half: Optional[int]
    granularity: str
    period: PeriodOut
    days: list[str]
    colors: dict[str, str]
    codes: list[TabelCodeOut]
    values: list[str]
    windows: dict[str, list[str]]          # значение Табеля → [начало, конец] окна
    can_edit: bool
    rows: list[TabelRowOut]


class TabelCellSavedOut(ApiModel):
    ok: bool
    warning: Optional[str]


class CellRefusalOut(ApiModel):
    employee_id: int
    date: str
    detail: Any


class TabelBulkOut(ApiModel):
    ok: bool                               # False — не записано ничего, отказы в errors
    cells: int
    written: int
    warnings: list[str]
    errors: list[CellRefusalOut]


class TabelFillOut(ApiModel):
    written: int
    skipped: int
    warnings: list[str]


class ClearedCellOut(ApiModel):
    employee_id: int
    date: str
    code: str
    hours: float
    note: str


class UncoveredDayOut(ApiModel):
    employee_id: int
    employee: str
    date: str


class TabelResetOut(ApiModel):
    ok: bool
    cleared: int
    cells: list[ClearedCellOut]            # первые 80 убранных ручных ячеек
    written: int
    skipped: int
    warnings: list[str]
    uncovered: list[UncoveredDayOut]       # первые 80 дней без строки Табеля
    uncovered_total: int
    locked_skipped: list[int]
    manual_shifts_dropped: list[str]
