# Шахматка, часть 3: сопровождение по правилам, VIP-коды, «Особый гость» — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** «Нужен ли батлер» — по четырём правилам (категория, узел дерева, VIP-код, «Особый гость»
в группе) с ручной отметкой поверх; нагрузка — вес места × наибольший коэффициент кода ×
коэффициент «Особого гостя»; справочник VIP-кодов, флаг «◆ Особый гость» вместо VIP/VVIP.

**Architecture:** Чистая функция `domain/escort.py` (`escort_need`, `place_weight`) получает уже
разобранные признаки; `StayDay` несёт `EscortNeed` вместо `escorted/declined`, и всё, что сейчас
смотрит на `escorted and not declined` (дыры, статус табло, нагрузка, подбор), переходит на неё.
Узел дерева получает версионируемое `escorted` в `stays_group_states`. Старые поля (`level`,
`declined_butler`, надбавки VIP/VVIP) живут до последней задачи и удаляются отдельной миграцией —
так каждая задача оставляет приложение рабочим. Один PR (боевой базы нет).

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Alembic, pydantic v2, openpyxl, vanilla JS, jsdom-сценарии, pytest.

**Spec:** `docs/superpowers/specs/2026-10-27-stays-escort-rules-design.md` (ред. 3).

## Global Constraints

* Батлер нужен, если **любое**: категория объекта (версия дня) escorted; любой узел на пути
  объекта (версия дня) escorted; VIP-код брони escorted (архивный — тоже); в ночь D в брони **или
  в любой брони её группы** проживает «Особый гость» (§2, §4.1).
* `escort_mode`: `rules` (по умолчанию) | `required` | `declined`; `declined` главнее всех правил,
  `required` — нужен всегда (§2).
* Вес считается **по месту** (одна вилла — один вес; бронь без объекта — своё место):
  `категория × max(коэффициент кода по броням места; 1) × (Особый в месте ? special_factor : 1)`;
  «Особый» умножает один раз и только своё место; вес места делится поровну между батлерами;
  отдельных надбавок батлеру гостя нет (§4.2).
* Код — строка цифр, ведущий ноль значим («03» ≠ «3»), `^\d{1,8}$`; `factor ≥ 0.1`, по умолчанию
  1.0; `special_factor` по умолчанию 2.0 (§3).
* Код в брони копируется из профиля главного гостя при создании и смене главного — поверх прежнего
  значения брони; ручной выбор в том же сохранении побеждает (см. Task 4) (§3.1, §9 п. 14).
* Смена кода в профиле — галочка «обновить в бронях: N» (по умолчанию включена): текущие и будущие
  брони (`check_out > сегодня`), где гость главный; прошлые не меняются; одна операция с
  предпросмотром (§3.1).
* Архивный код: действует в бронях и профилях, где уже стоит; для новых не выбирается (422); в
  списках — «в архиве» (§3, §9 п. 13). Использованный код удалить нельзя — 409.
* Права: коды и коэффициенты — `stays.setup`; код и `escort_mode` брони, «Особый гость» и код
  профиля — `stays.edit`; батлер (`stays.edit_mine`) их не меняет (§7).
* Код и ◆ — уровень «с фамилиями» и выше; уровню occupancy — нет (§7).
* Подписи причин: `категория {title}`, `узел {title}`, `код {code} — {title}`, `◆ Особый гость {short_name}`,
  `отмечено вручную`, `гость отказался`; вес показывается с одним знаком («5,5»).
* Каждая задача: `pytest -q`, `ruff check .`, `lint-imports`, `npx eslint static/js`,
  `python tools/check_api_contract.py`, `python tools/export_openapi.py` (перегенерировать
  `openapi.json` при смене API), `python tools/bump_version.py <версия>` при смене статики (без
  префикса `tt-`, строго больше последней), `python tools/gen_js_globals.py --check`, сценарии
  шахматки (`tools/run_stays_scenario.sh` — admin, ivanov, sluzhba, rukovod), фонда, `tools/run_ui_check.sh`.
* Коммиты — по-русски, с трейлером `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`;
  добавлять файлы по путям (никогда `git add -A`); не коммитить `docs/audit/` и `.superpowers/`;
  без push; серверы после проверок не оставлять.
* Бюджет SQL шахматки на 440 объектов × 31 день и табло дня — не выше нынешних (30 и 32).
* Задача, которая меняет поле API, правит и существующие тесты и помощники, которые его шлют
  (`declined_butler` — Task 4; `level` и `tests/stays/helpers.make_guest` — Task 5), и jsdom-сценарии
  — каждая задача заканчивается зелёным полным набором.

## Review Focus

1. **Существующая бронь с архивным кодом открыта в форме и сохранена без правок** — код остаётся
   (селект показывает архивный код текущей брони), а не сбрасывается в «нет» и не даёт 422; тест в
   Task 4 (`test_archived_code_survives_resave`) и проверка в сценарии Task 6.
2. **«Особый гость» живёт в группе только часть срока (заезжает на 2 ночи из 5)** — сопровождение
   другим виллам группы нужно только в эти 2 ночи, в остальные — по их собственным правилам; тест в
   Task 3 (`test_special_in_group_only_on_his_nights`).
3. **Коэффициенты дают дробный вес (1,5 × 3 = 4,5; 1,1 × 3 = 3,3000000000000003)** —
   сравнение с лимитом и предпросмотр без «шума» плавающей точки, показ «3,3»; тест в Task 3
   (`test_place_weight_rounded`).
4. **Код «03» и «3», пробелы, буквы** — «03» и «3» — разные коды; « 03 » нормализуется в «03»;
   «A3» — 422; тест в Task 1 (`test_code_text_rules`).
5. **Главный гость брони сменяется посреди проживания (две строки main)** — «главный» для
   копирования кода — главный на ночь заезда; смена главного только на поздние ночи код не трогает;
   тест в Task 4 (`test_main_guest_is_first_night_main`).

---

## Ветка `feat/stays-escort-rules`, один PR

### Task 1: Модели, миграция 0017, справочник VIP-кодов, коэффициент «Особого гостя»

**Files:** `app/modules/stays/adapters/orm.py` (`VipCode`; новые поля `Guest.vip_code_id`, `Guest.special`, `Reservation.vip_code_id`, `Reservation.escort_mode`, `StaysSettings.special_factor`, `GroupState.escorted`), `app/bootstrap/alembic/versions/0017_stays_escort_rules.py`, `app/modules/stays/application/vip_codes.py` (новый), `app/modules/stays/interface/fund_api.py` (эндпоинты кодов, `special_factor` в `SettingsIn`/`GET /fund`), `app/modules/stays/application/fund.py` (`save_settings`), `application/fund_reset.py` (WIPE и копия нового справочника), `application/demo.py` (коды 03, 13, 14), `manifest.py` (метка аудита `stays_vip_code`).
**Test:** `tests/stays/test_vip_codes.py`, `tests/stays/test_schema.py` (дополнить).

**Interfaces:**
- `VipCode(id, code: String(8) UNIQUE, title: String(80), escorted: bool=False, factor: Numeric(4,2)=1.0, sort_order: int=100, archived: bool=False)`, таблица `stays_vip_codes`.
- `Guest.vip_code_id: FK NULL`, `Guest.special: bool=False`; `Reservation.vip_code_id: FK NULL`, `Reservation.escort_mode: String(8)='rules'`; `StaysSettings.special_factor: Numeric(4,2)=2.0`; `GroupState.escorted: bool=False`.
- Миграция 0017 только **добавляет** (старые колонки удаляет Task 7) и переносит: `escort_mode = 'declined'` где `declined_butler`, `special = true` где `level in ('vip','vvip')`.
- `vip_codes.py`: `normalize_code(raw: str) -> str` (strip; `^\d{1,8}$`, иначе `FundError`); `save_code(db, data: dict, code_id: int | None) -> int`; `archive_code(db, code_id: int, archived: bool) -> None`; `delete_code(db, code_id: int) -> None` (использован в госте или брони → `FundConflict`); `code_dict(c: VipCode) -> dict` (`id, code, title, escorted, factor, sort_order, archived`); `all_codes(db) -> list[VipCode]` (порядок `sort_order, code`); `check_selectable(db, code_id: int | None, current: int | None) -> None` — архивный код можно оставить (`code_id == current`), выбрать заново нельзя (`FundError`).
- API (`stays.setup`, аудит): `POST /api/stays/vip-codes`, `PUT /api/stays/vip-codes/{id}`, `PUT /api/stays/vip-codes/{id}/archive` (`{archived}`), `DELETE /api/stays/vip-codes/{id}`; `GET /api/stays/fund` отдаёт `vip_codes` (все, с архивными) и `settings.special_factor`; `PUT /api/stays/settings` принимает `special_factor` (`≥ 0.1`, `≤ 99`), прежние надбавки пока остаются в теле.

- [ ] Тесты: `test_code_text_rules` («03» ≠ «3», « 03 » → «03», «A3» и «123456789» — 422), `test_code_unique_409`, `test_factor_min_0_1`, `test_archive_used_code_ok_delete_409`, `test_codes_need_setup_perm` (403 у `stays.edit`), `test_special_factor_default_and_save`, `test_migration_copies_declined_and_level` (0016 → 0017 на SQLite с данными), `test_reset_backs_up_vip_codes`, `test_demo_has_codes_03_13_14`.
- [ ] RED → реализация → GREEN; `python tools/export_openapi.py`; коммит `feat(stays): справочник VIP-кодов, особый гость и режим сопровождения в модели`.

### Task 2: Узел дерева с сопровождением — фонд, черновик, файл

**Files:** `application/fund_versions.py` (`GroupInfo.escorted`, `_group_paths`, `FundSnapshot.unit_escorted`), `application/fund_drafts.py` (`_copy_states`, `_STATE["group"]`, `_plain`, `save_group`, `seed_initial`, перенос в поздние версии), `interface/fund_versions_api.py` (`escorted` в теле узла и в `_snapshot_dict`), `application/fund_xlsx.py` (колонка «Сопровождение» листа «Дерево»: выгрузка, разбор), `application/fund_reset.py` (`plan_load`), `static/js/modules/stays_fund.js` (галочка в карточке узла, отметка в дереве, подпись поля в разнице).
**Test:** `tests/stays/test_fund_drafts.py`, `tests/stays/test_fund_xlsx.py` (дополнить), `tools/stays_fund_scenario.mjs` (дополнить).

**Interfaces:**
- `GroupInfo.escorted: bool`; `FundSnapshot.unit_escorted(unit_id: int | None) -> bool` — категория объекта escorted или любой узел на `unit_path` escorted (правила 1–2; для фильтров объектов).
- Тело узла черновика — `{title, parent_id, sort_order, escorted}`; разница версий показывает `escorted`.
- Лист «Дерево»: `ID | Название | Родитель | Сопровождение | Порядок` («да»/«нет» как у категорий через `_yn`); колонки нет (старый файл) — все узлы «нет», без ошибки; неизвестное значение — ошибка файла с листом и строкой.

- [ ] Тесты: `test_group_escorted_versioned` (с даты — да, до — нет), `test_branch_inherits_escorted` (`unit_escorted` для объекта во внуке), `test_group_escorted_in_diff`, `test_carry_to_later_versions_keeps_escorted`, `test_xlsx_tree_escorted_roundtrip_empty_draft`, `test_xlsx_tree_without_escorted_column`, `test_xlsx_tree_bad_escorted_value_row`.
- [ ] jsdom (сценарий фонда): галочка «С сопровождением» в карточке узла сохраняется в черновик и видна в разнице.
- [ ] RED → реализация → GREEN; коммит `feat(stays): сопровождение у узла дерева фонда`.

### Task 3: Домен сопровождения и нагрузки; контекст покрытия

**Files:** `app/modules/stays/domain/escort.py` (новый), `domain/types.py` (`StayDay`), `domain/load.py`, `domain/warnings.py`, `application/context.py`, `application/coverage.py` (`rank_in_ctx`), `application/boards.py` (`_status`), `tests/stays/test_escort_domain.py` (новый), `tests/stays/test_coverage_domain.py` (помощник `stay()`), `tests/stays/test_day_board.py`, `tests/stays/test_coverage_api.py`.

**Interfaces:**
- `escort.py`:
  - `@dataclass(frozen=True) EscortNeed(required: bool, reasons: tuple[str, ...], declined: bool = False)` — `declined=True`, когда правила требуют, а гость отказался.
  - `escort_need(mode: str, *, category: tuple[str, bool], nodes: Sequence[tuple[str, bool]], code: tuple[str, str, bool] | None, specials: Sequence[str]) -> EscortNeed` — `category=(title, escorted)`, `nodes` — путь от корня, `code=(code, title, escorted)`, `specials` — короткие имена «Особых» брони и её группы в эту ночь. Порядок причин: категория, узлы (по пути), код, особые. `required` → `(True, ("отмечено вручную",))`; `declined` → `(False, ("гость отказался",), declined=bool(причины правил))`.
  - `place_weight(category_weight: float, code_factors: Iterable[float], special: bool, special_factor: float) -> float` — `round(..., 2)`; пустые коэффициенты → 1.
- `StayDay`: поля `escorted`, `declined`, `guests: Mapping[int, str]` заменяются на `need: EscortNeed`, `code_factor: float | None` (коэффициент кода брони, `None` — кода нет), `guests: Mapping[int, bool]` (гость → «Особый»). Остальные поля и порядок — как были.
- `day_loads(stays, cover, special_factor: float) -> dict[int, float]` — место = объект (или бронь без объекта); вес места — `place_weight(вес категории, коэффициенты броней места, есть ли «Особый» среди гостей места, special_factor)`; делится поровну между батлерами места.
- `day_warnings`: дыра — если `s.need.required`.
- `StaysContext`: `vip_bonus/vvip_bonus` → `special_factor: float`; новое поле `vip_codes: dict[int, VipCode]` (все коды одним запросом, с архивными; имя `codes` уже занято кодами дня Табеля). `_stays_on(day)` — два прохода: сначала «Особые» по броням, затем объединение по `group_id`, затем `escort_need(...)`. Бюджет SQL табло дня — не выше 32 (запрос кодов вместо чтения надбавок не добавляет, настройки уже читаются).
- `rank_in_ctx`: вес назначения — `place_weight(stays[0].weight, [s.code_factor ...], any(s.guests[g] for выбранных g), ctx.special_factor)`.
- `boards._status`: `declined` → `"declined"`; не нужен → `"not_required"`; во всех статусах — `"escort_reasons": list(need.reasons)`.

- [ ] Тесты домена: `test_each_rule_alone` (4 правила по отдельности), `test_rules_are_or`, `test_node_escorted_category_not_needs`, `test_required_overrides`, `test_declined_overrides_special_and_code`, `test_declined_without_rules_not_flagged`, `test_reasons_text_and_order`, `test_place_weight_product` (2 × 2 × 1,5 = 6), `test_place_weight_max_code_one_place` (две брони, коды ×2 и нет → 4), `test_special_once` (два «Особых» при 2.0 → ×2), `test_place_weight_rounded` (1,1 × 3 → 3.3), `test_load_split_evenly_two_butlers`.
- [ ] Тесты применения: `test_special_in_group_needs_other_villas` (вилла Б группы без правил — дыра в ночь «Особого» в вилле А), `test_special_in_group_only_on_his_nights`, `test_special_weight_only_own_villa`, `test_archived_code_still_acts`, `test_unallocated_ignores_node_rule_then_applies` (без объекта — нет правила узла; после распределения — есть), `test_node_from_date_version_of_day`, `test_day_board_status_reasons`, `test_day_board_query_budget` (≤ 32).
- [ ] RED → реализация → GREEN; коммит `feat(stays): сопровождение по правилам и вес места с коэффициентами`.

### Task 4: Бронь — код, режим сопровождения, фильтры, карточка

**Files:** `interface/reservations_api.py` (`ReservationIn`), `application/reservations.py` (`SCALARS`, копирование кода, `reservation_dict`), `application/views.py` (карточка, полосы, `BoardFilters`, `_passing`), `application/bookings.py` (фильтры), `application/boards.py` (`DayFilters`), `interface/views_api.py` / `bookings_api.py` / `boards_api.py` (параметры), `application/visibility.py` (поля полосы), `application/mine.py` (`LOCKED`), `application/export.py` (колонки), `static/js/modules/stays_forms.js` (форма брони), `static/js/modules/stays.js` (карточка).
**Test:** `tests/stays/test_reservations_api.py`, `tests/stays/test_board_filters.py`, `tests/stays/test_bookings_list.py`, `tests/stays/test_occupancy_and_mine.py`, `tests/stays/test_pd_leaks.py` (дополнить).

**Interfaces:**
- `ReservationIn`: `declined_butler` → `escort_mode: Literal["rules","required","declined"] = "rules"`, `vip_code_id: Optional[int] = None`. `SCALARS` — `escort_mode`, `vip_code_id` вместо `declined_butler`.
- Правило кода в `save_reservation` (главный — гость с `role == "main"` на ночь заезда):
  ```
  prev = r.vip_code_id (новая бронь — None); payload = doc["vip_code_id"]
  если payload != prev: code = payload            # ручной выбор в этом сохранении
  иначе если главный сменился (или бронь новая): code = профиль главного.vip_code_id
  иначе: code = prev
  check_selectable(db, code, prev)
  ```
  Смена кода видна в предпросмотре (снимок брони несёт `vip_code_id`).
- `reservation_dict` и карточка: `vip_code: {id, code, title, archived} | None`, `escort_mode`, `escort: {required_nights: int, declined: bool, reasons: [str]}` (объединение причин по ночам брони, из `StaysContext`); в форме — подсказка «по правилам: нужен — причины / не нужен».
- Фильтры (`BoardFilters`, `DayFilters`, API): `vip: bool` → `special: bool` и `vip_code_ids: tuple[int, ...]`; параметр `vip` — 422 (добавить в `REMOVED_PARAMS`). «С сопровождением»: шахматка объектов и «Загрузка» — `snap.unit_escorted(uid)`; «Брони» — `EscortNeed.required` хотя бы в одну ночь брони в окне запроса (через `load_context` на окно, пересечённое со сроками найденных броней); табло дня — как сейчас, по статусу.
- Полоса (`NAMES_BAR`): `level` → `special: bool`, `vip_code: str` (текст кода); `FULL_BAR`: `declined_butler` → `escort_mode`. Выгрузка «Брони»: «Уровень» → «◆» и «VIP-код»; «Сопровождение» — по правилам / требуется / отказался.
- `mine.LOCKED`: `escort_mode`, `vip_code_id` вместо `declined_butler`.

- [ ] Тесты: `test_code_copied_from_main_on_create`, `test_code_recopied_on_main_change_over_manual` (бронь с ручным «13», главный сменён на гостя с «03» → «03», в предпросмотре «13 → 03»), `test_manual_code_in_same_save_wins`, `test_main_guest_is_first_night_main`, `test_archived_code_survives_resave`, `test_archived_code_not_selectable_new_422`, `test_escort_mode_values_and_422`, `test_card_escort_reasons`, `test_filter_special_and_codes`, `test_vip_param_422`, `test_bookings_escorted_by_rules` (узел с сопровождением при категории без — бронь в фильтре), `test_units_escorted_filter_by_node`, `test_butler_cannot_change_code_or_mode` (403), `test_occupancy_level_no_code_no_special` (`assert_no_pd`).
- [ ] jsdom: форма брони — «VIP-код» подставляется при выборе главного гостя, «Сопровождение: по правилам / требуется / не требуется (гость отказался)» сохраняется, архивный код текущей брони виден в списке с пометкой «в архиве».
- [ ] RED → реализация → GREEN; `python tools/export_openapi.py`; коммит `feat(stays): VIP-код и режим сопровождения брони, фильтры по правилам`.

### Task 5: Профиль гостя — «Особый гость», VIP-код, обновление броней

**Files:** `interface/guests_api.py` (`GuestIn`, `PUT /guests/{id}` через `_ops.run`, список), `application/guests.py` (`PROFILE_FIELDS`, `save_guest`, слияние), `application/guests_list.py` (фильтр, сортировка), `application/family.py`, `static/js/modules/stays_forms.js` (профиль, быстрый новый гость), `static/js/modules/stays_guests.js` (вкладка «Гости»), `tests/stays/helpers.py` (`make_guest(client, last=None, special=False, vip_code_id=None)`).
**Test:** `tests/stays/test_guests_api.py`, `tests/stays/test_guests_list.py` (дополнить).

**Interfaces:**
- `GuestIn`: `level` → `special: bool = False`, `vip_code_id: Optional[int] = None`; `PUT /api/stays/guests/{id}?preview=` с телом `GuestIn` + `update_reservations: bool = True`. Код сменился и `update_reservations` → в той же операции `Reservation.vip_code_id` = новый код у броней, где гость — главный на ночь заезда и `check_out > local_date()`; окно предпросмотра — от сегодня до самого позднего выезда этих броней. Ответ — `{guest, updated_reservations: int, diff?}`.
- Карточка гостя: `main_current: int` — число таких броней (подпись «обновить в бронях: N»).
- `check_selectable` для кода профиля (архивный можно оставить, выбрать — нет).
- Слияние: `special = keep.special or drop.special`; `vip_code_id` — заполняется из дубля, если пуст.
- Список: фильтр `level` → `special: bool`, `vip_code_id: Optional[int]`; сортировка `level` → `special` («Особые» первыми, затем по коду); строка — `special`, `vip_code`.
- `GET /api/stays/guests` (подбор) и семейное дерево: `special`, `vip_code` вместо `level`.

- [ ] Тесты: `test_profile_code_updates_current_and_future_only` (прошлая бронь не меняется), `test_profile_code_update_off_leaves_reservations`, `test_profile_code_update_preview_equals_save`, `test_profile_code_update_only_where_main`, `test_main_current_count`, `test_special_and_code_need_edit_perm`, `test_butler_cannot_change_special_or_code` (через `check_guest_change`), `test_merge_special_and_code`, `test_guests_filter_special_and_code`, `test_guests_sort_special`.
- [ ] jsdom: профиль — галочка «◆ Особый гость», выбор кода; при смене кода — галочка «обновить в бронях: N» и предпросмотр; вкладка «Гости» — фильтр «◆ Особые» и колонка кода.
- [ ] RED → реализация → GREEN; `python tools/export_openapi.py`; коммит `feat(stays): особый гость и VIP-код в профиле, обновление броней`.

### Task 6: Экраны — «Настройки → Сопровождение», значки ◆ и код, фильтры, табло

**Files:** `static/js/modules/stays_settings.js` (справочник кодов, коэффициент «Особого гостя», сводка правил на дату), `static/js/modules/stays.js` (`STAYS_LEVEL_MARK` → значок ◆ и код; полосы, карточка; фильтры `special`, `vip_code_ids`, перенос сохранённого `vip: true` в `special: true`), `static/js/modules/stays_filters.js`, `static/js/modules/stays_board.js` (табло: причины, ◆, итоги), `static/js/modules/stays_bookings.js`, `application/boards.py` (итоги: `special` вместо `vip`/`vvip`), `tools/stays_scenario.mjs`.
**Test:** `tools/stays_scenario.mjs` (новый раздел), `tests/stays/test_day_board.py` (итоги).

**Interfaces:**
- «Настройки → Сопровождение»: список «сопровождают гостей» (как есть); таблица кодов (код, что значит, «сопровождение», коэффициент, порядок, архив, удалить); поле «Коэффициент „Особого гостя“»; надбавки VIP/VVIP убираются с экрана; подсказка «после смены коэффициентов подберите лимит нагрузки заново»; сводка «на дату» — категории и узлы с сопровождением из `GET /api/stays/fund/snapshot?date=` со ссылкой на «Фонд».
- Табло дня: у брони — причины сопровождения (`escort_reasons`), «сопровождение: отказался»; итоги — `special: int` вместо `vip`/`vvip`; ◆ у имени особого гостя, код рядом с главным гостем.
- Вес в подписях нагрузки — с одним знаком через запятую.

- [ ] Тест: `test_day_board_totals_special`.
- [ ] jsdom: заведение кода «13» с сопровождением → бронь без сопровождения по категории получает статус «не назначено» на табло с причиной «код 13 — …»; архив кода; удаление использованного — сообщение 409; ◆ на полосе и в «Бронях»; фильтр «◆ Особый гость»; уровень occupancy (сценарий sluzhba) — нет ◆ и кода.
- [ ] RED → реализация → GREEN; `python tools/bump_version.py <версия>`; коммит `feat(stays): экран сопровождения, значок особого гостя и VIP-код на экранах`.

### Task 7: Уборка — миграция 0018, удаление старых полей, финальная проверка

**Files:** `app/bootstrap/alembic/versions/0018_stays_drop_levels.py`, `adapters/orm.py` (удалить `Guest.level`, `Reservation.declined_butler`, `StaysSettings.vip_bonus/vvip_bonus`), `application/fund.py` (`SETTINGS_FIELDS`, `save_settings(db, special_factor, daily_limit, replacement_codes)`), `interface/fund_api.py` (`SettingsIn` без надбавок), `application/demo.py` (особые гости вместо VIP/VVIP; брони с кодами), `application/fund_reset.py`, все оставшиеся ссылки на `level`/`declined_butler`/`vip_bonus` в `app/modules/stays` и `static/js`.
**Test:** весь набор + `tests/stays/test_schema.py` (`test_old_columns_gone`), `tests/test_db_upgrade.py`.

- [ ] `grep -rnE "declined_butler|vvip|vip_bonus|\.level\b|\"level\"" app/modules/stays static/js/modules/stays*.js` — пусто (кроме уровней видимости `Level`/`level_for`).
- [ ] Тесты: `test_old_columns_gone`, `test_migration_0018_up_down`, `test_demo_has_special_and_codes`.
- [ ] Полный прогон Global Constraints; `python tools/export_openapi.py`; `python tools/bump_version.py <версия>`; коммит `refactor(stays): убраны уровни VIP/VVIP, отказ от батлера и надбавки`.
