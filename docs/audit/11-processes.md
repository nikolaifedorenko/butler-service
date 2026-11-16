# 11. Ключевые процессы: кто, где, откуда, куда, зачем, как

Принятая нагрузка: один объект, десятки сотрудников (в сиде 11), 2–5 одновременных
пользователей в пересменку. Прод: 2 воркера uvicorn, PostgreSQL. Права указаны по
`ROLE_DEFAULTS` (`app/core/permissions.py:73-80`). «Аудит» — вызов `core/audit.py:audit()`
в той же транзакции, если не сказано иное. ID находок — в [REPORT.md](REPORT.md).

## 11.1. Вход, выход, смена пароля, «войти как сотрудник»
| | |
|---|---|
| Кто | любой (вход); вошедший (выход, смена пароля); `employees.impersonate` (имперсонация: admin, manager, supervisor) |
| Где | `access/interface/auth_routes.py:89-120` (JSON), `:134-155` (форма), `:158-172` (выход), `:203-220` (пароль), `:227-253` (имперсонация) → `core/security.py` (PBKDF2 600k, токен `base64(json).hmac[:32]`) → `core/auth.py:78-95` (`current_principal`) |
| Откуда / куда | `users` (хеш, `token_version`), cookie `tt_session` (httponly, SameSite=Lax, `Secure` по `COOKIE_SECURE`), `audit_log` |
| Как | rate-limit 10 неудач за 5 мин на IP в памяти процесса (`:30-65`); выход и смена пароля увеличивают `token_version` (отзыв на всех устройствах); имперсонация выдаёт токен с `uid` менеджера и `emp_id` сотрудника, права считаются как у роли employee (`permissions.py:112-114`) |
| Находки | SEC-01 (подмена XFF обходит лимит), SEC-02 (демо-учётки `demo1234` на боевой базе), AUTHZ-01 (имперсонация без `can_manage_user`, журнал пишет имя сотрудника), AUTHZ-04 (сброс пароля админом не отзывает сессии), AUTHZ-10 (сессия «как сотрудник» живёт после блокировки сотрудника) |

## 11.2. Отметка «Пришёл/Ушёл»
| | |
|---|---|
| Кто | `me.punch` — за себя; `punches.manage` + `punches.punch_for_others` — за другого; `punches.backfill` — задним числом (до 62 дней) |
| Где | `timesheet/interface/punches.py:222-350` → `application/punch_plan.py` (план на сегодня) → ORM `Punch` |
| Откуда / куда | `schedule_shifts`/`schedule_absences` (план), `tabel_days` + код дня (режим отметок), `punches` (запись), `audit_log` |
| Как | `threading.Lock` на сотрудника внутри процесса (`:64-70`) + `SELECT … FOR UPDATE` строки `employees` (`:244`). В PostgreSQL это корректно сериализует (Вероятно, PG не запускали); SQLite FOR UPDATE игнорирует, но в SQLite-профиле один воркер. Дубль автокнопки отсекается окном 60 с (`:300-307`) |
| Находки | AUTHZ-02 (запрос «за другого» без `punch_for_others` молча ставит отметку себе). Отметка задним числом в закрытый период не блокируется — по спецификации закрытый период неизменяем и это допустимо (`docs/overtime_spec_v7_1_final.md:1476`), см. вопрос владельцу В-6 |

## 11.3. Правка Графика и Табеля
| | |
|---|---|
| Кто | `schedule.edit` (admin/manager/supervisor), `tabel.edit` (то же) |
| Где | `timesheet/interface/schedule.py` (74 КБ, 10 изменяющих маршрутов), `tabel_api.py:180-300` → `application/timesheet_edit.py:26-65` (`lock_state`: open / last_closed / locked), `tabel_fill.py`, `base_schedule.py`, `schedule_view.py` (перегенерация Графика из Табеля) |
| Откуда / куда | `tabel_days` (unique employee_id+date), `schedule_shifts` (generated/manual), `schedule_absences`, `block_assignments`, `settings`, `audit_log` |
| Как | правка ячейки Табеля → доменные проверки (F-16) → запись → перегенерация Графика дня ±1. Закрытый период (кроме последнего) — `TimesheetLockedError`. Конкурентная правка одной ячейки: побеждает последний, версии нет |
| Находки | ARCH-02 (бизнес-логика остаётся в 74-КБ роутере), DEAD-02 (5 маршрутов Графика без UI: patterns, fill-pattern, continue, copy, clear-month), PERF-02 (Табель 6 SQL на сотрудника) |

## 11.4. Управленческий табель: просмотр, закрытие, пересчёт
| | |
|---|---|
| Кто | `mgmt.view`, `mgmt.close` (admin/manager/supervisor), `mgmt.recalculate` (admin/manager) |
| Где | `timesheet/interface/mgmt_api.py:140-175` → `application/close_period.py:31-54`, `recalculate.py` → `adapters/sql_uow.py`, `sql_closings.py` |
| Откуда / куда | Табель, отметки, График, настройки движка (версия по дате начала периода) → `period_closings` (unique employee_id+period_start), банк, переносы, снимок входа и флагов |
| Как | у каждого сотрудника своя транзакция (UoW). Повторное или конкурентное закрытие ловит уникальный ключ и превращает в 409 (`close_period.py:38-53`). Запись аудита — **отдельной** транзакцией после цикла (`mgmt_api.py:162-165`) |
| Находки | ARCH-01 (аудит закрытия не в транзакции закрытия: при сбое после цикла периоды закрыты без записи в журнале), PERF-02 (14 SQL на сотрудника — это свойство конвейера, тест `test_query_budget.py` это фиксирует) |

## 11.5. Жизненный цикл сотрудника
| | |
|---|---|
| Кто | `employees.edit` (admin/manager/supervisor) + `can_manage_user` (иерархия ролей); банк часов — только роли admin/manager (`employees.py:389-392`) |
| Где | `employees/interface/employees.py:212-316` (создание и правка прямо в роутере), `application/lifecycle.py` (перевод, увольнение, повторный приём: 4 `db.commit()` внутри сервиса), `application/employment.py` |
| Откуда / куда | `employees`, `users`, `employment_periods`, `position_history`, `block_assignments`, `emergency_contacts`, `bank_adjustments`, `audit_log` |
| Находки | AUTHZ-03 (PUT без `role` понижает до employee; в аудит пишется только ФИО), AUTHZ-04, UI-01 («Стартовый банк часов» сохраняется, но движок его не читает), ARCH-01 (commit в сервисе) |

## 11.6. Ночной отчёт
| | |
|---|---|
| Кто | `night.view` (у всех ролей), `night.edit` (справочник), `night.close` (закрытие и переоткрытие смены); ход обхода — **любой вошедший** |
| Где | `night/interface/night_api.py` (75 КБ) → `application/night.py` (создание и автозакрытие), `night_notify.py` (отправка службам), `night_export.py` (DOCX/XLSX) → `notify/application/dispatch.py` → транспорты |
| Откуда / куда | `night_reports` (unique date), `night_area_sections`, `night_check_items`, `photos`, `car_night_checks`, `notify_dispatches`; Telegram и почта |
| Как | создание и автозакрытие в 08:00 делает фоновый поток (`bootstrap/night_sync.py`) под `try_lock`; GET больше не пишет в БД (P1 20.10, подтверждено чтением `night_api.py:872-903`) |
| Находки | AUTHZ-06 (взять, отметить, закрыть область, фото, кары без `night.view`), CONC-02 (отправка в сеть внутри запроса до commit: дубли), PERF-01 (архив 750 SQL на 31 отчёт), CONC-04 (2 `async def` с синхронной БД), AUTHZ-09 (удаление фото-доказательств из закрытого отчёта) |

## 11.7. Электрокары
| | |
|---|---|
| Кто | `cars.view`, `cars.use` (взять, вернуть, передать — все роли), `cars.issue` (выдать, закрепить, статус — supervisor+), `cars.manage` (парк — admin/manager) |
| Где | `cars/interface/cars_api.py` → `application/cars.py:195-357` |
| Откуда / куда | `cars` (unique number), `car_history`, `car_locations`, `photos` |
| Находки | CONC-01 (два телефона берут один кар: оба успешны), BUG-02 («выдать» снимает кар с обслуживания в обход правила менеджера), BUG-03 (`by_name` при возврате принимается от любого), AUTHZ-05 (роли строками в сервисе), CONC-04 (`car_return` — `async def`) |

## 11.8. Уведомления
| | |
|---|---|
| Кто | `settings.edit` (конфигурация, шаблоны, журнал, повтор); `settings.edit` или `night.edit` — список чатов; отправку недостатков запускает `night.view` |
| Где | `notify/interface/notify_api.py` → `application/{config,dispatch,recipients,templates,chats}.py` → `adapters/transports/{telegram,email}.py` |
| Как | секреты (токен, пароль SMTP) хранятся в `settings` открытым текстом, в API отдаются маской (`notify/application/config.py:96-112`) |
| Находки | SEC-03 (адрес Bot API и SMTP-хост меняются в UI: токен и пароль уходят на любой хост, SSRF), CONC-02 |

## 11.9. Документы
| | |
|---|---|
| Кто | `settings.view` (рендер заявлений, образцы), `settings.edit` (виды и бланки) |
| Где | `docs/interface/docs_api.py` → `application/doc_render.py`, `doc_templates.py`, `grid_docx.py`; `core/render.py` (PDF) |
| Как | бланк `templates/<code>.docx`, код по регулярке, zip-лимиты, python-docx без разрешения сущностей; PDF через LibreOffice до 180 с синхронно |
| Находки | PERF-04 (генерация в потоке запроса), CONC-04 (`upload_template` — `async def` с разбором DOCX на event loop) |

## 11.10. Настройки и справочники
| | |
|---|---|
| Кто | `settings.view` / `settings.edit` (admin, manager; supervisor — только просмотр); двойная оплата — роль admin/manager в теле (`timesheet/interface/doublepay.py:44-48`); `access.manage` — права |
| Где | `settings/interface/settings_api.py`, `timesheet/interface/engine_settings_api.py` (версии настроек движка), `doublepay.py`, `access/interface/access_api.py` |
| Находки | CONC-03 (две вкладки редактора настроек: молча побеждает последняя публикация), HARD-01 (часовой пояс движка редактируется в UI отдельно от `APP_TZ`), AUTHZ-05 |

## 11.11. Бизнес-логика в роутерах и дубли
- В interface-слое остаются целые сценарии: `employees.py:212-316` (создание и правка учётки вместе
  с периодами, историей и контактами), `night_api.py:925-1000` (взять область, перехват,
  переоткрытие), `night_api.py:1097-1125` (предпросмотр рассылки дублирует выборку
  `night_notify.dispatch_defects:90-99`), `schedule.py` (74 КБ: сетка, правки, массовые операции,
  XLSX и PDF).
- Одинаковые правила в двух местах: «супервайзер и выше» строками ролей в `cars.py:241,294`,
  `cars_api.py:150`, `night_api.py:948`; «admin или manager» в `employees.py:390` и
  `timesheet/interface/doublepay.py:47`; фильтр «что можно отправить» в `night_api.py:1104-1112` и
  `night_notify.py:90-99`.
- Дубли форматтеров часов (`formatting.hours_text`, `grid_docx._fmt_hours` мёртвые, три живые
  реализации с разными контрактами) подробно описаны в
  `docs/CHANGES-2026-10-21-review-p2-inventory.md` §2.1 (ветка `chore/review-p2`). Проверено
  выборочно, совпадает с кодом.
