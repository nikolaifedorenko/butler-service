# 03. Матрица «право ↔ маршрут ↔ UI» (сгенерировано `docs/audit/scripts/perm_matrix.py`)

Коммит `3801abf`. Источник прав — `app/core/permissions.py` (`PERMISSIONS`, `ROLE_DEFAULTS`). «UI» — строки JS, где ключ права встречается литералом (обычно `can('…')`, реестр экранов настроек или пунктов меню).

| Право | admin | manager | supervisor | employee | Маршруты (метод путь) | UI (файл:строка) |
|---|---|---|---|---|---|---|
| `presence.view` — Просмотр присутствия | ✔ | ✔ | ✔ | ✔ | GET `/api/presence/board`<br>GET `/api/fact/sessions`<br>GET `/api/fact/month`<br>GET `/api/fact/day` | `app.js:39`, `app.js:53` |
| `schedule.view` — Просмотр графика | ✔ | ✔ | ✔ | ✔ | GET `/api/schedule`<br>GET `/api/schedule/timeoff-hours`<br>GET `/api/schedule/absence-period`<br>GET `/api/schedule/pdf` | `app.js:38` |
| `schedule.edit` — Редактирование графика | ✔ | ✔ | ✔ |  | PUT `/api/schedule/shift`<br>DELETE `/api/schedule/shift`<br>POST `/api/schedule/absence`<br>DELETE `/api/schedule/absence/{absence_id}`<br>POST `/api/schedule/range-absence`<br>GET `/api/schedule/patterns`<br>POST `/api/schedule/fill-pattern`<br>POST `/api/schedule/continue`<br>POST `/api/schedule/copy`<br>POST `/api/schedule/clear-month`<br>POST `/api/schedule/reset-month`<br>GET `/api/schedule/xlsx` | `modules/timesheet_layers.js:21` |
| `schedule.view_all` — Полные данные сетки (заметки и id записей в ячейках) | ✔ | ✔ | ✔ |  | — | — |
| `fact.view_all` — Сессии и сетка «Номера» всех сотрудников | ✔ | ✔ | ✔ |  | — | — |
| `tabel.view` — Просмотр Табеля | ✔ | ✔ | ✔ |  | GET `/api/tabel` | `app.js:37` |
| `tabel.edit` — Редактирование Табеля | ✔ | ✔ | ✔ |  | PUT `/api/tabel/cell`<br>POST `/api/tabel/bulk`<br>POST `/api/tabel/fill-from-cycles`<br>POST `/api/tabel/reset` | — |
| `mgmt.view` — Просмотр (view) | ✔ | ✔ | ✔ |  | GET `/api/mgmt`<br>GET `/api/mgmt/periods`<br>GET `/api/mgmt/xlsx` | `app.js:40` |
| `mgmt.close` — Закрытие периода (close) | ✔ | ✔ | ✔ |  | POST `/api/mgmt/close` | — |
| `mgmt.recalculate` — Пересчёт последнего закрытого | ✔ | ✔ |  |  | POST `/api/mgmt/recalculate` | — |
| `punches.manage` — Ручные отметки и отмена отметок | ✔ | ✔ | ✔ |  | DELETE `/api/punches/{punch_id}` | — |
| `punches.view_all` — Журнал отметок всех сотрудников и комментарии к чужим | ✔ | ✔ | ✔ |  | — | — |
| `punches.punch_for_others` — Отметка за другого сотрудника | ✔ | ✔ | ✔ |  | — | — |
| `punches.backfill` — Отметка задним числом (произвольное время) | ✔ | ✔ | ✔ |  | — | — |
| `employees.view` — Просмотр сотрудников | ✔ | ✔ | ✔ |  | GET `/api/employees`<br>GET `/api/group-choices`<br>POST `/api/employees/suggest-genitive`<br>GET `/api/employees/{employee_id}/bank-adjustments`<br>GET `/api/employees/{employee_id}/history`<br>GET `/api/departments`<br>GET `/api/subdivisions` | `app.js:54`, `modules/employees.js:50`, `modules/timesheet_layers.js:271`, `modules/timesheet_v4.js:344`, `modules/timesheet_v4.js:569` |
| `employees.edit` — Редактирование сотрудников и банка | ✔ | ✔ | ✔ |  | POST `/api/employees`<br>PUT `/api/employees/{employee_id}`<br>POST `/api/employees/{employee_id}/position-change`<br>POST `/api/employees/{employee_id}/block-change`<br>POST `/api/employees/{employee_id}/dismiss`<br>POST `/api/employees/{employee_id}/rehire`<br>POST `/api/employees/{employee_id}/bank-adjust`<br>DELETE `/api/employees/{employee_id}/bank-adjustments/{adjustment_id}`<br>POST `/api/employees/{employee_id}/deactivate`<br>POST `/api/employees/{employee_id}/delete` | `modules/employees.js:75` |
| `employees.impersonate` — Войти как сотрудник (имперсонация) | ✔ | ✔ | ✔ |  | POST `/api/auth/impersonate`<br>GET `/api/auth/employees-for-demo` | `modules/employees.js:128` |
| `settings.view` — Просмотр настроек | ✔ | ✔ | ✔ |  | GET `/api/shift-types/{type_id}/revisions`<br>GET `/api/engine-settings`<br>GET `/api/engine-settings/modifiers`<br>GET `/api/engine-settings/health`<br>GET `/api/engine-settings/rules/resolve`<br>GET `/api/settings`<br>GET `/api/docs/kinds`<br>GET `/api/docs/templates`<br>GET `/api/docs/sample`<br>POST `/api/docs/render`<br>GET `/api/doublepay` | `app.js:58`, `modules/cars.js:54`, `modules/night.js:150` |
| `settings.edit` — Изменение настроек и справочников | ✔ | ✔ |  |  | POST `/api/departments`<br>PUT `/api/departments/{dep_id}`<br>DELETE `/api/departments/{dep_id}`<br>POST `/api/subdivisions`<br>PUT `/api/subdivisions/{sub_id}`<br>DELETE `/api/subdivisions/{sub_id}`<br>POST `/api/shift-types`<br>PUT `/api/shift-types/{type_id}`<br>DELETE `/api/shift-types/{type_id}`<br>POST `/api/shift-types/{type_id}/restore`<br>PUT `/api/engine-settings`<br>POST `/api/engine-settings/modifiers`<br>DELETE `/api/engine-settings/modifiers/{mod_id}`<br>PUT `/api/settings/doc`<br>PUT `/api/settings/base`<br>PUT `/api/settings`<br>POST `/api/docs/kinds`<br>PUT `/api/docs/kinds/{kind_id}`<br>DELETE `/api/docs/kinds/{kind_id}`<br>POST `/api/docs/templates`<br>DELETE `/api/docs/templates`<br>POST `/api/doublepay/days`<br>DELETE `/api/doublepay/days/{day_id}`<br>POST `/api/doublepay/vip`<br>DELETE `/api/doublepay/vip/{vip_id}`<br>GET `/api/notify/config`<br>PUT `/api/notify/config`<br>POST `/api/notify/telegram/check`<br>POST `/api/notify/telegram/chats`<br>GET `/api/notify/chats`<br>POST `/api/notify/telegram/test`<br>POST `/api/notify/email/test`<br>GET `/api/notify/dispatches`<br>GET `/api/notify/dispatches/export.csv`<br>POST `/api/notify/dispatches/{dispatch_id}/resend`<br>GET `/api/notify/templates`<br>PUT `/api/notify/templates/{domain}`<br>POST `/api/notify/templates/{domain}/preview` | `modules/dicts.js:217`, `modules/settings.js:70`, `modules/settings.js:359`, `modules/settings.js:660`, `modules/settings.js:662`, `modules/settings.js:663`, `modules/settings.js:744`, `modules/settings.js:948`, `modules/settings.js:1257`, `modules/settings.js:1548`, `modules/settings.js:1690`, `modules/settings.js:1758`, `modules/settings.js:1778`, `modules/settings.js:1877`, `modules/settings.js:1992`, `modules/timesheet_v4.js:1262` |
| `access.manage` — Управление правами доступа | ✔ |  |  |  | GET `/api/access`<br>PUT `/api/access/roles/{role}`<br>POST `/api/access/groups`<br>PUT `/api/access/groups/{group_id}`<br>DELETE `/api/access/groups/{group_id}`<br>PUT `/api/access/groups/{group_id}/grants`<br>PUT `/api/access/groups/{group_id}/members`<br>PUT `/api/access/users/{user_id}/grants` | `app.js:58`, `modules/settings.js:72`, `modules/settings.js:2014` |
| `audit.view` — Просмотр журнала аудита | ✔ | ✔ | ✔ |  | GET `/api/audit`<br>GET `/api/audit/csv` | `app.js:58`, `modules/settings.js:73` |
| `me.punch` — Отмечаться «Пришёл/Ушёл» | ✔ | ✔ | ✔ | ✔ | — | `app.js:55` |
| `night.view` — Ночной отчёт | ✔ | ✔ | ✔ | ✔ | GET `/api/night/areas`<br>GET `/api/night/zones`<br>GET `/api/night/zones/{zone_id}/items`<br>GET `/api/night/areas/{area_id}/checklist`<br>GET `/api/night/services`<br>GET `/api/night/today`<br>GET `/api/night/reports`<br>GET `/api/night/reports/{report_id}`<br>GET `/api/night/reports/{report_id}/defects`<br>POST `/api/night/reports/{report_id}/dispatch`<br>GET `/api/night/reports/{report_id}/dispatches`<br>POST `/api/night/reports/{report_id}/defects/preview`<br>GET `/api/night/reports/{report_id}/cars`<br>GET `/api/night/reports/{report_id}/export.docx`<br>GET `/api/night/reports/{report_id}/export.pdf` | `app.js:56`, `modules/settings.js:66`, `modules/settings.js:2093` |
| `night.edit` — Зоны, объекты, чек-листы, службы | ✔ | ✔ | ✔ |  | POST `/api/night/areas/bulk`<br>POST `/api/night/areas`<br>PUT `/api/night/areas/{area_id}`<br>DELETE `/api/night/areas/{area_id}`<br>POST `/api/night/areas/{area_id}/items`<br>PUT `/api/night/items/{item_id}`<br>DELETE `/api/night/items/{item_id}`<br>POST `/api/night/zones`<br>PUT `/api/night/zones/{zone_id}`<br>DELETE `/api/night/zones/{zone_id}`<br>POST `/api/night/zones/{zone_id}/items`<br>PUT `/api/night/zone-items/{item_id}`<br>DELETE `/api/night/zone-items/{item_id}`<br>PUT `/api/night/areas/{area_id}/overrides/{zone_item_id}`<br>DELETE `/api/night/areas/{area_id}/overrides/{zone_item_id}`<br>POST `/api/night/services`<br>PUT `/api/night/services/{service_id}`<br>DELETE `/api/night/services/{service_id}`<br>GET `/api/notify/chats` | — |
| `night.close` — Закрытие и переоткрытие смены/объектов | ✔ | ✔ | ✔ |  | POST `/api/night/sections/{section_id}/reopen`<br>POST `/api/night/reports/{report_id}/close`<br>POST `/api/night/reports/{report_id}/reopen` | `modules/night.js:164`, `modules/night.js:165` |
| `cars.view` — Просмотр парка и истории | ✔ | ✔ | ✔ | ✔ | GET `/api/cars/meta`<br>GET `/api/cars/locations`<br>GET `/api/cars`<br>GET `/api/cars/{car_id}/history` | `app.js:57`, `modules/settings.js:67`, `modules/settings.js:2098` |
| `cars.use` — Взять / вернуть / передать кар | ✔ | ✔ | ✔ | ✔ | POST `/api/cars/{car_id}/take`<br>POST `/api/cars/{car_id}/handover`<br>POST `/api/cars/{car_id}/return` | — |
| `cars.issue` — Выдать, закрепить, сменить статус | ✔ | ✔ | ✔ |  | POST `/api/cars/{car_id}/give`<br>POST `/api/cars/{car_id}/assign`<br>POST `/api/cars/{car_id}/status` | — |
| `cars.manage` — Парк и места стоянки: создание, правка, удаление | ✔ | ✔ |  |  | DELETE `/api/cars/locations/{loc_id}`<br>POST `/api/cars/locations`<br>PUT `/api/cars/locations/{loc_id}`<br>POST `/api/cars`<br>PUT `/api/cars/{car_id}` | — |

Право без маршрута и без UI: `schedule.view_all`, `fact.view_all`, `punches.view_all`, `punches.punch_for_others`, `punches.backfill`

## Маршруты без права (только вход или вообще без входа)

- POST `/api/auth/login` — `нет` — `app/modules/access/interface/auth_routes.py:113`
- GET `/api/auth/login-form` — `нет` — `app/modules/access/interface/auth_routes.py:123`
- POST `/api/auth/login-form` — `нет` — `app/modules/access/interface/auth_routes.py:134`
- POST `/api/auth/logout` — `current_principal` — `app/modules/access/interface/auth_routes.py:158`
- GET `/api/auth/me` — `current_principal` — `app/modules/access/interface/auth_routes.py:175`
- POST `/api/auth/change-password` — `current_principal` — `app/modules/access/interface/auth_routes.py:203`
- POST `/api/auth/impersonate/stop` — `current_principal` — `app/modules/access/interface/auth_routes.py:243`
- GET `/api/tabel-values` — `current_principal` — `app/modules/employees/interface/employees.py:729`
- GET `/api/shift-types` — `current_principal` — `app/modules/employees/interface/employees.py:759`
- GET `/api/shift-types/tabel-codes` — `current_principal` — `app/modules/employees/interface/employees.py:779`
- GET `/api/punches/status` — `current_principal` — `app/modules/timesheet/interface/punches.py:210`
- POST `/api/punches` — `current_principal` — `app/modules/timesheet/interface/punches.py:222`
- GET `/api/punches` — `current_principal` — `app/modules/timesheet/interface/punches.py:351`
- PUT `/api/punches/{punch_id}/note` — `current_principal` — `app/modules/timesheet/interface/punches.py:410`
- POST `/api/night/sections/{section_id}/take` — `current_principal` — `app/modules/night/interface/night_api.py:924`
- POST `/api/night/sections/{section_id}/close` — `current_principal` — `app/modules/night/interface/night_api.py:965`
- PUT `/api/night/items/{item_id}/answer` — `current_principal` — `app/modules/night/interface/night_api.py:1004`
- POST `/api/night/items/{item_id}/photo` — `current_principal` — `app/modules/night/interface/night_api.py:1032`
- GET `/api/night/photos/{photo_id}/file` — `current_principal` — `app/modules/night/interface/night_api.py:1128`
- POST `/api/night/reports/{report_id}/cars/{car_id}/check` — `current_principal` — `app/modules/night/interface/night_api.py:1162`
- POST `/api/night/reports/{report_id}/cars/finish` — `current_principal` — `app/modules/night/interface/night_api.py:1240`
- DELETE `/api/night/photos/{photo_id}` — `current_principal` — `app/modules/night/interface/night_api.py:1317`
- GET `/api/photos/limits` — `current_principal` — `app/core/media_api.py:32`
- GET `/api/photos/{photo_id}/file` — `current_principal` — `app/core/media_api.py:39`
- DELETE `/api/photos/{photo_id}` — `current_principal` — `app/core/media_api.py:50`
- GET `/api/selfcheck` — `optional_principal` — `app/main.py:282`
- GET `/api/health` — `нет` — `app/main.py:302`

## Проверки по РОЛИ, а не по праву: бэкенд

- `app/core/media.py:414`: `if photo.uploaded_by != principal.user.id and not principal.is_manager:`
- `app/core/permissions.py:113`: `return effective_permissions(db, principal.user.id, principal.role) if not principal.impersonated \`
- `app/main.py:296`: `if principal is not None and principal.is_admin:`
- `app/modules/cars/application/cars.py:241`: `manager = principal.role in ("supervisor", "manager", "admin")`
- `app/modules/cars/application/cars.py:294`: `manager = principal.role in ("supervisor", "manager", "admin")`
- `app/modules/cars/application/cars.py:353`: `if principal.role not in ("manager", "admin"):`
- `app/modules/cars/application/cars.py:356`: `if principal.role not in ("manager", "admin"):`
- `app/modules/cars/interface/cars_api.py:150`: `show_all = principal.role in ("admin", "manager", "supervisor")`
- `app/modules/employees/interface/employees.py:390`: `if principal.role not in (ROLE_ADMIN, ROLE_MANAGER):`
- `app/modules/night/interface/night_api.py:948`: `if principal.user.id != sec.closed_by and principal.role not in ("supervisor", "manager", "admin"):`
- `app/modules/timesheet/interface/doublepay.py:47`: `if principal.role not in (ROLE_ADMIN, ROLE_MANAGER):`

## Проверки по РОЛИ, а не по праву: фронтенд

- `static/js/app.js:239`: `const order = state.user?.role === 'employee'`
- `static/js/app.js:296`: `if (state.user.role !== 'employee') {`
- `static/js/modules/cars.js:313`: `${state.user?.role !== 'employee' ? personFieldHtml('cr') : ''}`
- `static/js/modules/cars.js:339`: `const person = state.user?.role !== 'employee' ? personFieldValue('cr') : { employee_id: null, name: '' };`
- `static/js/modules/employees.js:408`: `const roleOptions = state.user?.role === 'admin' ? ['employee', 'supervisor', 'manager', 'admin']`
- `static/js/modules/employees.js:409`: `: state.user?.role === 'manager' ? ['employee', 'supervisor', 'manager']`
- `static/js/modules/timesheet_layers.js:10`: `if (state.user?.role === 'employee' && !state.shiftTypes.length) {`
- `static/js/modules/timesheet_layers.js:140`: `if (state.user?.role === 'employee') {`

> Примечание аудитора. Пять «прав без маршрута» на деле используются: их проверяют внутри
> обработчиков через `has_perm` и `principal_permissions`, а не через `require_perm`. Места:
> `punches.py:87` (`punch_for_others`), `punches.py:237-252` (`backfill`, `manage`),
> `punches.py:358` (`view_all`), `fact_api.py:54` (`fact.view_all`), `schedule.py:381`
> (`schedule.view_all`). UI на эти ключи не смотрит: кнопки ручной отметки зависят от
> других условий (см. 12-ui-api.md).
