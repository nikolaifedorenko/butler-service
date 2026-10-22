"""Манифест модуля (ADR-0012, фаза 5 аудита, 22.10.2026).

Модуль объявляет о себе в одном файле `app/modules/<имя>/manifest.py` (переменная MODULE):
роутеры, ORM-модели, права с ролями по умолчанию, заголовки журнала аудита, домены
уведомлений, пункты меню и экраны «Настроек» (шаг 5.4, дополнение к ADR-0008). Composition root (`bootstrap/modules.py`) находит манифесты и регистрирует их
здесь. Ядро модули не импортирует (R5): оно читает только зарегистрированные описания.

Раньше то же самое правилось вручную в main.py, bootstrap/registry.py, core/permissions.py,
audit_api.py и notify/domain/templates.py.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

# роли, получающие право по умолчанию; администратор получает все права всегда
EVERYONE = ("manager", "supervisor", "employee")
SUPERVISOR_UP = ("manager", "supervisor")
MANAGER_UP = ("manager",)
ADMIN_ONLY: tuple[str, ...] = ()


@dataclass(frozen=True)
class Perm:
    """Право каталога «Права доступа»: ключ, раздел, название, роли по умолчанию."""

    key: str
    section: str
    title: str
    roles: tuple[str, ...] = ADMIN_ONLY


@dataclass(frozen=True)
class NotifyDomain:
    """Раздел уведомлений: заголовок в настройках, текст по умолчанию, плейсхолдеры."""

    title: str
    template: str
    placeholders: tuple[str, ...]


@dataclass(frozen=True)
class MenuItem:
    """Пункт главного меню: виден, если есть хотя бы одно из прав `perms` (пусто — всем).
    Загрузчик раздела регистрирует файл модуля: `registerModule({views: {<id>: loadX}})`."""

    id: str
    title: str
    order: int
    perms: tuple[str, ...] = ()


@dataclass(frozen=True)
class Screen:
    """Экран «Настроек». `perm` — право видимости (None — всем, кто открыл Настройки);
    экраны одной группы идут подряд по `order`; `external` — раздел приложения, который
    открывает пункт. Рендер и иконку регистрирует файл модуля: `registerModule({screens})`."""

    id: str
    title: str
    order: int
    group: str | None = None
    perm: str | None = None
    external: str | None = None


@dataclass(frozen=True)
class ModuleManifest:
    name: str
    title: str
    order: int                                  # порядок подключения роутеров и строк каталога прав
    routers: tuple[str, ...] = ()               # «пакет.модуль:атрибут»
    models: tuple[str, ...] = ()                # модули с ORM-моделями
    permissions: tuple[Perm, ...] = ()
    audit_actions: dict[str, str] = field(default_factory=dict)
    notify_domains: dict[str, NotifyDomain] = field(default_factory=dict)
    menu: tuple[MenuItem, ...] = ()
    settings_screens: tuple[Screen, ...] = ()


_REGISTERED: list[ModuleManifest] = []


def register(manifests: list[ModuleManifest]) -> None:
    """Зарегистрировать манифесты (вызывает bootstrap). Идемпотентно."""
    _REGISTERED[:] = sorted(manifests, key=lambda m: (m.order, m.name))


def registered() -> list[ModuleManifest]:
    return list(_REGISTERED)


def audit_titles() -> dict[str, str]:
    return {k: v for m in _REGISTERED for k, v in m.audit_actions.items()}


def notify_domains() -> dict[str, NotifyDomain]:
    return {k: v for m in _REGISTERED for k, v in m.notify_domains.items()}


def ui_for(perms: set[str]) -> dict[str, list[dict]]:
    """Меню и экраны «Настроек», которые видит обладатель прав `perms` (для /api/auth/me)."""
    menu = sorted((i for m in _REGISTERED for i in m.menu), key=lambda i: i.order)
    screens = sorted((s for m in _REGISTERED for s in m.settings_screens), key=lambda s: s.order)
    return {"menu": [asdict(i) for i in menu if not i.perms or perms & set(i.perms)],
            "settings_screens": [asdict(s) for s in screens if s.perm is None or s.perm in perms]}


# Ядро — тоже «модуль» со своими роутерами, моделями и правом: core/manifest описывает его сам.
CORE = ModuleManifest(
    name="core", title="Ядро", order=1000,
    routers=("app.core.media_api:router",),
    models=("app.core.identity", "app.core.audit", "app.core.media", "app.core.settings_store"),
    permissions=(Perm("media.delete_any", "Фото и видео", "Удалить чужое фото или видео", SUPERVISOR_UP),),
)
