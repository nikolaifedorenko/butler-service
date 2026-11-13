"""Манифест модуля (ADR-0012): что модуль добавляет в приложение."""
from __future__ import annotations

from app.core.manifest import ModuleManifest

MODULE = ModuleManifest(
    name="people", title="Люди", order=15, layer=1,
    models=("app.modules.people.adapters.orm",),
)
