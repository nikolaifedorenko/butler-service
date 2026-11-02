# Шахматка, часть 4: батлер — «свои гости», права, «Мои гости» — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** батлер видит всех своих гостей за всё время, шахматку и табло — на уровне «с фамилиями»
без правки, правит профили своих гостей (включая семейное дерево и пожелания к объекту) и их брони
по двум отдельным правам; экран «Мои гости» — «Сегодня», «Мой месяц», «Все мои гости».

**Architecture:** «Свой» перестаёт зависеть от окна «вчера…+7»: `application/mine.py` считает
множества своих гостей и броней прямыми запросами по строкам покрытия за всё время (плюс гости,
заведённые батлером — новая колонка `stays_guests.created_by_employee_id`). Все проверки
принадлежности (бронь, гость, связь, пожелания) идут через эти множества. Право `stays.edit_mine`
делится на `stays.mine_guest_edit` и `stays.mine_res_edit` миграцией грантов; `stays.view`
получают все. Экран «Мои гости» читает три новых эндпоинта. Один PR (боевой базы нет).

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Alembic, vanilla JS, jsdom-сценарии, pytest.

**Spec:** `docs/superpowers/specs/2026-10-27-stays-butler-mine-design.md` (ред. 3).

## Global Constraints

* «Свой гость» — у батлера есть хоть одна строка покрытия на него (по гостям, или «вся бронь /
  группа», где явный список гостей другого батлера сильнее) — за всё время, включая подмену; плюс
  гость, которого батлер завёл сам через семейное дерево. «Своя бронь» — бронь со строкой батлера
  (своей или группы) за всё время. Предварительные — тоже свои (§2, §4).
* Права: `stays.mine` — экран и чтение своих; `stays.mine_guest_edit` — профиль своих (предпочтения,
  пожелания к объекту, особые даты, семейное дерево и связи, поля, примечание);
  `stays.mine_res_edit` — бронь своих (состав кроме главного, логистика, сопровождающие, примечание,
  поля); `stays.view` — все роли по умолчанию. Все три новых/изменённых — по умолчанию EVERYONE (§3).
* Запертые поля брони — `mine.LOCKED` как сейчас (с `vip_code_id`, `escort_mode`); в профиле батлер
  не меняет «◆ Особый гость» и VIP-код; запертое — 403 (§3).
* Новый проживающий от батлера — родственник проживающего по семейному дереву (в том числе
  вычисленный, `domain/kinship.py`) или прямая связь любого вида; иначе 403 (§3).
* Правка брони выехавшего — без срока (§3, §8 п. 9).
* Пожелания к объекту от батлера — через общий предпросмотр (`interface/_ops.run`); новый
  овербукинг без `stays.overbook` — 409 (§3).
* Батлер на шахматке и табло — уровень «с фамилиями», ни одной записи (403 на всё, кроме своих
  правок выше); табло целиком, включая подбор кандидатов и замены, без кнопок (§6).
* Открытие профиля аудит не пишет; изменения — пишут, как сейчас (§3).
* Бюджет запросов «Мои гости» (все три вкладки) не зависит от длины истории (§7).
* Каждая задача: `pytest -q`, `ruff check .`, `lint-imports`, `npx eslint static/js`,
  `python tools/check_api_contract.py`, `python tools/export_openapi.py` (перегенерировать при смене
  API), `python tools/bump_version.py <версия>` при смене статики (без `tt-`, строго больше),
  `python tools/gen_js_globals.py --check`, сценарии шахматки (admin, ivanov, sluzhba, rukovod),
  `tools/run_ui_check.sh`.
* Коммиты — по-русски, трейлер `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; добавлять
  по путям; не коммитить `docs/audit/` и `.superpowers/`; без push; серверы не оставлять.

## Review Focus

1. **Батлер вёл гостя год назад на подмене и больше не назначен** — гость свой: профиль, история,
   правка брони (выехавшей) разрешены; тест в Task 1 (`test_substitute_year_ago_still_own`).
2. **Строка батлера «вся бронь», а на гостя Б — явная строка другого батлера** — гость Б не свой
   (профиль 403), гость А той же брони — свой; тест в Task 1 (`test_explicit_other_butler_wins`).
3. **Батлер добавляет в состав бабушку жены главного гостя (связи только через дерево, прямой
   нет)** — разрешено; гость без связи — 403; тест в Task 3 (`test_mine_adds_computed_relative`).
4. **Батлер удаляет связь между своим гостем и чужим** — разрешено (связь его гостя); связь между
   двумя чужими — 403; тест в Task 3 (`test_mine_link_delete_ownership`).
5. **У батлера 3 года истории (500 броней)** — «Мои гости» и «Все мои гости» укладываются в тот же
   бюджет запросов, что и при 5 бронях; тест в Task 4 (`test_mine_budget_independent_of_history`).

---

## Ветка `feat/stays-butler-mine`, один PR

### Task 1: Права и «свои» за всё время

**Files:** `app/modules/stays/manifest.py` (права), `app/bootstrap/alembic/versions/0019_stays_butler_mine.py`, `app/modules/stays/adapters/orm.py` (`Guest.created_by_employee_id`), `app/modules/stays/application/mine.py`, `interface/reservations_api.py`, `interface/guests_api.py`, `interface/fund_api.py` (`READ`), `interface/boards_api.py`.
**Test:** `tests/stays/test_mine_ownership.py` (новый), `tests/stays/test_occupancy_and_mine.py`, `tests/stays/test_manifest.py` (дополнить).

**Interfaces:**
- Права в манифесте: `Perm("stays.mine_guest_edit", …, "Правка профилей своих гостей: предпочтения, пожелания, особые даты, семья, поля", EVERYONE)`, `Perm("stays.mine_res_edit", …, "Правка броней своих гостей: состав, логистика, сопровождающие, примечание", EVERYONE)`; `stays.edit_mine` удаляется; `stays.view` → `EVERYONE`.
- Миграция 0019: `stays_guests.created_by_employee_id INTEGER NULL` (FK на сотрудников, как в других таблицах модуля); для каждой строки `access_grants` с `permission='stays.edit_mine'` — две такие же строки с `stays.mine_guest_edit` и `stays.mine_res_edit` (тот же group_id/user_id/role/effect), исходная удаляется; downgrade — обратно (одна строка `stays.edit_mine` на пару, колонка удаляется).
- `mine.py`: `my_reservation_ids(db, employee_id: int) -> set[int]`; `my_guest_ids(db, employee_id: int) -> set[int]` — без `load_context`, по строкам покрытия за всё время (правило «явный список другого батлера сильнее строки „вся бронь/группа“» — на уровне ночи, как в `domain/coverage.resolve_day`, но запросами по `CoverageLine`/`CoverageGuest`/`Occupant`), плюс `Guest.created_by_employee_id == employee_id`; `owns_reservation(db, employee_id, rid) -> bool`; `owns_guest(db, employee_id, gid) -> bool`. Удалить `window`, `owned_reservations`, `_my_lines` (их потребители переходят на новые функции; `my_guests` переписывает Task 4 — до тех пор оставить его работающим на новых множествах).
- Эндпоинты: правка брони батлером — `require_perm("stays.edit", "stays.mine_res_edit")`; профиль (`GET /guests/{gid}` и `GET /guests/{gid}/card`) — чтение `require_perm("stays.guests", "stays.mine")`, правка `require_perm("stays.edit", "stays.mine_guest_edit")`; `fund_api.READ` — `stays.mine` вместо `stays.edit_mine`. Принадлежность — на каждом запросе.

- [ ] Тесты: `test_coverage_line_year_ago_own`, `test_future_line_own`, `test_no_lines_403`, `test_substitute_year_ago_still_own`, `test_tentative_reservation_own`, `test_explicit_other_butler_wins`, `test_group_line_owns_member_guests`, `test_created_by_butler_own`, `test_grants_split_migration` (грант allow и deny на `stays.edit_mine` → по два гранта; откат), `test_view_default_everyone`, `test_checked_out_reservation_edit_allowed_fields`, `test_profile_read_no_audit_edit_audited`.
- [ ] RED → реализация → GREEN; `python tools/export_openapi.py`; коммит `feat(stays): права батлера на профиль и бронь, «свои» за всё время`.

### Task 2: Батлер на шахматке и табло — чтение без записи

**Files:** `interface/coverage_api.py` (чтение кандидатов и замен), `application/views.py` (признак своей брони на полосе; карточка своей брони — полный уровень), `interface/views_api.py`, `application/visibility.py`, `static/js/modules/stays.js` (рамка своей полосы, кнопки только по правам), `static/js/modules/stays_board.js` (табло без кнопок назначения без `stays.assign`), `tools/stays_scenario.mjs` (сценарий ivanov).
**Test:** `tests/stays/test_butler_board_access.py` (новый), `tests/stays/test_pd_leaks.py` (дополнить).

**Interfaces:**
- `GET /api/stays/candidates` и `GET /api/stays/replacements` — `require_perm("stays.assign", "stays.view")` (только чтение); все записи покрытия — по-прежнему `stays.assign`.
- Полоса брони: `mine: bool` — бронь своя для текущего батлера (только когда у принципала есть `stays.mine` и сотрудник; одно множество `my_reservation_ids` на запрос, без N+1).
- `GET /api/stays/reservations/{id}/card`: своя бронь батлера — уровень `full` (телефоны и ДР гостей этой брони), чужая — уровень принципала (`names`).
- JS: кнопки создания брони, назначения, OOO, блоков, подмены — только при соответствующем праве из `principal.permissions`; своя полоса — класс `sb-mine` (рамка).

- [ ] Тесты: `test_butler_sees_units_board_names_level`, `test_butler_no_phone_of_foreign_guest`, `test_butler_own_card_full`, `test_butler_candidates_readable`, `test_butler_assign_403`, `test_butler_create_reservation_403`, `test_butler_ooo_block_403`, `test_bar_mine_flag_only_own`, `test_units_board_budget_with_mine_flag` (≤ 30).
- [ ] jsdom (ivanov): шахматка открывается, своя полоса с рамкой, кнопок создания и назначения нет, табло с подбором кандидатов без кнопок.
- [ ] RED → реализация → GREEN; `python tools/export_openapi.py`; `python tools/bump_version.py <версия>`; коммит `feat(stays): шахматка и табло у батлера — только чтение, свои брони выделены`.

### Task 3: Правка батлером — профиль, семейное дерево, пожелания, состав брони

**Files:** `interface/guests_api.py` (связи, пожелания, новый человек), `application/guests.py` (`created_by_employee_id` при создании через дерево), `application/mine.py` (`check_reservation_change` — родство по дереву; `check_link_change`), `application/family.py`, `static/js/modules/stays_family.js`, `static/js/modules/stays_forms.js` (кнопки по правам), `tools/stays_scenario.mjs`.
**Test:** `tests/stays/test_mine_edit.py` (новый).

**Interfaces:**
- `POST /api/stays/guests/{gid}/links`, `DELETE /api/stays/guest-links/{link_id}`, `PATCH /api/stays/guest-links/{link_id}` (бывшие) — `require_perm("stays.edit", "stays.mine_guest_edit")`; без `stays.edit` — `gid` (для удаления — хотя бы одна сторона связи) свой, иначе 403. Новый человек из тела связи получает `created_by_employee_id = principal.employee.id`, когда правит батлер.
- `GET/PUT /api/stays/guests/{gid}/prefs` — чтение `require_perm("stays.guests", "stays.mine")`, запись `require_perm("stays.edit", "stays.mine_guest_edit")`; для батлера — свой гость; запись через `_ops.run` (предпросмотр, овербукинг — как у всех).
- `mine.check_reservation_change`: новый проживающий допустим, если он связан с кем-то из прежних проживающих прямой связью любого вида **или** родством по `domain/kinship.py` (вычисленным); иначе `MineForbidden("Батлер добавляет только родственников и связанных с проживающими брони")`.
- Профиль: `GUEST_FREE` — `preferences`, `special_dates`, `fields`, `note` (как есть); `special`, `vip_code_id`, ФИО, телефон, email, ДР, пол — заперты (403).
- JS: в карточке гостя кнопки «Изменить», «+ родитель/супруг(а)/ребёнок», удаление связи, «Предпочитает» — по `stays.mine_guest_edit` (или `stays.edit`); в карточке брони «Изменить» — по `stays.mine_res_edit` (или `stays.edit`).

- [ ] Тесты: `test_mine_adds_child_new_person_becomes_own`, `test_mine_link_on_foreign_guest_403`, `test_mine_link_delete_ownership`, `test_mine_tree_checks_422` (свой предок, третий родитель), `test_mine_prefs_preview_equals_save`, `test_mine_prefs_new_overbook_409`, `test_mine_prefs_foreign_guest_403`, `test_mine_adds_computed_relative`, `test_mine_adds_direct_link_assistant`, `test_mine_adds_unlinked_403`, `test_mine_profile_locked_fields_403`, `test_no_guest_edit_perm_read_only` (снятое право — 403 на запись, чтение есть).
- [ ] jsdom (ivanov): «+ ребёнок» своему гостю → новый человек в дереве и открывается его профиль; пожелание к объекту с предпросмотром.
- [ ] RED → реализация → GREEN; `python tools/export_openapi.py`; `python tools/bump_version.py <версия>`; коммит `feat(stays): батлер правит профиль, семью и пожелания своих гостей`.

### Task 4: API «Мои гости» — сегодня, месяц, все мои гости

**Files:** `application/mine.py` (`mine_today`, `mine_month`, `mine_guests`, `mine_guest_card`), `application/history.py` (кто вёл — имя батлера), `interface/boards_api.py` (эндпоинты).
**Test:** `tests/stays/test_mine_screens.py` (новый).

**Interfaces:**
- `GET /api/stays/mine/today` (`stays.mine`) → `{"date", "reservations": [{reservation_id, number, status, unit, check_in, check_out, guests: [{guest_id, name, special, vip_code, role, phone, preferences, special_dates_soon: [{date, what}]}], logistics: [today и завтра]}]}` — брони, где батлер ведёт кого-то сегодня; `unit` — по фонду дня; `special_dates_soon` — особые даты и ДР в ближайшие 7 дней. Прежний `GET /api/stays/mine` удаляется (экран переходит на новые в Task 5).
- `GET /api/stays/mine/month?first&last` (`stays.mine`; не длиннее 62 дней) → `{"days", "rows": [{unit_id | null, label, bars: [{reservation_id, start_pos, end_pos, status, main_guest, special}]}], "load": [{day, value, guests, level: "one"|"many"|"over"}], "limit", "absences": [day…]}` — строки — объекты своих броней в периоде (по фонду дня) и строка `unit_id: null` «без объекта» внизу, если есть своя бронь без объекта; `load` — нагрузка батлера по дням из `StaysContext.loads` (одна загрузка контекста на период); `absences` — дни отсутствия по Графику (`DutyPort`), отметка «О».
- `GET /api/stays/mine/guests?q=&offset=&limit=` (`stays.mine`) → `{"rows": [{guest_id, name, special, vip_code, last_stay, stays}], "total"}` — только свои, поиск по фамилии; по 50.
- `GET /api/stays/mine/guests/{gid}` (`stays.mine`, свой) → профиль (полный) + `history: [{reservation_id, check_in, check_out, unit, led: [{employee_id, name, me: bool, first, last}]}]` — кто вёл по непрерывным отрезкам.
- Бюджет: каждый из четырёх — фиксированное число запросов, не растущее с числом броней в истории.

- [ ] Тесты: `test_today_lists_only_today_led`, `test_today_unit_by_fund_of_day`, `test_today_special_dates_7_days`, `test_month_rows_and_unallocated_row`, `test_month_tentative_flag`, `test_month_load_levels_one_many_over`, `test_month_absences_from_schedule`, `test_month_span_max_62_422`, `test_all_guests_search_only_own`, `test_guest_card_history_me_and_other_name`, `test_foreign_guest_card_403`, `test_mine_budget_independent_of_history` (5 и 500 броней — одинаковое число запросов).
- [ ] RED → реализация → GREEN; `python tools/export_openapi.py`; коммит `feat(stays): API «Мои гости» — сегодня, мой месяц, все мои гости`.

### Task 5: Экран «Мои гости» (телефон)

**Files:** `static/js/modules/stays_board.js` (`renderMine` → три вкладки) или новый `static/js/modules/stays_mine.js` (если `stays_board.js` растёт сверх ~600 строк — вынести), `static/css/*` (стили мини-шахматки и полосы нагрузки), `tools/stays_scenario.mjs`.
**Test:** `tools/stays_scenario.mjs` (сценарий ivanov — новый раздел).

**Interfaces:**
- Вкладки «Сегодня» / «Мой месяц» / «Все мои гости»; ◀ ▶ месяца — общий месяц приложения `state.year`/`state.month` (как в Табеле, `static/js/app.js`).
- «Сегодня»: карточки броней — ◆, код, объект, заезд–выезд, логистика сегодня/завтра, предпочтения, особые даты в 7 днях; кнопки «Изменить» по правам (Task 3).
- «Мой месяц»: над сеткой полоса нагрузки (цвета: один гость / несколько / выше лимита; «О» — отсутствие); строки объектов, полосы по половинкам суток (как на шахматке); предварительная — бледная с пунктиром; строка «без объекта» — красная полоса; клик — карточка брони.
- «Все мои гости»: поиск по фамилии, список, карточка гостя с историей («вёл я 03.05–08.05» / «вела Кузнецова 03.05–08.05»).
- Ширина 375 px без горизонтальной прокрутки страницы (сетка месяца прокручивается внутри себя).

- [ ] jsdom (ivanov): «Сегодня» — карточка с ◆ и логистикой; «Мой месяц» — ◀ ▶ меняет месяц и общий месяц приложения, полоса нагрузки, строка «без объекта» (бронь без объекта в данных сценария); «Все мои гости» — поиск находит своего, не находит чужого, история с именем другого батлера; правка профиля из карточки.
- [ ] Проверка 375 px: `scrollWidth` страницы ≤ ширины окна.
- [ ] RED → реализация → GREEN; `python tools/bump_version.py <версия>`; коммит `feat(stays): экран «Мои гости» — сегодня, мой месяц, все мои гости`.
