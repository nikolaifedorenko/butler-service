"""Манифест модуля (ADR-0012): что модуль добавляет в приложение.

Права ``stays.*``, меню и подписи аудита объявляет манифест ``stays``: для пользователя табло —
часть «Шахматки», ключи прав не меняются.
"""
from __future__ import annotations

from app.core.manifest import ModuleManifest

MODULE = ModuleManifest(
    name="board", title="Табло", order=76, layer=5,
    routers=("app.modules.board.interface.views_api:router",
             "app.modules.board.interface.boards_api:router",
             "app.modules.board.interface.bookings_api:router",
             "app.modules.board.interface.export_api:router",
             "app.modules.board.interface.guests_read_api:router"),
)
