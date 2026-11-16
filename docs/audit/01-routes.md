# 01. Маршруты API (сгенерировано `docs/audit/scripts/routes_inventory.py`)

Коммит: `3801abf`. Всего строк «метод + путь»: **191**, уникальных путей: **159**, `async def`: **4**.

Легенда. **Авторизация**: `perm:a|b` — `require_perm` (хотя бы одно право); `current_principal` — любой вошедший; `нет` — без входа. **Роль в теле** — в обработчике встречаются проверки роли/прав вручную (`is_admin`, `.role`, `has_perm`, `can_manage_user`, `impersonated`). **audit** — глубина вызова `audit()` от обработчика (0 — прямо в нём, 1–3 — во вложенном сервисе; `—` — не найден в пределах 3 уровней). **Сущности** — ORM-классы, упомянутые в обработчике и вызываемых им функциях app.* (до 3 уровней).

| # | Метод | Путь | Файл:строка → функция | async | Авторизация | Роль в теле | audit | commit | Сущности |
|---|---|---|---|---|---|---|---|---|---|
| 1 | GET | `/metrics` | `app/core/observability.py:178` → `metrics_endpoint` | def | `нет` |  | — |  |  |
| 2 | POST | `/api/auth/login` | `app/modules/access/interface/auth_routes.py:113` → `login` | def | `нет` |  | 0 | да | AuditLog, Employee, User |
| 3 | GET | `/api/auth/login-form` | `app/modules/access/interface/auth_routes.py:123` → `login_form_get` | def | `нет` |  | — |  |  |
| 4 | POST | `/api/auth/login-form` | `app/modules/access/interface/auth_routes.py:134` → `login_form` | def | `нет` |  | 0 | да | AuditLog, Employee, User |
| 5 | POST | `/api/auth/logout` | `app/modules/access/interface/auth_routes.py:158` → `logout` | def | `current_principal` |  | 0 | да | AuditLog |
| 6 | GET | `/api/auth/me` | `app/modules/access/interface/auth_routes.py:175` → `me` | def | `current_principal` | principal_permissions | — |  |  |
| 7 | POST | `/api/auth/change-password` | `app/modules/access/interface/auth_routes.py:203` → `change_password` | def | `current_principal` | impersonated | 0 | да | AuditLog, User |
| 8 | POST | `/api/auth/impersonate` | `app/modules/access/interface/auth_routes.py:227` → `impersonate` | def | `perm:employees.impersonate` |  | 0 | да | AccessGrant, AuditLog, Employee, User |
| 9 | POST | `/api/auth/impersonate/stop` | `app/modules/access/interface/auth_routes.py:243` → `stop_impersonate` | def | `current_principal` | impersonated | 0 | да | AuditLog, Employee, User |
| 10 | GET | `/api/auth/employees-for-demo` | `app/modules/access/interface/auth_routes.py:256` → `employees_for_demo` | def | `perm:employees.impersonate` |  | — |  | AccessGrant, Employee |
| 11 | GET | `/api/employees` | `app/modules/employees/interface/employees.py:178` → `list_employees` | def | `perm:employees.view` |  | — |  | AccessGrant, Car, Employee |
| 12 | GET | `/api/group-choices` | `app/modules/employees/interface/employees.py:192` → `group_choices` | def | `perm:employees.view` |  | — |  | AccessGrant |
| 13 | POST | `/api/employees/suggest-genitive` | `app/modules/employees/interface/employees.py:205` → `suggest_genitive_api` | def | `perm:employees.view` |  | — |  | AccessGrant |
| 14 | POST | `/api/employees` | `app/modules/employees/interface/employees.py:212` → `create_employee` | def | `perm:employees.edit` | role | 0 | да | AccessGrant, AuditLog, BlockAssignment, Car, Department, EmergencyContact, Employee, EmploymentPeriod, PositionHistory, User |
| 15 | PUT | `/api/employees/{employee_id}` | `app/modules/employees/interface/employees.py:264` → `update_employee` | def | `perm:employees.edit` | role | 0 | да | AccessGrant, AuditLog, BlockAssignment, Car, Department, EmergencyContact, Employee, EmploymentPeriod, PositionHistory, User |
| 16 | POST | `/api/employees/{employee_id}/position-change` | `app/modules/employees/interface/employees.py:340` → `position_change` | def | `perm:employees.edit` |  | 1 | да | AccessGrant, AuditLog, Car, Employee, PositionHistory |
| 17 | POST | `/api/employees/{employee_id}/block-change` | `app/modules/employees/interface/employees.py:348` → `block_change` | def | `perm:employees.edit` |  | 1 | да | AccessGrant, AuditLog, BlockAssignment, Car, Employee |
| 18 | POST | `/api/employees/{employee_id}/dismiss` | `app/modules/employees/interface/employees.py:356` → `dismiss_employee` | def | `perm:employees.edit` |  | 1 | да | AccessGrant, AuditLog, Car, Employee, EmploymentPeriod, User |
| 19 | POST | `/api/employees/{employee_id}/rehire` | `app/modules/employees/interface/employees.py:376` → `rehire_employee` | def | `perm:employees.edit` |  | 1 | да | AccessGrant, AuditLog, BlockAssignment, Car, Employee, EmploymentPeriod, PositionHistory |
| 20 | POST | `/api/employees/{employee_id}/bank-adjust` | `app/modules/employees/interface/employees.py:422` → `bank_adjust` | def | `perm:employees.edit` |  | 0 | да | AccessGrant, AuditLog, BankAdjustment, Employee, PeriodClosing |
| 21 | GET | `/api/employees/{employee_id}/bank-adjustments` | `app/modules/employees/interface/employees.py:457` → `bank_adjustments` | def | `perm:employees.view` |  | — |  | AccessGrant, BankAdjustment, Employee, PeriodClosing |
| 22 | DELETE | `/api/employees/{employee_id}/bank-adjustments/{adjustment_id}` | `app/modules/employees/interface/employees.py:471` → `bank_adjust_delete` | def | `perm:employees.edit` |  | 0 | да | AccessGrant, AuditLog, BankAdjustment, Employee, PeriodClosing |
| 23 | GET | `/api/employees/{employee_id}/history` | `app/modules/employees/interface/employees.py:486` → `employee_history` | def | `perm:employees.view` |  | — |  | AccessGrant, BankAdjustment, BlockAssignment, Employee, EmploymentPeriod, PeriodClosing, PositionHistory |
| 24 | POST | `/api/employees/{employee_id}/deactivate` | `app/modules/employees/interface/employees.py:539` → `deactivate_employee` | def | `perm:employees.edit` |  | 0 | да | AccessGrant, AuditLog, Car, Employee, User |
| 25 | POST | `/api/employees/{employee_id}/delete` | `app/modules/employees/interface/employees.py:560` → `delete_employee` | def | `perm:employees.edit` |  | 0 | да | AccessGrant, AuditLog, Car, Employee, User |
| 26 | GET | `/api/departments` | `app/modules/employees/interface/employees.py:582` → `list_departments` | def | `perm:employees.view` |  | — |  | AccessGrant, Department |
| 27 | POST | `/api/departments` | `app/modules/employees/interface/employees.py:592` → `create_department` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, Department |
| 28 | PUT | `/api/departments/{dep_id}` | `app/modules/employees/interface/employees.py:607` → `rename_department` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, Department |
| 29 | DELETE | `/api/departments/{dep_id}` | `app/modules/employees/interface/employees.py:626` → `delete_department` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, Department, Employee |
| 30 | GET | `/api/subdivisions` | `app/modules/employees/interface/employees.py:644` → `list_subdivisions` | def | `perm:employees.view` |  | — |  | AccessGrant, Subdivision |
| 31 | POST | `/api/subdivisions` | `app/modules/employees/interface/employees.py:654` → `create_subdivision` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, Subdivision |
| 32 | PUT | `/api/subdivisions/{sub_id}` | `app/modules/employees/interface/employees.py:669` → `rename_subdivision` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, Employee, Subdivision |
| 33 | DELETE | `/api/subdivisions/{sub_id}` | `app/modules/employees/interface/employees.py:694` → `delete_subdivision` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, Employee, Subdivision |
| 34 | GET | `/api/tabel-values` | `app/modules/employees/interface/employees.py:729` → `tabel_values` | def | `current_principal` |  | — |  | EngineSettingsVersion |
| 35 | GET | `/api/shift-types` | `app/modules/employees/interface/employees.py:759` → `list_shift_types` | def | `current_principal` |  | — |  | ShiftRevision, ShiftType |
| 36 | GET | `/api/shift-types/tabel-codes` | `app/modules/employees/interface/employees.py:779` → `shift_tabel_codes` | def | `current_principal` |  | — |  | EngineSettingsVersion |
| 37 | POST | `/api/shift-types` | `app/modules/employees/interface/employees.py:815` → `create_shift_type` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, ShiftType |
| 38 | PUT | `/api/shift-types/{type_id}` | `app/modules/employees/interface/employees.py:829` → `update_shift_type` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, ShiftRevision, ShiftType |
| 39 | DELETE | `/api/shift-types/{type_id}` | `app/modules/employees/interface/employees.py:878` → `delete_shift_type` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, ShiftRevision, ShiftType |
| 40 | POST | `/api/shift-types/{type_id}/restore` | `app/modules/employees/interface/employees.py:899` → `restore_shift_type` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, ShiftType |
| 41 | GET | `/api/shift-types/{type_id}/revisions` | `app/modules/employees/interface/employees.py:913` → `shift_revisions` | def | `perm:settings.view` |  | — |  | AccessGrant, ShiftRevision, ShiftType |
| 42 | GET | `/api/schedule` | `app/modules/timesheet/interface/schedule.py:245` → `get_grid` | def | `perm:schedule.view` | principal_permissions | — |  | AccessGrant, AccessGroupMember, BlockAssignment, DoublePayDay, Employee, EmploymentPeriod, EngineSettingsVersion, ScheduleAbsence, ScheduleShift, ShiftType, TabelDay |
| 43 | PUT | `/api/schedule/shift` | `app/modules/timesheet/interface/schedule.py:424` → `put_manual_shift` | def | `perm:schedule.edit` |  | 0 | да | AccessGrant, AuditLog, ScheduleShift, ShiftType |
| 44 | DELETE | `/api/schedule/shift` | `app/modules/timesheet/interface/schedule.py:476` → `delete_manual_shift` | def | `perm:schedule.edit` |  | 0 | да | AccessGrant, AuditLog |
| 45 | POST | `/api/schedule/absence` | `app/modules/timesheet/interface/schedule.py:503` → `add_absence` | def | `perm:schedule.edit` |  | 0 | да | AccessGrant, AuditLog, ScheduleAbsence |
| 46 | DELETE | `/api/schedule/absence/{absence_id}` | `app/modules/timesheet/interface/schedule.py:538` → `remove_absence` | def | `perm:schedule.edit` |  | 0 | да | AccessGrant, AuditLog |
| 47 | POST | `/api/schedule/range-absence` | `app/modules/timesheet/interface/schedule.py:719` → `range_absence` | def | `perm:schedule.edit` |  | 0 | да | AccessGrant, AuditLog, EmploymentPeriod, ScheduleAbsence, ShiftType, TabelDay |
| 48 | GET | `/api/schedule/timeoff-hours` | `app/modules/timesheet/interface/schedule.py:805` → `timeoff_hours` | def | `perm:schedule.view` |  | — |  | AccessGrant, Employee, TabelDay |
| 49 | GET | `/api/schedule/absence-period` | `app/modules/timesheet/interface/schedule.py:860` → `absence_period` | def | `perm:schedule.view` |  | — |  | AccessGrant, Employee, EngineSettingsVersion, ScheduleAbsence, ShiftType, StatementKind, TabelDay |
| 50 | GET | `/api/schedule/patterns` | `app/modules/timesheet/interface/schedule.py:986` → `get_patterns` | def | `perm:schedule.edit` |  | — |  | AccessGrant |
| 51 | POST | `/api/schedule/fill-pattern` | `app/modules/timesheet/interface/schedule.py:991` → `fill_pattern` | def | `perm:schedule.edit` |  | 0 | да | AccessGrant, AuditLog, BlockAssignment, Employee, EmploymentPeriod, Setting, TabelDay |
| 52 | POST | `/api/schedule/continue` | `app/modules/timesheet/interface/schedule.py:1093` → `continue_schedule` | def | `perm:schedule.edit` |  | 0 | да | AccessGrant, AuditLog, Employee, EmploymentPeriod, Setting, TabelDay |
| 53 | POST | `/api/schedule/copy` | `app/modules/timesheet/interface/schedule.py:1120` → `copy_period` | def | `perm:schedule.edit` |  | 0 | да | AccessGrant, AuditLog, Employee, EmploymentPeriod, TabelDay |
| 54 | POST | `/api/schedule/clear-month` | `app/modules/timesheet/interface/schedule.py:1179` → `clear_month` | def | `perm:schedule.edit` |  | 0 | да | AccessGrant, AuditLog, Employee, EmploymentPeriod, TabelDay |
| 55 | POST | `/api/schedule/reset-month` | `app/modules/timesheet/interface/schedule.py:1213` → `reset_month` | def | `perm:schedule.edit` |  | 0 | да | AccessGrant, AuditLog, Employee, EmploymentPeriod, ScheduleAbsence, ScheduleShift |
| 56 | GET | `/api/schedule/xlsx` | `app/modules/timesheet/interface/schedule.py:1266` → `export_xlsx` | def | `perm:schedule.edit` |  | — |  | AccessGrant, BlockAssignment, DoublePayDay, Employee, EmploymentPeriod, ScheduleAbsence, ScheduleShift, ShiftType, TabelDay |
| 57 | GET | `/api/schedule/pdf` | `app/modules/timesheet/interface/schedule.py:1314` → `export_pdf` | def | `perm:schedule.view` |  | 0 | да | AccessGrant, AuditLog, BlockAssignment, DoublePayDay, Employee, EmploymentPeriod, ScheduleAbsence, ScheduleShift, ShiftType, TabelDay |
| 58 | GET | `/api/punches/status` | `app/modules/timesheet/interface/punches.py:210` → `my_status` | def | `current_principal` |  | — |  | Employee, PeriodClosing, Punch, ScheduleAbsence, ScheduleShift, TabelDay |
| 59 | POST | `/api/punches` | `app/modules/timesheet/interface/punches.py:222` → `punch` | def | `current_principal` |  | 1 | да | AuditLog, Employee, EmploymentPeriod, PeriodClosing, Punch, ScheduleAbsence, ScheduleShift, TabelDay |
| 60 | GET | `/api/punches` | `app/modules/timesheet/interface/punches.py:351` → `list_punches` | def | `current_principal` | principal_permissions | — |  | AccessGrant, AccessGroupMember, Employee, Punch |
| 61 | DELETE | `/api/punches/{punch_id}` | `app/modules/timesheet/interface/punches.py:392` → `delete_punch` | def | `perm:punches.manage` |  | 0 | да | AccessGrant, AuditLog, Punch |
| 62 | PUT | `/api/punches/{punch_id}/note` | `app/modules/timesheet/interface/punches.py:410` → `set_punch_note` | def | `current_principal` | principal_permissions | 0 | да | AccessGrant, AccessGroupMember, AuditLog, Punch |
| 63 | GET | `/api/tabel` | `app/modules/timesheet/interface/tabel_api.py:74` → `get_tabel` | def | `perm:tabel.view` | principal_permissions | — |  | AccessGrant, AccessGroupMember, Employee, EmploymentPeriod, EngineSettingsVersion, TabelDay |
| 64 | PUT | `/api/tabel/cell` | `app/modules/timesheet/interface/tabel_api.py:180` → `put_cell` | def | `perm:tabel.edit` |  | 1 | да | AccessGrant, AuditLog, TabelDay |
| 65 | POST | `/api/tabel/bulk` | `app/modules/timesheet/interface/tabel_api.py:189` → `bulk` | def | `perm:tabel.edit` |  | 1 | да | AccessGrant, AuditLog, TabelDay |
| 66 | POST | `/api/tabel/fill-from-cycles` | `app/modules/timesheet/interface/tabel_api.py:226` → `fill` | def | `perm:tabel.edit` |  | 0 | да | AccessGrant, AuditLog, Employee, EmploymentPeriod, Setting, TabelDay |
| 67 | POST | `/api/tabel/reset` | `app/modules/timesheet/interface/tabel_api.py:289` → `reset` | def | `perm:tabel.edit` |  | 0 | да | AccessGrant, AuditLog, Employee, EmploymentPeriod, Setting, TabelDay |
| 68 | GET | `/api/mgmt` | `app/modules/timesheet/interface/mgmt_api.py:107` → `get_mgmt` | def | `perm:mgmt.view` | principal_permissions | — |  | AccessGrant, AccessGroupMember, Employee, EmploymentPeriod |
| 69 | POST | `/api/mgmt/close` | `app/modules/timesheet/interface/mgmt_api.py:159` → `close` | def | `perm:mgmt.close` |  | 0 | да | AccessGrant, AuditLog, Employee, EmploymentPeriod |
| 70 | POST | `/api/mgmt/recalculate` | `app/modules/timesheet/interface/mgmt_api.py:169` → `recalc` | def | `perm:mgmt.recalculate` |  | 0 | да | AccessGrant, AuditLog, Employee, EmploymentPeriod |
| 71 | GET | `/api/mgmt/periods` | `app/modules/timesheet/interface/mgmt_api.py:179` → `periods` | def | `perm:mgmt.view` |  | — |  | AccessGrant, Employee, EmploymentPeriod |
| 72 | GET | `/api/mgmt/xlsx` | `app/modules/timesheet/interface/mgmt_api.py:209` → `export_xlsx` | def | `perm:mgmt.view` |  | — |  | AccessGrant, Employee, EmploymentPeriod |
| 73 | GET | `/api/presence/board` | `app/modules/timesheet/interface/presence_api.py:26` → `board` | def | `perm:presence.view` |  | — |  | AccessGrant, Employee |
| 74 | GET | `/api/fact/sessions` | `app/modules/timesheet/interface/fact_api.py:48` → `sessions` | def | `perm:presence.view` | principal_permissions | — |  | AccessGrant, Employee |
| 75 | GET | `/api/fact/month` | `app/modules/timesheet/interface/fact_api.py:73` → `fact_month` | def | `perm:presence.view` | principal_permissions | — |  | AccessGrant, Employee, EmploymentPeriod, ScheduleAbsence, ScheduleShift, ShiftType, TabelDay |
| 76 | GET | `/api/fact/day` | `app/modules/timesheet/interface/fact_api.py:280` → `day_grid` | def | `perm:presence.view` | principal_permissions | — |  | AccessGrant, Employee, EmploymentPeriod |
| 77 | GET | `/api/access` | `app/modules/access/interface/access_api.py:31` → `catalog` | def | `perm:access.manage` | effective_permissions, role | — |  | AccessGrant, AccessGroup, AccessGroupMember, Employee, User |
| 78 | PUT | `/api/access/roles/{role}` | `app/modules/access/interface/access_api.py:75` → `put_role` | def | `perm:access.manage` | role | 0 | да | AccessGrant, AuditLog |
| 79 | POST | `/api/access/groups` | `app/modules/access/interface/access_api.py:92` → `create_group` | def | `perm:access.manage` |  | 0 | да | AccessGrant, AccessGroup, AuditLog |
| 80 | PUT | `/api/access/groups/{group_id}` | `app/modules/access/interface/access_api.py:108` → `update_group` | def | `perm:access.manage` |  | 0 | да | AccessGrant, AccessGroup, AuditLog |
| 81 | DELETE | `/api/access/groups/{group_id}` | `app/modules/access/interface/access_api.py:127` → `delete_group` | def | `perm:access.manage` |  | 0 | да | AccessGrant, AccessGroup, AccessGroupMember, AuditLog |
| 82 | PUT | `/api/access/groups/{group_id}/grants` | `app/modules/access/interface/access_api.py:141` → `put_group_grants` | def | `perm:access.manage` |  | 0 | да | AccessGrant, AccessGroup, AuditLog |
| 83 | PUT | `/api/access/groups/{group_id}/members` | `app/modules/access/interface/access_api.py:157` → `put_members` | def | `perm:access.manage` |  | 0 | да | AccessGrant, AccessGroup, AccessGroupMember, AuditLog, User |
| 84 | PUT | `/api/access/users/{user_id}/grants` | `app/modules/access/interface/access_api.py:178` → `put_user_grants` | def | `perm:access.manage` |  | 0 | да | AccessGrant, AuditLog, User |
| 85 | GET | `/api/audit` | `app/modules/audit/interface/audit_api.py:76` → `list_audit` | def | `perm:audit.view` |  | — |  | AccessGrant, AuditLog |
| 86 | GET | `/api/audit/csv` | `app/modules/audit/interface/audit_api.py:89` → `export_csv` | def | `perm:audit.view` |  | — |  | AccessGrant, AuditLog |
| 87 | GET | `/api/engine-settings` | `app/modules/timesheet/interface/engine_settings_api.py:41` → `get_settings` | def | `perm:settings.view` |  | — |  | AccessGrant, EngineSettingsVersion |
| 88 | PUT | `/api/engine-settings` | `app/modules/timesheet/interface/engine_settings_api.py:87` → `put_settings` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, EngineSettingsVersion, PeriodClosing, TabelDay |
| 89 | GET | `/api/engine-settings/modifiers` | `app/modules/timesheet/interface/engine_settings_api.py:158` → `list_modifiers` | def | `perm:settings.view` |  | — |  | AccessGrant, DayModifier |
| 90 | POST | `/api/engine-settings/modifiers` | `app/modules/timesheet/interface/engine_settings_api.py:238` → `add_modifier` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, DayModifier, EngineSettingsVersion |
| 91 | DELETE | `/api/engine-settings/modifiers/{mod_id}` | `app/modules/timesheet/interface/engine_settings_api.py:278` → `delete_modifier` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, DayModifier |
| 92 | GET | `/api/engine-settings/health` | `app/modules/timesheet/interface/engine_settings_api.py:430` → `get_health` | def | `perm:settings.view` |  | — |  | AccessGrant, AuditLog, DayModifier, Employee, EngineSettingsVersion, NightArea, NightZone, PeriodClosing, ResponsibilityService, ZoneChecklistItem |
| 93 | GET | `/api/engine-settings/rules/resolve` | `app/modules/timesheet/interface/engine_settings_api.py:556` → `resolve_rules` | def | `perm:settings.view` |  | — |  | AccessGrant, DayModifier, DoublePayDay, Employee, EngineSettingsVersion, TabelDay, VipDoublePay |
| 94 | GET | `/api/settings` | `app/modules/settings/interface/settings_api.py:69` → `get_settings_api` | def | `perm:settings.view` |  | — |  | AccessGrant, Employee, EngineSettingsVersion, PeriodClosing, Punch, ScheduleShift, Setting, TabelDay, User |
| 95 | PUT | `/api/settings/doc` | `app/modules/settings/interface/settings_api.py:107` → `update_doc` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, Setting |
| 96 | PUT | `/api/settings/base` | `app/modules/settings/interface/settings_api.py:123` → `update_base` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, Setting |
| 97 | PUT | `/api/settings` | `app/modules/settings/interface/settings_api.py:153` → `update_settings` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, Setting |
| 98 | GET | `/api/docs/kinds` | `app/modules/docs/interface/docs_api.py:90` → `list_kinds` | def | `perm:settings.view` |  | — |  | AccessGrant, StatementKind |
| 99 | POST | `/api/docs/kinds` | `app/modules/docs/interface/docs_api.py:112` → `create_kind` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, StatementKind |
| 100 | PUT | `/api/docs/kinds/{kind_id}` | `app/modules/docs/interface/docs_api.py:131` → `update_kind` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, StatementKind |
| 101 | DELETE | `/api/docs/kinds/{kind_id}` | `app/modules/docs/interface/docs_api.py:148` → `delete_kind` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, ShiftType, StatementKind |
| 102 | GET | `/api/docs/templates` | `app/modules/docs/interface/docs_api.py:168` → `get_templates` | def | `perm:settings.view` |  | — |  | AccessGrant, StatementKind |
| 103 | GET | `/api/docs/sample` | `app/modules/docs/interface/docs_api.py:180` → `sample_template` | def | `perm:settings.view` |  | — |  | AccessGrant, StatementKind |
| 104 | POST | `/api/docs/templates` | `app/modules/docs/interface/docs_api.py:190` → `upload_template` | **async** | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, StatementKind |
| 105 | DELETE | `/api/docs/templates` | `app/modules/docs/interface/docs_api.py:209` → `remove_template` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, StatementKind |
| 106 | POST | `/api/docs/render` | `app/modules/docs/interface/docs_api.py:234` → `render` | def | `perm:settings.view` |  | 0 | да | AccessGrant, AuditLog, Employee, Setting, StatementKind |
| 107 | GET | `/api/doublepay` | `app/modules/timesheet/interface/doublepay.py:113` → `get_doublepay` | def | `perm:settings.view` |  | — |  | AccessGrant, DoublePayDay, Employee, VipDoublePay |
| 108 | POST | `/api/doublepay/days` | `app/modules/timesheet/interface/doublepay.py:141` → `add_days` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, DoublePayDay |
| 109 | DELETE | `/api/doublepay/days/{day_id}` | `app/modules/timesheet/interface/doublepay.py:198` → `delete_day` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, DoublePayDay |
| 110 | POST | `/api/doublepay/vip` | `app/modules/timesheet/interface/doublepay.py:220` → `add_vip` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, Employee, VipDoublePay |
| 111 | DELETE | `/api/doublepay/vip/{vip_id}` | `app/modules/timesheet/interface/doublepay.py:250` → `delete_vip` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, Employee, VipDoublePay |
| 112 | GET | `/api/night/areas` | `app/modules/night/interface/night_api.py:182` → `list_areas` | def | `perm:night.view` | has_perm | — |  | AccessGrant, ChecklistItem, NightArea, NightZone, ResponsibilityService, ZoneChecklistItem |
| 113 | POST | `/api/night/areas/bulk` | `app/modules/night/interface/night_api.py:217` → `create_areas_bulk` | def | `perm:night.edit` |  | 0 | да | AccessGrant, AuditLog, NightArea, NightZone |
| 114 | POST | `/api/night/areas` | `app/modules/night/interface/night_api.py:239` → `create_area` | def | `perm:night.edit` |  | 0 | да | AccessGrant, AuditLog, NightArea, NightZone |
| 115 | PUT | `/api/night/areas/{area_id}` | `app/modules/night/interface/night_api.py:257` → `update_area` | def | `perm:night.edit` |  | 0 | да | AccessGrant, AuditLog, ChecklistItem, ChecklistOverride, NightArea, NightAreaSection, NightCheckItem, NightReport, NightZone, ResponsibilityService, ZoneChecklistItem |
| 116 | DELETE | `/api/night/areas/{area_id}` | `app/modules/night/interface/night_api.py:287` → `delete_area` | def | `perm:night.edit` |  | 0 | да | AccessGrant, AuditLog, NightArea, NightAreaSection, NightReport |
| 117 | POST | `/api/night/areas/{area_id}/items` | `app/modules/night/interface/night_api.py:307` → `add_item` | def | `perm:night.edit` |  | 0 | да | AccessGrant, AuditLog, ChecklistItem, NightArea, NightAreaSection, NightCheckItem, NightReport, ResponsibilityService |
| 118 | PUT | `/api/night/items/{item_id}` | `app/modules/night/interface/night_api.py:342` → `update_item` | def | `perm:night.edit` |  | 0 | да | AccessGrant, AuditLog, ChecklistItem, NightAreaSection, NightCheckItem, NightReport, ResponsibilityService |
| 119 | DELETE | `/api/night/items/{item_id}` | `app/modules/night/interface/night_api.py:377` → `delete_item` | def | `perm:night.edit` |  | 0 | да | AccessGrant, AuditLog, ChecklistItem, NightAreaSection, NightCheckItem, NightReport |
| 120 | GET | `/api/night/zones` | `app/modules/night/interface/night_api.py:446` → `list_zones` | def | `perm:night.view` | has_perm | — |  | AccessGrant, NightArea, NightZone, ZoneChecklistItem |
| 121 | POST | `/api/night/zones` | `app/modules/night/interface/night_api.py:470` → `create_zone` | def | `perm:night.edit` |  | 0 | да | AccessGrant, AuditLog, NightZone |
| 122 | PUT | `/api/night/zones/{zone_id}` | `app/modules/night/interface/night_api.py:486` → `update_zone` | def | `perm:night.edit` |  | 0 | да | AccessGrant, AuditLog, NightAreaSection, NightReport, NightZone |
| 123 | DELETE | `/api/night/zones/{zone_id}` | `app/modules/night/interface/night_api.py:513` → `delete_zone` | def | `perm:night.edit` |  | 0 | да | AccessGrant, AuditLog, NightArea, NightZone |
| 124 | GET | `/api/night/zones/{zone_id}/items` | `app/modules/night/interface/night_api.py:533` → `zone_items` | def | `perm:night.view` |  | — |  | AccessGrant, ChecklistOverride, NightArea, NightZone, ResponsibilityService, ZoneChecklistItem |
| 125 | POST | `/api/night/zones/{zone_id}/items` | `app/modules/night/interface/night_api.py:560` → `add_zone_item` | def | `perm:night.edit` |  | 0 | да | AccessGrant, AuditLog, ChecklistItem, ChecklistOverride, NightArea, NightAreaSection, NightCheckItem, NightReport, NightZone, ResponsibilityService, ZoneChecklistItem |
| 126 | PUT | `/api/night/zone-items/{item_id}` | `app/modules/night/interface/night_api.py:606` → `update_zone_item` | def | `perm:night.edit` |  | 0 | да | AccessGrant, AuditLog, ChecklistOverride, NightAreaSection, NightCheckItem, NightReport, ResponsibilityService, ZoneChecklistItem |
| 127 | DELETE | `/api/night/zone-items/{item_id}` | `app/modules/night/interface/night_api.py:642` → `delete_zone_item` | def | `perm:night.edit` |  | 0 | да | AccessGrant, AuditLog, NightAreaSection, NightCheckItem, NightReport, ZoneChecklistItem |
| 128 | GET | `/api/night/areas/{area_id}/checklist` | `app/modules/night/interface/night_api.py:657` → `area_checklist` | def | `perm:night.view` |  | — |  | AccessGrant, ChecklistItem, ChecklistOverride, NightArea, NightZone, ResponsibilityService, ZoneChecklistItem |
| 129 | PUT | `/api/night/areas/{area_id}/overrides/{zone_item_id}` | `app/modules/night/interface/night_api.py:699` → `set_override` | def | `perm:night.edit` |  | 0 | да | AccessGrant, AuditLog, ChecklistItem, ChecklistOverride, NightArea, NightAreaSection, NightCheckItem, NightReport, ResponsibilityService, ZoneChecklistItem |
| 130 | DELETE | `/api/night/areas/{area_id}/overrides/{zone_item_id}` | `app/modules/night/interface/night_api.py:741` → `reset_override` | def | `perm:night.edit` |  | 0 | да | AccessGrant, AuditLog, ChecklistItem, ChecklistOverride, NightArea, NightAreaSection, NightCheckItem, NightReport, ResponsibilityService, ZoneChecklistItem |
| 131 | GET | `/api/night/services` | `app/modules/night/interface/night_api.py:769` → `list_services` | def | `perm:night.view` | has_perm | — |  | AccessGrant, ChecklistItem, ResponsibilityService, ZoneChecklistItem |
| 132 | POST | `/api/night/services` | `app/modules/night/interface/night_api.py:788` → `create_service` | def | `perm:night.edit` |  | 0 | да | AccessGrant, AuditLog, ResponsibilityService |
| 133 | PUT | `/api/night/services/{service_id}` | `app/modules/night/interface/night_api.py:809` → `update_service` | def | `perm:night.edit` |  | 0 | да | AccessGrant, AuditLog, NightAreaSection, NightCheckItem, NightReport, ResponsibilityService |
| 134 | DELETE | `/api/night/services/{service_id}` | `app/modules/night/interface/night_api.py:849` → `delete_service` | def | `perm:night.edit` |  | 0 | да | AccessGrant, AuditLog, ResponsibilityService, ZoneChecklistItem |
| 135 | GET | `/api/night/today` | `app/modules/night/interface/night_api.py:872` → `today_report` | def | `perm:night.view` |  | — |  | AccessGrant, Car, CarNightCheck, NightAreaSection, NightInterception, NightReport, Photo |
| 136 | GET | `/api/night/reports` | `app/modules/night/interface/night_api.py:895` → `list_reports` | def | `perm:night.view` |  | — |  | AccessGrant, Car, CarNightCheck, NightAreaSection, NightCheckItem, NightInterception, NightReport |
| 137 | GET | `/api/night/reports/{report_id}` | `app/modules/night/interface/night_api.py:906` → `get_report` | def | `perm:night.view` |  | — |  | AccessGrant, Car, CarNightCheck, NightAreaSection, NightInterception, NightReport, Photo |
| 138 | POST | `/api/night/sections/{section_id}/take` | `app/modules/night/interface/night_api.py:924` → `take_section` | def | `current_principal` | role | 0 | да | AuditLog, NightAreaSection, NightCheckItem, NightInterception, NightReport |
| 139 | POST | `/api/night/sections/{section_id}/close` | `app/modules/night/interface/night_api.py:965` → `close_section` | def | `current_principal` |  | 0 | да | AuditLog, NightAreaSection, NightCheckItem, NightReport |
| 140 | POST | `/api/night/sections/{section_id}/reopen` | `app/modules/night/interface/night_api.py:991` → `reopen_section` | def | `perm:night.close` |  | 0 | да | AccessGrant, AuditLog, NightAreaSection, NightCheckItem, NightReport |
| 141 | PUT | `/api/night/items/{item_id}/answer` | `app/modules/night/interface/night_api.py:1004` → `answer_item` | def | `current_principal` |  | 0 | да | AuditLog, NightAreaSection, NightCheckItem, NightReport |
| 142 | POST | `/api/night/items/{item_id}/photo` | `app/modules/night/interface/night_api.py:1032` → `add_item_photo` | **async** | `current_principal` |  | — | да | NightAreaSection, NightCheckItem, NightReport, Photo, Setting |
| 143 | GET | `/api/night/reports/{report_id}/defects` | `app/modules/night/interface/night_api.py:1063` → `report_defects` | def | `perm:night.view` |  | — |  | AccessGrant, NightReport |
| 144 | POST | `/api/night/reports/{report_id}/dispatch` | `app/modules/night/interface/night_api.py:1073` → `dispatch_report` | def | `perm:night.view` |  | — |  | AccessGrant, NightReport |
| 145 | GET | `/api/night/reports/{report_id}/dispatches` | `app/modules/night/interface/night_api.py:1086` → `report_dispatches` | def | `perm:night.view` |  | — |  | AccessGrant, NightReport |
| 146 | POST | `/api/night/reports/{report_id}/defects/preview` | `app/modules/night/interface/night_api.py:1097` → `preview_defects` | def | `perm:night.view` |  | — |  | AccessGrant, NightCheckItem, NightReport |
| 147 | GET | `/api/night/photos/{photo_id}/file` | `app/modules/night/interface/night_api.py:1128` → `photo_file` | def | `current_principal` |  | — |  | Photo |
| 148 | GET | `/api/night/reports/{report_id}/cars` | `app/modules/night/interface/night_api.py:1152` → `report_cars` | def | `perm:night.view` |  | — |  | AccessGrant, NightReport |
| 149 | POST | `/api/night/reports/{report_id}/cars/{car_id}/check` | `app/modules/night/interface/night_api.py:1162` → `report_car_check` | **async** | `current_principal` |  | — | да | Car, NightAreaSection, NightReport, Setting |
| 150 | POST | `/api/night/reports/{report_id}/cars/finish` | `app/modules/night/interface/night_api.py:1240` → `report_cars_finish` | def | `current_principal` |  | 0 | да | AuditLog, NightAreaSection, NightReport |
| 151 | POST | `/api/night/reports/{report_id}/close` | `app/modules/night/interface/night_api.py:1271` → `close_report` | def | `perm:night.close` |  | 0 | да | AccessGrant, AuditLog, Car, CarNightCheck, NightAreaSection, NightInterception, NightReport, Photo |
| 152 | POST | `/api/night/reports/{report_id}/reopen` | `app/modules/night/interface/night_api.py:1295` → `reopen_report` | def | `perm:night.close` |  | 0 | да | AccessGrant, AuditLog, Car, CarNightCheck, NightAreaSection, NightInterception, NightReport, Photo |
| 153 | DELETE | `/api/night/photos/{photo_id}` | `app/modules/night/interface/night_api.py:1317` → `delete_photo` | def | `current_principal` |  | 1 | да | AuditLog, Photo |
| 154 | GET | `/api/night/reports/{report_id}/export.docx` | `app/modules/night/interface/night_api.py:1332` → `export_docx` | def | `perm:night.view` |  | — |  | AccessGrant, NightReport, Photo, Setting |
| 155 | GET | `/api/night/reports/{report_id}/export.pdf` | `app/modules/night/interface/night_api.py:1347` → `export_pdf` | def | `perm:night.view` |  | — |  | AccessGrant, NightReport, Photo, Setting |
| 156 | GET | `/api/cars/meta` | `app/modules/cars/interface/cars_api.py:107` → `meta` | def | `perm:cars.view` | principal_permissions | — |  | AccessGrant, AccessGroupMember |
| 157 | DELETE | `/api/cars/locations/{loc_id}` | `app/modules/cars/interface/cars_api.py:126` → `location_delete` | def | `perm:cars.manage` |  | 0 | да | AccessGrant, AuditLog, Car, CarLocation |
| 158 | GET | `/api/cars/locations` | `app/modules/cars/interface/cars_api.py:148` → `locations` | def | `perm:cars.view` | role | — |  | AccessGrant, CarLocation |
| 159 | POST | `/api/cars/locations` | `app/modules/cars/interface/cars_api.py:155` → `location_add` | def | `perm:cars.manage` |  | 0 | да | AccessGrant, AuditLog, CarLocation |
| 160 | PUT | `/api/cars/locations/{loc_id}` | `app/modules/cars/interface/cars_api.py:167` → `location_update` | def | `perm:cars.manage` |  | 0 | да | AccessGrant, AuditLog, Car, CarLocation |
| 161 | GET | `/api/cars` | `app/modules/cars/interface/cars_api.py:180` → `park` | def | `perm:cars.view` | principal_permissions | — |  | AccessGrant, AccessGroupMember, Car, Employee |
| 162 | POST | `/api/cars` | `app/modules/cars/interface/cars_api.py:205` → `car_add` | def | `perm:cars.manage` |  | 0 | да | AccessGrant, AuditLog, Car, CarHistory, Employee |
| 163 | PUT | `/api/cars/{car_id}` | `app/modules/cars/interface/cars_api.py:217` → `car_edit` | def | `perm:cars.manage` |  | 0 | да | AccessGrant, AuditLog, Car, CarHistory, Employee |
| 164 | GET | `/api/cars/{car_id}/history` | `app/modules/cars/interface/cars_api.py:230` → `car_history` | def | `perm:cars.view` |  | — |  | AccessGrant, Car, CarHistory, Photo |
| 165 | POST | `/api/cars/{car_id}/take` | `app/modules/cars/interface/cars_api.py:248` → `car_take` | def | `perm:cars.use` |  | 0 | да | AccessGrant, AuditLog, Car, CarHistory, Employee |
| 166 | POST | `/api/cars/{car_id}/handover` | `app/modules/cars/interface/cars_api.py:261` → `car_handover` | def | `perm:cars.use` |  | 0 | да | AccessGrant, AuditLog, Car, CarHistory, Employee |
| 167 | POST | `/api/cars/{car_id}/give` | `app/modules/cars/interface/cars_api.py:276` → `car_give` | def | `perm:cars.issue` |  | 0 | да | AccessGrant, AuditLog, Car, CarHistory, Employee |
| 168 | POST | `/api/cars/{car_id}/return` | `app/modules/cars/interface/cars_api.py:291` → `car_return` | **async** | `perm:cars.use` |  | 0 | да | AccessGrant, AuditLog, Car, CarHistory, Employee, Setting |
| 169 | POST | `/api/cars/{car_id}/assign` | `app/modules/cars/interface/cars_api.py:338` → `car_assign` | def | `perm:cars.issue` |  | 0 | да | AccessGrant, AuditLog, Car, CarHistory, Employee |
| 170 | POST | `/api/cars/{car_id}/status` | `app/modules/cars/interface/cars_api.py:352` → `car_set_status` | def | `perm:cars.issue` |  | 0 | да | AccessGrant, AuditLog, Car, CarHistory, Employee |
| 171 | GET | `/api/notify/config` | `app/modules/notify/interface/notify_api.py:97` → `get_config` | def | `perm:settings.edit` |  | — |  | NotifyChat, ResponsibilityService, Setting |
| 172 | PUT | `/api/notify/config` | `app/modules/notify/interface/notify_api.py:105` → `put_config` | def | `perm:settings.edit` |  | 0 | да | AuditLog, Setting |
| 173 | POST | `/api/notify/telegram/check` | `app/modules/notify/interface/notify_api.py:120` → `telegram_check` | def | `perm:settings.edit` |  | 0 | да | AuditLog, Setting |
| 174 | POST | `/api/notify/telegram/chats` | `app/modules/notify/interface/notify_api.py:138` → `telegram_chats` | def | `perm:settings.edit` |  | 0 | да | AuditLog, NotifyChat, ResponsibilityService, Setting |
| 175 | GET | `/api/notify/chats` | `app/modules/notify/interface/notify_api.py:156` → `get_chats` | def | `perm:settings.edit|night.edit` |  | — |  | AccessGrant, NotifyChat, ResponsibilityService |
| 176 | POST | `/api/notify/telegram/test` | `app/modules/notify/interface/notify_api.py:162` → `telegram_test` | def | `perm:settings.edit` |  | 0 | да | AuditLog, Setting |
| 177 | POST | `/api/notify/email/test` | `app/modules/notify/interface/notify_api.py:180` → `email_test` | def | `perm:settings.edit` |  | 0 | да | AuditLog, Setting |
| 178 | GET | `/api/notify/dispatches` | `app/modules/notify/interface/notify_api.py:202` → `list_dispatches` | def | `perm:settings.edit` |  | — |  | AccessGrant, NotifyDispatch |
| 179 | GET | `/api/notify/dispatches/export.csv` | `app/modules/notify/interface/notify_api.py:225` → `export_dispatches_csv` | def | `perm:settings.edit` |  | — |  | AccessGrant, NotifyDispatch |
| 180 | POST | `/api/notify/dispatches/{dispatch_id}/resend` | `app/modules/notify/interface/notify_api.py:273` → `resend_dispatch` | def | `perm:settings.edit` |  | 0 | да | AccessGrant, AuditLog, NotifyDispatch, Setting |
| 181 | GET | `/api/notify/templates` | `app/modules/notify/interface/notify_api.py:297` → `get_templates` | def | `perm:settings.edit` |  | — |  | NotifyTemplate |
| 182 | PUT | `/api/notify/templates/{domain}` | `app/modules/notify/interface/notify_api.py:303` → `put_template` | def | `perm:settings.edit` |  | 0 | да | AuditLog, NotifyTemplate |
| 183 | POST | `/api/notify/templates/{domain}/preview` | `app/modules/notify/interface/notify_api.py:327` → `preview_template` | def | `perm:settings.edit` |  | — |  |  |
| 184 | GET | `/api/photos/limits` | `app/core/media_api.py:32` → `photo_limits` | def | `current_principal` |  | — |  | Setting |
| 185 | GET | `/api/photos/{photo_id}/file` | `app/core/media_api.py:39` → `photo_file` | def | `current_principal` |  | — |  | Photo |
| 186 | DELETE | `/api/photos/{photo_id}` | `app/core/media_api.py:50` → `photo_delete` | def | `current_principal` |  | 1 | да | AuditLog, Photo |
| 187 | GET | `/api/selfcheck` | `app/main.py:282` → `selfcheck` | def | `optional_principal` | is_admin | — |  |  |
| 188 | GET | `/api/health` | `app/main.py:302` → `health` | def | `нет` |  | — |  |  |
| 189 | GET | `/sw.js` | `app/main.py:321` → `service_worker` | def | `нет` |  | — |  |  |
| 190 | GET | `/manifest.webmanifest` | `app/main.py:328` → `manifest` | def | `нет` |  | — |  |  |
| 191 | GET | `/{full_path:path}` | `app/main.py:337` → `spa` | def | `нет` |  | — |  |  |
