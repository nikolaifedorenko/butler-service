"""Манифест модуля (ADR-0012): что модуль добавляет в приложение."""
from __future__ import annotations

from app.core.manifest import ModuleManifest

MODULE = ModuleManifest(
    name="notify", title="Уведомления: Telegram и почта", order=90,
    routers=("app.modules.notify.interface.notify_api:router",),
    models=("app.modules.notify.adapters.orm",),
)
