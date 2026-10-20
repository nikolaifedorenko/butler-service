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
    """Импортировать все ORM-модели (регистрация в Base.metadata). Идемпотентно."""
    from app import models  # noqa: F401 — фасад тянет все подмодули и core-модели

    # Фаза C2: ORM-модели Табеля/Графика/движка живут в модуле timesheet —
    # импортируем явно (G4: реестр не полагается только на фасад).
    from app.modules.notify.adapters import orm as notify_orm  # noqa: F401
    from app.modules.timesheet.adapters import orm  # noqa: F401


def wire() -> None:
    """Инъекция провайдеров прикладного слоя в core. Идемпотентно, дёргается из
    main.py при импорте и из init_db (тесты/скрипты)."""
    ensure_models()
    from app.core import auth as core_auth
    from app.core import media
    from app.models import Employee
    from app.modules.timesheet.application import schedule_helpers
    media.set_rules_provider(schedule_helpers.load_rules)
    core_auth.set_employee_loader(lambda db, pk: db.get(Employee, pk))
