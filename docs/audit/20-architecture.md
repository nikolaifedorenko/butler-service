# 20. Качество кода и архитектура

ID → [REPORT.md](REPORT.md).

## 20.1. Границы слоёв на деле
- `lint-imports`: 14 контрактов соблюдены (`commands.md`). Исключение одно, задокументированное:
  `app.core.auth -> app.modules.employees.application.catalog` (аннотация под `TYPE_CHECKING`,
  `.importlinter:29-32`).
- AST-тесты `tests/test_modules_architecture.py` держат R1/R3/R6 для 9 модулей. Явный
  allowlist (adapters → interface и adapters → application в `timesheet`) описан в
  p2-инвентаризации §3.1; продуктовый батч «порты/DTO» ещё не сделан.
- Промпт описывает `app/*.py` верхнего уровня (`night.py`, `cars.py`, `photos.py`) вне слоёв —
  **устарело**: их больше нет, всё разложено по `app/modules/*` и `app/core/*` (ADR-0010).
- Пустые слои. У `access`, `audit`, `settings` папки `domain/`, `application/`, `ports/`,
  `adapters/` содержат только `__init__.py` (00-inventory, список файлов). Это шаблон «на вырост»,
  кода в нём нет. Проблемы в этом нет, но для нового модуля это 5 пустых пакетов, которые нужно
  создавать вручную (TARGET-ARCHITECTURE.md §1).

## 20.2. ARCH-02. Крупные файлы и функции
| Файл | Строк | Что в нём смешано |
|---|---|---|
| `static/js/modules/settings.js` | 2 412 | реестр экранов настроек + 15 экранов + редактор настроек движка |
| `static/js/modules/night.js` | 1 576 | ход смены, архив, отправка, справочник обхода |
| `app/modules/night/interface/night_api.py` | 1 362 | справочник (зоны, области, чек-листы, службы), ход смены, фото, отправка, кары, экспорт |
| `static/js/modules/timesheet_v4.js` | 1 339 | Табель, УТ, права доступа, журнал |
| `app/modules/timesheet/interface/schedule.py` | 1 331 | сетка, правки, массовые операции, отсутствия, XLSX, PDF |
| `app/modules/employees/interface/employees.py` | 926 | сотрудники и учётки, банк, справочники (департаменты, службы, виды смен) |
| `app/modules/timesheet/interface/engine_settings_api.py` | 621 | версии, модификаторы, «здоровье», правила |

Функции со сложностью ≥ 38 по radon: `night_export.build_docx` (80, `night_export.py:34`),
`seed_if_empty` (58, `bootstrap/seed.py:110`), `fact_api.fact_month` (51, `fact_api.py:74`),
`render.docx_to_pdf_native` (50, `render.py:238`), `grid_docx.schedule_docx` (48,
`grid_docx.py:210`), `punches._punch_locked` (46, `punches.py:238`), `schedule.get_grid`
(45, `schedule.py:246`), `schedule.absence_period` (43, `schedule.py:861`),
`recipients.group_by_service` (41, `recipients.py:38`), `night.defects_of` (38,
`night.py:393`). Резать нужно по задачам, а не по числу строк. `_punch_locked` смешивает
разбор ввода, правила режима отметок, выбор направления и сборку ответа. Именно в ней сидит
AUTHZ-02, и для правил отметок нужна отдельная тестируемая функция.

## 20.3. ARCH-01. Транзакции и аудит
- `db.commit()` встречается в роутерах (`night_api.py` — 27, `employees.py` — 16, `schedule.py`
  — 12, …), в сервисах (`employees/application/lifecycle.py:198,223,246,289`,
  `night/application/night.py:194,243`, `night_notify.py:146`, `core/media.py:387,420`) и в
  UoW движка (`timesheet/adapters/sql_uow.py:22`). Единой точки фиксации нет: у одного сценария
  коммит может быть в сервисе, а у соседнего — в роутере.
- В большинстве мест `audit()` пишется **в той же транзакции**, что и изменение. Исключения:
  - закрытие и пересчёт периода: каждый сотрудник коммитится внутри UoW, запись аудита
    коммитится отдельно после цикла (`mgmt_api.py:140-175`). При сбое после цикла периоды закрыты
    без записи в журнале;
  - отправка недостатков: сначала сеть, потом журнал и аудит (CONC-02).
- `SqlUnitOfWork` используется только движком.

## 20.4. Ошибки
- Доменные ошибки ядра (`core/errors.py`: NotFound, Forbidden, Validation, Conflict, Gone,
  PayloadTooLarge) и движка (ConfigError, DomainError, ApplicationError) централизованно
  переводятся в HTTP-коды (`main.py:167-226`). Это хорошо.
- В interface-слое 222 вызова `HTTPException(` с русским текстом. Допустимо для
  роутеров, но правила (`_guard_bank`, `doublepay._guard`, `_guard_open`) сидят там же, и
  сервисный слой их не видит. `core/auth_guards.can_manage_user` и `core/permissions.require_perm`
  бросают `HTTPException` из ядра: исключение задокументировано (ADR-0006, EXECUTION-SPEC §5.2).
- Вперемешку с этим `except ValueError → HTTPException(400, str(e))` пробрасывает тексты
  исключений библиотек: `night_api.py:1048-1049`, `cars_api.py:327-328`, `docs_api.py:202-203`
  («Файл не является корректным .docx: <текст python-docx>»). Low.

## 20.5. ARCH-03. Покрытие тестами вне движка (`pytest --cov`, общее 88 %)
| Файл | Покрытие | Что не покрыто и чем рискует |
|---|---|---|
| `timesheet/application/doublepay.py` | 35 % | расчёт двойной оплаты: деньги |
| `timesheet/application/shiftrev.py` | 40 % | ревизии смен словаря |
| `bootstrap/night_sync.py` | 56 % | фоновый поток (раунд, пропуск, ошибки) |
| `timesheet/interface/doublepay.py` | 58 % | маршруты двойной оплаты, ролевой `_guard` |
| `core/auth_guards.py` | 61 % | **иерархия ролей** (`can_manage_user`): ветки manager и supervisor |
| `employees/application/employment.py` | 62 % | периоды работы |
| `bootstrap/migrations.py` | 68 % | **обновление старых баз** — ни одного теста со схемой прошлых версий (DB-01 прошёл незамеченным) |
| `core/startup_lock.py` | 72 % | ветки PostgreSQL (нет PG в CI) |
| `timesheet/interface/tabel_api.py` | 74 % | массовые операции Табеля |
| `cars/application/cars.py` | 75 % | передача, ролевые ветки, гонка (CONC-01) |

Не покрыто совсем: прогон на PostgreSQL (DB-04), матрица «роль × маршрут» с индивидуальными
allow/deny (в репозитории — только точечные тесты `test_permissions_unification.py`,
`test_scope_perms.py`), конкурентные сценарии, кроме закрытия периода.

## 20.6. Типизация и логирование
- Аннотации в основном есть; mypy или pyright в CI нет. Слабо типизированы `dict`-ответы
  роутеров: ни у одного маршрута нет `response_model` (grep: 0), поэтому OpenAPI не описывает ответы, а
  `check_api_contract` сверяет только пути, не поля.
- Логирование: JSON access log и логгер `uvicorn.error` для старта и фона. Доменные события
  (закрытие периода, отправки) идут только в `audit_log`. Для одного объекта этого достаточно.
