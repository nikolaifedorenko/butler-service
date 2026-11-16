"""График, отметки, Факт и Табель — операции прикладного слоя (ADR-0013, раздел 4).

Правки идут в далёкий будущий месяц и убираются за собой: текущий месяц нужен другим тестам.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import func, select

from app.core import errors
from app.core.audit import AuditLog
from app.core.identity import User
from app.modules.people.application import Employee
from app.modules.timesheet.adapters.orm import Punch, ScheduleAbsence, ScheduleShift, TabelDay
from app.modules.timesheet.application import (
    absence_statement,
    punches,
    schedule_edit,
    tabel_screen,
    timesheet_edit,
)
from app.modules.timesheet.application.errors import TimesheetLockedError
from app.modules.timesheet.application.period_params import ensure_period

FAR = (dt.date.today().replace(day=1) + dt.timedelta(days=430)).replace(day=10)
DATES_AT_RUN_TIME = ("FAR",)


@pytest.fixture()
def admin(db):
    from app.core.auth import Principal

    return Principal(db.scalar(select(User).where(User.username == "admin")), None)


@pytest.fixture()
def staff(db) -> list[int]:
    """Двое работающих сотрудников без даты увольнения."""
    rows = db.scalars(select(Employee).where(Employee.deleted_at.is_(None), Employee.active.is_(True),
                                             Employee.dismissed_at.is_(None)).order_by(Employee.id).limit(2))
    return [e.id for e in rows]


@pytest.fixture()
def work_day(db, admin, staff):
    """Рабочий день «Я 12» у первого сотрудника в далёком месяце; после теста ячейка очищается."""
    cell = tabel_screen.CellIn(employee_id=staff[0], date=FAR, code="Я", hours=12)
    tabel_screen.put_cell(db, admin, cell)
    yield staff[0], FAR
    db.rollback()
    for row in db.scalars(select(ScheduleAbsence).where(ScheduleAbsence.employee_id == staff[0],
                                                        ScheduleAbsence.note == "проверка операций")):
        schedule_edit.remove_absence(db, admin, row.id)
    schedule_edit.delete_manual_shift(db, admin, staff[0], FAR)
    tabel_screen.put_cell(db, admin, cell.model_copy(update={"code": "", "hours": 0}))


def _count(app_stack, model, *where) -> int:
    with app_stack["SessionLocal"]() as other:        # другая сессия видит только зафиксированное
        return other.scalar(select(func.count()).select_from(model).where(*where))


def _code(app_stack, employee_id: int, day: dt.date):
    with app_stack["SessionLocal"]() as other:
        return other.scalar(select(TabelDay.code).where(TabelDay.employee_id == employee_id, TabelDay.date == day))


def _shift(start: str, end: str, note: str = "") -> schedule_edit.ShiftIntervalIn:
    return schedule_edit.ShiftIntervalIn(start=start, end=end, note=note)


# ── График ───────────────────────────────────────────────────────────────────

def test_manual_shift_is_all_or_nothing(app_stack, db, admin, work_day, monkeypatch):
    """Ручная смена заменяет генерацию дня. Сбой на записи в журнал возвращает и генерацию."""
    emp, day = work_day
    manual = (ScheduleShift.employee_id == emp, ScheduleShift.date == day, ScheduleShift.source == "manual")
    generated = (ScheduleShift.employee_id == emp, ScheduleShift.date == day, ScheduleShift.source == "generated")
    assert _count(app_stack, ScheduleShift, *generated) == 1

    def broken_audit(*args, **kwargs):
        raise RuntimeError("журнал недоступен")

    payload = schedule_edit.ManualShiftIn(employee_id=emp, date=day, shifts=[_shift("09:00", "18:00", "ручная")])
    monkeypatch.setattr(schedule_edit, "audit", broken_audit)
    with pytest.raises(RuntimeError):
        schedule_edit.put_manual_shift(db, admin, payload)
    monkeypatch.undo()
    assert _count(app_stack, ScheduleShift, *manual) == 0
    assert _count(app_stack, ScheduleShift, *generated) == 1

    schedule_edit.put_manual_shift(db, admin, payload)
    assert _count(app_stack, ScheduleShift, *manual) == 1
    assert _count(app_stack, ScheduleShift, *generated) == 0
    schedule_edit.delete_manual_shift(db, admin, emp, day)
    assert _count(app_stack, ScheduleShift, *manual) == 0
    assert _count(app_stack, ScheduleShift, *generated) == 1


def test_manual_shift_refusals_are_input_errors(db, admin, work_day, staff):
    emp, day = work_day

    def refuse(**fields):
        with pytest.raises(errors.Validation) as refusal:
            schedule_edit.put_manual_shift(db, admin, schedule_edit.ManualShiftIn(
                **{"employee_id": emp, "date": day, "shifts": [], **fields}))
        return str(refusal.value)

    assert refuse() == "Укажите интервалы смены"
    assert refuse(shift_type_id=10 ** 9) == "Смена словаря не найдена"
    assert refuse(shifts=[_shift("9", "25:00")]) == "Время в формате ЧЧ:ММ"
    assert refuse(shifts=[_shift("18:00", "09:00")]).startswith("Конец смены должен быть позже начала")
    # день без строки Табеля ручную смену не принимает: отказ ввода (422), а не «настройки повреждены»
    assert refuse(date=day + dt.timedelta(days=1), shifts=[_shift("09:00", "18:00")]).startswith("День не редактируем")


def test_absence_for_unknown_employee_is_not_found(app_stack, db, admin, admin_client):
    payload = {"employee_id": 10 ** 9, "date": FAR.isoformat(), "from_time": "14:00", "until_time": "16:00"}
    with pytest.raises(errors.NotFound):
        schedule_edit.add_absence(db, admin, schedule_edit.AbsenceIn(**payload))
    r = admin_client.post("/api/schedule/absence", json=payload)
    assert (r.status_code, r.json()["detail"]) == (404, "Сотрудник не найден")
    assert _count(app_stack, ScheduleAbsence, ScheduleAbsence.employee_id == 10 ** 9) == 0


def test_absence_is_saved_with_kind_and_note(app_stack, db, admin, work_day):
    emp, day = work_day
    absence_id = schedule_edit.add_absence(db, admin, schedule_edit.AbsenceIn(
        employee_id=emp, date=day, from_time="14:00", until_time="16:00", note="проверка операций"))
    assert _count(app_stack, ScheduleAbsence, ScheduleAbsence.id == absence_id,
                  ScheduleAbsence.note == "проверка операций") == 1
    with pytest.raises(errors.Validation):
        schedule_edit.add_absence(db, admin, schedule_edit.AbsenceIn(
            employee_id=emp, date=day, from_time="16:00", until_time="14:00"))
    schedule_edit.remove_absence(db, admin, absence_id)
    assert _count(app_stack, ScheduleAbsence, ScheduleAbsence.id == absence_id) == 0


def test_range_absence_writes_every_day_or_none(app_stack, db, admin, work_day, monkeypatch):
    """Отсутствие на период: отказ одного дня отменяет и уже записанные дни, и запись в журнал."""
    emp, day = work_day
    real = timesheet_edit.save_timesheet_day

    def locked_second_day(employee_id, d, *args, **kwargs):
        if d == day + dt.timedelta(days=1):
            raise TimesheetLockedError(f"{employee_id}:{d}")
        return real(employee_id, d, *args, **kwargs)

    audit_rows = (AuditLog.action == "schedule_range_absence", AuditLog.target == f"{day}..{day + dt.timedelta(days=1)}")
    payload = schedule_edit.RangeAbsenceIn(employee_ids=[emp], first=day, last=day + dt.timedelta(days=1), code="ОТ")
    monkeypatch.setattr(timesheet_edit, "save_timesheet_day", locked_second_day)
    result = schedule_edit.range_absence(db, admin, payload)
    monkeypatch.undo()
    assert (result["ok"], result["written"]) == (False, 0)
    assert [(e["employee_id"], e["date"]) for e in result["errors"]] == [(emp, (day + dt.timedelta(days=1)).isoformat())]
    assert result["errors"][0]["error"].startswith("Период закрыт")
    assert _code(app_stack, emp, day) == "Я"
    assert _count(app_stack, AuditLog, *audit_rows) == 0


def test_range_absence_checks_request_before_writing(db, admin, staff):
    def refuse(**fields):
        with pytest.raises(errors.Validation) as refusal:
            schedule_edit.range_absence(db, admin, schedule_edit.RangeAbsenceIn(
                **{"employee_ids": staff, "first": FAR, "last": FAR, "code": "ОТ", **fields}))
        return str(refusal.value)

    assert refuse(last=FAR - dt.timedelta(days=1)) == "Дата окончания раньше даты начала"
    assert refuse(last=FAR + dt.timedelta(days=400)) == "Период отсутствия не может быть больше 366 дней"
    assert refuse(employee_ids=list(range(1, 502))) == "Слишком много сотрудников (максимум 500)"
    assert refuse(shift_type_id=10 ** 9) == "Вид отсутствия не найден"
    assert refuse(code="Я") == "Код несёт плановые часы — это не отсутствие"
    assert "отсутствует в CFG-DAY-CODES" in refuse(code="ЫЫ")


def test_period_is_checked_once_for_every_screen(db, admin):
    with pytest.raises(errors.Validation):
        ensure_period(2026, 13)
    with pytest.raises(errors.Validation):
        schedule_edit.reset_month(db, admin, schedule_edit.ClearMonthIn(year=2026, month=0))
    with pytest.raises(errors.Validation):
        tabel_screen.reset(db, admin, tabel_screen.ResetIn(year=2026, month=13))


def test_statement_hours_need_an_employee(db):
    with pytest.raises(errors.NotFound):
        absence_statement.timeoff_hours(db, 10 ** 9, FAR)
    with pytest.raises(errors.NotFound):
        absence_statement.absence_period(db, 10 ** 9, FAR)


def test_grid_without_full_rights_keeps_keys_and_hides_values(admin_client, employee_client):
    """Сетка для сотрудника имеет те же ключи, что и полная: скрытые значения — ``None``."""
    today = dt.date.today()
    params = {"year": today.year, "month": today.month}

    def shifts(client):
        return [sh for row in client.get("/api/schedule", params=params).json()["rows"]
                for cell in row["cells"].values() for sh in cell["shifts"]]

    full, plan = shifts(admin_client), shifts(employee_client)
    assert full and plan and set(full[0]) == set(plan[0])
    assert all(sh["id"] is None and sh["note"] is None and sh["start_hm"] for sh in plan)
    assert all(sh["id"] for sh in full)


# ── Табель ───────────────────────────────────────────────────────────────────

def test_bulk_writes_every_cell_or_none(app_stack, db, admin, work_day):
    emp, day = work_day
    cells = (AuditLog.action == "tabel_cell", AuditLog.target == f"employee:{emp}")
    before = _count(app_stack, AuditLog, *cells)
    result = tabel_screen.bulk(db, admin, tabel_screen.BulkIn(employee_ids=[emp, 10 ** 9], dates=[day], code="В"))
    assert (result["ok"], result["written"], result["cells"]) == (False, 0, 2)
    assert [e["employee_id"] for e in result["errors"]] == [10 ** 9]
    assert _code(app_stack, emp, day) == "Я"
    assert _count(app_stack, AuditLog, *cells) == before

    result = tabel_screen.bulk(db, admin, tabel_screen.BulkIn(employee_ids=[emp], dates=[day], code="В"))
    assert (result["ok"], result["written"], result["errors"]) == (True, 1, [])
    assert _code(app_stack, emp, day) == "В"
    assert _count(app_stack, AuditLog, *cells) == before + 1


def test_bulk_size_is_limited(db, admin):
    with pytest.raises(errors.Validation):
        tabel_screen.bulk(db, admin, tabel_screen.BulkIn(employee_ids=list(range(1, 502)), dates=[FAR], code="В"))


def test_cell_is_all_or_nothing(app_stack, db, admin, work_day, monkeypatch):
    emp, day = work_day

    def broken_audit(*args, **kwargs):
        raise RuntimeError("журнал недоступен")

    monkeypatch.setattr(tabel_screen, "audit", broken_audit)
    with pytest.raises(RuntimeError):
        tabel_screen.put_cell(db, admin, tabel_screen.CellIn(employee_id=emp, date=day, code="В"))
    monkeypatch.undo()
    assert _code(app_stack, emp, day) == "Я"
    assert _count(app_stack, ScheduleShift, ScheduleShift.employee_id == emp, ScheduleShift.date == day) == 1


# ── отметки ──────────────────────────────────────────────────────────────────

def test_punch_refusals_write_nothing(app_stack, db, admin, staff):
    emp = staff[0]
    before = _count(app_stack, Punch, Punch.employee_id == emp)
    with pytest.raises(errors.Forbidden):                       # у администратора нет своего сотрудника
        punches.punch(db, admin, punches.PunchIn())
    with pytest.raises(errors.NotFound):
        punches.punch(db, admin, punches.PunchIn(employee_id=10 ** 9))
    with pytest.raises(errors.Validation):
        punches.punch(db, admin, punches.PunchIn(employee_id=emp, kind="sideways"))
    with pytest.raises(errors.Validation):
        punches.punch(db, admin, punches.PunchIn(employee_id=emp, ts="вчера"))
    db.rollback()
    assert _count(app_stack, Punch, Punch.employee_id == emp) == before


def test_backfilled_punch_is_all_or_nothing(app_stack, db, admin, staff, monkeypatch):
    emp = staff[1]
    ts = (dt.datetime.now() - dt.timedelta(days=3)).replace(hour=3, minute=7, second=0, microsecond=0)
    same = (Punch.employee_id == emp, Punch.note == "проверка операций")

    def broken_audit(*args, **kwargs):
        raise RuntimeError("журнал недоступен")

    payload = punches.PunchIn(employee_id=emp, ts=ts.isoformat(timespec="minutes"), note="проверка операций")
    monkeypatch.setattr(punches, "audit", broken_audit)
    with pytest.raises(RuntimeError):
        punches.punch(db, admin, payload)
    monkeypatch.undo()
    assert _count(app_stack, Punch, *same) == 0

    done = punches.punch(db, admin, payload)
    assert done["backfill"] is True and done["punch"]["source"] == "manual"
    assert _count(app_stack, Punch, *same) == 1
    assert punches.set_punch_note(db, admin, done["punch"]["id"], punches.NoteIn(note="  проверка операций  ")) \
        == "проверка операций"
    assert punches.delete_punch(db, admin, done["punch"]["id"]) is None
    assert _count(app_stack, Punch, *same) == 0
    with pytest.raises(errors.NotFound):
        punches.delete_punch(db, admin, done["punch"]["id"])
