# 15. Смена БД (SQLite → PostgreSQL) и движка (v4 → v7.1)

**Дополнение от 21.10.2026.** DB-02 проверен запуском на PostgreSQL 16.15
(`postgres:16-alpine`, Docker) скриптом `docs/audit/scripts/pg_check.py`: настоящие функции
миграций, свежая схема на каждый сценарий. Все 9 сценариев упали с предсказанными ошибками
(таблица §15.2). Весь pytest на PostgreSQL прогнан на временной копии —
[15b-pytest-postgres.md](15b-pytest-postgres.md) (4 падения, новая ошибка DB-06). Обновление старых
SQLite-баз проверено запуском ([04b-schema-diff.md](04b-schema-diff.md)).

## 15.1. Тесты только на SQLite
- `tests/conftest.py:38-39` жёстко присваивает `os.environ["DATABASE_URL"] = "sqlite:///…"` (не
  `setdefault`), поэтому прогнать тесты на PostgreSQL без правки кода нельзя.
  `.github/workflows/ci.yml` поднимает только Python; сервисного контейнера postgres нет.
- Отсюда **DB-04**: всё PostgreSQL-специфичное ниже не покрыто ни одним тестом.

Как проверить (5 минут, нужен Docker):
```bash
docker run -d --rm --name pg16 -e POSTGRES_PASSWORD=pg -p 55432:5432 postgres:16-alpine
```
```bash
DATABASE_URL=postgresql+psycopg2://postgres:pg@127.0.0.1:55432/postgres SECRET_KEY=0123456789abcdef0123 .venv/bin/python -c "from app.main import init_db; init_db()"
```
Для прогона pytest на копии репозитория замените в `tests/conftest.py:39` присваивание на
`os.environ.setdefault(...)` и уберите `_drop_db()`.

## 15.2. Raw-SQL, несовместимый с PostgreSQL (DB-02, **Факт**, запуск на PostgreSQL 16.15)
| Место | SQL | Когда выполняется | Ошибка PostgreSQL 16.15 (запуск `pg_check.py`) |
|---|---|---|---|
| `migrations.py:252-260` | `CASE WHEN e.dismissed_at IS NOT NULL AND e.active = 0 …` | **каждый старт** (таблицы `employment_periods` и `employees` есть всегда) | `UndefinedFunction: operator does not exist: boolean = integer`; `init_db()` на чистой базе падает (`migrations.py:207` → `:252`), приложение не стартует |
| `migrations.py:263-269` | `… WHERE dismissed_at IS NOT NULL AND active = 0 …` | каждый старт | та же ошибка (тот же шаг) |
| `migrations.py:401` | `UPDATE shift_types SET active=0, …` | если есть вид `AWAY_HOURS` | `DatatypeMismatch: column "active" is of type boolean but expression is of type integer` |
| `migrations.py:568-569` | `INSERT INTO night_zones (…, active, …) VALUES (:n, 100, 1, …)` | старые базы с категориями областей без зоны | `DatatypeMismatch: column "active" is of type boolean but expression is of type integer` |
| `migrations.py:750-754` | `INSERT INTO shift_types (…) VALUES (…, 0, …, 0, 0, 0, '', 1, 1, 1)` | базы с колонкой `tzh_code` | `DatatypeMismatch: column "overnight" is of type boolean but expression is of type integer` |
| `migrations.py:93-94,128` | `ADD COLUMN … BOOLEAN DEFAULT 1` / `DEFAULT 0` | база без этих колонок | `DatatypeMismatch: column "punch_in_allowed"` (и `"moved"`) `is of type boolean but default expression is of type integer` |
| `migrations.py:122,603` | `ADD COLUMN dispatched_at DATETIME`, `reopened_at DATETIME` | база без колонок (созданная до 19–20.10) | `UndefinedObject: type "datetime" does not exist` |

**На PostgreSQL текущий `main` не стартует, даже на чистой базе** (Факт). Это противоречит
формулировке «в проде PostgreSQL 16» (вопрос В-1).

**Достаточно ли двух строк.** На временной копии кода (git worktree в каталоге сессии, не
аудируемое дерево) заменены только `e.active = 0` и `active = 0` на `FALSE` в
`migrations.py:256,268`. Результат на чистой PostgreSQL 16.15: `init_db()` проходит, повторный
`init_db()` на той же базе (рестарт) тоже проходит. Вход и 12 основных экранов отвечают 200:
`/api/auth/me`, `/api/employees`, `/api/schedule`, `/api/tabel`, `/api/mgmt`,
`/api/presence/board`, `/api/night/today`, `/api/night/reports`, `/api/cars`, `/api/audit`,
`/api/settings`, `/api/engine-settings`. Остальные пять мест из таблицы нужно исправить всё
равно: они уронят старт на базе, созданной более старым кодом. Исправление: булевы литералы
`FALSE`/`TRUE`, `TIMESTAMP` вместо `DATETIME` или SQLAlchemy Core (`sa.false()`,
`sa.DateTime()`), и прогон CI на PostgreSQL.

Прочие различия диалектов:
- **`ILIKE` и кириллица** (Факт, запуск). `audit_api.py:57-62` фильтрует журнал через `ilike`.
  В SQLite `LIKE` регистронезависим только для ASCII: `'Смирнов' LIKE '%смирнов%'` = 0
  (проверено `sqlite3`). На PostgreSQL 16 `GET /api/audit?actor=смирнов` находит запись
  «Смирнов…» (total = 1). Поиск в журнале ведёт себя по-разному в dev и в проде (DB-04).
- **Сортировка кириллицы** (Факт, запуск). `order_by(Employee.full_name)` (`employees.py:184`,
  `auth_routes.py:259`). SQLite сортирует по кодам символов. В `postgres:16-alpine` база
  создаётся с `en_US.utf8`, но musl сравнивает по байтам: `ORDER BY` даёт
  «Ёлкин Абрамов Ежов Яковлев абрамова» — тот же «неправильный» порядок («Ё» раньше «А», строчные
  в конце). Low. Исправление: `COLLATE` на ICU (`und-x-icu`) для имён или сортировка в Python.
- **`VARCHAR(n)`** (Факт, запуск). PostgreSQL проверяет длину, SQLite нет. Обрезка есть не везде:
  `Photo.filename[:200]`, `car.note[:255]`, `note[:255]` в настройках сделаны, а у
  `Employee.full_name String(200)` и `position` ограничения на вводе нет (`EmployeeIn` без
  `max_length`). На PostgreSQL 16 `POST /api/employees` с ФИО из 250 символов вернул **500**
  (на SQLite запись сохранилась бы). Low. Исправление: `max_length` в pydantic-схемах по длине
  колонок.
- **`FOR UPDATE`** — корректно в PostgreSQL, в SQLite игнорируется (см. 14-concurrency.md).
- **Транзакционный DDL.** `migrate_db` выполняет все `ALTER` одной транзакцией
  `engine.begin()`. В PostgreSQL первая ошибка откатит весь шаг (это лучше, чем в SQLite, где
  часть DDL уже применилась бы).
- **`DROP COLUMN`** (`migrations.py:766-771`) поддерживается SQLite ≥ 3.35 и PostgreSQL.

## 15.3. Шаги миграций, которые ничего не делают или противоречат друг другу (DB-03, Факт)
| Шаг | Что не так |
|---|---|
| `migrate_db.additions["timesheet_rows"]` (10 колонок), `["schedule_entries"]` (5) — `migrations.py:64-99` | таблицы удаляет `migrate_engine_v7` (`:630-632`), который идёт двумя шагами позже. На старой базе колонки добавляются в таблицу перед её удалением, на новой таблиц нет |
| `_migrate_remove_sick_unpaid`, `_migrate_missing_shifts` (`:214-225`) | тело — `return` |
| `_apply_timesheet_code_normative` (`:228-241`) | тело — только docstring и комментарий; вызывается каждый старт |
| `migrate_shift_tabel_codes` (`:352-355`) | тело — `return`, вызывается из `main.py:101` |
| `UPDATE users SET role='supervisor' WHERE role='senior'` (`:149`) и прочие одноразовые переименования | нужны только базам старше 12.10; безопасно удалить, когда все стенды их прошли. Таблица версий шагов (Alembic) решит это навсегда |
| `migrate_settings_value_text` (`:405-418`) | только PostgreSQL. Корректно, но не покрыто тестами (DB-04) |
| `migrate_engine_v7` маркер `engine_v7_reset` (`:634-653`) | после отключения автоочистки маркер только пишется и больше ни на что не влияет |

## 15.4. Обновление старых баз (DB-01, Факт)
`migrate_schedule_dict_simplify` (`migrations.py:757-758`) обращается к строке
`con.execute(text(...))` как `r["id"]`, а строка в SQLAlchemy 2.x — кортеж (`.mappings()`
пропущен). Ветка выполняется, только если в `shift_types` ещё есть колонка `tzh_code`. Базы,
созданные кодом 06.10, 11.10 и 16.10, обновить нельзя: `TypeError` → старт падает. Проверено
запуском, таблица в 04b-schema-diff.md. Тест обновления с реальной старой схемы отсутствует.

## 15.5. Остатки движка v4 и прежних моделей
| Остаток | Где | Вердикт |
|---|---|---|
| Имя `timesheet_v4.js` (103 КБ) и функции `v4*` | `static/js/modules/timesheet_v4.js` | переименовать, когда разделы будут разрезаны по экранам (Табель, УТ, доступ). Сейчас там Табель v7.1, права и доступ |
| `tests/test_v4_api.py` | название исторически осталось, тесты рабочие (`test_engine_settings_validation`) | переименовать |
| `LEGACY_NAMES` («Администрация» → «Пятидневка») | `employees/domain/groups.py` | нужен, пока на базах есть старые имена блоков; проверить SQL-запросом и удалить вместе с миграцией |
| `Employee.balance_hours` («стартовый банк») | `employees/adapters/orm.py:105`, UI | **не используется движком** (UI-01) |
| Колонки и таблицы v4 | `timesheet_rows`, `schedule_entries` удаляются при старте; в схеме `main` их нет | — |
| Маркер очистки v4 | `engine_v7_reset` | см. 15.3 |

## 15.6. Схема «чистая против мигрированной»
С базы от 19.10 — 1 расхождение: `notify_dispatches.cc_json` в чистой базе NOT NULL, в
мигрированной NULL (`migrations.py:133` добавляет колонку без NOT NULL). Код пишет `''`, так что
это безвредно (DB-05, Low). Сравнение на PostgreSQL не выполнялось.
