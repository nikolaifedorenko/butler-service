"""Манифест модуля (ADR-0012): что модуль добавляет в приложение."""
from __future__ import annotations

from app.core.manifest import (
    EVERYONE,
    MANAGER_UP,
    SUPERVISOR_UP,
    MenuItem,
    ModuleManifest,
    NotifyDomain,
    Perm,
    Screen,
)

MODULE = ModuleManifest(
    name="cars", title="Электрокары", order=70,
    routers=("app.modules.cars.interface.cars_api:router",),
    models=("app.modules.cars.adapters.orm",),
    permissions=(
        Perm("cars.view", "Электрокары",
             "Просмотр парка и истории", EVERYONE),
        Perm("cars.use", "Электрокары",
             "Взять / вернуть / передать кар", EVERYONE),
        Perm("cars.override", "Электрокары",
             "Передать или вернуть чужой кар", SUPERVISOR_UP),
        Perm("cars.issue", "Электрокары",
             "Выдать, закрепить, сменить статус", SUPERVISOR_UP),
        Perm("cars.maintenance", "Электрокары",
             "Поставить на обслуживание и снять с него", MANAGER_UP),
        Perm("cars.manage", "Электрокары",
             "Парк и места стоянки: создание, правка, удаление", MANAGER_UP),
    ),
    notify_domains={
        "cars": NotifyDomain(
            title="Электрокары — замечания при возврате",
            template=("Электрокары · {date}\n"
                      "Замечания при возврате кара №{car} ({service}):\n"
                      "{items}\n"
                      "\n"
                      "Отметил: {author}, {time}. Фото — во вложении."),
            placeholders=("{date}", "{service}", "{car}", "{items}", "{author}", "{time}")),
    },
    menu=(MenuItem("cars", "Электрокары", 60, ("cars.view",)),),
    settings_screens=(Screen("cars", "Электрокары", 320, "Объект", "cars.view"),),
)
