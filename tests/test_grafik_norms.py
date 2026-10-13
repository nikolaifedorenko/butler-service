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
from app.migrations import migrate_shift_tabel_codes, migrate_timeoff_entity  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
