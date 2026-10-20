# Изменения 20.10.2026 — этап C, фаза C6: фронтенд `static/js/modules/`

Исполнение `docs/EXECUTION-SPEC-v2.md` (фаза 8, §6). Реорганизация фронтенда:
разделы переехали в `static/js/modules/` под имена модулей бэкенда. Перенос
**1:1, без слияния файлов и без переписывания логики**; глобальные функции
сохранены (ADR-0008) — отказ от `window.App.modules.*` отклонён спекой
(§0 п.5: property-доступ не проверяется `no-undef` статически).

## 1. Карта переноса (§6, имена из спеки)

| Было | Стало |
|------|-------|
| `section_grid.js` | `modules/timesheet_layers.js` |
| `section_v4.js` | `modules/timesheet_v4.js` |
| `section_me.js` | `modules/me.js` |
| `section_employees.js` | `modules/employees.js` |
| `section_night.js` | `modules/night.js` |
| `section_cars.js` | `modules/cars.js` |
| `section_docs.js` | `modules/docs.js` |
| `section_dicts.js` | `modules/dicts.js` |
| `section_settings.js` | `modules/settings.js` |

`core.js` и `app.js` остались на месте (ядро и оболочка). Порядок подключения
в `index.html` сохранён, включая зафиксированные зависимости:
**cars → night → timesheet_v4 → settings** (night использует CAR_BADGE/
CHARGE_OPTS/photoThumb из cars; settings — renderEngineSettings из v4 и
реестр SETTINGS_SCREENS из cars/night). Комментарии в index.html и файлах
переведены на новые имена.

## 2. Обязательные сопутствующие правки (§6 — все в этой же фазе)

* **`tools/bump_version.py`**: `local_assets()` переведён на `rglob` +
  относительные пути — SHELL `sw.js` пересобирается с файлами `modules/`
  (дефект v1 §0 п.6: нерекурсивный glob ломал бы PWA). Версия статики поднята:
  **`2026-10-19h` → `2026-10-20a`** (index.html ×12 замен, sw.js VERSION +
  SHELL из 16 элементов).
* **`tools/gen_js_globals.py`**: сканирование `rglob`, ключи `by_file`/
  `used_elsewhere` — относительные пути (`modules/cars.js`); `js_globals.json`
  перегенерирован (320 имён, 11 файлов); маппинг ESLint `static/js/${file}`
  совместим без правок.
* **`eslint.config.mjs`**: не менялся — паттерн `static/js/**/*.js` уже
  рекурсивен, per-file `varsIgnorePattern`-настройки подъезжают из
  js_globals.json (относительные ключи).
* **`tools/check_api_contract.py`**: `rglob` — вызовы API из `modules/`
  продолжают сверяться с openapi (154 вызова, все имеют маршрут).
* **`tools/ui_harness.mjs` и сценарии**: не менялись — читают `<script src>`
  из index.html (проверено смоуками).
* **`static/sw.js`**: SHELL regenerated (все 9 файлов modules/ в пре-кэше).
* `docs/prototypes/*.smoke.mjs` не затрагивались (автономны, §6).
* `tools/snapshot.mjs` — обновлено упоминание имён в пояснительном тексте.

## 3. Проверки (фаза 8 — полный набор смоуков)

* `bump_version --check` ✓ (2026-10-20a согласована, SHELL 14 ассетов);
* `gen_js_globals --check` ✓ (320 имён); `check_api_contract` ✓;
* `npm run lint` — **0 errors** (2 warnings — предсуществующие no-unused-vars
  в timesheet_layers/settings, разрешены varsIgnorePattern-исключениями);
* `run_ui_check` **на трёх ролях**: admin (52 запроса), ivanov (25), gromova
  (52) — 0 пустых разделов, 0 сбоев, 0 ошибок консоли;
* сценарии: **settings ✓, night_zones ✓, night_cars ✓, layers ✓, norms ✓**
  (весь набор фазы 8; snapshot — опционально, не запускался);
* бэкенд не менялся: pytest **642/5s**; ruff (весь репозиторий) ✓;
  lint-imports 14/14; `export_openapi --check` — без дельты.

## 4. Дальше

**C7 (фаза 9)** — документация: ARCHITECTURE.md (слои, §3.5 клиент,
онбординг-маршрут), README (структура, quick start), SPEC.md (пути),
AST-покрытие всех модулей (DoD), финальные статусы ADR; продуктовые батчи
(§5.2 is_manager → права; R6 relationship → порты) — отдельные решения владельца.
