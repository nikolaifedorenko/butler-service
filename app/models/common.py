"""Общие константы и утилиты модели: роли пользователей, utcnow()."""
from __future__ import annotations

import datetime as dt

# ───────────────────────────────────────── роли ─────────────────────────────────────────
ROLE_ADMIN = "admin"          # полный доступ; сам в график не встаёт и не работает
ROLE_MANAGER = "manager"      # права как у admin, но сам может стоять в графике и работать
ROLE_SUPERVISOR = "supervisor"# как manager, но не может создавать/удалять/править supervisor
ROLE_EMPLOYEE = "employee"    # только свои отметки, описания и история своих действий

MANAGER_ROLES = (ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERVISOR)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


