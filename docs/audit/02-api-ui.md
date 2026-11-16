# 02. Матрица «API ↔ UI» (сгенерировано `docs/audit/scripts/api_ui_matrix.py`)

Коммит `3801abf`. Литералов `/api/…` в JS: **216**; маршрутов `/api/*`: **187**; маршрутов без вызова из JS: **21**; литералов без маршрута: **1**.

Метод `ANY` — метод не найден рядом с литералом (обычно GET или адрес передаётся дальше). Сопоставление «по префиксу» (★) — путь собирается конкатенацией, проверено вручную в 12-ui-api.md.

## 2.1. Маршрут → кто вызывает

| Метод | Путь | Обработчик | Вызовы из JS (файл:строка → функция) |
|---|---|---|---|
| POST | `/api/auth/login` | `access/interface/auth_routes.py:113` | **— нет вызовов —** |
| GET | `/api/auth/login-form` | `access/interface/auth_routes.py:123` | `static/index.html:37` → `(верхний уровень)` |
| POST | `/api/auth/login-form` | `access/interface/auth_routes.py:134` | `static/index.html:37` → `(верхний уровень)` |
| POST | `/api/auth/logout` | `access/interface/auth_routes.py:158` | `app.js:359` → `loadDirectory` |
| GET | `/api/auth/me` | `access/interface/auth_routes.py:175` | `app.js:229` → `loadPerms`<br>`app.js:417` → `bootApp`<br>`modules/employees.js:135` → `onMount`<br>`modules/me.js:13` → `loadMe`<br>`modules/me.js:166` → `loadMeSilently`<br>`modules/me.js:186` → `doPunch` |
| POST | `/api/auth/change-password` | `access/interface/auth_routes.py:203` | `app.js:381` → `onMount` |
| POST | `/api/auth/impersonate` | `access/interface/auth_routes.py:227` | `modules/employees.js:134` → `onMount` |
| POST | `/api/auth/impersonate/stop` | `access/interface/auth_routes.py:243` | `app.js:390` → `onMount` |
| GET | `/api/auth/employees-for-demo` | `access/interface/auth_routes.py:256` | **— нет вызовов —** |
| GET | `/api/employees` | `employees/interface/employees.py:178` | `app.js:317` → `loadDirectory`<br>`modules/employees.js:54` → `openEmployeeCard`<br>`modules/timesheet_v4.js:345` → `loadFactSessions` |
| GET | `/api/group-choices` | `employees/interface/employees.py:192` | `modules/employees.js:215` → `datedActionModal`<br>`modules/employees.js:287` → `rehireModal`<br>`modules/employees.js:398` → `employeeModal` |
| POST | `/api/employees/suggest-genitive` | `employees/interface/employees.py:205` | `modules/employees.js:491` → `onMount` |
| POST | `/api/employees` | `employees/interface/employees.py:212` | `app.js:317` → `loadDirectory`<br>`modules/employees.js:525` → `onMount`<br>`modules/employees.js:54` → `openEmployeeCard`<br>`modules/timesheet_v4.js:345` → `loadFactSessions` |
| PUT | `/api/employees/{employee_id}` | `employees/interface/employees.py:264` | `modules/employees.js:526` → `onMount` |
| POST | `/api/employees/{employee_id}/position-change` | `employees/interface/employees.py:340` | `modules/employees.js:266` → `renderPattern` |
| POST | `/api/employees/{employee_id}/block-change` | `employees/interface/employees.py:348` | `modules/employees.js:270` → `renderPattern` |
| POST | `/api/employees/{employee_id}/dismiss` | `employees/interface/employees.py:356` | `modules/employees.js:272` → `renderPattern` |
| POST | `/api/employees/{employee_id}/rehire` | `employees/interface/employees.py:376` | `modules/employees.js:333` → `onMount` |
| POST | `/api/employees/{employee_id}/bank-adjust` | `employees/interface/employees.py:422` | `modules/employees.js:386` → `reopen` |
| GET | `/api/employees/{employee_id}/bank-adjustments` | `employees/interface/employees.py:457` | **— нет вызовов —** |
| DELETE | `/api/employees/{employee_id}/bank-adjustments/{adjustment_id}` | `employees/interface/employees.py:471` | `modules/employees.js:376` → `reopen` |
| GET | `/api/employees/{employee_id}/history` | `employees/interface/employees.py:486` | `modules/employees.js:371` → `reopen`<br>`modules/employees.js:72` → `employeeCard` |
| POST | `/api/employees/{employee_id}/deactivate` | `employees/interface/employees.py:539` | **— нет вызовов —** |
| POST | `/api/employees/{employee_id}/delete` | `employees/interface/employees.py:560` | `modules/employees.js:153` → `onMount` |
| GET | `/api/departments` | `employees/interface/employees.py:582` | `app.js:321` → `loadDirectory`<br>`modules/dicts.js:15` → `renderDicts`<br>`modules/dicts.js:61` → `add`<br>`modules/employees.js:402` → `employeeModal` |
| POST | `/api/departments` | `employees/interface/employees.py:592` | `app.js:321` → `loadDirectory`<br>`modules/dicts.js:15` → `renderDicts`<br>`modules/dicts.js:61` → `add`<br>`modules/employees.js:402` → `employeeModal` |
| PUT | `/api/departments/{dep_id}` | `employees/interface/employees.py:607` | **— нет вызовов —** |
| DELETE | `/api/departments/{dep_id}` | `employees/interface/employees.py:626` | **— нет вызовов —** |
| GET | `/api/subdivisions` | `employees/interface/employees.py:644` | `app.js:322` → `loadDirectory`<br>`modules/dicts.js:16` → `renderDicts`<br>`modules/dicts.js:62` → `add`<br>`modules/employees.js:403` → `employeeModal` |
| POST | `/api/subdivisions` | `employees/interface/employees.py:654` | `app.js:322` → `loadDirectory`<br>`modules/dicts.js:16` → `renderDicts`<br>`modules/dicts.js:62` → `add`<br>`modules/employees.js:403` → `employeeModal` |
| PUT | `/api/subdivisions/{sub_id}` | `employees/interface/employees.py:669` | **— нет вызовов —** |
| DELETE | `/api/subdivisions/{sub_id}` | `employees/interface/employees.py:694` | **— нет вызовов —** |
| GET | `/api/tabel-values` | `employees/interface/employees.py:729` | `modules/employees.js:220` → `datedActionModal`<br>`modules/employees.js:294` → `rehireModal` |
| GET | `/api/shift-types` | `employees/interface/employees.py:759` | `app.js:317` → `loadDirectory`<br>`modules/settings.js:1781` → `settingsScreenShifts`<br>`modules/timesheet_layers.js:12` → `loadSchedule` |
| GET | `/api/shift-types/tabel-codes` | `employees/interface/employees.py:779` | `app.js:332` → `loadDirectory`<br>`modules/dicts.js:349` → `shiftModal`<br>`modules/timesheet_layers.js:448` → `onMount` |
| POST | `/api/shift-types` | `employees/interface/employees.py:815` | `app.js:317` → `loadDirectory`<br>`modules/dicts.js:439` → `recalc`<br>`modules/settings.js:1781` → `settingsScreenShifts`<br>`modules/timesheet_layers.js:12` → `loadSchedule` |
| PUT | `/api/shift-types/{type_id}` | `employees/interface/employees.py:829` | `app.js:332` → `loadDirectory`<br>`modules/dicts.js:349` → `shiftModal`<br>`modules/dicts.js:440` → `recalc`<br>`modules/timesheet_layers.js:448` → `onMount` |
| DELETE | `/api/shift-types/{type_id}` | `employees/interface/employees.py:878` | `app.js:332` → `loadDirectory`<br>`modules/dicts.js:349` → `shiftModal`<br>`modules/settings.js:1856` → `settingsScreenShifts`<br>`modules/timesheet_layers.js:448` → `onMount` |
| POST | `/api/shift-types/{type_id}/restore` | `employees/interface/employees.py:899` | `modules/settings.js:1864` → `settingsScreenShifts` |
| GET | `/api/shift-types/{type_id}/revisions` | `employees/interface/employees.py:913` | **— нет вызовов —** |
| GET | `/api/schedule` | `timesheet/interface/schedule.py:245` | `modules/timesheet_layers.js:14` → `loadSchedule` |
| PUT | `/api/schedule/shift` | `timesheet/interface/schedule.py:424` | `modules/timesheet_layers.js:648` → `pick` |
| DELETE | `/api/schedule/shift` | `timesheet/interface/schedule.py:476` | `modules/timesheet_layers.js:657` → `pick` |
| POST | `/api/schedule/absence` | `timesheet/interface/schedule.py:503` | `modules/timesheet_layers.js:669` → `addAbsence` |
| DELETE | `/api/schedule/absence/{absence_id}` | `timesheet/interface/schedule.py:538` | `modules/timesheet_layers.js:749` → `hm` |
| POST | `/api/schedule/range-absence` | `timesheet/interface/schedule.py:719` | `modules/timesheet_layers.js:465` → `onMount` |
| GET | `/api/schedule/timeoff-hours` | `timesheet/interface/schedule.py:805` | `modules/timesheet_layers.js:702` → `showTimeoffHours` |
| GET | `/api/schedule/absence-period` | `timesheet/interface/schedule.py:860` | `modules/docs.js:49` → `absencePeriodInfo` ★ |
| GET | `/api/schedule/patterns` | `timesheet/interface/schedule.py:986` | **— нет вызовов —** |
| POST | `/api/schedule/fill-pattern` | `timesheet/interface/schedule.py:991` | **— нет вызовов —** |
| POST | `/api/schedule/continue` | `timesheet/interface/schedule.py:1093` | **— нет вызовов —** |
| POST | `/api/schedule/copy` | `timesheet/interface/schedule.py:1120` | **— нет вызовов —** |
| POST | `/api/schedule/clear-month` | `timesheet/interface/schedule.py:1179` | **— нет вызовов —** |
| POST | `/api/schedule/reset-month` | `timesheet/interface/schedule.py:1213` | `modules/timesheet_layers.js:76` → `shiftMonth` |
| GET | `/api/schedule/xlsx` | `timesheet/interface/schedule.py:1266` | `modules/timesheet_layers.js:66` → `shiftMonth` |
| GET | `/api/schedule/pdf` | `timesheet/interface/schedule.py:1314` | `modules/timesheet_layers.js:65` → `shiftMonth` |
| GET | `/api/punches/status` | `timesheet/interface/punches.py:210` | `modules/me.js:13` → `loadMe`<br>`modules/me.js:165` → `loadMeSilently` |
| POST | `/api/punches` | `timesheet/interface/punches.py:222` | `modules/me.js:183` → `doPunch`<br>`modules/me.js:228` → `loadMyHistory` |
| GET | `/api/punches` | `timesheet/interface/punches.py:351` | `modules/me.js:228` → `loadMyHistory` |
| DELETE | `/api/punches/{punch_id}` | `timesheet/interface/punches.py:392` | `modules/me.js:13` → `loadMe`<br>`modules/me.js:165` → `loadMeSilently` |
| PUT | `/api/punches/{punch_id}/note` | `timesheet/interface/punches.py:410` | `modules/me.js:213` → `onMount` |
| GET | `/api/tabel` | `timesheet/interface/tabel_api.py:74` | `modules/timesheet_v4.js:524` → `loadTabel` |
| PUT | `/api/tabel/cell` | `timesheet/interface/tabel_api.py:180` | `modules/timesheet_v4.js:718` → `ifSaved` |
| POST | `/api/tabel/bulk` | `timesheet/interface/tabel_api.py:189` | `modules/timesheet_v4.js:714` → `ifSaved` |
| POST | `/api/tabel/fill-from-cycles` | `timesheet/interface/tabel_api.py:226` | `modules/timesheet_v4.js:755` → `onMount` |
| POST | `/api/tabel/reset` | `timesheet/interface/tabel_api.py:289` | `modules/timesheet_v4.js:802` → `onMount` |
| GET | `/api/mgmt` | `timesheet/interface/mgmt_api.py:107` | `modules/timesheet_v4.js:866` → `shiftPeriod`<br>`modules/timesheet_v4.js:968` → `mgmtDetail` |
| POST | `/api/mgmt/close` | `timesheet/interface/mgmt_api.py:159` | `modules/timesheet_v4.js:954` → `mgmtAction` ★ |
| POST | `/api/mgmt/recalculate` | `timesheet/interface/mgmt_api.py:169` | `modules/timesheet_v4.js:954` → `mgmtAction` ★ |
| GET | `/api/mgmt/periods` | `timesheet/interface/mgmt_api.py:179` | **— нет вызовов —** |
| GET | `/api/mgmt/xlsx` | `timesheet/interface/mgmt_api.py:209` | `modules/timesheet_v4.js:878` → `shiftPeriod` |
| GET | `/api/presence/board` | `timesheet/interface/presence_api.py:26` | `modules/timesheet_v4.js:79` → `fetchMarks` |
| GET | `/api/fact/sessions` | `timesheet/interface/fact_api.py:48` | `modules/timesheet_v4.js:470` → `fetchFact` |
| GET | `/api/fact/month` | `timesheet/interface/fact_api.py:73` | `modules/timesheet_v4.js:227` → `loadFactMonth` |
| GET | `/api/fact/day` | `timesheet/interface/fact_api.py:280` | `modules/timesheet_v4.js:392` → `fetchFactDay` |
| GET | `/api/access` | `access/interface/access_api.py:31` | `modules/timesheet_v4.js:1050` → `loadAccess` |
| PUT | `/api/access/roles/{role}` | `access/interface/access_api.py:75` | `modules/timesheet_v4.js:1095` → `onMount` |
| POST | `/api/access/groups` | `access/interface/access_api.py:92` | `modules/timesheet_v4.js:1122` → `userName` |
| PUT | `/api/access/groups/{group_id}` | `access/interface/access_api.py:108` | **— нет вызовов —** |
| DELETE | `/api/access/groups/{group_id}` | `access/interface/access_api.py:127` | `modules/timesheet_v4.js:1155` → `onMount` |
| PUT | `/api/access/groups/{group_id}/grants` | `access/interface/access_api.py:141` | `modules/timesheet_v4.js:1132` → `onMount` |
| PUT | `/api/access/groups/{group_id}/members` | `access/interface/access_api.py:157` | `modules/timesheet_v4.js:1149` → `onMount` |
| PUT | `/api/access/users/{user_id}/grants` | `access/interface/access_api.py:178` | `modules/timesheet_v4.js:1180` → `onMount` |
| GET | `/api/audit` | `audit/interface/audit_api.py:76` | `modules/timesheet_v4.js:1218` → `qs` |
| GET | `/api/audit/csv` | `audit/interface/audit_api.py:89` | `modules/timesheet_v4.js:1216` → `qs` |
| GET | `/api/engine-settings` | `timesheet/interface/engine_settings_api.py:41` | `modules/settings.js:130` → `settingsEngine`<br>`modules/settings.js:2028` → `settingsScreenSystem`<br>`modules/settings.js:2040` → `onMount`<br>`modules/settings.js:690` → `settingsCompareWithPrevious`<br>`modules/settings.js:717` → `onMount`<br>`modules/timesheet_v4.js:1256` → `renderEngineSettings` |
| PUT | `/api/engine-settings` | `timesheet/interface/engine_settings_api.py:87` | `modules/settings.js:130` → `settingsEngine`<br>`modules/settings.js:2028` → `settingsScreenSystem`<br>`modules/settings.js:2040` → `onMount`<br>`modules/settings.js:555` → `render`<br>`modules/settings.js:690` → `settingsCompareWithPrevious`<br>`modules/settings.js:717` → `onMount`<br>`modules/timesheet_v4.js:1256` → `renderEngineSettings`<br>`modules/timesheet_v4.js:1323` → `hm` |
| GET | `/api/engine-settings/modifiers` | `timesheet/interface/engine_settings_api.py:158` | `modules/settings.js:1655` → `settingsScreenCalendar`<br>`modules/settings.js:952` → `settingsScreenPay`<br>`modules/timesheet_v4.js:1257` → `renderEngineSettings` |
| POST | `/api/engine-settings/modifiers` | `timesheet/interface/engine_settings_api.py:238` | `modules/settings.js:1162` → `render`<br>`modules/settings.js:1655` → `settingsScreenCalendar`<br>`modules/settings.js:952` → `settingsScreenPay`<br>`modules/timesheet_v4.js:1257` → `renderEngineSettings`<br>`modules/timesheet_v4.js:1331` → `hm` |
| DELETE | `/api/engine-settings/modifiers/{mod_id}` | `timesheet/interface/engine_settings_api.py:278` | `modules/settings.js:1044` → `shiftMonth`<br>`modules/timesheet_v4.js:1335` → `hm` |
| GET | `/api/engine-settings/health` | `timesheet/interface/engine_settings_api.py:430` | `modules/settings.js:134` → `settingsHealth` |
| GET | `/api/engine-settings/rules/resolve` | `timesheet/interface/engine_settings_api.py:556` | `modules/settings.js:1199` → `run` |
| GET | `/api/settings` | `settings/interface/settings_api.py:69` | `modules/docs.js:30` → `getDocTemplates`<br>`modules/settings.js:226` → `loadSettings` |
| PUT | `/api/settings/doc` | `settings/interface/settings_api.py:107` | `modules/settings.js:1942` → `input` |
| PUT | `/api/settings/base` | `settings/interface/settings_api.py:123` | `modules/settings.js:1640` → `syncCycle` |
| PUT | `/api/settings` | `settings/interface/settings_api.py:153` | `modules/docs.js:30` → `getDocTemplates`<br>`modules/settings.js:1935` → `input`<br>`modules/settings.js:226` → `loadSettings` |
| GET | `/api/docs/kinds` | `docs/interface/docs_api.py:90` | `app.js:326` → `loadDirectory`<br>`modules/docs.js:34` → `getDocTemplates`<br>`modules/settings.js:1250` → `settingsScreenCodes`<br>`modules/settings.js:1879` → `settingsScreenDocs`<br>`modules/timesheet_layers.js:718` → `showTimeoffHours` |
| POST | `/api/docs/kinds` | `docs/interface/docs_api.py:112` | `app.js:326` → `loadDirectory`<br>`modules/dicts.js:177` → `onMount`<br>`modules/docs.js:34` → `getDocTemplates`<br>`modules/settings.js:1250` → `settingsScreenCodes`<br>`modules/settings.js:1879` → `settingsScreenDocs`<br>`modules/timesheet_layers.js:718` → `showTimeoffHours` |
| PUT | `/api/docs/kinds/{kind_id}` | `docs/interface/docs_api.py:131` | `modules/dicts.js:180` → `onMount` |
| DELETE | `/api/docs/kinds/{kind_id}` | `docs/interface/docs_api.py:148` | `modules/dicts.js:165` → `onMount` |
| GET | `/api/docs/templates` | `docs/interface/docs_api.py:168` | **— нет вызовов —** |
| GET | `/api/docs/sample` | `docs/interface/docs_api.py:180` | `modules/dicts.js:132` → `onMount` |
| POST | `/api/docs/templates` | `docs/interface/docs_api.py:190` | `modules/dicts.js:141` → `onMount` |
| DELETE | `/api/docs/templates` | `docs/interface/docs_api.py:209` | `modules/dicts.js:155` → `onMount` |
| POST | `/api/docs/render` | `docs/interface/docs_api.py:234` | `modules/docs.js:92` → `downloadAbsenceDoc` |
| GET | `/api/doublepay` | `timesheet/interface/doublepay.py:113` | `modules/dicts.js:212` → `refreshDoublePay`<br>`modules/settings.js:1656` → `settingsScreenCalendar` |
| POST | `/api/doublepay/days` | `timesheet/interface/doublepay.py:141` | `modules/dicts.js:297` → `refreshDoublePay` |
| DELETE | `/api/doublepay/days/{day_id}` | `timesheet/interface/doublepay.py:198` | `modules/dicts.js:324` → `refreshDoublePay` |
| POST | `/api/doublepay/vip` | `timesheet/interface/doublepay.py:220` | `modules/dicts.js:313` → `refreshDoublePay` |
| DELETE | `/api/doublepay/vip/{vip_id}` | `timesheet/interface/doublepay.py:250` | `modules/dicts.js:335` → `refreshDoublePay` |
| GET | `/api/night/areas` | `night/interface/night_api.py:182` | `modules/night.js:1301` → `renderItems`<br>`modules/night.js:724` → `render` |
| POST | `/api/night/areas/bulk` | `night/interface/night_api.py:217` | `modules/night.js:908` → `bindDictAreas` |
| POST | `/api/night/areas` | `night/interface/night_api.py:239` | `modules/night.js:1301` → `renderItems`<br>`modules/night.js:724` → `render`<br>`modules/night.js:897` → `bindDictAreas` |
| PUT | `/api/night/areas/{area_id}` | `night/interface/night_api.py:257` | `modules/night.js:960` → `onMount` |
| DELETE | `/api/night/areas/{area_id}` | `night/interface/night_api.py:287` | `modules/night.js:929` → `bindDictAreas` |
| POST | `/api/night/areas/{area_id}/items` | `night/interface/night_api.py:307` | `modules/night.js:1332` → `onMount` |
| PUT | `/api/night/items/{item_id}` | `night/interface/night_api.py:342` | `modules/night.js:1355` → `onMount`<br>`modules/night.js:1368` → `onMount` |
| DELETE | `/api/night/items/{item_id}` | `night/interface/night_api.py:377` | `modules/night.js:1375` → `onMount` |
| GET | `/api/night/zones` | `night/interface/night_api.py:446` | `modules/night.js:724` → `render` |
| POST | `/api/night/zones` | `night/interface/night_api.py:470` | `modules/night.js:724` → `render`<br>`modules/night.js:791` → `bindNightDictScreen` |
| PUT | `/api/night/zones/{zone_id}` | `night/interface/night_api.py:486` | `modules/night.js:831` → `onMount` |
| DELETE | `/api/night/zones/{zone_id}` | `night/interface/night_api.py:513` | `modules/night.js:805` → `bindNightDictScreen` |
| GET | `/api/night/zones/{zone_id}/items` | `night/interface/night_api.py:533` | `modules/night.js:1116` → `dictItemsTab` |
| POST | `/api/night/zones/{zone_id}/items` | `night/interface/night_api.py:560` | `modules/night.js:1116` → `dictItemsTab`<br>`modules/night.js:1184` → `dictItemsTab` |
| PUT | `/api/night/zone-items/{item_id}` | `night/interface/night_api.py:606` | `modules/night.js:1196` → `dictItemsTab`<br>`modules/night.js:1247` → `onMount` |
| DELETE | `/api/night/zone-items/{item_id}` | `night/interface/night_api.py:642` | `modules/night.js:1208` → `dictItemsTab` |
| GET | `/api/night/areas/{area_id}/checklist` | `night/interface/night_api.py:657` | `modules/night.js:1124` → `dictItemsTab` |
| PUT | `/api/night/areas/{area_id}/overrides/{zone_item_id}` | `night/interface/night_api.py:699` | `modules/night.js:1286` → `onMount` |
| DELETE | `/api/night/areas/{area_id}/overrides/{zone_item_id}` | `night/interface/night_api.py:741` | `modules/night.js:1280` → `onMount` |
| GET | `/api/night/services` | `night/interface/night_api.py:769` | `modules/night.js:1301` → `renderItems`<br>`modules/night.js:725` → `render` |
| POST | `/api/night/services` | `night/interface/night_api.py:788` | `modules/night.js:1016` → `bindDictServices`<br>`modules/night.js:1301` → `renderItems`<br>`modules/night.js:725` → `render` |
| PUT | `/api/night/services/{service_id}` | `night/interface/night_api.py:809` | `modules/night.js:1093` → `onMount` |
| DELETE | `/api/night/services/{service_id}` | `night/interface/night_api.py:849` | `modules/night.js:1030` → `bindDictServices` |
| GET | `/api/night/today` | `night/interface/night_api.py:872` | `modules/night.js:67` → `fetchNight` |
| GET | `/api/night/reports` | `night/interface/night_api.py:895` | `modules/night.js:676` → `nightArchiveModal` |
| GET | `/api/night/reports/{report_id}` | `night/interface/night_api.py:906` | `modules/night.js:65` → `fetchNight`<br>`modules/night.js:706` → `exportNight` ★ |
| POST | `/api/night/sections/{section_id}/take` | `night/interface/night_api.py:924` | `modules/night.js:421` → `sectionTake` |
| POST | `/api/night/sections/{section_id}/close` | `night/interface/night_api.py:965` | `modules/night.js:435` → `sectionClose` |
| POST | `/api/night/sections/{section_id}/reopen` | `night/interface/night_api.py:991` | `modules/night.js:337` → `reload` |
| PUT | `/api/night/items/{item_id}/answer` | `night/interface/night_api.py:1004` | `modules/night.js:347` → `reload`<br>`modules/night.js:459` → `onMount` |
| POST | `/api/night/items/{item_id}/photo` | `night/interface/night_api.py:1032` | `modules/night.js:365` → `reload` |
| GET | `/api/night/reports/{report_id}/defects` | `night/interface/night_api.py:1063` | `modules/night.js:1460` → `render`<br>`modules/night.js:706` → `exportNight` ★ |
| POST | `/api/night/reports/{report_id}/dispatch` | `night/interface/night_api.py:1073` | `modules/night.js:1505` → `send`<br>`modules/night.js:706` → `exportNight` ★ |
| GET | `/api/night/reports/{report_id}/dispatches` | `night/interface/night_api.py:1086` | `modules/night.js:706` → `exportNight` ★ |
| POST | `/api/night/reports/{report_id}/defects/preview` | `night/interface/night_api.py:1097` | `modules/night.js:1535` → `send`<br>`modules/night.js:706` → `exportNight` ★ |
| GET | `/api/night/photos/{photo_id}/file` | `night/interface/night_api.py:1128` | **— нет вызовов —** |
| GET | `/api/night/reports/{report_id}/cars` | `night/interface/night_api.py:1152` | `modules/night.js:472` → `render`<br>`modules/night.js:526` → `nightCarCheckModal`<br>`modules/night.js:706` → `exportNight` ★ |
| POST | `/api/night/reports/{report_id}/cars/{car_id}/check` | `night/interface/night_api.py:1162` | `modules/night.js:619` → `syncFound`<br>`modules/night.js:706` → `exportNight` ★ |
| POST | `/api/night/reports/{report_id}/cars/finish` | `night/interface/night_api.py:1240` | `modules/night.js:631` → `send`<br>`modules/night.js:706` → `exportNight` ★ |
| POST | `/api/night/reports/{report_id}/close` | `night/interface/night_api.py:1271` | `modules/night.js:650` → `send`<br>`modules/night.js:706` → `exportNight` ★ |
| POST | `/api/night/reports/{report_id}/reopen` | `night/interface/night_api.py:1295` | `modules/night.js:669` → `reopenReport`<br>`modules/night.js:706` → `exportNight` ★ |
| DELETE | `/api/night/photos/{photo_id}` | `night/interface/night_api.py:1317` | **— нет вызовов —** |
| GET | `/api/night/reports/{report_id}/export.docx` | `night/interface/night_api.py:1332` | `modules/night.js:706` → `exportNight` ★ |
| GET | `/api/night/reports/{report_id}/export.pdf` | `night/interface/night_api.py:1347` | `modules/night.js:706` → `exportNight` ★ |
| GET | `/api/cars/meta` | `cars/interface/cars_api.py:107` | `modules/cars.js:48` → `fetchCars`<br>`modules/cars.js:585` → `render` |
| DELETE | `/api/cars/locations/{loc_id}` | `cars/interface/cars_api.py:126` | `modules/cars.js:665` → `bindCarsDictScreen` |
| GET | `/api/cars/locations` | `cars/interface/cars_api.py:148` | `modules/cars.js:244` → `ensureCarLocations`<br>`modules/cars.js:586` → `render` |
| POST | `/api/cars/locations` | `cars/interface/cars_api.py:155` | `modules/cars.js:244` → `ensureCarLocations`<br>`modules/cars.js:586` → `render`<br>`modules/cars.js:645` → `bindCarsDictScreen` |
| PUT | `/api/cars/locations/{loc_id}` | `cars/interface/cars_api.py:167` | `modules/cars.js:652` → `bindCarsDictScreen`<br>`modules/cars.js:657` → `bindCarsDictScreen` |
| GET | `/api/cars` | `cars/interface/cars_api.py:180` | `modules/cars.js:47` → `fetchCars`<br>`modules/cars.js:584` → `render`<br>`modules/me.js:110` → `bindCarStrip` |
| POST | `/api/cars` | `cars/interface/cars_api.py:205` | `modules/cars.js:47` → `fetchCars`<br>`modules/cars.js:516` → `onMount`<br>`modules/cars.js:584` → `render`<br>`modules/me.js:110` → `bindCarStrip` |
| PUT | `/api/cars/{car_id}` | `cars/interface/cars_api.py:217` | `modules/cars.js:244` → `ensureCarLocations`<br>`modules/cars.js:48` → `fetchCars`<br>`modules/cars.js:490` → `onMount`<br>`modules/cars.js:585` → `render`<br>`modules/cars.js:586` → `render` |
| GET | `/api/cars/{car_id}/history` | `cars/interface/cars_api.py:230` | `modules/cars.js:527` → `carHistoryModal` |
| POST | `/api/cars/{car_id}/take` | `cars/interface/cars_api.py:248` | `modules/cars.js:211` → `carTake`<br>`modules/me.js:140` → `bindCarStrip`<br>`modules/me.js:147` → `bindCarStrip` |
| POST | `/api/cars/{car_id}/handover` | `cars/interface/cars_api.py:261` | `modules/cars.js:384` → `onMount` |
| POST | `/api/cars/{car_id}/give` | `cars/interface/cars_api.py:276` | `modules/cars.js:410` → `onMount` |
| POST | `/api/cars/{car_id}/return` | `cars/interface/cars_api.py:291` | `modules/cars.js:354` → `onMount` |
| POST | `/api/cars/{car_id}/assign` | `cars/interface/cars_api.py:338` | `modules/cars.js:437` → `onMount` |
| POST | `/api/cars/{car_id}/status` | `cars/interface/cars_api.py:352` | `modules/cars.js:466` → `onMount` |
| GET | `/api/notify/config` | `notify/interface/notify_api.py:97` | `modules/settings.js:2190` → `settingsScreenNotify` |
| PUT | `/api/notify/config` | `notify/interface/notify_api.py:105` | `modules/settings.js:2190` → `settingsScreenNotify`<br>`modules/settings.js:2317` → `settingsScreenNotify`<br>`modules/settings.js:2357` → `settingsScreenNotify` |
| POST | `/api/notify/telegram/check` | `notify/interface/notify_api.py:120` | `modules/settings.js:2326` → `settingsScreenNotify` |
| POST | `/api/notify/telegram/chats` | `notify/interface/notify_api.py:138` | `modules/settings.js:2334` → `settingsScreenNotify` |
| GET | `/api/notify/chats` | `notify/interface/notify_api.py:156` | `modules/night.js:1040` → `serviceEditModal` |
| POST | `/api/notify/telegram/test` | `notify/interface/notify_api.py:162` | `modules/settings.js:2341` → `settingsScreenNotify` |
| POST | `/api/notify/email/test` | `notify/interface/notify_api.py:180` | `modules/settings.js:2366` → `settingsScreenNotify` |
| GET | `/api/notify/dispatches` | `notify/interface/notify_api.py:202` | **— нет вызовов —** |
| GET | `/api/notify/dispatches/export.csv` | `notify/interface/notify_api.py:225` | `modules/night.js:1562` → `onMount`<br>`modules/settings.js:2411` → `onMount` |
| POST | `/api/notify/dispatches/{dispatch_id}/resend` | `notify/interface/notify_api.py:273` | `modules/night.js:1565` → `onMount` |
| GET | `/api/notify/templates` | `notify/interface/notify_api.py:297` | `modules/settings.js:2199` → `settingsScreenNotify` |
| PUT | `/api/notify/templates/{domain}` | `notify/interface/notify_api.py:303` | `modules/settings.js:2383` → `settingsScreenNotify`<br>`modules/settings.js:2404` → `onMount` |
| POST | `/api/notify/templates/{domain}/preview` | `notify/interface/notify_api.py:327` | `modules/settings.js:2390` → `settingsScreenNotify` |
| GET | `/api/photos/limits` | `app/core/media_api.py:32` | `core.js:275` → `loadMediaLimits` |
| GET | `/api/photos/{photo_id}/file` | `app/core/media_api.py:39` | **— нет вызовов —** |
| DELETE | `/api/photos/{photo_id}` | `app/core/media_api.py:50` | `core.js:275` → `loadMediaLimits`<br>`modules/cars.js:567` → `bindPhotoDelete` |
| GET | `/api/selfcheck` | `app/main.py:282` | `app.js:291` → `enterApp`<br>`modules/settings.js:2023` → `settingsScreenSystem` |
| GET | `/api/health` | `app/main.py:302` | `app.js:412` → `bootApp` |

## 2.2. Литералы `/api/…` в JS без маршрута

- `static/sw.js:38` → `(верхний уровень)`: `ANY /api/`

## 2.3. Вызовы с нелитеральным адресом (проверить вручную)

- `static/js/core.js:132` → `httpError`: `api(path`
- `static/js/core.js:147` → `api`: `fetch(path`
- `static/js/core.js:171` → `api`: `multipartApi(path`
- `static/js/core.js:178` → `multipartApi`: `fetch(path`
- `static/js/core.js:287` → `mediaHint`: `downloadBlob(path`
- `static/js/core.js:290` → `downloadBlob`: `fetch(path`
- `static/js/modules/dicts.js:43` → `add`: `api(url`
- `static/sw.js:42` → `(верхний уровень)`: `fetch(req`
- `static/sw.js:52` → `(верхний уровень)`: `fetch(req`
