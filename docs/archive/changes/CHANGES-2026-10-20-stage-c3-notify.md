# Изменения 20.10.2026 — этап C, фаза C3: модуль `notify/` (эталон)

Исполнение `docs/archive/EXECUTION-SPEC-v2.md` (фаза 5). Второй бизнес-модуль и
**эталон** целевой структуры: пять слоёв, R1–R6, публичная граница `__init__` —
всё проверено механически (новый `tests/test_notify_module.py`, 8 AST-тестов).
Поведение и контракты API не изменились (`export_openapi --check` — без дельты).

## 1. Что переехало

| Новый путь | Из чего |
|------------|---------|
| `modules/notify/domain/templates.py` | чистая половина `app/notify/templates.py`: `DEFAULT_TEMPLATES`, `DOMAIN_TITLES`, `PLACEHOLDERS`, `render_template`, `items_block` (единственный разделённый файл — по границе «чистое/БД») |
| `modules/notify/application/` | `config.py`, `dispatch.py`, `recipients.py`, `chats.py` (целиком из `app/notify/`) + БД-половина `templates.py` (`template_of`, `save_template`, `templates_payload`) |
| `modules/notify/ports/transports.py` | `TransportError` (контракт сбоя доставки) из `app/notify/transports/__init__.py` |
| `modules/notify/adapters/transports/` | `email.py` (SMTP/Exchange), `telegram.py` (Bot API) — единственные выходы в сеть |
| `modules/notify/adapters/orm.py` | `app/models/notify.py` (ResponsibilityService, NotifyChat, NotifyTemplate, NotifyDispatch; FK строками, relationship нет — R6-чисто) |
| `modules/notify/interface/notify_api.py` | `app/api/notify_api.py` |
| `modules/notify/__init__.py` | публичная граница (R4): `__all__` бывшей `app/notify` сохранён один-в-один (проверяется тестом) |
| **`core/settings_store.py`** | **`Setting` из `timesheet/adapters/orm.py`** — см. §2 |

`app/notify/` и `app/models/notify.py` удалены; фасад `app/models/__init__`
ре-экспортирует классы notify (транзит, как в C2). `bootstrap/registry.py`
импортирует orm notify явно (G4).

## 2. Ключевое решение: `Setting` → `core/settings_store.py`

Таблицу `settings` (ключ-значение) читают/пишут **несколько модулей**: timesheet
(правила объекта, `schedule_helpers`), notify (учётные данные доставки),
позже docs (шаблоны документов, `doc_templates`) и settings (центр настроек).
Оставь её в `timesheet/adapters/orm.py` — эталонный notify с рождения нарушал
бы R3 (импорт чужих adapters), а в C4 то же потребовалось бы модулям docs и
settings. Решение — по прецеденту `Photo`/`core/media` (§2: «кросс-модульное
медиахранилище»): кросс-модульное key-value хранилище живёт в core. R5 не
нарушен (модель не знает о модулях), FK/relationship у Setting нет (R6 тривиально).
Импортёры: 3 файла timesheet + notify/config переписаны на `app.core.settings_store`;
легаси (`doc_templates`, `settings_api`, `night_api`, seed/миграции, тесты) —
через фасад `app.models`, без правок. Состав `engine_store` в timesheet не
изменился (TabelDay, EngineSettingsVersion, DayModifier, PeriodClosing, DeferredCarry).

## 3. Контракты и эталонная проверка

* `.importlinter` — **8 контрактов**: добавлены **notify-isolation** (эталон не
  знает legacy-приложение, composition root и чужие модули) и
  **modules-independence** (timesheet ⊥ notify — R3 механически; транзитные
  рёбра фасада `app.models` проигнорированы до C6). Транзитный контракт G3:
  `app.notify` убран из источников; добавлены исключения для legacy-потребителей
  доставки — `services/night_notify`, `api/night_api`, `night_export` → только
  `notify.application.*` (R3-легальное направление; в C4 станут night-модулем).
* `tests/test_notify_module.py` — 8 AST-проверок эталона: пять слоёв с
  `__init__`; домен чист (stdlib, без I/O и системного времени); порты — только
  stdlib/domain/core; application не импортирует interface; adapters не
  импортируют interface/application; R6 (FK строками, relationship нет);
  публичный `__all__` = поверхность бывшей `app/notify`. В C7 этот файл —
  шаблон для AST-покрытия всех модулей (DoD).
* Слои внутри notify: `dispatch`/`chats`/`recipients` (application) вызывают
  транспорты (adapters) напрямую — наследие плоского пакета; инъекция
  `bot=`/`mailer=` уже есть (тесты ею пользуются). Формальный ports-контракт
  отправителя — кандидат на C7 (сейчас в ports — только TransportError).

## 4. Тесты

* monkeypatch-мишени переехали: `app.notify.transports.telegram.http_sender` →
  `app.modules.notify.adapters.transports.telegram.http_sender`, аналогично
  `smtp_mailer`; `TransportError` — из `app.modules.notify.ports.transports`.
  Семантика проверок не менялась (подмена leaf-функций transports).
* `app.notify.*`-импорты тестов переведены на слои модуля; +8 новых (эталон).

## 5. Проверки (§7.1 — все зелёные)

* pytest день: **642 passed / 5 skipped**; «ночь» (faketime 05:30 Мск):
  **643 passed / 4 skipped**;
* ruff ✓; lint-imports **8/8** ✓; `check_api_contract` ✓;
* `export_openapi --check` — **без дельты** (156 путей);
* `bump_version --check` ✓; `gen_js_globals --check` ✓; `npm run lint` — 0 errors;
* `run_ui_check` admin + ivanov: 0 пустых разделов / 0 ошибок консоли;
* `run_settings_scenario` **76/76**; `run_night_zones_scenario` **87/87**
  (включая «Чаты и Почта»); `run_night_cars_scenario` ✓;
* реестр моделей: **45 таблиц**, состав идентичен C2 (G4).

## 6. Дальше по плану

**C4** — остальные модули по одному коммиту: employees (включая переезд
Employee/Department/… из `timesheet/adapters/orm.py` и решение по R6 для
`Punch.employee` и др. relationship), night, cars, docs (+`core/render` — G2),
settings, access, audit; в конце фазы — удаление `app/models/`, `app/services/`,
`app/api/`. Затем C5 (main.py + финальные контракты), C6 (фронтенд), C7 (доки).
