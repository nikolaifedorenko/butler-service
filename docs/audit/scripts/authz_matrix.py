"""Матрица «роль × маршрут» запуском (временная SQLite с демо-сидом).

Для каждой роли — свежая копия базы. Параметры пути подставляются несуществующими
(999999), тело — пустой JSON: 403 означает отказ по правам, 401 — нет входа,
остальные коды (404/409/422/200) — проверка прав пройдена. Маршруты с сетевыми
побочными эффектами (Telegram/SMTP) и выходом/имперсонацией пропускаются.

    .venv/bin/python docs/audit/scripts/authz_matrix.py > docs/audit/03b-authz-run.md
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
TMP = Path(tempfile.mkdtemp(prefix="audit-authz-"))
DB = TMP / "authz.db"
os.environ.update(DATABASE_URL=f"sqlite:///{DB}", SECRET_KEY="audit-secret-key-0123456789",
                  CSRF_ENABLED="0", ALLOW_IMPERSONATION="1", NIGHT_SYNC_ENABLED="0", DEMO_SEED="1")

from fastapi.testclient import TestClient  # noqa: E402
from routes_inventory import collect  # noqa: E402

from app.core.db import engine  # noqa: E402
from app.core.permissions import ROLE_DEFAULTS  # noqa: E402
from app.main import app, init_db  # noqa: E402

init_db()
engine.dispose()
PRISTINE = TMP / "pristine.db"
shutil.copy(DB, PRISTINE)

SKIP = re.compile(r"^/api/auth/(logout|login|login-form|impersonate|change-password)|"
                  r"/telegram/|/email/test|/dispatch$|/resend$")
USERS = {"admin": "admin", "manager": "smirnov", "supervisor": "gromova", "employee": "ivanov",
         "impersonated": "smirnov"}


def run_role(role: str, routes: list[dict]) -> dict:
    engine.dispose()
    for suf in ("-wal", "-shm"):
        Path(str(DB) + suf).unlink(missing_ok=True)
    shutil.copy(PRISTINE, DB)
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"username": USERS[role], "password": "demo1234"}).status_code == 200
    if role == "impersonated":
        emp = c.get("/api/auth/employees-for-demo").json()[3]["id"]
        assert c.post("/api/auth/impersonate", json={"employee_id": emp}).status_code == 200
    res = {}
    for r in routes:
        path = re.sub(r"\{[^}]+\}", "999999", r["path"])
        if "{full_path" in r["path"] or not r["path"].startswith("/api/") or SKIP.search(r["path"]):
            continue
        kw = {"json": {}} if r["method"] in ("POST", "PUT", "PATCH") else {}
        try:
            res[(r["method"], r["path"])] = c.request(r["method"], path, **kw).status_code
        except Exception as exc:  # noqa: BLE001
            res[(r["method"], r["path"])] = f"ERR {type(exc).__name__}"
    return res


def expected(r: dict, role: str):
    """Чего ждём по каталогу: True — пропустить, False — 403, None — правило не из каталога."""
    a = r["auth"]
    if not a or not a[0].startswith("perm:"):
        return None
    keys = a[0][5:].split("|")
    base = ROLE_DEFAULTS["employee" if role == "impersonated" else role]
    return any(k in base for k in keys)


def main():
    routes = collect()
    roles = list(USERS)
    data = {role: run_role(role, routes) for role in roles}
    print("# 03b. Матрица «роль × маршрут» запуском (сгенерировано `docs/audit/scripts/authz_matrix.py`)\n")
    print("Свежая копия демо-базы на роль; id в пути — 999999, тело — `{}`. **403** — отказ по правам; "
          "прочие коды — права пройдены (дальше 404/422/409 от валидации). Пропущены выход, вход, "
          "имперсонация, смена пароля и маршруты с отправкой в Telegram/почту. "
          "⚠ — поведение расходится с каталогом `ROLE_DEFAULTS` (роль в теле обработчика, "
          "или маршрут без `require_perm`).\n")
    print("| Метод | Путь | Авторизация | " + " | ".join(roles) + " |")
    print("|---|---|---|" + "---|" * len(roles))
    mismatches = []
    for r in routes:
        key = (r["method"], r["path"])
        if key not in data["admin"]:
            continue
        cells = []
        for role in roles:
            code = data[role][key]
            exp = expected(r, role)
            flag = ""
            if exp is not None and isinstance(code, int):
                if exp and code == 403 or not exp and code != 403:
                    flag = " ⚠"
                    mismatches.append((r, role, code))
            cells.append(f"{code}{flag}")
        auth = ", ".join(r["auth"])
        print(f"| {r['method']} | `{r['path']}` | `{auth}` | " + " | ".join(cells) + " |")
    print(f"\n**Расхождений с каталогом: {len(mismatches)}**\n")
    for r, role, code in mismatches:
        print(f"- {role}: `{r['method']} {r['path']}` → {code} (по каталогу `{r['auth'][0]}`) — "
              f"`{r['file']}:{r['line']}`")
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
