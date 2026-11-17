"""Манифест модуля (ADR-0012): что модуль добавляет в приложение.

Права ``stays.*``, меню, экраны настроек и подписи аудита гостей объявляет манифест ``stays``: для
пользователя гости — часть «Шахматки», ключи прав не меняются. Роутера у модуля нет.
"""
from __future__ import annotations

from app.core.manifest import ModuleManifest

MODULE = ModuleManifest(
    name="guests", title="Гости", order=74, layer=3,
    models=("app.modules.guests.adapters.orm",),
)
