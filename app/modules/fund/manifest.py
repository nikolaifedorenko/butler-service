"""Манифест модуля (ADR-0012): что модуль добавляет в приложение.

Права ``stays.*``, строки меню, экраны настроек и подписи аудита шахматки объявляет манифест
``stays``: для пользователя фонд — часть «Шахматки», ключи прав не меняются.
"""
from __future__ import annotations

from app.core.manifest import ModuleManifest

MODULE = ModuleManifest(
    name="fund", title="Фонд", order=74, layer=2,
    routers=("app.modules.fund.interface.fund_api:router",),
    models=("app.modules.fund.adapters.orm",),
)
