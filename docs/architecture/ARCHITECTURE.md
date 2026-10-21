# «Батлер Сервис» (butler-service) — архитектурный разбор

**Репозиторий:** https://github.com/nikolaifedorenko/butler-service
**Редакция:** 11.10.2026 — после переписывания расчётного движка по спецификации v7.1
(предыдущий разбор от 28.09.2026 описывал legacy-движок `app/timesheet.py` и движок v4;
история — в `docs/archive/AUDIT-2026-09-27.md` и `docs/CHANGES-*.md`)
**Фокус:** слои и модули, модель данных, ключевые потоки, риски, онбординг
**Как получен материал:** статический анализ импортов (архитектурные тесты), подсчёт
SQL-запросов (`SQLAlchemy before_cursor_execute`, `tests/test_query_budget.py`),
полный прогон тестов (436 тестов)

---

## 1. Резюме

Система учёта рабочего времени для службы батлеров: Табель и График «ФИО × дни»,
отметки с телефона (PWA), банк часов, управленческий табель (УТ) с кодами ДЯ/ДН/ДЯ2/ДН2,
закрытие/пересчёт периодов, доска «кто сейчас на работе», история сессий, заявления
DOCX/PDF + два независимых поддомена (ночные отчёты, электрокары).

Приложение — **модульный монолит** (ADR-0010, фазы C1–C7 исполнены 20.10.2026):
`app/core/` (инфраструктура: config, db-сессия, время, ошибки, безопасность,
права, идентичность, аудит, медиа, key-value хранилище, рендер-транспорт) +
`app/bootstrap/` и `app/main.py` (composition root — единственное место, знающее
все модули) + **9 бизнес-модулей** `app/modules/*` (timesheet, employees, night,
cars, docs, notify, settings, access, audit), каждый — гексагон из пяти слоёв
`domain / application / ports / adapters / interface`. Границы закреплены
инструментально: 14 контрактов `.importlinter` (R5, R3-приватность слоёв,
независимость роутеров) + AST-тесты (`tests/engine/test_architecture.py` —
законы движка, `tests/test_modules_architecture.py` — все модули). Межмодульные
импорты — только чужие `application`/`ports` (R3), модели — через
`application/catalog.py` владельца.

Главная ценность и главная защита проекта — **расчётный движок v7.1**
(`app/modules/timesheet/`, ~11 400 строк в модуле): чистая архитектура из пяти слоёв, детерминированные
чистые функции «данные → данные», поведение из справочников CFG-* (ни одной ветки
по строковым кодам), трассируемость каждого действия (`Reason`/`Cut`/`Flag` с
исчерпывающим составом данных), 21 инвариант, проверяемый внутри расчёта, и 55
приёмочных примеров EX-01…EX-55, воспроизведённых автотестами цифра в цифру.
Архитектурные законы (чистота домена, независимость конвейеров вкладок, «тяжёлый
конвейер — только УТ») enforced **архитектурными тестами**, а не соглашением.

Проблемы прежней редакции разбора закрыты или сняты переписыванием:

| Было (28.09.2026) | Стало |
|---|---|
| N+1 в сетке месяца (966 запросов на 11 сотрудниках) | батч-загрузка: сетка ~15 запросов, не растёт со штатом (тест-страж) |
| `recalc-all` 11 820 запросов синхронно | удалён: живой `view` считается на один период/сотрудника (6–8 запросов + конвейер, 16.1 п.5); закрытие — атомарная транзакция |
| Два источника правды о схеме (models + selfcheck) | модели — единственный источник; `migrate_engine_v7` идемпотентна; расчётные данные v4 очищены маркером |
| Логика расчёта в API-слое (`factview`, пересчёты в роутерах) | расчёт — только домен движка (ныне `app/modules/timesheet/domain`); API тонкие; тяжёлый конвейер вызывает одна вкладка |
| Иллюзорная изоляция тестов на одной БД | движковые тесты (317+) вообще не трогают БД (чистый домен + in-memory порты); интеграция — одна сидируемая база |
| Противоречивая документация (4 копии разделов) | норматив — `docs/overtime_spec_v7_1_final.md` (монолит v7.1); SPEC/README синхронизированы |

Остались осознанные компромиссы: самодельные миграции (Alembic — точка роста),
линейный по штату бюджет УТ (по спеке: конвейер на сотрудника), SPA без сборки
(оболочка `app.js` + 9 файлов разделов в `static/js/modules/`). R6 выполнен
полностью (батч 20.10.2026): кросс-модульных `relationship()` нет.

---

## 2. Что это за система

### 2.1 Предметная область

Учёт рабочего времени посменного персонала объекта (отель/резиденция). Ключевые
особенности домена (полная модель — спека v7.1, раздел 4):

* **Сессии первичны, дни — нарезка**: отметки сопрягаются в сессии на всей временной
  оси, обрезаются по горизонту, режутся локальными полуночами; ночные смены и забытые
  уходы — естественное следствие, а не особые ветки кода.
* **Табель — часы, График — флаги**: два независимых контура; расхождение не ошибка.
* **Окно — единственная операционная норма**: рабочее время, недостача, план карточки
  и ёмкость переносов считаются от окна CFG-WINDOWS; план строки Табеля — информационный
  (зарплатный) атрибут.
* **Две валюты**: физические минуты (факт, коды) и взвешенные часы банка (недостача,
  погашение по весу кода).
* **Долг — часть периода**: гасится банком и каскадом кодов при закрытии; остаток
  переносится минусом банка; коды переносятся только вперёд.

### 2.2 Поддомены = модули (структура §2 EXECUTION-SPEC-v2)

| Модуль (`app/modules/`) | Поддомен | Публичная граница |
|---|---|---|
| **timesheet** | Учёт рабочего времени: движок v7.1, Табель, График, отметки, доска, УТ, двойные, engine-настройки | `application` (use case'ы движка, engine_common, base_schedule, tabel_fill, shiftrev, catalog моделей) |
| **employees** | Каталог персонала, трудоустройство, жизненный цикл, группы графика, имена | `application` (catalog: Employee/Department/…, employment, groups/names-реэкспорт) |
| **night** | Ночной отчёт v2: зоны, объекты, чек-листы, недостатки, журнал, выгрузки. Обслуживание (досоздание смен, автозакрытие в 08:00) — стартовый прогон + фоновый поток `bootstrap/night_sync` под лидер-замком `try_lock`, НЕ в GET-запросах | `application` (night, night_export, night_notify, catalog) |
| **cars** | Электрокары: парк, заряд/возврат, места, ночная проверка | `application` (cars, catalog) |
| **docs** | Заявления DOCX/PDF, сетка Графика в Excel, шаблоны | `application` (doc_render, grid_docx, doc_templates) |
| **notify** | Общая доставка: Telegram + почта, каталог чатов, журнал отправок | `application` (config, dispatch, recipients, chats, catalog), `ports` (TransportError) |
| **settings** | Единый центр настроек (агрегирует границы timesheet/docs) | `interface` (своей логики нет) |
| **access** | Вход/сессии/impersonation, экран «Права доступа» | `interface` (модели — core/identity) |
| **audit** | Журнал действий + CSV | `interface` (модель и audit() — core/audit) |

Кросс-модульное: медиа (Photo) и роутер photos — `core/media*`; ключ-значение
`Setting` — `core/settings_store`; транспорт рендера — `core/render`;
`can_manage_user` — `core/auth_guards` (ролевой страж, не право).

### 2.3 Цифры (20.10.2026, батч review-P1 night/cars)

| Показатель | Значение |
|---|---|
| Модуль timesheet | ~11 500 строк: domain 3 583 · interface 4 219 (8 роутеров + views/formatting/period_params) · application 1 971 · adapters 1 329 · ports 195 · bootstrap |
| Прочие 8 модулей | employees 1 776 · night 2 639 · cars 1 098 · docs 1 200 · notify 1 595 · settings 186 · access 445 · audit 102 строк |
| `app/core/` + composition root | 1 996 (19 файлов) + bootstrap/main 1 795 строк |
| API | 18 роутеров по модулям, **156 путей OpenAPI** (`docs/openapi.json` сверяется в CI) |
| Фронтенд `static/js` | ~8 900 строк, 11 файлов: core.js, app.js + 9 разделов в `modules/` |
| Тесты | ~13 600 строк, **767 тестов**: движок (EX-01…55, юниты, валидация, property, архитектура) + интеграция + AST-законы всех модулей |
| Покрытие `timesheet/domain` | ≥ 95 % (DoD спеки) |
| Таблиц БД | **45** (реестр `bootstrap/registry.py`, `/api/selfcheck` сверяет схему с `Base.metadata`) |
| Приёмочных примеров спеки | 55 (EX-01…EX-55) — каждый в автотестах |

---

## 3. Слои и модули

Каждый модуль — гексагон (§3 EXECUTION-SPEC-v2); на примере timesheet:

```
static/js/modules/* (SPA) ─HTTP→ main.py (composition root: роутеры, хэндлеры
                                     ошибок, middleware из core/observability)
                                          │
                       modules/timesheet/interface (8 роутеров + views/formatting)
                                          │  now = now_utc() (composition-параметр, F-15)
                                          ▼
                       modules/timesheet/application ── знает domain + ports
                                          │        (и catalog — публичная поверхность моделей)
             ┌────────────────────────────┼──────────────────────┐
             ▼                            ▼                      ▼
   timesheet/domain              timesheet/ports        timesheet/adapters
   (чистое ядро, 18 пакетов)     (13 Protocol'ов)       (SQL + ORM-модели orm.py)
                                                                │
                                                                ▼
                                             app/core (db-сессия, время, ошибки,
                                             identity, media, settings_store, render)
```

Между модулями — только чужие `application`/`ports` (R3), модели — через
`application/catalog.py` владельца; `core` не знает модулей (R5), composition
root (`main.py`, `bootstrap/`) — единственный, кто знает всё. Контракты:
`.importlinter` (14) + AST-тесты. Схема: [`diagrams/01-layers.svg`](diagrams/01-layers.svg)
(историческая, до модульной перестройки; актуальный текст — выше).

### 3.1 Домен (`app/modules/timesheet/domain/`, 3 583 строки, ~120 файлов)

Одна функция — один файл (каталог спеки 8.1); пакеты по стадиям конвейера:

| Пакет | Содержание |
|---|---|
| `types/` | сущности (Period, Day, Mark, CalcMark, Interval, RawInterval, Session, Shift, Absence, Adjustment, DeferredBlock, ShiftEntry, Employment, ClosingInputs, PeriodState), результаты (Reason, Flag, Cut, DayCard, SettleResult, FlagsResult, DayView, SessionView, EmployeeCard, ExpectedArrival, PresenceBoard), ошибки, глубокая неизменяемость (MappingProxyType по копиям) |
| `codes_registry/` | реестры: 8 кодов Reason + канонические `step`, 3 кода флагов, 21 INV-код |
| `settings/` | структура Settings, стартовое наполнение CFG-* (единственное место бизнес-литералов), `validate_settings` + 14 проверок уровня 1 (файл на проверку), `resolve_modifier` (приоритеты 1–7) |
| `validation/` | 9 проверок уровня 2 (стадия 1) + композиция |
| `time/` | round_moment/calc_now/calc_horizon/local_minute/to_calc_mark/today_of/period_days |
| `sessions/` | ядро `pair_marks` + `check_punch_sequence` (CHK-PUNCH-SEQUENCE; opening/closing mark по R32) — общее для часов, флагов и истории |
| `presence/` | split_by_day, presence_intervals (расчётный путь), raw_presence_intervals (исходный, с секундами) |
| `day_card/` | value_of/fmt_hours, window_of_day, plan_of_day (= окно), has_presence_event, apply_plan_equals_fact (единый предикат R30), fact/work/overtime/debt, категории через полночь, codes_of_day, признаки дня (5.2), build_day_card |
| `placement/` | аккумулятор `Codes` (единственное мутабельное исключение), seed/accept_deferred/credit_unpaid, placement_order, free_capacity (от окна), place_block, relocate_codes/relocate_pending, collect_deferred, канонический порядок |
| `opening/` | нормализация входящих остатков при смене шага (round_signed: половина — от нуля) |
| `bank/` | available_bank, total_debt, pay_debt_with_bank, sacrifice_order, гранулы (CFG-GRANULE), sacrifice_codes, close_bank |
| `schedule/` | shift_segments (через полночь + слияние смежных), merge_absences (UTC), expected_subintervals |
| `flags/` | present_at, late/early/off_shift, drop_suppressed_lates, day_flags, evaluate_flags |
| `board/` | open_sessions, expected_now, expected_arrivals (одна ближайшая, R40), assemble_board |
| `checks/` | инварианты по стадиям (10.1) + итоговые |
| `reports/` | mgmt_timesheet (ключ на каждый день), build_exceptions, build_trace (восстанавливает PLAN_EQUALS_FACT) |
| `pipeline/` | `settle()` — 14 стадий, каждая строка — вызов стадии |

Запреты домена (проверяются тестами): `datetime.now()`/I/O/`print`/logging/случайность;
литералы бизнес-кодов (кроме `defaults.py`); русские строки (тексты — только interface);
`settle()` не импортирует `flags/`; флаги не знают DayCard/SettleResult (вход —
`Mapping[date, bool]`); `board/` и `sessions/` не импортируют тяжёлые пакеты.

### 3.2 Application (`app/modules/timesheet/application/`, 1 950 строк)

`view_period / close_period / recalculate` (с параметром `now`, эффективный период,
типованные отказы до домена: R35 → RUL-VIEW-AFTER-PREVIOUS → права закрытия),
`load_inputs` (выборка 7.4: запас в шаг, opening_mark, Табель полным периодом — R27),
`presence_board` (фильтр active_employees до домена — R38, ≤ 5 запросов),
`view_sessions`, `schedule_view` (генерация из Табеля, manual-якорь accepts_ut,
логические отсутствия; `rebuild_generated_for_days` — пакетная перегенерация после
массовой записи), `timesheet_edit` (валидация доменными checks — F-16,
перегенерация дня ±1, `rebuild=False` для массовок), `months` (гранулярность R36, цепочка), `bank_adjustment`
(правила посева R37), `period_view` (PeriodView + day_views с информационным планом R39).

### 3.3 Адаптеры (`app/modules/timesheet/adapters/`, 1 339 строк + `orm.py`)

По файлу на источник поверх существующей БД: `sql_timesheet` (группа по дням из
истории блоков — RUL-GROUP-PER-DAY, без N+1), `sql_punch` (naive-local → UTC-aware,
стабильная сортировка (ts, id), sanitize — первая линия чередования, границы [from,to)
по R7), `sql_schedule` (Shift/Absence/ScheduleStore; выборка по пересечению — F-04;
валидация уровня 3 → ConfigError), `sql_bank` (opening = closing предыдущего периода
цепочки; OPENING_SEED-конвенция), `sql_employment` (Employment + active_employees
батчем), `sql_settings` (версия по сроку + сборка CFG-MODIFIERS из day_modifiers/
double_pay/vip с дедупликацией), `sql_closings` (PeriodState с previous/next по
цепочке гранулярности + признаком посева; снимок флагов; замена переносов),
`sql_uow`, `factory`.

### 3.4 Interface

`app/modules/timesheet/interface/`: formatting (тексты флагов/трассы и `error_text`
— единственное место человекочитаемых текстов ошибок движка), serialize/deserialize
(сохранение и чтение SettleResult/FlagsResult), views (payload вкладок),
period_params (единая валидация `year`/`month` всех точек ввода — 422 вместо 500)
+ 8 тонких роутеров (tabel, mgmt, fact, presence, punches, doublepay, schedule,
engine_settings). `now` снимается в `application/engine_common.now_utc()`
(composition-параметр) и передаётся параметром — ClockPort не вводится (F-15).
Доменные ошибки маппятся в HTTP центральными хэндлерами `main.py`
(ConfigError → 409, DomainError → 422, ApplicationError → 409; три
задокументированных локальных catch — валидация ввода 422, см. CHANGES C2 §2).

### 3.5 Клиент

SPA без сборки (ADR-0008): `core.js` (утилиты/api/модалки), `app.js` (оболочка,
меню, роутинг) и **`static/js/modules/`** — 9 файлов разделов, имена соответствуют
модулям бэкенда (фаза C6): `timesheet_layers.js` (сетка Графика), `timesheet_v4.js`
(Отметки-доска, Факт, Табель, УТ, Права, Аудит, CFG-*), `me.js`, `employees.js`,
`night.js`, `cars.js`, `docs.js`, `dicts.js`, `settings.js` (реестр экранов единого
центра конфигурации; подключается ПОСЛЕ timesheet_v4/cars/night). Глобальные функции
сохранены: межфайловые вызовы через глобальную область, границы держат
`tools/gen_js_globals.py` (рекурсивный скан `static/js/**` → `js_globals.json`) и
ESLint `no-undef` — отказ от `window.App.modules.*` отклонён (property-доступ не
проверяется статически; прецедент — регрессия loadNight/loadCars). Порядок
`<script>` в index.html фиксирует зависимости (cars → night → v4 → settings).
Контракты: `tools/check_api_contract.py` (JS-вызовы ↔ OpenAPI, rglob),
`tools/bump_version.py` (версии кэша + SHELL `sw.js` c файлами `modules/`, rglob).

## 4. Модель данных

Схема: [`diagrams/03-data-model.svg`](diagrams/03-data-model.svg). Ключевые решения:

* **Табель первичен** (`tabel_days`): код + информационный план; График
  (`schedule_shifts`) генерируется из него по окнам и хранит явный UTC-интервал
  с `source` (generated/manual) — ручная смена заменяет генерацию дня целиком.
* **Отсутствия** (`schedule_absences`) — UTC-интервалы (могут через полночь, ≤ 24 ч);
  «разрез» смены логический: смена физически не делится.
* **Отметки** (`punches`) — локальное naive-время объекта (конвенция приложения);
  адаптер конвертирует в UTC-aware и гарантирует стабильный порядок.
* **Закрытия** (`period_closings`) — результат + снимок флагов + ClosingInputs +
  закрывающий банк + версии настроек + ревизия; уникальный ключ (сотрудник, период)
  исключает конкурентное закрытие.
* **Переносы** (`deferred_carry`) — вход следующего периода;сохранение заменяет набор
  целиком (исчезнувшие блоки удаляются).
* **Настройки** — версии JSON-payload (`engine_settings_versions`) с `valid_from`;
  ретро-исправление — новая версия; идентификаторы версий сохраняются с результатом.
* **Корректировки банка** (`bank_adjustments`) — с `reason_code`; `OPENING_SEED` —
  конвенция адаптера (ядро маркер не интерпретирует, RUL-REASON-CODE-FREE).

## 5. Ключевые потоки

Схемы: [`diagrams/04-flows.svg`](diagrams/04-flows.svg).

### 5.1 Просмотр УТ (view)
`GET /api/mgmt` → на сотрудника: `period_state` → закрыт? → чтение `result_json +
flags_json` (без домена); иначе проверка допуска (previous_closed | opening_bank_set)
→ `load_inputs` (Табель полным периодом, отметки [from−step, to+step), opening_mark,
банк/переносы/шаг предыдущего периода) → `settle(view)` → `evaluate_flags` → payload.
Бюджет: 6–8 запросов + конвейер на сотрудника (16.1 п.5).

### 5.2 Закрытие периода
Проверки до домена (типованные отказы) → `UnitOfWork`: `settle(close)` +
`evaluate_flags` → `save_result` (результат + снимок флагов + ClosingInputs + версии)
→ `save_closing_bank` → `save_deferred(next_period)` → commit; любое исключение →
rollback (ничего не сохранено). Повторное закрытие отсекает уникальный ключ.

### 5.3 Пересчёт
Только последний закрытый (next_closed = False) → старт с замороженных ClosingInputs;
отметки/Табель/корректировки перечитываются свежими (R28) → то же `settle(close)` →
сохранение **заменяет** результат/банк/переносы/снимок флагов.

### 5.4 Отметка (запись)
POST /api/punches: сериализация по сотруднику (lock) → защита от дублей (60 с) →
занятость (периоды работы) → запись IN/OUT. Расчёт не запускается (RUL-ALL-MARKS-COUNTED:
ворот нет). Экран статуса — лёгкие данные: График + ожидаемые интервалы (домен
`schedule/`) + последняя отметка + банк последнего закрытого периода.

### 5.5 Доска (каждые 30 с на клиент)
`presence_board(now)`: Settings (кэш) → `active_employees(today)` → `last_marks(now)`
→ `shifts_on_day` → `absences_on_day` → `assemble_board`. Константное число запросов,
не зависит от штата; уволенные с «забытым уходом» на доску не попадают (R38).

## 6. Карта зависимостей

Внутри модуля (§3 спеки; AST-тесты `tests/test_modules_architecture.py`):

* `domain` не импортирует никого, кроме stdlib и своего домена (R1);
* `application` → `domain` + `ports` + `core.errors`; не импортирует `interface`;
* `ports` → только stdlib + `domain` + `core`;
* `adapters` → `ports` + `domain` + `core` + ORM; не импортируют `interface`
  (исключения — изначальная архитектура движка: `factory.py`, `sql_closings.py`
  и др. — явный allowlist в AST-тесте, кандидаты на продуктовый батч);
* `interface` → `application` + `ports` + `core` (+ свой `adapters.orm` —
  задокументированный прагматизм до финальных контрактов).

Между модулями (R3; private-контракты `.importlinter` ×9):

* чужие `domain`/`adapters`/`interface` — запрещены; публичны только
  `application`/`ports`; модели — через `application/catalog.py` владельца;
* `core` не импортирует модули (R5; единственная TYPE_CHECKING-аннотация
  `core.auth → employees.catalog`, в runtime — инъекция `set_employee_loader`);
* composition root (`main.py`, `bootstrap/`) — единственный импортёр всего
  (реестр моделей `registry.ensure_models()` — явные импорты всех `adapters.orm`;
  фоновый поток `bootstrap/night_sync` — обслуживание ночных отчётов вне запросов);
* циклов нет: кросс-модульные импорты идут в чужие `application`-границы, которые
  не импортируют чужие модули обратно (проверяется запуском + контрактами).

## 7. Риски и точки роста

| Риск | Статус | Что делать при росте |
|---|---|---|
| Самодельные миграции (raw DDL при старте) | 🟠 | Alembic: autogenerate + версионирование; `migrate_engine_v7` — образец идемпотентного шага. Гонку одновременного старта воркеров закрывает `core/startup_lock` (20.10.2026); следующий шаг — таблица версий шагов и отдельная команда миграций до uvicorn |
| Гонка DDL при старте нескольких воркеров (`duplicate column name`, IntegrityError `night_reports.date`) | 🟢 закрыт 20.10.2026 | `init_db()` целиком под замком `core/startup_lock`: PostgreSQL — сеансовый `pg_advisory_lock` (держит и несколько контейнеров), SQLite — `flock` на файле рядом с БД; `suppress(Exception)` вокруг DDL заменён явной проверкой таблиц (на PostgreSQL сбой DDL портил транзакцию шага). Стражи: `tests/test_review_p0.py` |
| GET `/api/night/*` с побочными записями; переоткрытие отчёта закрывалось обратно ≤ 120 с | 🟢 закрыт 20.10.2026 | `sync_reports` убран из роутеров: обслуживание — старт (под `startup_lock`) + фоновый поток `bootstrap/night_sync` (каждые `NIGHT_SYNC_SECONDS`, по умолчанию 60); в нескольких воркерах раунд выполняет один процесс под неблокирующим `core/startup_lock.try_lock("night-sync")`. Переоткрытый отчёт (`night_reports.reopened_at`) автозакрытием больше не закрывается; reopen открытого — 409. Окно досоздания смен — честная константа `BACKFILL_DAYS=31` вместо `min(len(have)+31, 31)`. Стражи: `tests/test_review_p1_night_cars.py` |
| Автозакрытие смены не проставляло `close_reason` (DOCX подписывал закрытый отчёт «Открыт · закроется 08:00»); повторная отметка кара не обновляла `checked_at` | 🟢 закрыт 20.10.2026 | `finalize_report(rep, reason="auto"|"manual")` — причина закрытия пишется всегда; `check_car_night` обновляет `ch.checked_at` при каждом сохранении (last write wins) — `car.last_checked_at` и флаг «взяли после проверки» свежие. Стражи: `tests/test_review_p1_night_cars.py` |
| Массовые операции перегенерировали График по-ячеечно | 🟢 закрыт 20.10.2026 | `bulk` / `range-absence` / `copy` пишут Табель с `rebuild=False` и делают ОДНУ перегенерацию на затронутый месяц (`schedule_view.rebuild_generated_for_days`): 12 ячеек — 373 → 265 запросов, перегенераций 13 → 1; на пределе 500×366 экономия ~1,6 млн запросов |
| `year`/`month` без валидации → 500 на запросе клиента | 🟢 закрыт 20.10.2026 | единый `interface/period_params.ensure_period` во всех 14 точках ввода периода (422 + `{"detail": …}`); параметризованный страж `test_bad_period_is_422_not_500` |
| Бюджет УТ линейный по штату (по спеке) | 🟡 | батч-порты `load_inputs` на группу сотрудников; кэш Settings уже есть |
| SPA без сборки, один app.js ~2 400 строк | 🟢 закрыт 15.10.2026 | app.js 2262 → 369 строк: разделы — 9 файлов `static/js/modules/` (C6); границы держат gen_js_globals + ESLint no-undef + смоуки (ADR-0008); esbuild — при росте команды |
| Кросс-модульные `relationship()` на каталог (R6) | 🟢 закрыт 20.10.2026 | все 9 связей удалены, навигации → батч-словари/`db.get` через identity map; allowlist в `tests/test_modules_architecture.py` пуст и охраняется тестом (`docs/CHANGES-2026-10-20-debt2-r6-relationships.md`) |
| `dt.date.today()` в timesheet (системная TZ вместо `core/time.local_date()`) | 🟢 закрыт 20.10.2026 | все 9 вызовов переведены на `local_date()`/`now_utc()`; AST-страж `test_no_system_time_reads_in_modules` запрещает `today()/now()` в модулях (allowlist: `now_utc()` — composition-параметр F-15); граничные тесты у полуночи (`tests/test_tz_local_date.py`) |
| SQLite в проде | 🟢 закрыт 15.10.2026 | прод-профиль `docker-compose.prod.yml`: PostgreSQL 16 + nginx (TLS) + бэкапы; драйвер в образе |
| Настройки движка правятся JSON-в-текстарея | 🟡 | форма-редактор справочников (валидация уже сообщает все нарушения разом) |
| Демо-сид завязан на «сегодня» | 🔵 | фиксация даты сида переменной окружения для скриншот-тестов |

## 8. Онбординг-маршрут

1. `README.md` → «Структура» и «Правила расчёта — модель v7/v7.1» (10 пунктов).
2. `docs/EXECUTION-SPEC-v2.md` §2–§3 — целевая структура и правила слоёв R1–R6;
   `docs/adr/0010-modular-monolith-core-modules.md` — почему модульный монолит.
3. `docs/overtime_spec_v7_1_final.md`: разделы 2 (законы), 4 (модель), 6.3 (стадии
   settle), 7.2 (truth table режимов), 16 (вкладки).
4. Код по стадиям: `app/modules/timesheet/domain/pipeline/settle.py` → пакеты
   стадий → `application/view_period.py`.
5. `tests/engine/test_ex_01_15.py` — как читать приёмочные примеры (вход/выход/контроли).
6. Вертикальный срез вкладки: `app/modules/timesheet/interface/mgmt_api.py` +
   `static/js/modules/timesheet_v4.js (loadMgmt)`.
7. Границы: `.importlinter` (14 контрактов) + `tests/test_modules_architecture.py`
   (AST-законы всех модулей) — что можно импортировать и откуда.
8. `docs/CHANGES-2026-10-20-stage-c*.md` — как и почему прошла модульная
   перестройка (C1–C7), включая задокументированные долги.
