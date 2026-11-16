# 00. Инвентаризация «Батлер Сервис» (этап 0)

**Объект аудита:** `github.com/nikolaifedorenko/butler-service`, ветка `main`, коммит `3801abf`
(21.10.2026 16:26 МСК, PR #69). Локальная ветка аудита `audit/2026-10-21`: в ней только новые
файлы `docs/audit/**`, код не менялся, коммитов нет.
**Окружение аудита:** macOS, Python 3.14.8, зависимости строго из `requirements.lock.txt`
(fastapi 0.150.0, starlette 1.9.0, SQLAlchemy 2.1.5, pydantic 2.14.1). Node и PostgreSQL не
запускались (решение владельца), Docker-демон выключен.

## 0.1. Карта путей: промпт и фактический код

Описание системы в промпте отстаёт от кода. После рефакторинга C1–C7 (20.10) и ревью P0/P1
(20–21.10) код разложен по модулям (ADR-0010, «модульный монолит»):

| В промпте | В `main` |
|---|---|
| `app/api/*.py` (18 модулей) | `app/modules/<m>/interface/*.py`: 18 роутеров в 9 модулях (`access`, `audit`, `cars`, `docs`, `employees`, `night`, `notify`, `settings`, `timesheet`) + `app/core/media_api.py` |
| `app/engine/` | `app/modules/timesheet/{domain,application,ports,adapters}` |
| `app/models/*` | `app/modules/*/adapters/orm.py` + `app/core/{identity,audit,media,settings_store}.py`; реестр `app/bootstrap/registry.py` |
| `app/migrations.py`, `app/seed.py` | `app/bootstrap/migrations.py` (771 строка), `app/bootstrap/seed.py` (547) |
| `app/permissions.py`, `auth.py`, `security.py`, `deps.py` | `app/core/permissions.py`, `roles.py`, `auth.py`, `auth_guards.py`, `security.py`, `time.py`, `format.py` |
| `app/photos.py` | `app/core/media.py`, `app/core/media_api.py` |
| middleware в `main.py` | `app/core/observability.py` |
| `static/js/section_*.js` | `static/js/modules/*.js`: `settings.js` 179 КБ, `night.js` 109 КБ, `timesheet_v4.js` 103 КБ, `timesheet_layers.js` 57 КБ, `cars.js` 46 КБ, `employees.js` 41 КБ, `dicts.js` 30 КБ, `me.js` 14 КБ, `docs.js` 11 КБ; плюс `core.js` 18 КБ и `app.js` 31 КБ |
| `require_manager/require_admin/require_supervisor` | **удалены** (этап B, 20.10), см. 13-security.md |

Размер кода по `radon raw -s app`: 24 721 LOC (17 071 SLOC). Тесты: 52 файла, **803 passed,
3 skipped** за 50 с, покрытие `app/` 88 %.

## 0.2. Маршруты
- [01-routes.md](01-routes.md): **191** пара «метод + путь», **159** уникальных путей, **4** `async def`.
  Авторизация: `require_perm` у 160, только вход (`current_principal`) у 22, `optional_principal`
  у 1, без входа у 8 (`/metrics`, `/api/health`, вход, `/sw.js`, манифест, SPA-fallback).
- Сверка с OpenAPI: `tools/check_api_contract.py` нашёл 188 маршрутов в OpenAPI и 154 вызова из
  JS, битых нет. `tools/export_openapi.py --check`: `docs/openapi.json` актуален, 156 путей.
- [03b-authz-run.md](03b-authz-run.md): матрица «роль × маршрут», снятая **запуском** для admin,
  manager, supervisor, employee и режима «как сотрудник».

## 0.3. API ↔ UI
- [02-api-ui.md](02-api-ui.md): каждому маршруту сопоставлены вызывающие функции JS и наоборот.
  216 литералов `/api/…`; маршрутов без вызова из JS: 21, из них 8 ложных срабатываний
  (динамический адрес в `dicts.js:43`, адреса фото приходят с сервера, форма входа в
  `index.html`). Классификация оставшихся — в 12-ui-api.md.

## 0.4. Права
- [03-perm-matrix.md](03-perm-matrix.md): 29 ключей `PERMISSIONS`, роли по умолчанию, маршруты и
  места UI для каждого ключа, маршруты без права, все проверки **по роли** (8 в бэкенде,
  8 во фронтенде).

## 0.5. Модели и схема
- [04-schema.md](04-schema.md): **45 таблиц** в `Base.metadata`, FK, unique, индексы, модуль-владелец.
- [04b-schema-diff.md](04b-schema-diff.md): «старая база после миграций» против «чистой» (запуском,
  SQLite). Базы, созданные кодом 06.10, 11.10 и 16.10, **не обновляются**: старт падает (DB-01).
  С базы от 19.10 обновление проходит с одним расхождением.
- `GET /api/selfcheck` (`app/main.py:251-298`) сверяет только наличие таблиц и колонок
  (`schema_report`). Типы, NOT NULL, индексы и unique он не проверяет, поэтому расхождение
  `notify_dispatches.cc_json` (NULL против NOT NULL) не видит.

## 0.6. Последовательность старта (`app/main.py:65-147`)
1. `lifespan` → `_check_secret_key()`: старт запрещён при ключе короче 16 символов или с
   префиксом `change-me` (если не задан `ALLOW_INSECURE_DEV_SECRET`).
2. `init_db()` под `core/startup_lock.startup_lock()`: advisory-lock в PostgreSQL, `flock` в SQLite.
   Порядок `_init_db_steps()`:
   `registry.wire()` → `Base.metadata.create_all` → `migrate_db` (внутри
   `_migrate_remove_sick_unpaid`, `_migrate_missing_shifts`, `_migrate_employment_periods`,
   `_migrate_fiveday_patterns`, `_migrate_base_groups_key`) → `migrate_settings_value_text` →
   `migrate_engine_v7` → `migrate_schedule_dict_simplify` → `seed_statement_kinds` →
   `seed_if_empty` → `bootstrap_engine` → commit → `migrate_timeoff_entity` →
   `migrate_manual_replaces_generated` → `migrate_time_off_template` → `migrate_shift_tabel_codes`
   → `migrate_night_cars` → `migrate_night_zones` → `migrate_night_reopened_at` →
   `sync_reports(force=True)` → `cleanup_photos`.
3. `start_night_sync()`: фоновый поток каждые `NIGHT_SYNC_SECONDS` (60 с), раунд выполняет один
   процесс под `try_lock("night-sync")`.
4. Запуск uvicorn `--workers 2` на временной SQLite (Факт, запуск): второй воркер ждёт замок,
   сид выполнен один раз (12 пользователей), ночных отчётов 31, дублей нет.

## 0.7. Глобальное состояние процесса (AST-скан `app/`)
| Где | Что | Риск при 2 воркерах |
|---|---|---|
| `access/interface/auth_routes.py:33-34` | `_login_failures` (dict IP → список времён), `_login_lock` | лимит считается отдельно в каждом воркере; словарь растёт без предела при подмене IP (SEC-01) |
| `timesheet/interface/punches.py:64-65` | `_emp_locks` (Lock на сотрудника), `_emp_locks_guard` | работает только внутри процесса; между процессами — `SELECT … FOR UPDATE` (в PostgreSQL), SQLite его игнорирует |
| `night/application/night.py:207` | `_last_sync` (троттлинг 120 с) | у каждого процесса свой; после переноса в фоновый поток с `force=True` троттлинг фактически не используется |
| `bootstrap/night_sync.py:39-40` | `_thread`, `_stop` | поток в каждом воркере, раунд под `try_lock` |
| `core/startup_lock.py:54` | `_depth` (вложенность замка) | только на старте |
| `core/render.py:33-34` | `_font_ready`, `_font_error` (шрифты PDF) | безвредно |
| `core/auth.py:65`, `core/media.py:142` | `_EMPLOYEE_LOADER`, `_RULES_PROVIDER` (инъекция из `registry.wire`) | безвредно |
| `core/config.py:53` | `@lru_cache get_settings()`; `core/time.py:16` и `timesheet/adapters/_db.py:10-11` — `TZ` на импорте | смена `APP_TZ` требует перезапуска; второй источник TZ — настройки движка (HARD-01) |

## 0.8. Внешние интеграции и файлы
| Что | Где | Замечания |
|---|---|---|
| Telegram Bot API | `notify/adapters/transports/telegram.py:27-55` (httpx, таймаут из настроек 1–300 с, по умолчанию 20) | адрес API меняется в UI (SEC-03); вызов синхронный, внутри HTTP-запроса (CONC-02) |
| SMTP / Exchange | `notify/adapters/transports/email.py:36-38` (smtplib, `timeout=cfg.timeout`) | хост меняется в UI (SEC-03) |
| Фото и видео | `core/media.py`: `data/uploads/YYYY/MM/<uuid>.<ext>`; тип по магическим байтам; потоковая запись; лимиты 12/50 МБ из настроек объекта, аварийный предел 500 МБ | nginx пропускает тело только до 8 МБ (OPS-01); очистка по сроку только при старте и с ошибкой окна (BUG-01) |
| Шаблоны DOCX | `docs/application/doc_render.py:26,150-178`: `templates/<code>.docx`, код по `^[a-z][a-z0-9_]{1,39}$`, проверка zip (число файлов, 50 МБ распаковки), разбор python-docx | защищено |
| PDF | `core/render.py` (reportlab, шрифты `assets/fonts`), конвертация DOCX → PDF через LibreOffice до 180 с (`docx_to_pdf_native`) | выполняется синхронно в запросе (PERF-04) |
| XLSX и CSV | openpyxl: `schedule.py:1266-1310`, `mgmt_api.py:209-240`; CSV: `audit_api.py:89-103`, `notify_api.py:225-270` | `safe_sheet_cell` стоит почти везде (13-security.md) |
| Каталоги | `data/` (БД SQLite, загрузки), `templates/` (бланки) — тома в compose | `TEMPLATES_DIR.mkdir()` при импорте модуля (`doc_render.py:27`) |
