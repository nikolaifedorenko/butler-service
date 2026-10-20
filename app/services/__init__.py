"""Сервисный слой приложения (use-case'ы).

Паттерн — по образцу `app/cars.py` + тонкого `app/api/cars_api.py` (ADR-0006):
роутеры `app/api/*` занимаются только HTTP (права через require_perm, DTO,
статусы), а обработка и бизнес-правила живут здесь. Сервисы НЕ знают про
FastAPI: ошибки — исключения `core.errors` (до фазы C1 — `services.errors`), которые маппятся в HTTP-статусы
обработчиками в `app/main.py`. `audit()` и `db.commit()` — часть use-case'а.

Границы поддержаны контрактами import-linter (`.importlinter`):
api → services → models; модули api независимы друг от друга.
"""
