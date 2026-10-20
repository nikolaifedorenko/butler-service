# Изменения 20.10.2026 — этап C, фаза C4: остальные 7 модулей + удаление legacy-пакетов

Исполнение `docs/EXECUTION-SPEC-v2.md` (фазы 6 и фактически 7 — транзитные
контракты сняты в этой же фазе). Восемь коммитов, по одному на модуль +
финальная зачистка: **employees → night → cars → docs → settings → access →
audit → cleanup**. Целевая структура §2 достигнута:

```
app/ = core/ + bootstrap/ + modules/ (9 модулей) + main.py
```

`app/api/`, `app/services/`, `app/models/`, `app/engine/` — **удалены** (DoD).
Поведение и контракты API не изменились: `export_openapi --check` — без дельты
(156 путей) после каждого коммита; 45 таблиц `Base.metadata` идентичны
дорефакторным (G4).

## 1. Карта модулей (фаза 6)

| Модуль | Из чего | Слои |
|--------|---------|------|
| **employees** | `api/employees.py`, `employment.py`, `employee_lifecycle.py`, `groups.py`, `names.py` + каталог из `timesheet/adapters/orm.py` (Employee, Department, Subdivision, StatementKind, EmergencyContact, PositionHistory, EmploymentPeriod) | domain (groups, names — чистые) / application (employment, lifecycle, **catalog**) / adapters (orm) / interface (employees) / ports (тривиальный) |
| **night** | `night.py`, `night_export.py`, `services/night_notify.py`, `models/night.py`, `api/night_api.py` | application (night, night_export, night_notify, catalog) / adapters (orm) / interface (night_api) / domain, ports (тривиальные) |
| **cars** | `cars.py`, `models/cars.py`, `api/cars_api.py` | application (cars, catalog) / adapters (orm) / interface (cars_api) |
| **docs** | `doc_render.py`, `grid_docx.py`, `doc_templates.py`, `api/docs_api.py`; **G2: `pdf_render.py` → `core/render.py`** | application (doc_render, grid_docx, doc_templates) / interface (docs_api); моделей нет |
| **settings** | `api/settings_api.py` | interface-агрегатор чужих границ (timesheet.application, docs.application); своя логика отсутствует — слои тривиальные |
| **access** | `api/auth_routes.py`, `api/access_api.py` | interface (auth_routes, access_api); модели — core/identity (C1), `can_manage_user` — core/auth_guards (§0 п.8, не тронут) |
| **audit** | `api/audit_api.py` | interface (audit_api); модель и `audit()` — core/audit (C1) |
| **core += ** | `photos_api` → **`core/media_api.py`** (G1: роутер при медиахранилище, бизнес-логики нет) | — |

**Паттерн `application/catalog.py`** (введён в C4): публичная поверхность данных
модуля — ре-экспорт ORM-моделей из adapters. Другие модули импортируют модели
только через catalog (R3: чужие adapters приватны); внутри модуля — напрямую.
Каталоги: employees (7 моделей), timesheet (14 моделей + SqlSettingsAdapter),
night (9), cars (4), notify (4, добавлен в C4b).

## 2. Ключевые решения и отступления

* **`shiftrev.py` → `timesheet/application/`** (отступление от списка фазы 6,
  где он значился в employees): сервис оперирует исключительно моделями
  ShiftType/ShiftRevision таймшита; размещение в employees создало бы
  межмодульное ребро в чужие adapters, в timesheet — ноль новых рёбер.
  Единственный потребитель (карточка сотрудника) ходит через
  `timesheet.application.shiftrev` (R3).
* **R6 — кросс-модульные relationship сохранены** (`Punch.employee lazy=joined`,
  `ScheduleShift.employee`, `Car.assigned_employee`, `Employee.assigned_car`,
  `CarNightCheck.report` и др.): аннотации `Mapped[Employee]`/`Mapped[Car]`
  разрешаются реестром SQLAlchemy, импорты — TYPE_CHECKING через catalog
  владельцев. Удаление relationship изменило бы бюджеты запросов
  (`test_query_budget`) и поведение — это продуктовый рефакторинг
  (порты/DTO вместо навигации), выполняется отдельным батчом после C7.
  Строковые FK уже соответствуют R6. Задокументировано в §15 спеки.
* **Employee — в `employees/adapters/orm.py`** (план из §13/C2 выполнен):
  таймшит-классы (BlockAssignment, BankAdjustment, DoublePayDay, VipDoublePay)
  остались в timesheet; движок читает employment-периоды через
  `employees.application` (R3) — data-level связь зафиксирована в докстрингах.
* **G2 исполнен**: `pdf_render` → `core/render.py` (чистый транспорт
  LibreOffice/reportlab, R5 ✓); `doc_render`/`grid_docx`/`doc_templates` —
  бизнес документов в `docs.application`. Patch-таргет тестов переведён на
  `app.core.render.docx_to_pdf`.
* **Фаза 7 (контракты) выполнена досрочно**, вместе с зачисткой: транзитные
  контракты G3 и фасад `app/models` удалены; `.importlinter` — 14 контрактов
  финальной формы: R5 (core), изоляции timesheet/notify, независимость роутеров
  (timesheet, access) и **9 контрактов R3-private** (domain/adapters/interface
  каждого модуля приватны, `allow_indirect_imports` — R3 про прямые импорты).
* **§5.2 inline-ветвления `principal.is_manager`** (fact_api ×4, punches ×5,
  schedule ×2) — НЕ переводились на права: по спеке «каждый модуль сам решает
  семантику менеджерской видимости» — это продуктовое решение по экранам,
  выносится владельцу отдельным списком после C7 (механический перевод изменил
  бы поведение).

## 3. Тесты и проверки (§7.1 — после каждого коммита и финально)

* pytest день: **642 passed / 5 skipped**; «ночь» (faketime 05:30 Мск):
  **643 passed / 4 skipped**;
* ruff ✓; lint-imports **14/14** ✓; `check_api_contract` ✓;
* `export_openapi --check` — **без дельты** (156 путей) — после КАЖДОГО коммита;
* `bump_version --check` ✓; `gen_js_globals --check` ✓; eslint 0 errors;
* `run_ui_check` admin + ivanov: 0 пустых разделов / 0 ошибок консоли;
* сценарии: settings **76/76**, night_zones **87/87**, night_cars ✓, layers ✓,
  norms ✓ (полный набор фазы 6+);
* реестр моделей: **45 таблиц**, состав побайтово идентичен main до C2 (G4/DoD).

Известная flaky-зона (не связана с рефакторингом): прогон `test_settings_ui_api
+ test_grafik_norms + test_api` ОДНОЙ командой даёт order-dependent провал
test_15c (общая session-БД); по отдельности и полный прогон — зелёные.

## 4. Осталось по плану

* **C5 (фаза 7)** — фактически выполнена в C4h (контракты финальные, main.py —
  composition root с полным набором хэндлеров и middleware из core); формально
  в C5 остаётся снять статус «транзитных» пометок в доках.
* **C6 (фаза 8)** — фронтенд: `static/js/modules/*.js` (перенос 1:1 без слияния),
  `rglob` в `bump_version.py`, SHELL `sw.js`, index.html, eslint/gen_js_globals,
  поднятие версии статики, смоуки всех сценариев.
* **C7 (фаза 9)** — документация: ARCHITECTURE.md, README, SPEC.md (пути),
  финальный openapi-переэкспорт, AST-покрытие всех модулей (DoD), ADR-статусы;
  продуктовый батч «is_manager → права» (§5.2) и «relationship → порты» (R6) —
  отдельные решения владельца.
