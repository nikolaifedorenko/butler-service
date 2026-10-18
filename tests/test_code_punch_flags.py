"""Карточка кода Табеля (решение владельца 16.10.2026): режим отметок и заявление.

Что проверяем:
* app-поля строк day_code_policy (punch_in/punch_out/doc_type) — в стартовом
  наполнении: отпуск «ОТ» и «ДО» не отмечаются и оформляются заявлением,
  «В» отмечается (RUL-ALL-MARKS-COUNTED — работа в выходной даёт переработку);
* сервер СОБЛЮДАЕТ режим отметок (находка 16.10.2026: раньше флаги читал только
  фронтенд): POST /api/punches в день с кодом «ОТ» — 409, корректировка задним
  числом (инструмент менеджера) — разрешена;
* заявление по коду Табеля: absence-period берёт doc_type карточки кода даже
  без привязки словарного вида;
* публикация версии не даёт удалить код, который стоит в Табеле или на который
  ссылается живой вид смены (кнопка «✕» в карточке кода);
* apply_code_app_defaults идемпотентно добирает app-поля в сохранённые версии.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import tempfile
import unittest

_tmp_db = os.path.join(tempfile.gettempdir(), "tt_code_punch.db")
if "DATABASE_URL" not in os.environ:
    if os.path.exists(_tmp_db):
        os.remove(_tmp_db)
    os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"
    os.environ.setdefault("SECRET_KEY", "test-secret-key")

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.deps import local_date, now_local  # noqa: E402
from app.main import app, init_db  # noqa: E402
from app.models import EngineSettingsVersion, ShiftType  # noqa: E402

init_db()
client = TestClient(app)          # администратор
TODAY = local_date()


def _login_into(c: TestClient, username: str) -> TestClient:
    r = c.post("/api/auth/login", json={"username": username, "password": "demo1234"})
    assert r.status_code == 200, r.text
    return c


def _login(username: str) -> TestClient:
    return _login_into(TestClient(app), username)


_login_into(client, "admin")


def _create_employee(username: str, full_name: str, hired: dt.date) -> dict:
    r = client.post("/api/employees", json={
        "full_name": full_name, "position": "Батлер (тест)",
        "hired_at": hired.isoformat(), "schedule_group": "Смена 1",
        "role": "employee", "username": username, "password": "demo1234",
        "nationality": "Российская Федерация", "subdivision": "Служба управления виллами"})
    assert r.status_code == 200, r.text
    return r.json()


_login("admin")


class TestCodePunchFlags(unittest.TestCase):
    emp: dict
    emp_client: TestClient

    @classmethod
    def setUpClass(cls):
        cls.emp = _create_employee("codepunch_emp", "Отпускников Пётр Петрович",
                                   TODAY - dt.timedelta(days=90))
        cls.emp_client = _login("codepunch_emp")
        # сегодня — ежегодный отпуск: назначение на период пишет код «ОТ» в Табель
        r = client.post("/api/schedule/range-absence", json={
            "employee_ids": [cls.emp["id"]], "first": TODAY.isoformat(),
            "last": TODAY.isoformat(), "code": "ОТ", "note": "отпуск на день"})
        assert r.status_code == 200, r.text

    def test_01_payload_app_fields(self):
        """Стартовое наполнение: режим отметок и заявление — app-поля карточки кода."""
        p = client.get("/api/engine-settings").json()["active"]["payload"]
        codes = p["day_code_policy"]
        for code in ("ОТ", "ДО"):
            self.assertFalse(codes[code]["punch_in"], f"«{code}»: приход должен быть запрещён")
            self.assertFalse(codes[code]["punch_out"], f"«{code}»: уход должен быть запрещён")
        self.assertEqual(codes["ОТ"]["doc_type"], "vacation_paid")
        self.assertEqual(codes["ДО"]["doc_type"], "vacation_unpaid")
        for code in ("Я", "К", "В", "Б", "НН"):
            self.assertTrue(codes[code]["punch_in"], f"«{code}»: отметки разрешены по умолчанию")
            self.assertTrue(codes[code]["punch_out"], f"«{code}»: отметки разрешены по умолчанию")

    def test_02_status_reflects_code_flags(self):
        """«Мои отметки»: статус показывает запрет по коду сегодняшнего дня."""
        s = self.emp_client.get("/api/punches/status").json()
        self.assertFalse(s["punch_in_allowed"])
        self.assertFalse(s["punch_out_allowed"])
        self.assertIn("Ежегодный отпуск", s["punch_status_hint"] or "")

    def test_03_server_blocks_punch_on_vacation_day(self):
        """Находка 16.10.2026: прямой запрос к API больше не обходит флаги."""
        r = self.emp_client.post("/api/punches", json={"kind": "auto"})
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("запрещено", r.json()["detail"])
        self.assertIn("Ежегодный отпуск", r.json()["detail"])
        # чужая отметка «сейчас» (менеджер, без ts) — тот же запрет
        r = client.post("/api/punches", json={"kind": "IN", "employee_id": self.emp["id"]})
        self.assertEqual(r.status_code, 409, r.text)

    def test_04_backfill_still_allowed(self):
        """Корректировка задним числом — инструмент менеджера: ограничению не подлежит."""
        ts = (now_local() - dt.timedelta(hours=1)).isoformat(timespec="minutes")
        r = client.post("/api/punches", json={
            "kind": "IN", "employee_id": self.emp["id"], "ts": ts,
            "note": "корректировка"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["backfill"])

    def test_05_absence_period_doc_from_code_card(self):
        """Заявление по коду Табеля: doc_type карточки кода первее привязки вида."""
        r = client.get("/api/schedule/absence-period",
                       params={"employee_id": self.emp["id"], "date": TODAY.isoformat()})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["source"], "tabel_code")
        self.assertEqual(r.json()["doc_type"], "vacation_paid")
        # видов отсутствий в словаре с 18.10.2026 нет: карточка кода — единственный
        # источник шаблона заявления для отсутствий Табеля

    def test_06_work_code_allows_punch(self):
        """Явка «Я»: отметки разрешены (регресс — запрет не «расползается» на все дни)."""
        r = client.put("/api/tabel/cell", json={
            "employee_id": self.emp["id"], "date": TODAY.isoformat(),
            "code": "Я", "hours": 12})
        self.assertEqual(r.status_code, 200, r.text)
        s = self.emp_client.get("/api/punches/status").json()
        self.assertTrue(s["punch_in_allowed"])
        self.assertTrue(s["punch_out_allowed"])
        # сессия открыта корректировкой (test_04) — «auto» закрывает её уходом
        r = self.emp_client.post("/api/punches", json={"kind": "auto"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["punch"]["kind"], "OUT")

    def test_07_publish_guard_removal(self):
        """Публикация версии: код из Табеля / от живой смены удалить нельзя."""
        from app.api.engine_settings_api import _guard_removed_day_codes

        base = client.get("/api/engine-settings").json()["active"]["payload"]
        db = SessionLocal()
        try:
            # без изъятий — проходит
            _guard_removed_day_codes(copy.deepcopy(base), db)
            # «Я» стоит в Табеле демо-сотрудников
            p = copy.deepcopy(base)
            p["day_code_policy"].pop("Я")
            with self.assertRaises(HTTPException) as ctx:
                _guard_removed_day_codes(p, db)
            self.assertEqual(ctx.exception.status_code, 422)
            self.assertIn("«Я»", ctx.exception.detail)
            self.assertIn("Табел", ctx.exception.detail)
            # связка со словарём смен удалена (18.10.2026): второй предохранитель —
            # только история Табеля, видов отсутствий в словаре больше нет
        finally:
            db.close()

    def test_08_apply_code_app_defaults_idempotent(self):
        """apply_code_app_defaults добирает недостающие app-поля и не трогает остальные."""
        from app.engine_bootstrap import apply_code_app_defaults

        db = SessionLocal()
        try:
            ver = db.scalars(select(EngineSettingsVersion)
                             .order_by(EngineSettingsVersion.valid_from.desc(),
                                       EngineSettingsVersion.id.desc())).first()
            assert ver is not None
            payload = json.loads(ver.payload_json)
            row = payload["day_code_policy"]["ОТ"]
            row.pop("punch_in", None)
            row.pop("doc_type", None)
            ver.payload_json = json.dumps(payload, ensure_ascii=False)
            db.flush()
            self.assertGreaterEqual(apply_code_app_defaults(db), 1)
            row = json.loads(ver.payload_json)["day_code_policy"]["ОТ"]
            self.assertFalse(row["punch_in"])
            self.assertEqual(row["doc_type"], "vacation_paid")
            self.assertFalse(row["punch_out"], "существующее значение не перезаписано")
            self.assertEqual(apply_code_app_defaults(db), 0, "второй вызов — без изменений")
        finally:
            db.rollback()   # тестовая правка версии не должна остаться в базе
            db.close()


if __name__ == "__main__":
    unittest.main()
