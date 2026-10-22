"""Стражи находок P1 внешнего ревью от 20.10.2026 — батч «таймшит/движок» (батч 3 плана).

Каждая группа закрепляет один фикс, чтобы находка не вернулась:

* **P1-ts-1** — конкурентное закрытие периода: нарушение уникального ключа
  ``uq_closing_emp_period`` транслируется адаптером в ``StorageConflictError``,
  use case — в ``PeriodAlreadyClosedError`` (409; в mgmt bulk — запись в errors,
  массовая семантика 200 сохранена). Транзакция откатывается целиком:
  «сбой между записями → ничего не сохранено» (тест-план спеки п.15, 7.3
  «конкурентное закрытие одного периода невозможно»). HTTP-семантику «повторное
  закрытие → errors» стережёт test_engine_api (здесь не дублируется);
* **P1-ts-2** — ноты ручных смен ложатся на свои интервалы: повторная выборка
  ``put_manual_shift`` детерминирована (ORDER BY id = порядок вставки = порядок
  интервалов запроса);
* **P1-ts-3** — повреждённая строка Табеля (план не кратен 15, CHK-PLAN-FORMAT)
  отказывает ОТКРЫТИЕ вкладок типизированно (409, ``TimesheetRowCorruptError``),
  а не сырым ValueError → 500; домен строг как прежде (решение владельца —
  строгий вариант, а не приблизительное отображение);
* **P1-ts-4** — ``presence_board`` грузит Settings для месяца ЛОКАЛЬНОГО
  «сегодня» (16.2, 16.1 п.7), а не UTC-дня: на границе месяцев доска не берёт
  справочники прошлого месяца;
* **P1-ts-5** — битый tz сохранённых настроек — ``ConfigError("CFG-TZ")``
  (409 вкладки / 422 редактор) вместо ``ZoneInfoNotFoundError`` → 500;
* **P1-ts-6** — на горячем пути ``deserialize`` нет assert: битый сохранённый
  результат — типизированная ``StoredResultCorruptError``, в том числе под
  ``python -O`` (assert'ы вырезаются — проверка обязана выжить);
* **P1-ts-7** — ``view_period`` не обращается к ``saved[0]`` вслепую:
  closed без сохранённого результата — типизированный отказ.

Посадки данных — будущие месяцы 2027-01…2027-06: демо-цепочка закрытий
(test_api) доходит только до прошлого месяца текущего года, пересечений с
другими модулями тестов нет; посаженное удаляется в каждом тесте. Напоминание
review-p1 §5: после записей чужой (HTTP) сессии тестовая сессия делает
``expire_all()``, иначе identity map отдаёт устаревшие атрибуты.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import delete, event, select

from app.core.db import engine as db_engine
from app.modules.employees.application import Employee
from app.modules.timesheet.adapters.orm import (
    EngineSettingsVersion,
    PeriodClosing,
    ScheduleShift,
    TabelDay,
)
from app.modules.timesheet.adapters.settings_codec import from_payload, to_payload
from app.modules.timesheet.adapters.sql_closings import SqlSettlementStore
from app.modules.timesheet.adapters.sql_uow import SqlUnitOfWork
from app.modules.timesheet.application.close_period import close_period
from app.modules.timesheet.application.engine_common import covers_window
from app.modules.timesheet.application.errors import (
    PeriodAlreadyClosedError,
    StoredResultCorruptError,
    TimesheetRowCorruptError,
)
from app.modules.timesheet.application.months import month_period
from app.modules.timesheet.application.view_period import view_period
from app.modules.timesheet.domain.settings.defaults import default_settings
from app.modules.timesheet.domain.types.entities import ClosingInputs, Employment, Period
from app.modules.timesheet.domain.types.errors import ConfigError
from app.modules.timesheet.domain.types.results import FlagsResult, SettleResult
from app.modules.timesheet.interface.deserialize import result_from_dict
from app.modules.timesheet.ports.unit_of_work import StorageConflictError
from tests.engine.fakes import FakeDb, build_fakes
from tests.engine.helpers import EMP, at, day

BASE = pathlib.Path(__file__).resolve().parent.parent
OCT = month_period(2026, 10)


# ── общий стенд (как tests/engine/test_application._stand) ────────────────────

def _stand():
    db = FakeDb(settings=default_settings())
    db.timesheet_rows = [day(n, "Я 12") if n % 2 else day(n, "В") for n in range(1, 32)]
    db.employment[EMP] = Employment(dt.date(2026, 10, 1), None)
    db.adjustments.append((EMP, OCT.start, 0, "OPENING_SEED"))
    return build_fakes(db)


def _ivanov(db):
    return next(e for e in db.scalars(select(Employee)) if "Иванов" in e.display_name)


def _empty_result() -> SettleResult:
    return SettleResult(cards=(), mgmt_timesheet={}, bank_open_minutes=0,
                        bank_open_normalized_minutes=0, bank_adjustments_minutes=0,
                        bank_closed_minutes=0, credited_to_bank_minutes=0,
                        paid_with_bank_minutes=0, total_debt_minutes=0,
                        residual_debt_minutes=0, cuts=(), deferred_blocks=(),
                        exceptions=(), trace=())


def _corrupt_result_json(step: str) -> str:
    """Валидный по форме SettleResult с НЕВАЛИДНЫМ шагом записи трассы."""
    return json.dumps({
        "cards": [], "mgmt_timesheet": {}, "bank_open_minutes": 0,
        "bank_open_normalized_minutes": 0, "bank_adjustments_minutes": 0,
        "bank_closed_minutes": 0, "credited_to_bank_minutes": 0,
        "paid_with_bank_minutes": 0, "total_debt_minutes": 0,
        "residual_debt_minutes": 0, "cuts": [], "deferred_blocks": [],
        "exceptions": [], "trace": [{"step": step, "code": "X", "data": {}}]})


# ── P1-ts-1: конкурентное закрытие — типизированный конфликт, атомарность ─────

def test_ts1_storage_conflict_maps_to_period_already_closed(monkeypatch):
    """Гонка: соперник закоммитил закрытие между нашей проверкой права и flush —
    адаптер отдаёт StorageConflictError, use case переводит его в
    PeriodAlreadyClosedError (409), а не роняет IntegrityError (500)."""
    db, ports = _stand()

    def conflict(*_args, **_kwargs):
        raise StorageConflictError("UNIQUE constraint failed: uq_closing_emp_period")

    monkeypatch.setattr(ports.store, "save_result", conflict)
    with pytest.raises(PeriodAlreadyClosedError):
        close_period(EMP, OCT, at(1, 0, month=11), ports)
    # атомарность: UoW откатил транзакцию — ничего не сохранено
    assert db.closings == {}
    assert db.deferred == {}


def test_ts1_failure_between_writes_saves_nothing():
    """Сбой МЕЖДУ записями закрытия (тест-план спеки п.15): результат, успевший
    попасть в транзакцию до сбоя, откатывается — ничего не сохранено."""
    db, ports = _stand()
    db.fail_on = "save_closing_bank"           # инъекция после save_result
    with pytest.raises(RuntimeError):
        close_period(EMP, OCT, at(1, 0, month=11), ports)
    assert db.closings == {}
    assert db.deferred == {}


def test_ts1_adapter_translates_integrity_error_on_flush(db, monkeypatch):
    """Реальная БД: строка соперника уже в базе, наш save_result её не видит
    (окно READ COMMITTED между проверкой и flush — здесь моделируется патчем
    _row), INSERT упирается в уникальный ключ → StorageConflictError."""
    emp = _ivanov(db)
    period = Period(dt.date(2027, 5, 1), dt.date(2027, 5, 31))
    db.add(PeriodClosing(employee_id=emp.id, period_start=period.start,
                         period_end=period.end, revision=1))
    db.commit()
    try:
        store = SqlSettlementStore(db, None, "test")
        monkeypatch.setattr(store, "_row", lambda employee_id, prd: None)
        with pytest.raises(StorageConflictError):
            store.save_result(str(emp.id), period, _empty_result(), FlagsResult(()),
                              ClosingInputs(0, (), 60), ["v-test"], 60)
    finally:
        db.rollback()
        db.execute(delete(PeriodClosing).where(
            PeriodClosing.employee_id == emp.id,
            PeriodClosing.period_start >= dt.date(2027, 5, 1),
            PeriodClosing.period_start <= dt.date(2027, 5, 31)))
        db.commit()


def test_ts1_uow_commit_translates_integrity_error(db):
    """Страховка отложенного flush: конфликт уникальности на commit — тоже
    StorageConflictError (и rollback, сессия остаётся usable)."""
    emp = _ivanov(db)
    start, end = dt.date(2027, 6, 1), dt.date(2027, 6, 30)
    db.add(PeriodClosing(employee_id=emp.id, period_start=start, period_end=end,
                         revision=1))
    db.commit()
    try:
        with pytest.raises(StorageConflictError), SqlUnitOfWork(db):
            db.add(PeriodClosing(employee_id=emp.id, period_start=start,
                                 period_end=end, revision=1))
    finally:
        db.rollback()
        db.execute(delete(PeriodClosing).where(
            PeriodClosing.employee_id == emp.id, PeriodClosing.period_start == start))
        db.commit()


# ── P1-ts-2: ноты ручных смен — на своих интервалах (ORDER BY) ────────────────

def test_ts2_manual_shift_notes_land_on_own_intervals(manager_client, db):
    emp = _ivanov(db)
    d0 = dt.date(2027, 4, 5)
    # строка Табеля «Я 12» делает день редактируемым (accepts_ut = Да, 16.3)
    db.add(TabelDay(employee_id=emp.id, date=d0, code="Я", plan_minutes=720,
                    source="manual"))
    db.commit()
    captured: list[str] = []

    def _capture(conn, cur, stmt, params, ctx, many):
        captured.append(stmt)

    event.listen(db_engine, "before_cursor_execute", _capture)
    try:
        # интервалы НАРОЧНО вне хронологии: порядок вставки = порядок запроса,
        # а не порядок по времени — zip обязан следовать за ним
        r = manager_client.put("/api/schedule/shift", json={
            "employee_id": emp.id, "date": d0.isoformat(),
            "shifts": [{"start": "18:00", "end": "22:00", "note": "вечер"},
                       {"start": "08:00", "end": "12:00", "note": "утро"}]})
        assert r.status_code == 200, r.text
        db.expire_all()   # записи сделала чужая (HTTP) сессия — review-p1 §5
        rows = list(db.scalars(select(ScheduleShift).where(
            ScheduleShift.employee_id == emp.id, ScheduleShift.date == d0,
            ScheduleShift.source == "manual").order_by(ScheduleShift.id)))
        # 18:00 МСК = 15:00 UTC, 08:00 МСК = 05:00 UTC (наивный UTC в ORM)
        assert [(row.start_utc.hour, row.note) for row in rows] == \
            [(15, "вечер"), (5, "утро")]
        # SQL-страж: повторная выборка manual-строк — с ORDER BY (без него
        # порядок строк не гарантирует даже PostgreSQL, не только тест)
        selects = [s for s in captured
                   if s.lstrip().upper().startswith("SELECT") and "schedule_shifts" in s]
        assert selects, "повторная выборка manual-строк не выполнялась"
        assert all("ORDER BY" in s.upper() for s in selects), selects
    finally:
        event.remove(db_engine, "before_cursor_execute", _capture)
        db.expire_all()
        db.execute(delete(ScheduleShift).where(
            ScheduleShift.employee_id == emp.id, ScheduleShift.date == d0))
        db.execute(delete(TabelDay).where(
            TabelDay.employee_id == emp.id, TabelDay.date == d0))
        db.commit()


# ── P1-ts-3: битая строка Табеля — типизированный отказ вкладок, не 500 ───────

def test_ts3_corrupt_plan_row_fails_tabs_typed_not_500(manager_client, db):
    emp = _ivanov(db)
    d0 = dt.date(2027, 3, 10)
    db.add(TabelDay(employee_id=emp.id, date=d0, code="Я", plan_minutes=50,
                    source="manual"))   # 50 не кратно 15 — CHK-PLAN-FORMAT
    db.commit()
    try:
        r = manager_client.get("/api/tabel", params={"year": 2027, "month": 3})
        assert r.status_code == 409, r.text
        assert "не кратен 15" in r.json()["detail"]
        assert "10.03.2027" in r.json()["detail"]     # указано, где чинить

        r = manager_client.get("/api/schedule", params={"year": 2027, "month": 3})
        assert r.status_code == 409, r.text
        assert "не кратен 15" in r.json()["detail"]

        # Гант «Факт/Месяц» читает строки Табеля напрямую (без конвейера)
        r = manager_client.get("/api/fact/month", params={"year": 2027, "month": 3})
        assert r.status_code == 409, r.text
        assert "не кратен 15" in r.json()["detail"]
    finally:
        db.expire_all()
        db.execute(delete(TabelDay).where(
            TabelDay.employee_id == emp.id, TabelDay.date == d0))
        db.commit()


def test_ts3_domain_fmt_hours_stays_strict():
    """Домен НЕ смягчён: канонический ключ CFG-WINDOWS по-прежнему требует
    представимости (§3.3); послабление живёт только в отказе вкладок."""
    from app.modules.timesheet.domain.day_card.fmt_hours import fmt_hours
    with pytest.raises(ValueError):
        fmt_hours(50)
    assert fmt_hours(720) == "12" and fmt_hours(645) == "10,75"


def test_ts3_covers_window_raises_typed_error():
    row = TabelDay(employee_id=1, date=dt.date(2027, 3, 10), code="Я", plan_minutes=50)
    with pytest.raises(TimesheetRowCorruptError):
        covers_window(default_settings(), row, dt.date(2027, 3, 10),
                      dt.datetime(2027, 3, 10, 10, 0), dt.datetime(2027, 3, 10, 14, 0))


# ── P1-ts-4: доска — Settings месяца локального «сегодня» (16.2) ──────────────

def test_ts4_board_loads_settings_of_local_today_month(monkeypatch):
    db, ports = _stand()
    db.settings_by_period[(dt.date(2026, 11, 1), dt.date(2026, 11, 30))] = \
        dataclasses.replace(default_settings(), tz=ZoneInfo("Asia/Yekaterinburg"))

    loaded: list[Period] = []

    class RecSettings:
        def load(self, period):
            loaded.append(period)
            return db.settings_for(period)

    active_days: list[dt.date] = []

    class RecEmployment:
        def active_employees(self, on_day):
            active_days.append(on_day)
            return list(db.active)

    import app.modules.timesheet.application.presence_board as pb
    captured: dict = {}
    original = pb.assemble_board

    def spy(last_marks, shifts, absences, now, st):
        captured["st"] = st
        return original(last_marks, shifts, absences, now, st)

    monkeypatch.setattr(pb, "assemble_board", spy)
    ports2 = dataclasses.replace(ports, settings=RecSettings(),
                                 employment=RecEmployment())
    # 2026-10-31 22:30 UTC = 2026-11-01 01:30 МСК: граница месяцев
    now = dt.datetime(2026, 10, 31, 22, 30, tzinfo=dt.timezone.utc)
    pb.presence_board(now, ports2)

    # двухшаговое уточнение: месяц UTC-дня (узнать tz) → месяц локального «сегодня»
    assert loaded == [month_period(2026, 10), month_period(2026, 11)]
    assert active_days == [dt.date(2026, 11, 1)]       # «сегодня» — локальное
    assert captured["st"].tz == ZoneInfo("Asia/Yekaterinburg")   # версия ноября


def test_ts4_board_http_month_boundary_smoke(app_stack, db, freeze):
    """Смоук границы: версия справочников с 01.11 (tz Екатеринбург), запрос в
    2026-10-31 22:30 UTC — доска отвечает 200 и «сегодня» = 01.11.

    Вход — ВНУТРИ заморозки: сессия, выданная до freeze, на замороженной дате
    могла бы истечь (401), а герметичность к дате прогона важнее удобства."""
    from fastapi.testclient import TestClient

    from tests.conftest import DEMO_PASSWORD

    # payload версии — ПОЛНЫЙ документ (to_payload), а не только tz: from_payload
    # берёт категории/веса/дефолты из payload, частичный не проходит валидацию
    payload = {**to_payload(default_settings()), "tz": "Asia/Yekaterinburg"}
    ver = EngineSettingsVersion(valid_from=dt.date(2026, 11, 1),
                                payload_json=json.dumps(payload, ensure_ascii=False),
                                note="P1-ts-4 guard")
    db.add(ver)
    db.commit()
    try:
        with freeze("2026-10-31 22:30:00"):
            c = TestClient(app_stack["app"])
            login = c.post("/api/auth/login",
                           json={"username": "gromova", "password": DEMO_PASSWORD})
            assert login.status_code == 200, login.text
            r = c.get("/api/presence/board")
        assert r.status_code == 200, r.text
        assert r.json()["today"] == "2026-11-01"
    finally:
        db.expire_all()
        db.execute(delete(EngineSettingsVersion).where(
            EngineSettingsVersion.valid_from == dt.date(2026, 11, 1),
            EngineSettingsVersion.note == "P1-ts-4 guard"))
        db.commit()


# ── P1-ts-5: битый tz — ConfigError CFG-TZ (409 вкладки / 422 редактор) ───────

def test_ts5_from_payload_raises_config_error():
    with pytest.raises(ConfigError) as ei:
        from_payload({"tz": "Mars/Olympus"})
    assert ei.value.violations[0][0] == "CFG-TZ"


def test_ts5_bad_tz_in_stored_settings_is_409(manager_client, db):
    ver = EngineSettingsVersion(valid_from=dt.date(2027, 1, 1),
                                payload_json=json.dumps({"tz": "Mars/Olympus"}),
                                note="P1-ts-5 guard")
    db.add(ver)
    db.commit()
    try:
        r = manager_client.get("/api/mgmt", params={"year": 2027, "month": 1})
        assert r.status_code == 409, r.text          # раньше — 500 (KeyError)
        assert "CFG-TZ" in r.json()["detail"]
        assert "Mars/Olympus" in r.json()["detail"]  # текст указывает битое значение
    finally:
        db.expire_all()
        db.execute(delete(EngineSettingsVersion).where(
            EngineSettingsVersion.valid_from == dt.date(2027, 1, 1),
            EngineSettingsVersion.note == "P1-ts-5 guard"))
        db.commit()


def test_ts5_bad_tz_in_editor_is_422(admin_client):
    r = admin_client.put("/api/engine-settings", json={
        "valid_from": "2027-01-01", "payload": {"tz": "Mars/Olympus"},
        "note": "P1-ts-5 guard"})
    assert r.status_code == 422, r.text              # редактор валидирует ВВОД
    assert "CFG-TZ" in r.json()["detail"]


# ── P1-ts-6: deserialize без assert — типизированно, в т.ч. под python -O ─────

def test_ts6_deserialize_raises_typed_error_not_assert():
    with pytest.raises(StoredResultCorruptError):
        result_from_dict(json.loads(_corrupt_result_json("НЕСУЩЕСТВУЮЩИЙ")))


def test_ts6_deserialize_typed_error_under_python_o():
    """Под -O assert'ы вырезаются: прежняя проверка исчезала бы молча.
    Типизированная ошибка обязана бросаться в любом режиме."""
    script = (
        "import json, sys\n"
        "from app.modules.timesheet.interface.deserialize import result_from_dict\n"
        "from app.modules.timesheet.application.errors import StoredResultCorruptError\n"
        "assert not __debug__, 'ожидается режим -O'\n"
        "try:\n"
        "    result_from_dict(json.load(sys.stdin))\n"
        "except StoredResultCorruptError:\n"
        "    sys.exit(0)\n"
        "sys.exit(1)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-O", "-c", script], cwd=BASE,
        input=_corrupt_result_json("НЕСУЩЕСТВУЮЩИЙ"),
        capture_output=True, text=True, timeout=120,
        env={**os.environ, "DATABASE_URL": "sqlite:///:memory:",
             "SECRET_KEY": "test-secret-key"})
    assert proc.returncode == 0, proc.stderr


def test_ts6_http_corrupt_saved_result_shown_in_row_error(manager_client, db):
    """Вкладка «Управленческий табель»: битый сохранённый результат — ошибка в
    payload строки (200 + error, семантика _row), а не 500 на весь период."""
    emp = _ivanov(db)
    start, end = dt.date(2027, 2, 1), dt.date(2027, 2, 28)
    row = PeriodClosing(employee_id=emp.id, period_start=start, period_end=end,
                        revision=1, result_json=_corrupt_result_json("НЕСУЩЕСТВУЮЩИЙ"),
                        flags_json=json.dumps({"flags": []}))
    db.add(row)
    db.commit()
    try:
        r = manager_client.get("/api/mgmt", params={"year": 2027, "month": 2,
                                                    "employee_id": emp.id})
        assert r.status_code == 200, r.text
        error = r.json()["rows"][0]["error"]
        assert error and "повреждён" in error
        assert "Пересчитать" in error               # текст подсказывает выход
    finally:
        db.expire_all()
        db.execute(delete(PeriodClosing).where(
            PeriodClosing.employee_id == emp.id, PeriodClosing.period_start == start))
        db.commit()


# ── P1-ts-7: view_period — saved под проверкой ────────────────────────────────

def test_ts7_view_period_closed_without_saved_result(monkeypatch):
    """closed=True, но load_result вернул None (контракт порта — tuple | None):
    гонка с удалением или рассинхрон хранилища — типизированный отказ вместо
    слепого saved[0] → TypeError → 500."""
    db, ports = _stand()
    close_period(EMP, OCT, at(1, 0, month=11), ports)      # закрываем штатно
    monkeypatch.setattr(ports.store, "load_result", lambda employee_id, period: None)
    with pytest.raises(StoredResultCorruptError):
        view_period(EMP, OCT, at(5, 0, month=12), ports)
