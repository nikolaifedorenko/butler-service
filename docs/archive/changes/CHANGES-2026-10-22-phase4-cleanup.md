# Изменения 22.10.2026 — фаза 4: мёртвый код, наследие v4, хардкод

Седьмой батч по `docs/audit/PLAN.md`: фаза 4, шаги 4.1–4.7. Закрыты DEAD-01…04, DB-03, OPS-04 и
остаток HARD-02. Решения владельца — В-7 (удалить пять скрытых операций Графика) и В-10 (окно
ночной смены 20:00–08:00 остаётся).

Версия статики: `2026-10-22d`. Схема БД не менялась. OpenAPI: 156 → 146 путей.
Новые стражи: `tests/test_audit_phase4.py` (2).

## 1. Мёртвые функции (DEAD-01)

* Удалены 14 функций без единой ссылки: `weekday_short`, `list_templates`, `_fmt_hours`,
  `_tint`, `aware_to_utc_naive`, `days_of`, `is_working_date`, `double_map_for`,
  `chain_last_period`, `shift_window`, `month_bounds`, `daterange`, `ShiftRevision.brief`,
  `midnight_of_settings`. Перед удалением каждую заново проверил поиском по `app/`, `tests/`,
  `tools/` и `static/`.
* `delete_photo_files` не удалена, а начала работать: при удалении объекта обхода пункты
  открытых смен уходят каскадом, и вместе с ними теперь удаляются их фото (записи и файлы).
  Раньше они оставались сиротами.
* Оставлены по смыслу: `view_schedule` (контракт спецификации 16.3), `close_month` и
  `recalculate_month` (обёртки 16.6 со своими тестами), `retention_days` (покрыт тестом).

## 2. Маршруты без интерфейса и пять операций Графика (DEAD-02, В-7)

* Удалены операции Графика без кнопок: `GET /api/schedule/patterns`, `POST /fill-pattern`,
  `/continue`, `/copy`, `/clear-month`. Вместе с ними удалён код, нужный только им: генераторы
  «N/M» и пресеты в `schedule_patterns.py`. Там остался только разбор произвольного цикла для
  базового цикла сотрудника. `reset-month` остаётся (им пользуется интерфейс).
* Удалены маршруты, к которым никто не обращается:
  * `GET /api/auth/employees-for-demo`;
  * `GET /api/employees/{id}/bank-adjustments` — те же данные отдаёт `/history`;
  * `GET /api/docs/templates` — то же отдаёт `/api/docs/kinds`;
  * `GET /api/notify/dispatches` — интерфейс выгружает CSV;
  * алиасы `/api/night/photos/{id}/file` и `DELETE /api/night/photos/{id}` — ссылок на них
    нет ни в интерфейсе, ни в выгрузках, ни в сообщениях.
* Оставлен `GET /api/mgmt/periods`: он описан в `docs/SPEC.md` как часть контракта слоя 3.
* Тесты и сценарий `layers` заполняли график через `fill-pattern`. Теперь это массовая правка
  Табеля («Я 12» / «В» по циклу 2/2), как в интерфейсе. Тесты самих удалённых операций
  удалены (8).

## 3. Инструменты, прототипы, зависимости (DEAD-03, DEAD-04)

* Удалены `tools/verify_requirements.py` (падал), `tools/cleanup_dev_db.py` (чистил таблицы,
  которых больше нет) и `tools/kill_server.py` (ни одной ссылки).
* Прототипы `docs/prototypes/` перенесены в `docs/archive/prototypes/` (с `README.md`). Скрипты
  `smoke:proto*` из `package.json` убраны, ссылки в двух PROPOSAL-документах обновлены.
* Из `requirements.txt` убрана строка `python-dotenv`: `.env` читает `pydantic-settings`, а он
  сам тянет этот пакет. Лок-файл не изменился.

## 4. Пустые и противоречивые шаги старых миграций (DB-03)

* Убраны добавления колонок в `timesheet_rows` и `schedule_entries`: эти таблицы удаляет
  соседний шаг `migrate_engine_v7`.
* Удалены пустые функции `_migrate_remove_sick_unpaid`, `_migrate_missing_shifts`,
  `_apply_timesheet_code_normative`, `migrate_shift_tabel_codes` (и вызов из `main.py`), а также
  их тесты-заглушки (2).
* Убран маркер `engine_v7_reset`: его только записывали и никогда не читали. README утверждал,
  что по маркеру данные «очищаются», хотя автоочистка давно отключена; текст исправлен.
* Обновление базы, созданной до Alembic, по-прежнему покрыто `test_db_upgrade.py`.

## 5. Наследие v4 (шаг 4.5)

* `static/js/modules/timesheet_v4.js` (1340 строк) разделён по экранам, файлы подключаются там
  же, где был он:
  * `timesheet_common.js` — общие помощники;
  * `marks.js`, `fact.js`, `tabel.js`, `mgmt.js`, `access.js`, `audit.js`, `engine_settings.js` —
    по файлу на экран.

  Код перенесён без изменений; верхнеуровневый код там только инициализирует `state`, поэтому
  от порядка файлов он не зависит.
* `tests/test_v4_api.py` → `tests/test_engine_api.py`. Упоминания обновлены в README,
  ARCHITECTURE, SPEC, `main.py`, `app.js`, `settings.js`.
* **Не сделано:** префикс `v4` в именах функций (`v4CodeColor`, `v4MonthNav` …) оставлен —
  переименование задело бы все экраны ради имени.

## 6. Хардкод (HARD-02, В-10)

* Интервалы опроса разделов собраны в `POLL_MS` рядом с `poll()` в `app.js`: доска и «Мои
  отметки» — 30 с, ночной обход и кары — 60 с.
* Пояс в подсказках флагов УТ (`interface/views.py`) берётся из `APP_TZ`, а не из строки
  `"Europe/Moscow"`.
* Окно ночной смены 20:00–08:00 не трогали (решение владельца В-10). Подпись пояса на экране
  каров берётся с сервера с фазы 2.

## 7. Документация API в проде (OPS-04)

Новый флаг `API_DOCS`: по умолчанию `1`, в `docker-compose.prod.yml` — `0`. При `0` Swagger
`/api/docs` и схема `/api/openapi.json` не отдаются. ReDoc выключен всегда: `/redoc` уходит в
оболочку SPA. Флаг описан в `deploy/README.md` §3, `.env.example` и чек-листе `docs/AUTH.md`.
`docs/openapi.json` по-прежнему собирает `tools/export_openapi.py`.

## Проверки

* `pytest`: **844 passed** на SQLite и **844 passed** на PostgreSQL 16.15 (1 пропуск: тест ждёт
  число месяца ≥ 26).
* Мутации подтвердили, что стражи падают без исправлений: удаление фото при удалении объекта,
  флаг `API_DOCS`.
* `npm run lint`: 0 ошибок (2 старых предупреждения). Все семь UI-сценариев в jsdom зелёные,
  включая полный обход разделов за менеджера и за сотрудника после разреза `timesheet_v4.js`.
* `ruff`, `lint-imports` (14/14), `check_api_contract`, `gen_js_globals --check`,
  `bump_version --check` (SHELL — 21 файл), `export_openapi --check`.
* `freeze_requirements --check` по-прежнему показывает только `colorama` из инструментов аудита
  в venv.
