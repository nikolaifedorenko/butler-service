# 17. Мёртвый и дублирующийся код

Перед вердиктом «удалить» каждое имя проверено grep-ом по `app/`, `tests/`, `tools/`, `static/`
(в том числе строковые и динамические ссылки). Сверено с инвентаризацией в неслитой ветке
`chore/review-p2` (`docs/CHANGES-2026-10-21-review-p2-inventory.md`): списки совпадают, здесь они
дополнены. ID → [REPORT.md](REPORT.md).

## 17.1. DEAD-01. Функции без единой ссылки (Факт)
| Функция | Файл:строка | Вердикт |
|---|---|---|
| `delete_photo_files` | `app/core/media.py:320` | **не удалять, а начать вызывать**: при `night_api.delete_area` записи `Photo(kind="night_item")` остаются сиротами (вывод p2-инвентаризации подтверждён чтением) |
| `weekday_short` | `app/core/time.py:50` | удалить |
| `list_templates` | `app/modules/docs/application/doc_render.py:135` | удалить (вместе с мёртвым `GET /api/docs/templates`) |
| `_fmt_hours`, `_tint` | `app/modules/docs/application/grid_docx.py:85,97` | удалить |
| `aware_to_utc_naive`, `days_of` | `app/modules/timesheet/adapters/_db.py:26,42` | удалить |
| `is_working_date` | `app/modules/timesheet/application/base_schedule.py:248` | удалить |
| `double_map_for` | `app/modules/timesheet/application/doublepay.py:137` | удалить |
| `chain_last_period` | `app/modules/timesheet/application/months.py:82` | удалить после сверки с тестами R35 |
| `shift_window`, `month_bounds` | `app/modules/timesheet/application/schedule_helpers.py:71,85` | удалить |
| `daterange` | `app/modules/timesheet/application/schedule_patterns.py:111` | удалить |
| `brief` (метод) | `app/modules/timesheet/application/shiftrev.py:71` | удалить |
| `midnight_of_settings` | `app/modules/timesheet/domain/time/local_midnight.py:18` | удалить |
| `view_schedule` | `app/modules/timesheet/application/schedule_view.py:20` | **оставить**: контракт спецификации 16.3 |
| `retention_days`, `close_month`, `recalculate_month` | `core/media.py:357`, `months.py:87,93` | вызываются только тестами. Проверить, нужны ли тесты, иначе удалить вместе с ними |

Безопасное удаление: одна функция за коммит, затем `ruff`, `lint-imports`, `pytest`. Страж —
grep-тест «имя не встречается в `app/`».

## 17.2. DEAD-02. Маршруты без UI
По 12-ui-api.md: удалить `GET /api/auth/employees-for-demo`,
`GET /api/employees/{id}/bank-adjustments`, `GET /api/mgmt/periods`, `GET /api/docs/templates`,
`GET /api/notify/dispatches` (проверить по `grep` в `tools/*.mjs` — там вызовов нет). Алиасы
`/api/night/photos/{id}/file` и `DELETE /api/night/photos/{id}` удалить после проверки, что в
выгруженных DOCX и старых сообщениях Telegram нет ссылок на них (сообщения ссылок на фото не
содержат, вложения отправляются файлами). Пять массовых операций Графика (`patterns`,
`fill-pattern`, `continue`, `copy`, `clear-month`) требуют решения владельца (В-7).

## 17.3. DEAD-03. Инструменты и прототипы
| Файл | Вердикт |
|---|---|
| `tools/verify_requirements.py` | **сломан** (StopIteration, проверяет старую тему). Удалить или переписать |
| `tools/cleanup_dev_db.py` | одноразовый скрипт от 27.09: удаляет из `timesheet_rows` и `schedule_entries`, которых больше нет. Удалить |
| `tools/kill_server.py` | ни одной ссылки в `tools/`, `docs/`, `README.md`, `run.sh`, CI — удалить или описать в README как ручную утилиту |
| `docs/prototypes/night-report-v2.html` (147 КБ), `settings-ia.html` (110 КБ) + `*.smoke.mjs` | прототипы реализованы (CHANGES 19.10). Перенести в `docs/archive/` или удалить: они не участвуют в CI |
| `tools/*_scenario.mjs`, `run_*_scenario.sh`, `snapshot.mjs`, `ui_harness.mjs` | актуальны, их гоняет CI (`ci.yml:150-201`) |
| `tools/check_api_contract.py`, `gen_js_globals.py`, `bump_version.py`, `export_openapi.py`, `freeze_requirements.py` | актуальны (CI) |

## 17.4. DEAD-04. Зависимости
- `python-dotenv` (`requirements.txt:7`) не импортируется. `.env` читает `pydantic-settings`,
  который сам зависит от `python-dotenv`. Прямую строку можно убрать, на установку это не
  повлияет. Low.
- `prometheus-client` — опциональный, импорт под `try` (`observability.py:114-123`). Оставить.

## 17.5. Дубли
| Что | Где | Вердикт |
|---|---|---|
| Хелперы времени | `core/time.py` (`TZ`, `now_local`, `utc_to_local`, `utcnow`) и `timesheet/adapters/_db.py:10-31` (`TZ` из того же `APP_TZ`, `local_naive_to_utc`, …) | оставить один источник `core/time.py`; адаптеры импортируют из него (правило R5 разрешает «модуль → core») |
| Форматирование часов | 5 реализаций, 2 мёртвые (p2 §2.1) | удалить мёртвые, живые переименовать по контракту |
| `except ValueError → 409` вокруг загрузки Settings | 5 мест (`mgmt_api`, `presence_api`, `fact_api`) — p2 §2.2 | один хелпер |
| Проверки «супервайзер и выше» и «admin/manager» строками | 8 мест (AUTHZ-05) | заменить ключами прав |
| Выборка «что отправить» | `night_api.py:1104-1112` и `night_notify.py:90-99` | вынести в одну функцию сервиса |
| `/api/night/photos/*` и `/api/photos/*` | см. 17.2 | — |
