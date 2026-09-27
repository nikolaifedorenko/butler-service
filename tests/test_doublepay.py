"""Дни двойной оплаты: производственный календарь (сменные/пятидневка), ВИП-гости,
коды ДЯ2/ДН2 в реестре к выплате и списания «вполовину» из двойных часов."""
from __future__ import annotations

import datetime as dt
import os
import tempfile
import unittest

# если модуль запущен отдельно — своя тестовая БД; если вместе с остальными —
# app.main уже импортирован и использует общую тестовую базу
_tmp_db = os.path.join(tempfile.gettempdir(), "tt_doublepay.db")
if "DATABASE_URL" not in os.environ:
    if os.path.exists(_tmp_db):
        os.remove(_tmp_db)
    os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"
    os.environ["SECRET_KEY"] = "test-secret-key"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app, init_db  # noqa: E402
from app.deps import local_date  # noqa: E402
from app.timesheet import settle_overtime  # noqa: E402

init_db()
client = TestClient(app)          # администратор
sup = TestClient(app)             # супервайзер
emp_client = TestClient(app)      # сотрудник

TODAY = local_date()
# оба дня в одном месяце и гарантированно в прошлом
_LAST_MONTH_END = TODAY.replace(day=1) - dt.timedelta(days=1)
DAY_A = _LAST_MONTH_END - dt.timedelta(days=6)   # день с двойной переработкой
DAY_B = _LAST_MONTH_END - dt.timedelta(days=5)   # день со списанием (ранний уход)
MONTH = (DAY_A.year, DAY_A.month)


def _login(c: TestClient, username: str) -> None:
    r = c.post("/api/auth/login", json={"username": username, "password": "demo1234"})
    assert r.status_code == 200, r.text


def _create_employee(username: str, full_name: str, group: str = "Смена 1") -> dict:
    r = client.post("/api/employees", json={
        "full_name": full_name, "position": "Батлер (тест двойной оплаты)",
        "hired_at": (TODAY - dt.timedelta(days=120)).isoformat(), "schedule_group": group,
        "role": "employee", "username": username, "password": "demo1234"})
    assert r.status_code == 200, r.text
    return r.json()


def _shift_id(code: str) -> int:
    for s in client.get("/api/shift-types").json():
        if s["code"] == code:
            return s["id"]
    raise AssertionError(f"смена {code} не найдена")


def _set_cell(emp_id: int, day: dt.date, shift_id) -> None:
    r = client.put("/api/schedule/cell", json={
        "employee_id": emp_id, "date": day.isoformat(),
        "shift_type_id": shift_id, "note": ""})
    assert r.status_code == 200, r.text


def _punch(emp_id: int, day: dt.date, hm_in: str, hm_out: str) -> None:
    for kind, hm in (("in", hm_in), ("out", hm_out)):
        r = client.post("/api/punches", json={
            "kind": kind, "employee_id": emp_id, "ts": f"{day.isoformat()}T{hm}"})
        assert r.status_code == 200, r.text


def _overtime(emp_id: int) -> dict:
    r = client.get("/api/timesheet/overtime", params={"year": MONTH[0], "month": MONTH[1]})
    assert r.status_code == 200, r.text
    for row in r.json()["rows"]:
        if row["employee"]["id"] == emp_id:
            return row
    raise AssertionError("сотрудник не найден в реестре переработок")


def _mark_day(day: dt.date, scope: str, note: str = "тест") -> dict:
    r = client.post("/api/doublepay/days", json={
        "dates": day.isoformat(), "scope": scope, "note": note})
    assert r.status_code == 200, r.text
    return r.json()


def _unmark_day(day: dt.date) -> None:
    r = client.get("/api/doublepay", params={"year": day.year})
    assert r.status_code == 200, r.text
    for d in r.json()["days"]:
        if d["date"] == day.isoformat():
            assert client.delete(f"/api/doublepay/days/{d['id']}").status_code == 200
            return
    raise AssertionError("день не найден в календаре")


class TestDoublePay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _login(client, "admin")
        _login(sup, "gromova")
        _login(emp_client, "ivanov")
        cls.off = _shift_id("OFF")
        cls.day12 = _shift_id("DAY12")
        # сменщик 2/2: DAY_A — работа в «выходной» 09:00–17:00 (8 ч переработки, все дневные)
        cls.emp_shift = _create_employee("dp_shift", "Двойнов Дбл Двойнович", "Смена 1")
        # пятидневка: те же отметки в DAY_A
        cls.emp_week5 = _create_employee("dp_week5", "Пятидневкин Пд Пдвич", "Пятидневка")
        # сотрудник для ВИП-теста
        cls.emp_vip = _create_employee("dp_vip", "Випов Вип Випович", "Смена 1")

    # ── 0. доступ: супервайзер и сотрудник не могут менять календарь оплаты ──
    def test_00_permissions(self):
        self.assertEqual(sup.get("/api/doublepay").status_code, 200)      # смотреть можно
        self.assertEqual(emp_client.get("/api/doublepay").status_code, 403)
        r = sup.post("/api/doublepay/days", json={"dates": "2030-01-01", "scope": "all"})
        self.assertEqual(r.status_code, 403)
        r = sup.post("/api/doublepay/vip", json={
            "employee_id": self.emp_shift["id"], "start_date": "2030-01-01",
            "end_date": "2030-01-02"})
        self.assertEqual(r.status_code, 403)

    # ── 1. календарь: день отмечен ПОСЛЕ отметок → точечный пересчёт, ДЯ2 ──
    def test_01_calendar_shift_scope(self):
        e = self.emp_shift["id"]
        _set_cell(e, DAY_A, self.off)
        _punch(e, DAY_A, "09:00", "17:00")
        # до отметки дня в календаре — обычные 8 ч ДЯ
        t = _overtime(e)["totals"]
        self.assertEqual((t["credit_dya"], t["credit_dya2"]), (8.0, 0.0))
        self.assertEqual(t["pay_total"], 8.0)

        res = _mark_day(DAY_A, "shift", "праздник из производственного календаря")
        self.assertEqual(res["added"], 1)
        self.assertGreaterEqual(res["recalculated"], 1)

        row = _overtime(e)
        t = row["totals"]
        self.assertEqual((t["credit_dya"], t["credit_dya2"]), (0.0, 8.0))
        self.assertEqual(t["pay_total"], 16.0)          # 8 ч ДЯ2 = 16 одинарных к выплате
        self.assertEqual(t["pay_hours"], 8.0)
        self.assertEqual(row["credits"][0]["dya2"], 8.0)

        # маркеры в табеле и в шапке сетки графика
        r = client.get("/api/timesheet", params={"year": MONTH[0], "month": MONTH[1],
                                                 "employee_id": e})
        day = [d for d in r.json()["rows"][0]["days"] if d["date"] == DAY_A.isoformat()][0]
        self.assertTrue(day["is_double"])
        self.assertEqual(day["double_reason"], "calendar")
        g = client.get("/api/schedule", params={"year": DAY_A.year, "month": DAY_A.month}).json()
        gd = [d for d in g["days"] if d["date"] == DAY_A.isoformat()][0]
        self.assertEqual(gd["double_scope"], "shift")

    # ── 2. scope: список сменщиков НЕ действует на пятидневку и наоборот ──
    def test_02_scope_week5(self):
        w = self.emp_week5["id"]
        _set_cell(w, DAY_A, self.off)
        _punch(w, DAY_A, "10:00", "12:00")
        t = _overtime(w)["totals"]
        self.assertEqual((t["credit_dya"], t["credit_dya2"]), (2.0, 0.0),
                         "день отмечен только для сменщиков — пятидневку не затрагивает")
        # отмечаем тот же день для пятидневки (существующая дата обновляется)
        res = client.post("/api/doublepay/days", json={
            "dates": DAY_A.isoformat(), "scope": "all", "note": "праздник для всех"})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["updated"], 1)
        t = _overtime(w)["totals"]
        self.assertEqual((t["credit_dya"], t["credit_dya2"]), (0.0, 2.0))
        self.assertEqual(t["pay_total"], 4.0)

    # ── 3. списание из двойных часов — ВПОЛОВИНУ (8 оплаты = 4 ч ДЯ2) ──
    def test_03_debit_halved_from_double(self):
        e = self.emp_shift["id"]
        # DAY_B: плановая смена 08:00–20:00, ушёл в 16:00 → списание 4 ч
        _set_cell(e, DAY_B, self.day12)
        _punch(e, DAY_B, "08:00", "16:00")
        row = _overtime(e)
        t = row["totals"]
        self.assertEqual(t["debit"], 4.0)
        # 4 ч оплаты съедают 2 ч ДЯ2: осталось 6 ч ДЯ2 (= 12 одинарных)
        self.assertEqual((t["pay_dya2"], t["pay_total"]), (6.0, 12.0))
        log_double = [l for l in row["log"] if l["from"] == "ДЯ2"]
        self.assertTrue(log_double)
        self.assertEqual(log_double[0]["hours"], 4.0)          # снято оплаты (одинарных)
        self.assertEqual(log_double[0]["credit_hours"], 2.0)   # снято часов кода ДЯ2

    # ── 4. ранний уход в двойной день гасится часами ОБЫЧНОГО дня 1=1 ──
    def test_04_debit_from_regular_one_to_one(self):
        w = self.emp_week5["id"]
        # DAY_A-2: обычный день (не в календаре), работа в выходной 09:00–13:00 → 4 ч ДЯ
        reg = DAY_A - dt.timedelta(days=2)
        _set_cell(w, reg, self.off)
        _punch(w, reg, "09:00", "13:00")
        # DAY_B: день уже двойной (отмечен в тесте 2), план 08:00–20:00, ушёл в 16:00
        _set_cell(w, DAY_B, self.day12)
        _punch(w, DAY_B, "08:00", "16:00")
        row = _overtime(w)
        t = row["totals"]
        self.assertEqual(t["debit"], 4.0)
        # списание 4 ч полностью легло на обычные ДЯ раннего дня (1=1); двойные не тронуты
        self.assertEqual((t["pay_dya"], t["pay_dya2"], t["pay_total"]), (0.0, 2.0, 4.0))
        log_reg = [l for l in row["log"] if l["from"] == "ДЯ"]
        self.assertTrue(log_reg)
        self.assertEqual(log_reg[0]["credit_hours"], 4.0)      # 1=1
        self.assertEqual(log_reg[0]["credit_date"], reg.isoformat())

    # ── 5. ВИП-гость: двойные переработки в обычный день; с календарём не перемножается ──
    def test_05_vip_union_no_multiplication(self):
        v = self.emp_vip["id"]
        day = DAY_A - dt.timedelta(days=1)       # обычный день (не в календаре)
        _set_cell(v, day, self.off)
        _punch(v, day, "10:00", "14:00")
        t = _overtime(v)["totals"]
        self.assertEqual((t["credit_dya"], t["credit_dya2"]), (4.0, 0.0))

        r = client.post("/api/doublepay/vip", json={
            "employee_id": v, "start_date": day.isoformat(),
            "end_date": (day + dt.timedelta(days=2)).isoformat(),
            "note": "ВИП-гость: мистер Смит, вилла №4"})
        self.assertEqual(r.status_code, 200, r.text)
        item = r.json()["item"]
        self.assertEqual(item["days"], 3)
        row = _overtime(v)
        t = row["totals"]
        self.assertEqual((t["credit_dya"], t["credit_dya2"]), (0.0, 4.0))
        self.assertEqual(t["pay_total"], 8.0)

        # день и в календаре, и в ВИП-периоде → всё равно ×2, не ×4
        _mark_day(day, "all", "совпал с праздником")
        t = _overtime(v)["totals"]
        self.assertEqual(t["credit_dya2"], 4.0)
        self.assertEqual(t["pay_total"], 8.0)
        r = client.get("/api/timesheet", params={"year": MONTH[0], "month": MONTH[1],
                                                 "employee_id": v})
        d = [x for x in r.json()["rows"][0]["days"] if x["date"] == day.isoformat()][0]
        self.assertEqual(d["double_reason"], "vip")   # ВИП важнее для подписи

        # удалили ВИП → день остался двойным по календарю
        r = client.delete(f"/api/doublepay/vip/{item['id']}")
        self.assertEqual(r.status_code, 200, r.text)
        t = _overtime(v)["totals"]
        self.assertEqual(t["credit_dya2"], 4.0)

        # убрали и из календаря → снова обычные ДЯ
        _unmark_day(day)
        t = _overtime(v)["totals"]
        self.assertEqual((t["credit_dya"], t["credit_dya2"]), (4.0, 0.0))
        self.assertEqual(t["pay_total"], 4.0)

    # ── 6. массовое добавление периодом с фильтром по дням недели ──
    def test_06_bulk_range_weekdays(self):
        r = client.post("/api/doublepay/days", json={
            "start": "2027-06-01", "end": "2027-06-30", "weekdays": [5],
            "scope": "week5", "note": "субботы июня (пятидневка)"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["added"], 4)   # 5, 12, 19, 26 июня 2027 — субботы
        r = client.get("/api/doublepay", params={"year": 2027})
        days = r.json()["days"]
        self.assertEqual(len(days), 4)
        self.assertTrue(all(d["weekday"] == "сб" and d["scope"] == "week5" for d in days))
        # список дат строкой в разных форматах
        r = client.post("/api/doublepay/days", json={
            "dates": "2027-01-01, 07.01.2027 08.01.2027", "scope": "all",
            "note": "Новогодние каникулы"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["added"], 3)
        # мусор в датах — понятная ошибка
        r = client.post("/api/doublepay/days", json={"dates": "позавчера", "scope": "all"})
        self.assertEqual(r.status_code, 422)

    # ── 7. юнит: долг прошлых периодов тоже съедает двойные часы вполовину ──
    def test_07_settle_debt_halved(self):
        credits = [{"date": "2026-10-05", "dya2": 6.0, "dn2": 0.0}]
        debits = [{"date": "2026-09-10", "hours": 4.0, "kind": "Выходной за часы"}]
        log, remain, totals = settle_overtime(credits, debits)
        self.assertEqual(totals["debt_out"], 0.0)
        self.assertEqual(totals["pay_dya2"], 4.0)     # долг 4 ч оплаты снял 2 ч ДЯ2
        self.assertEqual(totals["pay_total"], 8.0)
        dbl_log = [l for l in log if l["from"] == "ДЯ2"]
        self.assertEqual((dbl_log[0]["hours"], dbl_log[0]["credit_hours"]), (4.0, 2.0))

    # ── 8. юнит: порядок списания — обычные часы раньше двойных ──
    def test_08_settle_regular_first(self):
        credits = [{"date": "2026-09-01", "dya2": 4.0},          # двойной день раньше
                   {"date": "2026-09-02", "dya": 4.0}]           # обычный позже
        debits = [{"date": "2026-09-05", "hours": 4.0, "kind": "Отгул"}]
        _, remain, totals = settle_overtime(credits, debits)
        # списание съело обычные ДЯ (1=1), двойные часы не тронуты
        self.assertEqual(totals["pay_dya2"], 4.0)
        self.assertEqual(totals["pay_dya"], 0.0)
        self.assertEqual(totals["pay_total"], 8.0)
        self.assertEqual([r["date"] for r in remain], ["2026-09-01"])

    # ── 9. экспорт в учёт зарплаты: коды ДЯ2 в CSV ──
    def test_09_payroll_csv_contains_dya2(self):
        r = client.get("/api/timesheet/csv",
                       params={"year": MONTH[0], "month": MONTH[1], "mode": "payroll"})
        self.assertEqual(r.status_code, 200)
        text = r.content.decode("utf-8-sig")
        self.assertIn("ДЯ2", text.splitlines()[0])
        self.assertIn("Двойнов Дбл Двойнович", text)
        line = [l for l in text.splitlines() if l.startswith("Двойнов")][0]
        self.assertIn("ДЯ2 6", line)


if __name__ == "__main__":
    unittest.main()
