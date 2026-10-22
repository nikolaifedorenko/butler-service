"""Поиск манифестов модулей (ADR-0012): каждый пакет `app/modules/<имя>/` обязан иметь
`manifest.py` с переменной MODULE. Новый модуль подключается без правки этого файла,
main.py, registry.py и каталогов прав, аудита и уведомлений."""
from __future__ import annotations

import importlib
import pkgutil

from fastapi import FastAPI

from app.core.manifest import CORE, ModuleManifest


def discover() -> list[ModuleManifest]:
    import app.modules as pkg

    found = [CORE]
    for info in pkgutil.iter_modules(pkg.__path__):
        if not info.ispkg:
            continue
        mod = importlib.import_module(f"app.modules.{info.name}.manifest")   # нет файла — ошибка старта
        found.append(mod.MODULE)
    return sorted(found, key=lambda m: (m.order, m.name))


def _attr(spec: str):
    path, _, name = spec.partition(":")
    return getattr(importlib.import_module(path), name)


def import_models(manifests: list[ModuleManifest]) -> None:
    for m in manifests:
        for path in m.models:
            importlib.import_module(path)


def include_routers(app: FastAPI, manifests: list[ModuleManifest]) -> None:
    for m in manifests:
        for spec in m.routers:
            app.include_router(_attr(spec))
