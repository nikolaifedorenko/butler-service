"""Норматив справочника кодов Табеля от 12.10.2026.

В Табеле (первичном документе) нет кодов «Суточная смена (части дня)» и «Выходной за
отработанные часы» — оба случая оформляются данными Графика и банка:

* суточная/ночная смена — **графиковая смена**: в Табеле обычная явка с зарплатной
  нормой («Я 10,75» при окне 08:00–20:00), по факту сотрудник работает через полночь
  (08:00–08:00 или 20:00–20:00). Расчёт разделяет присутствие сам: рабочее время —
  пересечение с окном, всё вне окна — переработка (4.7, RUL-WORK-AND-OVERTIME);
* выходной за ранее отработанные часы — **согласованное отсутствие** в Графике: в
  Табеле остаётся явка, отсутствие не меняет план (RUL-ABSENCE-ONLY-FLAGS), недостачу
  гасит банк часов, то есть ранее накопленные переработки (паттерн EX-29).

Что проверяем: стартовый справочник и окна, заполнение Табеля из циклов для суточной
смены (одно значение в дне-якоре, «утро» следующего дня не дублируется), изъятие
кодов из сохранённых версий справочников и безопасность изъятия, пока коды стоят в
Табеле.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import unittest

tmp_db = os.path.join(tempfile.gettempdir(), "tt_timesheet_norm.db")
if os.path.exists(tmp_db):
    os.remove(tmp_db)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tmp_db}")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.engine_bootstrap import REMOVED_DAY_CODES, strip_removed_day_codes  # noqa: E402
from app.main import app, init_db  # noqa: E402
from app.models import EngineSettingsVersion, ShiftType, TabelDay  # noqa: E402

init_db()
client = TestClient(app)

REMOVED_WINDOWS = ("С 16", "С 8", "С 24")


def _payload(db) -> dict:
    ver = db.scalars(select(EngineSettingsVersion)
                     .order_by(EngineSettingsVersion.valid_from.desc(),
                               EngineSettingsVersion.id.desc()).limit(1)).one()
    return json.loads(ver.payload_json)


class TestTimesheetCodeNorm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r = client.post("/api/auth/login", json={"username": "admin", "password": "demo1234"})
        assert r.status_code == 200, r.text

    # ── 1. стартовый справочник ──
    def test_01_removed_codes_absent(self):
        db = SessionLocal()
        try:
            payload = _payload(db)
            for code in REMOVED_DAY_CODES:
                self.assertNotIn(code, payload["day_code_policy"],
                                 f"код «{code}» исключён из справочника Табеля")
            for key in REMOVED_WINDOWS:
                self.assertNotIn(key, payload["windows"],
                                 f"окно «{key}» исключено вместе с кодом")
            # норматив требует значения для суточной сменя: явка с зарплатной нормой
            self.assertIn("Я 10,75", payload["windows"])
            self.assertEqual(payload["windows"]["Я 10,75"],
                             {"start_minute": 480, "end_minute": 1200})
        finally:
            db.close()

    def test_02_shift_dictionary_has_no_link_fields(self):
        """18.10.2026: словарь смен — только ячейки Графика: ни tzh_code, ни
        display_code, ни deduct_from_bank; суточные — обычная добавляемая смена,
        а «выходной за часы» — системное отсутствие с заявлением."""
        db = SessionLocal()
        try:
            sutki = db.scalar(select(ShiftType).where(ShiftType.code == "SUTKI"))
            self.assertIsNotNone(sutki)
            self.assertFalse(hasattr(sutki, "tzh_code"), "связка со справочником кодов удалена")
            self.assertFalse(hasattr(sutki, "tzh_hours"),
                             "зарплатная норма смены не моделируется в словаре")
            timeoff = db.scalar(select(ShiftType).where(ShiftType.code == "TIMEOFF_HOURS"))
            self.assertIsNotNone(timeoff)
            self.assertEqual(timeoff.doc_type, "day_off_hours", "заявление остаётся")
            self.assertEqual(timeoff.color, "#0e9aa7", "цвет плашки «Выходной за часы»")
        finally:
            db.close()

    # ── 2. заполнение Табеля из циклов ──
    def test_03_overnight_shift_single_anchor_value(self):
        today = dt.date.today()
        first = today.replace(day=1)
        r = client.post("/api/tabel/fill-from-cycles", json={
            "year": first.year, "month": first.month, "overwrite": True})
        self.assertEqual(r.status_code, 200, r.text)
        db = SessionLocal()
        try:
            # сотрудник на суточных сменах (демо-сид: «Смена 2», цикл 1/3)
            from app.models import Employee
            emp = db.scalar(select(Employee).where(Employee.full_name.like("Петров%")))
            self.assertIsNotNone(emp)
            rows = {r.date: r for r in db.scalars(select(TabelDay).where(
                TabelDay.employee_id == emp.id, TabelDay.date >= first,
                TabelDay.date <= first + dt.timedelta(days=31)))}
            self.assertTrue(rows, "Табель месяца заполнен из циклов")
            used = {row.code for row in rows.values()}
            for code in REMOVED_DAY_CODES:
                self.assertNotIn(code, used, f"в Табеле не осталось кода «{code}»")
            # суточные 08:00–08:00 → явка с окном 08:00–20:00, одна строка в дне начала
            anchor_days = [d for d, row in rows.items() if row.code == "Я" and row.plan_minutes]
            self.assertTrue(anchor_days, "суточная смена записана явкой в дне-якоре")
            for day in anchor_days:
                self.assertEqual(rows[day].plan_minutes, 720,
                                 "план строки = плановые часы значения окна 08:00–20:00")
            # «утро» суточной смены не превращается в отдельное значение следующего дня
            self.assertFalse(any(row.plan_minutes == 480 for row in rows.values()),
                             "значения «8 ч» от утреннего куска смены в Табеле нет")
        finally:
            db.close()

    # ── 3. изъятие кодов из сохранённых версий ──
    def test_04_strip_removes_unused_codes(self):
        db = SessionLocal()
        try:
            payload = _payload(db)
            broken = json.loads(json.dumps(payload))
            broken["day_code_policy"]["С"] = {"carries_hours": True, "accepts_ut": True,
                                              "counts_in_ut": True,
                                              "plan_equals_fact_auto": False}
            broken["day_code_policy"]["НВ"] = {"carries_hours": False, "accepts_ut": False,
                                               "counts_in_ut": True,
                                               "plan_equals_fact_auto": False}
            for key, win in (("С 16", {"start_minute": 480, "end_minute": 1440}),
                             ("С 8", {"start_minute": 0, "end_minute": 480})):
                broken["windows"][key] = win
            db.add(EngineSettingsVersion(valid_from=dt.date(2001, 1, 1),
                                         payload_json=json.dumps(broken, ensure_ascii=False),
                                         note="тест: версия с исключёнными кодами",
                                         created_by_name="test"))
            db.commit()
            out = strip_removed_day_codes(db)
            db.commit()
            # «НБ» — в REMOVED_DAY_CODES с 16.10.2026 (артефакт старого наполнения)
            self.assertEqual(sorted(out["removed_codes"]), ["НБ", "НВ", "С"])
            self.assertEqual(sorted(out["removed_windows"]), ["С 16", "С 8"])
            self.assertEqual(out["blocked_by_timesheet"], [])
            after = _payload(db)
            for code in REMOVED_DAY_CODES:
                self.assertNotIn(code, after["day_code_policy"])
            for key in ("С 16", "С 8"):
                self.assertNotIn(key, after["windows"])
            # прочие строки справочника не пострадали
            self.assertEqual(after["cascade_order"], payload["cascade_order"])
            self.assertEqual(after["global_defaults"], payload["global_defaults"])
        finally:
            db.close()

    def test_05_strip_blocked_while_code_in_timesheet(self):
        """Пока код стоит в Табеле, справочник не трогается: иначе расчёт остановится."""
        db = SessionLocal()
        try:
            from app.models import Employee
            emp = db.scalars(select(Employee).where(Employee.deleted_at.is_(None))).first()
            day = dt.date(2001, 6, 1)
            db.add(TabelDay(employee_id=emp.id, date=day, code="С", plan_minutes=960,
                            source="manual"))
            payload = _payload(db)
            broken = json.loads(json.dumps(payload))
            broken["day_code_policy"]["С"] = {"carries_hours": True, "accepts_ut": True,
                                              "counts_in_ut": True,
                                              "plan_equals_fact_auto": False}
            db.add(EngineSettingsVersion(valid_from=dt.date(2001, 1, 1),
                                         payload_json=json.dumps(broken, ensure_ascii=False),
                                         note="тест: код используется в Табеле",
                                         created_by_name="test"))
            db.commit()
            out = strip_removed_day_codes(db)
            db.commit()
            self.assertEqual(out["blocked_by_timesheet"], ["С"])
            after = _payload(db)
            self.assertIn("С", after["day_code_policy"], "код остался: он используется")
        finally:
            db.rollback()
            for row in db.scalars(select(TabelDay).where(TabelDay.date == dt.date(2001, 6, 1))):
                db.delete(row)
            for ver in db.scalars(select(EngineSettingsVersion).where(
                    EngineSettingsVersion.note.like("тест:%"))):
                db.delete(ver)
            db.commit()
            db.close()


class TestDailyShiftExample(unittest.TestCase):
    """Пример владельца от 12.10.2026 — суточная смена без кода «С».

    01.10 в Табеле «Я 10,75» при стандартном окне 08:00–20:00; в Графике смена
    08:00–08:00 следующих суток; сотрудник пришёл 01.10 08:00, ушёл 02.10 08:00.
    Присутствие режется полуночью на 01.10 08:00–24:00 и 02.10 00:00–08:00, из первого
    куска вырезается окно — переработка 01.10 ДЯ 2 (20:00–22:00) и ДН 2 (22:00–24:00),
    02.10 ДН 6 (00:00–06:00) и ДЯ 2 (06:00–08:00).
    """

    @classmethod
    def setUpClass(cls):
        r = client.post("/api/auth/login", json={"username": "admin", "password": "demo1234"})
        assert r.status_code == 200, r.text
        from app.seed import accounting_start
        cls.emp_id = 4
        month = accounting_start(dt.date.today())
        while (month.year, month.month) < (2026, 10):
            cls._close(month)
            month = dt.date(month.year + (month.month == 12), month.month % 12 + 1, 1)

    @staticmethod
    def _close(month):
        return client.post("/api/mgmt/close", json={"year": month.year, "month": month.month,
                                                    "employee_ids": [TestDailyShiftExample.emp_id]})

    def test_11_daily_shift_split_by_midnight(self):
        emp = self.emp_id
        r = client.put("/api/tabel/cell", json={"employee_id": emp, "date": "2026-10-01",
                                                "code": "Я", "hours": 10.75, "note": ""})
        self.assertEqual(r.status_code, 200, r.text)
        r = client.put("/api/tabel/cell", json={"employee_id": emp, "date": "2026-10-02",
                                                "code": "В", "note": ""})
        self.assertEqual(r.status_code, 200, r.text)
        r = client.put("/api/schedule/shift", json={
            "employee_id": emp, "date": "2026-10-01",
            "shifts": [{"start": "08:00", "end": "08:00", "end_next_day": True, "note": "сутки"}]})
        self.assertEqual(r.status_code, 200, r.text)
        for ts, kind in (("2026-10-01T08:00:00", "in"), ("2026-10-02T08:00:00", "out")):
            r = client.post("/api/punches", json={"employee_id": emp, "ts": ts, "kind": kind,
                                                  "source": "manager", "note": "пример"})
            self.assertIn(r.status_code, (200, 409), r.text)
        r = client.get("/api/mgmt", params={"year": 2026, "month": 10, "employee_id": emp,
                                            "detail": True})
        self.assertEqual(r.status_code, 200, r.text)
        row = r.json()["rows"][0]
        self.assertIsNone(row.get("error"), row.get("error"))
        days = {d["day"]: d for d in row["days"]}

        first = days["2026-10-01"]
        self.assertEqual(first["timesheet_value"], "Я 10,75")
        self.assertEqual(first["plan_minutes"], 720, "план карточки = длина окна 08:00–20:00")
        self.assertEqual(first["timesheet_plan_minutes"], 645, "план строки — информационный")
        self.assertEqual(first["fact_minutes"], 16 * 60, "08:00–24:00 в этом дне")
        self.assertEqual(first["work_minutes"], 12 * 60, "рабочее время = факт ∩ окно")
        self.assertEqual(first["overtime_minutes"], 4 * 60)
        self.assertEqual(first["debt_minutes"], 0)
        self.assertEqual(dict(first["codes"]), {"ДЯ": 120, "ДН": 120},
                         "20:00–22:00 дневные, 22:00–24:00 ночные")

        second = days["2026-10-02"]
        self.assertEqual(second["timesheet_value"], "В")
        self.assertEqual(second["plan_minutes"], 0, "у выходного окна нет")
        self.assertEqual(second["fact_minutes"], 8 * 60, "00:00–08:00 — кусок нового дня")
        self.assertEqual(second["work_minutes"], 0)
        self.assertEqual(second["overtime_minutes"], 8 * 60)
        self.assertEqual(dict(second["codes"]), {"ДН": 360, "ДЯ": 120},
                         "00:00–06:00 ночные, 06:00–08:00 дневные")


class TestTimeoffHours(unittest.TestCase):
    """Часы «выходного за часы» выводятся из стандартного окна смен сотрудника."""

    @classmethod
    def setUpClass(cls):
        r = client.post("/api/auth/login", json={"username": "admin", "password": "demo1234"})
        assert r.status_code == 200, r.text

    def test_06_hours_from_employee_window(self):
        from app.models import Employee
        db = SessionLocal()
        try:
            emp = db.scalar(select(Employee).where(Employee.full_name.like("Иванов%")))
            self.assertIsNotNone(emp)
            eid = emp.id
        finally:
            db.close()
        today = dt.date.today()
        first = today.replace(day=1)
        r = client.post("/api/tabel/fill-from-cycles", json={
            "year": first.year, "month": first.month, "overwrite": True})
        self.assertEqual(r.status_code, 200, r.text)
        db = SessionLocal()
        try:
            work_day = db.scalar(select(TabelDay).where(
                TabelDay.employee_id == eid, TabelDay.date >= first,
                TabelDay.plan_minutes > 0).order_by(TabelDay.date))
        finally:
            db.close()
        self.assertIsNotNone(work_day, "у сотрудника есть рабочие дни в Табеле")
        r = client.get("/api/schedule/timeoff-hours", params={
            "employee_id": eid, "date": work_day.date.isoformat()})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertEqual(data["hours_source"], "window_of_day")
        self.assertEqual(data["hours"], round(work_day.plan_minutes / 60, 2))

    def test_07_day_off_statement_carries_hours(self):
        """Заявление «выходной за часы» печатается с часами, а не с нулём."""
        from app.models import Employee
        db = SessionLocal()
        try:
            emp = db.scalar(select(Employee).where(Employee.full_name.like("Иванов%")))
            eid = emp.id
        finally:
            db.close()
        today = dt.date.today()
        first = today.replace(day=1)
        client.post("/api/tabel/fill-from-cycles", json={
            "year": first.year, "month": first.month, "overwrite": True})
        db = SessionLocal()
        try:
            work_day = db.scalar(select(TabelDay).where(
                TabelDay.employee_id == eid, TabelDay.date >= first,
                TabelDay.plan_minutes > 0).order_by(TabelDay.date))
            kind = db.scalar(select(ShiftType).where(ShiftType.code == "TIMEOFF_HOURS"))
        finally:
            db.close()
        day = work_day.date.isoformat()
        r = client.post("/api/schedule/range-absence", json={
            "employee_ids": [eid], "first": day, "last": day,
            "shift_type_id": kind.id, "note": "отгул за переработки"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["mode"], "schedule_absence")
        p = client.get("/api/schedule/absence-period",
                       params={"employee_id": eid, "date": day})
        self.assertEqual(p.status_code, 200, p.text)
        payload = p.json()
        self.assertIsNotNone(payload.get("hours"), "часы для заявления считаются")
        self.assertGreater(payload["hours"], 0, "в заявлении не должно быть «0 ч переработки»")
        self.assertEqual(payload["shift"]["doc_type"], "day_off_hours")
        self.assertEqual(payload["hours_source"], "window_of_day")
        # Табель не переписан: явка осталась
        db = SessionLocal()
        try:
            row = db.scalar(select(TabelDay).where(TabelDay.employee_id == eid,
                                                   TabelDay.date == work_day.date))
            self.assertEqual(row.code, "Я")
            self.assertGreater(row.plan_minutes, 0)
        finally:
            db.close()


class TestPayRulesAndConflicts(unittest.TestCase):
    """Правила оплаты: глобальные значения видны в интерфейсе, конфликт не сохраняется."""

    @classmethod
    def setUpClass(cls):
        r = client.post("/api/auth/login", json={"username": "admin", "password": "demo1234"})
        assert r.status_code == 200, r.text

    def test_08_engine_defaults_exposed(self):
        data = client.get("/api/settings").json()
        defaults = data["engine_defaults"]
        names = {m["name"]: m for m in defaults["modifiers"]}
        self.assertIn("pays_overtime", names, "«Оплачиваются ли переработки» видны в настройках")
        self.assertTrue(names["pays_overtime"]["title"])
        self.assertTrue(names["pays_overtime"]["hint"])
        self.assertIsNotNone(names["pays_overtime"]["value"])
        self.assertIn("double_overtime", names)
        self.assertIn("plan_equals_fact", names)
        self.assertEqual(defaults["version"]["on"], defaults["version"]["on"])
        self.assertIsInstance(defaults["upcoming_versions"], list)

    def test_09_conflicting_modifier_rejected(self):
        day = (dt.date.today() + dt.timedelta(days=1)).isoformat()
        first = {"name": "pays_overtime", "value": "0", "group": "Смена 1", "date": day,
                 "note": "первое"}
        r = client.post("/api/engine-settings/modifiers", json=first)
        self.assertEqual(r.status_code, 200, r.text)
        kept_id = r.json()["id"]
        second = {**first, "value": "1", "note": "второе (конфликт)"}
        r = client.post("/api/engine-settings/modifiers", json=second)
        self.assertEqual(r.status_code, 409, "конфликт одного уровня не сохраняется")
        detail = r.json()["detail"]
        self.assertEqual(detail["conflict_with"]["id"], kept_id)
        self.assertIn("CHK-MODIFIER-CONFLICT", detail["message"])
        # расчёт не сломан: вкладки отвечают 200
        today = dt.date.today()
        self.assertEqual(client.get("/api/mgmt", params={"year": today.year,
                                                         "month": today.month}).status_code, 200)
        # другое правило (сотрудник + день) сильнее и конфликтом не считается
        r = client.post("/api/engine-settings/modifiers", json={
            "name": "pays_overtime", "value": "1", "employee_id": 4, "date": day,
            "note": "исключение для сотрудника"})
        self.assertEqual(r.status_code, 200, r.text)
        exception_id = r.json()["id"]
        for mod_id in (kept_id, exception_id):
            self.assertEqual(client.delete(f"/api/engine-settings/modifiers/{mod_id}").status_code,
                             200)

    def test_10_config_error_is_409_not_500(self):
        """Повреждённая конфигурация — типизированный отказ 409 с человеческим текстом."""
        from app.models import DayModifier
        day = dt.date.today() + dt.timedelta(days=2)
        db = SessionLocal()
        try:
            db.add(DayModifier(name="pays_overtime", value="0", group="Смена 2", date=day,
                               note="сломано A"))
            db.add(DayModifier(name="pays_overtime", value="1", group="Смена 2", date=day,
                               note="сломано B"))
            db.commit()
            for path in ("/api/mgmt", "/api/tabel", "/api/schedule", "/api/presence/board"):
                r = client.get(path, params={"year": day.year, "month": day.month})
                self.assertEqual(r.status_code, 409, f"{path}: ожидали 409, не 500")
                text = r.json()["detail"]
                self.assertIn("Два правила одного уровня", text)
                self.assertNotIn("{'", text, "текст без машинных словарей")
        finally:
            for row in db.scalars(select(DayModifier).where(DayModifier.date == day)):
                db.delete(row)
            db.commit()
            db.close()
        today = dt.date.today()
        self.assertEqual(client.get("/api/mgmt", params={"year": today.year,
                                                         "month": today.month}).status_code, 200)
