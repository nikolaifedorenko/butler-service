# Шахматка, часть 1 — дополнение: виды, дерево в Excel, гости и семейное дерево, оплата — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** справочник видов категорий, дерево в файле фонда через колонку «Родитель», вкладка
«Гости» с объединением дублей, семейное дерево с вычисляемым родством и визуальным редактором,
«Оплата за» выбором категории, без «Повода визита».

**Architecture:** справочник видов — как справочник флагов (не версионируется, ссылка из
`stays_category_states.kind_id`). Родство — чистая функция `domain/kinship.py` над первичными
связями `parent` / `spouse`; остальное — представление. Гости — новый модуль
`application/guests_list.py` + вкладка `stays_guests.js`; семейный редактор — `stays_family.js`.
Боевой базы нет: миграции меняют схему без переноса данных, демо-сид пересоздаётся.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Alembic, openpyxl, vanilla JS, jsdom-сценарии, pytest.

**Spec:** `docs/superpowers/specs/2026-10-28-stays-part1-addendum-design.md`.

## Global Constraints

* Справочник видов: `title` уникален, использованный вид — только в архив, удаление — 409; вид у
  категории обязателен (спека §1).
* Лист «Дерево»: `ID | Название | Родитель | Порядок`; «Родитель» и «Узел» — полный путь через
  « / »; глубина не ограничена; выпадающие списки — скрытый лист «Списки» (§2).
* Круговая выгрузка/загрузка файла фонда без правок — пустой черновик (Review Focus 3 части 1).
* Вкладка «Гости» — право `stays.guests`; уровню occupancy — нет; телефон и дата рождения — только
  полный уровень (§3).
* Первичные семейные связи только `parent` (≤ 2 родителя) и `spouse` (с «бывшие»); родство —
  вычисляется, не хранится (§4).
* Пол гостя: `m | f | ''`; без пола — нейтральные названия (§4).
* `paid_category_id` вместо `paid_by`; `purpose` удалён (§5).
* Записи — под `lock_module(db)`; ввод — 422, состояние — 409.
* Каждая задача: `pytest -q`, `ruff check .`, `lint-imports`, `npx eslint static/js`,
  `python tools/check_api_contract.py`, `python tools/export_openapi.py --check` (схема
  перегенерирована), `python tools/bump_version.py --check` (версия статики — явно, строго больше
  последней), `python tools/gen_js_globals.py --check`, сценарии шахматки/фонда, `tools/run_ui_check.sh`.

## Review Focus

1. **Объединение двух гостей, проживающих в одной брони** — бронь остаётся с одним гостем, без
   дубля в составе и без ошибки уникальности; тест в Task B2 (`test_merge_guests_in_same_reservation`).
2. **Семейная связь, создающая цикл через брак** (сделать супругом своего внука) — 422, а не
   бесконечный обход; тест в Task B1 (`test_spouse_cannot_be_descendant`).
3. **Узел в файле, чей «Родитель» стоит ниже по листу** — узел создаётся, порядок строк не важен;
   тест в Task A2 (`test_tree_parent_below_child`).
4. **Вид, переведённый в архив, у существующей категории** — категория показывается и фильтруется,
   в выборе для новой категории вида нет; тест в Task A1 (`test_archived_kind_still_shown`).
5. **Бронь с «оплата за» категорией, которой нет в фонде на дату заезда** — 422 при сохранении,
   а не молчаливое сохранение; тест в Task A3 (`test_paid_category_must_exist_on_check_in`).

---

## Этап A — фонд и бронь (ветка `feat/stays-addendum-fund`, PR A)

### Task A1: Справочник видов категорий

**Files:** `adapters/orm.py` (`CategoryKind`, `CategoryState.kind_id`), миграция `0012_stays_category_kinds.py`, `application/fund.py` (убрать `KINDS`), `application/fund_drafts.py`, `application/fund_versions.py` (`CategoryInfo.kind_id`, `kind_title`), `application/views.py` (`BoardFilters.kinds` → `kind_ids: tuple[int, ...]`), `interface/fund_versions_api.py` (`/fund/kinds` CRUD + архив), `application/fund_xlsx.py` (колонка «Вид» по названию), `application/demo.py`, `static/js/modules/stays_fund.js` (вкладка «Виды», выбор в форме категории), `static/js/modules/stays_filters.js`, `static/js/modules/stays.js` (раскрытие по `expanded`).
**Test:** `tests/stays/test_category_kinds.py`, правки затронутых тестов, `tools/stays_fund_scenario.mjs`.

**Interfaces:** `CategoryKind(id, title, sort_order, expanded: bool, archived: bool)`; `save_kind(db, data, kind_id|None) -> int`, `archive_kind(db, kind_id, archived)`, `delete_kind(db, kind_id)` (409 если используется); `GET /fund/snapshot` отдаёт `kinds: [{id, title, sort_order, expanded, archived}]`, категории — `kind_id`; фильтр — повторяемый `kind_ids`.

- [ ] Тесты: `test_kind_crud`, `test_delete_used_kind_409_archive_ok`, `test_archived_kind_still_shown`, `test_filter_by_kind_ids`, `test_expanded_kind_opens_section` (jsdom), `test_xlsx_kind_by_title`, `test_xlsx_unknown_kind_error`, круговой тест файла фонда.
- [ ] RED → реализация → GREEN; коммит `feat(stays): справочник видов категорий`.

### Task A2: Дерево в файле фонда — колонка «Родитель», выпадающие списки

**Files:** `application/fund_xlsx.py`, `tests/stays/test_fund_xlsx.py`, `tests/stays/test_fund_import.py`.

**Interfaces:** лист «Дерево» `ID | Название | Родитель | Порядок`; скрытый лист «Списки» (колонка A — все пути, отсортированы как дерево); проверка данных `list` на «Родитель» (лист «Дерево») и «Узел» (лист «Объекты»); `ParsedGroup.path` строится из «Родитель» + «Название».

- [ ] Тесты: `test_tree_parent_below_child`, `test_tree_missing_parent_error_with_row`, `test_tree_depth_seven`, `test_export_has_lists_sheet_and_validation`, `test_roundtrip_is_empty_draft` (существующий — остаётся зелёным).
- [ ] RED → реализация → GREEN; коммит `feat(stays): дерево в файле фонда — колонка «Родитель»`.

### Task A3: Бронь — «Оплата за» категорией, без «Повода визита»

**Files:** `adapters/orm.py`, миграция `0013_stays_paid_category.py` (drop `purpose`, `paid_by`; add `paid_category_id`), `application/reservations.py` (`LOCKED`), `interface/reservations_api.py`, `application/views.py` (карточка: пометка апгрейда), `application/bookings.py` и выгрузки, `static/js/modules/stays_forms.js`, `static/js/modules/stays_bookings.js`, `application/demo.py`, спека части 4 (`2026-10-27-stays-butler-mine-design.md` §3 — список запертых полей).
**Test:** `tests/stays/test_reservations_api.py` (+ новые), `tools/stays_scenario.mjs`.

- [ ] Тесты: `test_paid_category_defaults_to_booking_category`, `test_paid_category_must_exist_on_check_in`, `test_upgrade_mark_in_card_and_bookings`, `test_purpose_removed_from_api_and_export`, `test_butler_cannot_change_paid_category`.
- [ ] RED → реализация → GREEN; коммит `feat(stays): «Оплата за» — категория, без «Повода визита»`; push, PR A.

## Этап B — гости и семейное дерево (ветка `feat/stays-guests`, PR B)

### Task B1: Пол гостя, первичные семейные связи, вычисление родства

**Files:** `adapters/orm.py` (`Guest.gender`, `GuestLink.former: bool`), миграция `0014_stays_guest_family.py`, `domain/kinship.py` (новый), `application/guests.py` (`LINK_KINDS`: `child` → `parent`; `add_link` — проверки), `application/views.py`/`boards.py` (родственники среди проживающих), `application/demo.py` (семья из 3 поколений).
**Test:** `tests/stays/test_kinship.py`, `tests/stays/test_guests_api.py`.

**Interfaces:**
- `@dataclass(frozen=True) Person(id: int, gender: str)`; `@dataclass(frozen=True) Kin(person_id: int, title: str, degree: int, via: tuple[int, ...])`
- `kin_of(person_id: int, people: Mapping[int, Person], parents: Mapping[int, tuple[int, ...]], spouses: Mapping[int, tuple[tuple[int, bool], ...]]) -> list[Kin]` — все названия §4 спеки по полу, нейтральные при `gender == ''`; бывшие супруги (`former`) не дают свойственников.
- `check_parent(child, parent, graph) -> str | None`, `check_spouse(a, b, graph) -> str | None` — текст ошибки или None.
- `GET /api/stays/guests/{gid}/family` → `{people: [{id, name, gender, level}], parents: [[child, parent]…], spouses: [[a, b, former]…], kin: [{person_id, title, degree}]}` — граф семьи в пределах 3 поколений вверх/вниз и брака.

- [ ] Тесты: по тесту на каждую группу названий (родители/дети, сиблинги, деды/внуки, прадеды/правнуки, дяди/племянники, двоюродные, свойственники — каждое по полу и без пола); `test_owner_example_son_is_great_grandson_of_ivans_grandmother`; `test_third_parent_422`; `test_cannot_be_own_ancestor`; `test_spouse_cannot_be_descendant`; `test_former_spouse_gives_no_in_laws`; `test_family_endpoint_visibility` (occupancy — 403; names — без телефонов).
- [ ] RED → реализация → GREEN; коммит `feat(stays): семейные связи и вычисление родства`.

### Task B2: Вкладка «Гости» и объединение дублей

**Files:** `application/guests_list.py` (новый), `application/guests.py` (`merge_guests`), `interface/guests_api.py`, `static/js/modules/stays_guests.js` (новый), `static/js/modules/stays.js` (`STAYS_TABS` += `['guests', 'Гости']` при `can('stays.guests')`), `templates`/`index.html`, `sw.js`.
**Test:** `tests/stays/test_guests_list.py`, `tools/stays_scenario.mjs`.

**Interfaces:** `GET /api/stays/guests/list?q=&level=&stayed_from=&stayed_to=&birthday_days=&sort=&dir=&offset=&limit=` → `{total, rows: [{id, name, level, gender, phone?, last_stay, stays}]}` (≤ 200); `GET /api/stays/guests/{gid}/stays` → история проживаний; `POST /api/stays/guests/merge?preview=1` `{keep_id, drop_id}` → `{moves: {reservations, links, special_dates, preferences}}`; аудит `stays_guest_merge`.

- [ ] Тесты: `test_guests_list_search_filters_sort`, `test_guests_list_phone_only_full_level`, `test_guests_tab_occupancy_403`, `test_merge_guests_moves_everything`, `test_merge_guests_in_same_reservation`, `test_merge_preview_equals_save`, `test_merge_keeps_family_links_without_duplicates`; сценарий: вкладка, поиск, фильтр «день рождения», карточка, объединение.
- [ ] RED → реализация → GREEN; коммит `feat(stays): вкладка «Гости», объединение дублей`.

### Task B3: Визуальный семейный редактор

**Files:** `static/js/modules/stays_family.js` (новый), карточка гостя в `stays_guests.js` и в карточке брони, `static/css/app.css`.
**Test:** `tools/stays_scenario.mjs` (шаги семейного редактора).

**Interfaces:** `renderFamilyTree(host, guestId, {editable})` — центр, родители сверху, супруги рядом, дети снизу, сиблинги по бокам (из `/family`); клик по человеку — перецентровка; кнопки «+ родитель / + супруг(а) / + ребёнок» → поиск гостя или новый (фамилия, имя, пол) → `POST /guests/{gid}/links`; крестик на линии → `DELETE`; ошибки 422 → тост с текстом сервера; под деревом — список «Все родственники» из `kin`. Без внешних библиотек; рисование — HTML/CSS-сетка или inline SVG; всё экранируется `esc`.

- [ ] Сценарий: добавить Ивану и Марии сына → у бабушки Ивана в списке «правнук»; перецентровка; запрет третьего родителя показывает тост; удаление связи.
- [ ] RED → реализация → GREEN; коммит `feat(stays): семейное дерево — визуальный редактор`; push, PR B.
