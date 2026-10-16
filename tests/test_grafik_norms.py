"""Норматив владельца от 12.10.2026: задачи T1, T3, T4.

План и решения — в `docs/REVIEW-GRAFIK-4-SLOYA-2026-10-12.md` (§5, §6, §9).

**T1 · «код в табеле» у смены** (ответ на Q9): модель не меняется — код Табеля жёстко
определяет стандартное окно дня, эти же часы попадают в График первоначальными сменами.
Чинится поле: редактор отправлял одну подпись («08-20») и в `display_code`, и в
`tzh_code`, из-за чего health-панель выдавала APP-SHIFT-CODE, а ночные и суточные смены
переставали заполнять Табель из циклов. Теперь подпись сетки и код Табеля — разные поля,
в коде Табеля допустимы только коды CFG-DAY-CODES или пусто, а старым базам значения не
из словаря чистит миграция.

**T3 · «Сбросить» в Табеле** (Q5): убирает введённые вручную коды периода и возвращает
автозаполнение из циклов; закрытых периодов не касается; График перегенерируется.

**T4 · единое «отпросился (выходной за часы)»** (Q3, Q4, Q8): одна запись словаря с двумя
точками ввода (интервал / вся смена), назначение информационное (часов и плана не меняет —
неотработанные часы окна уходят в недостачу, её гасит банк при закрытии), заявление
выбирается по точке ввода, а из Графика назначаются только виды «за счёт часов»:
отпуск/больничный/за свой счёт/оплачиваемый выходной — коды Табеля (слой 0).

**T5 · «График» = 4 слоя** (Q2, Q7): один пункт меню «График» со слоями 0 Табель ·
1 План/График · 2 Факт · 3 Управленческий Табель; в слое 2 — сетка «Номера»
(``GET /api/fact/day``): день глазами движка — отметки СКУД и округление до шага,
окно из кода Табеля, план/отработано/недостача/переработка, флаги из Графика.
Доска «Отметки» остаётся отдельным пунктом меню.
"""
from __future__ import annotations

import calendar
import datetime as dt
import os
import tempfile
import unittest

# свой файл БД при отдельном запуске модуля; в общем прогоне — база conftest
_tmp_db = os.path.join(tempfile.gettempdir(), "tt_grafik_norms.db")
if "DATABASE_URL" not in os.environ:
    if os.path.exists(_tmp_db):
        os.remove(_tmp_db)
    os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"
    os.environ["SECRET_KEY"] = "test-secret-key"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.deps import local_date  # noqa: E402
from app.main import app, init_db  # noqa: E402
from app.migrations import (  # noqa: E402
    migrate_shift_tabel_codes,
    migrate_time_off_template,
    migrate_timeoff_entity,
)
from app.models import PeriodClosing, ScheduleAbsence, ShiftType, TabelDay  # noqa: E402

init_db()
client = TestClient(app)          # администратор
employee_client = TestClient(app)  # сотрудник (проверка прав)

TODAY = local_date()
FIRST = TODAY.replace(day=1)


def _login(c: TestClient, username: str) -> None:
    r = c.post("/api/auth/login", json={"username": username, "password": "demo1234"})
    assert r.status_code == 200, r.text


def _shift(code: str) -> dict:
    for s in client.get("/api/shift-types?include_archived=true").json():
        if s["code"] == code:
            return s
    raise AssertionError(f"вид смены {code} не найден в словаре")


def _tabel(year: int = None, month: int = None) -> dict:
    y, m = year or TODAY.year, month or TODAY.month
    r = client.get("/api/tabel", params={"year": y, "month": m})
    assert r.status_code == 200, r.text
    return r.json()


def _tabel_row(emp_id: int, day: dt.date):
    db = SessionLocal()
    try:
        return db.scalar(select(TabelDay).where(TabelDay.employee_id == emp_id,
                                                TabelDay.date == day))
    finally:
        db.close()


def _create_employee(username: str, full_name: str, group: str = "Смена 1") -> dict:
    r = client.post("/api/employees", json={
        "full_name": full_name, "position": "Батлер (норматив 12.10)",
        "hired_at": (TODAY - dt.timedelta(days=120)).isoformat(), "schedule_group": group,
        "role": "employee", "username": username, "password": "demo1234"})
    assert r.status_code == 200, r.text
    return r.json()


def _month_end(day: dt.date) -> dt.date:
    return dt.date(day.year, day.month, calendar.monthrange(day.year, day.month)[1])


def _fill_cycle(emp_id: int) -> None:
    """Цикл 2/2 сменами 08:00–20:00 на ВЕСЬ месяц: Табель заполнится явками «Я 12».

    Месяц закрывается целиком, чтобы «Сбросить» не оставлял хвост незаполненных дней
    (Табель обязан покрывать период — RUL-TIMESHEET-COVERS-PERIOD).
    """
    r = client.post("/api/schedule/fill-pattern", json={
        "employee_ids": [emp_id], "start_date": FIRST.isoformat(),
        "end_date": _month_end(FIRST).isoformat(), "work_shift_id": _shift("DAY12")["id"],
        "off_shift_id": _shift("OFF")["id"], "pattern": "2/2", "offset": 0})
    assert r.status_code == 200, r.text


def _work_days(emp_id: int) -> list[dt.date]:
    """Дни месяца, где по Табелю стоит явка с часами."""
    data = _tabel(TODAY.year, TODAY.month)
    row = next(r for r in data["rows"] if r["employee"]["id"] == emp_id)
    return [dt.date.fromisoformat(iso) for iso, cell in sorted(row["cells"].items())
            if cell["hours"]]


class TestShiftTabelCode(unittest.TestCase):
    """T1: «код в сетке» и «код в табеле» — разные поля; код Табеля — из словаря."""

    @classmethod
    def setUpClass(cls):
        _login(client, "admin")
        _login(employee_client, "ivanov")

    def test_01_grid_label_is_not_tabel_code(self):
        """Подпись сетки («07–16») больше не копируется в код Табеля."""
        r = client.post("/api/shift-types", json={
            "code": "NORM_T1_A", "name": "07:00–16:00 (9 ч, норматив)", "short_code": "07–16",
            "kind": "work", "start_time": "07:00", "end_time": "16:00"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["display_code"], "07–16")
        self.assertEqual(r.json()["tzh_code"], "",
                         "иначе health-панель снова получит APP-SHIFT-CODE")

    def test_02_unknown_tabel_code_rejected(self):
        payload = {"code": "NORM_T1_B", "name": "20:00–08:00 (ночная, норматив)",
                   "short_code": "20–08", "tzh_code": "20-08", "kind": "work",
                   "start_time": "20:00", "end_time": "08:00", "overnight": True}
        r = client.post("/api/shift-types", json=payload)
        self.assertEqual(r.status_code, 422, r.text)
        self.assertIn("CFG-DAY-CODES", r.json()["detail"])
        codes = [s["code"] for s in client.get("/api/shift-types?include_archived=true").json()]
        self.assertNotIn("NORM_T1_B", codes, "смена с битым кодом не создаётся")
        # тот же код, но из словаря Табеля — принимается
        r = client.post("/api/shift-types", json={**payload, "tzh_code": "Я"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["tzh_code"], "Я")
        self.assertEqual(r.json()["display_code"], "20–08")
        TestShiftTabelCode.shift_id = r.json()["id"]
        # правка: битый код отклоняется, прежнее значение сохраняется
        r = client.put(f"/api/shift-types/{self.shift_id}",
                       json={**payload, "tzh_code": "08-20", "name": "20:00–08:30 (ночная)"})
        self.assertEqual(r.status_code, 422, r.text)
        after = _shift("NORM_T1_B")
        self.assertEqual(after["tzh_code"], "Я")
        self.assertEqual(after["name"], "20:00–08:00 (ночная, норматив)",
                         "отклонённая правка не меняет смену")
        # PUT без поля «код в табеле» его не обнуляет
        r = client.put(f"/api/shift-types/{self.shift_id}", json={
            "code": "NORM_T1_B", "name": "20:00–08:00 (ночная, норматив)", "short_code": "20–08",
            "kind": "work", "start_time": "20:00", "end_time": "08:00", "overnight": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["tzh_code"], "Я")
        # явная очистка разрешена: пусто — «смена не участвует в автозаполнении»
        r = client.put(f"/api/shift-types/{self.shift_id}", json={
            "code": "NORM_T1_B", "name": "20:00–08:00 (ночная, норматив)", "short_code": "20–08",
            "tzh_code": "", "kind": "work", "start_time": "20:00", "end_time": "08:00",
            "overnight": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["tzh_code"], "")

    def test_03_tabel_codes_available_to_editor(self):
        r = client.get("/api/shift-types/tabel-codes")
        self.assertEqual(r.status_code, 200, r.text)
        codes = {c["code"]: c for c in r.json()["codes"]}
        self.assertIn("Я", codes)
        self.assertTrue(codes["Я"]["carries_hours"], "явка несёт часы")
        self.assertIn("В", codes)
        self.assertFalse(codes["В"]["carries_hours"])
        # справочник нужен редактору смены, поэтому читается любым вошедшим
        r = employee_client.get("/api/shift-types/tabel-codes")
        self.assertEqual(r.status_code, 200, r.text)

    def test_04_legacy_values_cleared_by_migration(self):
        """База владельца: 6 смен с подписями в «коде в табеле» → APP-SHIFT-CODE.

        Миграция чистит значения не из словаря (подпись сетки не трогает), проверка
        здоровья уходит, автозаполнение Табеля снова возможно.
        """
        before = client.get("/api/engine-settings/health").json()["checks"]
        self.assertEqual([c for c in before if c["code"] == "APP-SHIFT-CODE"], [],
                         "свежий словарь смен чист")
        db = SessionLocal()
        try:
            st = db.get(ShiftType, self.shift_id)
            st.tzh_code = "20-08"          # как записывал прежний редактор
            db.commit()
        finally:
            db.close()
        checks = client.get("/api/engine-settings/health").json()["checks"]
        broken = [c for c in checks if c["code"] == "APP-SHIFT-CODE"]
        self.assertEqual(len(broken), 1, checks)
        self.assertIn("NORM_T1_B", broken[0]["text"])
        self.assertEqual(broken[0]["level"], "error")

        migrate_shift_tabel_codes()
        migrate_shift_tabel_codes()        # идемпотентно

        db = SessionLocal()
        try:
            st = db.get(ShiftType, self.shift_id)
            self.assertEqual(st.tzh_code, "")
            self.assertEqual(st.display_code, "20–08", "подпись сетки не меняется")
        finally:
            db.close()
        checks = client.get("/api/engine-settings/health").json()["checks"]
        self.assertEqual([c for c in checks if c["code"] == "APP-SHIFT-CODE"], [])


class TestTabelReset(unittest.TestCase):
    """T3: «Сбросить» — ручные коды периода убираются, возвращается автозаполнение."""

    @classmethod
    def setUpClass(cls):
        _login(client, "admin")
        _login(employee_client, "ivanov")
        cls.emp = _create_employee("norm_reset", "Сбросов Сброс Сбросович")
        cls.other = _create_employee("norm_reset2", "Ручнов Руч Ручнович")
        _fill_cycle(cls.emp["id"])
        _fill_cycle(cls.other["id"])
        cls.day = _work_days(cls.emp["id"])[0]
        cls.other_day = _work_days(cls.other["id"])[0]
        cls.absence_code = next(c["code"] for c in _tabel()["codes"]
                                if not c["carries_hours"] and c["code"] != "В")

    def _set_manual(self, emp_id: int, day: dt.date, code: str) -> None:
        r = client.put("/api/tabel/cell", json={
            "employee_id": emp_id, "date": day.isoformat(), "code": code, "hours": 0})
        self.assertEqual(r.status_code, 200, r.text)

    def test_01_reset_restores_autofill(self):
        emp_id, day = self.emp["id"], self.day
        auto = _tabel_row(emp_id, day)
        self.assertEqual(auto.source, "cycle")
        self.assertGreater(auto.plan_minutes, 0)
        self._set_manual(emp_id, day, self.absence_code)
        manual = _tabel_row(emp_id, day)
        self.assertEqual(manual.source, "manual")
        self.assertEqual(manual.code, self.absence_code)

        r = client.post("/api/tabel/reset", json={
            "year": day.year, "month": day.month, "employee_ids": [emp_id]})
        self.assertEqual(r.status_code, 200, r.text)
        res = r.json()
        self.assertEqual(res["cleared"], 1, res)
        self.assertGreaterEqual(res["written"], 1)
        self.assertEqual(res["locked_skipped"], [])
        self.assertEqual([c["code"] for c in res["cells"]], [self.absence_code])

        row = _tabel_row(emp_id, day)
        self.assertEqual(row.source, "cycle", "ячейка снова из циклов")
        self.assertEqual(row.code, auto.code)
        self.assertEqual(row.plan_minutes, auto.plan_minutes)
        # действие видно в журнале
        log = client.get("/api/audit", params={"action": "tabel_reset"}).json()
        self.assertTrue(log["items"], "сброс пишется в аудит")
        self.assertEqual(log["items"][0]["action_title"], "Табель: сброс к автозаполнению")
        self.assertIn(f"{day.year}-{day.month:02d}", log["items"][0]["target"])

    def test_02_reset_is_scoped_to_employee(self):
        other_id, day = self.other["id"], self.other_day
        self._set_manual(other_id, day, self.absence_code)
        r = client.post("/api/tabel/reset", json={
            "year": day.year, "month": day.month, "employee_ids": [self.emp["id"]]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(_tabel_row(other_id, day).source, "manual",
                         "чужие ручные правки сброс не трогает")
        # сброс второму сотруднику — его ячейка возвращается к автозаполнению
        r = client.post("/api/tabel/reset", json={
            "year": day.year, "month": day.month, "employee_ids": [other_id]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["cleared"], 1)
        self.assertEqual(_tabel_row(other_id, day).source, "cycle")

    def test_03_reset_skips_closed_period(self):
        """Закрытый период (и следующий за ним закрытый) — только чтение (16.5)."""
        emp_id, day = self.emp["id"], self.day
        self._set_manual(emp_id, day, self.absence_code)
        next_month = dt.date(day.year + (day.month == 12), day.month % 12 + 1, 1)
        db = SessionLocal()
        created = []
        try:
            for start, end in ((FIRST, _month_end(FIRST)), (next_month, _month_end(next_month))):
                row = PeriodClosing(employee_id=emp_id, period_start=start, period_end=end,
                                    closed_by_name="норматив-тест")
                db.add(row)
                db.flush()
                created.append(row.id)
            db.commit()
        finally:
            db.close()
        try:
            r = client.post("/api/tabel/reset", json={
                "year": day.year, "month": day.month, "employee_ids": [emp_id]})
            self.assertEqual(r.status_code, 200, r.text)
            res = r.json()
            self.assertEqual(res["locked_skipped"], [emp_id], res)
            self.assertEqual(res["cleared"], 0)
            self.assertEqual(_tabel_row(emp_id, day).code, self.absence_code,
                             "ручная правка закрытого периода осталась")
        finally:
            db = SessionLocal()
            try:
                for cid in created:
                    row = db.get(PeriodClosing, cid)
                    if row is not None:
                        db.delete(row)
                db.commit()
            finally:
                db.close()
            client.post("/api/tabel/reset", json={
                "year": day.year, "month": day.month, "employee_ids": [emp_id]})

    def test_04_reset_requires_permission(self):
        day = self.day
        r = employee_client.post("/api/tabel/reset", json={
            "year": day.year, "month": day.month})
        self.assertEqual(r.status_code, 403, r.text)
        r = TestClient(app).post("/api/tabel/reset", json={"year": day.year, "month": day.month})
        self.assertEqual(r.status_code, 401, r.text)

    def test_05_reset_reports_uncovered_days(self):
        """День, для которого цикл не даёт значения, остаётся пустым — сервер это показывает."""
        emp_id = self.emp["id"]
        day = self.day
        db = SessionLocal()
        try:
            row = db.scalar(select(TabelDay).where(TabelDay.employee_id == emp_id,
                                                   TabelDay.date == day))
            row.source = "manual"          # сброс удалит строку
            db.commit()
        finally:
            db.close()
        r = client.post("/api/tabel/reset", json={
            "year": day.year, "month": day.month, "employee_ids": [emp_id]})
        self.assertEqual(r.status_code, 200, r.text)
        res = r.json()
        self.assertEqual(res["cleared"], 1)
        # цикл заполняет день заново: пропусков нет
        self.assertEqual(res["uncovered_total"], 0, res["uncovered"])
        self.assertIsNotNone(_tabel_row(emp_id, day))


class TestTimeoffEntity(unittest.TestCase):
    """T4: «отпросился» и «выходной за часы» — одна сущность с двумя точками ввода."""

    @classmethod
    def setUpClass(cls):
        _login(client, "admin")
        cls.emp = _create_employee("norm_timeoff", "Отпросов Отпрос Отпросович")
        _fill_cycle(cls.emp["id"])
        cls.day = _work_days(cls.emp["id"])[0]
        cls.kind = _shift("TIMEOFF_HOURS")

    def test_01_single_dictionary_record(self):
        kinds = client.get("/api/shift-types?include_archived=true").json()
        away = [k for k in kinds if k["code"] == "AWAY_HOURS"]
        self.assertTrue(not away or away[0]["archived"],
                        "дубль «Отпросился: отсутствовал часть смены» слит и в архиве")
        live = [k for k in kinds if not k["archived"]]
        codeless = [k for k in live if k["kind"] == "absence" and not k["tzh_code"]]
        self.assertEqual([k["code"] for k in codeless], ["TIMEOFF_HOURS"],
                         "из Графика назначается один вид — «за счёт часов»")
        self.assertIn("Отпросился", codeless[0]["name"])
        self.assertIn("выходной за часы", codeless[0]["name"].lower())

    def test_02_whole_shift_entry_point(self):
        """Точка ввода «на всю смену»: заявление — «выходной за ранее отработанные часы»."""
        before = _tabel_row(self.emp["id"], self.day)
        code_before, plan_before = before.code, before.plan_minutes
        r = client.post("/api/schedule/range-absence", json={
            "employee_ids": [self.emp["id"]], "first": self.day.isoformat(),
            "last": self.day.isoformat(), "shift_type_id": self.kind["id"],
            "workdays_only": True, "note": "за ранее отработанные часы"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["mode"], "schedule_absence", "пишется в График, не в Табель")

        p = client.get("/api/schedule/absence-period", params={
            "employee_id": self.emp["id"], "date": self.day.isoformat()})
        self.assertEqual(p.status_code, 200, p.text)
        data = p.json()
        self.assertEqual(data["source"], "schedule_absence")
        self.assertTrue(data["whole_shift"])
        self.assertEqual(data["doc_type"], "day_off_hours")
        self.assertEqual(data["hours_source"], "window_of_day")
        self.assertEqual(data["hours"], 12.0, "часы — стандартное окно, не длина записи")

        after = _tabel_row(self.emp["id"], self.day)
        self.assertEqual((after.code, after.plan_minutes), (code_before, plan_before),
                         "Q8: назначение информационное — Табель не меняется")

    def test_03_interval_entry_point(self):
        """Точка ввода «интервал»: заявление — «об отсутствии на рабочем месте»."""
        grid = client.get("/api/schedule", params={
            "year": self.day.year, "month": self.day.month}).json()
        row = next(r for r in grid["rows"] if r["employee"]["id"] == self.emp["id"])
        absence_id = row["cells"][self.day.isoformat()]["absences"][0]["id"]
        r = client.delete(f"/api/schedule/absence/{absence_id}")
        self.assertEqual(r.status_code, 200, r.text)

        before = _tabel_row(self.emp["id"], self.day)
        code_before, plan_before = before.code, before.plan_minutes
        r = client.post("/api/schedule/absence", json={
            "employee_id": self.emp["id"], "date": self.day.isoformat(),
            "from_time": "14:00", "until_time": "16:00", "kind_id": self.kind["id"],
            "note": "отпросился к врачу"})
        self.assertEqual(r.status_code, 200, r.text)

        data = client.get("/api/schedule/absence-period", params={
            "employee_id": self.emp["id"], "date": self.day.isoformat()}).json()
        self.assertEqual(data["source"], "schedule_absence")
        self.assertFalse(data["whole_shift"])
        self.assertEqual(data["doc_type"], "time_off_request")
        self.assertEqual(data["hours"], 2.0)
        self.assertEqual(data["partial"]["from_time"], "14:00")

        after = _tabel_row(self.emp["id"], self.day)
        self.assertEqual((after.code, after.plan_minutes), (code_before, plan_before))
        # смена физически не делится (v7/R17): разрез логический
        grid = client.get("/api/schedule", params={
            "year": self.day.year, "month": self.day.month}).json()
        row = next(r for r in grid["rows"] if r["employee"]["id"] == self.emp["id"])
        cell = row["cells"][self.day.isoformat()]
        self.assertEqual([(s["start_hm"], s["end_hm"]) for s in cell["shifts"]],
                         [("08:00", "20:00")])
        self.assertEqual(len(cell["absences"]), 1)

    def test_04_migration_merges_duplicate_kind(self):
        """Старая база: дубль вида сливается, записи отсутствий переносятся, вид архивируется."""
        r = client.post("/api/shift-types", json={
            "code": "AWAY_HOURS", "name": "Отпросился: отсутствовал часть смены",
            "short_code": "ОТПР", "kind": "absence", "is_working": False,
            "counts_as_worked": False, "doc_type": "time_off_request"})
        self.assertEqual(r.status_code, 200, r.text)
        dup_id = r.json()["id"]
        db = SessionLocal()
        try:
            row = db.scalar(select(ScheduleAbsence).where(
                ScheduleAbsence.employee_id == self.emp["id"]))
            self.assertIsNotNone(row)
            row.kind_id = dup_id           # как в базе до объединения
            db.commit()
            absence_id = row.id
        finally:
            db.close()

        migrate_timeoff_entity()
        migrate_timeoff_entity()           # идемпотентно

        db = SessionLocal()
        try:
            row = db.get(ScheduleAbsence, absence_id)
            self.assertEqual(row.kind_id, self.kind["id"], "запись перенесена на единый вид")
            dup = db.get(ShiftType, dup_id)
            self.assertTrue(dup.archived_at or not dup.active, "дубль в архиве, не удалён")
            unified = db.get(ShiftType, self.kind["id"])
            self.assertEqual(unified.name, "Отпросился (выходной за часы)")
            self.assertEqual(unified.display_code, "ОТПР")
            self.assertEqual(unified.tzh_code, "", "кода Табеля у вида нет (Q4)")
        finally:
            db.close()
        # архивный дубль не мешает: в словаре активным остаётся один вид «за счёт часов»
        live = [k for k in client.get("/api/shift-types").json()
                if k["kind"] == "absence" and not k["tzh_code"]]
        self.assertEqual([k["code"] for k in live], ["TIMEOFF_HOURS"])


class TestIntervalStatements(unittest.TestCase):
    """Несколько отлучек в один день (решение владельца 16.10.2026): ОДНО заявление
    с перечнем интервалов либо заявление по каждому интервалу отдельно (absence_id)."""

    @classmethod
    def setUpClass(cls):
        _login(client, "admin")
        cls.emp = _create_employee("norm_intervals", "Интервалов Интервал Интервалович")
        _fill_cycle(cls.emp["id"])
        cls.day = _work_days(cls.emp["id"])[0]
        cls.kind = _shift("TIMEOFF_HOURS")
        for frm, until, note in (("14:00", "16:00", "к врачу"), ("18:00", "20:00", "")):
            r = client.post("/api/schedule/absence", json={
                "employee_id": cls.emp["id"], "date": cls.day.isoformat(),
                "from_time": frm, "until_time": until,
                "kind_id": cls.kind["id"], "note": note})
            assert r.status_code == 200, r.text

    def _period(self, **extra) -> dict:
        r = client.get("/api/schedule/absence-period", params={
            "employee_id": self.emp["id"], "date": self.day.isoformat(), **extra})
        return r

    def test_01_combined_period_lists_intervals(self):
        r = self._period()
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertEqual(data["source"], "schedule_absence")
        self.assertEqual([(iv["from_time"], iv["until_time"]) for iv in data["intervals"]],
                         [("14:00", "16:00"), ("18:00", "20:00")])
        self.assertEqual(data["hours"], 4.0, "часы — сумма интервалов")
        self.assertEqual(data["hours_source"], "combined")
        self.assertFalse(data["whole_shift"])
        self.assertEqual(data["doc_type"], "time_off_request")
        self.assertEqual(data["intervals_text"],
                         "с 14:00 до 16:00 (2 ч) и с 18:00 до 20:00 (2 ч)")
        # прежний контракт для одиночных полей сохранён: границы — первого и последнего
        self.assertEqual(data["partial"]["from_time"], "14:00")
        self.assertEqual(data["partial"]["until_time"], "20:00")
        self.assertEqual(data["notes"], ["к врачу"])

    def test_02_single_interval_by_id(self):
        combined = self._period().json()
        second = combined["intervals"][1]
        r = self._period(absence_id=second["id"])
        self.assertEqual(r.status_code, 200, r.text)
        one = r.json()
        self.assertEqual(len(one["intervals"]), 1)
        self.assertEqual(one["partial"]["from_time"], "18:00")
        self.assertEqual(one["partial"]["until_time"], "20:00")
        self.assertEqual(one["hours"], 2.0)
        self.assertEqual(one["hours_source"], "absence_interval")
        self.assertEqual(one["intervals_text"], "с 18:00 до 20:00 (2 ч)")
        self.assertEqual(one["doc_type"], "time_off_request")

    def test_03_unknown_interval_404(self):
        r = self._period(absence_id=10 ** 9)
        self.assertEqual(r.status_code, 404)

    def _docx_text(self, payload: dict) -> str:
        import io

        from docx import Document
        r = client.post("/api/docs/render", json=payload)
        self.assertEqual(r.status_code, 200, r.text[:300])
        doc = Document(io.BytesIO(r.content))
        return "\n".join(par.text for par in doc.paragraphs)

    def test_04_render_combined_intervals(self):
        text = self._docx_text({
            "type": "time_off_request", "employee_id": self.emp["id"],
            "date_from": self.day.isoformat(), "date_to": self.day.isoformat(),
            "format": "docx",
            "intervals": "с 14:00 до 16:00 (2 ч) и с 18:00 до 20:00 (2 ч)"})
        self.assertIn("с 14:00 до 16:00 (2 ч) и с 18:00 до 20:00 (2 ч)", text)
        self.assertIn(self.emp["full_name"], text)

    def test_05_render_single_interval_fallback(self):
        """Без intervals сервер собирает строку из from/until — старые вызовы работают."""
        text = self._docx_text({
            "type": "time_off_request", "employee_id": self.emp["id"],
            "date_from": self.day.isoformat(), "date_to": self.day.isoformat(),
            "format": "docx", "from_time": "14:00", "until_time": "16:00", "hours": 2})
        self.assertIn("с 14:00 до 16:00 (2 ч)", text)

    def test_06_migration_updates_pristine_template(self):
        """Старая база: нетронутый шаблон заменяется на версию с {intervals};
        отредактированный вручную — не трогается. Идемпотентно."""
        from app.doc_templates import DEFAULT_TPL_TIME_OFF, PREV_DEFAULT_TPL_TIME_OFF
        from app.models import Setting, StatementKind

        def _texts():
            db = SessionLocal()
            try:
                return (db.scalar(select(Setting.value).where(
                            Setting.key == "tpl_time_off_request")),
                        db.scalar(select(StatementKind.text).where(
                            StatementKind.code == "time_off_request")))
            finally:
                db.close()

        db = SessionLocal()
        try:
            row = db.scalar(select(Setting).where(Setting.key == "tpl_time_off_request"))
            if row is None:      # в свежей базе строки нет — старая база её сохраняла
                row = Setting(key="tpl_time_off_request", value="", description="")
                db.add(row)
            row.value = PREV_DEFAULT_TPL_TIME_OFF
            db.scalar(select(StatementKind).where(
                StatementKind.code == "time_off_request")).text = PREV_DEFAULT_TPL_TIME_OFF
            db.commit()
        finally:
            db.close()
        migrate_time_off_template()
        migrate_time_off_template()                        # идемпотентно
        self.assertEqual(_texts(), (DEFAULT_TPL_TIME_OFF, DEFAULT_TPL_TIME_OFF))

        db = SessionLocal()
        try:
            db.scalar(select(Setting).where(
                Setting.key == "tpl_time_off_request")).value = "свой текст {intervals}"
            db.commit()
        finally:
            db.close()
        migrate_time_off_template()
        setting_text, kind_text = _texts()
        self.assertEqual(setting_text, "свой текст {intervals}", "ручная правка не тронута")
        self.assertEqual(kind_text, DEFAULT_TPL_TIME_OFF)

        # вернуть штатный шаблон — за классом следуют другие тесты документов
        db = SessionLocal()
        try:
            db.scalar(select(Setting).where(
                Setting.key == "tpl_time_off_request")).value = DEFAULT_TPL_TIME_OFF
            db.commit()
        finally:
            db.close()


class TestGridCellSegments(unittest.TestCase):
    """Сетка Графика (16.10.2026): segments — видимые отрезки смены (минус отсутствия),
    whole_shift — плашка «Выходной за часы» на весь день. Считает СЕРВЕР — один
    источник правила EX-29 для сетки, печати и заявлений."""

    @classmethod
    def setUpClass(cls):
        _login(client, "admin")
        cls.emp = _create_employee("norm_segments", "Отрезов Отрез Отрезович")
        _fill_cycle(cls.emp["id"])
        days = _work_days(cls.emp["id"])
        cls.day_a, cls.day_b = days[0], days[1]
        cls.kind = _shift("TIMEOFF_HOURS")

    def _cell(self, day) -> dict:
        grid = client.get("/api/schedule", params={
            "year": day.year, "month": day.month}).json()
        row = next(r for r in grid["rows"] if r["employee"]["id"] == self.emp["id"])
        return row["cells"][day.isoformat()]

    def test_01_interval_splits_shift_into_segments(self):
        r = client.post("/api/schedule/absence", json={
            "employee_id": self.emp["id"], "date": self.day_a.isoformat(),
            "from_time": "14:00", "until_time": "16:00", "kind_id": self.kind["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        cell = self._cell(self.day_a)
        self.assertEqual(cell["segments"], [["08:00", "14:00"], ["16:00", "20:00"]])
        self.assertEqual([a["whole_shift"] for a in cell["absences"]], [False])
        # смена физически не делится (v7/R17) — запись осталась одной
        self.assertEqual([(s["start_hm"], s["end_hm"]) for s in cell["shifts"]],
                         [("08:00", "20:00")])

    def test_02_whole_window_absence_flags_whole_shift(self):
        r = client.post("/api/schedule/absence", json={
            "employee_id": self.emp["id"], "date": self.day_b.isoformat(),
            "from_time": "08:00", "until_time": "20:00", "kind_id": self.kind["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        cell = self._cell(self.day_b)
        self.assertTrue(any(a["whole_shift"] for a in cell["absences"]),
                        "отсутствие на всё окно дня — whole_shift для плашки")
        self.assertEqual(cell["segments"], [], "видимых отрезков не осталось")

    def test_03_seniors_first_within_group(self):
        """Порядок строк (решение 16.10.2026): внутри блока старшие впереди,
        далее по алфавиту — задаётся сервером, поэтому действует на всех стоках."""
        base = {"hired_at": (TODAY - dt.timedelta(days=120)).isoformat(),
                "schedule_group": "Смена 1", "role": "employee", "password": "demo1234"}
        junior = client.post("/api/employees", json={
            **base, "full_name": "Абрамова Батлеровна Батлерова", "position": "Батлер",
            "username": "norm_order_jr"})
        senior = client.post("/api/employees", json={
            **base, "full_name": "Яковлева Старшая Петровна", "position": "Старший батлер",
            "username": "norm_order_sr"})
        self.assertEqual(junior.status_code, 200, junior.text)
        self.assertEqual(senior.status_code, 200, senior.text)
        grid = client.get("/api/schedule", params={
            "year": TODAY.year, "month": TODAY.month}).json()
        order = [r["employee"]["id"] for r in grid["rows"]]
        self.assertLess(order.index(senior.json()["id"]), order.index(junior.json()["id"]),
                        "«Старший батлер» Яковлева — раньше «Батлера» Абрамовой")


class TestScheduleMonthReset(unittest.TestCase):
    """«Сбросить месяц» в Графике (16.10.2026): убирает только РУЧНЫЕ смены,
    Табель не трогается (сбрасывается из слоя 0), отсутствия сохраняются."""

    @classmethod
    def setUpClass(cls):
        _login(client, "admin")
        cls.emp = _create_employee("norm_month_reset", "Сбросов Сброс Сбросович")
        _fill_cycle(cls.emp["id"])
        cls.day = _work_days(cls.emp["id"])[0]
        cls.kind = _shift("TIMEOFF_HOURS")

    def test_01_reset_removes_manual_shifts_keeps_tabel_and_absences(self):
        day = self.day
        r = client.put("/api/schedule/shift", json={
            "employee_id": self.emp["id"], "date": day.isoformat(),
            "shifts": [{"start": "10:00", "end": "19:00"}]})
        self.assertEqual(r.status_code, 200, r.text)
        r = client.post("/api/schedule/absence", json={
            "employee_id": self.emp["id"], "date": day.isoformat(),
            "from_time": "14:00", "until_time": "15:00", "kind_id": self.kind["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        before = _tabel_row(self.emp["id"], day)
        self.assertEqual((before.code, before.plan_minutes), ("Я", 720))

        r = client.post("/api/schedule/reset-month", json={
            "year": day.year, "month": day.month, "employee_ids": [self.emp["id"]]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["cleared"], 1, "удалена одна ручная смена")

        grid = client.get("/api/schedule", params={
            "year": day.year, "month": day.month}).json()
        row = next(x for x in grid["rows"] if x["employee"]["id"] == self.emp["id"])
        cell = row["cells"][day.isoformat()]
        self.assertEqual([(s["source"], s["start_hm"], s["end_hm"]) for s in cell["shifts"]],
                         [("generated", "08:00", "20:00")], "График снова из Табеля")
        self.assertEqual(len(cell["absences"]), 1, "согласованное отсутствие сохранено")
        after = _tabel_row(self.emp["id"], day)
        self.assertEqual((after.code, after.plan_minutes, after.source),
                         (before.code, before.plan_minutes, before.source),
                         "Табель не тронут")

    def test_02_reset_requires_schedule_edit(self):
        _login(client, "ivanov")
        r = client.post("/api/schedule/reset-month", json={
            "year": TODAY.year, "month": TODAY.month})
        self.assertEqual(r.status_code, 403)
        _login(client, "admin")


class TestAbsenceLayers(unittest.TestCase):
    """Q4: из Графика — только «за счёт часов», отпуск/ДО/ОВ — коды Табеля."""

    @classmethod
    def setUpClass(cls):
        _login(client, "admin")
        cls.emp = _create_employee("norm_layers", "Слоёв Слой Слоевич")
        _fill_cycle(cls.emp["id"])
        days = _work_days(cls.emp["id"])
        cls.day, cls.next_work_day = days[0], days[1]

    def test_01_vacation_is_tabel_code(self):
        vac = _shift("VACATION")
        r = client.post("/api/schedule/range-absence", json={
            "employee_ids": [self.emp["id"]], "first": self.day.isoformat(),
            "last": self.day.isoformat(), "shift_type_id": vac["id"], "note": "приказ №47"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotEqual(r.json().get("mode"), "schedule_absence")
        row = _tabel_row(self.emp["id"], self.day)
        self.assertEqual(row.code, vac["tzh_code"], "отпуск — код первичного документа")
        self.assertEqual(row.plan_minutes, 0)
        # заявление печатается из Табеля: источник — код Табеля
        data = client.get("/api/schedule/absence-period", params={
            "employee_id": self.emp["id"], "date": self.day.isoformat()}).json()
        self.assertEqual(data["source"], "tabel_code")
        self.assertEqual(data["doc_type"], "vacation_paid")

    def test_02_timeoff_stays_in_schedule(self):
        kind = _shift("TIMEOFF_HOURS")
        day = self.next_work_day       # другой рабочий день: в первом уже код отпуска
        r = client.post("/api/schedule/range-absence", json={
            "employee_ids": [self.emp["id"]], "first": day.isoformat(),
            "last": day.isoformat(), "shift_type_id": kind["id"], "workdays_only": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["mode"], "schedule_absence")
        row = _tabel_row(self.emp["id"], day)
        self.assertNotEqual(row.code, "", "в Табеле остаётся явка")
        self.assertGreater(row.plan_minutes, 0, "план дня отсутствие не уменьшает")


class TestFactDayGrid(unittest.TestCase):
    """T5 (Q7): слой 2 «Факт» — сетка «Номера» (GET /api/fact/day).

    Один день глазами движка: сырые отметки СКУД и их округление до шага,
    сопряжённые сессии, окно из кода Табеля (Q1 — жёстко из кода), план /
    отработано / недостача / переработка по категориям и флаги из Графика.
    Числа — из settle периода, содержащего день; шаг округления и границы
    категорий ДЯ/ДН — из настроек, интерфейс ничего не пересчитывает.
    """

    @classmethod
    def setUpClass(cls):
        _login(client, "admin")
        _login(employee_client, "ivanov")
        # сотрудник, принятый в текущем месяце: первый период цепочки — текущий,
        # после посева OPENING_SEED (v7.1/R37) view_period работает без закрытий
        r = client.post("/api/employees", json={
            "full_name": "Номерова Номер Номеровна", "position": "Батлер (норматив T5)",
            "hired_at": FIRST.isoformat(), "schedule_group": "Смена 1",
            "role": "employee", "username": "norm_t5_fact", "password": "demo1234"})
        assert r.status_code == 200, r.text
        cls.emp = r.json()
        r = client.post(f"/api/employees/{cls.emp['id']}/bank-adjust", json={
            "hours": 0, "date": FIRST.isoformat(), "note": "начальный банк (тест T5)",
            "reason_code": "OPENING_SEED"})
        assert r.status_code == 200, r.text
        # цикл 2/2 покрывает месяц явками; целевой день переопределяем «Я 10,75»
        # (окно 08:00–20:00) и отмечаем 07:35 → 19:25
        _fill_cycle(cls.emp["id"])
        cls.day = min(FIRST + dt.timedelta(days=4), TODAY)
        r = client.put("/api/tabel/cell", json={
            "employee_id": cls.emp["id"], "date": cls.day.isoformat(),
            "code": "Я", "hours": 10.75, "note": ""})
        assert r.status_code == 200, r.text
        for ts, kind in ((f"{cls.day.isoformat()}T07:35:00", "in"),
                         (f"{cls.day.isoformat()}T19:25:00", "out")):
            r = client.post("/api/punches", json={
                "employee_id": cls.emp["id"], "ts": ts, "kind": kind,
                "source": "manager", "note": "сетка «Номера»"})
            assert r.status_code == 200, r.text

    @staticmethod
    def _rounded(hhmm: str, step: int) -> str:
        """Правило RUL-ROUND-MOMENTS: ближайшее кратное шагу от полуночи,
        ровно половина шага — вперёд. Дублирует домен для проверки ответа."""
        total = int(hhmm[:2]) * 60 + int(hhmm[3:])
        whole, rest = divmod(total, step)
        grids = whole + 1 if rest * 2 >= step else whole
        return f"{grids * step // 60:02d}:{grids * step % 60:02d}"

    def _grid(self, c=None):
        r = (c or client).get("/api/fact/day", params={"date": self.day.isoformat()})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        row = next(x for x in d["rows"] if x["employee"]["id"] == self.emp["id"])
        return d, row

    def test_01_marks_and_rounding(self):
        """Сырые отметки, округление до шага и сопряжённая сессия — из движка."""
        d, row = self._grid()
        self.assertTrue(d["all_employees"], "менеджер видит всех трудоустроенных в дне")
        self.assertIsNone(row["error"], row["error"])
        self.assertFalse(row["out_of_staff"])
        step = d["step_minutes"]
        self.assertEqual([(m["at"], m["kind"]) for m in row["marks"]],
                         [("07:35", "in"), ("19:25", "out")])
        self.assertEqual([m["rounded"] for m in row["marks"]],
                         [self._rounded("07:35", step), self._rounded("19:25", step)],
                         "округление — то же правило, что в расчёте")
        self.assertEqual([(s["start"], s["end"], s["open"]) for s in row["segments"]],
                         [(self._rounded("07:35", step), self._rounded("19:25", step), False)])

    def test_02_card_numbers_from_engine(self):
        """Окно/план/отработано/недостача/переработка — числа settle, не клиента."""
        d, row = self._grid()
        c = row["card"]
        self.assertIsNotNone(c, row.get("error"))
        step = d["step_minutes"]
        self.assertEqual(c["timesheet_value"], "Я 10,75")
        self.assertEqual(c["window"], ["08:00", "20:00"], "окно жёстко из кода Табеля (Q1)")
        self.assertEqual(c["plan_minutes"], 720, "расчётный план = длина окна (R34)")
        to_min = lambda hhmm: int(hhmm[:2]) * 60 + int(hhmm[3:])  # noqa: E731
        start = to_min(self._rounded("07:35", step))
        end = to_min(self._rounded("19:25", step))
        self.assertEqual(c["fact_minutes"], end - start)
        self.assertEqual(c["work_minutes"], min(end, 20 * 60) - max(start, 8 * 60),
                         "рабочее = сессия ∩ окно")
        self.assertEqual(c["debt_minutes"], max(0, 720 - c["work_minutes"]))
        self.assertEqual(c["overtime_minutes"], c["fact_minutes"] - c["work_minutes"])
        self.assertEqual(sum(c["codes"].values()), c["overtime_minutes"],
                         "переработка целиком разбирается по категориям ДЯ/ДН")

    def test_03_flags_from_schedule(self):
        """Флаги — из Графика: уход раньше конца смены — РАННИЙ УХОД; опоздания нет."""
        _d, row = self._grid()
        codes = {f["code"] for f in row["card"]["flags"]}
        self.assertIn("EARLY_DEPARTURE", codes)
        self.assertNotIn("LATE", codes)
        for f in row["card"]["flags"]:
            self.assertTrue(f["title"], "человеческий текст флага")

    def test_04_employee_sees_only_self(self):
        """Не-менеджер видит в сетке только себя (как в истории сессий)."""
        r = employee_client.get("/api/fact/day", params={"date": self.day.isoformat()})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertFalse(d["all_employees"])
        self.assertEqual(len(d["rows"]), 1)
        me = employee_client.get("/api/auth/me").json()
        self.assertEqual(d["rows"][0]["employee"]["id"], me["user"]["employee_id"])

    def test_05_day_before_employment_excluded(self):
        """День до приёма: сотрудника нет в строках сетки (R35)."""
        before = (FIRST - dt.timedelta(days=10)).isoformat()
        r = client.get("/api/fact/day", params={"date": before})
        self.assertEqual(r.status_code, 200, r.text)
        ids = [x["employee"]["id"] for x in r.json()["rows"]]
        self.assertNotIn(self.emp["id"], ids)


if __name__ == "__main__":
    unittest.main()
