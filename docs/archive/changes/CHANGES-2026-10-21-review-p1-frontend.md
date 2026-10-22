# Изменения 21.10.2026 — батч review-P1: фронтенд

Четвёртый батч по внешнему ревью `REVIEW-2026-10-20.md` (продолжение P0 — PR #65,
P1 «ночь/кары» — PR #66, P1 «таймшит/движок» — PR #67; план батчей — §8
`docs/archive/changes/CHANGES-2026-10-20-review-p1-night-cars.md`). Закрыты шесть находок P1
в клиентских скриптах (`static/js/`, SPA без сборки — ADR-0008).

Версия статики поднята: **2026-10-21a** (index.html `?v=`, SHELL `sw.js`).
Новые стражи: `tests/test_review_p1_frontend.py` (8).

## 1. P1 — `resetUserViewState`: утечка состояния между пользователями

**Проблема.** Выход не перезагружает страницу (SPA): сбрасывались только
fact-поля, `employees`, `grafikLayer` и вкладки «Графика». Кэши справочников
(`shiftTypes/departments/subdivisions/docKinds/docPlaceholders/tabelCodes`),
сетка/табель/статус, фильтры, позиция UI (год/месяц/`attDate`/`dpYear`),
состояния модулей (`carsState`, `nightState`, `settingsUI`) и DOM чужих разделов
переживали смену пользователя — следующий видел чужие данные/черновики/позицию
(например, сотрудник после менеджера — кэш справочников в памяти, админ после
админа — чужой черновик справочников и открытый экран).

**Исправление.** `resetUserViewState()` (app.js) сбрасывает всё перечисленное:
кэши — в пустые, позицию UI — на «сегодня» по часам объекта (`serverShiftMs`),
состояния модулей — в начальные (`Object.assign`, исходные литералы сохранены),
все `.view` — в пустое состояние index.html (каркас `#view-grafik` восстановит
`grafikSkeleton()` — `loadGrafik` проверяет `#grafik-tabs`; прежняя очистка
одного `#grafik-tabs` поглощена общей). **Исключение:** `settingsUI.searchBound`
НЕ сбрасывается — флаг стережёт одноразовую привязку document-листнера ⌘K,
которая не снимается: сброс удвоил бы обработчик (страж `test_fe1_reset_keeps_search_bound_flag`).

## 2. P1 — селектор rehire: `workShifts` вместо значений Табеля

**Проблема.** `rehireModal` передавал в `patternFieldsHtml('rh', kind, workShifts, …)`
словарь типов смен (`state.shiftTypes`, форма `{id, code, start_time, …}`), а
«Значение рабочего дня» (18.10.2026) строится из `/api/tabel-values`
(`{value, title, start_hm, end_hm}` — код + окно CFG-WINDOWS): селектор рисовал
пустые option «undefined · undefined», выбор значения при повторном приёме был
невозможен (молча уходило значение блока по умолчанию).

**Исправление.** Загрузка `/api/tabel-values` в `rehireModal` — по образцу модалки
перевода блока (`da`, employees.js:220); `patternFieldsHtml('rh', kind, values, today)`.

## 3. P1 — `esc(double_title)` в title ячейки Графика

**Проблема.** `timesheet_layers.js`: `title="… день двойной оплаты (' + (d.double_title || '') + ')…"` —
подстановка в HTML-атрибут без экранирования. Сегодня `double_title` — константы
`SCOPE_TITLES` с бэкенда, но точка выхода в HTML обязана защищать класс риска
(как `cssColor` для цветов из БД).

**Исправление.** `esc(d.double_title || '')`. Страж сканирует ВСЕ JS-файлы:
любое упоминание `double_title` — только в строке с `esc(`.

## 4. P1 — сырой JSON в тосте 422

**Проблема.** FastAPI на 422 (pydantic-валидация) отдаёт `detail` МАССИВОМ
`{loc, msg, type}`; `api()` string'ифицировал объект через `JSON.stringify` —
пользователь видел в тосте `[{"loc":["body","year"],"msg":…}]`.

**Исправление.** Общая `httpError(msg, status)` в core.js: массив → «year:
Input should be a valid integer» (поле + причина, несколько — через «;», пустой
массив → «Ошибка <status>»); структурный 409 (`{message, …}` — «перехват области»,
«всё равно закрыть?») сохраняет прежний контракт `e.message/e.payload/e.status`
(на них завязана логика подтверждения); строковый `detail` — без изменений.
Подключена в обоих транспортах: `api()` и `multipartApi()` (там был свой
нетипизированный разбор). Поведенческий страж гоняет чистую функцию в node.

## 5. P1 — `loadMyHistory()` без catch

**Проблема.** Раздел «Я»: сбой `/api/punches` уходил в `unhandledrejection` —
глобальный обработчик пугал общим тостом «Ошибка интерфейса … обновите страницу
(Cmd/Ctrl+Shift+R)», хотя история — некритичная панель.

**Исправление.** `loadMyHistory().catch(…)` — причина показывается плашкой в самой
панели истории. `bindCarStrip()` не затронут — у него свой try/catch («Раздел недоступен»).

## 6. P1 — гонка `settingsRenderScreen`

**Проблема.** Быстрое переключение экранов Настроек: `await item.render(body)`
прежнего экрана возвращался ПОСЛЕ нового и перезаписывал общий `#st-body` чужим
содержимым — nav подсвечивал один экран, показывался другой; `settingsFail` и
`settingsUpdateDraftBars` тоже срабатывали от устаревшего рендера.

**Исправление.** Счётчик поколений `settingsRenderGen` + рендер в СВЕЖИЙ узел:
`old.cloneNode(false)` + `replaceWith` — запоздалый render пишет в отсоединённый
старый узел и невидим; `id`/`class` сохраняются, поэтому `$('#st-body')` везде
указывает на актуальный узел. Стражи поколения — в обработке сбоя
(`gen === settingsRenderGen`) и перед обновлением черновых панелей
(`gen !== settingsRenderGen → return`). Сигнатуры `render(body)` не менялись —
экраны правок не потребовали.

## 7. Стражи и проверки

* `tests/test_review_p1_frontend.py` (8) — source-сканы (прецедент test_review_p0:
  JS без сборки, юнит-инфраструктуры нет) + поведенческий прогон `httpError` в node:
  полнота сброса и исключение `searchBound`, tabel-values в rehire, `double_title`
  только через `esc`, оба транспорта через `httpError`, `loadMyHistory().catch`,
  поколение + свежий узел в `settingsRenderScreen`;
* eslint: **0 errors, 2 warnings** (те же два, что до батча — новых нет);
  `node --check` всех скриптов ✓; `gen_js_globals --check` ✓ (**322** имени:
  добавились `httpError`, `settingsRenderGen`);
* смоуки (jsdom + живой сервер): ui_check **admin/gromova/ivanov — пустых разделов 0,
  сбоев 0, ошибок консоли 0**; сценарии settings **76/76**, layers **68/68**,
  norms **106/106**, night_zones **87/87**;
* night_cars в песочнице прогона (Node 20 + jsdom 26) падает на загрузке фото —
  **идентично на чистом main до батча** (эмуляция multipart/File окружением,
  не регрессия); штатная среда сценария — Node 22 + jsdom 30 (CI frontend-job);
* pytest день: **787 passed / 5 skipped**; «ночь» (`faketime '2026-10-21 02:30:00'`):
  **788 / 4** (было 780/4 после батча P1 timesheet — добавилось 8 стражей);
* ruff ✓; `lint-imports` **14/14**; `export_openapi --check` — без дельты (156 путей);
  `check_api_contract` ✓ (188 маршрутов / 154 вызова SPA); `bump_version --check` ✓
  (**2026-10-21a**); `freeze_requirements --check` ✓.

## 8. Дальше (по плану батчей ревью)

* **Батч 5 — P1 прочее:** границы фильтра аудита (−3 ч хардкод), `cc` в `resend()`,
  FK/unique-валидации до INSERT, потоковое чтение медиа (лимит 500 МБ в память).
* **Батч 6 — P2:** мёртвый код и no-op миграции, консолидация дублей,
  архитектурные протечки (adapters→interface в `sql_closings`, god-роутеры),
  устаревшие пути в докстрингах, lock-файлы prod/dev, блокирующие pip-audit/npm-audit.
* **Стратегия (отдельные решения):** Alembic (ADR-0002) + таблица версий миграций;
  кэш/выборочность settle для day_grid/mgmt.
