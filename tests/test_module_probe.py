"""Пробный модуль: механизм манифестов (ADR-0012, шаг 5.4) подключает новый модуль без правки
существующих файлов. Решение владельца 22.10.2026: пилот «Гости» пропущен, вместо него — этот
тест. Модуль живёт во временной папке и подключается только в отдельном процессе со своей
базой, поэтому в меню приложения и в каталоге прав основного прогона его нет.

Проверяется, что из одного manifest.py модуль получает: маршрут под своим правом, модель в
метаданных, право в каталоге с ролями по умолчанию, название действия в журнале аудита,
раздел уведомлений, пункт меню и экран Настроек в /api/auth/me — только у тех, кому положено.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import textwrap

ROOT = pathlib.Path(__file__).resolve().parents[1]

PROBE = {
    "__init__.py": "",
    "manifest.py": """
        from app.core.manifest import SUPERVISOR_UP, MenuItem, ModuleManifest, NotifyDomain, Perm, Screen

        MODULE = ModuleManifest(
            name="probe", title="Пробный модуль", order=95,
            routers=("app.modules.probe.api:router",),
            models=("app.modules.probe.orm",),
            permissions=(Perm("probe.view", "Проба", "Просмотр пробы", SUPERVISOR_UP),),
            audit_actions={"probe_ping": "Проба: пинг"},
            notify_domains={"probe": NotifyDomain("Проба — сообщения", "Проба {date}", ("{date}",))},
            menu=(MenuItem("probe", "Проба", 65, ("probe.view",)),),
            settings_screens=(Screen("probe", "Проба", 335, "Объект", "probe.view"),),
        )
    """,
    "orm.py": """
        from sqlalchemy.orm import Mapped, mapped_column

        from app.core.db import Base


        class ProbeItem(Base):
            __tablename__ = "probe_items"
            id: Mapped[int] = mapped_column(primary_key=True)
    """,
    "api.py": """
        from fastapi import APIRouter, Depends
        from sqlalchemy.orm import Session

        from app.core.audit import audit
        from app.core.auth import Principal
        from app.core.db import get_db
        from app.core.permissions import require_perm

        router = APIRouter(prefix="/api/probe", tags=["probe"])


        @router.post("/ping")
        def ping(principal: Principal = Depends(require_perm("probe.view")), db: Session = Depends(get_db)):
            audit(db, principal, "probe_ping")
            db.commit()
            return {"ok": True}
    """,
}

RUN = """
import json, sys
import app.modules
app.modules.__path__.append(sys.argv[1])          # модуль-проба рядом с настоящими

from fastapi.testclient import TestClient

from app.core.db import Base
from app.main import app, init_db

init_db()


def login(username):
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"username": username, "password": "demo1234"}).status_code == 200
    return c


admin, supervisor, employee = login("admin"), login("gromova"), login("ivanov")
access = admin.get("/api/access").json()
me = {name: c.get("/api/auth/me").json() for name, c in
      (("admin", admin), ("supervisor", supervisor), ("employee", employee))}
print(json.dumps({
    "ping": [c.post("/api/probe/ping").status_code for c in (admin, supervisor, employee)],
    "table": "probe_items" in Base.metadata.tables,
    "catalog": [p for p in access["permissions"] if p["key"] == "probe.view"],
    "defaults": {r["role"]: "probe.view" in r["defaults"] for r in access["roles"] if r["builtin"]},
    "audit": admin.get("/api/audit").json()["actions"],
    "notify": admin.get("/api/notify/config").json()["domains"].get("probe"),
    "menu": {k: [i["id"] for i in v["menu"]] for k, v in me.items()},
    "screens": {k: [s["id"] for s in v["settings_screens"]] for k, v in me.items()},
}))
"""


def test_probe_module_plugs_in_from_manifest_alone(tmp_path):
    pkg = tmp_path / "modules" / "probe"
    pkg.mkdir(parents=True)
    for name, body in PROBE.items():
        (pkg / name).write_text(textwrap.dedent(body), encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(ROOT), "SECRET_KEY": "probe-test-secret",
           "DATABASE_URL": f"sqlite:///{tmp_path / 'probe.db'}", "DEMO_SEED": "1",
           "CSRF_ENABLED": "0", "APP_TZ": "Europe/Moscow"}
    res = subprocess.run([sys.executable, "-c", RUN, str(pkg.parent)], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=180)
    assert res.returncode == 0, res.stderr[-3000:]
    out = json.loads(res.stdout.strip().splitlines()[-1])

    assert out["ping"] == [200, 200, 403]
    # модель зарегистрирована; таблицу создаёт ревизия Alembic (общий каталог — ADR-0012, «не сделано»)
    assert out["table"]
    assert out["catalog"] == [{"key": "probe.view", "section": "Проба", "title": "Просмотр пробы"}]
    assert out["defaults"] == {"admin": True, "manager": True, "supervisor": True, "employee": False}
    assert {"action": "probe_ping", "title": "Проба: пинг"} in out["audit"]
    assert out["notify"] == "Проба — сообщения"
    # пункт меню — между «Электрокарами» (60) и «Настройками» (70), экран — в группе «Объект»
    assert out["menu"]["admin"][-3:] == ["cars", "probe", "settings"]
    assert "probe" in out["menu"]["supervisor"] and "probe" not in out["menu"]["employee"]
    assert out["screens"]["admin"][7:11] == ["night", "cars", "docs", "probe"]
    assert "probe" not in out["screens"]["employee"]
