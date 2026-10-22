"""Манифест модуля (ADR-0012): что модуль добавляет в приложение."""
from __future__ import annotations

from app.core.manifest import SUPERVISOR_UP, ModuleManifest, Perm, Screen

MODULE = ModuleManifest(
    name="audit", title="Журнал аудита", order=50,
    routers=("app.modules.audit.interface.audit_api:router",),
    permissions=(
        Perm("audit.view", "Журнал аудита",
             "Просмотр журнала аудита", SUPERVISOR_UP),
    ),
    settings_screens=(Screen("audit", "Журнал аудита", 520, "Администрирование", "audit.view",
                             external="audit"),),
)
