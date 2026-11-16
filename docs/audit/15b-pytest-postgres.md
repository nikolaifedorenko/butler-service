# 15b. Весь pytest на PostgreSQL 16 (запуск 21.10.2026)

**Где запускалось:** временная копия кода — `git worktree` коммита `3801abf` в каталоге
сессии, после проверки удалена. Аудируемое дерево не менялось. PostgreSQL 16.15
(`postgres:16-alpine`, Docker), драйвер `psycopg2-binary` 2.9.13, Python 3.14.8, зависимости
из `requirements.lock.txt`. Перед каждым прогоном схема `public` пересоздавалась.

## Правки в копии (минимум, чтобы pytest вообще пошёл на PostgreSQL)
| Файл | Правка | Зачем |
|---|---|---|
| `app/bootstrap/migrations.py:256,268` | `e.active = 0` → `e.active = FALSE`, `active = 0` → `active = FALSE` | без этого `init_db()` на PostgreSQL падает, и все тесты получают ошибку (DB-02) |
| `tests/conftest.py:39` | `os.environ["DATABASE_URL"] = …` → `os.environ.setdefault(...)` | позволить задать PostgreSQL извне (DB-04) |
| `tests/test_api.py:12` | то же | модуль тоже жёстко прописывает SQLite |
| `tests/conftest.py` (фикстура `app_stack`) | `assert engine.url.get_backend_name() == os.environ["AUDIT_EXPECT_BACKEND"]` | страж: тесты действительно идут на нужной базе |

## Результат 1: с исправлением двух строк
| База | Итог | Время |
|---|---|---|
| **PostgreSQL 16.15** | **4 failed**, 799 passed, 3 skipped | 69 с |
| SQLite (та же копия) | 803 passed, 3 skipped | 42 с |

Значит, исправление двух строк SQLite не ломает, а 4 падения относятся только к PostgreSQL.
Пропущенные 3 теста одинаковы на обеих базах и с диалектом не связаны («node недоступен»,
«нужно число месяца ≥ 26», «нет открытой смены по демо-данным»).

### Падения и их причины
| # | Тест | Ошибка PostgreSQL | Корень | Находка |
|---|---|---|---|---|
| 1 | `tests/test_grafik_norms.py::TestTimeoffEntity::test_04_migration_merges_duplicate_kind` | `DatatypeMismatch: column "active" is of type boolean but expression is of type integer` — `UPDATE shift_types SET active=0, …` | `app/bootstrap/migrations.py:401` | DB-02 (одно из оставшихся мест) |
| 2 | `tests/test_notify_settings.py::test_katalog_chatov_iz_getupdates` | `DataError: NumericValueOutOfRange: integer out of range` — `INSERT INTO notify_chats (chat_id, …)` со значением `-1001234567890` | `app/modules/notify/adapters/orm.py:80`: `chat_id` объявлен `Integer` (32 бита в PostgreSQL, в SQLite — 64). Падает в `notify/application/chats.py:112` (`refresh_chats`) из `POST /api/notify/telegram/chats` | **DB-06 (новая)** |
| 3 | `tests/test_notify_settings.py::test_zakreplenie_chata_delaet_sluzhbu_gotovoy` | `assert row is not None` — чата нет в каталоге | **следствие №2**: каталог чатов не сохранился | DB-06 |
| 4 | `tests/test_settings_ui_api.py::TestHealth::test_08_sick_unpaid_migration_idempotent` | `['TIMEOFF_HOURS', 'AWAY_HOURS'] != ['TIMEOFF_HOURS']` | **следствие №1**: тест №1 вставил вид `AWAY_HOURS`, миграция упала и не архивировала его, а база у тестов общая | DB-02 |

## Результат 2: плюс ещё две правки в копии
К двум строкам добавлены `migrations.py:401` (`active=0` → `active=FALSE`) и
`notify/adapters/orm.py:80` (`Integer` → `BigInteger`, импорт `BigInteger`).

| База | Итог |
|---|---|
| **PostgreSQL 16.15** | **803 passed, 3 skipped** (68 с) — столько же, сколько на SQLite |

Вывод: кроме найденного раньше (DB-02), тесты на PostgreSQL выявили **одну новую ошибку**
(DB-06). Других расхождений поведения между SQLite и PostgreSQL набор из 806 тестов не ловит.
Это не значит, что их нет: в 15-db-engine.md §15.2 описаны ещё три различия (поиск по
кириллице в журнале аудита, длина `VARCHAR`, сортировка), на которые тестов нет, и пять мест
DB-02, которые выполняются только на старых базах.

## Что это значит для прода
- **DB-06.** Идентификаторы групп и каналов Telegram (`-100…`) и личных чатов (сейчас больше
  2³¹) не помещаются в INTEGER PostgreSQL. На PostgreSQL кнопка «Обновить каталог чатов» в
  «Настройки → Чаты и Почта» (`static/js/modules/settings.js:2334`) отвечает 500, каталог
  остаётся пустым, и закрепить чат за службой нельзя. Доставка в Telegram через UI не
  настраивается.
- Для **существующих** баз PostgreSQL одной правки модели мало: `create_all` тип колонки не
  меняет. Нужен шаг миграции
  `ALTER TABLE notify_chats ALTER COLUMN chat_id TYPE BIGINT` (идемпотентен, на SQLite не
  нужен).

## Как воспроизвести
```bash
docker run -d --rm --name audit-pg16 -e POSTGRES_PASSWORD=pg -p 127.0.0.1:55432:5432 postgres:16-alpine
```
В копии репозитория внести правки из первой таблицы, затем:
```bash
AUDIT_EXPECT_BACKEND=postgresql DATABASE_URL=postgresql+psycopg2://postgres:pg@127.0.0.1:55432/postgres .venv/bin/python -m pytest tests/ -q -rfE
```
