"""Матрица «роль × маршрут» (аудит 22.10.2026, ARCH-03, шаг 3.5 PLAN.md).

Для каждого маршрута с require_perm ожидание берётся из каталога прав: пользователь
проходит, если у него есть хотя бы один ключ каждой зависимости require_perm маршрута
(эффективные права — роль по умолчанию, группы и индивидуальные гранты).

Обработчики при этом не выполняются, и демо-данные не меняются: целые параметры пути —
«x», тело — `[{}]`, обязательные query не передаются. FastAPI решает зависимости
(require_perm → 403) раньше проверки входных данных (→ 422). Без такой остановки
проходят только GET-маршруты, а это чтение.
"""
from __future__ import annotations

import re

import pytest
from fastapi.routing import APIRoute

SKIP = re.compile(r"/telegram/")          # обращение к Telegram при пройденном гейте
USERS = ("admin", "smirnov", "gromova", "ivanov")      # admin · manager · supervisor · employee


def _flat(routes):
    for r in routes:
        ctx = getattr(r, "include_context", None)       # FastAPI ≥ 0.150: _IncludedRouter
        if ctx is not None:
            yield from _flat(ctx.included_router.routes)
        else:
            yield r


def _gates(dependant) -> list[tuple[str, ...]]:
    out = []
    for d in dependant.dependencies:
        if getattr(d.call, "__qualname__", "").startswith("require_perm."):
            out.append(next(c.cell_contents for c in d.call.__closure__
                            if isinstance(c.cell_contents, tuple)))
        else:
            out += _gates(d)
    return out


def _routes(app):
    rows = []
    for r in _flat(app.routes):
        if isinstance(r, APIRoute) and r.path.startswith("/api/") and not SKIP.search(r.path):
            gates = _gates(r.dependant)
            if gates:
                rows += [(m, r.path, gates) for m in sorted(r.methods - {"HEAD"})]
    return rows


def _run(app_stack, db, username: str) -> list[str]:
    from sqlalchemy import func, select

    from app.core.audit import AuditLog
    from app.core.identity import User
    from app.core.permissions import effective_permissions
    from tests.conftest import _login

    user = db.scalar(select(User).where(User.username == username))
    perms = effective_permissions(db, user.id, user.role)
    client = _login(app_stack["app"], username)
    audit_before = db.scalar(select(func.count(AuditLog.id)))
    wrong = []
    for method, path, gates in _routes(app_stack["app"]):
        kw = {"json": [{}]} if method in ("POST", "PUT", "PATCH") else {}
        code = client.request(method, re.sub(r"\{[^}]+\}", "x", path), **kw).status_code
        allowed = all(any(k in perms for k in gate) for gate in gates)
        if code == 401 or (code == 403) == allowed:
            wrong.append(f"{username}: {method} {path} → {code}, по каталогу "
                         f"{'можно' if allowed else 'нельзя'} ({gates})")
    if db.scalar(select(func.count(AuditLog.id))) != audit_before:
        wrong.append("обработчик записи выполнился: в журнале аудита новые строки")
    return wrong


@pytest.mark.parametrize("username", USERS)
def test_rol_x_marshrut_po_katalogu(app_stack, db, username):
    assert _run(app_stack, db, username) == []


def test_individualnye_granty_rabotayut_na_vseh_marshrutah(app_stack, db, admin_client):
    """Индивидуальные deny и allow супервайзера действуют на каждом маршруте с их ключами."""
    uid = next(u["id"] for u in admin_client.get("/api/access").json()["users"]
               if u["username"] == "gromova")
    grants = {"night.view": "deny", "cars.use": "deny", "schedule.view": "deny",
              "settings.doublepay": "allow", "cars.maintenance": "allow"}
    assert admin_client.put(f"/api/access/users/{uid}/grants",
                            json={"grants": grants}).status_code == 200
    try:
        assert _run(app_stack, db, "gromova") == []
    finally:
        admin_client.put(f"/api/access/users/{uid}/grants", json={"grants": {}})
