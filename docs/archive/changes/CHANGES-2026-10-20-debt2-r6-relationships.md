# Изменения 20.10.2026 — долг №2 закрыт: R6 полностью (кросс-модульные relationship удалены)

Решение владельца: вариант B (полный fix). Все 9 кросс-модульных `relationship()`
удалены; навигации заменены явными запросами/батч-словарями. `CROSS_RELATIONSHIPS`
в `tests/test_modules_architecture.py` — **пустой allowlist**: новая кросс-модульная
связь падает тестом. R6 выполнен буквально: FK — только строкой, `relationship()` —
только внутри своего модуля **или на core** (core — общая инфраструктура, его
импорт разрешён всем; обратное направление запрещено R5).

## 1. Удалённые связи и замена навигаций

| Удалено (владелец → цель) | Чем заменено у потребителей |
|---|---|
| `Punch.employee` (lazy=joined) | журнал отметок: батч-словарь сотрудников на страницу (`select(Employee).where(id.in_(…))`) — вместо JOIN на каждый запрос |
| `ScheduleShift.employee`, `ScheduleAbsence.employee` (lazy=joined) | навигаций не было — связи мертвым грузом джойнили таблицы во всех запросах Графика; удаление — чистый выигрыш |
| `BlockAssignment.employee`, `BankAdjustment.employee`, `DoublePayDay.employee` | навигаций не было |
| `VipDoublePay.employee` | `_vip_dict` (doublepay): `object_session(v).get(Employee, v.employee_id)` — identity map делает повторные чтения в списке бесплатными |
| `User.employee` (core → employees — нарушение R5) | `access_api.catalog`: батч-запрос `Employee.id in {u.employee_id}` (FK живёт на стороне User) |
| `Employee.assigned_car` | `_emp_dict` (employees): предзагруженная карта `cars_by_employee` (списки, как было) либо один запрос `Car.assigned_to == e.id` (карточка) |
| `Car.assigned_employee` | `cars.py`: хелпер `_assigned_name(car)` — `object_session(car).get(Employee, car.assigned_to)`; в take/assign — `db.get(Employee, …)` |
| `CarNightCheck.report` (cars → night) | навигаций не было (ночной обход и так ходит по `report_id` строковым FK) |

**Сохранены (легальны по R6):** связи внутри модулей (Department.employees,
Employee.department/contacts, night-внутренние, CarHistory.car), а также
`Employee.user → User` (employees → core: односторонняя, back_populates снят)
и `AuditLog.actor → User` (внутри core). `Employee.user` интенсивно используется
карточкой сотрудника (роль, пароль, активность, joinedload в списке) — связь
с core не создаёт модульной связности.

## 2. Производительность и бюджеты

* `test_query_budget` зелёный без изменений: lazy=joined не добавлял запросов
  (JOIN внутри тех же запросов), батч-словарь журнала — +1 запрос на страницу
  (журнал вне бюджета); identity-map (`db.get`) в списках каров/двойных —
  по одному чтению на уникального сотрудника (как прежняя ленивая загрузка).
* Сетка Графика и запросы смен/отсутствий стали легче: убраны два постоянных
  JOIN на `employees`, которые никто не читал.
* Поведение ответов побайтово прежнее: те же поля (`employee`, `position`,
  `assigned_name`, `assigned_car_*`, `name` в каталоге прав), тот же фолбэк
  для отсутствующего сотрудника (пустая строка / `#id`).

## 3. Механика

* ORM: удалены связи + TYPE_CHECKING-импорты чужих каталогов (timesheet,
  employees, cars), `core/identity` больше не упоминает Employee (R5 — core
  чист); docstring'и модулей и каталогов обновлены.
* AST-тест R6 переработан: «цель — свой unit или core» легально; unit для core —
  весь core (все файлы); `CROSS_RELATIONSHIPS = {}` (точный пустой список —
  страж от возврата долга).
* `access_api`: батч-запрос сотрудников через `employees.application` (R3).

## 4. Проверки

* pytest день: **707 passed / 4 skipped**; «ночь» (faketime): **707 / 4**;
* ruff ✓ (весь репозиторий); lint-imports **14/14** ✓; openapi **без дельты** ✓;
* сценарии: **night_cars ✓** (закрепление/взятие/возврат кара — главные
  потребители assigned_employee), night_zones ✓, settings ✓;
* `run_ui_check` admin + ivanov: 0 пустых разделов, 0 ошибок консоли
  (экран «Права доступа» — имена пользователей из батч-запроса).

## 5. Итог по трём долгам

| Долг | Статус |
|---|---|
| №3 TZ/now (dt.date.today) | закрыт — PR #61 |
| №1 is_manager → права | закрыт — PR #62 |
| №2 R6 relationship | закрыт — этот батч |

EXECUTION-SPEC-v2 исполнен полностью, зарегистрированных долгов нет.
