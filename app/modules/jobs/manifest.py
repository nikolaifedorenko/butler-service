"""Манифест модуля (ADR-0012): что модуль добавляет в приложение."""
from __future__ import annotations

from app.core.manifest import ModuleManifest

MODULE = ModuleManifest(name="jobs", title="Очередь задач", order=13, layer=1,
                        models=("app.modules.jobs.adapters.orm",))
