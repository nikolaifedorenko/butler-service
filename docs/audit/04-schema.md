# 04. Модели и схема (сгенерировано `docs/audit/scripts/schema_inventory.py`)

Коммит `3801abf`. Таблиц в `Base.metadata`: **45**. Сравнение «старая база после миграций ↔ чистая» — в [04b-schema-diff.md](04b-schema-diff.md); шаги миграций — в 15-db-engine.md.

| Таблица | Модель (модуль) | Колонок | FK → | Unique | Индексы |
|---|---|---|---|---|---|
| `access_groups` | `AccessGroup` (core.identity) | 4 | — | name; name | — |
| `car_locations` | `CarLocation` (modules.cars.adapters.orm) | 6 | — | name; name | — |
| `departments` | `Department` (modules.employees.adapters.orm) | 2 | — | name; name | — |
| `engine_settings_versions` | `EngineSettingsVersion` (modules.timesheet.adapters.orm) | 6 | — | — | ix_engine_settings_versions_valid_from(valid_from) |
| `night_reports` | `NightReport` (modules.night.adapters.orm) | 10 | — | date | ix_night_reports_date(date) |
| `night_zones` | `NightZone` (modules.night.adapters.orm) | 6 | — | name; name | — |
| `notify_chats` | `NotifyChat` (modules.notify.adapters.orm) | 7 | — | chat_id | ix_notify_chats_chat_id(chat_id) |
| `notify_templates` | `NotifyTemplate` (modules.notify.adapters.orm) | 4 | — | domain | ix_notify_templates_domain(domain) |
| `responsibility_services` | `ResponsibilityService` (modules.notify.adapters.orm) | 12 | — | name; name | — |
| `settings` | `Setting` (core.settings_store) | 3 | — | — | — |
| `shift_types` | `ShiftType` (modules.timesheet.adapters.orm) | 17 | — | code; code | — |
| `statement_kinds` | `StatementKind` (modules.employees.adapters.orm) | 9 | — | code; code | — |
| `subdivisions` | `Subdivision` (modules.employees.adapters.orm) | 2 | — | name; name | — |
| `employees` | `Employee` (modules.employees.adapters.orm) | 23 | department_id→departments | — | — |
| `night_areas` | `NightArea` (modules.night.adapters.orm) | 8 | zone_id→night_zones | name; name | ix_night_areas_zone_id(zone_id) |
| `shift_revisions` | `ShiftRevision` (modules.timesheet.adapters.orm) | 15 | shift_type_id→shift_types | — | ix_shift_revisions_shift_type_id(shift_type_id) |
| `zone_checklist_items` | `ZoneChecklistItem` (modules.night.adapters.orm) | 8 | service_id→responsibility_services, zone_id→night_zones | — | ix_zone_checklist_items_service_id(service_id), ix_zone_checklist_items_zone_id(zone_id) |
| `block_assignments` | `BlockAssignment` (modules.timesheet.adapters.orm) | 6 | employee_id→employees | employee_id,group,start_date | ix_block_assignments_employee_id(employee_id) |
| `checklist_items` | `ChecklistItem` (modules.night.adapters.orm) | 8 | area_id→night_areas, service_id→responsibility_services | — | ix_checklist_items_area_id(area_id), ix_checklist_items_service_id(service_id) |
| `checklist_overrides` | `ChecklistOverride` (modules.night.adapters.orm) | 8 | area_id→night_areas, service_id→responsibility_services, zone_item_id→zone_checklist_items | area_id,zone_item_id | ix_checklist_overrides_area_id(area_id), ix_checklist_overrides_zone_item_id(zone_item_id) |
| `day_modifiers` | `DayModifier` (modules.timesheet.adapters.orm) | 10 | employee_id→employees | — | ix_day_modifiers_date(date), ix_day_modifiers_period_start(period_start) |
| `deferred_carry` | `DeferredCarry` (modules.timesheet.adapters.orm) | 6 | employee_id→employees | — | ix_deferred_carry_employee_id(employee_id), ix_deferred_carry_period_start(period_start) |
| `emergency_contacts` | `EmergencyContact` (modules.employees.adapters.orm) | 5 | employee_id→employees | — | ix_emergency_contacts_employee_id(employee_id) |
| `period_closings` | `PeriodClosing` (modules.timesheet.adapters.orm) | 15 | employee_id→employees | employee_id,period_start | ix_period_closings_employee_id(employee_id) |
| `position_history` | `PositionHistory` (modules.employees.adapters.orm) | 5 | employee_id→employees | — | ix_position_history_employee_id(employee_id) |
| `users` | `User` (core.identity) | 8 | employee_id→employees | username | ix_users_username(username) |
| `access_grants` | `AccessGrant` (core.identity) | 6 | group_id→access_groups, user_id→users | — | ix_access_grants_group_id(group_id), ix_access_grants_user_id(user_id) |
| `access_group_members` | `AccessGroupMember` (core.identity) | 3 | group_id→access_groups, user_id→users | group_id,user_id | ix_access_group_members_group_id(group_id), ix_access_group_members_user_id(user_id) |
| `audit_log` | `AuditLog` (core.audit) | 7 | actor_id→users | — | ix_audit_log_ts(ts) |
| `bank_adjustments` | `BankAdjustment` (modules.timesheet.adapters.orm) | 9 | author_id→users, employee_id→employees | — | ix_bank_adjustments_employee_id(employee_id) |
| `cars` | `Car` (modules.cars.adapters.orm) | 20 | assigned_to→employees, holder_user_id→users | number | ix_cars_number(number) |
| `double_pay_days` | `DoublePayDay` (modules.timesheet.adapters.orm) | 6 | created_by→users | date | ix_double_pay_days_date(date) |
| `employment_periods` | `EmploymentPeriod` (modules.employees.adapters.orm) | 7 | created_by→users, employee_id→employees | — | ix_employment_periods_employee_id(employee_id) |
| `night_area_sections` | `NightAreaSection` (modules.night.adapters.orm) | 15 | area_id→night_areas, closed_by→users, report_id→night_reports, taken_by→users, zone_id→night_zones | report_id,area_id | ix_night_area_sections_report_id(report_id) |
| `notify_dispatches` | `NotifyDispatch` (modules.notify.adapters.orm) | 20 | actor_user_id→users, recipient_id→responsibility_services | — | ix_notify_dispatches_domain(domain), ix_notify_dispatches_recipient_id(recipient_id), ix_notify_dispatches_ref_id(ref_id), ix_notify_dispatches_ts(ts) |
| `photos` | `Photo` (core.media) | 10 | uploaded_by→users | — | ix_photos_kind(kind), ix_photos_ref_id(ref_id) |
| `punches` | `Punch` (modules.timesheet.adapters.orm) | 7 | created_by→users, employee_id→employees | — | ix_punches_emp_ts(employee_id,ts), ix_punches_employee_id(employee_id), ix_punches_ts(ts) |
| `schedule_absences` | `ScheduleAbsence` (modules.timesheet.adapters.orm) | 9 | created_by→users, employee_id→employees, kind_id→shift_types | — | ix_sched_abs_emp_start(employee_id,start_utc), ix_sched_abs_start(start_utc), ix_schedule_absences_employee_id(employee_id) |
| `schedule_shifts` | `ScheduleShift` (modules.timesheet.adapters.orm) | 10 | employee_id→employees, shift_type_id→shift_types, updated_by→users | — | ix_sched_shifts_emp_date(employee_id,date), ix_sched_shifts_start(start_utc), ix_schedule_shifts_date(date), ix_schedule_shifts_employee_id(employee_id) |
| `tabel_days` | `TabelDay` (modules.timesheet.adapters.orm) | 9 | employee_id→employees, updated_by→users | employee_id,date | ix_tabel_days_date(date), ix_tabel_days_employee_id(employee_id) |
| `vip_double_pay` | `VipDoublePay` (modules.timesheet.adapters.orm) | 8 | created_by→users, employee_id→employees | — | ix_vip_double_pay_employee_id(employee_id) |
| `car_history` | `CarHistory` (modules.cars.adapters.orm) | 10 | actor_user_id→users, car_id→cars | — | ix_car_history_car_id(car_id), ix_car_history_car_ts(car_id,ts) |
| `car_night_checks` | `CarNightCheck` (modules.cars.adapters.orm) | 18 | car_id→cars, checker_user_id→users, report_id→night_reports | — | ix_car_night_checks_car_id(car_id), ix_car_night_checks_report_id(report_id) |
| `night_check_items` | `NightCheckItem` (modules.night.adapters.orm) | 15 | answered_by→users, dispatch_id→notify_dispatches, item_id→checklist_items, section_id→night_area_sections, service_id→responsibility_services, zone_item_id→zone_checklist_items | — | ix_night_check_items_section_id(section_id), ix_night_check_items_service_id(service_id) |
| `night_interceptions` | `NightInterception` (modules.night.adapters.orm) | 8 | from_user_id→users, report_id→night_reports, section_id→night_area_sections, to_user_id→users | — | ix_night_interceptions_report_id(report_id), ix_night_interceptions_section_id(section_id) |
