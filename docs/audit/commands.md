# Запущенные команды и результаты

Коммит `3801abf`, Python 3.14.8, `pip install -r requirements.lock.txt`, а также `ruff
vulture bandit pip-audit radon` в `.venv`. Все запуски шли на временных SQLite-файлах в
каталоге сессии. `timetrack.db` и `.env` в клоне отсутствуют (они в `.gitignore`) и не
открывались.

| Команда | Результат |
|---|---|
| `python -m pytest tests/ -q --cov=app` | **803 passed, 3 skipped** за 50,6 с; покрытие `app/` **88 %** (13 102 stmts, 1 617 miss) |
| `ruff check .` | All checks passed |
| `lint-imports` | 14 контрактов, 14 kept, 0 broken (336 файлов, 1 099 зависимостей) |
| `python tools/check_api_contract.py` | 188 маршрутов в OpenAPI, 154 вызова из JS, все вызовы находят маршрут |
| `python tools/gen_js_globals.py --check` | `js_globals.json` актуален (322 имени) |
| `python tools/bump_version.py --check` | версия статики согласована: 2026-10-21a, 14 файлов в SHELL |
| `python tools/export_openapi.py --check` | `docs/openapi.json` актуален (156 путей) |
| `python tools/freeze_requirements.py --check` | ✗ `colorama` отсутствует в lock. Это шум окружения аудита: пакет пришёл вместе с bandit/radon, к проекту отношения не имеет |
| `python tools/verify_requirements.py` | ✗ **падает**: `StopIteration` на `t["code"] == "OFF"` и проверка темы `--bg #eef1f6` (инструмент устарел, DEAD-03) |
| `vulture app --min-confidence 60` | 294 строки; после grep по всему дереву: 16 функций без единой ссылки и 3 функции, которые вызывают только тесты (DEAD-01) |
| `bandit -q -r app` | 15 Low/Medium: 3×B608 (f-string SQL в `migrations.py`, значения — int из БД и константы, ложная тревога), 4×B110 (`try/except/pass`), B105 `demo1234` (SEC-02), B603/B404 (LibreOffice), B311 (`random` в сиде) |
| `pip-audit -r requirements.lock.txt` | No known vulnerabilities found |
| `radon cc -s -a -nc app` | 98 блоков сложности C и выше, средняя C (19,5); худшие: `build_docx` F80, `seed_if_empty` F58, `fact_month` F51, `docx_to_pdf_native` F50, `schedule_docx` F48, `_punch_locked` F46, `get_grid` F45, `absence_period` F43, `group_by_service` F41 |
| `uvicorn app.main:app --workers 2` (временная SQLite) | оба воркера стартовали, второй ждал `startup_lock`; сид один раз, ночных отчётов 31, дублей нет |
| `docs/audit/scripts/experiments.py` | 15 экспериментов, все 15 подтвердились (вывод ниже) |
| `docs/audit/scripts/authz_matrix.py` | матрица 5 ролей × 180 маршрутов: 1 расхождение с каталогом на несуществующих id; ролевые проверки в теле проявились в экспериментах |
| `docs/audit/scripts/query_budget_scan.py` | 24 экрана × (11 и 71 сотрудник), см. 16b-query-budget.md |
| `docs/audit/scripts/schema_diff.py <коммит>` | обновление баз от `d2e0ea2`, `66a264b`, `206d948` падает с TypeError; от `b929007` проходит с 1 расхождением |
| `docs/audit/scripts/xss_scan.py` | 292 интерполяции в HTML-шаблонах без явного `esc()`; ручная проверка всех текстовых полей нашла ноль уязвимостей |
| `docs/audit/scripts/doc_links.py` | 102 битые ссылки на файлы в `*.md`, из них 19 в «живых» документах |

**Не запускались** (решение владельца): `npm run lint`, `tools/*_scenario.mjs`, `npm audit`.

## Дополнение 21.10.2026: весь pytest на PostgreSQL 16 (временная копия)

Подробности и правки копии — в [15b-pytest-postgres.md](15b-pytest-postgres.md).

| Прогон | Результат |
|---|---|
| PostgreSQL 16.15, копия + 2 строки `migrations.py:256,268` | **4 failed, 799 passed, 3 skipped** (69 с) |
| SQLite, та же копия | 803 passed, 3 skipped (42 с) |
| PostgreSQL 16.15, копия + ещё `migrations.py:401` и `notify_chats.chat_id` → `BigInteger` | **803 passed, 3 skipped** (68 с) |

```
FAILED tests/test_grafik_norms.py::TestTimeoffEntity::test_04_migration_merges_duplicate_kind   — DatatypeMismatch, migrations.py:401
FAILED tests/test_notify_settings.py::test_katalog_chatov_iz_getupdates                         — NumericValueOutOfRange: integer out of range (chat_id)
FAILED tests/test_notify_settings.py::test_zakreplenie_chata_delaet_sluzhbu_gotovoy             — следствие предыдущего
FAILED tests/test_settings_ui_api.py::TestHealth::test_08_sick_unpaid_migration_idempotent      — следствие первого (AWAY_HOURS не архивирован)
```

## Дополнение 21.10.2026: проверка DB-02 на PostgreSQL 16

Контейнер `postgres:16-alpine` (PostgreSQL 16.15, `en_US.utf8`) на `127.0.0.1:55432`,
драйвер `psycopg2-binary` 2.9.13 из `requirements-postgres.txt`.

```
PG_URL=postgresql+psycopg2://postgres:pg@127.0.0.1:55432/postgres .venv/bin/python docs/audit/scripts/pg_check.py
# PostgreSQL: PostgreSQL 16.15 on aarch64-unknown-linux-musl
FAIL | init_db() целиком на ЧИСТОЙ базе | UndefinedFunction: operator does not exist: boolean = integer | migrations.py:207, migrations.py:252
FAIL | _migrate_employment_periods() — `e.active = 0` (migrations.py:252-269), каждый старт | UndefinedFunction: operator does not exist: boolean = integer | migrations.py:252
FAIL | migrate_db(): ADD COLUMN punch_in_allowed BOOLEAN DEFAULT 1 (migrations.py:93) | DatatypeMismatch: column "punch_in_allowed" is of type boolean but default expression is of type integer | migrations.py:146
FAIL | migrate_db(): ADD COLUMN moved BOOLEAN DEFAULT 0 (migrations.py:128) | DatatypeMismatch: column "moved" is of type boolean but default expression is of type integer | migrations.py:146
FAIL | migrate_db(): ADD COLUMN dispatched_at DATETIME (migrations.py:122) | UndefinedObject: type "datetime" does not exist | migrations.py:146
FAIL | migrate_night_reopened_at(): ADD COLUMN reopened_at DATETIME (migrations.py:603) | UndefinedObject: type "datetime" does not exist | migrations.py:603
FAIL | migrate_timeoff_entity(): UPDATE shift_types SET active=0 (migrations.py:401), есть AWAY_HOURS | DatatypeMismatch: column "active" is of type boolean but expression is of type integer | migrations.py:401
FAIL | migrate_night_zones(): INSERT night_zones (…, active=1) (migrations.py:568), область без зоны | DatatypeMismatch: column "active" is of type boolean but expression is of type integer | migrations.py:568
FAIL | migrate_schedule_dict_simplify(): база с tzh_code и без TIMEOFF_HOURS (migrations.py:750-758) | DatatypeMismatch: column "overnight" is of type boolean but expression is of type integer | migrations.py:750
```

Временная копия кода (git worktree `3801abf` в каталоге сессии, удалена после проверки). В ней
изменены только две строки `migrations.py:256,268` (`= 0` → `= FALSE`). Результат на чистой
PostgreSQL 16.15:

```
init_db OK
login 200
200 /api/auth/me · /api/employees · /api/schedule · /api/tabel · /api/mgmt · /api/presence/board
200 /api/night/today · /api/night/reports · /api/cars · /api/audit?actor=смирнов · /api/settings · /api/engine-settings
повторный init_db OK
audit actor=смирнов total: 1 | actor=Смирнов total: 1        (на SQLite «смирнов» не находится)
POST /api/employees с ФИО 250 символов: 500 Internal Server Error   (на SQLite сохранилось бы)
ORDER BY: Ёлкин Абрамов Ежов Яковлев абрамова                     (побайтовая сортировка musl, как в SQLite)
```

## Вывод `experiments.py`

```
EXP-XFF | ФАКТ | 30 неверных паролей с разным левым XFF (nginx дописывает реальный IP справа): 429 ни разу ([401]); с одинаковым XFF 429 на попытке 11
EXP-IMP-1 | ФАКТ | supervisor → impersonate(сотрудник менеджера smirnov): 200; затем POST /api/punches от его имени: 200 Отмечен уход в 17:51; в журнале: actor_id=4 actor_name='Смирнов Алексей Владимирович (как сотрудник)' action=punch_out
EXP-PWD | ФАКТ | PUT /api/employees/5 с новым паролем: 200; старая cookie → /api/auth/me: 200
EXP-ROLE | ФАКТ | роль до: supervisor, после PUT без role: employee; запись аудита: '{"full_name": "Громова Ольга Петровна"}'
EXP-BANK | ФАКТ | balance_hours 2 → 999: сохранено (200), bank_now до 0.0 / после 0.0, у сотрудника на экране отметок 0.0
EXP-SUPBANK | ФАКТ | supervisor: PUT balance_hours=77 → 200; POST bank-adjust → 403
EXP-ROLEGRANT | ФАКТ | manager с deny settings.edit → POST /api/doublepay/days: 403 (ожидаемо 403); supervisor с ЯВНЫМ allow settings.edit → 403: 'Менять дни двойной оплаты может только администратор или менеджер'
EXP-PUNCHOTHER | ФАКТ | POST /api/punches employee_id=7 (sidorov) от supervisor без punch_for_others: 200 'Отмечен уход в 17:51'; отметка записана сотруднику id=3 (сама gromova=3, была на смене: True)
EXP-PHOTO | ФАКТ | сотрудник с правами [] (всё снято) → GET /api/photos/1/file: 200, алиас /api/night/photos: 200
EXP-NIGHTVIEW | ФАКТ | сотрудник с deny night.view: GET /today 403; take 200; answer 200; close 200
EXP-DISPATCH | ФАКТ | рядовой сотрудник (night.view по умолчанию) → POST /api/night/reports/31/dispatch: 409 {'detail': 'Доставка не настроена: …'}
EXP-CARRACE | ФАКТ | кар id=1: два «взять» с чередованием чтение/чтение/запись+commit/запись+commit — оба успешны, в истории 2 записи «take», держатель в карточке: Кузнецова Мария Сергеевна
EXP-GIVEMAINT | ФАКТ | supervisor: снять с обслуживания → 400; «выдать» тот же кар → 200, статус стал busy
EXP-RETENTION | ФАКТ | срок фото 30 дн, видео 180 дн; фото возрастом 60 дн → cleanup_photos удалил 0, файл на месте: True
EXP-PHOTODEL | ФАКТ | автор удаляет фото-доказательство из ЗАКРЫТОГО ночного отчёта: 200
```

EXP-DISPATCH. Ответ 409 приходит уже после проверки прав, то есть сотрудник дошёл до самой
отправки. Остановило его только то, что доставка в демо-базе не настроена.
