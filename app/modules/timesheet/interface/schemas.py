"""Модели ответов модуля «Учёт времени».

Каждый ключ ответа присутствует всегда; значение, которого в данном случае нет, — ``None``.
Модели запросов лежат рядом с операциями прикладного слоя.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

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


# ── Управленческий табель ────────────────────────────────────────────────────


class MgmtDayOut(ApiModel):
    day: str
    timesheet_value: str
    plan_minutes: int                      # расчётный план — длина окна
    plan_hours: str
    timesheet_plan_minutes: int            # информационный план строки Табеля
    timesheet_plan_hours: str
    fact_minutes: int
    work_minutes: int
    overtime_minutes: int
    debt_minutes: int
    codes: dict[str, int]
    pays_overtime: bool
    plan_equals_fact: bool
    flags: list[FlagOut]


class MgmtBankOut(ApiModel):
    open: int
    open_normalized: int
    adjustments: int
    credited: int
    paid: int
    closed: int
    open_h: str
    closed_h: str
    adjustments_h: str
    credited_h: str


class MgmtDebtOut(ApiModel):
    total: int
    residual: int
    total_h: str
    residual_h: str


class MgmtDeferredOut(ApiModel):
    source_day: str
    tariff: str
    minutes: int
    hours: str


class MgmtReasonOut(ApiModel):
    code: str
    text: str


class MgmtCutOut(ApiModel):
    source_day: str
    placed_day: Optional[str]
    tariff: str
    taken_minutes: int
    paid_minutes: int


class MgmtTraceOut(ApiModel):
    step: str
    code: str
    text: str


class MgmtStateOut(ApiModel):
    closed: bool
    previous_closed: bool
    next_closed: bool
    opening_bank_set: bool
    can_close: bool
    can_recalculate: bool


class NullablePeriodOut(ApiModel):
    start: Optional[str]
    end: Optional[str]


class MgmtRowOut(ApiModel):
    """Строка сотрудника. При отказе расчёта — сотрудник, сообщение и причина блокировки."""

    employee: EmployeeBriefOut
    error: Optional[str]
    error_code: Optional[Literal["PREVIOUS_PERIOD_NOT_CLOSED", "OPENING_BANK_REQUIRED", "EMPLOYMENT_CHAIN_GAP"]]
    revision: Optional[int]                # сведения о закрытии — только у закрытого периода
    closed_by: Optional[str]
    closed_at: Optional[str]
    versions: Optional[list[str]]
    effective_period: Optional[NullablePeriodOut]
    employment: Optional[NullablePeriodOut]
    out_of_staff_days: Optional[list[str]]
    days: Optional[list[MgmtDayOut]]
    ut: Optional[dict[str, dict[str, int]]]     # дата → код УТ → минуты
    bank: Optional[MgmtBankOut]
    debt: Optional[MgmtDebtOut]
    deferred: Optional[list[MgmtDeferredOut]]
    exceptions: Optional[list[MgmtReasonOut]]
    cuts: Optional[list[MgmtCutOut]]
    totals: Optional[dict[str, int]]
    trace: Optional[list[MgmtTraceOut]]
    state: Optional[MgmtStateOut]
    source: Optional[str]                  # saved — сохранённый результат, view — живой расчёт


class MgmtPreviousPeriodOut(PeriodOut):
    year: int
    month: int
    half: Optional[Literal[1, 2]]


class MgmtBlockingOut(ApiModel):
    previous_period: Optional[MgmtPreviousPeriodOut]
    opening_bank_missing: int


class MgmtOut(ApiModel):
    year: int
    month: int
    half: Optional[int]
    granularity: str
    period: PeriodOut
    days: list[str]
    tariffs: list[str]
    step_minutes: int
    settings_versions: list[str]
    now: str
    can_close: bool
    can_recalculate: bool
    blocking: MgmtBlockingOut
    rows: list[MgmtRowOut]


class PeriodDoneOut(ApiModel):
    employee_id: int
    bank_closed: float
    deferred: int


class PeriodRefusalOut(ApiModel):
    employee_id: int
    name: str
    error: str


class PeriodActionOut(ApiModel):
    ok: bool
    period: PeriodOut
    total: int
    skipped_closed: int
    stage: str                             # check — остановились на предпроверке, save — записывали
    done: list[PeriodDoneOut]
    errors: list[PeriodRefusalOut]


# ── банк часов ───────────────────────────────────────────────────────────────


class BankAdjustmentOut(ApiModel):
    id: int
    hours: float
    date: str
    note: str
    author: str
    reason_code: str
    created_at: str


class BankAdjustedOut(ApiModel):
    ok: bool
    adjustment: BankAdjustmentOut
    bank_now: float


class BankNowOut(ApiModel):
    ok: bool
    bank_now: float


# ── двойная оплата ───────────────────────────────────────────────────────────


class DoubleDayOut(ApiModel):
    id: int
    date: str
    day: int
    month: int
    year: int
    weekday: str
    is_weekend: bool
    scope: str
    scope_title: str
    note: str


class VipPeriodOut(ApiModel):
    id: int
    employee_id: int
    employee_name: str
    employee_full_name: str
    start_date: str
    end_date: str
    days: int
    note: str
    author: str


class ScopeOut(ApiModel):
    id: str
    title: str


class DoubleCalendarOut(ApiModel):
    days: list[DoubleDayOut]
    vip: list[VipPeriodOut]
    year: Optional[int]
    scopes: list[ScopeOut]
    reason_titles: dict[str, str]


class DoubleDaysAddedOut(ApiModel):
    ok: bool
    added: int
    updated: int
    days: list[DoubleDayOut]


class DoubleDayDeletedOut(ApiModel):
    ok: bool
    deleted: DoubleDayOut


class VipAddedOut(ApiModel):
    ok: bool
    item: VipPeriodOut


class VipDeletedOut(ApiModel):
    ok: bool
    deleted: VipPeriodOut


# ── словарь смен ─────────────────────────────────────────────────────────────


class TabelValueOut(ApiModel):
    value: str
    code: str
    hours: str
    title: str
    start_hm: str
    end_hm: str


class TabelValuesOut(ApiModel):
    values: list[TabelValueOut]


class ShiftTypeOut(ApiModel):
    id: int
    code: str
    name: str
    kind: str
    start_time: str
    end_time: str
    overnight: bool
    color: str
    sort_order: int
    is_working: bool
    counts_as_worked: bool
    is_default_off: bool
    planned_hours: float
    active: bool
    doc_type: str
    punch_in_allowed: bool
    punch_out_allowed: bool
    archived: bool
    archived_at: Optional[str]
    revisions: int


class DayCodeOut(ApiModel):
    code: str
    title: str
    carries_hours: bool
    accepts_ut: bool
    counts_in_ut: bool
    punch_in: bool
    punch_out: bool
    doc_type: str


class DayCodesOut(ApiModel):
    codes: list[DayCodeOut]


class ShiftArchivedOut(ApiModel):
    ok: bool
    archived: bool
    shift: ShiftTypeOut


class ShiftRestoredOut(ApiModel):
    ok: bool
    shift: ShiftTypeOut


class ShiftRevisionOut(ApiModel):
    valid_from: str
    code: str
    name: str
    kind: str
    start_time: str
    end_time: str
    overnight: bool
    color: str
    is_working: bool
    counts_as_worked: bool
    is_default_off: bool
    doc_type: Optional[str]


class ShiftRevisionsOut(ApiModel):
    current: ShiftTypeOut
    revisions: list[ShiftRevisionOut]


# ── настройки расчёта ────────────────────────────────────────────────────────


class ActiveSettingsOut(ApiModel):
    id: Optional[int]                      # None — версий ещё нет, показаны справочники по умолчанию
    valid_from: Optional[str]
    payload: JsonDict                      # документ справочников целиком


class SettingsVersionOut(ApiModel):
    id: int
    valid_from: str
    note: Optional[str]
    created_by: Optional[str]
    created_at: Optional[str]


class ModifierNameOut(ApiModel):
    name: str
    title: str


class EngineSettingsOut(ApiModel):
    active: ActiveSettingsOut
    latest_id: Optional[int]
    versions: list[SettingsVersionOut]
    modifier_names: list[ModifierNameOut]


class PeriodClosedStateOut(ApiModel):
    """Закрыт ли период — по сотрудникам, и доступен ли пересчёт."""

    start: str
    end: Optional[str]
    closed: bool
    last_closed_start: Optional[str]
    closed_count: int
    total: int
    complete: bool
    not_closed: list[str]
    recalc_available: bool


class SettingsPublishedOut(ApiModel):
    ok: bool
    id: int
    applies_from: str                      # начало первого периода, который посчитается по версии
    period: PeriodClosedStateOut


class ModifierOut(ApiModel):
    id: int
    name: str
    title: str
    value: str
    employee_id: Optional[int]
    group: Optional[str]
    date: Optional[str]
    period_start: Optional[str]
    note: Optional[str]
    created_by: Optional[str]


class ModifierAddedOut(ApiModel):
    id: int


class HealthCheckOut(ApiModel):
    code: str
    level: str                             # error | warn
    screen: str                            # под-экран настроек, где это исправляется
    text: str


class HealthPeriodsOut(ApiModel):
    granularity: str
    current: PeriodOut
    last_closed_start: Optional[str]
    last_closed: Optional[PeriodClosedStateOut]


class HealthVersionOut(ApiModel):
    id: Optional[int]
    valid_from: Optional[str]
    note: Optional[str]
    created_by: Optional[str]
    created_at: str


class HealthStatsOut(ApiModel):
    tz: str
    step_minutes: Optional[int]
    period_granularity: str
    late_limit_minutes: Optional[int]
    day_limit_minutes: Optional[int]
    codes: int
    windows: int
    groups: int
    weights: int
    rules_active: int
    rules_upcoming: int
    global_defaults: JsonDict


class HealthUpcomingOut(ApiModel):
    kind: str                              # version | rule
    date: str
    screen: str
    text: str


class HealthRecentOut(ApiModel):
    ts: str
    actor: Optional[str]
    action: str
    target: Optional[str]
    title: str


class HealthOut(ApiModel):
    on: str
    periods: HealthPeriodsOut
    version: HealthVersionOut
    stats: HealthStatsOut
    checks: list[HealthCheckOut]
    upcoming: list[HealthUpcomingOut]
    recent: list[HealthRecentOut]


class RuleSourceOut(ApiModel):
    kind: str                              # rule | calendar | vip | static | global_default | code_column | none
    id: Optional[int]
    author: str
    note: str
    text: str


class RuleChainOut(ApiModel):
    level: int
    form: str
    hit: bool


class ResolvedRuleOut(ApiModel):
    name: str
    title: str
    value: Optional[str]
    text: str
    level: Optional[int]
    scope: Optional[str]
    source: RuleSourceOut
    chain: list[RuleChainOut]


class ResolveEmployeeOut(ApiModel):
    id: int
    name: str
    full_name: str
    group: str


class ResolvePeriodOut(ApiModel):
    start: str
    end: str
    granularity: str


class ResolveVersionOut(ApiModel):
    id: Optional[int]
    valid_from: Optional[str]


class ResolvedRulesOut(ApiModel):
    employee: ResolveEmployeeOut
    date: str
    code: str
    plan_minutes: int
    period: ResolvePeriodOut
    version: ResolveVersionOut
    modifiers: list[ResolvedRuleOut]
