# 19. Захардкоженное

Классы: **env** (переменная окружения и `Settings`), **БД** (справочник или настройка объекта
в UI), **const** (именованная константа или enum в коде), **модуль** (конфиг модуля в его
манифесте). ID → [REPORT.md](REPORT.md).

| Что | Где | Сейчас | Куда | Комментарий |
|---|---|---|---|---|
| **Часовой пояс: два источника** | `core/config.py:13` (`APP_TZ`, env) → `core/time.py:16`, `timesheet/adapters/_db.py:10-11`; **и** `tz` в версии настроек движка, редактируется в UI (`settings.js:747-838`, `adapters/settings_codec.py:41`) | env + БД | один источник: env `APP_TZ`, а поле `tz` в редакторе движка только показывать | **HARD-01**: если в UI выбрать другой пояс, отметки переводятся в UTC по `APP_TZ`, а движок режет сутки по `Settings.tz` |
| Подпись пояса на экране каров | `static/js/modules/cars.js:186` `APP_TZ_LABEL = 'Europe/Moscow'` | const во фронте | брать из `/api/health` (`tz`) или `/api/auth/me` | HARD-02 |
| Пояс по умолчанию в домене | `timesheet/domain/settings/defaults.py:62`, `types.py:96`, `interface/views.py:55` | const | допустимо как значение по умолчанию; `views.py:55` — заменить на `APP_TZ` | — |
| Окно ночной смены 20:00–08:00 | `night/application/night.py:45-46` (`SHIFT_START`, `SHIFT_END`), подписи `night/adapters/orm.py:171`, `notify_api.py:52`, `night_export.py:63` | const | **модуль** (настройка ночного отчёта в БД) | объект с другой ночной сменой — правка кода. HARD-02 |
| Досоздание пропущенных смен 31 день, троттлинг 120 с | `night.py:52,206` | const | модуль; троттлинг удалить (фоновый поток вызывает с `force=True`) | — |
| Период фоновой синхронизации 60 с | `core/config.py:49-50` | env | ✓ | — |
| Лимит входа 10 за 300 с | `auth_routes.py:31-32` | const | env | ADR-0005 |
| TTL сессии 48 ч | `core/config.py:16` | env | ✓ (нет в `.env.example`) | DOC-04 |
| Дубль отметки 60 с, опоздание 5 мин по умолчанию | `punches.py:43,61` | const; опоздание берётся из настроек движка (`load_rules`) | ✓ | — |
| Отметка задним числом ≤ 62 дней | `punches.py:263` | const | настройки объекта | — |
| Лимиты медиа 12/50 МБ, хранение 180 дней, аварийный предел 500 МБ | `core/media.py:150-159` | БД (настройки объекта) + const | ✓; nginx 8 МБ не согласован (OPS-01) | — |
| Лимит бланка 5 МБ, распаковка 50 МБ | `docs_api.py:197-199`, `doc_render.py` | const | ✓ | — |
| **Роли строками в Python** | `cars.py:241,294,353,356`, `cars_api.py:150`, `night_api.py:948`, `employees.py:390`, `timesheet/interface/doublepay.py:47`, `auth_guards.py:33-53`, `core/roles.py` | const и строки | **права** (`require_perm`, `has_perm`) | AUTHZ-05 |
| Роли строками в JS | `app.js:239,296`, `cars.js:313,339`, `employees.js:408-409`, `timesheet_layers.js:10,140`; `ROLE_TITLES` в JS | const | `can('…')` и роли с подписями из `/api/access` | UI-02 |
| `ROLE_DEFAULTS`, `ROLE_TITLES`, `PERMISSIONS` | `core/permissions.py:22-82` | const | права объявляет модуль, роли и их базовые права — данные в БД (TARGET-ARCHITECTURE.md §2) | — |
| Названия разделов прав и тексты UI в Python | `permissions.py` (поля `section`, `title`), `formatting.py`, тексты `HTTPException` | const | допустимо для одного языка | — |
| Коды Табеля и блоков | `employees/domain/groups.py` (`GROUP_FIVEDAY`, `LEGACY_NAMES`), сид | const + БД | блоки — справочник в БД | — |
| Адрес Telegram Bot API по умолчанию | `notify/application/config.py:24-26` | БД с дефолтом | **env** (адрес не должен меняться из UI, SEC-03) | — |
| `DEFAULT_PASSWORD = "demo1234"` | `bootstrap/seed.py:44` | const | только для демо-режима (флаг `DEMO_SEED=1`) | SEC-02 |
| Пути `data/`, `templates/`, `assets/fonts` | `core/media.py:245-250`, `doc_render.py:26-27`, `core/render.py` | const от `BASE_DIR` | env (`DATA_DIR`) для гибкого монтирования томов | Low |
| Порт 8000, `--workers 2` | `Dockerfile`, compose | env (`UVICORN_WORKERS`) | ✓ | — |
| Поллинг 30 с, кары 60 с, таймаут API 20 с, загрузка 60 с | `app.js:204`, `cars.js:41`, `core.js:141,171` | const во фронте | константы в одном месте `core.js` | UI-03 |
| `max_length` во фронте (`maxlength=255/120/40`) | `cars.js` и другие | const | генерировать из схемы или держать рядом с pydantic | — |
| Демо-данные: телефоны, Telegram, почты `@butler.service` | `bootstrap/seed.py:150-163` | const | только в демо | — |
