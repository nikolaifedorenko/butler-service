"""Сид пустой базы без DEMO_SEED (аудит 21.10.2026, SEC-02): ни демо-сотрудников, ни
известного пароля demo1234 — только справочники и admin с паролем из ADMIN_PASSWORD.

Отдельный процесс со своей SQLite: настройки читаются один раз на процесс."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE = """
from sqlalchemy import func, select
from app.main import init_db
from app.core.db import SessionLocal
from app.core.identity import User
from app.core.security import verify_password
from app.modules.employees.adapters.orm import Employee
from app.modules.timesheet.adapters.orm import ShiftType
init_db()
with SessionLocal() as db:
    users = db.scalars(select(User)).all()
    print([u.username for u in users], db.scalar(select(func.count(Employee.id))),
          db.scalar(select(func.count(ShiftType.id))) > 0,
          verify_password("demo1234", users[0].password_hash),
          verify_password("Admin-Pass-2026", users[0].password_hash))
"""


def _run(tmp_path, **env):
    full = {k: v for k, v in os.environ.items() if k not in ("DEMO_SEED", "ADMIN_PASSWORD")}
    full.update(DATABASE_URL=f"sqlite:///{tmp_path / 'prod.db'}", SECRET_KEY="test-secret-key-0123456789",
                NIGHT_SYNC_ENABLED="0", **env)
    return subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT, env=full,
                          capture_output=True, text=True, timeout=120)


def test_empty_base_without_admin_password_refuses_to_start(tmp_path):
    r = _run(tmp_path)
    assert r.returncode != 0
    assert "ADMIN_PASSWORD" in r.stderr


def test_empty_base_gets_only_admin_from_env(tmp_path):
    r = _run(tmp_path, ADMIN_PASSWORD="Admin-Pass-2026")
    assert r.returncode == 0, r.stderr[-2000:]
    # только admin, ни одного сотрудника, словарь смен на месте, demo1234 не подходит
    assert r.stdout.strip().splitlines()[-1] == "['admin'] 0 True False True"
