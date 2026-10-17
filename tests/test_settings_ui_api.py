"""Экраны «Обзор» и «Проверитель» нового раздела настроек: /health и /rules/resolve.

Что проверяем:
* «Обзор» отдаёт паспорт объекта (действующая версия, счётчики справочников) и список
  замечаний, в том числе доменные CHK-* ДО сохранения версии — то, что раньше
  всплывало только как HTTP 500 на вкладке «Управленческий табель» (дефект D8);
* прикладные сверки D18/D19 (группы ↔ блоки, коды Табеля ↔ словарь смен) видны в
  «Обзоре» и не требуют открытия расчёта;
* «Проверитель» объясняет значение правила для (сотрудник, день): приоритет 1–7
  считается доменом, а интерфейс получает уровень и источник (ручное правило,
  производственный календарь, ВИП-период, глобальный дефолт, колонка кода);
* права: оба эндпоинта — только с `settings.view`.
"""
from __future__ import annotations

import datetime as dt
import os
import tempfile
import unittest

tmp_db = os.path.join(tempfile.gettempdir(), "tt_settings_ui.db")
if os.path.exists(tmp_db):
    os.remove(tmp_db)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tmp_db}")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.main import app, init_db  # noqa: E402
from app.models import (  # noqa: E402
    DayModifier,
    DoublePayDay,
    Employee,
    ScheduleAbsence,
    ShiftType,
)

init_db()
client = TestClient(app)


def _login(username: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": username, "password": "demo1234"})
    assert r.status_code == 200, r.text
    return c


def _employee(db, group: str) -> Employee:
    return db.scalars(select(Employee).where(Employee.schedule_group == group,
                                             Employee.deleted_at.is_(None))
                      .order_by(Employee.id)).first()


class TestHealth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin = _login("admin")
        cls.emp = _login("ivanov")
        cls.today = dt.date.today()

    def test_01_passport(self):
        r = self.admin.get("/api/engine-settings/health")
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["on"], self.today.isoformat())
        self.assertIsNotNone(d["version"]["id"])
        s = d["stats"]
        for key in ("tz", "step_minutes", "period_granularity", "late_limit_minutes",
                    "codes", "windows", "groups", "rules_active", "global_defaults"):
            self.assertIn(key, s)
        self.assertGreater(s["codes"], 0)
        self.assertGreater(s["windows"], 0)
        self.assertIsInstance(d["checks"], list)
        self.assertIsInstance(d["upcoming"], list)
        self.assertIsInstance(d["recent"], list)

    def test_02_domain_checks_clean(self):
        """Доменных нарушений CHK-* нет: именно они останавливают расчёт периода.

        Прикладные сверки (APP-*) в общем тестовом прогоне могут срабатывать на данных
        других тестов — например, test_api создаёт смену с кодом Табеля «07–16», которого
        нет в справочнике. Это не дефект конфигурации движка, а честно найденный разрыв
        словарей: он и должен быть виден в «Обзоре».
        """
        d = self.admin.get("/api/engine-settings/health").json()
        chk = [c for c in d["checks"] if c["code"].startswith("CHK-")]
        self.assertEqual(chk, [], [c["text"] for c in chk])
        for c in d["checks"]:
            self.assertIn(c["screen"], {"overview", "calc", "pay", "codes", "groups",
                                        "shifts", "docs", "system", "expert"})
            self.assertIn(c["level"], ("error", "warn"))
            self.assertTrue(c["text"].strip())

    def test_03_broken_shift_link_is_reported(self):
        """D19: смена ссылается на код Табеля, которого нет в справочнике."""
        db = SessionLocal()
        st = ShiftType(code="TEST_UI_BROKEN", name="Тест битой ссылки", tzh_code="ЫЫ",
                       kind="work", start_time="08:00", end_time="17:00")
        db.add(st)
        db.commit()
        st_id = st.id
        db.close()
        try:
            d = self.admin.get("/api/engine-settings/health").json()
            codes = [c for c in d["checks"] if c["code"] == "APP-SHIFT-CODE"]
            self.assertTrue(any("ЫЫ" in c["text"] for c in codes), d["checks"])
            self.assertTrue(all(c["level"] == "error" for c in codes))
            self.assertTrue(all(c["screen"] == "shifts" for c in codes))
        finally:
            db = SessionLocal()
            db.delete(db.get(ShiftType, st_id))
            db.commit()
            db.close()

    def test_04_health_requires_permission(self):
        self.assertEqual(self.emp.get("/api/engine-settings/health").status_code, 403)

    def test_05_seed_closes_code_no_shift_warnings(self):
        """16.10.2026: предупреждений APP-CODE-NO-SHIFT для «К» и «НБ» больше нет.

        «К» — документарный код с «План=Факт = Авто» (R19): Табель первичен,
        График генерируется из Табеля, вид смены ему не нужен — проверка пропускает.
        «НБ» — артефакт старого наполнения: код изъят из справочника целиком
        (REMOVED_DAY_CODES), а добавленный было вид SICK_UNPAID убран миграцией.
        """
        db = SessionLocal()
        try:
            st = db.scalars(select(ShiftType).where(ShiftType.code == "SICK_UNPAID")).first()
            self.assertIsNone(st, "вид-артефакт SICK_UNPAID должен быть удалён миграцией")
        finally:
            db.close()
        payload = self.admin.get("/api/engine-settings").json()["active"]["payload"]
        self.assertNotIn("НБ", payload["day_code_policy"], "код «НБ» исключён из справочника")
        d = self.admin.get("/api/engine-settings/health").json()
        warns = [c for c in d["checks"] if c["code"] == "APP-CODE-NO-SHIFT"]
        for code in ("К", "НБ"):
            self.assertFalse(any(f"«{code}»" in c["text"] for c in warns), d["checks"])

    def test_06_code_no_shift_still_warns_without_live_kind(self):
        """Регресс: код без ЖИВОГО вида по-прежнему даёт APP-CODE-NO-SHIFT.

        Архив вида (active=False + archived_at) рвёт связь справочников — из
        Табеля код поставить нельзя; раньше проверка архив не видела (у модели
        нет атрибута «archived», getattr всегда возвращал False). Носитель —
        «Б» (SICK): у него нет «План=Факт = Авто», пропуск проверки не срабатывает.
        """
        db = SessionLocal()
        st = db.scalars(select(ShiftType).where(ShiftType.code == "SICK")).first()
        assert st is not None
        st.active = False
        st.archived_at = self.today
        db.commit()
        db.close()
        try:
            d = self.admin.get("/api/engine-settings/health").json()
            warns = [c for c in d["checks"] if c["code"] == "APP-CODE-NO-SHIFT"]
            self.assertTrue(any("«Б»" in c["text"] for c in warns), d["checks"])
            self.assertTrue(all(c["level"] == "warn" for c in warns))
            self.assertTrue(all(c["screen"] == "shifts" for c in warns))
        finally:
            db = SessionLocal()
            st = db.scalars(select(ShiftType).where(ShiftType.code == "SICK")).first()
            st.active = True
            st.archived_at = None
            db.commit()
            db.close()
        d = self.admin.get("/api/engine-settings/health").json()
        warns = [c for c in d["checks"] if c["code"] == "APP-CODE-NO-SHIFT"]
        self.assertFalse(any("«Б»" in c["text"] for c in warns),
                         "после возврата вида из архива предупреждение уходит")

    def test_07_missing_kind_readded_by_migration(self):
        """Старая база без вида словаря: _migrate_missing_shifts докладывает его из сида.

        Регресс старта приложения: raw-INSERT миграции не перечислял
        punch_in_allowed/punch_out_allowed, а в базах, созданных create_all, эти
        колонки NOT NULL без серверного дефолта — сервер падал при старте.
        Носитель — ABSENT_UNKNOWN («НН»): обычный вид из сида.
        """
        from app.migrations import _migrate_missing_shifts

        db = SessionLocal()
        st = db.scalars(select(ShiftType).where(ShiftType.code == "ABSENT_UNKNOWN")).first()
        assert st is not None
        db.delete(st)
        db.commit()
        db.close()
        try:
            _migrate_missing_shifts()
            _migrate_missing_shifts()          # идемпотентно
            db = SessionLocal()
            try:
                st = db.scalars(select(ShiftType).where(ShiftType.code == "ABSENT_UNKNOWN")).first()
                self.assertIsNotNone(st, "миграция не вернула вид «НН» в словарь")
                self.assertEqual(st.tzh_code, "НН")
                self.assertTrue(st.punch_in_allowed)
                self.assertTrue(st.punch_out_allowed)
            finally:
                db.close()
        finally:
            d = self.admin.get("/api/engine-settings/health").json()
            warns = [c for c in d["checks"] if c["code"] == "APP-CODE-NO-SHIFT"]
            self.assertFalse(any("«НН»" in c["text"] for c in warns),
                             "после миграции health снова чист")

    def test_08_sick_unpaid_migration_idempotent(self):
        """16.10.2026: «НБ» — артефакт. _migrate_remove_sick_unpaid убирает вид:
        удаление без ссылок, архив + очистка tzh_code при ссылках, идемпотентно."""
        from app.migrations import _migrate_remove_sick_unpaid

        def _kind():
            db = SessionLocal()
            try:
                return db.scalars(select(ShiftType).where(
                    ShiftType.code == "SICK_UNPAID")).first()
            finally:
                db.close()

        # 1) без ссылок — удаление
        db = SessionLocal()
        db.add(ShiftType(code="SICK_UNPAID", name="Неоплачиваемый больничный",
                         display_code="НБ", tzh_code="НБ", kind="absence",
                         color="#c0504d", sort_order=85, is_working=False,
                         counts_as_worked=False))
        db.commit()
        db.close()
        _migrate_remove_sick_unpaid()
        _migrate_remove_sick_unpaid()      # идемпотентно
        self.assertIsNone(_kind(), "вид-артефакт не удалён")

        # 2) со ссылкой отсутствия — архив и очистка tzh_code (health не ругается)
        db = SessionLocal()
        emp = db.scalars(select(Employee).order_by(Employee.id)).first()
        st = ShiftType(code="SICK_UNPAID", name="Неоплачиваемый больничный",
                       display_code="НБ", tzh_code="НБ", kind="absence",
                       color="#c0504d", sort_order=85, is_working=False,
                       counts_as_worked=False)
        db.add(st)
        db.flush()
        now = dt.datetime.utcnow()
        db.add(ScheduleAbsence(employee_id=emp.id, start_utc=now - dt.timedelta(hours=2),
                               end_utc=now + dt.timedelta(hours=2), kind_id=st.id))
        db.commit()
        st_id = st.id
        db.close()
        try:
            _migrate_remove_sick_unpaid()
            _migrate_remove_sick_unpaid()  # идемпотентно
            db = SessionLocal()
            row = db.get(ShiftType, st_id)
            self.assertIsNotNone(row, "вид со ссылкой удалён — история сломана")
            self.assertFalse(row.active)
            self.assertIsNotNone(row.archived_at)
            self.assertEqual(row.tzh_code, "", "tzh_code архивного вида должен быть очищен")
            db.close()
        finally:
            from sqlalchemy import delete

            db = SessionLocal()
            db.execute(delete(ScheduleAbsence).where(ScheduleAbsence.kind_id == st_id))
            row = db.get(ShiftType, st_id)
            if row is not None:
                db.delete(row)
            db.commit()
            db.close()



class TestResolver(unittest.TestCase):
    """«Проверитель»: какое значение подействовало и на каком уровне приоритета."""

    @classmethod
    def setUpClass(cls):
        cls.admin = _login("admin")
        cls.emp = _login("ivanov")
        cls.db = SessionLocal()
        cls.today = dt.date.today()
        cls.first = cls.today.replace(day=1)
        e = _employee(cls.db, "Смена 1")
        assert e is not None, "в демо-базе нет сотрудника группы «Смена 1»"
        cls.emp_id = e.id
        cls.emp_name = e.display_name

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def _resolve(self, emp_id=None, date=None, name=None):
        q = {"employee_id": emp_id or self.emp_id, "date": (date or self.today).isoformat()}
        if name:
            q["name"] = name
        r = self.admin.get("/api/engine-settings/rules/resolve", params=q)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def _cleanup(self):
        for row in self.db.scalars(select(DayModifier).where(
                DayModifier.note == "тест-проверитель")):
            self.db.delete(row)
        for row in self.db.scalars(select(DoublePayDay).where(
                DoublePayDay.note == "тест-проверитель")):
            self.db.delete(row)
        self.db.commit()

    def test_10_all_four_modifiers_explained(self):
        self._cleanup()
        d = self._resolve()
        self.assertEqual(d["employee"]["id"], self.emp_id)
        self.assertEqual(d["employee"]["group"], "Смена 1")
        self.assertEqual(d["date"], self.today.isoformat())
        names = {m["name"] for m in d["modifiers"]}
        self.assertEqual(names, {"double_overtime", "pays_overtime",
                                 "plan_equals_fact", "counts_in_ut"})
        for m in d["modifiers"]:
            if m["level"] == 7:
                self.assertIsNone(m.get("scope"))
            if m["name"] != "counts_in_ut" or d["code"]:
                self.assertIn(m["level"], (1, 2, 3, 4, 5, 6, 7))
                self.assertTrue(m["source"]["text"])
                self.assertTrue(m["text"])

    def test_11_global_default_is_level_seven(self):
        self._cleanup()
        m = next(x for x in self._resolve()["modifiers"] if x["name"] == "pays_overtime")
        self.assertEqual(m["level"], 7)
        self.assertEqual(m["source"]["kind"], "global_default")
        self.assertEqual(len(m["chain"]), 7)
        self.assertEqual([c["level"] for c in m["chain"] if c["hit"]], [7])

    def test_12_group_rule_wins_over_default(self):
        """Уровень 4 (группа + период) сильнее глобального дефолта (уровень 7)."""
        self._cleanup()
        row = DayModifier(name="pays_overtime", value="0", group="Смена 1",
                          period_start=self.first, note="тест-проверитель",
                          created_by_name="admin")
        self.db.add(row)
        self.db.commit()
        try:
            m = next(x for x in self._resolve(name="pays_overtime")["modifiers"]
                     if x["name"] == "pays_overtime")
            self.assertEqual(m["level"], 4)
            self.assertEqual(m["value"], "0")
            self.assertEqual(m["text"], "Нет")
            self.assertEqual(m["source"]["kind"], "rule")
            self.assertEqual(m["source"]["id"], row.id)
            self.assertIn("Смена 1", m["scope"])
            self.assertEqual([c["level"] for c in m["chain"] if c["hit"]], [4])
        finally:
            self._cleanup()

    def test_13_employee_day_rule_wins_over_group(self):
        """Уровень 1 (сотрудник + день) сильнее уровня 4 (группа + период)."""
        self._cleanup()
        self.db.add(DayModifier(name="double_overtime", value="0", group="Смена 1",
                                period_start=self.first, note="тест-проверитель"))
        emp_rule = DayModifier(name="double_overtime", value="1", employee_id=self.emp_id,
                               date=self.today, note="тест-проверитель")
        self.db.add(emp_rule)
        self.db.commit()
        try:
            m = next(x for x in self._resolve(name="double_overtime")["modifiers"]
                     if x["name"] == "double_overtime")
            self.assertEqual(m["level"], 1)
            self.assertEqual(m["source"]["id"], emp_rule.id)
            self.assertEqual(m["value"], "1")
        finally:
            self._cleanup()

    def test_14_double_pay_day_explains_source(self):
        """День производственного календаря — источник «Двойных переработок», не ручное правило."""
        self._cleanup()
        day = DoublePayDay(date=self.today, scope="all", note="тест-проверитель")
        self.db.add(day)
        self.db.commit()
        try:
            m = next(x for x in self._resolve(name="double_overtime", date=self.today)["modifiers"]
                     if x["name"] == "double_overtime")
            self.assertEqual(m["value"], "1")
            self.assertEqual(m["source"]["kind"], "calendar")
            self.assertIn("производственный календарь", m["source"]["text"])
            self.assertIn(m["level"], (5, 6))
        finally:
            self._cleanup()

    def test_15_no_timesheet_row_means_no_counts_in_ut(self):
        """Без строки Табеля «Учитываются ли часы в УТ» не разрешается — честно показываем."""
        far = self.today + dt.timedelta(days=400)
        m = next(x for x in self._resolve(date=far)["modifiers"]
                 if x["name"] == "counts_in_ut")
        self.assertIsNone(m["value"])
        self.assertEqual(m["source"]["kind"], "none")

    def test_16_unknown_employee_and_modifier(self):
        self.assertEqual(self.admin.get("/api/engine-settings/rules/resolve",
                                        params={"employee_id": 999999,
                                                "date": self.today.isoformat()}).status_code, 404)
        self.assertEqual(self.admin.get("/api/engine-settings/rules/resolve",
                                        params={"employee_id": self.emp_id,
                                                "date": self.today.isoformat(),
                                                "name": "no_such_rule"}).status_code, 422)

    def test_17_resolve_requires_permission(self):
        self.assertEqual(self.emp.get("/api/engine-settings/rules/resolve",
                                      params={"employee_id": self.emp_id,
                                              "date": self.today.isoformat()}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
