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

Главная ценность и главная защита проекта — **расчётный движок v7.1**
(`app/engine/`, ~5 700 строк): чистая архитектура из пяти слоёв, детерминированные
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
| Логика расчёта в API-слое (`factview`, пересчёты в роутерах) | расчёт — только `app/engine/domain`; API тонкие; тяжёлый конвейер вызывает одна вкладка |
| Иллюзорная изоляция тестов на одной БД | движковые тесты (317+) вообще не трогают БД (чистый домен + in-memory порты); интеграция — одна сидируемая база |
| Противоречивая документация (4 копии разделов) | норматив — `docs/overtime_spec_v7_1_final.md` (монолит v7.1); SPEC/README синхронизированы |

Остались осознанные компромиссы: самодельные миграции (Alembic — точка роста),
линейный по штату бюджет УТ (по спеке: конвейер на сотрудника), SPA без сборки
(один `app.js` ~2 400 строк + секционные файлы).

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

### 2.2 Поддомены в монолите

| Поддомен | Модули | Связь с ядром |
|---|---|---|
| **Учёт рабочего времени** (ядро) | `app/engine/*`, `api/{schedule,tabel,mgmt,presence,fact,punches,engine_settings}`, `base_schedule`, `schedule_patterns`, `tabel_fill`, `shiftrev`, `employment`, `groups`, `doublepay` | — |
| **Ночные отчёты** | `night`, `night_export`, `photos`, `api/night_api` | только общие `models/db/auth`; к движку не обращается |
| **Электрокары** | `cars`, `api/cars_api` (+`photos`) | то же |
| **Документы** | `doc_templates`, `doc_render`, `grid_docx`, `pdf_render`, `names`, `api/docs_api` | читает Табель/отсутствия и карточки сотрудников |

### 2.3 Цифры (11.10.2026)

| Показатель | Значение |
|---|---|
| Движок `app/engine/` | ~5 700 строк: domain 3 530 · adapters 947 · application 700 · interface 354 · ports 195 |
| API-слой `app/api/` | ~5 200 строк, 17 роутеров, ~140 маршрутов |
| Фронтенд `static/js` | ~4 600 строк (core, app, section_v4, section_night, section_cars) |
| Тесты | ~7 100 строк, **436 тестов**: движок (EX-01…55, юниты, валидация, property, архитектура, application) + интеграция |
| Покрытие `app/engine/domain` | ≥ 95 % (DoD спеки) |
| Таблиц БД | 28 (движковые: tabel_days, schedule_shifts, schedule_absences, punches, engine_settings_versions, day_modifiers, period_closings, deferred_carry, bank_adjustments, employment_periods) |
| Приёмочных примеров спеки | 55 (EX-01…EX-55) — каждый в автотестах |

---

## 3. Слои и модули

```
static/js (SPA)  ─HTTP→  app/api/* (interface-слой)
                              │  now = now_utc() (composition root, F-15)
                              ▼
                     app/engine/application  ── знает domain + ports
                              │
             ┌────────────────┼──────────────────┐
             ▼                ▼                  ▼
   app/engine/domain   app/engine/ports   app/engine/interface
   (чистое ядро)       (13 Protocol'ов)   (тексты, serialize, views)
                              ▲
                     app/engine/adapters (SQL поверх app/models)
```

Схема: [`diagrams/01-layers.svg`](diagrams/01-layers.svg).

### 3.1 Домен (`app/engine/domain/`, 3 530 строк, ~120 файлов)

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

### 3.2 Application (`app/engine/application/`, 700 строк)

`view_period / close_period / recalculate` (с параметром `now`, эффективный период,
типованные отказы до домена: R35 → RUL-VIEW-AFTER-PREVIOUS → права закрытия),
`load_inputs` (выборка 7.4: запас в шаг, opening_mark, Табель полным периодом — R27),
`presence_board` (фильтр active_employees до домена — R38, ≤ 5 запросов),
`view_sessions`, `schedule_view` (генерация из Табеля, manual-якорь accepts_ut,
логические отсутствия), `timesheet_edit` (валидация доменными checks — F-16,
перегенерация дня ±1), `months` (гранулярность R36, цепочка), `bank_adjustment`
(правила посева R37), `period_view` (PeriodView + day_views с информационным планом R39).

### 3.3 Адаптеры (`app/engine/adapters/`, 947 строк)

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

`app/engine/interface/`: formatting (тексты флагов/трассы — единственное место),
serialize/deserialize (сохранение и чтение SettleResult/FlagsResult), views (payload
вкладок). `app/api/*`: тонкие роутеры; `now` снимается в `engine_common.now_utc()`
(composition root) и передаётся параметром — ClockPort не вводится (F-15).

### 3.5 Клиент

SPA без сборки: `core.js` (утилиты/api/модалки), `app.js` (График, Мои отметки,
Сотрудники, Настройки), `section_v4.js` (Отметки-доска, Факт, Табель, УТ, Права,
Аудит, справочники CFG-*), `section_night.js`, `section_cars.js`. Контракты:
`tools/check_api_contract.py` (JS-вызовы ↔ OpenAPI), `tools/gen_js_globals.py`
(no-undef по списку глобальных имён), `tools/bump_version.py` (версии кэша + sw.js).

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

* `domain` не импортирует никого (тест `test_domain_imports_nothing_above`).
* `application` → `domain` + `ports`; не импортирует `adapters`/`interface`/`app.*`.
* `ports` → только `typing` + `domain`.
* `adapters` → `ports`(контракты) + `domain` + `app.models`.
* `app/api` → `application` + `adapters.factory` (композиция) + `interface`.
* Циклических импортов внутри `app/engine` нет (проверяется запуском тестов и
  графом импортов в `test_architecture.py`).

## 7. Риски и точки роста

| Риск | Статус | Что делать при росте |
|---|---|---|
| Самодельные миграции (raw DDL при старте) | 🟠 | Alembic: autogenerate + версионирование; `migrate_engine_v7` — образец идемпотентного шага |
| Бюджет УТ линейный по штату (по спеке) | 🟡 | батч-порты `load_inputs` на группу сотрудников; кэш Settings уже есть |
| SPA без сборки, один app.js ~2 400 строк | 🟡 | секционные файлы уже отделены; далее — esbuild/модули при росте команды |
| SQLite в проде | 🟡 | PostgreSQL поддерживается (DATABASE_URL); WAL включён |
| Настройки движка правятся JSON-в-текстарея | 🟡 | форма-редактор справочников (валидация уже сообщает все нарушения разом) |
| Демо-сид завязан на «сегодня» | 🔵 | фиксация даты сида переменной окружения для скриншот-тестов |

## 8. Онбординг-маршрут

1. `README.md` → «Правила расчёта — модель v7/v7.1» (10 пунктов).
2. `docs/overtime_spec_v7_1_final.md`: разделы 2 (законы), 4 (модель), 6.3 (стадии
   settle), 7.2 (truth table режимов), 16 (вкладки).
3. Код по стадиям: `domain/pipeline/settle.py` → пакеты стадий → `application/view_period.py`.
4. `tests/engine/test_ex_01_15.py` — как читать приёмочные примеры (вход/выход/контроли).
5. `app/api/mgmt_api.py` + `static/js/section_v4.js (loadMgmt)` — вертикальный срез вкладки.
6. `docs/MIGRATION-MAP-v7.md` — что и почему заменили (карта «прототип → v7.1»).
