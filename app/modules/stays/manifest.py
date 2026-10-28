"""Манифест модуля (ADR-0012): что модуль добавляет в приложение."""
from __future__ import annotations

from app.core.manifest import (
    ADMIN_ONLY,
    EVERYONE,
    MANAGER_UP,
    SUPERVISOR_UP,
    MenuItem,
    ModuleManifest,
    Perm,
    Screen,
)

_S = "Шахматка"

MODULE = ModuleManifest(
    name="stays", title="Шахматка", order=75,
    routers=("app.modules.stays.interface.fund_api:router",
             "app.modules.stays.interface.fund_versions_api:router",
             "app.modules.stays.interface.guests_api:router",
             "app.modules.stays.interface.reservations_api:router",
             "app.modules.stays.interface.views_api:router",
             "app.modules.stays.interface.coverage_api:router",
             "app.modules.stays.interface.boards_api:router",
             "app.modules.stays.interface.export_api:router",
             "app.modules.stays.interface.bookings_api:router"),
    models=("app.modules.stays.adapters.orm",),
    permissions=(
        # без персональных данных — только своей ролью «Загрузка без гостей» (§7–§8)
        Perm("stays.occupancy", _S, "Загрузка без данных гостей", ADMIN_ONLY),
        Perm("stays.view", _S, "Шахматки, табло и загрузка с фамилиями", SUPERVISOR_UP),
        Perm("stays.edit", _S, "Брони, состав гостей, блоки и статусы", SUPERVISOR_UP),
        Perm("stays.edit_mine", _S, "Правка своих броней: состав, логистика, сведения о гостях",
             EVERYONE),
        Perm("stays.assign", _S, "Назначение батлеров, шаблоны, подбор и подмена", SUPERVISOR_UP),
        Perm("stays.guests", _S, "Профили гостей целиком: телефоны, даты рождения, предпочтения",
             SUPERVISOR_UP),
        Perm("stays.mine", _S, "Экран «Мои гости»", EVERYONE),
        Perm("stays.setup", _S, "Фонд, веса, настраиваемые поля, сопровождение, метки", MANAGER_UP),
        Perm("stays.export", _S, "Выгрузка в Excel", MANAGER_UP),
        Perm("stays.reset", _S, "Сброс данных шахматки (брони, гости, фонд) до запуска в работу", ADMIN_ONLY),
    ),
    audit_actions={
        "stays_fund": "Шахматка: справочник фонда",
        "stays_fund_version": "Шахматка: версия фонда",
        "stays_fund_import": "Шахматка: импорт фонда",
        "stays_reset": "Шахматка: сброс данных",
        "stays_guest": "Шахматка: профиль гостя",
        "stays_guest_link": "Шахматка: связь гостей",
        "stays_reservation": "Шахматка: бронь",
        "stays_reservation_status": "Шахматка: статус брони",
        "stays_hold": "Шахматка: блок / OOO",
        "stays_coverage": "Шахматка: назначение батлера",
        "stays_coverage_cleanup": "Шахматка: снятие назначений без гостей",
        "stays_add_shift": "Шахматка: смена в График",
        "stays_export": "Шахматка: выгрузка",
    },
    menu=(MenuItem("stays", "Шахматка", 55, ("stays.view", "stays.occupancy")),
          MenuItem("mystays", "Мои гости", 56, ("stays.mine",))),
    settings_screens=(
        Screen("stays_fund", "Фонд и категории", 340, _S, "stays.setup"),
        Screen("stays_escort", "Сопровождение", 341, _S, "stays.setup"),
        Screen("stays_fields", "Настраиваемые поля", 342, _S, "stays.setup"),
        Screen("stays_labels", "Метки броней", 343, _S, "stays.setup"),
    ),
)
