"""Манифест модуля (ADR-0012): что модуль добавляет в приложение."""
from __future__ import annotations

from app.core.manifest import ModuleManifest

MODULE = ModuleManifest(name="exchange", title="Импорт и экспорт файлов", order=12, layer=1)
