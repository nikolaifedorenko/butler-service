"""Число SQL-запросов, время и число расчётов прав на GET-экранах — на демо-штате
(11 сотрудников) и после добавления +60 сотрудников. Временная SQLite, демо-сид.

    .venv/bin/python docs/audit/scripts/query_budget_scan.py > docs/audit/16b-query-budget.md
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="audit-perf-"))
os.environ.update(DATABASE_URL=f"sqlite:///{TMP / 'perf.db'}", SECRET_KEY="audit-secret-key-0123456789",
                  CSRF_ENABLED="0", NIGHT_SYNC_ENABLED="0", DEMO_SEED="1")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402

import app.core.permissions as perms_mod  # noqa: E402
from app.core.db import SessionLocal, engine  # noqa: E402
from app.core.time import local_date  # noqa: E402
from app.main import app, init_db  # noqa: E402

init_db()
today = local_date()
Y, M = today.year, today.month
SCREENS = [
    ("/api/auth/me", {}), ("/api/employees", {}), ("/api/schedule", {"year": Y, "month": M}),
    ("/api/tabel", {"year": Y, "month": M}), ("/api/mgmt", {"year": Y, "month": M}),
    ("/api/presence/board", {}), ("/api/fact/month", {"year": Y, "month": M}),
    ("/api/fact/sessions", {"date": today.isoformat()}), ("/api/punches", {"year": Y, "month": M}),
    ("/api/night/today", {}), ("/api/night/reports", {}), ("/api/night/zones", {}),
    ("/api/cars", {}), ("/api/cars/meta", {}), ("/api/audit", {}), ("/api/access", {}),
    ("/api/engine-settings", {}), ("/api/engine-settings/health", {}), ("/api/settings", {}),
    ("/api/notify/dispatches", {}), ("/api/doublepay", {}), ("/api/docs/kinds", {}),
    ("/api/schedule/xlsx", {"year": Y, "month": M}), ("/api/mgmt/xlsx", {"year": Y, "month": M}),
]

counter = {"q": 0}


@event.listens_for(engine, "before_cursor_execute")
def _count(*_a, **_k):
    counter["q"] += 1


perm_calls = {"n": 0}
_orig = perms_mod.effective_permissions


def _wrapped(*a, **k):
    perm_calls["n"] += 1
    return _orig(*a, **k)


perms_mod.effective_permissions = _wrapped


def measure(c: TestClient) -> dict:
    out = {}
    for path, params in SCREENS:
        counter["q"] = 0
        perm_calls["n"] = 0
        t = time.perf_counter()
        r = c.get(path, params=params)
        out[path] = (r.status_code, counter["q"], round((time.perf_counter() - t) * 1000), perm_calls["n"],
                     len(r.content))
    return out


def add_staff(n: int) -> None:
    from app.core.identity import User
    from app.core.security import hash_password
    from app.modules.employees.adapters.orm import Employee
    from app.modules.employees.application.employment import open_period
    h = hash_password("x" * 12)
    with SessionLocal() as db:
        for i in range(n):
            e = Employee(full_name=f"Тестов{i} Иван Иванович", short_name=f"Тестов{i} И.И.", position="Батлер",
                         hired_at=dt.date(today.year, 1, 1), schedule_group="Смена 1")
            db.add(e)
            db.flush()
            open_period(db, e, e.hired_at, note="аудит", user_id=None)
            db.add(User(username=f"perf{i}", password_hash=h, role="employee", employee_id=e.id))
        db.commit()


def main():
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"username": "smirnov", "password": "demo1234"}).status_code == 200
    measure(c)                      # прогрев (ленивое построение схем FastAPI)
    base = measure(c)
    add_staff(60)
    more = measure(c)
    print("# 16b. Бюджет SQL-запросов на экранах (сгенерировано `docs/audit/scripts/query_budget_scan.py`)\n")
    print("Роль manager (`smirnov`), временная SQLite с демо-сидом. «Права» — сколько раз за запрос "
          "вызывается `effective_permissions` (3–4 SQL каждый). «+60» — после добавления 60 сотрудников "
          "без отметок и смен (рост запросов на сотрудника = N+1).\n")
    print("| Экран | Код | SQL (11 сотр.) | SQL (+60) | Δ на сотрудника | мс (11) | мс (+60) | Права | Ответ, КБ (+60) |")
    print("|---|---|---|---|---|---|---|---|---|")
    for path, _ in SCREENS:
        s0, q0, t0, p0, _b0 = base[path]
        s1, q1, t1, p1, b1 = more[path]
        print(f"| `{path}` | {s0}/{s1} | {q0} | {q1} | {(q1 - q0) / 60:.1f} | {t0} | {t1} | {p0} | {b1 // 1024} |")


if __name__ == "__main__":
    main()
