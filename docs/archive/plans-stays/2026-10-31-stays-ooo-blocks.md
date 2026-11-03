# Шахматка, часть 2: OOO по половинкам, блоки по категориям, пожелания гостей — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** OOO — объект по половинкам суток; блок — остаток «категория × ночь», раскладываемый
автоматически; приоритет OOO → блоки → подтверждённые/заселённые → предварительные; овербукинг с
правом `stays.overbook`; правило «без пинг-понга»; пожелания главного гостя и HK-правило; вкладки
«Блоки» и «OOO».

**Architecture:** `stays_holds` заменяется двумя моделями: `stays_ooo` (объект, половинки) и
`stays_blocks` + `stays_block_nights` (остаток по ночам). Чистый домен получает OOO как занятость
объекта, блоки — как слоты (`domain/blocks.py`), брони — с классом приоритета; распределитель
(`domain/allocate.py`) раскладывает по порядку §4.2 спеки. Проверка «нового овербукинга» —
сравнение предупреждений до/после в общем пути операций (`preview.run_operation`). Один PR (боевой
базы нет; миграция без переноса истории).

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Alembic, vanilla JS, jsdom-сценарии, pytest.

**Spec:** `docs/superpowers/specs/2026-10-27-stays-ooo-blocks-design.md` (ред. 3).

## Global Constraints

* Приоритет при нехватке: OOO → заморожено (прошлые части; части заселённых, которые OOO/фонд не
  отнимают) → слоты блоков → закрепления броней → подтверждённые и заселённые → предварительные
  (спека §4.2).
* Блок никогда не переселяет заселённого гостя; OOO переселяет (один раз, до конца проживания)
  (§2, §4.3).
* Блоки и OOO не уменьшаются и не удаляются автоматически; без объекта остаётся бронь —
  `overbooked`; блоку не хватило — `block_short` (§4.2).
* Новый овербукинг — только с `stays.overbook` (по умолчанию старший и выше), иначе 409 с
  предпросмотром; существующий не мешает; импорт из Fidelio — без проверки (§7).
* «Без пинг-понга»: незаселённая бронь — в объект на весь срок или овербукинг; заселённая — один
  переезд с ночи D до конца (§4.3).
* Выбор объекта: закрепление → непрерывность → пожелания главного гостя → HK → порядок (§4.3).
* Ночь D = `pos(D, PM)..pos(D+1, AM)`; OOO — `[pos(start, start_half), pos(end, end_half)]`.
* Блок без закрепления; полосы блока не перетаскиваются (§2, §6).
* Блок и OOO — права `stays.edit`; прошлое можно править, всё в журнале; прошлые части броней не
  переселяются (§4.5, §7).
* Окно предпросмотра для OOO и блоков — ±62 дня вокруг изменения (§7).
* Все записи — под `lock_module(db)`; ввод — 422, состояние/версия — 409.
* Бюджет SQL шахматки на 440 объектов × 31 день — ≤ 30 запросов (часть 1).
* Каждая задача: `pytest -q`, `ruff check .`, `lint-imports`, `npx eslint static/js`,
  `python tools/check_api_contract.py`, `python tools/export_openapi.py --check`,
  `python tools/bump_version.py --check` (версия статики — явно, строго больше последней),
  `python tools/gen_js_globals.py --check`, сценарии шахматки/фонда, `tools/run_ui_check.sh`.

## Review Focus

1. **Блок на категорию, где все объекты заняты заселёнными гостями** — `block_short`, ни один
   гость не переселён, овербукинга нет; тест в Task 2 (`test_block_never_moves_in_house`).
2. **Предварительная и подтверждённая бронь конкурируют за последний объект после нового блока**
   — без объекта остаётся предварительная, даже если подтверждённая создана позже; тест в Task 2
   (`test_tentative_loses_first`).
3. **Правка прошлого OOO (продлили назад на 3 дня), когда в эти дни жил гость** — история гостя не
   меняется, на шахматке за прошлые дни предупреждение о наложении; тест в Task 3
   (`test_past_ooo_edit_does_not_move_past_pieces`).
4. **Операция без `stays.overbook`, которая убирает один овербукинг и создаёт другой** — 409
   (новый овербукинг), а не «количество не выросло»; тест в Task 3
   (`test_overbook_check_by_identity_not_count`).
5. **Блок на 90 ночей × 6 категорий** — сохранение и предпросмотр в пределах окна ±62 дня,
   бюджет SQL шахматки не превышен; тест в Task 4 (`test_long_block_preview_window`).

---

## Ветка `feat/stays-ooo-blocks`, один PR

### Task 1: Модели, миграция, право, сброс, демо

**Files:** `app/modules/stays/adapters/orm.py` (`Ooo`, `Block`, `BlockNight`, `GuestPref`; удалить `Hold`), миграция `0015_stays_ooo_blocks.py`, `app/modules/stays/manifest.py` (`Perm("stays.overbook", …, SUPERVISOR_UP)`; аудит `stays_ooo`, `stays_block`), `application/fund_reset.py` (WIPE + сырые листы копии), `application/demo.py` (2 OOO, в т. ч. с половинками; 2 блока, один — с переменным остатком), временные адаптеры там, где читается `Hold` (`allocation.py`, `views.py`, `reservations.save_hold`) — заменить чтением `Ooo`/блоков минимально, полная логика — Task 2–4.
**Test:** `tests/stays/test_ooo_blocks_schema.py`.

**Interfaces:** `Ooo(id, unit_id, start, end, start_half: 'AM'|'PM', end_half, reason, version, created_at, author_id)`; `Block(id, title, start, end, version, created_at, author_id)`; `BlockNight(block_id, category_id, night, quantity)` PK `(block_id, category_id, night)`; `GuestPref(id, guest_id, kind: 'group'|'flag'|'unit', ref_id, priority)`.

- [ ] Тесты: `test_tables_and_constraints` (quantity ≥ 1, PK ночи), `test_migration_up_down_sqlite`, `test_reset_wipes_and_backs_up_new_tables`, `test_overbook_perm_registered`, `test_demo_has_ooo_and_blocks`.
- [ ] RED → реализация → GREEN; коммит `feat(stays): модели OOO, блоков и пожеланий; право stays.overbook`.

### Task 2: Домен распределения — слоты блоков, приоритеты, «без пинг-понга», пожелания, HK

**Files:** `app/modules/stays/domain/blocks.py` (новый), `app/modules/stays/domain/allocate.py`, `tests/stays/test_allocate.py`, `tests/stays/test_blocks_domain.py`.

**Interfaces:**
- `blocks.py`: `@dataclass(frozen=True) SlotRef(block_id: int, category_id: int, slot: int, start_pos: int, end_pos: int, title: str)`; `slots(nights: Mapping[tuple[int, int, date], int]) -> list[SlotRef]` — ключ `(block_id, category_id, night)`; непрерывные ночи слота — один `SlotRef`, режется границами версий как части.
- `allocate.py`: `OooRef(unit_id, start_pos, end_pos, title)` вместо `HoldRef`; `AllocItem.rank: int` (0 — подтверждённая/заселённая, 1 — предварительная); `AllocItem.in_house: bool`; `AllocItem.prefs: Callable[[UnitSpan], int] | None` (счёт выполненных пожеланий); `allocate(spans, ooo, slots, items, category_codes, turnover: Mapping[tuple[int, int], bool]) -> (assignments, slot_assignments: dict[tuple[int, int, int, int], int | None], warnings)`; новые виды предупреждений `overbooked`, `block_short`.
- Правила §4.2–§4.3 спеки; HK: `turnover[(unit_id, day_ordinal)]` — в этот день в объекте выезд.

- [ ] Тесты: `test_slots_from_variable_quantity`, `test_two_blocks_same_category_take_two_units`, `test_slot_keeps_unit_when_free`, `test_slot_moves_when_busy`, `test_block_short_never_shrinks`, `test_block_displaces_confirmed_created_earlier`, `test_block_never_moves_in_house`, `test_tentative_loses_first`, `test_ooo_moves_not_in_house_whole_stay`, `test_ooo_moves_in_house_once_until_end`, `test_no_patchwork_overbooked_instead`, `test_pin_transferred_on_move`, `test_preferences_win_over_hk`, `test_hk_avoids_turnover_when_choice`, `test_hk_allows_turnover_when_no_choice`, `test_ooo_halfday_checkout_then_ooo_same_day`.
- [ ] RED → реализация → GREEN; коммит `feat(stays): распределение — блоки, OOO, приоритеты, без пинг-понга`.

### Task 3: Применение — расчёт, предпросмотр, `stays.overbook`, батлеры при овербукинге

**Files:** `application/allocation.py` (загрузка OOO, ночей блоков, пожеланий главного гостя, оборотов; запись назначений слотов в памяти — без таблицы, только в `AllocationState`), `application/preview.py` (окно ±62 дня для OOO/блоков; проверка нового овербукинга), `application/context.py`/`coverage.py`/`views.py` (бронь без объекта — дыры и нагрузка по категории брони, «Требуют внимания»), `interface/_ops.py` (403/409 по праву).
**Test:** `tests/stays/test_overbooking.py`, `tests/stays/test_allocation_versions.py` (дополнить).

**Interfaces:** `AllocationState.slots: dict[(block_id, category_id, slot, piece_index), unit_id | None]`; `overbooked_keys(state) -> set[tuple[int, int]]` — `(reservation_id, piece_index)`; `run_operation(…, principal)` — если `overbooked_keys(after) - overbooked_keys(before)` не пусто и у `principal` нет `stays.overbook` → `OverbookRefused` (409) с предпросмотром.

- [ ] Тесты: `test_overbook_needs_perm_409`, `test_overbook_with_perm_saves_with_warning`, `test_existing_overbook_does_not_block_other_edits`, `test_overbook_check_by_identity_not_count`, `test_overbooked_booking_has_hole_and_load`, `test_past_ooo_edit_does_not_move_past_pieces`, `test_preview_equals_save_with_blocks_and_ooo`, `test_board_query_budget_with_blocks` (≤ 30).
- [ ] RED → реализация → GREEN; коммит `feat(stays): овербукинг под правом, предпросмотр и батлеры для броней без объекта`.

### Task 4: API OOO и блоков

**Files:** `application/ooo.py`, `application/blocks.py` (новые; `reservations.save_hold` и маршруты `/holds` удаляются), `interface/ooo_api.py`, `interface/blocks_api.py` (+ роутеры в манифесте), `docs/openapi.json`.
**Test:** `tests/stays/test_ooo_api.py`, `tests/stays/test_blocks_api.py`.

**Interfaces:**
- `GET /ooo?first=&last=&group_ids=&category_ids=&q=&sort=&dir=&offset=&limit` → `{total, rows}`; `POST /ooo`, `PUT /ooo/{id}` `{unit_id, start, end, start_half, end_half, reason, version}`, `DELETE /ooo/{id}?version=`; `?preview=1` на всех записях.
- `GET /blocks?first=&last=&category_ids=&short_only=&q=&sort=&dir=&offset=&limit` → `{total, rows: [{id, title, start, end, nights, top: [{code, max}], placed, short}]}`; `GET /blocks/{id}` → `{…, grid: {category_id: {night: quantity}}, short: [{category_id, first, last, missing}]}`; `POST /blocks`, `PUT /blocks/{id}` `{title, start, end, grid, version}` (сетка целиком), `PATCH /blocks/{id}/nights` `{version, category_id, first, last, quantity}` (помощник «заполнить» и быстрая правка; `quantity = 0` — убрать ночи), `DELETE /blocks/{id}?version=`; `?preview=1`.
- Проверки: OOO на объект вне фонда — 422; пересечение OOO одного объекта — 409; категория ночи вне фонда — 422; ночь вне `[start, end)` — 422; версия — 409. Аудит с «было → стало». Прошлое править можно.

- [ ] Тесты: `test_ooo_crud_halves_and_flags`, `test_ooo_absent_unit_422`, `test_ooo_overlap_409`, `test_block_grid_crud`, `test_block_fill_helper_and_quick_edit`, `test_block_narrow_dates_drops_nights`, `test_block_category_absent_422`, `test_version_conflict_409`, `test_past_edits_allowed_and_audited`, `test_long_block_preview_window`, `test_lists_filters_sort`, `test_visible_to_all_levels_with_titles`.
- [ ] RED → реализация → GREEN; коммит `feat(stays): API OOO и блоков`.

### Task 5: Пожелания гостя

**Files:** `application/guests.py` (`save_prefs(db, guest_id, prefs: list[{kind, ref_id, priority}])` под `lock_module`), `interface/guests_api.py` (`GET/PUT /guests/{gid}/prefs`, право `stays.guests`), `application/allocation.py` (счёт пожеланий главного гостя для `AllocItem.prefs`), `application/views.py` (карточка брони: «пожелание выполнено / нет»), `static/js/modules/stays_forms.js` (блок «Предпочитает» в карточке гостя: узел / флаг / объект, порядок), `application/guests.py merge_guests` (перенос пожеланий без дублей).
**Test:** `tests/stays/test_guest_prefs.py`, `tools/stays_scenario.mjs`.

- [ ] Тесты: `test_prefs_crud_and_perm`, `test_pref_satisfied_when_free`, `test_pref_ignored_when_busy`, `test_pref_flag_by_version_day`, `test_pref_unit_follows_lineage`, `test_card_shows_pref_status`, `test_merge_moves_prefs_without_duplicates`; сценарий: добавить «Первая линия» гостю → бронь встаёт на первую линию.
- [ ] RED → реализация → GREEN; коммит `feat(stays): пожелания гостя в распределении`.

### Task 6: Отображение — шахматка, «Загрузка», табло дня

**Files:** `application/views.py` (полосы OOO по половинкам с причиной; полосы слотов блока — склейка соседних ночей одного слота в одном объекте; «Не распределено» — `overbooked` красным; `occupancy_grid`: OOO и блоки по половинкам PM, «Блоки» — сумма остатков, «Свободно» без нижней границы), `application/boards.py` (табло дня: OOO начинается/заканчивается сегодня, овербукинг — в «Требуют внимания»), `static/js/modules/stays.js`, `stays_board.js` (отрисовка, клик по блоку — карточка блока, полосы блока не перетаскиваются, отрицательное «Свободно» красным).
**Test:** `tests/stays/test_units_board.py`, `tests/stays/test_occupancy_and_mine.py`, `tests/stays/test_day_board.py`, `tools/stays_scenario.mjs`.

- [ ] Тесты: `test_ooo_bar_halves`, `test_block_slot_bars_merged`, `test_overbooked_in_unassigned`, `test_occupancy_blocks_sum_remainder`, `test_occupancy_free_negative`, `test_day_board_ooo_and_overbook_attention`, бюджет SQL ≤ 30; сценарий: полосы, клик по блоку, «Загрузка» с «−1».
- [ ] RED → реализация → GREEN; коммит `feat(stays): OOO, блоки и овербукинг на шахматке, в «Загрузке» и на табло`.

### Task 7: Вкладки «Блоки» и «OOO»

**Files:** `static/js/modules/stays_blocks.js`, `static/js/modules/stays_ooo.js` (новые), `static/js/modules/stays.js` (`STAYS_TABS` += `['blocks', 'Блоки']`, `['ooo', 'OOO']`), `static/css/app.css`, `static/index.html`, `static/sw.js`, `tools/js_globals.json`.
**Test:** `tools/stays_scenario.mjs`.

**Interfaces:** `renderBlocksTab(body)`, `openBlockCard(id | null, onChanged)` — сетка «категория × ночь» (строки — категории, столбцы — ночи месяца с прокруткой), помощник «заполнить», выделение ночей и «задать число», предпросмотр перед сохранением («кто без объекта», «нехватка»), 409 по `stays.overbook` — текст сервера; `renderOooTab(body)`, `openOooForm(id | null, onChanged)` — объект, с–по, «с утра» / «до вечера», причина, предпросмотр. Список — фильтры и сортировка по образцу «Брони»; всё экранируется `esc`; `loadGenerationFor`.

- [ ] Сценарий: новый блок помощником → полосы на шахматке; быстрая правка ночей; блок с нехваткой — в списке «с нехваткой»; новый OOO с половинками → гость переезжает (предпросмотр); без `stays.overbook` — тост с текстом 409; список OOO фильтр по узлу.
- [ ] RED → реализация → GREEN; коммит `feat(stays): вкладки «Блоки» и «OOO»`; push, PR.
