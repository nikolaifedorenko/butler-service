# Изменения 21.10.2026 — миграции: PostgreSQL, обновление старых баз, переход на Alembic

Первый батч по аудиту `docs/audit/REPORT.md` (шаги 1.1–1.2 `docs/audit/PLAN.md` и
минимальный переход на Alembic, пересмотр ADR-0002). Закрыты находки DB-01, DB-02, DB-04,
DB-06 и найденная по ходу DB-07.

Версия статики не менялась (JS не затронут): `2026-10-21a`.
Новые стражи: `tests/test_db_upgrade.py` (3) + CI-джоб `postgres` (весь pytest на PostgreSQL 16).

## 1. DB-02 — на PostgreSQL приложение не стартовало

**Проблема.** Raw-SQL в `app/bootstrap/migrations.py` сравнивал boolean с integer
(`e.active = 0`), вставлял `0/1` в boolean-колонки и использовал тип `DATETIME`. PostgreSQL
16 отвечал `operator does not exist: boolean = integer` уже на чистой базе: `init_db()` падал
при каждом старте (проверено запуском, `docs/audit/scripts/pg_check.py`).

**Исправление.** `FALSE`/`TRUE` вместо `0/1`, `TIMESTAMP` вместо `DATETIME` во всех 9 местах.
SQLite понимает те же литералы (с 3.23), поведение на нём не изменилось.

## 2. DB-01 — базы старше 18.10 не обновлялись

**Проблема.** `migrate_schedule_dict_simplify` читал строку результата как `r["id"]`, а в
SQLAlchemy 2.x это кортеж: `TypeError` и падение старта у любой базы, где осталась колонка
`shift_types.tzh_code` (проверено на базах коммитов 06.10, 11.10, 16.10).

**Исправление.** `.scalars()`.

## 3. DB-07 — у баз до 18.10 не было колонки `schedule_absences.doc_type`

**Проблема.** Колонка появилась в модели 18.10, а шага `ADD COLUMN` для неё не было. ORM
читает её в каждом запросе к отсутствиям (сетка Графика, статус отметок), то есть обновлённая
база от 16.10 отвечала бы 500 на основных экранах.

**Исправление.** Колонка добавлена в `migrate_db()` (путь старых баз), туда же — отсутствовавший
у старых баз индекс `ix_checklist_items_service_id`.

## 4. DB-06 — id чатов Telegram не помещались в INTEGER PostgreSQL

**Проблема.** `notify_chats.chat_id` был `Integer` (32 бита в PostgreSQL), а id групп и
каналов Telegram (`-100…`) больше 2³¹: `refresh_chats` падал с `integer out of range`, каталог
чатов в «Настройки → Чаты и Почта» отвечал 500.

**Исправление.** `BigInteger` в модели и ревизия Alembic `0002` (`ALTER COLUMN … TYPE BIGINT`
для существующих баз).

## 5. Переход на Alembic (ADR-0002 пересмотрен)

* Ревизии: `app/bootstrap/alembic/versions/` — `0001_baseline` (схема `main 3801abf`), `0002`
  (DB-06), `0003` (дубли индексов, см. ниже). `alembic.ini` в корне — для команды
  `alembic revision --autogenerate`; адрес БД — из `DATABASE_URL`.
* `app/bootstrap/schema_version.py`: `upgrade()`, `stamp_baseline()`.
* `init_db()`: пустая база и база под Alembic — `upgrade head`; база до перехода — прежние шаги
  и `create_all`, затем `stamp 0001` и `upgrade head`. Для баз под Alembic прежние шаги и
  `create_all` больше не выполняются.
* **Индексы.** Шаги `migrate_night_cars/zones` создавали 10 индексов, которых не было в
  моделях. 3 из них настоящие (`ix_night_area_sections_zone`, `ix_night_check_items_zone_item`,
  `ix_photos_kind_ref`): теперь они объявлены в моделях под прежними именами, иначе новые базы
  остались бы без них. 7 дублировали индексы моделей под другими именами: шаги их больше не
  создают, а ревизия `0003` удаляет их в старых базах, предварительно гарантировав индекс
  модели.

## Проверки

* `pytest`: **806 passed** на SQLite и **806 passed** на PostgreSQL 16.15 (было 803 + 3 новых).
* Старые базы (`docs/audit/scripts/schema_diff.py`): обновление с коммитов `d2e0ea2` (06.10),
  `66a264b` (11.10), `206d948` (16.10), `b929007` (19.10) проходит. База от `3801abf`
  совпадает с чистой полностью. У более старых остаются только NULL и default от `ADD COLUMN`
  и отсутствующие в SQLite FK — так было и раньше.
* PostgreSQL-база, созданная кодом `3801abf` (с двумя исправленными строками, иначе он не
  стартует): два старта нового кода → 12 пользователей на месте, ревизия `0003`, `chat_id
  bigint`, дублей индексов нет, `alembic check` чистый.
* `ruff`, `lint-imports` (14/14), `check_api_contract`, `gen_js_globals --check`,
  `bump_version --check`, `export_openapi --check` — без изменений. `freeze_requirements --check`
  на машине аудита показывает только `colorama` от инструментов аудита. `npm run lint` не
  запускался (нет Node).

## Откат

Код: revert батча. База, уже получившая штамп, со старым кодом работает: таблицу
`alembic_version` он не читает. Ревизии `0002`/`0003` старому коду не мешают (BIGINT шире
INTEGER, удалены только дубли индексов). Перед первым стартом новой версии на боевой базе —
бэкап (`deploy/README.md`).
