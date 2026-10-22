"""Реестр моделей и инъекция провайдеров в core (composition root).

Зачем: SQLAlchemy создаёт таблицы по Base.metadata — если модель не импортирована
до create_all, её таблица молча не создастся. Фасад app/models импортирует все
модули моделей (включая переехавшие в core: identity/audit/media), поэтому
одного импорта фасада достаточно. wire() дополнительно регистрирует провайдеры,
которые core не может импортировать сам (R5): «прочие правила объекта» для
лимитов медиа.
"""
from __future__ import annotations


def ensure_models() -> None:
    """Импортировать все ORM-модели (регистрация в Base.metadata). Идемпотентно.

    Явный реестр (G4, фаза C4): core-модели (identity/audit/media/settings_store)
    + adapters.orm всех пяти модулей с моделями. Фасад app/models удалён —
    порядок импортов больше не зависит от него.
    """
    from app.core import audit, identity, media, settings_store  # noqa: F401
    from app.modules.cars.adapters import orm as cars_orm  # noqa: F401
    from app.modules.employees.adapters import orm as employees_orm  # noqa: F401
    from app.modules.night.adapters import orm as night_orm  # noqa: F401
    from app.modules.notify.adapters import orm as notify_orm  # noqa: F401
    from app.modules.timesheet.adapters import orm  # noqa: F401


def wire() -> None:
    """Инъекция провайдеров прикладного слоя в core. Идемпотентно, дёргается из
    main.py при импорте и из init_db (тесты/скрипты)."""
    ensure_models()
    from app.core import auth as core_auth
    from app.core import media
    from app.modules.employees.adapters.orm import Employee
    from app.modules.night.application.night import photo_delete_blocker
    from app.modules.timesheet.application import schedule_helpers
    media.set_rules_provider(schedule_helpers.load_rules)
    media.set_delete_guard(photo_delete_blocker)
    core_auth.set_employee_loader(lambda db, pk: db.get(Employee, pk))
