"""Манифест модуля (ADR-0012): что модуль добавляет в приложение."""
from __future__ import annotations

from app.core.manifest import ModuleManifest

MODULE = ModuleManifest(
    name="docs", title="Заявления и бланки", order=80,
    routers=("app.modules.docs.interface.docs_api:router",),
)
