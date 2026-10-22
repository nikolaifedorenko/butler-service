"""Реестр модулей и инъекция провайдеров в core (composition root).

SQLAlchemy создаёт таблицы по Base.metadata — если модель не импортирована до create_all,
её таблица молча не создастся. Модели, роутеры, права, заголовки аудита и разделы
уведомлений модули объявляют в манифестах (ADR-0012, bootstrap/modules.py); wire()
регистрирует их в core и дополнительно внедряет провайдеры, которые core не может
импортировать сам (R5): «прочие правила объекта» для лимитов медиа, запрет удаления фото
закрытого отчёта, загрузчик сотрудника.
"""
from __future__ import annotations


def ensure_models() -> None:
    """Импортировать все ORM-модели (регистрация в Base.metadata). Идемпотентно.

    Список моделей — из манифестов модулей (ADR-0012): ядро + `models` каждого модуля.
    """
    from . import modules

    modules.import_models(modules.discover())


def wire() -> None:
    """Инъекция провайдеров прикладного слоя в core. Идемпотентно, дёргается из
    main.py при импорте и из init_db (тесты/скрипты)."""
    ensure_models()
    from app.core import auth as core_auth
    from app.core import manifest, permissions

    from . import modules

    found = modules.discover()
    manifest.register(found)
    permissions.load_catalog(p for m in found for p in m.permissions)
    from app.core import media
    from app.modules.employees.adapters.orm import Employee
    from app.modules.night.application.night import photo_delete_blocker
    from app.modules.timesheet.application import schedule_helpers
    media.set_rules_provider(schedule_helpers.load_rules)
    media.set_delete_guard(photo_delete_blocker)
    core_auth.set_employee_loader(lambda db, pk: db.get(Employee, pk))
