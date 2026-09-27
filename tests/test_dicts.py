"""Справочники «Департаменты» и «Службы/подразделения»: CRUD, влияние на карточки,
права доступа, бэкфилл из существующих значений при миграции."""
from __future__ import annotations

import os
import tempfile
import unittest

tmp_db = os.path.join(tempfile.gettempdir(), "tt_test_dicts.db")
if os.path.exists(tmp_db):
    os.remove(tmp_db)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tmp_db}")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app, init_db, migrate_db  # noqa: E402

init_db()
client = TestClient(app)

DEP = "Департамент тест справочников"
SUB = "Служба тест справочников"
EMP = "Справочников Тест Спринтович"


class TestDicts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r = client.post("/api/auth/login", json={"username": "admin", "password": "demo1234"})
        assert r.status_code == 200, r.text
        cls.emp_client = TestClient(app)
        r = cls.emp_client.post("/api/auth/login", json={"username": "ivanov", "password": "demo1234"})
        assert r.status_code == 200, r.text

    # ── департаменты ──
    def test_01_department_crud(self):
        r = client.post("/api/departments", json={"name": DEP})
        self.assertEqual(r.status_code, 200, r.text)
        dep_id = r.json()["id"]

        dup = client.post("/api/departments", json={"name": DEP})
        self.assertEqual(dup.status_code, 409)

        empty = client.post("/api/departments", json={"name": "   "})
        self.assertEqual(empty.status_code, 422)

        r = client.put(f"/api/departments/{dep_id}", json={"name": DEP + " 2"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["name"], DEP + " 2")

        names = [d["name"] for d in client.get("/api/departments").json()]
        self.assertIn(DEP + " 2", names)
        self.__class__.dep_id = dep_id

    def test_02_department_delete_unlinks_employee(self):
        r = client.post("/api/employees", json={
            "full_name": EMP, "department_id": self.dep_id, "subdivision": SUB})
        self.assertEqual(r.status_code, 200, r.text)
        emp_id = r.json()["id"]
        self.__class__.emp_id = emp_id

        r = client.delete(f"/api/departments/{self.dep_id}")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["unlinked_employees"], 1)

        emp = next(e for e in client.get("/api/employees").json() if e["id"] == emp_id)
        self.assertEqual(emp.get("department") or "", "")

        again = client.delete(f"/api/departments/{self.dep_id}")
        self.assertEqual(again.status_code, 404)

    # ── службы/подразделения ──
    def test_03_subdivision_crud(self):
        r = client.post("/api/subdivisions", json={"name": SUB})
        self.assertEqual(r.status_code, 200, r.text)
        sub_id = r.json()["id"]

        dup = client.post("/api/subdivisions", json={"name": SUB})
        self.assertEqual(dup.status_code, 409)

        # переименование обновляет карточку сотрудника
        r = client.put(f"/api/subdivisions/{sub_id}", json={"name": SUB + " 2"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["employees_updated"], 1)
        emp = next(e for e in client.get("/api/employees").json() if e["id"] == self.emp_id)
        self.assertEqual(emp["subdivision"], SUB + " 2")

        # удаление очищает поле у сотрудника
        r = client.delete(f"/api/subdivisions/{sub_id}")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["employees_cleared"], 1)
        emp = next(e for e in client.get("/api/employees").json() if e["id"] == self.emp_id)
        self.assertEqual(emp["subdivision"], "")

    def test_04_subdivision_backfill_on_migrate(self):
        """Значение из карточки, которого нет в справочнике, попадает туда при миграции."""
        from sqlalchemy import select

        from app.db import SessionLocal
        from app.models import Employee, Subdivision

        db = SessionLocal()
        try:
            emp = db.get(Employee, self.emp_id)
            emp.subdivision = "Служба ручного бэкфилла"
            db.commit()
            existed = db.scalar(select(Subdivision).where(
                Subdivision.name == "Служба ручного бэкфилла"))
            self.assertIsNone(existed)
        finally:
            db.close()

        migrate_db()

        names = [s["name"] for s in client.get("/api/subdivisions").json()]
        self.assertIn("Служба ручного бэкфилла", names)

        # вторая миграция не дублирует
        migrate_db()
        names = [s["name"] for s in client.get("/api/subdivisions").json()]
        self.assertEqual(names.count("Служба ручного бэкфилла"), 1)

    # ── права ──
    def test_05_employee_forbidden(self):
        for call in (
            lambda: self.emp_client.post("/api/subdivisions", json={"name": "x"}),
            lambda: self.emp_client.put("/api/subdivisions/1", json={"name": "x"}),
            lambda: self.emp_client.delete("/api/subdivisions/1"),
            lambda: self.emp_client.post("/api/departments", json={"name": "x"}),
            lambda: self.emp_client.put("/api/departments/1", json={"name": "x"}),
            lambda: self.emp_client.delete("/api/departments/1"),
        ):
            self.assertEqual(call().status_code, 403)

    # ── уборка за собой (БД может быть общей с другими тест-модулями) ──
    def test_99_cleanup(self):
        r = client.post(f"/api/employees/{self.emp_id}/delete")
        self.assertEqual(r.status_code, 200, r.text)
        for s in client.get("/api/subdivisions").json():
            if s["name"].startswith(SUB):
                client.delete(f"/api/subdivisions/{s['id']}")


if __name__ == "__main__":
    unittest.main()
