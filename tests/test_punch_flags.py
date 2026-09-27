"""Флаги «можно ли жать Пришёл/Ушёл» у вида смены/отсутствия + override в ячейке и периоде:
запрет блокирует отметку сотрудника (409 «Сейчас статус: …»), менеджерские корректировки
не блокируются, override ячейки/периода перекрывает словарь."""
from __future__ import annotations

import datetime as dt
import os
import tempfile
import unittest

tmp_db = os.path.join(tempfile.gettempdir(), "tt_test_punchflags.db")
if os.path.exists(tmp_db):
    os.remove(tmp_db)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tmp_db}")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from fastapi.testclient import TestClient  # noqa: E402

from app.deps import local_date  # noqa: E402
from app.main import app, init_db  # noqa: E402

init_db()
client = TestClient(app)          # без логина — для проверок 401 не используется
admin = TestClient(app)
emp = TestClient(app)

assert admin.post("/api/auth/login", json={"username": "admin", "password": "demo1234"}).status_code == 200
# Соколова — «Пятидневка» (дневная смена): вчерашнее окно не «перетягивает» план на себя в любое время суток
assert emp.post("/api/auth/login", json={"username": "sokolova", "password": "demo1234"}).status_code == 200

EMP_ID = emp.get("/api/auth/me").json()["user"]["employee_id"]
TODAY = local_date()
CODE = "NOPUNCH_TEST"


class TestPunchFlags(unittest.TestCase):
    shift_id = None
    punch_ids: list[int] = []

    # ── 01. словарь: вид отсутствия с запрещёнными отметками ──
    def test_01_create_shift_with_flags(self):
        r = admin.post("/api/shift-types", json={
            "code": CODE, "name": "Тест: без отметок", "short_code": "НТ",
            "kind": "absence", "is_working": False, "counts_as_worked": False,
            "punch_in_allowed": False, "punch_out_allowed": False,
        })
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertFalse(d["punch_in_allowed"])
        self.assertFalse(d["punch_out_allowed"])
        TestPunchFlags.shift_id = d["id"]

    # ── 02. назначение на сегодня: статус и отметка сотрудника заблокированы ──
    def test_02_employee_blocked(self):
        r = admin.put("/api/schedule/cell", json={
            "employee_id": EMP_ID, "date": TODAY.isoformat(), "shift_type_id": self.shift_id})
        self.assertEqual(r.status_code, 200, r.text)

        s = emp.get("/api/punches/status").json()
        self.assertEqual(s["plan_date"], TODAY.isoformat())   # план — именно сегодня
        self.assertFalse(s["punch_in_allowed"])
        self.assertFalse(s["punch_out_allowed"])

        r = emp.post("/api/punches", json={"kind": "auto"})
        self.assertEqual(r.status_code, 409)
        self.assertIn("Сейчас статус", r.json()["detail"])

    # ── 03. override ячейки: приход разрешён, уход по-прежнему нет ──
    def test_03_cell_override(self):
        r = admin.put("/api/schedule/cell", json={
            "employee_id": EMP_ID, "date": TODAY.isoformat(), "shift_type_id": self.shift_id,
            "punch_in_override": True})
        self.assertEqual(r.status_code, 200, r.text)
        cell = r.json()["cell"]
        self.assertTrue(cell["punch_in_override"])
        self.assertIsNone(cell["punch_out_override"])

        s = emp.get("/api/punches/status").json()
        self.assertTrue(s["punch_in_allowed"])
        self.assertFalse(s["punch_out_allowed"])

        r = emp.post("/api/punches", json={"kind": "auto"})   # → IN
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["punch"]["kind"], "IN")
        TestPunchFlags.punch_ids.append(r.json()["punch"]["id"])

        r = emp.post("/api/punches", json={"kind": "out"})    # → OUT, запрещён
        self.assertEqual(r.status_code, 409)
        self.assertIn("Ушёл", r.json()["detail"])

    # ── 04. менеджер не блокируется (ручная отметка за сотрудника) ──
    def test_04_manager_bypass(self):
        r = admin.post("/api/punches", json={"kind": "OUT", "employee_id": EMP_ID})
        self.assertEqual(r.status_code, 200, r.text)
        TestPunchFlags.punch_ids.append(r.json()["punch"]["id"])

    # ── 05. override на период (range-absence) ──
    def test_05_range_override(self):
        start = TODAY + dt.timedelta(days=10)
        end = TODAY + dt.timedelta(days=12)
        r = admin.post("/api/schedule/range-absence", json={
            "employee_ids": [EMP_ID], "start": start.isoformat(), "end": end.isoformat(),
            "shift_type_id": self.shift_id, "note": "тест периода",
            "punch_in_override": False, "punch_out_override": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["updated"], 3)

        for d in (start, end):
            grid = admin.get("/api/schedule", params={"year": d.year, "month": d.month}).json()
            row = next(x for x in grid["rows"] if x["employee"]["id"] == EMP_ID)
            c = row["cells"][d.isoformat()]
            self.assertIs(c["punch_in_override"], False)
            self.assertIs(c["punch_out_override"], True)
        TestPunchFlags.range_cells = [(start + dt.timedelta(days=i)).isoformat() for i in range(3)]

    # ── 99. уборка: отметки, ячейки, архивация тестовой смены ──
    def test_99_cleanup(self):
        for pid in self.punch_ids:
            r = admin.delete(f"/api/punches/{pid}")
            self.assertEqual(r.status_code, 200, r.text)
        for date in [TODAY.isoformat()] + getattr(self, "range_cells", []):
            y, m, _ = (int(x) for x in date.split("-"))
            admin.put("/api/schedule/cell", json={
                "employee_id": EMP_ID, "date": date, "shift_type_id": None, "note": ""})
            admin.post("/api/timesheet/recalc", json={"year": y, "month": m, "employee_ids": [EMP_ID]})
        r = admin.delete(f"/api/shift-types/{self.shift_id}")
        self.assertEqual(r.status_code, 200, r.text)

        s = emp.get("/api/punches/status").json()
        self.assertTrue(s["punch_in_allowed"])   # базовая смена — отметки разрешены


if __name__ == "__main__":
    unittest.main()
