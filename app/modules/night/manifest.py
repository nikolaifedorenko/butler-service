"""Манифест модуля (ADR-0012): что модуль добавляет в приложение."""
from __future__ import annotations

from app.core.manifest import EVERYONE, SUPERVISOR_UP, MenuItem, ModuleManifest, NotifyDomain, Perm, Screen

MODULE = ModuleManifest(
    name="night", title="Ночной отчёт", order=60,
    routers=("app.modules.night.interface.night_api:router",),
    models=("app.modules.night.adapters.orm",),
    permissions=(
        Perm("night.view", "Ночной отчёт",
             "Ночной отчёт", EVERYONE),
        Perm("night.dispatch", "Ночной отчёт",
             "Отправка недостатков службам", EVERYONE),
        Perm("night.edit", "Ночной отчёт",
             "Зоны, объекты, чек-листы, службы", SUPERVISOR_UP),
        Perm("night.close", "Ночной отчёт",
             "Закрытие и переоткрытие смены/объектов", SUPERVISOR_UP),
        Perm("night.reopen_any", "Ночной отчёт",
             "Переоткрыть чужую закрытую область обхода", SUPERVISOR_UP),
    ),
    notify_domains={
        "night": NotifyDomain(
            title="Ночной отчёт — недостатки смены",
            template=("Ночной отчёт · смена {date} · {shift}\n"
                      "{service}: прошу исправить:\n"
                      "{items}\n"
                      "\n"
                      "Ночные батлеры смены: {duty}\n"
                      "Отметил: {author}, {time}. Фото и видео — во вложении."),
            placeholders=("{date}", "{shift}", "{service}", "{items}", "{duty}", "{author}", "{time}")),
    },
    menu=(MenuItem("night", "Ночной отчёт", 50, ("night.view",)),),
    settings_screens=(Screen("night", "Ночной обход", 310, "Объект", "night.view"),),
)
