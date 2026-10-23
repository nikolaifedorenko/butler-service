# Модуль «Шахматка» (stays) — план реализации

> **Для исполнителей-агентов:** обязательный навык — superpowers:subagent-driven-development
> (рекомендуется) или superpowers:executing-plans; задачи выполняются по одной, шаги
> отмечаются чекбоксами (`- [ ]`).

**Цель:** модуль butler-service, который показывает, какие гости где и когда живут, и кто
из батлеров их ведёт: с нагрузкой, конфликтами с Графиком, подбором подмены и
предпросмотром «что будет, если» до сохранения.

**Архитектура:** новый модуль `app/modules/stays` в гексагональной раскладке остальных
модулей (domain → application → interface, ports/adapters). Подключается манифестом
(ADR-0012), схема — одна ревизия Alembic `0008`. Алгоритмы (половинки суток,
автораспределение, покрытие, нагрузка, предупреждения, подбор) — чистые функции в
`domain/`. Предупреждения не хранятся: они считаются при каждом чтении против Графика,
который читается одним пакетным запросом. Предпросмотр выполняет ту же операцию в
SAVEPOINT и откатывает её.

**Стек:** FastAPI, SQLAlchemy 2, Alembic, pydantic 2, openpyxl, фронтенд без сборки
(`registerModule`), ESLint, jsdom-сценарии `tools/*_scenario.mjs`.

**Спецификация:** `docs/superpowers/specs/2026-10-23-stays-chessboard-design.md`
(редакция 2). Ниже ссылки вида «§4.6» ведут в неё. Алгоритмическое ядро взято из PoC:
`/Users/nikolayfedorenko/Documents/Claude/chessboard/SPEC.md` (§5, §6.3, §14.4) и
`app.py` (`compute_segments`, `auto_assign`).

## Общие ограничения

* Ответы, тексты интерфейса, сообщения об ошибках, комментарии и документы — по-русски.
* Перед каждым этапом и после него — полный прогон проверок (Global Gate):
  `pytest -q`, `ruff check .`, `lint-imports`, `python tools/check_api_contract.py`,
  `python tools/gen_js_globals.py --check`, `npm run lint`,
  `python tools/bump_version.py --check`, `python tools/gen_importlinter.py --check`,
  `python tools/doc_links.py`, `python tools/export_openapi.py --check`.
  Окружение: `PATH="$PWD/.venv/bin:/opt/homebrew/opt/node@22/bin:$PATH"`.
* В конце каждого этапа — запись в `CHANGELOG.md` (раздел даты, подзаголовок
  «Шахматка, этап N: …»), а не отдельный файл CHANGES-*.
* Коммит — только по явной просьбе владельца, без `docs/audit/`, с завершающей строкой
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Шаг «Коммит» в задачах
  означает: подготовить коммит и выполнить его, когда владелец попросит.
* `.env` не открывать, секреты не выводить; `timetrack.db` не читать.
* Модуль импортирует другие модули только через их `application`/`ports` (R3,
  `.importlinter`); `core` модуль не знает.
* Табель модуль не меняет никогда (§5): только чтение Графика и запись ручной смены
  через публичную функцию модуля timesheet.
* Даты — локальные даты объекта (`app.core.time.local_date`); моменты — как в ядре.
* Сервер не отдаёт поля, которые не положены уровню (§8): фильтрация в сериализаторе,
  а не в интерфейсе.
* Бюджеты SQL: шахматка объектов, шахматка батлеров, табло дня и сводная загрузка на
  440 объектах за 31 день — не больше **30** запросов каждый, без роста по числу объектов,
  броней и батлеров.
* Эталон фонда для демо и тестов на объёме: 37 вилл, имение, 2 медицинских апартамента,
  ~400 номеров основного корпуса в 2 корпусах.

## На что смотреть при ревью

Пять случаев, которые спецификация подразумевает, но легко пропустить. Тест на каждый
добавлен в задачу, которой принадлежит код.

1. **Устаревшая версия брони при предпросмотре.** Второй менеджер открыл бронь до
   чужого сохранения: и предпросмотр, и сохранение отвечают 409, а не показывают картину
   по старым данным (задача 9).
2. **Переезд в день замены батлера.** Утро в старом объекте, вечер в новом: строка
   покрытия одна, объект дня берётся по сегменту, который действует на PM этой даты, вес
   не считается дважды (задача 13).
3. **Отпуск, поставленный в Графике после назначения.** Без какого-либо действия в
   шахматке следующее чтение показывает «нужна подмена», а не «вне смены» (задачи 13
   и 15).
4. **Утечка фамилий в обезличенный уровень через побочные поля:** примечания, метка
   «гость отказался», логистика, текст предупреждений, дельта предпросмотра. Проверка
   ищет фамилии демо-гостей во **всём** JSON-ответе (задача 17).
5. **No-show единственного гостя группы совместного проживания.** Объект группы
   освобождается только тогда, когда не заехали все её брони; при одном отказе из
   двух — нет (задача 8).

---

## Структура файлов

```
app/modules/stays/
  __init__.py
  manifest.py                    права, меню, экраны Настроек, действия аудита
  domain/
    __init__.py
    halfday.py                   pos, overlaps, Segment, segments()
    allocate.py                  автораспределение (PoC §6.3 + группы + корпус)
    coverage.py                  кто кого ведёт на день, шаблоны покрытия
    load.py                      нагрузка батлеров
    warnings.py                  предупреждения §4.4
    candidates.py                подбор и подмена §4.5
    types.py                     общие dataclass'ы домена
  ports/
    __init__.py
    duty.py                      DutyPort: смены и отсутствия на диапазон
  adapters/
    __init__.py
    orm.py                       все модели модуля
    duty_timesheet.py            DutyPort поверх timesheet.application.roster
  application/
    __init__.py
    catalog.py                   публичная поверхность (как у остальных модулей)
    fund.py                      категории, объекты, блоки, метки, поля, «сопровождают», настройки
    guests.py                    профили, связи, поиск
    reservations.py              брони: документ брони, статусы, no-show, версии
    allocation.py                загрузка из БД → domain.allocate → запись назначений
    context.py                   StaysContext: сборка дня (кто где живёт) для покрытия и видов
    coverage.py                  шаблоны, ручная правка, чистка строк, подбор, «добавить смену»
    preview.py                   снимок, разница, запуск операции в SAVEPOINT
    views.py                     шахматки, табло, загрузка, «Мои гости»
    visibility.py                уровни ПД и сериализаторы
    history.py                   лента брони из аудита, история проживаний гостя
    export.py                    выгрузка Excel полная и обезличенная
    demo.py                      демо-данные
  interface/
    __init__.py
    fund_api.py  guests_api.py  reservations_api.py  coverage_api.py  views_api.py  export_api.py
app/bootstrap/alembic/versions/0008_stays.py
app/modules/timesheet/application/roster.py          публичный запрос «смены и отсутствия на даты»
static/js/modules/stays.js            вид «Шахматка»: вкладки, шахматка объектов, карточки
static/js/modules/stays_board.js      шахматка батлеров, табло дня, сводная загрузка, «Мои гости»
static/js/modules/stays_forms.js      формы брони, гостя, назначений + панель предпросмотра
static/js/modules/stays_settings.js   4 экрана Настроек
static/css/app.css                    стили шахматки (дописываются)
tests/stays/                          тесты модуля (по файлу на задачу)
tools/stays_scenario.mjs, tools/run_stays_scenario.sh
```

---

## Этап 1. Каркас и фонд

### Задача 1: Манифест, права, роли и пустой модуль

**Файлы:**
- Создать: `app/modules/stays/__init__.py`, `manifest.py`, пустые пакеты `domain/`,
  `ports/`, `adapters/`, `application/`, `interface/`
- Изменить: `.importlinter` (через `python tools/gen_importlinter.py`)
- Тест: `tests/stays/__init__.py`, `tests/stays/test_manifest.py`

**Интерфейсы:**
- Даёт: права `stays.occupancy`, `stays.view`, `stays.edit`, `stays.edit_mine`,
  `stays.assign`, `stays.guests`, `stays.mine`, `stays.setup`, `stays.export`; пункты меню
  `stays` («Шахматка», order 55, perms `("stays.view", "stays.occupancy")`) и
  `stays-mine` («Мои гости», order 56, perms `("stays.mine",)`); экраны Настроек
  `stays-fund` («Фонд и категории»), `stays-escort` («Сопровождение»), `stays-fields`
  («Настраиваемые поля»), `stays-labels` («Метки броней») — группа «Шахматка», perm
  `stays.setup`.

- [ ] **Шаг 1. Прогон Global Gate до правки** — зелёный; фиксирую число тестов.
  Сразу добавить `"docs/superpowers/plans/"` в `HISTORICAL` в `tools/doc_links.py`:
  план называет файлы, которых ещё нет, и без исключения `doc_links` падает
  (проверено: 65 срабатываний). Коммит плана — вместе с этой строкой.
- [ ] **Шаг 2. Падающий тест.**

```python
from app.core.permissions import role_permissions

def test_stays_permissions_defaults(db):
    sup, emp, man = (role_permissions(db, r) for r in ("supervisor", "employee", "manager"))
    assert {"stays.view", "stays.edit", "stays.assign", "stays.guests"} <= sup
    assert {"stays.edit_mine", "stays.mine"} <= emp
    assert not {"stays.view", "stays.setup", "stays.occupancy"} & emp
    assert {"stays.setup", "stays.export"} <= man and not {"stays.setup", "stays.export"} & sup
    assert "stays.occupancy" not in man          # только своей ролью «Загрузка без гостей»

def test_stays_menu_for_employee(employee_client):
    me = employee_client.get("/api/auth/me").json()
    ids = {m["id"] for m in me["menu"]}           # manifest.ui_for разворачивается в ответ /me
    assert "stays-mine" in ids and "stays" not in ids
```

- [ ] **Шаг 3. Запуск:** `pytest tests/stays/test_manifest.py -v` → FAIL (нет прав).
- [ ] **Шаг 4. Реализация** `MODULE = ModuleManifest(name="stays", title="Шахматка",
  order=75, routers=(), models=(), permissions=…, menu=…, settings_screens=…,
  audit_actions=…)`. Роли по умолчанию — из таблицы §7: `SUPERVISOR_UP` для view, edit,
  assign, guests; `EVERYONE` для edit_mine и mine; `MANAGER_UP` для setup и export;
  `()` для occupancy. `audit_actions` — все действия модуля, которые появятся дальше:
  `stays_fund`, `stays_guest`, `stays_guest_link`, `stays_reservation`,
  `stays_reservation_status`, `stays_hold`, `stays_coverage`, `stays_coverage_cleanup`,
  `stays_add_shift`, `stays_export` с русскими названиями. Перегенерировать
  `.importlinter`.
- [ ] **Шаг 5. Запуск:** тест PASS; `lint-imports` и `gen_importlinter --check` зелёные.
- [ ] **Шаг 6. Коммит** «Шахматка: каркас модуля и права».

### Задача 2: Модели модуля и ревизия 0008

Вся схема модуля — одной ревизией: модуль выходит одним выпуском, а
`tests/test_db_upgrade.py::test_models_match_migrations` требует совпадения моделей и
миграций на каждом шаге.

**Файлы:**
- Создать: `app/modules/stays/adapters/orm.py`, `app/bootstrap/alembic/versions/0008_stays.py`
- Изменить: `app/modules/stays/manifest.py` (`models=("app.modules.stays.adapters.orm",)`)
- Тест: `tests/stays/test_schema.py`

**Интерфейсы — даёт таблицы (все с префиксом `stays_`):**

| Модель | Таблица | Поля (кроме `id`) |
|---|---|---|
| `Category` | `stays_categories` | `code` String(16) unique, `title`, `kind` (`villa`/`estate`/`apartment`/`room`), `escorted` bool, `weight` Numeric(5,2), `sort_order` |
| `Unit` | `stays_units` | `label` String(40) unique, `category_id` FK, `building` String(40) "", `floor` String(8) "", `active` bool, `sort_order` |
| `Hold` | `stays_holds` | `unit_id` FK, `start` Date, `end` Date, `kind` (`block`/`ooo`), `title` |
| `Label` | `stays_labels` | `title` unique, `color` String(9) |
| `Guest` | `stays_guests` | `last_name`, `first_name`, `middle_name`, `phone` (нормализованный), `email`, `birth_date` null, `level` (`regular`/`vip`/`vvip`), `preferences_json`, `special_dates_json`, `fields_json`, `note`, `external_id` null, `source` "", `search_text` String(1000) index, `created_at`, `updated_at` |
| `GuestLink` | `stays_guest_links` | `guest_a_id` FK, `guest_b_id` FK, `kind`; UNIQUE(a,b,kind) |
| `StayGroup` | `stays_groups` | `title` |
| `Reservation` | `stays_reservations` | `number` String(40) index (не unique), `status` (`tentative`/`confirmed`/`in_house`/`checked_out`/`cancelled`/`no_show`), `check_in`, `check_out`, `early` bool, `late` bool, `category_id` FK, `paid_by`, `label_id` FK null, `customer`, `purpose`, `note`, `declined_butler` bool, `fields_json`, `external_id` null, `source`, `group_id` FK null, `version` int default 1, `search_text` String(1000) (номер брони, заказчик, значения полей с `searchable`; фамилии и телефоны гостей ищутся через `stays_guests.search_text`), `created_at`, `updated_at` |
| `Move` | `stays_moves` | `reservation_id` FK, `move_date`, `category_id` FK; UNIQUE(reservation_id, move_date) |
| `Assignment` | `stays_assignments` | `reservation_id` FK, `seg_index`, `unit_id` FK null, `pinned` bool; UNIQUE(reservation_id, seg_index) |
| `Occupant` | `stays_occupants` | `reservation_id` FK, `guest_id` FK, `date_from`, `date_to`, `role` (`main`/`guest`) |
| `Companion` | `stays_companions` | `reservation_id` FK, `kind` (`security`/`driver`/`nanny`/`pet`/`other`), `description` |
| `Logistics` | `stays_logistics` | `reservation_id` FK, `kind` (`flight`/`transfer`/`car`), `date` null, `time` String(5) "", `description` |
| `Escort` | `stays_escorts` | `employee_id` FK `employees.id` unique, `active` bool |
| `CoverageLine` | `stays_coverage` | `day` Date index, `employee_id` FK, `reservation_id` FK null, `group_id` FK null, `source` (`template`/`manual`), `overnight` bool, `comment`; CHECK ровно одно из reservation_id/group_id |
| `CoverageOccupant` | `stays_coverage_occupants` | `coverage_id` FK (ondelete CASCADE), `occupant_id` FK; PK (coverage_id, occupant_id) |
| `CustomField` | `stays_fields` | `target` (`guest`/`reservation`), `code`, `title`, `kind` (`text`/`choice`/`bool`/`date`), `choices_json`, `searchable` bool, `sort_order`; UNIQUE(target, code) |
| `StaysSettings` | `stays_settings` | одна строка `id=1`: `vip_bonus` Numeric(5,2)=1, `vvip_bonus`=2, `daily_limit`=8, `replacement_codes` String(120)="ОТ,ДО,Б,ОВ,К" |

Индексы: `stays_reservations(check_in, check_out)`, `stays_occupants(guest_id)`,
`stays_coverage(employee_id, day)`, `stays_holds(unit_id, start)`.

`replacement_codes` — решение плана: отпуск и больничный в проекте — это коды Табеля, по
которым График перегенерируется без смены, поэтому «нужна подмена» отличается от
«выходной» только по коду дня. Список кодов редактируется на экране «Сопровождение».

- [ ] **Шаг 1. Падающий тест.**

```python
def test_stays_tables_created(db):
    from sqlalchemy import inspect
    names = set(inspect(db.get_bind()).get_table_names())
    assert {"stays_categories", "stays_units", "stays_reservations", "stays_occupants",
            "stays_coverage", "stays_coverage_occupants", "stays_settings"} <= names

def test_stays_settings_row_seeded(db):
    from app.modules.stays.adapters.orm import StaysSettings
    s = db.get(StaysSettings, 1)
    assert (float(s.vip_bonus), float(s.vvip_bonus), float(s.daily_limit)) == (1.0, 2.0, 8.0)
```

- [ ] **Шаг 2. Запуск:** FAIL.
- [ ] **Шаг 3. Модели** в `orm.py` по таблице выше (стиль `cars/adapters/orm.py`:
  `Mapped`, `mapped_column`, без кросс-модульных relationship, FK на `employees.id`
  строкой). Ревизия `0008` (`down_revision='0007'`): создаёт таблицы, вставляет строку
  `stays_settings(id=1)` и две роли как данные — `mgmt_view` «Руководство: только
  просмотр» (rank 10, max_assignable_rank −1) с грантами `stays.view`, `stays.guests` и
  `occupancy` «Загрузка без гостей» (rank 10, −1) с грантом `stays.occupancy` (гранты —
  `access_grants(role=…, effect="allow")`, как в 0007). Повторный запуск безопасен
  (проверка существования, как в 0007). Создание таблиц сгенерировать
  `alembic revision --autogenerate` и вычитать вручную.
- [ ] **Шаг 4. Запуск:** `pytest tests/stays/test_schema.py tests/test_db_upgrade.py -v` → PASS;
  PG-прогон тех же тестов (`audit-pg16`, `DATABASE_URL=postgresql+psycopg2://postgres:pg@127.0.0.1:55432/postgres`) → PASS.
- [ ] **Шаг 5. Коммит** «Шахматка: схема и роли».

### Задача 3: Справочники фонда, настройки, метки, поля, «сопровождают гостей»

**Файлы:**
- Создать: `app/modules/stays/application/fund.py`, `application/catalog.py`,
  `interface/fund_api.py`
- Изменить: `manifest.py` (`routers=("app.modules.stays.interface.fund_api:router", …)`)
- Тест: `tests/stays/test_fund_api.py`

**Интерфейсы:**
- Даёт (application): `class FundError(Exception)`, `class FundConflict(FundError)`;
  `list_fund(db) -> dict` (`categories`, `units`, `labels`, `fields`, `escorts`,
  `settings`); `save_category(db, data: dict, cid: int | None) -> Category`;
  `save_unit(...)`, `save_label(...)`, `save_field(...)`, `delete_*(db, id)`;
  `set_escort(db, employee_id: int, active: bool) -> Escort`;
  `seed_escorts_from_positions(db) -> int` — добавляет активных сотрудников, у которых
  `position` без учёта регистра начинается с «батлер» или содержит «батлер», если их ещё
  нет в списке; `get_settings(db) -> StaysSettings`;
  `save_settings(db, vip_bonus, vvip_bonus, daily_limit, replacement_codes) -> StaysSettings`.
- Даёт (HTTP, prefix `/api/stays`, право `stays.setup` на запись, `stays.view` или
  `stays.occupancy` на чтение `GET /fund`): `GET /fund`, `POST|PUT|DELETE /categories[/{id}]`,
  `/units`, `/labels`, `/fields`, `PUT /escorts/{employee_id}`, `POST /escorts/seed`,
  `PUT /settings`. Каждая запись → `audit(db, principal, "stays_fund", "<что>:<id>",
  {"before": …, "after": …})`.

- [ ] **Шаг 1. Падающие тесты.**

```python
def test_category_crud_and_audit(manager_client, db): ...
    # POST /api/stays/categories {"code":"VEG","title":"Вилла Garden","kind":"villa",
    #   "escorted":true,"weight":4} → 200; повтор того же code → 409 «Код категории занят»;
    # в журнале аудита запись action="stays_fund", target начинается с "category:"
def test_unit_requires_existing_category(manager_client): ...   # 422
def test_delete_category_with_units_refused(manager_client): ... # 409 «В категории есть объекты»
def test_setup_forbidden_for_supervisor(client_supervisor): ...  # POST /categories → 403
def test_escorts_seed_from_position(manager_client, db): ...
    # сотрудник с position="Батлер" попадает в список, "Старший батлер" тоже, "Горничная" — нет;
    # повторный seed не создаёт дублей
def test_settings_validation(manager_client): ...
    # daily_limit <= 0 → 422; vip_bonus < 0 → 422
def test_choice_field_requires_choices(manager_client): ...      # kind="choice", choices=[] → 422
```

(Фикстура старшего — по образцу `tests/test_authz_matrix.py`; если её нет в
`conftest.py`, добавить `supervisor_client` туда же.)

- [ ] **Шаг 2. Запуск:** FAIL.
- [ ] **Шаг 3. Реализация** в `fund.py` и `fund_api.py` (pydantic-модели входа рядом с
  роутером, как в `cars_api.py`). Удаление объекта с назначениями или блоками → 409;
  такой объект можно сделать неактивным.
- [ ] **Шаг 4. Запуск:** PASS; `python tools/check_api_contract.py`, `export_openapi.py`
  (обновить `docs/openapi.json` командой без `--check`).
- [ ] **Шаг 5. Коммит.**

### Задача 4: Экраны Настроек модуля

**Файлы:**
- Создать: `static/js/modules/stays_settings.js`
- Изменить: `static/index.html` и `static/sw.js` через `python tools/bump_version.py`
  (список `<script>` генерирует он), `tools/js_globals.json` через `gen_js_globals.py`
- Тест: `tools/settings_scenario.mjs` (дописать шаг) или отдельный блок в
  `tools/stays_scenario.mjs` (создаётся здесь, расширяется в задаче 20)

**Интерфейсы:**
- Потребляет: HTTP из задачи 3.
- Даёт: `registerModule({ screens: { 'stays-fund': {render: renderStaysFund, icon: 'building'},
  'stays-escort': …, 'stays-fields': …, 'stays-labels': … } })`.

- [ ] **Шаг 1. Сценарий:** под `admin` открыть каждый из четырёх экранов, создать
  категорию и объект, отметить сотрудника «сопровождает», поменять лимит — проверить
  ответ API и перерисовку таблицы. Под `employee` экранов в списке Настроек нет.
- [ ] **Шаг 2. Запуск сценария** → FAIL.
- [ ] **Шаг 3. Реализация** в стиле `cars.js` (`esc()` для всего пользовательского
  текста, `api()`, `openModal`, `toast`). Экран «Сопровождение»: таблица сотрудников
  со столбцом «сопровождает», кнопка «Заполнить по должности», поля надбавок, лимита и
  кодов «нужна подмена».
- [ ] **Шаг 4. Запуск:** сценарий PASS; `npm run lint`, `gen_js_globals --check`,
  `bump_version --check` зелёные.
- [ ] **Шаг 5. Global Gate, запись этапа 1 в CHANGELOG.md, коммит.**

---

## Этап 2. Гости и брони

### Задача 5: Домен — половинки суток и сегменты

**Файлы:**
- Создать: `app/modules/stays/domain/halfday.py`, `domain/types.py`
- Тест: `tests/stays/test_halfday.py`

**Интерфейсы:**
- Даёт: `AM = 0`, `PM = 1`; `pos(day: date, half: int) -> int` (`day.toordinal()*2+half`);
  `overlaps(a0: int, a1: int, b0: int, b1: int) -> bool` (отрезки включительно);
  `@dataclass(frozen=True) Segment(index: int, category_id: int, start: date, end: date,
  start_pos: int, end_pos: int)`;
  `segments(check_in: date, check_out: date, early: bool, late: bool, category_id: int,
  moves: Sequence[tuple[date, int]]) -> list[Segment]` (PoC `compute_segments`);
  `validate_dates(check_in, check_out, moves) -> list[str]` — тексты ошибок:
  «Выезд должен быть позже заезда», «Дата переезда вне проживания», «Две даты переезда
  совпадают»; `hold_span(start: date, end: date) -> tuple[int, int]` =
  `(pos(start, AM), pos(end, PM))`;
  `segment_on(segments, day: date, half: int) -> Segment | None`.

- [ ] **Шаг 1. Тесты** — пять примеров PoC SPEC §5.4 дословно (сентябрь 2026):

```python
S = date(2026, 9, 1).toordinal() * 2   # pos(01.09, AM)
def p(d, h): return date(2026, 9, d).toordinal() * 2 + h

def test_poc_1_plain():
    (s,) = segments(date(2026,9,2), date(2026,9,18), False, False, 1, ())
    assert (s.start_pos, s.end_pos) == (p(2,1), p(18,0))
def test_poc_2_early_late():
    (s,) = segments(date(2026,9,17), date(2026,9,21), True, True, 1, ())
    assert (s.start_pos, s.end_pos) == (p(17,0), p(21,1))
def test_poc_3_move():
    a, b = segments(date(2026,9,17), date(2026,9,25), False, False, 1, ((date(2026,9,21), 2),))
    assert (a.category_id, a.start_pos, a.end_pos) == (1, p(17,1), p(21,0))
    assert (b.category_id, b.start_pos, b.end_pos) == (2, p(21,1), p(25,0))
def test_poc_4_checkout_then_checkin_same_day():
    assert not overlaps(p(2,1), p(18,0), p(18,1), p(20,0))
    assert overlaps(p(2,1), p(18,0), p(18,0), p(20,0))
def test_poc_5_ooo():
    assert hold_span(date(2026,9,1), date(2026,9,12)) == (p(1,0), p(12,1))
    assert overlaps(*hold_span(date(2026,9,1), date(2026,9,12)), p(12,1), p(15,0))
def test_segment_on_move_day():
    segs = segments(date(2026,9,17), date(2026,9,25), False, False, 1, ((date(2026,9,21), 2),))
    assert segment_on(segs, date(2026,9,21), AM).index == 0
    assert segment_on(segs, date(2026,9,21), PM).index == 1
```

- [ ] **Шаг 2. Запуск:** FAIL. **Шаг 3. Реализация.** **Шаг 4. Запуск:** PASS.
- [ ] **Шаг 5. Коммит.**

### Задача 6: Домен — автораспределение

**Файлы:**
- Создать: `app/modules/stays/domain/allocate.py`
- Тест: `tests/stays/test_allocate.py`

**Интерфейсы:**
- Потребляет: `Segment`, `overlaps`, `hold_span` из задачи 5.
- Даёт:
  * `UnitRef(id: int, category_id: int, building: str, cat_sort: int, label: str)`;
  * `HoldRef(unit_id: int, start_pos: int, end_pos: int, title: str)`;
  * `AllocItem(key: tuple[str, int], number: str, segments: tuple[Segment, ...],
    pinned: Mapping[int, int])` — `key` = `("r", reservation_id)` или `("g", group_id)`,
    `pinned` — `seg_index → unit_id`;
  * `AllocWarning(kind: str, key: tuple[str, int], seg_index: int, text: str)`,
    `kind` ∈ `unassigned`, `pin_invalid`, `pin_conflict`;
  * `allocate(units: Sequence[UnitRef], holds: Sequence[HoldRef], items: Sequence[AllocItem])
    -> tuple[dict[tuple[tuple[str, int], int], int | None], list[AllocWarning]]`.

Алгоритм — PoC §6.3 без изменений (`app.py:auto_assign`) с тремя дополнениями §4.1:
порядок объектов — `(cat_sort, natural_key(label))`; при переезде из объекта R в
корпусе b кандидаты сначала без R, затем среди них предпочитаются объекты корпуса b;
группы приходят одним `AllocItem` (их собирает задача 8), отменённые и no-show сюда не
попадают. Функция чистая: данные приходят готовыми, БД она не видит.

- [ ] **Шаг 1. Тесты:**

```python
def test_first_fit_by_natural_label(): ...        # объекты "4010","402","4003" одной категории:
                                                  # первая бронь получает "402" (natural: 402 < 4003 < 4010)
def test_longer_first_on_same_start(): ...        # две брони с одного дня: длинная получает первый объект
def test_pinned_respected_and_conflict_warned(): ...  # закреплённая поверх блока → pin_conflict, назначение остаётся
def test_pin_wrong_category_released(): ...       # pin_invalid, сегмент распределён автоматически
def test_move_prefers_other_unit_same_building(): ...
    # корпуса "1" и "2"; сегмент 0 в "1-201"; сегмент 1 той же категории → "1-202", не "2-201"
def test_no_free_unit_warning_text(): ...
    # text == "Бронь 777: нет свободных объектов категории DLX на 18.09–21.09"
def test_idempotent(): ...                        # два прогона на тех же данных дают одинаковый результат
def test_group_takes_one_unit(): ...              # один AllocItem ("g", 5) → один объект на всех
```

- [ ] **Шаг 2.** FAIL. **Шаг 3.** Реализация. **Шаг 4.** PASS. **Шаг 5.** Коммит.

### Задача 7: Гости — профили, связи, поиск

**Файлы:**
- Создать: `app/modules/stays/application/guests.py`, `interface/guests_api.py`
- Тест: `tests/stays/test_guests_api.py`

**Интерфейсы:**
- Даёт (application):
  * `normalize_phone(raw: str) -> str` — перенос PoC `normalize_phone` (`+7…`, только
    цифры и `+`), `format_phone(p: str) -> str`;
  * `LINK_KINDS = {"spouse": ("супруг(а)", "супруг(а)"), "child": ("ребёнок", "родитель"),
    "relative": ("родственник", "родственник"), "assistant": ("ассистент", "работодатель"),
    "security": ("охрана", "под охраной"), "driver": ("водитель", "пассажир"),
    "nanny": ("няня", "под присмотром"), "colleague": ("коллега", "коллега"),
    "other": ("другое", "другое")}` — подпись для B в профиле A и для A в профиле B;
  * `save_guest(db, data: dict, gid: int | None) -> Guest` (проверка значений
    настраиваемых полей по `CustomField.kind` и `choices`);
  * `links_of(db, guest_id: int) -> list[dict]` (`{"id", "guest_id", "name", "label"}`);
  * `guest_search_text(g: Guest, searchable: set[str]) -> str` — ФИО, цифры телефона,
    email и значения полей с `searchable=True`, в нижнем регистре Python (SQLite
    `lower()` кириллицу не понижает); пишется в `Guest.search_text` при каждом
    сохранении; `reindex_search(db) -> int` пересчитывает всех гостей и брони после
    изменения флага «искать по полю» (вызывается из `save_field`, задача 3);
  * `search_guests(db, q: str, limit: int = 30) -> list[Guest]` —
    `search_text.contains(q.strip().lower())`; если в `q` только цифры и знаки
    телефона — поиск по цифрам.
- Даёт (HTTP): `GET /guests?q=` (`stays.view` → список с фамилией и уровнем; полная
  карточка только с `stays.guests`), `POST /guests`, `PUT /guests/{id}` (`stays.guests` или
  `stays.edit_mine` на своего гостя — проверка владения подключается в задаче 17),
  `GET /guests/{id}`, `POST /guests/{id}/links {"guest_id","kind"}`,
  `DELETE /guest-links/{id}`; аудит `stays_guest`, `stays_guest_link` с разницей полей.

- [ ] **Шаг 1. Тесты:**

```python
def test_phone_normalized(manager_client): ...   # "8 (916) 123-45-67" → "+79161234567"
def test_link_labels_both_sides(manager_client):
    # A —child→ B: в профиле A у B подпись "ребёнок", в профиле B у A — "родитель"
def test_link_to_self_refused(manager_client): ...  # 422
def test_search_cyrillic_case_insensitive(manager_client): ...  # "орлов" находит "Орлов"
def test_search_by_searchable_field_only(manager_client): ...
    # поле "club" searchable=True находит, поле "secret" searchable=False — нет
def test_view_without_guests_perm_hides_phone(supervisor_without_guests_client): ...
    # ответ GET /guests/{id} без stays.guests → 403; список /guests?q= не содержит phone, birth_date
def test_guest_update_audited_with_diff(manager_client, db): ...
    # payload {"before": {"level": "regular"}, "after": {"level": "vip"}}
```

- [ ] **Шаг 2.** FAIL. **Шаг 3.** Реализация. **Шаг 4.** PASS (SQLite и PG). **Шаг 5.** Коммит.

### Задача 8: Брони — документ брони, состав, группы, статусы, no-show, версии

**Файлы:**
- Создать: `app/modules/stays/application/reservations.py`, `application/allocation.py`,
  `interface/reservations_api.py`
- Тест: `tests/stays/test_reservations_api.py`, `tests/stays/test_allocation.py`

**Интерфейсы:**
- Потребляет: `segments`, `validate_dates` (задача 5), `allocate` (задача 6).
- Даёт (application):
  * `class ReservationError(Exception)`, `class ReservationConflict(ReservationError)`
    (→ 409 «Бронь изменилась — обновите»), `class ReservationInvalid(ReservationError)` (→ 422);
  * `OCCUPYING = {"tentative", "confirmed", "in_house", "checked_out"}` — статусы,
    которые занимают объект;
  * `save_reservation(db, doc: ReservationDoc, rid: int | None, expected_version: int | None)
    -> Reservation` — документ целиком: поля брони, `moves`, `occupants`, `companions`,
    `logistics`, `group_id`, `pins: dict[int, int | None]`; увеличивает `version`;
    проверки: даты (задача 5); даты проживающих в пределах брони; на каждую дату брони
    ровно один `main` (иначе 422 «На DD.MM нет главного гостя» / «…два главных гостя»);
    в одной группе переезды всех броней совпадают (422 «В группе совместного проживания
    переезды должны совпадать»);
  * `set_status(db, rid: int, status: str, expected_version: int, new_check_in: date | None)
    -> Reservation` — `no_show` только если `local_date() >= check_in`
    (422 «Отметить «не заехал» можно с даты заезда»); возврат из `no_show` в
    `confirmed` требует `new_check_in`;
  * `reservation_diff(before: dict, after: dict) -> dict` — `{поле: [было, стало]}` по
    плоскому снимку `reservation_snapshot(db, r) -> dict` (поля, объект по сегментам,
    состав, статус);
  * `run_allocation(db) -> list[AllocWarning]` (`allocation.py`): читает объекты, блоки,
    брони со статусом из `OCCUPYING`, переезды, закрепления; группа совместного
    проживания — один `AllocItem` с датами-оболочкой (мин. заезд с РЗ, макс. выезд с ПВ)
    и переездами группы, в группу входят только её занимающие брони (если все её брони
    `no_show`/`cancelled`, группа объект не занимает); результат записывается в
    `stays_assignments` (членам группы — тот же объект). Вызывается после каждой
    операции, меняющей доступность: брони, статуса, блока, объекта.
  * `save_hold(db, data, hid) -> Hold`, `delete_hold(db, hid)` (здесь же: влияют на
    распределение).
- Даёт (HTTP): `POST /reservations`, `GET|PUT /reservations/{id}`,
  `POST /reservations/{id}/status`, `POST /groups`, `POST|PUT|DELETE /holds[/{id}]` —
  `stays.edit`; аудит `stays_reservation` (`{"diff": …}`), `stays_reservation_status`,
  `stays_hold`. Параметр `?preview=1` появится в задаче 9 — здесь роутеры уже вызывают
  операции через функцию `apply(...)`, которую задача 9 обернёт.

- [ ] **Шаг 1. Тесты:**

```python
def test_create_reservation_gets_unit(manager_client): ...
def test_two_mains_same_day_refused(manager_client): ...     # 422 с датой в тексте
def test_main_guest_changes_midstay(manager_client): ...
    # main A 10–14, main B 14–18 → OK; GET показывает обоих с датами
def test_occupant_outside_dates_refused(manager_client): ... # 422
def test_stale_version_conflict(manager_client): ...         # PUT с version-1 → 409 «Бронь изменилась — обновите»
def test_cancel_frees_unit(manager_client, db): ...          # назначения брони исчезают, объект отдан другой
def test_no_show_before_check_in_refused(manager_client, freeze): ...
def test_no_show_frees_unit_and_return_with_new_date(manager_client, freeze): ...
def test_group_one_unit(manager_client): ...                 # две брони одной группы — один объект, без конфликта
def test_group_no_show_one_of_two_keeps_unit(manager_client, freeze): ...   # «На что смотреть» №5
def test_group_moves_must_match(manager_client): ...         # 422
def test_hold_triggers_reallocation(manager_client): ...     # OOO на объект → бронь переехала в другой
def test_reservation_audit_has_diff(manager_client, db): ... # payload["diff"]["check_out"] == ["2026-11-05","2026-11-07"]
```

- [ ] **Шаг 2.** FAIL. **Шаг 3.** Реализация. **Шаг 4.** PASS. **Шаг 5.** Коммит.

### Задача 9: Предпросмотр «что будет, если» для операций броней

**Файлы:**
- Создать: `app/modules/stays/application/preview.py`
- Изменить: `interface/reservations_api.py` (все изменяющие маршруты задачи 8 принимают
  `preview: bool = Query(False)`)
- Тест: `tests/stays/test_preview.py`

**Интерфейсы:**
- Даёт:
  * `@dataclass(frozen=True) Snapshot(units: dict[tuple[int, int], int | None],
    warnings: frozenset[WarningKey], coverage: dict[tuple[date, int], frozenset[int]],
    loads: dict[tuple[int, date], float])` — `units`: `(reservation_id, seg_index) → unit_id`;
    `coverage`: `(day, occupant_id) → employee_ids`; `WarningKey = tuple[str, date | None,
    int | None, int | None]` (вид, день, батлер, бронь);
  * `take_snapshot(db, first: date, last: date, duty: DutyPort | None) -> Snapshot` —
    в этапе 2 `duty=None` и снимок содержит только `units` и предупреждения
    распределения; задача 14 добавляет покрытие и нагрузку;
  * `diff(before: Snapshot, after: Snapshot) -> PreviewDiff` —
    `moved: list[{reservation_id, seg_index, from_unit, to_unit}]` (включая **другие**
    брони, сдвинутые распределением), `warnings_added`, `warnings_removed`,
    `coverage_changes: list[{day, employee_id, gained: [occupant_id], lost: [occupant_id]}]`,
    `load_changes: list[{employee_id, day, before, after, limit}]`;
  * `run_operation(db, op: Callable[[], T], window: tuple[date, date], preview: bool,
    duty: DutyPort | None = None) -> tuple[T, PreviewDiff]` — снимок до →
    `db.begin_nested()` → `op()` → `db.flush()` → снимок после → при `preview`
    `rollback()` SAVEPOINT, иначе выход из SAVEPOINT с сохранением (commit — в роутере,
    как везде в проекте). Окно: объединение старых и новых дат брони, вычисляет роутер.
    Аудит пишется внутри `op`, поэтому откатывается вместе с ней.
- HTTP-ответ изменяющих маршрутов: `{"preview": bool, "result": …, "diff": …}`; `diff`
  сериализуется по уровню видимости (задача 10: номера броней и названия объектов,
  без ПД у `occupancy`).

- [ ] **Шаг 1. Тесты:**

```python
@pytest.mark.parametrize("op", ["move_dates", "pin_other_unit", "add_move", "cancel",
                                "no_show", "join_group", "add_ooo"])
def test_preview_equals_save(manager_client, op, db):
    before = dump_stays_tables(db)                 # все строки stays_* и число строк аудита
    pv = call(op, preview=True).json()
    assert dump_stays_tables(db) == before         # ничего не записано, аудит тоже
    sv = call(op, preview=False).json()
    assert pv["diff"] == sv["diff"]

def test_preview_shows_other_reservation_shift(manager_client): ...
    # продление брони A на день вытесняет B из 4003 в 4004: diff.moved содержит B 4003→4004
def test_preview_stale_version_409(manager_client): ...   # «На что смотреть» №1
def test_preview_validation_error_same_as_save(manager_client): ...  # 422 одинаковый текст
```

- [ ] **Шаг 2.** FAIL. **Шаг 3.** Реализация. **Шаг 4.** PASS на SQLite и PG (SAVEPOINT
  на обоих диалектах). **Шаг 5.** Global Gate, CHANGELOG этапа 2, коммит.

---

## Этап 3. Шахматка объектов и карточки

### Задача 10: Чтение шахматки объектов, уровни видимости, карточки и история

**Файлы:**
- Создать: `application/visibility.py`, `application/views.py` (функция шахматки
  объектов), `application/history.py`, `interface/views_api.py`
- Тест: `tests/stays/test_units_board.py`, `tests/stays/test_history.py`

**Интерфейсы:**
- Даёт:
  * `Level = Literal["occupancy", "names", "full"]`;
    `level_for(principal) -> Level | None` — `full` при `stays.guests`, `names` при
    `stays.view`, `occupancy` при `stays.occupancy`, иначе `None` (→ 403);
  * `serialize_reservation_bar(r, level: Level, coverage_names: list[str]) -> dict` —
    `occupancy`: `id, status, check_in, check_out, early, late, guests_count, segments`
    (+ `unit_id`), без номера брони, метки, фамилий, уровня, примечаний;
    `names`: + `number, label, main_guest_short ("Орлов А."), level, butlers_today`;
    `full`: + `customer, purpose, note, declined_butler, fields`;
  * `units_board(db, first: date, last: date, filters: BoardFilters, level: Level)
    -> dict` — `{"units": [...], "bars": [...], "holds": [...], "warnings": [...],
    "days": [...]}`; `BoardFilters(kind, building, floor, category_id, escorted_only,
    level_vip, employee_id, q)`; для `occupancy` фильтры `q`, VIP и батлер игнорируются;
  * `reservation_card(db, rid, level) -> dict` (состав по датам, сопровождающие,
    логистика, объекты по сегментам; покрытие по дням появится в задаче 14);
  * `guest_card(db, gid) -> dict` (профиль, связи, настраиваемые поля);
  * `reservation_history(db, rid) -> list[{ts, actor, action, diff}]` — из `AuditLog`
    по `target == f"reservation:{rid}"`;
  * `guest_stays(db, gid) -> list[{reservation_id, number, unit_labels, date_from,
    date_to, role, butlers}]` — по `Occupant` (в задаче 14 `butlers` заполняется из
    покрытия; до тех пор пустой список).
- HTTP: `GET /board/units?first&last&…`, `GET /reservations/{id}/card`,
  `GET /reservations/{id}/history`, `GET /guests/{id}/card`, `GET /guests/{id}/stays`.

- [ ] **Шаг 1. Тесты:**

```python
def test_board_level_names_has_surname_no_phone(supervisor_client, demo_small): ...
def test_board_level_occupancy_no_guest_fields(occupancy_client, demo_small):
    body = occupancy_client.get("/api/stays/board/units?first=…&last=…").text
    for surname in demo_small.surnames:
        assert surname not in body
    assert '"number"' not in body and '"note"' not in body
def test_board_query_budget_440_units(manager_client, big_fund, sql_counter): ...  # ≤ 30
def test_board_filters_building_and_escorted(manager_client, big_fund): ...
def test_history_shows_field_diff(manager_client): ...
def test_guest_stays_across_reservations(manager_client): ...
```

Фикстуры `demo_small` (5 объектов, 6 гостей, 4 брони) и `big_fund` (440 объектов,
~300 броней на 31 день) — в `tests/stays/conftest.py`; `occupancy_client` и
`mgmt_client` — пользователи с ролями `occupancy` и `mgmt_view` из ревизии 0008.

- [ ] **Шаг 2.** FAIL. **Шаг 3.** Реализация (загрузка пакетами: объекты, брони диапазона,
  переезды, назначения, проживающие, гости — по одному запросу). **Шаг 4.** PASS.
  **Шаг 5.** Коммит.

### Задача 11: Интерфейс — шахматка объектов, карточки, формы с предпросмотром

**Файлы:**
- Создать: `static/js/modules/stays.js`, `static/js/modules/stays_forms.js`
- Изменить: `static/css/app.css`; `bump_version.py`, `gen_js_globals.py`
- Тест: `tools/stays_scenario.mjs`, `tools/run_stays_scenario.sh` (по образцу
  `run_settings_scenario.sh`, порт 8146, база `/tmp/stays_scenario.db`)

**Интерфейсы:**
- Потребляет: HTTP задач 8–10.
- Даёт: `registerModule({ views: { stays: loadStays } })`; в `stays.js` — вкладки
  «Объекты / Батлеры / Табло дня / Загрузка» (вкладки 2–4 наполняет задача 16),
  `staysState`, `ordinal(y, m, d)` = `Math.round(Date.UTC(y, m-1, d)/86400000) + 719163`
  (PoC §5.1), `renderUnitsBoard()`; в `stays_forms.js` —
  `openReservationForm(id | null)`, `openGuestForm(id | null)`,
  `renderPreview(diff, el)` и `previewThenSave(url, method, body)`: первый вызов с
  `?preview=1` рисует картину (сдвиги объектов, новые и исчезнувшие предупреждения,
  дельта покрытия), кнопка «Сохранить» отправляет тот же `body` без `preview`.
  Действие «Перенести» на полосе — диалог выбора объекта или категории → тот же
  `previewThenSave`.

- [ ] **Шаг 1. Сценарий:** создать бронь формой → предпросмотр показывает объект →
  сохранить → полоса на шахматке; продлить бронь, вытесняющую другую, — предпросмотр
  называет вытесненную; 409 при устаревшей версии показывает «Бронь изменилась —
  обновите»; карточка брони показывает ленту изменений. Тест `ordinal` против
  `date.toordinal()` для 10 дат (PoC §11).
- [ ] **Шаг 2.** FAIL. **Шаг 3.** Реализация (CSS-сетка: колонка на половинку суток,
  виртуализация не нужна — фильтры сужают выдачу; на 440 строк прокрутка проверяется
  сценарием по времени отрисовки < 1 с в jsdom). **Шаг 4.** PASS, `npm run lint`.
- [ ] **Шаг 5.** Global Gate, CHANGELOG этапа 3, коммит.

---

## Этап 4. Покрытие батлерами

### Задача 12: Публичный запрос Графика «смены и отсутствия на даты»

**Файлы:**
- Создать: `app/modules/timesheet/application/roster.py`,
  `app/modules/stays/ports/duty.py`, `app/modules/stays/adapters/duty_timesheet.py`
- Изменить: `app/modules/timesheet/ports/{shift,absence,timesheet}.py` и их SQL-адаптеры
  (пакетные методы), `app/modules/timesheet/application/schedule_view.py` (функция ручной
  смены по пресету), `app/modules/timesheet/interface/schedule.py:421-468`
  (`put_manual_shift` вызывает новую функцию для ветки с `shift_type_id`)
- Тест: `tests/test_roster.py`, `tests/stays/test_duty_adapter.py`

**Интерфейсы:**
- Даёт (timesheet):
  * порты: `ShiftPort.shifts_for(employee_ids: Sequence[str], period: Period) -> Sequence[Shift]`,
    `AbsencePort.absences_for(...) -> Sequence[Absence]`,
    `TimesheetPort.days_for(employee_ids, period) -> Sequence[Day]` — по одному запросу
    (`IN` по сотрудникам, окно дат как в `_window`);
  * `@dataclass(frozen=True) RosterDay(on_shift: bool, tabel_code: str | None,
    absence_minutes: int)`;
  * `roster(employee_ids: Sequence[int], first: date, last: date, ports: EnginePorts)
    -> dict[tuple[int, date], RosterDay]` — `on_shift`: есть смена Графика с локальной
    датой начала = день; `absence_minutes`: сумма согласованных отсутствий, пересекающих
    смену дня; ровно 3 SQL-запроса независимо от числа сотрудников и дней;
  * `schedule_view.preset_shifts(employee_id: str, day: date, shift_type: ShiftType, tz)
    -> list[Shift]` и использование в `put_manual_shift` (поведение маршрута не меняется,
    существующие тесты Графика — зелёные).
- Даёт (stays): `DutyDay(on_shift: bool, code: str | None, partial_absence: bool)`;
  `class DutyPort(Protocol): def duty(self, employee_ids: Sequence[int], first: date,
  last: date) -> Mapping[tuple[int, date], DutyDay]`; `TimesheetDuty(db)` — адаптер,
  отсутствующий ключ = `DutyDay(False, None, False)`.

- [ ] **Шаг 1. Тесты:**

```python
def test_roster_three_queries(db, sql_counter, staff_20):
    with sql_counter() as n:
        roster(ids, date(2026,11,1), date(2026,11,30), engine_ports(db))
    assert n.count <= 3 + SETTINGS_QUERIES   # SETTINGS_QUERIES — как в test_query_budget
def test_roster_vacation_code_no_shift(db): ...   # ОТ через range-absence → on_shift False, tabel_code "ОТ"
def test_roster_night_shift_anchor_day(db): ...   # 20:00–08:00 → on_shift только в день начала
def test_put_manual_shift_preset_unchanged(manager_client): ...  # прежний ответ и аудит
```

- [ ] **Шаг 2.** FAIL. **Шаг 3.** Реализация. **Шаг 4.** PASS + весь `tests/engine` и
  `tests/test_query_budget.py`. **Шаг 5.** Коммит «График: публичный запрос смен на даты».

### Задача 13: Домен — покрытие, нагрузка, предупреждения, подбор

**Файлы:**
- Создать: `domain/coverage.py`, `domain/load.py`, `domain/warnings.py`,
  `domain/candidates.py` (типы — в `domain/types.py`)
- Тест: `tests/stays/test_coverage_domain.py`

**Интерфейсы:**
- Потребляет: `DutyDay` (задача 12; домен получает его как значение, порт не знает).
- Даёт:
  * `StayDay(day, reservation_id, group_id: int | None, unit_id: int | None,
    building: str, weight: float, escorted: bool, declined: bool,
    occupants: Mapping[int, GuestRef])`, `GuestRef(guest_id: int, level: str)` —
    одна бронь в один день; объект — по сегменту на PM дня, в день выезда — по AM;
  * `Line(id: int, day, employee_id, reservation_id: int | None, group_id: int | None,
    occupant_ids: frozenset[int], source: str, overnight: bool)` — пустой
    `occupant_ids` = вся бронь или группа;
  * `resolve_day(stays: Sequence[StayDay], lines: Sequence[Line]) -> DayCover` —
    `DayCover.by_occupant: dict[int, tuple[int, ...]]` (кто ведёт гостя),
    `DayCover.uncovered: dict[int, tuple[int, ...]]` (reservation_id → гости без
    батлера), `DayCover.double: list[(occupant_id, employee_ids)]`. Правило §4.2: явный
    список гостей сильнее «вся бронь/группа»; два явных на одного гостя — `double`;
  * `fill_template(kind: Literal["pair", "single"], days: Sequence[date],
    butlers: tuple[int, ...], duty: Mapping[tuple[int, date], DutyDay],
    busy_days: set[date]) -> list[tuple[date, int]]` — `pair (A, B)`: на смене A → A,
    иначе на смене B → B, иначе день пропускается (дыра); `single (X,)`: X каждый день;
    дни из `busy_days` (уже есть строки) не трогаются;
  * `day_loads(stays, cover: DayCover, vip_bonus: float, vvip_bonus: float)
    -> dict[int, float]` — §4.3: вес объекта делится поровну между батлерами, которые
    ведут гостей в объекте в этот день (по всем броням объекта); надбавка гостя —
    батлеру этого гостя, при нескольких — поровну; округление до 0.01 при выводе, не
    при счёте;
  * `day_warnings(day, stays, lines, cover, loads, duty, limit: float,
    replacement_codes: frozenset[str], alloc_warnings) -> list[Warning]`;
    `Warning(kind, day, employee_id, reservation_id, unit_id, text)`, `kind` ∈
    `hole` («Вилла 4003: гости без батлера»), `need_replacement` («Петров: ОТ —
    нужна подмена»), `off_shift` («Петров вне смены — переработка»), `overload`
    («Петров: 10 из 8»), `double_cover`, `unassigned_unit`, `late_vs_arrival`.
    При коде дня из `replacement_codes` выдаётся `need_replacement` и **не**
    выдаётся `off_shift`. `hole` не выдаётся при `declined` или `escorted=False`;
  * `rank_candidates(day, occupant_guest_ids: set[int], unit_id, building,
    escorts: Sequence[int], duty, loads: Mapping[int, float], add_weight: float,
    limit: float, known: Mapping[int, set[int]], places: Mapping[int, set[tuple[str, int]]],
    replacement_codes) -> list[Candidate]`; `Candidate(employee_id, knows_guest: bool,
    same_place: bool, load_after: float, note: str)`. Фильтры: на смене, код дня не из
    `replacement_codes`, `load_after <= limit`. Порядок: `knows_guest` ↓, `same_place` ↓
    (тот же объект или корпус), `load_after` ↑, `employee_id` ↑. `partial_absence` не
    исключает, а даёт `note` «есть отлучка в смене».

- [ ] **Шаг 1. Тесты:**

```python
def test_pair_template_follows_shifts(): ...   # A на смене пн, B вт, никто ср → [(пн,A),(вт,B)], ср — дыра
def test_pair_both_on_shift_takes_a(): ...
def test_template_keeps_manual_days(): ...
def test_explicit_guests_override_whole_booking(): ...
    # X — вся бронь, Y — [супруга] → by_occupant: глава→X, супруга→Y
def test_double_explicit_warns(): ...
def test_move_day_butler_follows_guest(): ...  # «На что смотреть» №2: StayDay в день переезда несёт новый unit, вес один раз
def test_weight_split_and_vip_bonus(): ...
    # вилла вес 4, X ведёт главного VVIP, Y — семью: X = 2 + 2, Y = 2
def test_vacation_is_replacement_not_off_shift(): ...   # «На что смотреть» №3, доменная часть
def test_declined_no_hole(): ...
def test_candidates_order_knows_guest_first(): ...
def test_candidates_exclude_overload_and_absent(): ...
```

- [ ] **Шаг 2.** FAIL. **Шаг 3.** Реализация. **Шаг 4.** PASS. **Шаг 5.** Коммит.

### Задача 14: Покрытие — операции, API, «добавить смену», подбор, дельта в предпросмотре

**Файлы:**
- Создать: `application/context.py`, `application/coverage.py`, `interface/coverage_api.py`
- Изменить: `application/preview.py` (`take_snapshot` с `duty`), `application/reservations.py`
  (чистка строк после изменения дат, статуса, состава), `application/views.py`
  (`butlers_today` на полосах), `application/history.py` (`butlers` в `guest_stays`),
  `reservation_card` (покрытие по дням)
- Тест: `tests/stays/test_coverage_api.py`

**Интерфейсы:**
- Потребляет: задачи 9, 12, 13.
- Даёт:
  * `load_context(db, first: date, last: date, duty: DutyPort) -> StaysContext` —
    пакетно: брони диапазона, сегменты, назначения, проживающие с уровнями гостей,
    категории, строки покрытия с гостями, «сопровождают гостей», настройки, Duty;
    методы `stays_on(day) -> list[StayDay]`, `lines_on(day) -> list[Line]`,
    `cover(day) -> DayCover`, `loads(day) -> dict[int, float]`,
    `warnings(day) -> list[Warning]`. Все виды и предпросмотр читают только через него;
  * `apply_template(db, principal, scope: Scope, kind, butlers, first, last, replace: bool)
    -> int`; `Scope(reservation_id | group_id, occupant_ids: frozenset[int])`;
  * `set_day(db, principal, day, scope, employee_id, overnight, comment) -> CoverageLine`;
    `delete_line(db, principal, line_id)`;
  * `cleanup_lines(db, principal, reservation_id) -> int` — удаляет строки на дни, где
    гостей брони уже нет (даты, отмена, no-show, состав), аудит `stays_coverage_cleanup`
    с перечнем удалённых дней; вызывается из `save_reservation` и `set_status`;
  * `candidates(db, day, scope) -> list[Candidate]` (`known` — из истории проживаний:
    батлеры, которые раньше вели любого из гостей scope);
  * `replacement_list(db, first, last) -> list[{day, employee_id, reservation_id, code,
    candidates}]`;
  * `add_shift(db, principal, employee_id, day, shift_type_id) -> None` — требует у
    `principal` и `stays.assign`, и `schedule.edit` (иначе 403 «Нужно право на правку
    Графика»), пишет ручную смену через `schedule_view.preset_shifts` +
    `save_schedule_day`, аудит `schedule_manual_shift` (как маршрут Графика) и
    `stays_add_shift`.
- HTTP (`stays.assign`, все изменяющие — с `?preview=1` через `run_operation`):
  `POST /coverage/template`, `PUT /coverage/day`, `DELETE /coverage/{id}`,
  `GET /coverage/candidates?day&reservation_id&group_id&occupant_ids`,
  `GET /coverage/replacements?first&last`, `POST /coverage/add-shift`.

- [ ] **Шаг 1. Тесты:**

```python
def test_template_pair_by_schedule(manager_client, two_butlers_2x2): ...
def test_off_shift_warning_and_add_shift(manager_client, ...):
    # single X на 5 дней, 2 вне смены → предупреждения off_shift;
    # add-shift на один день → следующий GET доски: off_shift остался на одном дне;
    # в аудите есть schedule_manual_shift и stays_add_shift; tabel_days не изменились
def test_add_shift_requires_schedule_edit(client_with_assign_only): ...   # 403
def test_schedule_change_seen_on_next_read(manager_client): ...
    # отменили смену в Графике (DELETE ручной смены) → off_shift без действий в шахматке
def test_vacation_in_schedule_gives_replacement(manager_client): ...   # «На что смотреть» №3
def test_cleanup_on_early_checkout(manager_client, db): ...   # строки после нового выезда удалены + аудит
def test_no_show_removes_coverage(manager_client, freeze): ...
def test_preview_coverage_delta_on_butler_swap(manager_client): ...
    # замена X→Y на 3 дня: coverage_changes X lost, Y gained; load_changes по дням
def test_preview_equals_save_coverage_ops(manager_client): ...   # для template, set_day, delete
def test_candidates_known_guest_first(manager_client): ...
```

- [ ] **Шаг 2.** FAIL. **Шаг 3.** Реализация. **Шаг 4.** PASS (SQLite и PG).
- [ ] **Шаг 5.** Global Gate, CHANGELOG этапа 4, коммит.

---

## Этап 5. Шахматка батлеров и табло дня

### Задача 15: Чтение шахматки батлеров и табло дня

**Файлы:**
- Изменить: `application/views.py`, `interface/views_api.py`
- Тест: `tests/stays/test_butlers_board.py`, `tests/stays/test_day_board.py`

**Интерфейсы:**
- Потребляет: `load_context` (задача 14), `serialize_*` (задача 10).
- Даёт:
  * `butlers_board(db, first, last, duty) -> dict` — строки «сопровождают гостей»;
    ячейка `{day, duty: "shift" | "off" | "absent", code, units: [label], guests:
    [short], load, limit, warnings: [kind]}`; только для `names` и `full` (у
    `occupancy` — 403);
  * `day_board(db, day, level, filters) -> dict` — итоги `{arrivals, departures,
    in_house, covered, uncovered, need_replacement, not_required, vip, vvip, no_show}`;
    списки `arrivals`, `departures`, `in_house`, `attention`, `no_show` (брони
    `no_show` с заездом в этот день); строка: `time` («РЗ 09:00» / «14:00» / «ПВ»),
    `unit`, `guests` (главный + остальные, по уровню), `cover_status` ∈ `covered` (с
    парами «батлер — кого»), `uncovered` (+ кандидаты), `replacement` (+ кандидаты),
    `declined`, `not_required`; `details` (логистика, сопровождающие, аллергии из
    предпочтений, повод) — только `full`. Для `occupancy` — строки без гостей и
    деталей, `cover_status` не отдаётся.
- HTTP: `GET /board/butlers?first&last`, `GET /day?date&escorted_only&vip&employee_id&q`.

- [ ] **Шаг 1. Тесты:**

```python
def test_butlers_board_shift_background(manager_client, two_butlers_2x2): ...
def test_butlers_board_overload_red(manager_client): ...
def test_day_board_totals(manager_client, demo_small): ...   # точные числа для фикстуры
def test_day_board_no_show_group(manager_client, freeze): ...
def test_day_board_vacation_shows_replacement(manager_client): ...  # «На что смотреть» №3, API
def test_query_budgets_440(manager_client, big_fund, sql_counter):
    for url in ("/api/stays/board/butlers?…", "/api/stays/day?date=…"):
        ...  # ≤ 30 запросов
```

- [ ] **Шаг 2.** FAIL. **Шаг 3.** Реализация. **Шаг 4.** PASS. **Шаг 5.** Коммит.

### Задача 16: Интерфейс — шахматка батлеров, табло дня, форма назначения

**Файлы:**
- Создать: `static/js/modules/stays_board.js`
- Изменить: `stays.js` (вкладки), `stays_forms.js` (`openCoverageForm(scope, day)` —
  шаблон «пара посменно / один на весь срок / вручную», подбор с кандидатами, кнопка
  «Добавить смену в График» у предупреждения `off_shift`), `app.css`
- Тест: `tools/stays_scenario.mjs`

**Интерфейсы:**
- Потребляет: HTTP задач 14–15.
- Даёт: `renderButlersBoard()`, `renderDayBoard()` (◀ ▶ «Сегодня», вкладки «Заезды /
  Выезды / Проживают / Требуют внимания», группа «Не заехали», фильтры), разметка табло
  в одну колонку при ширине < 640px.

- [ ] **Шаг 1. Сценарий:** назначить шаблоном «один на весь срок» → на шахматке
  батлеров красные дни «вне смены» → «Добавить смену» → предупреждение исчезло → табло
  дня показывает «Смирнова — Орлов». Клик по пустому дню батлера открывает назначение.
- [ ] **Шаг 2.** FAIL. **Шаг 3.** Реализация. **Шаг 4.** PASS, `npm run lint`.
- [ ] **Шаг 5.** Global Gate, CHANGELOG этапа 5, коммит.

---

## Этап 6. Загрузка, «Мои гости», обезличенный уровень, выгрузки, демо

### Задача 17: Сводная загрузка, «Мои гости», правка своих броней, проверка утечек ПД

**Файлы:**
- Изменить: `application/views.py`, `application/visibility.py`,
  `application/reservations.py`, `application/guests.py`, `interface/*.py`
- Тест: `tests/stays/test_occupancy_and_mine.py`, `tests/stays/test_pd_leaks.py`

**Интерфейсы:**
- Даёт:
  * `occupancy_grid(db, first, last, building: str | None) -> dict` — категории × дни:
    `{busy, total, arrivals, departures, no_show}`; доступно на всех трёх уровнях;
  * `owns_reservation(db, employee_id: int, reservation_id: int, today: date) -> bool`
    — есть строка покрытия батлера по этой брони (напрямую, через группу или гостей)
    на дни `[today − 1, today + 7]` (§1 «Допущения»);
  * `MINE_FIELDS = {"occupants", "companions", "logistics", "note", "fields"}` и для
    гостей `{"preferences", "special_dates", "links", "fields", "note"}`; правка с
    `stays.edit_mine` без `stays.edit`: изменение любого другого поля → 403 «Батлер
    может менять только состав, логистику и сведения о гостях»; новые проживающие —
    только в пределах дат брони, роль `main` менять нельзя;
  * `my_guests(db, employee_id, today) -> dict` — дни `today … today+7` и вчера; гости
    с предпочтениями, особыми датами, логистикой (уровень `full` только по своим);
  * `assert_no_pd(obj, surnames: set[str])` — тестовый помощник в
    `tests/stays/conftest.py`: обходит весь JSON.
- HTTP: `GET /occupancy?first&last&building`, `GET /mine`; `PUT /reservations/{id}` и
  `PUT /guests/{id}` принимают `stays.edit_mine` с проверкой владения.

- [ ] **Шаг 1. Тесты:**

```python
def test_occupancy_grid_counts(manager_client, demo_small): ...
def test_butler_edits_own_reservation_logistics(butler_client): ...         # 200
def test_butler_cannot_change_dates(butler_client): ...                      # 403 с текстом
def test_butler_cannot_edit_foreign_reservation(butler_client): ...          # 403
def test_butler_sees_yesterday_departed_guest(butler_client, freeze): ...
def test_mine_lists_only_own(butler_client): ...
@pytest.mark.parametrize("url", ALL_STAYS_GET_URLS)       # собирается из app.routes по префиксу /api/stays
def test_occupancy_level_never_sees_guests(occupancy_client, demo_small, url):
    r = occupancy_client.get(fill(url))
    if r.status_code == 200:
        assert_no_pd(r.json(), demo_small.surnames)       # «На что смотреть» №4
def test_preview_diff_has_no_pd_for_occupancy(...): ...   # дельта и тексты предупреждений
def test_role_matrix(...): ...
    # менеджер, старший, батлер (своя/чужая), mgmt_view (видит гостей, не правит → 403 на PUT),
    # occupancy (403 на /guests, /board/butlers, /mine)
```

- [ ] **Шаг 2.** FAIL. **Шаг 3.** Реализация. **Шаг 4.** PASS. **Шаг 5.** Коммит.

### Задача 18: Выгрузка в Excel — полная и обезличенная

**Файлы:**
- Создать: `application/export.py`, `interface/export_api.py`
- Тест: `tests/stays/test_export.py`

**Интерфейсы:**
- Даёт: `export_xlsx(db, first: date, last: date, kind: Literal["full", "anon"]) -> bytes`
  — лист «Шахматка» (объекты × дни, ячейка: `full` — фамилия главного гостя, `anon` —
  «занято»), лист «Брони» (`anon`: объект, категория, заезд, выезд, статус, число гостей;
  `full`: + номер, гости, уровень, метка, батлеры по дням, логистика), лист «Сводка»
  (сводная загрузка, no-show). Значения, начинающиеся с `= + - @`, экранируются
  апострофом (как в существующих выгрузках проекта).
- HTTP: `GET /export?first&last&kind` — `anon`: `stays.occupancy` или `stays.view`;
  `full`: `stays.export` **и** `stays.guests`; аудит `stays_export` с `{kind, first, last}`.

- [ ] **Шаг 1. Тесты:** `anon` под `occupancy` → 200, ни одной фамилии демо-гостей в
  ячейках; `full` под старшим → 403; `full` под менеджером → фамилии есть; формула в
  примечании экранирована; запись в аудите.
- [ ] **Шаг 2.** FAIL. **Шаг 3.** Реализация + кнопки «Выгрузить» на вкладках
  (`stays.js`). **Шаг 4.** PASS. **Шаг 5.** Коммит.

### Задача 19: Демо-данные

**Файлы:**
- Создать: `app/modules/stays/application/demo.py`
- Изменить: `app/bootstrap/seed.py` (вызов `seed_stays_demo(db, by_name)` при демо-сиде,
  рядом с `_seed_cars`)
- Тест: `tests/stays/test_demo.py`

**Интерфейсы:**
- Даёт: `seed_stays_demo(db, employees_by_name: dict) -> None` — идемпотентно (если
  категории уже есть — выход). Фонд §11: категории вилл (VEG, FWV, VIG — вес 4),
  имение (ESTATE — 6), апартаменты (MED — 3), 6 категорий номеров (вес 1, «с
  сопровождением» только у двух люксовых); 37 вилл, имение, 2 апартамента, 400 номеров
  в корпусах «1» и «2»; ~60 вымышленных гостей (из них 8 VIP и 2 VVIP, связи
  «семья», «ассистент», «охрана»); брони на 30 дней от `local_date()`, среди них
  совместная, с переездом, со сменой главного, с отказом от батлера, no-show; «сопровождают
  гостей» — демо-сотрудники с должностью «батлер»; покрытие шаблонами с одним
  перегрузом, одним днём «вне смены» и одним «нужна подмена» (код ОТ в Табеле
  демо-сотрудника через существующий сид Табеля).

- [ ] **Шаг 1. Тесты:** после `seed_if_empty` с `DEMO_SEED=1` — 440 объектов, есть
  каждое из предупреждений `overload`, `off_shift`, `need_replacement`; повторный вызов
  не дублирует; `tests/test_bootstrap_seed.py` зелёный.
- [ ] **Шаг 2.** FAIL. **Шаг 3.** Реализация. **Шаг 4.** PASS. **Шаг 5.** Коммит.

### Задача 20: UI-сценарий, смоук под ролями, документация, выпуск

**Файлы:**
- Изменить: `tools/stays_scenario.mjs`, `tools/run_stays_scenario.sh`,
  `tools/run_ui_check.sh` (вызов сценария шахматки), `.github/workflows/*.yml` (шаг
  сценария рядом с остальными `run_*_scenario.sh`), `README.md` (раздел модуля),
  `docs/architecture/ARCHITECTURE.md` (модуль в списке), `CHANGELOG.md`
- Изменить: `static/js/modules/stays_board.js` — «Мои гости»: `renderMine()` (карточки
  гостей на телефон, правка своей брони через `openReservationForm(id, {mine: true})`,
  где заблокированы даты, объект, статус и назначения) и вид `stays-mine` в
  `registerModule`

**Интерфейсы:**
- Потребляет: всё выше.

- [ ] **Шаг 1. Сценарий целиком (§10 «Интерфейс»):** под менеджером — бронь →
  назначение шаблоном → конфликт «вне смены» → «Добавить смену» → табло дня; под
  батлером — «Мои гости», правка логистики своей брони, отказ при правке чужой; смоук:
  каждая вкладка открывается без ошибок консоли под `admin`, `manager`, `supervisor`,
  `employee`, `mgmt_view`, `occupancy` (у `occupancy` на шахматке нет фамилий в DOM).
- [ ] **Шаг 2. Запуск** `tools/run_stays_scenario.sh` → FAIL до `renderMine`, затем PASS.
- [ ] **Шаг 3. Документация:** README — что умеет модуль и права; `doc_links.py` зелёный.
- [ ] **Шаг 4. Global Gate** на SQLite и PG; `export_openapi.py --check`.
- [ ] **Шаг 5.** CHANGELOG этапа 6, коммит, после просьбы владельца — push ветки
  `feat/stays-chessboard` и описание PR (буфер обмена, `LANG/LC_ALL=en_US.UTF-8`).

---

## Покрытие спецификации

| Раздел спецификации | Задачи |
|---|---|
| §3.1 фонд, §3.5 настройки и поля | 2, 3, 4 |
| §3.2 гости и связи | 2, 7 |
| §3.3 брони, состав, группы, переезды | 2, 8 |
| §3.4 покрытие, «сопровождают гостей» | 2, 3, 14 |
| §3.6 история | 10, 14 |
| §4.1 сегменты и распределение | 5, 6, 8 |
| §4.2 шаблоны, пересечение охватов | 13, 14 |
| §4.3 нагрузка | 13 |
| §4.4 предупреждения при чтении | 13, 14, 15 |
| §4.5 подбор и подмена | 13, 14 |
| §4.6 предпросмотр | 9, 14, 11, 16 |
| §4.7 no-show | 8, 14, 15 |
| §5 связь с Графиком и аудитом | 12, 14 |
| §6 экраны 1–6 и формы | 4, 11, 16, 17, 20 |
| §7 права и роли | 1, 2, 17 |
| §8 уровни ПД, выгрузки | 10, 17, 18 |
| §9 409 при конфликте версий | 8, 9 |
| §10 тесты | все; бюджеты SQL — 10, 15 |
| §11 демо | 19 |
