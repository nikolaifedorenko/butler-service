# Изменения 20.10.2026 — этап B: унификация прав (require_perm вместо ролевых зависимостей)

Исполнение `docs/archive/EXECUTION-SPEC-v2.md` (§5.2, этап B; план — PR #51). Единственный
вход проверки прав — `require_perm("<ключ>")` из каталога `PERMISSIONS`; ролевые
зависимости `require_manager` / `require_supervisor` / `require_admin` удалены из
`app/auth.py` (require_admin не использовался). Продолжение подхода `night.edit`
(PR #50): аудитория по умолчанию не меняется, но каждое право становится
управляемым грантами роли/группы/пользователя в «Настройках → Права доступа».

## 1. Новые ключи каталога

| Ключ | Раздел | Базово | Что заменяет |
|------|--------|--------|--------------|
| `night.close` | Ночной отчёт | supervisor+ | `require_supervisor` на закрытии/переоткрытии смены и переоткрытии объектов |
| `employees.impersonate` | Сотрудники | supervisor+ | `require_manager` на «Войти как сотрудник» и списке сотрудников для демо |

`can_manage_user` (страж иерархии ролей, анти-эскалация) сохранён без изменений —
второй страж имперсонации; плоский каталог ключей иерархию не выражает.

## 2. Карта замен (44 вызова в 8 файлах)

| Эндпоинты | Было | Стало |
|-----------|------|-------|
| `settings_api`: GET | require_manager | `settings.view` |
| `settings_api`: PUT ×3 | require_manager | `settings.edit` |
| `docs_api`: GET kinds/templates/sample, POST render | require_manager | `settings.view` |
| `docs_api`: мутации kinds/templates ×5 | require_manager | `settings.edit` |
| `doublepay`: GET | require_manager | `settings.view` |
| `doublepay`: мутации ×4 | require_manager | `settings.edit` |
| `employees`: group-choices, suggest-genitive, GET departments/subdivisions | require_manager | `employees.view` |
| `employees`: мутации departments/subdivisions ×6, shift-types ×4 | require_manager | `settings.edit` |
| `employees`: GET shift-types/{id}/revisions | require_manager | `settings.view` |
| `night_api`: close/reopen отчёта, reopen объекта ×3 | require_supervisor | `night.close` |
| `notify_api`: GET /chats (каталог для карточки службы) | require_manager | `settings.edit` ИЛИ `night.edit` |
| `notify_api`: журнал, CSV-выгрузка, resend ×3 | require_manager | `settings.edit` |
| `schedule`: GET /xlsx (экспорт Графика) | require_manager | `schedule.edit` |
| `auth_routes`: impersonate, employees-for-demo ×2 | require_manager | `employees.impersonate` |

Чтение везде сохранено для прежней аудитории (supervisor+ имеет settings.view /
employees.view / schedule.edit). Кнопка «Войти как сотрудник» в карточке и кнопки
закрытия/переоткрытия смены в «Ночном отчёте» переведены на `can(...)` — ролевая
проверка `nightIsSupervisor()` удалена из интерфейса.

## 3. Задокументированные ужесточения (сервер стал как интерфейс)

Раньше сервер разрешал супервайзеру больше, чем показывал UI (кнопки правок у него
и так скрыты за `settings.edit`). Теперь граница одна:

* супервайзер БЕЗ гранта не пишет: настройки, документы/бланки, двойные оплаты,
  департаменты/подразделения, словарь смен (всё — `settings.edit`);
* супервайзер без `cars.manage` не видит отключённые кары в парке
  (`GET /api/cars` — фильтр и `can_manage` по одному ключу);
* общий журнал доставок и его CSV — `settings.edit` (экран «Чаты и Почта»
  супервайзер и так не видел).

Любое ужесточение снимается грантом в «Правах доступа» — тест
`test_grant_vozvrashchaet_supervisoru_zapis` это фиксирует.

## 4. Отложено до этапа C (модульные фазы)

Inline-ветвления `principal.is_manager` (14 шт.) не переводились — они про
«менеджерскую видимость» внутри доменов и поедут вместе со своими модулями:
`fact_api` ×4, `punches` ×5, `schedule` ×2, `photos` ×1 (+ свойство
`Principal.is_manager` остаётся для них). `cars_api` — единственное переведённое
(видимость неактивных каров → `cars.manage`).

## 5. Тесты

* Новые: `tests/test_permissions_unification.py` (9 шт.) — каталог, отсутствие
  ролевых зависимостей, night.close на смене/объектах, имперсонация
  (с can_manage_user), чтение-без-записи супервайзера, грант возвращает запись,
  каталог чатов по night.edit, Excel Графика, неактивные кары по cars.manage.
* Приведены к новой границе: `test_api.py` 15d/15f (запись настроек — админом),
  `test_night_export_v2.py` (CSV общего журнала: супервайзер 403 вместо 200 —
  прежнее поведение было ролевым).

## 6. Проверки

pytest **637 passed / 0 failed**; ruff ✓; lint-imports 3/3 ✓; check_api_contract ✓;
export_openapi --check ✓ (дельты нет); gen_js_globals --check ✓ (320 имён);
eslint 0 ошибок; сценарии: settings 76/76 (admin), night_zones 87/87 (gromova —
супервайзер проходит службы/чат-каталог по night.edit), layers 68/68;
run_ui_check ×3 роли — 0 сбоев. night_cars-сценарий — 8 предсуществующих
средовых провалов (загрузка фото в jsdom/Node 20; идентично на базовой ветке,
в CI на Node 22 зелёный).
