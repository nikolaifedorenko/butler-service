"""Манифест модуля (ADR-0012): что модуль добавляет в приложение."""
from __future__ import annotations

from app.core.manifest import MANAGER_UP, SUPERVISOR_UP, MenuItem, ModuleManifest, Perm

MODULE = ModuleManifest(
    name="employees", title="Сотрудники", order=20,
    routers=("app.modules.employees.interface.employees:router",),
    models=("app.modules.employees.adapters.orm",),
    permissions=(
        Perm("employees.view", "Сотрудники",
             "Просмотр сотрудников", SUPERVISOR_UP),
        Perm("employees.edit", "Сотрудники",
             "Редактирование сотрудников", SUPERVISOR_UP),
        Perm("employees.bank", "Сотрудники",
             "Корректировка банка часов", MANAGER_UP),
        Perm("employees.impersonate", "Сотрудники",
             "Войти как сотрудник (имперсонация)", SUPERVISOR_UP),
    ),
    menu=(MenuItem("employees", "Сотрудники", 30, ("employees.view",)),),
)
