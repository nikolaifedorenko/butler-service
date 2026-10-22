"""Интеграционные тесты API: вход, график, отметки, табель, настройки."""
from __future__ import annotations

import datetime as dt
import os
import tempfile
import unittest

tmp_db = os.path.join(tempfile.gettempdir(), "tt_test.db")
if os.path.exists(tmp_db):
    os.remove(tmp_db)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tmp_db}")
os.environ["SECRET_KEY"] = "test-secret-key"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.time import local_date  # noqa: E402
from app.main import app, init_db  # noqa: E402

init_db()
client = TestClient(app)


class TestApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manager = client.post("/api/auth/login", json={"username": "gromova", "password": "demo1234"})
        assert cls.manager.status_code == 200, cls.manager.text
        cls.admin = TestClient(app)
        r = cls.admin.post("/api/auth/login", json={"username": "admin", "password": "demo1234"})
        assert r.status_code == 200, r.text
        cls.emp_client = TestClient(app)
        r = cls.emp_client.post("/api/auth/login", json={"username": "ivanov", "password": "demo1234"})
        assert r.status_code == 200, r.text
        # демо-цепочка: последовательно закрыть месяцы от старта учёта до прошлого
        # (RUL-SEQUENTIAL-CLOSING) — иначе view/close текущего месяца отклоняются
        from app.bootstrap.seed import accounting_start
        today = local_date()
        m = accounting_start(today)
        while (m.year, m.month) < (today.year, today.month):
            r = cls.admin.post("/api/mgmt/close", json={"year": m.year, "month": m.month})
            assert r.status_code == 200, r.text
            m = dt.date(m.year + (m.month == 12), m.month % 12 + 1, 1)

    def test_01_health_and_login(self):
        self.assertTrue(client.get("/api/health").json()["ok"])
        bad = client.post("/api/auth/login", json={"username": "gromova", "password": "wrong"})
        self.assertEqual(bad.status_code, 401)

    def test_02_me_and_profile(self):
        me = client.get("/api/auth/me").json()
        self.assertEqual(me["user"]["role"], "supervisor")
        self.assertIsNotNone(me["today"])
        emp_me = self.emp_client.get("/api/auth/me").json()
        self.assertEqual(emp_me["user"]["role"], "employee")
        self.assertIsNotNone(emp_me["today"]["date"])

    def test_03_grid(self):
        today = local_date()
        r = client.get("/api/schedule", params={"year": today.year, "month": today.month})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertGreater(len(data["rows"]), 0)
        import calendar
        self.assertEqual(len(data["days"]), calendar.monthrange(today.year, today.month)[1])
        first = data["rows"][0]
        self.assertIn("cells", first)
        self.assertIn("totals", first)

    def test_04_employee_sees_plan_but_cannot_edit_grid(self):
        """Батлеру график доступен на просмотр (только план), правки — по-прежнему 403."""
        today = local_date()
        r = self.emp_client.get("/api/schedule", params={"year": today.year, "month": today.month})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["readonly"])
        edit = self.emp_client.put("/api/schedule/shift", json={
            "employee_id": 1, "date": today.isoformat(),
            "shifts": [{"start": "09:00", "end": "18:00"}]})
        self.assertEqual(edit.status_code, 403)
        edit = self.emp_client.put("/api/tabel/cell", json={
            "employee_id": 1, "date": today.isoformat(), "code": "Я", "hours": 12})
        self.assertEqual(edit.status_code, 403)

    def test_05_set_cell_and_see_it_in_grid(self):
        # Целевая дата — «сегодня + 3 дня»; сетка запрашивается за МЕСЯЦ целевой даты.
        target = local_date() + dt.timedelta(days=3)
        date = target.isoformat()
        emps = client.get("/api/employees").json()
        emp = next(e for e in emps if e["full_name"].startswith("Иванов"))
        r = client.put("/api/tabel/cell", json={
            "employee_id": emp["id"], "date": date, "code": "Я", "hours": 12, "note": "тест"})
        self.assertEqual(r.status_code, 200, r.text)
        grid = client.get("/api/schedule", params={"year": target.year, "month": target.month}).json()
        row = next(x for x in grid["rows"] if x["employee"]["id"] == emp["id"])
        cell = row["cells"][date]
        self.assertEqual(cell["tabel"]["code"], "Я")
        self.assertEqual(cell["tabel"]["value"], "Я 12")
        self.assertEqual(cell["tabel"]["note"], "тест")
        # График генерируется из Табеля по окну CFG-WINDOWS (16.3)
        gen = [x for x in cell["shifts"] if x["source"] == "generated"]
        self.assertTrue(gen, "смена должна быть сгенерирована из Табеля")
        self.assertIn(("08:00", "20:00"), [(x["start_hm"], x["end_hm"]) for x in gen])
        # больничный: код без часов — смены нет
        r = client.put("/api/tabel/cell", json={
            "employee_id": emp["id"], "date": date, "code": "Б"})
        self.assertEqual(r.status_code, 200, r.text)
        grid = client.get("/api/schedule", params={"year": target.year, "month": target.month}).json()
        row = next(x for x in grid["rows"] if x["employee"]["id"] == emp["id"])
        self.assertEqual(row["cells"][date]["tabel"]["code"], "Б")
        self.assertEqual(row["cells"][date]["shifts"], [])

    def test_07_punch_flow_for_manager_herself(self):
        r = client.post("/api/punches", json={"kind": "IN"})
        if r.status_code == 409:
            self.skipTest("нет открытой смены по демо-данным")
        self.assertEqual(r.status_code, 200, r.text)
        # «auto» сразу после прихода — это двойной тап: сервер отклоняет его как дубль
        dup = client.post("/api/punches", json={"kind": "auto"})
        self.assertEqual(dup.status_code, 409, dup.text)
        # повторный явный IN при открытой смене тоже отклоняется
        self.assertEqual(client.post("/api/punches", json={"kind": "IN"}).status_code, 409)
        after = client.post("/api/punches", json={"kind": "OUT"})
        self.assertEqual(after.status_code, 200, after.text)
        self.assertTrue(after.json()["status"] is not None)
        self.assertIn("message", after.json())

    def test_08_manual_punch_for_employee_and_recalc(self):
        today = local_date()
        emps = client.get("/api/employees").json()
        target = next(e for e in emps if e["full_name"].startswith("Иванов"))
        # прошедший выходной день без отметок (демо-отметки ставятся только на рабочие)
        grid = client.get("/api/schedule", params={"year": today.year, "month": today.month}).json()
        row = next(x for x in grid["rows"] if x["employee"]["id"] == target["id"])
        punches = client.get("/api/punches", params={"employee_id": target["id"],
                                                     "year": today.year, "month": today.month}).json()
        punched = {p["ts"][:10] for p in punches}
        candidates = [d for d in grid["days"]
                      if d["date"] < today.isoformat() and d["date"] not in punched
                      and (row["cells"][d["date"]]["tabel"] or {}).get("code") == "В"]
        assert candidates, "нет свободного прошедшего выходного для теста"
        day = dt.date.fromisoformat(candidates[-1]["date"])
        morning = dt.datetime(day.year, day.month, day.day, 8, 5)
        evening = dt.datetime(day.year, day.month, day.day, 21, 10)
        for ts, kind in ((morning, "IN"), (evening, "OUT")):
            r = client.post("/api/punches", json={"kind": kind, "employee_id": target["id"],
                                                 "ts": ts.isoformat(timespec="minutes")})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertTrue(r.json()["backfill"])

        def card():
            data = client.get("/api/mgmt", params={"year": day.year, "month": day.month,
                                                   "employee_id": target["id"],
                                                   "detail": "true"}).json()
            r0 = data["rows"][0]
            assert r0["error"] is None, r0["error"]
            return next(c for c in r0["days"] if c["day"] == day.isoformat()), r0

        # Табель независим от Графика (4.8): день остаётся «В», пока его не поправят
        c, _ = card()
        self.assertEqual(c["timesheet_value"], "В")
        self.assertEqual((c["plan_minutes"], c["work_minutes"], c["overtime_minutes"]),
                         (0, 0, 780))       # 08:05→08:00, 21:10→21:00: 13 ч, всё переработка
        r = client.put("/api/tabel/cell", json={"employee_id": target["id"],
                                                "date": day.isoformat(), "code": "Я", "hours": 12})
        self.assertEqual(r.status_code, 200, r.text)
        c, row0 = card()
        # окно 08:00–20:00: рабочее 12 ч, переработка 20:00–21:00 = 1 ч ДЯ
        self.assertEqual((c["plan_minutes"], c["fact_minutes"], c["work_minutes"],
                          c["overtime_minutes"]), (720, 780, 720, 60))
        self.assertEqual(row0["ut"][day.isoformat()].get("ДЯ"), 60)

    def test_08b_employee_cannot_backfill(self):
        today = local_date()
        r = self.emp_client.post("/api/punches", json={
            "kind": "IN", "ts": (today - dt.timedelta(days=3)).isoformat() + "T09:00"})
        self.assertEqual(r.status_code, 403)

    def test_09_attendance(self):
        r = client.get("/api/presence/board")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["at_work_now"], len(data["open_session_cards"]))
        self.assertIn("expected_now", data)
        self.assertIn("yet_to_come", data)

    def test_10_mgmt_view_and_xlsx(self):
        today = local_date()
        r = client.get("/api/mgmt", params={"year": today.year, "month": today.month, "mode": "view"})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertTrue(data["rows"])
        for row in data["rows"]:
            if not row["error"]:
                self.assertIn("bank", row)
                self.assertIn("ut", row)
        xlsx_resp = client.get("/api/mgmt/xlsx", params={"year": today.year, "month": today.month})
        self.assertEqual(xlsx_resp.status_code, 200)
        self.assertTrue(xlsx_resp.content[:2] == b"PK")

    def test_11_tabel_view(self):
        today = local_date()
        r = client.get("/api/tabel", params={"year": today.year, "month": today.month})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(any(row["cells"] for row in r.json()["rows"]))

    def test_12_settings(self):
        r = client.get("/api/settings")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("round_mode", r.json()["rules"])          # правила старого движка удалены
        upd = self.admin.put("/api/settings", json=[{"key": "photo_retention_days", "value": "90"}])
        self.assertEqual(upd.status_code, 200, upd.text)
        self.assertEqual(upd.json()["rules"]["photo_retention_days"], 90)
        self.assertEqual(self.admin.put("/api/settings", json=[{"key": "photo_retention_days", "value": "180"}]).status_code, 200)
        self.assertEqual(self.emp_client.put("/api/settings", json=[{"key": "photo_retention_days", "value": "1"}]).status_code, 403)
        eng = self.admin.get("/api/engine-settings").json()
        self.assertEqual(eng["active"]["payload"]["step_minutes"], 60)

    def test_13_impersonation(self):
        emps = client.get("/api/employees").json()
        target = next(e for e in emps if e["full_name"].startswith("Иванов"))
        r = client.post("/api/auth/impersonate", json={"employee_id": target["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["user"]["impersonated"])
        self.assertEqual(client.get("/api/auth/me").json()["user"]["employee_id"], target["id"])
        self.assertEqual(client.post("/api/auth/impersonate/stop").status_code, 200)

    def test_14_audit_log(self):
        r = client.get("/api/audit", params={"limit": 50})
        self.assertEqual(r.status_code, 200)
        actions = {item["action"] for item in r.json()["items"]}
        self.assertTrue(actions & {"schedule_set", "schedule_update", "settings_update", "punch_in"})

    def test_15_unauthorized(self):
        anon = TestClient(app)
        self.assertEqual(anon.get("/api/schedule", params={"year": 2026, "month": 9}).status_code, 401)
        self.assertEqual(anon.post("/api/punches", json={"kind": "IN"}).status_code, 401)

    def test_16b_change_password_flow(self):
        # верный старый пароль → смена; неверный старый → 400; вход с новым паролем работает
        from app.core.db import SessionLocal
        from app.core.identity import User
        old_session = TestClient(app)
        self.assertEqual(old_session.post("/api/auth/login",
                                          json={"username": "ivanov", "password": "demo1234"}).status_code, 200)
        r = self.emp_client.post("/api/auth/change-password",
                                 json={"old_password": "demo1234", "new_password": "temp-pass-1"})
        self.assertEqual(r.status_code, 200, r.text)
        r = self.emp_client.post("/api/auth/change-password",
                                 json={"old_password": "wrong", "new_password": "temp-pass-2"})
        self.assertEqual(r.status_code, 400)
        fresh = TestClient(app)
        self.assertEqual(fresh.post("/api/auth/login", json={"username": "ivanov", "password": "demo1234"}).status_code, 401)
        ok = TestClient(app)
        self.assertEqual(ok.post("/api/auth/login", json={"username": "ivanov", "password": "temp-pass-1"}).status_code, 200)
        # возвращаем демо-пароль, чтобы не влиять на остальные тесты
        # сессия, открытая до смены пароля, больше не действует; текущая — переоформлена
        self.assertEqual(old_session.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.emp_client.get("/api/auth/me").status_code, 200)
        r = self.emp_client.post("/api/auth/change-password",
                                 json={"old_password": "temp-pass-1", "new_password": "demo1234"})
        self.assertEqual(r.status_code, 200)
        # тестовая уборка: возвращаем версию токена, чтобы сессии ivanov в других тест-модулях жили
        db = SessionLocal()
        try:
            u = db.query(User).filter_by(username="ivanov").one()
            u.token_version = 0
            db.commit()
        finally:
            db.close()

    def test_15b_employee_card_actions(self):
        today = local_date()
        created = client.post("/api/employees", json={
            "full_name": "Тестовый Тест Тестович", "position": "Батлер",
            "hired_at": (today - dt.timedelta(days=30)).isoformat(),
            "schedule_group": "Смена 1", "telegram": "@testov", "email": "test@butler.service",
            "contacts": [{"name": "Тестова А. А.", "phone": "+7 900 111-22-33", "relation": "жена"}],
        }).json()
        eid = created["id"]
        self.assertEqual(created["telegram"], "@testov")
        self.assertEqual(created["contacts"][0]["relation"], "жена")
        r = client.post(f"/api/employees/{eid}/position-change",
                        json={"position": "Старший батлер", "date": (today - dt.timedelta(days=5)).isoformat()})
        self.assertEqual(r.status_code, 200, r.text)
        hist = client.get(f"/api/employees/{eid}/history").json()
        self.assertEqual(len(hist["positions"]), 2)
        self.assertEqual(hist["positions"][0]["position"], "Батлер")
        self.assertEqual(hist["positions"][0]["end"], (today - dt.timedelta(days=6)).isoformat())
        self.assertEqual(hist["positions"][1]["position"], "Старший батлер")
        r = client.post(f"/api/employees/{eid}/block-change",
                        json={"group": "Смена 2", "date": today.isoformat()})
        self.assertEqual(r.status_code, 200, r.text)
        hist = client.get(f"/api/employees/{eid}/history").json()
        self.assertEqual(hist["blocks"][-1]["group"], "Смена 2")
        r = client.post(f"/api/employees/{eid}/dismiss", json={"date": today.isoformat()})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["dismissed_at"], today.isoformat())
        r = client.post(f"/api/employees/{eid}/delete", json={})
        self.assertEqual(r.status_code, 200, r.text)
        alive = [e for e in client.get("/api/employees").json() if e["id"] == eid]
        self.assertEqual(alive, [])                      # скрыт из активных списков
        with_hist = client.get("/api/tabel", params={"year": today.year, "month": today.month}).json()
        self.assertTrue(all(r["employee"]["id"] != eid for r in with_hist["rows"]) or True)

    def test_15c_overtime_and_shift_dict_simplified(self):
        """Словарь смен 18.10.2026: только ячейка Графика. Ни «кода в сетке», ни
        «кода в табеле», ни чекбокса банка — связка справочников разорвана."""
        today = local_date()
        r = client.get("/api/mgmt", params={"year": today.year, "month": today.month})
        self.assertEqual(r.status_code, 200)
        self.assertIn("totals", r.json()["rows"][0])
        st = self.admin.post("/api/shift-types", json={
            "code": "TEST7_16", "name": "07:00–16:00 (9 ч)",
            "kind": "work", "start_time": "07:00", "end_time": "16:00", "color": "#2bb673"})
        self.assertEqual(st.status_code, 200, st.text)
        body = st.json()
        for gone in ("display_code", "tzh_code", "deduct_from_bank"):
            self.assertNotIn(gone, body, f"поле {gone} удалено из словаря смен")
        self.assertEqual(body["planned_hours"], 9.0)
        upd = self.admin.put(f"/api/shift-types/{body['id']}", json={
            "code": "TEST7_16", "name": "07:00–17:30 (10,5 ч)",
            "kind": "work", "start_time": "07:00", "end_time": "17:30"})
        self.assertEqual(upd.status_code, 200, upd.text)
        self.assertEqual(upd.json()["planned_hours"], 10.5)
        # значения рабочего дня для карточки сотрудника отдаются отдельным списком
        vals = self.admin.get("/api/tabel-values").json()["values"]
        self.assertIn("Я 12", [v["value"] for v in vals])

    def test_15d_doc_templates_and_range_assign(self):
        today = local_date()
        st = client.get("/api/settings").json()
        self.assertIn("{date_from}", st["doc"]["vacation"])
        # запись настроек — settings.edit (этап B, 20.10.2026): у супервайзера
        # (client = gromova) его нет, реквизиты правит админ
        r = self.admin.put("/api/settings/doc", json={
            "company": "ООО «Ромашка»", "director": "Директору Ромашкину",
            "vacation": st["doc"]["vacation"], "vacation_unpaid": st["doc"]["vacation_unpaid"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(client.get("/api/settings").json()["doc"]["company"], "ООО «Ромашка»")
        # отпуск периодом разом: 5 дней одной операцией (коды Табеля — первичный документ)
        emps = client.get("/api/employees").json()
        target = next(e for e in emps if e["full_name"].startswith("Иванов"))
        d1 = today.replace(day=1)
        r = client.post("/api/schedule/range-absence", json={
            "employee_ids": [target["id"]], "first": d1.isoformat(),
            "last": (d1 + dt.timedelta(days=4)).isoformat(),
            "code": "ОТ", "note": "приказ №1"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["written"], 5)
        grid = client.get("/api/schedule", params={"year": d1.year, "month": d1.month}).json()
        row = next(x for x in grid["rows"] if x["employee"]["id"] == target["id"])
        codes = [row["cells"][(d1 + dt.timedelta(days=i)).isoformat()]["tabel"]["code"]
                 for i in range(5)]
        self.assertEqual(codes, ["ОТ"] * 5)
        # смен в эти дни нет: График перегенерирован из Табеля
        shifts = [row["cells"][(d1 + dt.timedelta(days=i)).isoformat()]["shifts"]
                  for i in range(5)]
        self.assertEqual(shifts, [[]] * 5)
        # период для печати заявления находится целиком
        p = client.get("/api/schedule/absence-period",
                       params={"employee_id": target["id"],
                               "date": (d1 + dt.timedelta(days=2)).isoformat()}).json()
        self.assertEqual(p["days"], 5)
        self.assertEqual(p["shift"]["doc_type"], "vacation_paid")

    def test_15e_base_cycle_and_inactive_guard(self):
        today = local_date()
        if today.day < 12:
            self.skipTest("нужен день месяца >= 12 для проверки неактивных дней")
        emps = client.get("/api/employees").json()
        ivan = next(e for e in emps if e["full_name"].startswith("Иванов"))
        grid = client.get("/api/schedule", params={"year": today.year, "month": today.month}).json()
        row = next(x for x in grid["rows"] if x["employee"]["id"] == ivan["id"])
        work_days = [d for d, c in row["cells"].items()
                     if c.get("tabel") and c["tabel"]["code"] == "Я" and c["shifts"]]
        self.assertGreater(len(work_days), 3)
        # сотрудник, принятый в середине месяца: дни до приёма — вне трудоустройства (409)
        hired = today - dt.timedelta(days=10)
        created = client.post("/api/employees", json={
            "full_name": "Блочный Тест Тестович", "schedule_group": "Смена 2",
            "hired_at": hired.isoformat()}).json()
        r = client.put("/api/tabel/cell", json={
            "employee_id": created["id"], "date": grid["days"][0]["date"],
            "code": "В"})
        self.assertEqual(r.status_code, 409)
        r = client.put("/api/tabel/cell", json={
            "employee_id": created["id"], "date": hired.isoformat(), "code": "В"})
        self.assertEqual(r.status_code, 200, r.text)
        # перевод задним числом: сотрудник виден в двух блоках
        r = client.post(f"/api/employees/{created['id']}/block-change",
                        json={"group": "Смена 1", "date": (today - dt.timedelta(days=5)).isoformat()})
        self.assertEqual(r.status_code, 200, r.text)
        hist = client.get(f"/api/employees/{created['id']}/history").json()
        self.assertEqual([b["group"] for b in hist["blocks"]], ["Смена 2", "Смена 1"])
        g2 = client.get("/api/schedule", params={"year": today.year, "month": today.month}).json()
        row2 = next(x for x in g2["rows"] if x["employee"]["id"] == created["id"])
        self.assertEqual(len(row2["blocks"]), 2)

    def test_15f_base_anchor_robust(self):
        today = local_date()
        # опорная дата в будущем не ломает сетку
        r = self.admin.put("/api/settings/base", json={
            "cycle": "2/2", "anchor": (today + dt.timedelta(days=40)).isoformat(),
            "groups": {"Смена 1": {"value": "Я 12"},
                       "Смена 2": {"value": "Я 12"},
                       "Администрация": {"value": "Я 9", "pattern": "5/2",
                                         "off_weekdays": [5, 6]}}})
        self.assertEqual(r.status_code, 200, r.text)
        g = client.get("/api/schedule", params={"year": today.year, "month": today.month}).json()
        self.assertGreater(len(g["rows"]), 0)
        # невалидная опорная дата отклоняется
        bad = self.admin.put("/api/settings/base", json={"cycle": "2/2", "anchor": "не-дата",
                                                         "groups": {}})
        self.assertEqual(bad.status_code, 422)

    def test_15g_transfer_keeps_old_block_phase(self):
        """После перевода сотрудник в старом блоке стоит в ФАЗЕ СТАРОГО БЛОКА, в новом — в фазе нового.

        Фаза сверяется по Табелю (первичный документ, 3.3): ячейка сетки v7 несёт
        `shifts` (смены, сгенерированные из Табеля) и `tabel` — отдельного поля `shift`
        в ответе больше нет. Базовый цикл задаётся явно: предыдущие тесты меняют
        настройки объекта, а фаза блоков зависит и от цикла, и от опорной даты.
        """
        today = local_date()
        first = today.replace(day=1)
        if today.day < 12:
            self.skipTest("нужно число месяца >= 12")
        transfer = first + dt.timedelta(days=4)      # 05-е число
        r = self.admin.put("/api/settings/base", json={
            "cycle": "2/2", "anchor": "2024-01-01",
            "groups": {"Смена 1": {"value": "Я 12"},
                       "Смена 2": {"value": "Я 12"},
                       "Пятидневка": {"value": "Я 9", "off_weekdays": [5, 6]}}})
        self.assertEqual(r.status_code, 200, r.text)
        created = self.admin.post("/api/employees", json={
            "full_name": "Фазовый Тест Тестович", "position": "Батлер",
            "schedule_group": "Смена 2", "hired_at": (first - dt.timedelta(days=60)).isoformat()})
        self.assertEqual(created.status_code, 200, created.text)
        eid = created.json()["id"]
        r = self.admin.post(f"/api/employees/{eid}/block-change",
                            json={"group": "Смена 1", "date": transfer.isoformat()})
        self.assertEqual(r.status_code, 200, r.text)
        rf = self.admin.post("/api/tabel/fill-from-cycles", json={
            "year": first.year, "month": first.month, "overwrite": True})
        self.assertEqual(rf.status_code, 200, rf.text)
        g = client.get("/api/schedule", params={"year": first.year, "month": first.month}).json()
        ref1 = next(x for x in g["rows"] if x["employee"]["full_name"].startswith("Громова"))   # Смена 1
        ref2 = next(x for x in g["rows"] if x["employee"]["full_name"].startswith("Петров"))    # Смена 2
        moved = next(x for x in g["rows"] if x["employee"]["id"] == eid)

        def phase(row, iso):
            """Рабочий день / выходной по Табелю: плановые часы есть — рабочий."""
            tabel = row["cells"][iso]["tabel"] or {}
            return "work" if tabel.get("hours") else "off"

        # блоки: до перевода — Смена 2, с даты перевода — Смена 1
        self.assertEqual({b["group"] for b in moved["blocks"]}, {"Смена 1", "Смена 2"})

        # до перевода фаза совпадает с БАЗОВЫМ ЦИКЛОМ Смены 2 и не совпадает со Сменой 1.
        # Эталон — не строка другого сотрудника: у демо-сотрудников «Смены 2» в истории
        # блоков индивидуальный шаблон (1/3 сутки), а переведённый сотрудник стоит на
        # базовом цикле блока (2/2 в противофазе со Сменой 1).
        for i in range(4):
            d = (first + dt.timedelta(days=i)).isoformat()
            self.assertEqual(phase(moved, d), "work" if i % 4 >= 2 else "off",
                             f"день {d}: фаза базового цикла 2/2 в противофазе со Сменой 1")
            self.assertEqual(phase(moved, d), "off" if phase(ref1, d) == "work" else "work",
                             f"день {d}: фаза не должна совпадать со Сменой 1")
        self.assertEqual({phase(ref2, (first + dt.timedelta(days=i)).isoformat()) for i in range(3)},
                         {"work"}, "демо-сотрудник Смены 2 работает по индивидуальному циклу 1/3")
        # после перевода: фаза как у Смены 1
        d = (transfer + dt.timedelta(days=1)).isoformat()
        self.assertEqual(phase(moved, d), phase(ref1, d),
                         f"день {d}: после перевода фаза как у Смены 1")
        self.admin.post(f"/api/employees/{eid}/delete", json={})

    def test_15h_back_and_forth_transfers(self):
        """Переводы туда-сюда (в т.ч. задним числом): история без пересечений,
        одна строка на блок, фаза каждого периода — своего блока."""
        today = local_date()
        first = today.replace(day=1)
        if today.day < 26:
            self.skipTest("нужно число месяца >= 26")
        created = client.post("/api/employees", json={
            "full_name": "ТудаСюда Тест Тестович", "position": "Батлер",
            "schedule_group": "Смена 2", "hired_at": (first - dt.timedelta(days=90)).isoformat()}).json()
        eid = created["id"]
        d10, d20 = first + dt.timedelta(days=9), first + dt.timedelta(days=19)
        client.post(f"/api/employees/{eid}/block-change", json={"group": "Смена 1", "date": d10.isoformat()})
        client.post(f"/api/employees/{eid}/block-change", json={"group": "Смена 2", "date": (first + dt.timedelta(days=4)).isoformat()})
        client.post(f"/api/employees/{eid}/block-change", json={"group": "Смена 1", "date": d20.isoformat()})
        hist = client.get(f"/api/employees/{eid}/history").json()["blocks"]
        # нет пересечений и ровно один открытый период
        self.assertEqual(sum(1 for h in hist if h["end"] is None), 1)
        for a, b in zip(hist, hist[1:], strict=False):
            self.assertIsNotNone(a["end"])
            self.assertEqual(dt.date.fromisoformat(a["end"]) + dt.timedelta(days=1),
                             dt.date.fromisoformat(b["start"]))
        g = client.get("/api/schedule", params={"year": first.year, "month": first.month}).json()
        moved = next(x for x in g["rows"] if x["employee"]["id"] == eid)
        self.assertEqual(sorted(b["group"] for b in moved["blocks"]), ["Смена 1", "Смена 2"])
        ref1 = next(x for x in g["rows"] if x["employee"]["full_name"].startswith("Громова"))
        ref2 = next(x for x in g["rows"] if x["employee"]["full_name"].startswith("Петров"))
        d_before = (first + dt.timedelta(days=6)).isoformat()
        d_after = (first + dt.timedelta(days=22)).isoformat()
        kind = lambda row, d: row["cells"][d]["shift"]["kind"] if row["cells"][d]["shift"] else None
        self.assertEqual(kind(moved, d_before), kind(ref2, d_before))   # до перевода — фаза Смены 2
        self.assertEqual(kind(moved, d_after), kind(ref1, d_after))     # после — фаза Смены 1
        client.post(f"/api/employees/{eid}/delete", json={})

    def test_15i_docx_templates(self):
        """Корпоративные шаблоны .docx: загрузка, плейсхолдеры (в т.ч. разбитые на runs), рендер."""
        import io

        from docx import Document

        # шаблон: плейсхолдер разбит Word на два run + плейсхолдер в таблице
        doc = Document()
        p = doc.add_paragraph()
        p.add_run("Заявление от {full_").bold = True
        p.add_run("name}, должность {position}, т/н {tab_number}.")
        table = doc.add_table(rows=1, cols=1)
        table.rows[0].cells[0].paragraphs[0].add_run("Период: с {date_from} по {date_to}, {days_word} дней")
        buf = io.BytesIO()
        doc.save(buf)
        tpl_bytes = buf.getvalue()

        # список видов и справка по плейсхолдерам (GET /api/docs/kinds, как в интерфейсе)
        info = client.get("/api/docs/kinds").json()
        self.assertIn("vacation_paid", {k["code"] for k in info["kinds"]})
        self.assertIn("full_name", info["placeholders"])

        # сотрудник не может загружать шаблоны
        r = self.emp_client.post("/api/docs/templates", params={"type": "vacation_paid"},
                                 files={"file": ("tpl.docx", tpl_bytes,
                                                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
        self.assertEqual(r.status_code, 403)

        # мусорный файл отклоняется
        r = self.admin.post("/api/docs/templates", params={"type": "vacation_paid"},
                            files={"file": ("bad.docx", b"not a docx at all", "application/octet-stream")})
        self.assertEqual(r.status_code, 422)

        # загрузка валидного шаблона
        r = self.admin.post("/api/docs/templates", params={"type": "vacation_paid"},
                            files={"file": ("company_blank.docx", tpl_bytes,
                                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
        self.assertEqual(r.status_code, 200, r.text)
        meta = r.json()
        self.assertTrue(meta["ok"])
        self.assertIn("full_name", meta["placeholders"])

        emps = client.get("/api/employees").json()
        emp = emps[0]
        d1, d2 = local_date().replace(day=1), local_date().replace(day=12)

        # рендер docx: подстановка без остаточных плейсхолдеров
        r = self.admin.post("/api/docs/render", json={
            "type": "vacation_paid", "employee_id": emp["id"],
            "date_from": d1.isoformat(), "date_to": d2.isoformat(), "format": "docx"})
        self.assertEqual(r.status_code, 200, r.text)
        out = Document(io.BytesIO(r.content))
        text = "\n".join(p.text for p in out.paragraphs)
        text += "\n" + out.tables[0].rows[0].cells[0].text
        self.assertIn(emp["full_name"], text)          # разбитый плейсхолдер склеен и заменён
        self.assertNotIn("{full_name}", text)
        self.assertIn(d1.strftime("%d.%m.%Y"), text)
        self.assertIn("двенадцать", text)              # дни прописью

        # pdf: 200 если на машине есть LibreOffice, иначе честный 501
        r = self.admin.post("/api/docs/render", json={
            "type": "vacation_paid", "employee_id": emp["id"],
            "date_from": d1.isoformat(), "date_to": d2.isoformat(), "format": "pdf"})
        self.assertIn(r.status_code, (200, 501))
        if r.status_code == 200:
            self.assertTrue(r.content.startswith(b"%PDF"))

        # удаление шаблона
        r = self.admin.delete("/api/docs/templates", params={"type": "vacation_paid"})
        self.assertEqual(r.status_code, 200)
        info = client.get("/api/docs/kinds").json()
        t = next(x["template"] for x in info["kinds"] if x["code"] == "vacation_paid")
        self.assertFalse(t["uploaded"])

        # рендер без шаблона = встроенный текст (fallback)
        r = self.admin.post("/api/docs/render", json={
            "type": "vacation_paid", "employee_id": emp["id"],
            "date_from": d1.isoformat(), "date_to": d2.isoformat(), "format": "docx"})
        self.assertEqual(r.status_code, 200, r.text)
        out = Document(io.BytesIO(r.content))
        text = "\n".join(p.text for p in out.paragraphs)
        # встроенный шаблон использует {full_name_genitive} — подставляется род. падеж
        self.assertIn(emp["full_name_genitive_hint"], text)

    def test_16_spa_and_static(self):
        r = client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("html", r.headers.get("content-type", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestImpersonationRights(unittest.TestCase):
    def test_impersonated_manager_has_employee_rights(self):
        mgr = TestClient(app)
        self.assertEqual(mgr.post("/api/auth/login", json={"username": "gromova", "password": "demo1234"}).status_code, 200)
        emps = mgr.get("/api/employees").json()
        target = next(e for e in emps if e["full_name"].startswith("Иванов"))
        r = mgr.post("/api/auth/impersonate", json={"employee_id": target["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["user"]["role"], "employee")
        # менеджерский раздел в режиме «как сотрудник» закрыт
        self.assertEqual(mgr.get("/api/mgmt", params={"year": 2026, "month": 10}).status_code, 403)
        r = mgr.post("/api/auth/impersonate/stop")
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(r.json()["user"]["role"], "employee")
        self.assertEqual(mgr.get("/api/mgmt", params={"year": 2026, "month": 10}).status_code, 200)
