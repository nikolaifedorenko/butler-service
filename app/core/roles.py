"""Роли пользователей — константы идентификации (ядро, R5).

Перенесено из app/models/common.py (фаза C1, 20.10.2026): роли нужны core.auth,
core.permissions и core.auth_guards, поэтому живут в core, а не в моделях.
"""
from __future__ import annotations

ROLE_ADMIN = "admin"          # полный доступ; сам в график не встаёт и не работает
ROLE_MANAGER = "manager"      # права как у admin, но сам может стоять в графике и работать
ROLE_SUPERVISOR = "supervisor"  # как manager, но не может создавать/удалять/править supervisor
ROLE_EMPLOYEE = "employee"    # только свои отметки, описания и история своих действий

MANAGER_ROLES = (ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERVISOR)

# Встроенные роли с уровнями (ADR-0011) — данные, а не код: их заводит ревизия 0007
# (свой снимок, не зависящий от будущих правок), дальше они живут в таблице roles.
