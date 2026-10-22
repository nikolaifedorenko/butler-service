"""Манифест модуля (ADR-0012): что модуль добавляет в приложение."""
from __future__ import annotations

from app.core.manifest import MANAGER_UP, SUPERVISOR_UP, MenuItem, ModuleManifest, Perm, Screen

MODULE = ModuleManifest(
    name="settings", title="Настройки", order=30,
    routers=("app.modules.settings.interface.settings_api:router",),
    permissions=(
        Perm("settings.view", "Настройки",
             "Просмотр настроек", SUPERVISOR_UP),
        Perm("settings.edit", "Настройки",
             "Изменение настроек и справочников", MANAGER_UP),
        Perm("settings.doublepay", "Настройки",
             "Дни двойной оплаты", MANAGER_UP),
    ),
    # «Права доступа» и «Журнал аудита» — экраны Настроек (группа «Администрирование»)
    menu=(MenuItem("settings", "Настройки", 70, ("settings.view", "access.manage", "audit.view")),),
    settings_screens=(
        Screen("overview", "Обзор", 0),
        Screen("calc", "Расчёт", 110, "Расчёт"),
        Screen("pay", "Правила оплаты", 120, "Расчёт"),
        Screen("codes", "Коды Табеля", 130, "Расчёт"),
        Screen("calendar", "Календарь правил", 140, "Расчёт"),
        Screen("groups", "Группы и графики", 210, "Персонал и смены"),
        Screen("shifts", "Смены и отсутствия", 220, "Персонал и смены"),
        Screen("docs", "Документы и справочники", 330, "Объект"),
        Screen("notify", "Чаты и Почта", 410, "Доставка", "settings.edit"),
        Screen("system", "Система", 530, "Администрирование"),
        Screen("expert", "Режим эксперта (JSON)", 540, "Администрирование"),
    ),
)
