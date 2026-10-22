"""Манифест модуля (ADR-0012): что модуль добавляет в приложение."""
from __future__ import annotations

from app.core.manifest import ADMIN_ONLY, ModuleManifest, Perm, Screen

MODULE = ModuleManifest(
    name="access", title="Вход и права доступа", order=40,
    routers=("app.modules.access.interface.auth_routes:router", "app.modules.access.interface.access_api:router"),
    permissions=(
        Perm("access.manage", "Права доступа",
             "Управление правами доступа", ADMIN_ONLY),
    ),
    audit_actions={
        "login": "Вход",
        "logout": "Выход",
        "access_role": "Права роли",
        "access_group_create": "Группа доступа: создана",
        "access_group_update": "Группа доступа: изменена",
        "access_group_delete": "Группа доступа: удалена",
        "access_group_grants": "Права группы",
        "access_group_members": "Состав группы",
        "access_user_grants": "Индивидуальные права",
        "access_role_create": "Роль: создана",
        "access_role_update": "Роль: изменена",
        "access_role_delete": "Роль: удалена",
    },
    settings_screens=(Screen("access", "Права доступа", 510, "Администрирование", "access.manage",
                             external="access"),),
)
