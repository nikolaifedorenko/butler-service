# Карта миграции: прототип (движок v4) → спецификация v7.1

Рабочий документ реализации (base 0.1 п.1). Слева — что найдено в прототипе,
справа — какой слой/порт/модуль новой спецификации это заменяет.

## Решения владельца (раунд вопросов от 11.10.2026)

1. **Цикл-редактор графиков сохраняется** как инструмент заполнения **Табеля**
   (пишет коды и планы в `tabel_days`); График генерируется из Табеля по CFG-WINDOWS
   строго по base 16.3.
2. **«Отпросился» — строго по спеке**: согласованное отсутствие не влияет на план,
   часы и банк (RUL-ABSENCE-ONLY-FLAGS); старое «списание часов с банка» удалено.
3. **Миграция данных не нужна**: расчётные данные v4 были тестовыми — удаляются;
   демо-база пересоздаётся; legacy-расчёт `timesheet_rows` удаляется вместе со
   старым движком.
4. **Документация — полный комплект**: спека v7.1 и ТЗ ред.3 — в `docs/` как
   норматив; `docs/SPEC.md`, README, `docs/architecture/ARCHITECTURE.md` переписываются;
   `docs/overtime_spec_v4.md` удаляется.

## Расчётный код

| Было (v4) | Стало (v7.1) |
|---|---|
| `domain/pipeline/settle.py` (10 стадий, `open_session_since`) | `settle()` из 14 стадий (6.3); `open_session_since_utc` удалён из результата |
| недостача/план/ёмкость от плана строки Табеля | от **окна** (R15/R34): `debt_of_day`, `plan_of_day`, `free_capacity` |
| `Window(code, plan_minutes, segments)` — сегменты, план | `Window(start_minute, end_minute)` — одно окно, без плана; план карточки = длина окна |
| `Category(name, segments, tariffs)` | `Category(code, start_minute, end_minute)`; коды УТ = `<категория>[<вес>]` слитно (`ДЯ2`) |
| `Group(plan_equals_fact_auto)` | `Group` без полей; «Авто» — только колонка CFG-DAY-CODES (R19) |
| `Modifier(employee_id, group, day)` | `ModifierEntry(+period)` — ровно шесть форм области (CHK-MODIFIER-SCOPE) + `GlobalDefaults` (CHK-DEFAULTS) |
| «План=Факт» с синтетическим фактом/отметками, групповой «Авто» | единый предикат из 4 условий (R30/R12/R16); синтетика запрещена |
| `presence/sort_marks.py` — пересортировка отметок в домене | **удалена**: сопряжение в исходном порядке (4.5), `pair_marks` проверяет чередование (`CHK-PUNCH-SEQUENCE`, R31) и не чинит |
| `flags/gap.py` (ABSENCE_GAP), `flags/missed.py` (MISSED_DAY), `activity_review.py`, `session_open.py` | **удалены** (R18/R21); реестр — 3 кода; след «не пришёл» — `LATE(None)` |
| `Absence(day, start_minute, end_minute)` — внутри дня | `Absence(start_utc, end_utc)` — UTC-интервал через полночь (R17); `domain/schedule/` |
| `DeferredBlock(reason_code)` | без `reason_code` (R1); колонка `deferred_carry.reason_code` удаляется |
| `Adjustment(amount, reason_code, note)` | `+ period` (RUL-BANK-CONTINUITY); CHK-OPENING — ошибка, не фильтр (R9) |
| валидация входа в `pipeline/check_*` | `domain/validation/` — 9 файлов стадии 1 (уровень 2) + `CHK-PERIOD-BOUNDS` |
| проверки настроек `settings/checks/v1..v11` | `settings/checks/<имя_проверки>.py` — 14 файлов уровня 1 (CHK-*) |
| `DayCard.open_at_start/open_at_end` | удалены (А.3 п.1); «кто на работе» — доска и история |
| `CalcMark.day` | удалено; день определяется нарезкой |
| `SettleResult` без нормализации записей стадии 2 | `OPENING_ROUNDED` возвращаются стадией 2 явно (R8); `PLAN_EQUALS_FACT` восстанавливает `build_trace` |

## Порты и адаптеры

| Было | Стало |
|---|---|
| `ports/clock.py` (`ClockPort`), `adapters/clock.py` | **удалены** (F-15): `now` — параметр use case'ов, снимается в composition root (`app/deps.py`) |
| — | `ports/employment.py` (`EmploymentPort`: `employment`, `active_employees`) → адаптер поверх `employment_periods` (R23/R38) |
| — | `ports/schedule_store.py` (`ShiftEntry(source)`), `ports/timesheet_store.py` (16.3/16.5) |
| `sql_schedule` — смены из `schedule_entries` по дням периода | выборка по **пересечению** с периодом (v7.1/F-04), включая ночные смены до `period.start`; валидация уровня 3 (`CHK-SHIFT-ORDER`, `CHK-ABSENCE-ORDER`, `CHK-ABSENCE-LENGTH`) |
| `sql_punch.sanitize()` — починка чередования | остаётся **первой линией** адаптера (1.3: исправление данных — ответственность адаптера и источника); домен при нарушении бросает `CHK-PUNCH-SEQUENCE` и не чинит |
| `sql_closings`: `PeriodState(closed, next_closed)` | `PeriodState(closed, previous_closed, next_closed, opening_bank_set)` (R26/R37); снимок флагов сохраняется при закрытии (7.2) |
| `sql_bank`: opening из `period_closings` | + `OPENING_SEED`-конвенция (R37): первый период — 0, посев корректировкой; `opening_bank_set` — из наличия посева |
| `bulk.py` — батч-порты доски | ≤ 5 запросов (R38): `last_marks`, `shifts_on_day`, `absences_on_day`, `active_employees`, `Settings` |

## Application / interface / API

| Было | Стало |
|---|---|
| `view_period(employee, period, ports)` — время из `ClockPort` | `view_period(employee, period, now)` + эффективный период (R23), отклонение при незакрытом предшественнике (R22/R26), отказ вне трудоустройства (R35) |
| `preview_close` (предпросмотр закрытия) | удалён: режимов четыре (R33) — `view` / чтение закрытого / `close` / `recalculate` |
| закрытый период: флаги пересчитывались живьём (`mgmt_api._row`) | снимок `FlagsResult` читается из хранилища (RUL-CLOSED-PERIOD-IMMUTABLE) |
| `recalculate`: отметки/Табель из `load_inputs` | то же, но **свежие** перечитывания закреплены тестами (R28); `ClosingInputs` заморожены |
| `periods.py`: только месяц | `months.py`: `month_period`/`half_month_period`, цепочка по `period_granularity` (R36), границы — трудоустройство (R35) |
| `presence_board` — статусная модель (present/stepped_out/expected) | `domain/board/` (`assemble_board`) + use case с фильтром `active_employees` (R38); структура `PresenceBoard` (a–d), `yet_to_come` — одна ближайшая запись (R40) |
| — | `view_sessions` (16.4) — вкладка «Факт»; `schedule_view` (16.3); `timesheet_edit` (16.5) |
| `factview.py` — «План/Факт» оверлей сетки на тяжёлом конвейере | **удалён** (16.1 п.2: тяжёлый конвейер — только УТ); отклонения — флаги в УТ, сессии — во «Факте» |
| `interface/formatting.py` — тексты 7 флагов | тексты 3 флагов + 8 Reason; `DayView.timesheet_plan_minutes` — два плана в карточке УТ (R39) |
| `api/mgmt_api` (месяц, mode=view/close) | период месяц/половина (R36), `PeriodOutsideEmploymentError`/RUL-VIEW-AFTER-PREVIOUS как типизированные отказы, «не в штате» дни (16.6) |
| `api/presence_api` — дубль «Кто на работе»/«Посещения» | одна вкладка «Отметки» — доска (a–d) |
| `api/tabel_api._apply_cell` — собственные копии правил | валидация записи доменными функциями (16.5/F-16) |
| `api/schedule.py` — цикл-редактор пишет `ScheduleEntry` | циклы пишут **Табель** (решение владельца 1); График — генерация из Табеля + manual-смены + логические отсутствия |
| `models.TimesheetRow` (legacy-расчёт) | **удалён** вместе со старым движком |
| `models.PeriodClosing` | + `flags_json` (снимок флагов), + `opening_seed`-признак через банк-адаптер; `DeferredCarry.reason_code` — удалить |
| `ScheduleEntry.partial_shift_id/from_time/until_time` | отсутствие — UTC-интервал, может через полночь: `until_next_day` |

## Тесты

| Было | Стало |
|---|---|
| `test_acceptance.py` — F1–F39 (46 тестов старой спеки) | EX-01…EX-55, каждый подкейс — отдельный тест, полное сравнение результата в канонической форме |
| `test_units.py`, `test_validation.py` — под старую модель | юниты на каждую функцию каталога 8.1; валидация трёх уровней (включая `CHK-PUNCH-SEQUENCE`, `CHK-PERIOD-BOUNDS`, уровень 3 адаптера) |
| `test_invariants_property.py` | + фаззинг «размещение → каскад → повторное размещение» (шаги 15/30/60), INV-DETERMINISM с перестановкой отметок и `deferred_in` |
| `test_architecture.py` | граф импортов по 8.1; `settle()` не импортирует `flags/`; флаги — вход только `Mapping[date, bool]`; доска/история независимы; `presence_board` без тяжёлого конвейера; ≤ 5 запросов доски |
| `test_application.py` | truth table четырёх режимов (R33), R35–R40, атомарность, эффективный период |
| покрытие domain | ≥ 95 % (DoD) |
