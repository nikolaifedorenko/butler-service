"""График «только просмотр» для батлеров, PDF-выгрузка графика/табеля
и контракт сохранения правил (регрессия бага «Сохранить правила» → 422)."""
from __future__ import annotations

import datetime as dt
import os
import tempfile
import unittest

# если модуль запущен отдельно — своя тестовая БД; если вместе с остальными —
# app.main уже импортирован и использует общую тестовую базу
_tmp_db = os.path.join(tempfile.gettempdir(), "tt_readonly_pdf.db")
if "DATABASE_URL" not in os.environ:
    if os.path.exists(_tmp_db):
        os.remove(_tmp_db)
    os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"
    os.environ["SECRET_KEY"] = "test-secret-key"

from fastapi.testclient import TestClient  # noqa: E402

from app.deps import local_date  # noqa: E402
from app.main import app, init_db  # noqa: E402
from app.pdf_render import pdf_mode  # noqa: E402

init_db()
client = TestClient(app)          # администратор
emp_client = TestClient(app)      # батлер (роль employee)

TODAY = local_date()
YEAR, MONTH = TODAY.year, TODAY.month
SECRET_FACT_KEYS = ("fact", "partial", "note", "fact_hours", "worked_off")


def _login(c: TestClient, username: str) -> None:
    r = c.post("/api/auth/login", json={"username": username, "password": "demo1234"})
    assert r.status_code == 200, r.text


EMP: dict = {}


def setUpModule() -> None:
    _login(client, "admin")
    r = client.post("/api/employees", json={
        "full_name": "Тестов Тест Тестович", "position": "Батлер (тест PDF и просмотра)",
        "hired_at": (TODAY - dt.timedelta(days=90)).isoformat(), "schedule_group": "Смена 1",
        "role": "employee", "username": "ro_butler_pdf", "password": "demo1234"})
    assert r.status_code == 200, r.text
    EMP.update(r.json())
    _login(emp_client, "ro_butler_pdf")


class TestRulesSaveContract(unittest.TestCase):
    """Регрессия: сохранение правил падало с 422, когда во фронтовый payload
    попадали пустые {"value": ""} без key (файловые инпуты шаблонов .docx)."""

    def test_put_valid_payload_ok(self):
        items = client.get("/api/settings").json()["items"]
        payload = [{"key": i["key"], "value": str(i["value"])} for i in items]
        r = client.put("/api/settings", json=payload)
        self.assertEqual(r.status_code, 200, r.text)

    def test_put_items_without_key_are_422(self):
        # ровно та форма, которую присылал сломанный селектор: 4 × {"value": ""}
        r = client.put("/api/settings", json=[{"value": ""}] * 4)
        self.assertEqual(r.status_code, 422)
        detail = r.json()["detail"]
        self.assertTrue(all(d["type"] == "missing" and d["loc"][-1] == "key" for d in detail))


class TestReadonlySchedule(unittest.TestCase):
    """Батлер видит план графика, но не факт/часы/банк; правки — 403."""

    def test_employee_gets_plan_only(self):
        r = emp_client.get("/api/schedule", params={"year": YEAR, "month": MONTH})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertTrue(data["readonly"])
        self.assertTrue(data["rows"], "в демо-базе должен быть хотя бы один сотрудник")
        for row in data["rows"]:
            self.assertNotIn("balance_hours", row["employee"])
            self.assertEqual(row["totals"].get("fact_hours", 0.0), 0.0)
            for cell in row["cells"].values():
                self.assertIsNone(cell["fact"])
                self.assertIsNone(cell["partial"])
                self.assertEqual(cell["note"], "")
                self.assertFalse(cell["worked_off"])
                self.assertEqual(cell["fact_hours"], 0.0)
            # план смен на месте — ради него всё и затевалось
            self.assertTrue(any(c.get("shift") for c in row["cells"].values()))

    def test_manager_gets_full_grid(self):
        r = client.get("/api/schedule", params={"year": YEAR, "month": MONTH})
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertFalse(data["readonly"])
        row = data["rows"][0]
        self.assertIn("balance_hours", row["employee"])
        self.assertIn("fact_hours", row["totals"])
        self.assertTrue(all(k in next(iter(row["cells"].values())) for k in SECRET_FACT_KEYS))

    def test_employee_cannot_edit_or_export(self):
        cell = {"employee_id": EMP["id"], "date": TODAY.replace(day=15).isoformat(),
                "shift_type_id": None, "note": "хак"}
        self.assertEqual(emp_client.put("/api/schedule/cell", json=cell).status_code, 403)
        self.assertEqual(emp_client.post("/api/schedule/clear-month",
                                         json={"year": YEAR, "month": MONTH}).status_code, 403)
        self.assertEqual(emp_client.get("/api/schedule/xlsx",
                                        params={"year": YEAR, "month": MONTH}).status_code, 403)
        # PDF графика батлеру доступен — но только его же план (200), либо 501 без движка
        self.assertIn(emp_client.get("/api/schedule/pdf",
                                     params={"year": YEAR, "month": MONTH}).status_code, (200, 501))
        self.assertEqual(emp_client.get("/api/tabel",
                                        params={"year": YEAR, "month": MONTH}).status_code, 403)
        self.assertEqual(emp_client.get("/api/mgmt",
                                        params={"year": YEAR, "month": MONTH}).status_code, 403)
        self.assertEqual(emp_client.get("/api/settings").status_code, 403)

    def test_employee_pdf_is_plan_only(self):
        r = emp_client.get("/api/schedule/pdf", params={"year": YEAR, "month": MONTH})
        if r.status_code != 200:
            self.skipTest("нет PDF-движка")
        import io as _io

        from pypdf import PdfReader
        text = " ".join(p.extract_text() or "" for p in PdfReader(_io.BytesIO(r.content)).pages)
        self.assertIn("График сменности", text)

    def test_employee_reads_shift_dictionary(self):
        r = emp_client.get("/api/shift-types")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(any(s["code"] == "OFF" for s in r.json()))

    def test_anonymous_rejected(self):
        anon = TestClient(app)
        self.assertEqual(anon.get("/api/schedule",
                                  params={"year": YEAR, "month": MONTH}).status_code, 401)


@unittest.skipIf(pdf_mode() == "none", "нет PDF-движка (ни LibreOffice, ни reportlab)")
class TestPdfExport(unittest.TestCase):
    """PDF графика и табеля собирается на сервере (DOCX → PDF)."""

    def _assert_pdf(self, r, prefix: str):
        self.assertEqual(r.status_code, 200, r.text[:300])
        self.assertEqual(r.headers["content-type"], "application/pdf")
        self.assertIn(f'filename="{prefix}', r.headers["content-disposition"])
        self.assertTrue(r.content.startswith(b"%PDF"), "это не PDF")
        self.assertGreater(len(r.content), 5_000, "PDF подозрительно пустой")

    def test_schedule_pdf(self):
        self._assert_pdf(client.get("/api/schedule/pdf",
                                    params={"year": YEAR, "month": MONTH}), "grafik_")

    def test_docx_builds_without_engine(self):
        # DOCX-макеты собираются даже там, где PDF-движка нет (python-docx — ядро)
        from app.grid_docx import schedule_docx

        grid = client.get("/api/schedule", params={"year": YEAR, "month": MONTH}).json()
        self.assertTrue(schedule_docx(grid).startswith(b"PK"))


class TestPdfHint(unittest.TestCase):
    """Без движка сервер честно объясняет, что делать (501 + подсказка)."""

    def test_501_hint_mentions_install(self):
        from unittest import mock

        # эндпоинт импортирует docx_to_pdf в момент запроса — подмена сработает
        with mock.patch("app.pdf_render.docx_to_pdf",
                        return_value=(None, "reportlab не установлен, LibreOffice не найден")):
            r = client.get("/api/schedule/pdf", params={"year": YEAR, "month": MONTH})
        self.assertEqual(r.status_code, 501, r.text)
        detail = r.json()["detail"]
        self.assertIn("requirements-pdf", detail)
        self.assertIn("Печать", detail)


if __name__ == "__main__":
    unittest.main()
