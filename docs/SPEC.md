# Батлер Сервис — спецификация приложения

> Нормативный документ расчётного ядра — [`overtime_spec_v7_1_final.md`](overtime_spec_v7_1_final.md)
> (спецификация v7.1) и [`overtime_ai_tz_v3.md`](overtime_ai_tz_v3.md) (ТЗ ред. 3).
> Этот документ описывает приложение вокруг ядра: слои, модель данных, вкладки, API,
> документы, выгрузки, тесты. При расхождении по расчётам приоритет у спецификации v7.1.

## 1. Термины и обозначения

| Термин | Значение |
|---|---|
| Табель | первичный документ: код дня + информационный (зарплатный) план строки на каждый день (`tabel_days`) |
| Значение Табеля | `<код>` или `<код> <часы>` («Я 12», «Я 10,75») — ключ строки CFG-WINDOWS |
| Окно | интервал рабочего времени из CFG-WINDOWS; единственная операционная норма: рабочее время, недостача, план карточки и ёмкость переносов считаются от окна (R34/R15/R13) |
| График | смены (`schedule_shifts`: generated/manual) и согласованные отсутствия (`schedule_absences`); используется только флагами и доской |
| Отметка | сырое событие PWA «пришёл»/«ушёл» (`punches`), локальное naive-время объекта → UTC в адаптере |
| Сессия | отрезок [пришёл, ушёл) на общей оси; ядро `pair_marks` проверяет чередование и не чинит его |
| Период | месяц либо половина месяца по настройке `period_granularity`; цепочка — по трудоустройству |
| Эффективный период | запрошенный период ∩ интервал трудоустройства; домен знает только его |
| УТ | управленческий табель: коды ДЯ/ДН/ДЯ2/ДН2 по дням после размещения и (в close) изъятия |
| Банк часов | взвешенный остаток; может быть отрицательным (перенос долга) |
| Флаги | `LATE` (в т.ч. actual_at=None — «не пришёл»), `EARLY_DEPARTURE`, `OFF_SHIFT_ATTENDANCE` |
| Посев | корректировка банка `OPENING_SEED` — начальный банк первого периода (R37) |

## 2. Архитектура

Пять слоёв, зависимости только вниз (спека 2.1):

```
interface (static/js, app/api/*) → application (app/engine/application) → domain (app/engine/domain)
        adapters (app/engine/adapters) реализуют ports (app/engine/ports) поверх БД (app/models)
```

* `domain` — чистые функции и справочники: нет времени, I/O, текстов для человека;
  одна функция — один файл (каталог 8.1); поведение из данных CFG-*, не из веток по кодам.
* `application` — use case'ы с параметром `now` (R10): `view_period`, `close_period`,
  `recalculate`, `presence_board`, `view_sessions`, `schedule_view`, `timesheet_edit`,
  `months`, `bank_adjustment`, `load_inputs` (выборка отметок с запасом в шаг + opening_mark, 7.4).
* `ports` — 13 Protocol'ов; контрактные dataclass'ы (`PeriodState`, `ClosingInputs`,
  `Employment`) живут в `domain/types/entities.py` (F-06). `ClockPort` не вводится (F-15):
  системное время снимается в composition root (`app/api/engine_common.now_utc`).
* `adapters` — SQL-реализации: стабильный порядок отметок и первая линия чередования
  (sanitize), валидация уровня 3 при чтении Графика, непрерывность банка
  (opening = closing предыдущего периода цепочки), замена переносов при сохранении.
* `interface` — HTTP-роутеры `app/api/*` и SPA `static/js/*`; единственное место
  человекочитаемых текстов (`app/engine/interface/formatting.py` + роутеры).

Четыре независимых расчёта (16.1): `settle()`, `evaluate_flags()`, `assemble_board()`,
история сессий (`pair_marks`). Тяжёлый конвейер запускает только вкладка
«Управленческий табель» — подтверждается архитектурными тестами.

## 3. Модель данных (таблицы)

### Движок v7.1
| Таблица | Содержание |
|---|---|
| `tabel_days` | Табель: `employee_id, date, code, plan_minutes, note, source (manual/cycle)` — ровно одна строка на день трудоустройства (RUL-TIMESHEET-COVERS-PERIOD) |
| `schedule_shifts` | График: `date` (якорь), `start_utc/end_utc` (naive UTC), `source (generated/manual)`, `shift_type_id?`, `note`; смена может пересекать полночь; физически не режется |
| `schedule_absences` | Согласованные отсутствия: `start_utc/end_utc` (≤ 24 ч, может через полночь), `kind_id` (вид из словаря — заявление/режим отметок), `note` |
| `punches` | Сырые отметки: `ts` (локальное naive), `kind IN/OUT`, `source`, `note`, `created_by` |
| `engine_settings_versions` | Версии справочников CFG-*: `valid_from`, `payload_json` (кодек `settings_codec`), ретро-исправление — новая версия |
| `day_modifiers` | Записи CFG-MODIFIERS (уровни 1–6): `name, value, employee_id?, group?, date?, period_start?` |
| `period_closings` | Закрытия периодов: `result_json` (SettleResult), `flags_json` (снимок FlagsResult), `bank_open/deferred_in_json/previous_step` (ClosingInputs), `closing_bank_minutes`, `settings_versions`, `revision`, автор/время |
| `deferred_carry` | Отложенные блоки во вход периода-получателя: `period_start, source_day, tariff, minutes` (без reason_code — v7/R1) |
| `bank_adjustments` | Ручные корректировки: `hours, effective_date, reason_code` (`OPENING_SEED` — посев), `note`, автор |
| `employment_periods` | Периоды работы: `start_date`, `end_date` (последний рабочий день включительно, NULL — работает) |
| `double_pay_days`, `vip_double_pay` | Дни двойной оплаты и ВИП-периоды — подмешиваются адаптером настроек как модификатор «Двойные переработки» |

### Приложение
`employees` (+гражданство/служба/контакты), `users`, `access_groups/access_group_members/
access_grants` (права), `departments`, `subdivisions`, `shift_types` (+`shift_revisions`) —
словарь смен и видов отсутствий (пресеты ручных смен, заявления, режим отметок),
`block_assignments` (блоки/циклы сотрудников), `position_history`, `emergency_contacts`,
`statement_kinds` (виды заявлений), `settings` (ключ/значение), `audit_log`,
`night_*` (ночной отчёт), `car_*` (электрокары), `photos`.

Удалены вместе со старым движком: `timesheet_rows` (расчётные строки legacy),
`schedule_entries` (ячейки старого графика); `deferred_carry.reason_code` не мапится.

## 4. Движок расчёта (app/engine)

Конвейер часов `settle()` — 14 стадий (спека 6.3): валидация входа (уровень 2) →
нормализация входящих остатков при смене шага (`OPENING_ROUNDED`) → округление отметок
и `now` → сессии и интервалы (обрезка по горизонту, нарезка полуночами) → карточки
дней (окно, план=окно, факт, рабочее, переработка, недостача от окна, «План=Факт») →
аккумулятор кодов → неоплачиваемая переработка в банк по весу → первичное размещение
(ёмкость от окна) → доступный банк и общий долг → (close) погашение банком → каскад
гранулами по CFG-CASCADE → повторное размещение → переносы и закрывающий банк →
результат (УТ, exceptions, trace, инварианты).

Конвейер флагов `evaluate_flags()` (6.6): исходные интервалы (секунды, без округления) +
отрезки смен (слияние смежных) − отсутствия (UTC) → ожидаемые подинтервалы →
LATE / EARLY_DEPARTURE / OFF_SHIFT_ATTENDANCE; из часового конвейера — только
`plan_equals_fact: Mapping[date, bool]`.

Доска `assemble_board()` (16.2) и история `view_sessions()` (16.4) — независимые
лёгкие расчёты на батч-портах и ядре `pair_marks`.

Режимы (truth table 7.2): `view` незакрытого (ничего не сохраняет), чтение закрытого
(без домена), `close` (атомарно: результат + снимок флагов + банк + переносы +
ClosingInputs + версии + состояние), `recalculate` (ClosingInputs заморожены; отметки,
Табель, корректировки свежие; сохранение заменяет).

Ошибки: типизированные (`ConfigError`, `UnknownDayCodeError`, `UnknownTimesheetValueError`,
`InvalidInputDataError(code)`, `IncompleteTimesheetError`, `IncompletePeriodError`,
`InvariantViolationError(code)`); бизнес-ситуации — структурированные записи
(`NO_RECEIVER` в exceptions), не ошибки.

## 5. Вкладки и API

| Вкладка | API | Use case | Домен |
|---|---|---|---|
| Отметки | `GET /api/presence/board` | `presence_board(now)` | `assemble_board` |
| График | `GET /api/schedule`, `PUT/DELETE /api/schedule/shift`, `POST/DELETE /api/schedule/absence`, `POST /api/schedule/range-absence`, `fill-pattern`, `continue`, `copy`, `clear-month`, `xlsx`, `pdf` | `view_schedule`, `save_schedule_day`, `drop_manual_day`, `save_absence/drop_absence`, `rebuild_generated_schedule` | `accepts_ut`, окна |
| Факт | `GET /api/fact/sessions?employee_id&first&last` | `view_sessions` | `pair_marks` |
| Табель | `GET /api/tabel`, `PUT /api/tabel/cell`, `POST /api/tabel/bulk`, `POST /api/tabel/fill-from-cycles` | `save_timesheet_day` (+валидация доменными checks, F-16) | checks уровня 2 |
| Управленческий табель | `GET /api/mgmt[?employee_id&detail&half]`, `POST /api/mgmt/close`, `POST /api/mgmt/recalculate`, `GET /api/mgmt/periods`, `GET /api/mgmt/xlsx` | `view_period` / `close_period` / `recalculate` | `settle` + `evaluate_flags` |
| Мои отметки | `GET /api/punches/status`, `POST /api/punches`, `GET /api/punches`, `DELETE /api/punches/{id}`, `PUT /api/punches/{id}/note` | — (лёгкие данные: График + отметки + банк последнего закрытого периода) | — |

Прочие роутеры: `auth`, `employees` (карточки, корректировки банка с правилами посева,
периоды работы, переводы), `access`, `audit`, `settings` (+ `base` — цикл объекта),
`engine-settings` (версии CFG-* + модификаторы), `shift-types` (словарь), `docs`
(заявления), `doublepay`, `night`, `cars`, `photos`, `departments`, `subdivisions`.

Права: роль → группы доступа → индивидуальные гранты (запрет сильнее разрешения);
вкладки учёта — `schedule.view/edit`, `tabel.view/edit`, `mgmt.view/close/recalculate`,
`presence.view`, `settings.view/edit`, `employees.view/edit`, `audit.view`, `access.manage`.

## 6. Циклы и заполнение Табеля

Блоки («Смена 1/2» — базовый цикл объекта 2/2 в противофазе; «Пятидневка» — свои
выходные; «Другие смены» — индивидуальный цикл) задают **смену дня** (`base_shift`).
Инструмент «Заполнить из циклов» (`app/tabel_fill.py`) раскладывает смены по дням и
подбирает значение Табеля по точным границам окон CFG-WINDOWS: дневная смена → одно
значение; ночная/суточная → части дня («утро» предыдущей смены + «вечер» своей
сливаются; «С 16» 08:00–24:00, «С 24» 00:00–24:00, «С 8» 00:00–08:00); день без работы
→ код отсутствия из словаря (Т-13 код вида), иначе «В». Непредставимые одним значением
дни (несмежные отрезки) — предупреждение: нужен другой цикл или ручная ячейка.
После заполнения График перегенерируется из Табеля.

## 7. Документы и выгрузки

* Заявления (DOCX/PDF): виды — расширяемый справочник `statement_kinds` + `doc_type`
  вида отсутствия в словаре смен; период отсутствия находится **целиком**
  (`/api/schedule/absence-period` — по непрерывному диапазону кода Табеля либо записи
  отсутствия); плейсхолдеры `{full_name_genitive}`, `{date_from_ru}`, `{days_word}`,
  `{from_time}/{until_time}`, `{hours}`, `{nationality}`, `{subdivision}`, `{department}`…
* PDF: DOCX → LibreOffice, иначе встроенный рендер (reportlab + DejaVu); без движка —
  честный 501 с подсказкой; «Печать» и Excel работают всегда.
* Excel: График («ФИО × дни», значение Табеля + интервалы смен, `*` — отсутствие),
  УТ («ФИО × дни», ячейка «ДЯ2 3 ДН 1», итоги по кодам, недостача, банк, статус).

## 8. Настройки

* Справочники движка CFG-* — версии `engine_settings_versions` (JSON payload);
  редактор в «Настройках»; валидация уровня 1 при сохранении (все нарушения разом);
  граница действия версии — 1 или 16 число (гранулярность периода).
* Модификаторы дня — таблица `day_modifiers` + дни двойной оплаты + ВИП-периоды
  (адаптер собирает их в CFG-MODIFIERS, дедуплицируя идентичные записи; конфликт
  одного уровня — `ConfigError`).
* Правила объекта (`settings`): базовый цикл и опорная дата; словарь смен; виды
  заявлений; департаменты/службы; прочее (фото, удержание…).
* Шаги расчёта, лимит опоздания, лимит дня, гранулярность — в payload справочников
  (CFG-LIMITS, R36); смена шага — только на границе периодов (входящие остатки
  нормализуются, `OPENING_ROUNDED`).

## 9. Тесты

* `tests/engine/` — домен и application: EX-01…EX-55 (каждый подкейс отдельно, полное
  сравнение результата в канонической форме), юниты каталога 8.1, валидация 3 уровней,
  property-based инварианты и детерминизм (hypothesis), архитектура (граф импортов,
  чистота, независимость конвейеров), truth table режимов, R35–R40, атомарность.
  Покрытие `app/engine/domain` ≥ 95 %.
* `tests/test_api.py`, `test_features.py`, `test_v4_api.py`, `test_readonly_pdf.py`,
  `test_query_budget.py` и др. — интеграция: роли и права, вкладки, документы,
  бюджет запросов (доска — константа; сетка не растёт со штатом; УТ — линейно
  по сотрудникам согласно 16.1 п.5), миграции и selfcheck схемы.

## 10. Ограничения и точки роста

* DST не поддерживается (локальные сутки = 1440 мин, R24); зоны с переходами требуют
  отдельного решения.
* Пересчёт — только последнего закрытого периода; каскадного пересчёта цепочки нет
  (осознанное решение, 7.2).
* Значение Табеля — один код на день: день из двух несмежных отрезков (ночная подряд
  + дневная) одним значением непредставим — окно не пересекает полночь (CHK-WINDOW-BOUNDS).
* Деньги не считаются; информационный план строки — зарплатный атрибут для внешнего
  расчёта.
* Рост: Alembic-миграции для боевой БД, батч-порты УТ на группу сотрудников,
  телеграм-бот отметок, дашборды по объектам.
