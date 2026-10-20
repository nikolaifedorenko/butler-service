# Изменения 20.10.2026 — этап C, фаза C2: модуль `timesheet/`

Исполнение `docs/EXECUTION-SPEC-v2.md` (фаза 4). Первый бизнес-модуль
модульного монолита (ADR-0010): расчётный движок v7.1, восемь табельных
роутеров, табельные хелперы и ORM-модели Табеля/Графика/движка/каталога
переехали в `app/modules/timesheet/`. Поведение приложения и контракты API
не изменились (`export_openapi --check` — без дельты, 156 путей).

## 1. Что переехало

| Новый путь | Из чего |
|------------|---------|
| `modules/timesheet/domain/` | `app/engine/domain/` (без изменений) |
| `modules/timesheet/application/` | `app/engine/application/` + `engine_common`, `punch_plan` (из `app/services/`), `base_schedule`, `tabel_fill`, `schedule_helpers`, `schedule_patterns`, `doublepay` (из корня `app/`) |
| `modules/timesheet/ports/` | `app/engine/ports/` |
| `modules/timesheet/adapters/` | `app/engine/adapters/` + **`orm.py`** — слияние `models/{directory,punch,schedule,engine_store}.py` (23 класса, тела без изменений) |
| `modules/timesheet/interface/` | `app/engine/interface/` + роутеры `tabel_api`, `mgmt_api`, `fact_api`, `presence_api`, `punches`, `doublepay`, `schedule`, `engine_settings_api` (из `app/api/`) |
| `modules/timesheet/bootstrap.py` | `app/engine_bootstrap.py` |
| `interface/formatting.py` (+`error_text`, `ERROR_TEXTS`) | `services/engine_common.domain_error_text` — тексты ошибок переехали в interface-слой (2.4: человеческие тексты только здесь) |

`schedule_patterns` помещён в **application**, не domain: файлы домена по
AST-закону (2.4) не содержат кириллицы, а там — кодовые наборы `WORK_CHARS`/
`OFF_CHARS` («р», «в», «вых») и тексты ValueError.

Фасад `app/models/__init__.py` ре-экспортирует переехавшие модели (транзитный
re-export, спека §7 фаза 4); `bootstrap/registry.py` дополнительно импортирует
`timesheet.adapters.orm` явно (G4). Число таблиц `Base.metadata` — **45, без
изменений** (сверено с main).

## 2. §5.3 — централизация ошибок движка

В `main.py` добавлены три хэндлера (текст — `timesheet.interface.error_text`,
побайтово равен бывшему `domain_error_text`):

| Исключение | Статус | Семантика |
|------------|--------|-----------|
| `ConfigError` | **409** | повреждённая конфигурация — СОСТОЯНИЕ системы; типизированный отказ вкладок, не 500 |
| `DomainError` (прочие) | **422** | невалидные входные данные запроса |
| `ApplicationError` | **409** | конфликт состояния (период закрыт, посев не в первый период, …) |

**Разрешённое противоречие спеки.** §5.3 предписывал `ConfigError → 422`, но
§11.1 требует побайтового сохранения статусов, закреплённых тестами, а тесты
фиксируют ОБА статуса для разных семантик:
`test_timesheet_norm::test_10_config_error_is_409_not_500` — 409 для вкладок
(`/api/mgmt`, `/api/tabel`, `/api/schedule`, `/api/presence/board`);
`test_v4_api::test_engine_settings_validation` — 422 для редактора настроек;
`test_features::test_03_partial_absence` — 422 для записи отсутствий
(CHK-ABSENCE-* — валидация уровня 3, «ошибка ввода», хотя и класс ConfigError).
По правилу приоритета спеки («при расхождении — более конкретный текст»)
принято: центральный хэндлер — 409; ТРИ задокументированных локальных catch
сохранены (все — `error_text`, без ручных склеек):
1. `PUT /api/engine-settings` — `ConfigError → 422` (валидация ввода);
2. `POST /api/schedule/shift` и `POST /api/schedule/absence` —
   `(DomainError, ApplicationError) → 422` (ошибка ввода записи Графика);
3. ValueError-стражи разбора параметров (R2-парсинг, не доменные ошибки) —
   в `tabel/cell` (422), `mgmt`/`presence`/`fact day_grid` (409, как раньше).

Удалено: 23 из 29 вызовов `domain_error_text` (pattern «HTTPException с
доменным текстом»); 6 вызовов в bulk-эндпоинтах (200 + `"error"` в payload —
не HTTP-ошибка) переведены на `error_text`. Суффиксы-подсказки («Исправьте в
разделе «Настройки»…») поглощены единым текстом `ConfigError` (коды CHK-* +
место правки в `config_violation_text`); тестами/openapi/фронтом не
закреплены — проверено grep'ом. `domain_error_text` удалена (DoD).

## 3. Контракты и AST-законы

* `.importlinter` — **6 контрактов**: слои legacy (api→services→models→core);
  независимость api-модулей (10 оставшихся); **timesheet-isolation** (модуль не
  знает api/services/main/bootstrap — правопреемник engine-isolation);
  R5 core-independence (список legacy-корня сокращён, добавлен `app.modules`);
  **timesheet-interface-independence** (8 роутеров не импортируют друг друга —
  правопреемник закона для уехавших); **транзитный контракт G3**: legacy
  `app.*` не импортирует `modules.*`, кроме 11 объявленных исключений (фасад
  models; `api/employees`, `api/settings_api`, `api/auth_routes`,
  `services/employee_lifecycle` — через границу `timesheet.application`,
  R3-легальное направление; строки исчезнут в C4–C6).
  Направление `modules → app-legacy` (groups, employment, doc_render, grid_docx,
  pdf_render, models.night/notify) разрешено транзитом G3 до переноса владельцев.
* `tests/engine/test_architecture.py` — префиксы и данные переведены на
  `app.modules.timesheet` (спека §7 фаза 4). В закон «application не импортирует
  adapters/interface» добавлен ТРАНЗИТ-allowlist из 6 поглощённых legacy-файлов
  (base_schedule, tabel_fill, schedule_helpers, doublepay, engine_common,
  punch_plan): им разрешены собственный `adapters` (ORM) и `app.groups`/
  `app.employment` (уедут в employees в C4 — тогда список пустеет); `app.core.*`
  разрешён всем (§3: application импортирует core). Файлы самого движка
  остались полностью чистыми — закон для них не ослаблен.

## 4. Известный долг (зафиксирован, не правится в C2)

* **Employee в `timesheet/adapters/orm.py`** — `directory.py` перенесён целиком
  (спека фаза 4 буквально); в C4 классы каталога (Employee, Department,
  Subdivision, StatementKind, EmergencyContact, PositionHistory, EmploymentPeriod)
  переедут в `modules/employees/adapters/orm.py`, после чего `relationship()`
  таймшита на Employee (Punch.employee lazy=joined и др.) станут кросс-модульными
  и потребуют решения по R6 (строковые FK уже соответствуют).
* **G2 отложен до C4**: `pdf_render`/`grid_docx`/`doc_render` импортируются
  `timesheet/interface/schedule.py` транзитом G3 (modules → app-legacy);
  перенос `pdf_render` в `core/render.py` — вместе с модулем docs.
* `timesheet/interface` местами импортирует `adapters` напрямую
  (SqlSettingsAdapter, orm) — наследие ADR-0006; внутри модуля допустимо до
  финальных контрактов R1–R6 (фаза C7).
* Роутер `interface/doublepay.py` и `application/doublepay.py` — разные слои
  одного раздела; слияние/переименование не выполнялись (файлы не сливаются, §6).

## 5. Проверки (§7.1 — все зелёные)

* pytest день: **634 passed / 5 skipped**; «ночь» (faketime 05:30 Мск):
  **635 passed / 4 skipped** (open_shift-герметичность);
* ruff ✓; lint-imports **6/6** ✓; `check_api_contract` ✓;
* `export_openapi --check` — **без дельты** (156 путей);
* `bump_version --check` ✓; `gen_js_globals --check` ✓; `npm run lint` — 0 errors
  (2 warnings — предсуществующие, static не менялся);
* `run_ui_check` admin: 0 пустых разделов / 0 ошибок консоли (52 запроса);
  ivanov: 0/0 (25 запросов); `run_settings_scenario` — **76/76**;
* реестр моделей: 45 таблиц = main (G4/DoD).

## 6. Дальше по плану (EXECUTION-SPEC-v2 §7)

* **C3** — `modules/notify/` (эталон): `app/notify/**` + `notify_api` + модель
  `notify.py`; проверка эталона R1–R6 и публичных `__init__`.
* **C4** — остальные модули (employees — включая переезд Employee из orm
  timesheet, night, cars, docs + `core/render` (G2), settings, access, audit);
  в конце — удаление `app/models/`, `app/services/`, `app/api/`.
* **C5** — main.py финальный + финальные контракты; **C6** — фронтенд;
  **C7** — документация (ARCHITECTURE, README, SPEC, openapi).
