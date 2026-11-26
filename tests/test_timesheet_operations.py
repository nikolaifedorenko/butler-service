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
    assert "отсутствует в справочнике кодов Табеля" in refuse(code="ЫЫ")


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


# ── банк часов ───────────────────────────────────────────────────────────────

def test_bank_adjustment_is_all_or_nothing(app_stack, db, admin, staff, monkeypatch):
    from app.modules.timesheet.adapters.orm import BankAdjustment
    from app.modules.timesheet.application import bank_entries

    emp = staff[0]
    mine = (BankAdjustment.employee_id == emp, BankAdjustment.note == "проверка операций")
    payload = bank_entries.BankAdjustIn(hours=1.5, note="проверка операций", date=FAR.isoformat())

    def broken_audit(*args, **kwargs):
        raise RuntimeError("журнал недоступен")

    monkeypatch.setattr(bank_entries, "audit", broken_audit)
    with pytest.raises(RuntimeError):
        bank_entries.adjust(db, admin, emp, payload)
    monkeypatch.undo()
    assert _count(app_stack, BankAdjustment, *mine) == 0

    done = bank_entries.adjust(db, admin, emp, payload)
    assert done["adjustment"]["hours"] == 1.5 and _count(app_stack, BankAdjustment, *mine) == 1
    bank_entries.delete_adjustment(db, admin, emp, done["adjustment"]["id"])
    assert _count(app_stack, BankAdjustment, *mine) == 0
    with pytest.raises(errors.NotFound):
        bank_entries.delete_adjustment(db, admin, emp, done["adjustment"]["id"])


def test_bank_adjustment_refusals(db, admin, staff):
    from app.modules.timesheet.application import bank_entries

    def refuse(cls, **fields):
        with pytest.raises(cls) as refusal:
            bank_entries.adjust(db, admin, fields.pop("employee", staff[0]),
                                bank_entries.BankAdjustIn(**{"hours": 1, "note": "проверка операций", **fields}))
        return str(refusal.value)

    assert refuse(errors.Validation, hours=0) == "Часы корректировки не могут быть нулевыми"
    assert refuse(errors.Validation, note="  ").startswith("Укажите причину")
    assert refuse(errors.NotFound, employee=10 ** 9) == "Сотрудник не найден"
    assert refuse(errors.Validation, date="10.11.2026") == "Дата должна быть в формате ГГГГ-ММ-ДД"


# ── двойная оплата ───────────────────────────────────────────────────────────

def test_double_pay_days_are_all_or_nothing(app_stack, db, admin, monkeypatch):
    from app.modules.timesheet.adapters.orm import DoublePayDay
    from app.modules.timesheet.application import doublepay_edit

    day = (FAR + dt.timedelta(days=60)).isoformat()
    mine = DoublePayDay.date == dt.date.fromisoformat(day)
    payload = doublepay_edit.DaysIn(dates=day, note="проверка операций")

    def broken_audit(*args, **kwargs):
        raise RuntimeError("журнал недоступен")

    monkeypatch.setattr(doublepay_edit, "audit", broken_audit)
    with pytest.raises(RuntimeError):
        doublepay_edit.add_days(db, admin, payload)
    monkeypatch.undo()
    assert _count(app_stack, DoublePayDay, mine) == 0

    added = doublepay_edit.add_days(db, admin, payload)
    assert (added["added"], added["updated"]) == (1, 0) and _count(app_stack, DoublePayDay, mine) == 1
    assert doublepay_edit.add_days(db, admin, payload)["updated"] == 1
    removed = doublepay_edit.delete_day(db, admin, added["days"][0]["id"])
    assert removed["date"] == day and _count(app_stack, DoublePayDay, mine) == 0


def test_double_pay_refusals(db, admin, staff):
    from app.modules.timesheet.application import doublepay_edit

    def refuse(cls, call, **fields):
        with pytest.raises(cls) as refusal:
            call(db, admin, **fields)
        return str(refusal.value)

    days = doublepay_edit.add_days
    assert refuse(errors.Validation, days, payload=doublepay_edit.DaysIn(dates="завтра")).startswith("Не понял даты")
    assert refuse(errors.Validation, days, payload=doublepay_edit.DaysIn()).startswith("Не указано ни одной даты")
    assert refuse(errors.Validation, days, payload=doublepay_edit.DaysIn(dates="2027-01-01", scope="x")) \
        .startswith("scope должен быть")
    assert refuse(errors.Validation, days, payload=doublepay_edit.DaysIn(start="2027-02-10", end="2027-02-01")) \
        == "Конец периода раньше начала"
    vip = doublepay_edit.add_vip
    assert refuse(errors.NotFound, vip, payload=doublepay_edit.VipIn(
        employee_id=10 ** 9, start_date="2027-01-01", end_date="2027-01-02")) == "Сотрудник не найден"
    assert refuse(errors.Validation, vip, payload=doublepay_edit.VipIn(
        employee_id=staff[0], start_date="2027-01-02", end_date="2027-01-01")) == "Конец периода раньше начала"
    assert refuse(errors.NotFound, doublepay_edit.delete_vip, vip_id=10 ** 9) == "Период не найден"


# ── словарь смен ─────────────────────────────────────────────────────────────

def test_shift_type_update_keeps_history_all_or_nothing(app_stack, db, admin, monkeypatch):
    from app.modules.timesheet.adapters.orm import ShiftRevision, ShiftType
    from app.modules.timesheet.application import shift_dictionary as dictionary

    base = {"code": "ПРОВОП", "name": "Проверочная смена", "start_time": "10:00", "end_time": "19:00"}
    created = dictionary.create_shift_type(db, admin, dictionary.ShiftTypeIn(**base))
    mine = ShiftType.id == created["id"]
    revisions = ShiftRevision.shift_type_id == created["id"]
    try:
        def broken_audit(*args, **kwargs):
            raise RuntimeError("журнал недоступен")

        change = dictionary.ShiftTypeIn(**{**base, "start_time": "11:00", "end_time": "20:00"})
        monkeypatch.setattr(dictionary, "audit", broken_audit)
        with pytest.raises(RuntimeError):
            dictionary.update_shift_type(db, admin, created["id"], change)
        monkeypatch.undo()
        with app_stack["SessionLocal"]() as other:
            assert other.scalar(select(ShiftType.start_time).where(mine)) == "10:00"
        assert _count(app_stack, ShiftRevision, revisions) == 0

        updated = dictionary.update_shift_type(db, admin, created["id"], change)
        assert updated["start_time"] == "11:00" and updated["revisions"] >= 1
        with pytest.raises(errors.Conflict):
            dictionary.create_shift_type(db, admin, dictionary.ShiftTypeIn(**base))
        assert dictionary.archive_shift_type(db, admin, created["id"])["archived"] is True
        with pytest.raises(errors.Conflict):
            dictionary.archive_shift_type(db, admin, created["id"])
        assert dictionary.restore_shift_type(db, admin, created["id"])["active"] is True
    finally:
        db.rollback()
        from sqlalchemy import delete

        db.execute(delete(ShiftRevision).where(revisions))
        db.execute(delete(ShiftType).where(mine))
        db.commit()


def test_shift_dictionary_refusals(db, admin):
    from app.modules.timesheet.application import shift_dictionary as dictionary

    with pytest.raises(errors.NotFound):
        dictionary.update_shift_type(db, admin, 10 ** 9, dictionary.ShiftTypeIn(code="X", name="X"))
    with pytest.raises(errors.NotFound):
        dictionary.archive_shift_type(db, admin, 10 ** 9)
    with pytest.raises(errors.NotFound):
        dictionary.restore_shift_type(db, admin, 10 ** 9)
    with pytest.raises(errors.NotFound):
        dictionary.revisions(db, 10 ** 9)


# ── настройки расчёта ────────────────────────────────────────────────────────

def test_settings_publication_is_all_or_nothing(app_stack, db, admin, monkeypatch):
    from app.modules.timesheet.adapters.orm import EngineSettingsVersion
    from app.modules.timesheet.application import engine_settings

    current = engine_settings.current(db)
    payload = current["active"]["payload"]
    valid_from = (FAR + dt.timedelta(days=400)).replace(day=1)
    mine = EngineSettingsVersion.note == "проверка операций"
    data = engine_settings.SettingsIn(valid_from=valid_from, payload=payload, note="проверка операций")

    def broken_audit(*args, **kwargs):
        raise RuntimeError("журнал недоступен")

    monkeypatch.setattr(engine_settings, "audit", broken_audit)
    with pytest.raises(RuntimeError):
        engine_settings.publish(db, admin, data)
    monkeypatch.undo()
    assert _count(app_stack, EngineSettingsVersion, mine) == 0

    stale = data.model_copy(update={"base_version_id": (current["latest_id"] or 0) - 1})
    with pytest.raises(errors.Conflict) as refusal:
        engine_settings.publish(db, admin, stale)
    assert "Настройки изменились" in str(refusal.value) and _count(app_stack, EngineSettingsVersion, mine) == 0
    try:
        published = engine_settings.publish(db, admin, data.model_copy(update={"base_version_id": current["latest_id"]}))
        assert published["applies_from"] == valid_from.isoformat() and _count(app_stack, EngineSettingsVersion, mine) == 1
    finally:
        db.rollback()
        from sqlalchemy import delete

        db.execute(delete(EngineSettingsVersion).where(mine))
        db.commit()


def test_settings_document_keeps_display_order(app_stack, db, admin):
    """Порядок кодов, окон и весов в опубликованной версии тот же, что в присланной."""
    from app.modules.timesheet.adapters.orm import EngineSettingsVersion
    from app.modules.timesheet.application import engine_settings

    payload = engine_settings.current(db)["active"]["payload"]
    payload["day_code_policy"] = dict(reversed(list(payload["day_code_policy"].items())))
    payload["weights"] = dict(reversed(list(payload["weights"].items())))
    valid_from = (FAR + dt.timedelta(days=800)).replace(day=1)
    note = "проверка порядка"
    try:
        engine_settings.publish(db, admin, engine_settings.SettingsIn(valid_from=valid_from, payload=payload, note=note))
        with app_stack["SessionLocal"]() as other:
            stored = other.scalar(select(EngineSettingsVersion).where(EngineSettingsVersion.note == note)).payload
        assert list(stored["day_code_policy"]) == list(payload["day_code_policy"])
        assert list(stored["weights"]) == list(payload["weights"])
    finally:
        db.rollback()
        from sqlalchemy import delete

        db.execute(delete(EngineSettingsVersion).where(EngineSettingsVersion.note == note))
        db.commit()


def test_settings_publication_refuses_bad_input(db, admin):
    from app.modules.timesheet.application import engine_settings

    payload = engine_settings.current(db)["active"]["payload"]

    def refuse(change, valid_from=(FAR + dt.timedelta(days=500)).replace(day=1)) -> str:
        import copy

        body = copy.deepcopy(payload)
        change(body)
        with pytest.raises(errors.Validation) as refusal:
            engine_settings.publish(db, admin, engine_settings.SettingsIn(valid_from=valid_from, payload=body))
        return str(refusal.value)

    assert refuse(lambda p: p.update(step_minutes=7)).startswith("Ошибка настроек")
    assert refuse(lambda p: p.update(windows={"Я 12": {"start_minute": "утро"}})).startswith("Некорректный формат")
    assert refuse(lambda p: p.update(tz="Asia/Tokyo")).startswith("Часовой пояс расчёта")
    assert "Цвет кода Табеля" in refuse(lambda p: next(iter(p["day_code_policy"].values())).update(color="red"))
    assert refuse(lambda p: p.update(period_granularity="half_month"),
                  valid_from=(FAR + dt.timedelta(days=500)).replace(day=16)).startswith("Гранулярность")


def test_modifier_conflict_carries_the_existing_record(app_stack, db, admin):
    from app.modules.timesheet.adapters.orm import DayModifier
    from app.modules.timesheet.application import engine_settings

    day = FAR + dt.timedelta(days=3)
    rule = engine_settings.ModifierIn(name="double_overtime", value="1", date=day, note="проверка операций")
    first = engine_settings.add_modifier(db, admin, rule)
    try:
        with pytest.raises(engine_settings.ModifierConflict) as refusal:
            engine_settings.add_modifier(db, admin, rule.model_copy(update={"value": "0"}))
        detail = refusal.value.detail
        assert refusal.value.status_code == 409 and detail["conflict_with"]["id"] == first
        assert "уже задано" in detail["message"] and "Удалите прежнее правило" in detail["message"]
        with pytest.raises(errors.Validation):
            engine_settings.add_modifier(db, admin, rule.model_copy(update={"name": "magic"}))
        with pytest.raises(errors.Validation):
            engine_settings.add_modifier(db, admin, rule.model_copy(update={"date": None}))
    finally:
        engine_settings.delete_modifier(db, admin, first)
    assert _count(app_stack, DayModifier, DayModifier.id == first) == 0
    with pytest.raises(errors.NotFound):
        engine_settings.delete_modifier(db, admin, first)


def test_rules_resolve_needs_known_employee_and_modifier(db, staff):
    from app.modules.timesheet.application import engine_settings

    with pytest.raises(errors.NotFound):
        engine_settings.resolve_rules(db, 10 ** 9, FAR)
    with pytest.raises(errors.Validation):
        engine_settings.resolve_rules(db, staff[0], FAR, "magic")


# ── управленческий табель ────────────────────────────────────────────────────

def test_period_refusal_is_journaled_once(app_stack, db, admin):
    """Закрытие, которое не прошло предпроверку, ничего не закрывает, но остаётся в журнале."""
    from app.modules.timesheet.application import mgmt_screen

    far = dt.date.today().replace(day=1) + dt.timedelta(days=95)
    target = f"{far.year}-{far.month:02d}"
    rows = (AuditLog.action == "period_close", AuditLog.target == target)
    before = _count(app_stack, AuditLog, *rows)
    out = mgmt_screen.close(db, admin, mgmt_screen.PeriodAction(year=far.year, month=far.month))
    assert out["ok"] is False and out["stage"] == "check" and out["done"] == [] and out["errors"]
    assert _count(app_stack, AuditLog, *rows) == before + 1


def test_period_actions_reject_extra_fields_and_bad_period(db, admin):
    from app.modules.timesheet.application import mgmt_screen

    with pytest.raises(Exception, match="employee_ids"):
        mgmt_screen.PeriodAction(year=2026, month=11, employee_ids=[1])
    with pytest.raises(errors.Validation):
        mgmt_screen.close(db, admin, mgmt_screen.PeriodAction(year=2026, month=13))
    with pytest.raises(errors.NotFound):
        mgmt_screen.table(db, admin, 2026, 11, employee_id=10 ** 9)
