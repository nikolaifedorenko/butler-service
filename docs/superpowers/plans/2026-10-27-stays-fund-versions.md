# Шахматка, часть 1: дерево фонда, версии с даты, флаги, месячный вид — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** фонд шахматки (категории, объекты, дерево групп, флаги) хранится версиями с даты; все виды
читают «фонд на день»; распределение учитывает границы версий; шахматки — по месяцу с фильтрами и
сортировкой; новая вкладка «Брони»; фонд выгружается и загружается Excel-файлом.

**Architecture:** постоянные таблицы держат только id; свойства — в снимках `stays_*_states` на
версию. Единственный читатель снимков — `application/fund_versions.py` (`FundTimeline`), писатель —
`application/fund_drafts.py` (черновик → предпросмотр → публикация). Сегменты броней режутся на
границах версий на «части» с индексом `seg_index * PIECE_BASE + n`; чистый домен распределения
получает интервалы объектов `UnitSpan`. Работа идёт шестью этапами — шесть веток и PR, каждый
этап самостоятелен и зелёный.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Alembic, pydantic v2, openpyxl, vanilla JS без сборки,
jsdom-сценарии (`tools/*_scenario.mjs`), pytest.

**Spec:** `docs/superpowers/specs/2026-10-26-stays-fund-versions-design.md` (редакция 2).

## Global Constraints

* Постоянен только внутренний `id` категории, объекта, узла; код категории, обозначение объекта,
  категория/узел/этаж/флаги объекта, свойства категорий и дерево — в версии (спека §3.1).
* Исходная версия: `valid_from = 2000-01-01`; удалять нельзя (§3.3, §4.1).
* Версия с `valid_from = D` действует с **PM дня D**: граница `pos(D, PM)` (§3.3).
* Черновик один на весь фонд; `D ≥ сегодня`; удалять можно только версии с `valid_from > сегодня`
  и черновик (§4.1).
* `UNIQUE (version_id, label)`, `UNIQUE (version_id, code)`; составные FK внутри версии (§3.2).
* Флаг объекта: строка = «да», нет строки = «нет»; справочник флагов не версионируется,
  использованный флаг — только в архив (§3.2).
* Фильтры: внутри измерения «или», между измерениями «и», флаги — всегда «и» (§7).
* Вкладка «Брони»: по 200 строк; уровню `occupancy` — 403; поиск по телефону — только при
  `stays.guests` (§8).
* Начальная загрузка: право `stays.reset` (ADMIN_ONLY), только при выключенном «Шахматка в
  эксплуатации», слово подтверждения `ЗАМЕНИТЬ`, копия до удаления, одна транзакция; настройки
  модуля (метки, поля, «сопровождают гостей», надбавки, лимит) не удаляются (§9.3).
* Записи фонда — под `lock_module(db)`; ответы ошибок: ввод — 422, состояние/версия — 409.
* Бюджет SQL шахматки на 440 объектов × 31 день — ≤ 30 запросов (§6).
* Каждый этап: `pytest -q`, `ruff check .`, `lint-imports`, `npx eslint static/js`,
  `tools/run_stays_scenario.sh`, `tools/run_ui_check.sh` зелёные; статика — `tools/bump_version.py`;
  новые глобальные функции JS — `python tools/gen_js_globals.py`.

## Decisions taken in this plan (spec gaps)

1. **Черновик на дату существующей версии.** Если `valid_from` черновика совпадает с уже
   опубликованной версией, черновик строится на ней, а публикация **заменяет её снимок** (версия
   остаётся та же строка, черновик удаляется). Так работают и повторные правки «с сегодня».
2. **Части сегментов.** Граница версии режет сегмент на части; индекс части
   `seg_index * 1000 + n` (`PIECE_BASE = 1000`), хранится в `stays_assignments.seg_index`.
   Закрепление — на уровне сегмента (все его части); миграция умножает существующие индексы на
   1000. Шахматка склеивает соседние части с одним объектом в одну полосу.
3. **Ревизия черновика** для оптимистической защиты — колонка `stays_fund_versions.rev`,
   передаётся полем `rev` в каждой записи черновика; несовпадение → 409.
4. **Копия перед начальной загрузкой** — `data/backups/stays/stays-YYYYMMDD-HHMMSS.xlsx`
   (рядом с `data/uploads`), листы «Категории», «Дерево», «Флаги», «Объекты», «Брони», «Гости».
5. **Сортировка строк шахматки — на клиенте:** сервер отдаёт все строки с `load` (занятые ночи /
   ночи в фонде за период); сортировка и «группировать по дереву» без нового запроса.

## Review Focus

1. **Бронь, пересекающая границу версии, где объект не изменился** — должна остаться в том же
   объекте одной полосой; тест в Task 2.2 (`test_piece_keeps_unit_across_unchanged_boundary`).
2. **Публикация черновика, пролежавшего до наступления его даты** — 409 с подсказкой сдвинуть
   дату, а не молчаливая публикация «задним числом»; тест в Task 1.4
   (`test_publish_stale_draft_date_409`).
3. **Файл фонда, выгруженный и загруженный без правок** — пустой черновик (ноль изменений), а не
   «вывести всё и завести заново»; тест в Task 6.2 (`test_roundtrip_is_empty_draft`).
4. **Фильтр по флагу, появившемуся у объекта с середины месяца** — объект в шахматке есть, но
   полосы и «занято» до даты не скрываются, строка просто попадает в фильтр по дням версии;
   тест в Task 4.2 (`test_flag_filter_respects_version_day`).
5. **Повторное нажатие «Заменить всё» / две вкладки одновременно** — вторая замена получает 409
   (замок модуля + проверка, что набор данных не изменился с предпросмотра); тест в Task 6.3
   (`test_reset_twice_second_conflicts`).

---

## Этап 1 — модель версий, чтение «фонд на дату», черновик и публикация (ветка `feat/stays-fund-versions`, PR 1)

Итог этапа: старые CRUD `/categories`, `/units` заменены черновиком; все виды читают фонд через
`FundTimeline`; поведение распределения пока прежнее (без частей), если версия одна.

**Порядок выполнения: 1.1 → 1.2 → 1.4 → 1.5 → 1.3 → 1.6.** Миграция 1.1 убирает колонки, на
которых держатся старый CRUD и читатели, поэтому до конца 1.3 прогоняются только новые тесты
задачи; полный `pytest tests/stays -q` обязан быть зелёным после 1.3 и в конце этапа.

### Task 1.1: Таблицы и миграция 0010

**Files:**
- Modify: `app/modules/stays/adapters/orm.py` (Category, Unit — только `id`; новые модели)
- Create: `app/bootstrap/alembic/versions/0010_stays_fund_versions.py`
- Modify: `app/modules/stays/manifest.py` (новое право `stays.reset`, ADMIN_ONLY; аудит `stays_fund_version`, `stays_fund_import`, `stays_reset`)
- Test: `tests/stays/test_fund_schema.py`

**Interfaces:**
- Produces ORM: `FundVersion(id, valid_from: date, status: str 'draft'|'published', base_version_id, rev: int, author_id, note, created_at, published_at)`; `CategoryState(version_id, category_id, code, title, kind, weight: Decimal, escorted, sort_order)`; `FundGroup(id)`; `GroupState(version_id, group_id, parent_id, title, sort_order)`; `UnitState(version_id, unit_id, label, category_id, group_id, floor)`; `UnitFlag(id, title, color, sort_order, archived)`; `UnitStateFlag(version_id, unit_id, flag_id)`; `UnitLineage(unit_id, predecessor_id, version_id)`; `StaysSettings.in_production: bool`.
- Колонки и ограничения — спека §3.2 дословно; `Assignment.seg_index` — без изменений типа.

- [ ] **Step 1: Write the failing tests** — `test_initial_version_exists` (одна `published`
  версия `2000-01-01` после upgrade), `test_label_unique_in_version` (IntegrityError на втором
  `UnitState` с тем же `label` в той же версии, ок — в другой), `test_code_unique_in_version`,
  `test_unit_state_category_must_be_in_same_version` (составной FK, на SQLite с
  `PRAGMA foreign_keys=ON`), `test_used_flag_restrict` (удаление `UnitFlag` со строкой
  `UnitStateFlag` → IntegrityError), `test_downgrade_restores_columns` (upgrade→downgrade→
  upgrade на SQLite, как `tests/test_db_upgrade.py`).
- [ ] **Step 2: Run** `pytest tests/stays/test_fund_schema.py -v` — FAIL (нет моделей).
- [ ] **Step 3: Models + migration.** Upgrade: создать таблицы; версия `2000-01-01` из текущих
  `stays_categories`/`stays_units` (только `active`), `group_id = NULL`; `Assignment.seg_index =
  seg_index * 1000`; убрать перенесённые колонки (`batch_alter_table` для SQLite); добавить
  `stays_settings.in_production` (default false). Downgrade: вернуть колонки из исходной версии,
  `seg_index // 1000`; guard: больше одной версии → `RuntimeError` с текстом как у 0007 (с
  явным флагом окружения `STAYS_FUND_DOWNGRADE_FORCE=1` — продолжить).
- [ ] **Step 4: Run** `pytest tests/stays/test_fund_schema.py tests/test_db_upgrade.py -v` — PASS.
- [ ] **Step 5: Commit** `feat(stays): версии фонда — таблицы и миграция 0010`.

### Task 1.2: `fund_versions` — фонд на дату

**Files:**
- Create: `app/modules/stays/application/fund_versions.py`
- Test: `tests/stays/test_fund_timeline.py`

**Interfaces:**
- Produces:
  - `INITIAL_DATE = date(2000, 1, 1)`
  - `@dataclass(frozen=True) CategoryInfo(id, code, title, kind, weight: float, escorted: bool, sort_order: int)`
  - `GroupInfo(id, parent_id: int | None, title, sort_order, path: tuple[int, ...])` — путь id от корня, включая себя
  - `UnitInfo(id, label, category_id, group_id: int | None, floor: str, flags: frozenset[int])`
  - `FundSnapshot(version_id, valid_from, categories: dict[int, CategoryInfo], groups: dict[int, GroupInfo], units: dict[int, UnitInfo])`; методы `branch(group_id) -> set[int]` (узел и все потомки), `path_titles(group_id) -> tuple[str, ...]`
  - `FundTimeline(parts: list[tuple[date, FundSnapshot]])`; `on(day: date) -> FundSnapshot`; `boundaries() -> list[date]` (даты начала версий внутри диапазона, без первой); `snapshots() -> list[FundSnapshot]`
  - `fund_for(db, first: date, last: date) -> FundTimeline` — только `published`, ≤ 6 запросов
  - `fund_on(db, day: date) -> FundSnapshot`
  - `snapshot_of(db, version_id: int) -> FundSnapshot` — любой статус (для черновика)
  - `category_exists(db, category_id: int) -> bool` — постоянный id (проверка брони)
  - `boundary_pos(d: date) -> int` = `halfday.pos(d, PM)`

- [ ] **Step 1: Write the failing tests** — `test_fund_on_picks_latest_not_after_day`,
  `test_timeline_two_versions_in_month` (`on(14.11)` — старая, `on(15.11)` — новая при
  `valid_from=15.11`), `test_boundary_is_pm_of_day` (`boundary_pos(D) == pos(D, PM)`),
  `test_draft_not_visible_in_timeline`, `test_branch_and_paths` (дерево «Корпус / Блок B / Вид на
  море»), `test_fund_for_query_budget` (≤ 6 запросов при трёх версиях; фикстура `sql_counter`).
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** — пакетная загрузка состояний всех нужных версий `IN (...)`; `on()` —
  `bisect` по датам.
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `feat(stays): FundTimeline — фонд на дату`.

### Task 1.3: Перевод читателей на `FundTimeline`

**Files:**
- Modify: `app/modules/stays/application/context.py`, `allocation.py`, `views.py`, `history.py`,
  `preview.py`, `reservations.py`, `export.py`, `demo.py`, `catalog.py`, `fund.py` (`list_fund` без
  категорий/объектов — они в новом `GET /fund/snapshot`, Task 1.5)
- Modify: `app/modules/stays/domain/types.py` (`StayDay.building: str` → `group_path: tuple[int, ...]`), `domain/candidates.py` (`building` → `group_path`), `domain/allocate.py` (`UnitRef.building` → `group_path`)
- Modify: `tests/test_modules_architecture.py`
- Test: существующие `tests/stays/*`, новый `test_stays_reads_fund_only_via_timeline`

**Interfaces:**
- Consumes: Task 1.2.
- Produces: `StaysContext.fund: FundTimeline` (вместо `cats`, `units`); `StaysContext.unit_label(unit_id, day) -> str`; `StaysContext.category(cat_id, day) -> CategoryInfo`.
- `rank_candidates(day, guest_ids, unit_id, group_path: tuple[int, ...], ...)` — «тот же узел» =
  совпадение последнего id пути; ближе — длиннее общий префикс.

- [ ] **Step 1: Write the failing architecture test** — в модулях `app/modules/stays/**` кроме
  `fund_versions.py`, `fund_drafts.py`, `fund_xlsx.py` и `adapters/orm.py` нет `select(Unit`,
  `select(Category`, `db.get(Unit`, `db.get(Category`, `Unit.label`, `Category.code` (поиск по тексту
  исходников, как соседние тесты архитектуры).
- [ ] **Step 2: Run** — FAIL (список нарушений).
- [ ] **Step 3: Перевести читателей.** Вес и `escorted` в `stays_on(day)` — из
  `ctx.fund.on(day)`; обозначения в истории и предпросмотре — на дату события
  (`history`: дата записи; `preview`: дата начала сегмента); проверка категории брони в
  `reservations.py` — существует ли постоянный id (`db.get(CategoryRow)` разрешён только через
  `fund_versions.category_exists(db, cid) -> bool`). `catalog.py` экспортирует
  `fund_on`/`FundSnapshot` вместо ORM `Category`/`Unit` (внешних импортёров нет — проверено grep).
- [ ] **Step 4: Run** `pytest tests/stays -q` — все прежние тесты PASS (после Task 1.5 helpers;
  выполнять 1.3 и 1.5 в одном коммите, если helpers мешают прогону).
- [ ] **Step 5: Commit** `refactor(stays): все виды читают фонд через FundTimeline`.

### Task 1.4: `fund_drafts` — черновик, действия, публикация (без переноса и предпросмотра броней)

**Files:**
- Create: `app/modules/stays/application/fund_drafts.py`
- Test: `tests/stays/test_fund_drafts.py`

**Interfaces:**
- Consumes: Task 1.1–1.2; `lock_module`; `FundError`, `FundConflict` из `fund.py`.
- Produces:
  - `open_draft(db, valid_from: date, author_id: int | None, note: str = "") -> FundVersion` — 409 если черновик есть; 422 если `valid_from < local_date()`; база — версия на D (или версия с той же датой — Decision 1)
  - `current_draft(db) -> FundVersion | None`
  - `check_rev(draft, rev: int) -> None` (409) и `bump(draft)`; каждая функция ниже принимает `rev` и увеличивает его
  - `save_category(db, rev, data: dict, category_id: int | None) -> int`
  - `retire_category(db, rev, category_id)` — 409, если в снимке есть её объекты
  - `save_group(db, rev, data: {title, parent_id, sort_order}, group_id: int | None) -> int` — 422 на цикл
  - `retire_group(db, rev, group_id)` — 409, если есть объекты или подузлы
  - `save_unit(db, rev, data: {label, category_id, group_id, floor, flags: list[int]}, unit_id: int | None) -> int`
  - `retire_unit(db, rev, unit_id)`
  - `split_unit(db, rev, unit_id, parts: list[{label, category_id, group_id?, floor?}]) -> list[int]` — `lineage`
  - `merge_units(db, rev, unit_ids: list[int], data: {label, category_id, group_id, floor}) -> int` — 422 при разных узле/категории без явного `data.group_id`/`data.category_id`
  - `set_flag(db, rev, flag_id, unit_ids: list[int], value: bool)`
  - `diff(db, base_id: int, other_id: int) -> FundDiff` (`@dataclass FundDiff(units, categories, groups, flags)` — списки `{id, kind: added|retired|changed, before: dict, after: dict}`)
  - `publish(db, principal) -> FundVersion` — 409 «дата черновика прошла — сдвиньте на сегодня или позже», если `valid_from < local_date()`; `run_allocation`; аудит `stays_fund_version`
  - `move_draft_date(db, rev, valid_from: date)`
  - `delete_version(db, version_id)` — 409 для исходной, действующей и прошедших
  - Справочник флагов (вне черновика): `save_flag(db, data: {title, color, sort_order}, flag_id | None) -> int`, `archive_flag(db, flag_id, archived: bool)`, `delete_flag(db, flag_id)` — 409, если используется
- Все записи — `lock_module(db)` первым действием.

- [ ] **Step 1: Write the failing tests** — `test_open_draft_in_past_422`,
  `test_second_draft_409`, `test_rev_mismatch_409`, `test_change_category_of_unit_keeps_id`,
  `test_rename_category_code_keeps_id`, `test_change_label_from_date` (4003 → 4103:
  `fund_on(D-1).units[u].label == "4003"`, `fund_on(D).units[u].label == "4103"`),
  `test_split_creates_lineage`, `test_merge_mixed_groups_requires_choice`,
  `test_retire_category_with_units_409`, `test_group_cycle_422`, `test_flag_from_date`,
  `test_draft_on_existing_version_date_replaces_it`, `test_publish_stale_draft_date_409`
  (черновик на завтра, «сегодня» сдвинуто фикстурой `today` на послезавтра),
  `test_delete_current_version_409`, `test_delete_future_version_ok`,
  `test_delete_used_flag_409_archive_ok`.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.** Черновик = копия строк состояний базовой версии (`INSERT … SELECT`).
  `local_date` импортировать модулем (`from app.core import time as _time` либо
  `from app.core.time import local_date` и добавить модуль в фикстуру `today` в
  `tests/stays/conftest.py`).
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `feat(stays): черновик фонда, действия и публикация`.

### Task 1.5: API черновика и новые помощники тестов

**Files:**
- Create: `app/modules/stays/interface/fund_versions_api.py` (+ роутер в `manifest.py`)
- Modify: `app/modules/stays/interface/fund_api.py` (удалить `/categories`, `/units`; остальное — как есть)
- Modify: `tests/stays/helpers.py` (`make_category`), `tests/stays/conftest.py` (`big_fund` — через `fund_drafts`)
- Test: `tests/stays/test_fund_versions_api.py`

**Interfaces:**
- Consumes: Task 1.4.
- Produces (все под `/api/stays`, чтение — `READ` из `fund_api.py`, запись — `stays.setup`):
  - `GET /fund/snapshot?date=` и `?version_id=` → `{version: {id, valid_from, status, rev}, categories, groups, units, flags}` (узлы с `path`, объекты с `flags`)
  - `GET /fund/versions` → `[{id, valid_from, status, author, note, published_at}]`
  - `POST /fund/draft` `{valid_from, note}`; `PATCH /fund/draft` `{rev, valid_from}`; `DELETE /fund/versions/{id}`
  - `POST|PUT|DELETE /fund/draft/categories[/{id}]`, `/fund/draft/groups[/{id}]`, `/fund/draft/units[/{id}]`; `POST /fund/draft/units/{id}/split`; `POST /fund/draft/units/merge`; `PUT /fund/draft/flags` `{rev, flag_id, unit_ids, value}` — тело содержит `rev`, ответ — `{rev, id?}`
  - `GET /fund/draft/diff` → `FundDiff`
  - `POST /fund/draft/publish` (без предпросмотра — он в этапе 2)
  - `POST|PUT|DELETE /fund/flags[/{id}]`, `PUT /fund/flags/{id}/archive` `{archived}`
- Помощник: `make_category(setup_client, n_units=2, kind="villa", escorted=True, weight=4, group_id=None) -> dict` — открывает черновик на сегодня (или берёт существующий), заводит категорию и объекты, публикует; возвращает `{id, code, units: [{id, label}]}` как раньше.

- [ ] **Step 1: Write the failing tests** — `test_setup_required_for_draft_writes` (403 у
  `names_client`), `test_snapshot_readable_by_occupancy`, `test_old_crud_endpoints_gone` (404),
  `test_publish_flow_via_api` (черновик → категория → объект → публикация → объект в
  `/fund/snapshot?date=`), `test_flag_dictionary_crud`.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** роутер (pydantic-модели — по образцу `CategoryIn`; `UnitIn` без
  `building/active/sort_order`, с `group_id`, `flags`); перевести `make_category` и `big_fund`.
- [ ] **Step 4: Run** `pytest tests/stays -q` — PASS целиком.
- [ ] **Step 5: Commit** `feat(stays): API черновика фонда; тесты на новом фонде`.

### Task 1.6: Демо-сид на версиях

**Files:**
- Modify: `app/modules/stays/application/demo.py`
- Test: `tests/stays/test_demo.py`

- [ ] **Step 1: Failing tests** — `test_demo_has_tree` (узлы «Винные виллы / Семейная / Первая
  линия», «Корпус / Блок B / Вид на море»), `test_demo_has_flags`, `test_demo_future_version_splits_connect`
  (будущая версия: коннект выведен, два DLX с `lineage`), `test_demo_idempotent`.
- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** через `fund_drafts`. Исходная версия заполняется напрямую функцией
  `fund_drafts.seed_initial(db, categories: list[dict], groups: list[dict], flags: list[dict],
  units: list[dict]) -> None` (ключи — как в телах API Task 1.5; узел — `path: list[str]`,
  категория объекта — `code`, флаги — названия): пишет в версию `INITIAL_DATE`, 409 если в ней
  уже есть объекты. Только для сида и начальной загрузки (Task 6.3).
- [ ] **Step 4: Run** `pytest tests/stays/test_demo.py -v` и `tools/run_stays_scenario.sh` — PASS.
- [ ] **Step 5: Commit**, push, PR «Шахматка, часть 1/1: версии фонда — модель и черновик».

---

## Этап 2 — распределение на границах, предпросмотр, перенос в поздние версии, перевод броней (ветка `feat/stays-fund-allocation`, PR 2)

### Task 2.1: Части сегментов

**Files:**
- Modify: `app/modules/stays/domain/halfday.py`
- Test: `tests/stays/test_halfday.py`

**Interfaces:**
- Produces: `PIECE_BASE = 1000`; `@dataclass(frozen=True) Piece(index: int, seg_index: int, category_id, start, end, start_pos, end_pos)`; `pieces(segs: Sequence[Segment], boundaries: Sequence[int]) -> list[Piece]` — режет сегмент в каждой `b` с `start_pos < b <= end_pos`: левая часть `[start_pos, b-1]`, правая `[b, end_pos]`; `index = seg_index * PIECE_BASE + n`.

- [ ] **Step 1: Failing tests** — `test_piece_without_boundary_is_segment` (`index == seg*1000`),
  `test_boundary_at_pm_splits_night` (граница `pos(D, PM)`: левая заканчивается `pos(D, AM)`),
  `test_boundary_outside_segment_ignored`, `test_two_boundaries_three_pieces`.
- [ ] **Step 2–4:** run FAIL → implement → run PASS.
- [ ] **Step 5: Commit** `feat(stays): части сегментов на границах версий`.

### Task 2.2: Домен распределения на интервалах объектов

**Files:**
- Modify: `app/modules/stays/domain/allocate.py`
- Test: `tests/stays/test_allocate.py`

**Interfaces:**
- Produces: `UnitSpan(unit_id, category_id, cat_sort, label, group_path: tuple[int, ...], start_pos, end_pos)` (вместо `UnitRef`); `AllocItem.segments: tuple[Piece, ...]`; `AllocItem.pinned: Mapping[int, int]` — **по `seg_index`**; `allocate(spans, holds, items, category_codes) -> (dict[(Key, piece_index), unit_id | None], list[AllocWarning])`; новый вид предупреждения `category_missing`.
- Правила: объект подходит части, если есть его `UnitSpan` нужной категории, покрывающий часть; часть
  `n>0` того же сегмента — сначала объект предыдущей части; первая часть сегмента `k>0` (переезд) —
  другой объект, затем самый длинный общий префикс `group_path`; закрепление сегмента применяется к
  каждой его части, где объект подходит, иначе `pin_invalid` для этой части; нет ни одного
  `UnitSpan` категории на части → `category_missing` с текстом «категории {code} нет в фонде с дд.мм».

- [ ] **Step 1: Failing tests** — `test_piece_keeps_unit_across_unchanged_boundary`,
  `test_unit_category_change_moves_reservation_from_D`, `test_pin_invalid_only_after_boundary`,
  `test_category_missing_warning`, `test_move_prefers_same_group_then_common_prefix`,
  существующие тесты переведены на `UnitSpan` (один интервал на всё окно).
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** `feat(stays): распределение по интервалам объектов`.

### Task 2.3: `allocation.compute` на частях; прошлое заморожено (L1)

**Files:**
- Modify: `app/modules/stays/application/allocation.py`, `views.py` (склейка соседних частей с одним объектом в одну полосу), `context.py` (`unit_of` по частям), `reservations.py`/`interface/reservations_api.py` (закрепление сегмента → все части)
- Test: `tests/stays/test_allocation_versions.py`

**Interfaces:**
- Consumes: Task 1.2, 2.1, 2.2.
- `compute(db)`: `timeline = fund_for(db, today, max(check_out))`; `spans` — по `timeline.parts`,
  соседние одинаковые (категория, присутствие) склеиваются; части через
  `pieces(segments(...), [boundary_pos(d) for d in timeline.boundaries()])`; часть с
  `end_pos < pos(today, AM)` — заморожена **и с объектом, и без** (без объекта не распределяется).

- [ ] **Step 1: Failing tests** — `test_past_piece_without_unit_not_placed` (сценарий L1 из
  `audit/stays-audit.md`), `test_board_merges_pieces_same_unit` (одна полоса),
  `test_pin_segment_pins_all_pieces`, `test_publish_version_reallocates_future_only`,
  `test_hold_on_absent_unit_warns` (OOO/блок на дни, когда объекта нет в фонде, — предупреждение
  `hold_absent` «объекта N нет в фонде дд.мм–дд.мм», спека §14).
- [ ] **Step 2–4:** FAIL → implement → PASS (`pytest tests/stays -q` целиком).
- [ ] **Step 5: Commit** `feat(stays): распределение на границах версий; прошлое не размещается`.

### Task 2.4: Предпросмотр публикации, перенос в поздние версии, перевод броней

**Files:**
- Modify: `app/modules/stays/application/fund_drafts.py`, `interface/fund_versions_api.py`
- Test: `tests/stays/test_fund_publish.py`

**Interfaces:**
- Produces:
  - `publish(db, principal, propagate: bool = True, transfers: list[Transfer] = ()) -> PublishResult`; `@dataclass Transfer(reservation_id: int, category_id: int)`; `PublishResult(version, propagated: list[dict], kept: list[dict], skipped: list[dict])`
  - перенос — правило §4.4 поле за полем относительно `base_version_id`;
  - перевод брони: заезд ≥ D → меняется `Reservation.category_id`; бронь живёт на D → добавляется
    `Move(move_date=D, category_id)`; журнал брони и аудит;
  - `POST /fund/draft/publish?preview=1` `{rev, propagate, transfers}` — через `_ops.run` (тот же
    `preview.run_operation`), ответ `{preview, result: {fund_diff, propagated, kept, skipped, affected: {moved, unassigned, pin_invalid, category_missing}}, diff}`.

- [ ] **Step 1: Failing tests** — `test_preview_equals_publish` и `test_preview_leaves_db_clean`
  (как `test_preview.py`), `test_propagate_untouched_field`, `test_propagate_keeps_later_own_change`,
  `test_propagate_label_conflict_skipped`, `test_propagate_false_leaves_later_versions`,
  `test_transfer_whole_reservation`, `test_transfer_live_reservation_adds_move`,
  `test_preview_lists_unassigned_after_connect_split`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit**, push, PR «Шахматка, часть 1/2: распределение на границах версий и публикация».

---

## Этап 3 — экран «Настройки → Фонд» (ветка `feat/stays-fund-settings-ui`, PR 3)

### Task 3.1: Экран фонда: дерево, объекты, черновик, история

**Files:**
- Create: `static/js/modules/stays_fund.js` (новый экран; `stays_settings.js` — без `renderStaysFund`)
- Modify: `templates/index.html` (подключить скрипт), `tools/js_globals.json` (генератором), `app/modules/stays/manifest.py` (Screen «Фонд и категории» → `renderStaysFund` из нового файла — имя прежнее)
- Test: `tools/stays_fund_scenario.mjs`, `tools/run_stays_fund_scenario.sh`; запуск добавить в CI-задачу frontend (`.github/workflows/ci.yml`)

**Interfaces:**
- Consumes: API Task 1.5, 2.4.
- Produces глобальные функции: `renderStaysFund(host)`, `staysFundTree(snapshot, selectedId) -> string`, `openFundUnitForm(unit, snapshot, onSaved)`, `openFundSplitForm(unit, snapshot, onSaved)`, `openFundMergeForm(unitIds, snapshot, onSaved)`, `openFundPublish(onDone)` (предпросмотр → галочки перевода броней → «Применить к поздним версиям» → публикация).
- Вид — согласованный макет (спека §10): шапка «Фонд на дату» (действующая / черновик / версия из
  истории), плашка черновика, дерево слева (клик — объекты ветки), объекты справа с пометками
  «с дд.мм / изменён / новый · из N / выведен с дд.мм», вкладки «Объекты / Флаги объектов /
  Категории», история версий; `#id` мелким серым.
- Изменения черновика всегда отправляют `rev`; 409 → тост «Черновик изменил другой пользователь» и
  перезагрузка снимка.
- Гонки переключения версии — `loadGenerationFor(host)`.

- [ ] **Step 1: Failing scenario** — `stays_fund_scenario.mjs` под `admin`: открыть экран, создать
  черновик с завтра, разделить объект демо-коннекта на два с новыми номерами, отметить флаг у узла,
  предпросмотр показывает «без объекта» для брони коннекта, перевести её галочкой, опубликовать;
  затем `GET /fund/snapshot?date=<завтра>` содержит новые объекты и флаг; под `rukovod` экран
  недоступен.
- [ ] **Step 2: Run** `tools/run_stays_fund_scenario.sh` — FAIL.
- [ ] **Step 3: Implement** экран.
- [ ] **Step 4: Run** сценарий, `tools/run_ui_check.sh`, `npx eslint static/js` — PASS;
  `python tools/gen_js_globals.py`, `python tools/bump_version.py <дата><буква>`.
- [ ] **Step 5: Commit**, push, PR «Шахматка, часть 1/3: экран фонда».

---

## Этап 4 — месячный вид, дерево в шахматке, фильтры и сортировка (ветка `feat/stays-month-filters`, PR 4)

### Task 4.1: Сервер: строки по дереву, «нет в фонде», нагрузка, загрузка по узлам

**Files:**
- Modify: `app/modules/stays/application/views.py` (`BoardFilters`, `units_board`, `occupancy_grid`), `interface/views_api.py`, `interface/boards_api.py`, `application/boards.py` (`DayFilters`)
- Test: `tests/stays/test_units_board.py`, `tests/stays/test_occupancy_and_mine.py`, новый `tests/stays/test_board_filters.py`

**Interfaces:**
- `BoardFilters(group_ids: tuple[int, ...] = (), category_ids: tuple[int, ...] = (), flag_ids: tuple[int, ...] = (), kinds: tuple[str, ...] = (), floor: str | None = None, escorted_only=False, vip=False, employee_id=None, q="")`; API — повторяющиеся query-параметры `group_ids`, `category_ids`, `flag_ids`, `kinds`; параметры `building` и одиночный `category_id` удаляются.
- Объект проходит фильтр **в день d**, если в `fund.on(d)` он в ветке одного из `group_ids`, его категория в `category_ids`, вид категории в `kinds`, все `flag_ids` ⊆ его флагов (пустой фильтр измерения = проходит). Строка показывается, если объект прошёл хотя бы в один день периода; дни, где не прошёл или нет в фонде, отдаются в `row.off: [[first, last], …]` с причиной `"absent" | "filtered"`.
- Строка: `{unit_id, label, labels: [{from, label}], category_id, categories: [{from, category_id}], group_path: [id…], floor, flags: [id…], load: float}`; `load` = занятые ночи / ночи в фонде за период, 0..1, `round(…, 3)`.
- `occupancy_grid(db, first, last, f: BoardFilters)` → `{days, total: NodeRow, nodes: [NodeRow]}`; `NodeRow = {group_id: int | None, path: [str], days: [{total, living, guests, arrivals, departures, free, ooo, blocks, pct: float | None}]}` — определения строк и формула `pct = (living + blocks) / (total − ooo)` (None при 0) — спека §6.1 дословно; `total` — «Итого по выбранному»; узлы — по фильтру `group_ids` (пустой — корневые узлы); всё по фонду дня.

- [ ] **Step 1: Failing tests** — `test_or_within_dimension_and_between` («Корпус» ∪ «Виллы»;
  «Виллы» ∩ флаг), `test_flags_are_and`, `test_flag_filter_respects_version_day`,
  `test_absent_days_marked` (объект выведен с 15.11 → `off` с 15.11 `absent`),
  `test_label_change_listed`, `test_load_metric`, `test_occupancy_by_tree_totals_per_day`,
  `test_occupancy_rows` (на одном объекте за день: заезд и выезд в тот же объект — по 1 в обеих
  строках и 1 в «Проживают»; OOO уменьшает знаменатель; блок — в числителе; «Свободно» не
  отрицательное; «Гостей» по составу; `pct` None при всём фонде в OOO),
  `test_occupancy_total_is_sum_of_selected_nodes`,
  `test_day_board_filters_by_group_and_flags` (табло дня — те же измерения),
  `test_month_query_budget_440_units` (31 день, ≤ 30 запросов), удалённые параметры → 422.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** `feat(stays): фильтры по дереву, флагам и категориям; строки по дереву`.

### Task 4.2: Клиент: месяц, «Сегодня», панель фильтров, сортировка, группировка

**Files:**
- Modify: `static/js/modules/stays.js` (`staysState`, `staysToolbar`, `staysBoardParams`, `renderUnitsBoard`), `static/js/modules/stays_board.js` (`renderButlersBoard`, `renderOccupancyGrid`)
- Create: `static/js/modules/stays_filters.js`
- Test: `tools/stays_scenario.mjs` (расширить)

**Interfaces:**
- Месяц — общий `state.year / state.month`; `staysMonthRange() -> {first, last}`; кнопки ◀ ▶ меняют
  `state.month/state.year` (как `mgmt.js`), «Сегодня» — текущий месяц + докрутка и подсветка колонки
  (как `tabel.js`). Селекторы `sb-days`, `bb-days` удаляются.
- `stays_filters.js`: `staysFilterPanel(fund, filters, onChange) -> HTMLElement`; `staysSavedFilters() -> [{name, filters}]`, `staysSaveFilter(name, filters)`, `staysDeleteFilter(name)` — `localStorage['stays.filters']`, каждый доступ в `try/catch`, без хранилища — пустой список.
- Сортировка строк: `staysSortRows(rows, {by: 'tree'|'label'|'category'|'floor'|'load', dir: 'asc'|'desc', grouped: bool}, fund)`; по умолчанию `tree`, `grouped=true`; номер и категория — по значению на первый день месяца.
- Разделы дерева сворачиваются; свёрнутые строки не рисуются; по умолчанию развёрнуты узлы,
  где есть категории вида `villa|estate|apartment`, свёрнуты остальные.
- Дни `off` — серый фон «нет в фонде» / приглушённые «вне фильтра»; подпись `labels` у строки
  («4003 → 4103 с 15.11»).
- Гонки — `loadGenerationFor(body)` на каждом виде.
- «Загрузка» (`renderOccupancyGrid`): весь месяц, узлы сворачиваются кликом по названию,
  развёрнутый узел — 8 строк спеки §6.1, свёрнутый — одна строка; переключатель «% / штуки»;
  клик по клетке «Проживают» — вкладка «Объекты» с фильтром узла и прокруткой к дню.

- [ ] **Step 1: Failing scenario steps** в `stays_scenario.mjs`: смена месяца ◀ ▶ синхронна с
  Табелем (открыть Табель → месяц тот же); «Сегодня» подсвечивает колонку; фильтр «Корпус» +
  «Винные виллы» показывает оба раздела; флаг сужает; сортировка «по загрузке ↓» без
  группировки — первая строка с максимальным `load`; «Загрузка» показывает все дни месяца и
  восемь строк у развёрнутого узла, свёрнутый — одну; сохранённый набор переживает перезагрузку;
  быстрая смена месяцев не показывает устаревший месяц.
- [ ] **Step 2–4:** FAIL → implement → PASS (+ `tools/run_ui_check.sh`, eslint, `gen_js_globals`, `bump_version`).
- [ ] **Step 5: Commit**, push, PR «Шахматка, часть 1/4: месяц, дерево, фильтры и сортировка».

---

## Этап 5 — вкладка «Брони» (ветка `feat/stays-bookings-tab`, PR 5)

### Task 5.1: API списка броней и выгрузка

**Files:**
- Create: `app/modules/stays/application/bookings.py`
- Modify: `app/modules/stays/interface/views_api.py` (или новый `bookings_api.py` + роутер в манифесте)
- Test: `tests/stays/test_bookings_list.py`

**Interfaces:**
- `@dataclass(frozen=True) BookingQuery(first: date, last: date, mode: Literal['stay','check_in','check_out','created'] = 'stay', filters: BoardFilters = BoardFilters(), statuses: tuple[str, ...] = (), label_ids: tuple[int, ...] = (), unassigned: bool = False, with_warnings: bool = False, sort: str = 'check_in', dir: Literal['asc','desc'] = 'asc', offset: int = 0, limit: int = 200)`; `limit` ≤ 200.
- `list_bookings(db, q: BookingQuery, level: Level, can_guests: bool) -> {total: int, rows: list[dict]}`; строки — колонки §8; сортируемые поля: `number, guest, check_in, check_out, nights, category, unit, status, created_at`; вторичный ключ — `number`, затем `id`.
- `GET /api/stays/bookings` — `stays.view`; уровень `occupancy` → 403; поиск `q` по телефону выполняется только при `can_guests` (иначе цифры телефона не сравниваются).
- `GET /api/stays/bookings/export` — `stays.export`, xlsx лист «Бронирования», аудит `stays_export` с параметрами.

- [ ] **Step 1: Failing tests** — `test_modes_stay_checkin_checkout_created`,
  `test_sort_each_column_both_directions`, `test_pagination_200_and_total`,
  `test_occupancy_level_403`, `test_phone_search_requires_guests`,
  `test_filters_reuse_board_semantics` (узел ∪, флаги ∩), `test_bookings_query_budget` (≤ 12
  запросов на 300 броней), `test_export_audited`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** `feat(stays): список броней — API и выгрузка`.

### Task 5.2: Клиент вкладки «Брони»

**Files:**
- Create: `static/js/modules/stays_bookings.js`
- Modify: `static/js/modules/stays.js` (`STAYS_TABS` += `['bookings', 'Брони']`, видимость — `can('stays.view')`; `staysTabRender`)
- Test: `tools/stays_scenario.mjs`

**Interfaces:**
- `renderBookings(body)`; период — общий месяц или свой диапазон (два поля дат); режим попадания;
  панель фильтров из `stays_filters.js`; клик по заголовку — сортировка, повторный — направление;
  «Показать ещё» (+200); клик по строке — `openReservationCard(rid, onChanged)`; кнопка «Выгрузить»
  при `can('stays.export')`.

- [ ] **Step 1: Failing scenario** — под `admin`: вкладка «Брони», сортировка по «Выезд ↓», «Показать
  ещё» добавляет строки, клик открывает карточку; под пользователем уровня occupancy вкладки нет.
- [ ] **Step 2–4:** FAIL → implement → PASS (+ ui_check, eslint, globals, bump).
- [ ] **Step 5: Commit**, push, PR «Шахматка, часть 1/5: вкладка «Брони»».

---

## Этап 6 — выгрузка и загрузка фонда, начальная загрузка (ветка `feat/stays-fund-xlsx`, PR 6)

### Task 6.1: Файл фонда — выгрузка и разбор

**Files:**
- Create: `app/modules/stays/application/fund_xlsx.py`
- Test: `tests/stays/test_fund_xlsx.py`

**Interfaces:**
- `export_fund(snapshot: FundSnapshot, flags: list[UnitFlag]) -> bytes` — листы и колонки §9.1;
  колонка ID — серая, лист защищён только на ID (`protection.locked` у ячеек ID, у прочих — нет).
- `@dataclass ParsedFund(categories, groups, flags, units)` — строки с `row_no`, `id: int | None`,
  ссылки по коду и пути, `predecessors: list[int]`; `@dataclass FileError(sheet, row, message)`.
- `parse_fund(data: bytes) -> tuple[ParsedFund | None, list[FileError]]` — проверки §9.2 (повтор
  ID/номера/кода, путь без родителя, цикл, «да/нет» с опечаткой, неизвестная категория в «Объектах»,
  неизвестный ID в «Из чего»); «да/нет» принимаются как `да|нет|1|0|true|false|yes|no` без регистра.

- [ ] **Step 1: Failing tests** — `test_export_has_four_sheets_and_id_column`,
  `test_parse_roundtrip_equals_snapshot`, по тесту на каждую ошибку из §9.2 с листом и строкой,
  `test_new_flag_column_becomes_flag`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** `feat(stays): файл фонда — выгрузка и разбор`.

### Task 6.2: «Загрузить как черновик с даты»

**Files:**
- Modify: `app/modules/stays/application/fund_drafts.py` (`apply_file(db, rev, parsed: ParsedFund) -> FundDiff` — сопоставление по ID, пусто → новая, нет строки → вывести, «Из чего» → `lineage`), `interface/fund_versions_api.py`
- Test: `tests/stays/test_fund_import.py`

**Interfaces:**
- `GET /fund/export?date=` (`stays.setup`) → xlsx; `POST /fund/import` multipart `file`, поля
  `valid_from` → открывает черновик (409, если он уже есть) и применяет файл; ответ — `FundDiff` и
  список «будут выведены»; ошибки файла → 422 `{errors: [{sheet, row, message}]}`; аудит
  `stays_fund_import`.

- [ ] **Step 1: Failing tests** — `test_roundtrip_is_empty_draft`, `test_missing_row_retires`,
  `test_empty_id_creates`, `test_from_column_lineage`, `test_unknown_id_422_nothing_applied`,
  `test_import_with_existing_draft_409`, `test_code_change_with_same_id_is_rename`.
- [ ] **Step 2–4:** FAIL → implement → PASS.
- [ ] **Step 5: Commit** `feat(stays): загрузка файла фонда черновиком`.

### Task 6.3: Начальная загрузка и «Шахматка в эксплуатации»

**Files:**
- Create: `app/modules/stays/application/fund_reset.py`
- Modify: `interface/fund_versions_api.py`, `static/js/modules/stays_fund.js` (кнопки «Выгрузить фонд», «Загрузить фонд» с выбором режима, диалог подтверждения со словом «ЗАМЕНИТЬ», переключатель «Шахматка в эксплуатации» — виден только при `can('stays.reset')`)
- Test: `tests/stays/test_fund_reset.py`, `tools/stays_fund_scenario.mjs`

**Interfaces:**
- `reset_counts(db) -> dict[str, int]` — что будет удалено (объекты, категории, узлы, версии,
  брони, гости, назначения батлеров, OOO/блоки); тот же словарь — `fingerprint` для 409 при
  повторе.
- `backup_module(db) -> Path` — `data/backups/stays/stays-YYYYMMDD-HHMMSS.xlsx` (Decision 4).
- `initial_load(db, parsed: ParsedFund, principal, expected_counts: dict) -> dict` — `lock_module`;
  409, если `in_production`, или `reset_counts(db) != expected_counts`; копия; удаление данных
  шахматки (все таблицы `stays_*`, кроме `stays_settings`, `stays_labels`, `stays_custom_fields`,
  `stays_escorts`); `fund_drafts.seed_initial(...)` из `parsed` (ID игнорируются); аудит `stays_reset` (удалено,
  загружено, имя файла копии).
- `set_in_production(db, principal, value: bool)` — аудит.
- API: `POST /fund/reset?preview=1` multipart `file` → `{counts, will_load, warnings: ["ID в файле
  будут проигнорированы"], fingerprint}`; `POST /fund/reset` multipart `file`, `confirm`, `fingerprint`
  → `confirm != "ЗАМЕНИТЬ"` → 422; `GET /fund/backups/{name}` → файл копии (`stays.reset`, имя по
  шаблону, без путей); `PUT /fund/in-production` `{value}` — `stays.reset`.

- [ ] **Step 1: Failing tests** — `test_reset_requires_stays_reset_perm` (manager → 403),
  `test_reset_blocked_in_production_409`, `test_reset_wrong_confirm_422`,
  `test_reset_backup_written_before_delete`, `test_reset_keeps_employees_schedule_tabel_audit_and_module_settings`,
  `test_reset_bad_file_deletes_nothing`, `test_reset_twice_second_conflicts`,
  `test_reset_ignores_ids_with_warning`, `test_backup_download_rejects_path_traversal`.
- [ ] **Step 2–4:** FAIL → implement → PASS; сценарий `stays_fund_scenario.mjs`: выгрузить фонд,
  загрузить его же черновиком (ноль изменений), под admin — предпросмотр начальной загрузки без
  подтверждения.
- [ ] **Step 5: Commit**, push, PR «Шахматка, часть 1/6: файл фонда и начальная загрузка».

---

## После этапа 6

- Обновить `docs/GUIDE.md` (раздел «Шахматка»: версии фонда, файл, начальная загрузка) и
  `CHANGELOG.md` — в PR 6.
- Отметить в `audit/stays-audit.md`, что L1 закрыт этапом 2.
