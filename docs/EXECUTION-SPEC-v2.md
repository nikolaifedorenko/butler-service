# SPEC v2: Реструктуринг butler-service — `core/` + `modules/`

> **Роль файла:** единственная инструкция для исполнения (заменяет присланный
> `EXECUTION-SPEC.md` ред. «2026-10-20» — далее «v1»). Аудитория — LLM-агент/разработчик.
> **Статус:** ПРОЕКТ — вступает в силу после (а) принятия `docs/adr/0010-modular-monolith-core-modules.md`
> и (б) мержа PR #50 (единый центр настроек).
> **Цель:** та же, что у v1 — единая гексагональная структура `core/` + `modules/`, —
> но план исполним: устранены противоречия v1, закрыты пробелы, из-за которых CI и PWA
> сломались бы в середине перестройки.

---

## 0. Заключение по v1: что исправлено в этой ревизии

Факты ниже проверены по коду (grep/запуски) на main@73a53a8 и ветке feat/settings-ia.

| # | Дефект v1 | Исправление в v2 |
|---|-----------|------------------|
| 1 | `core/seed.py`, `core/migrations.py` импортировали бы модели сотрудников, ночных зон, каров, служб → **core зависит от модулей**, направление зависимостей перевёрнуто | seed/migrations/реестр моделей вынесены в **composition root** (`app/bootstrap.py` + `app/main.py`) — единственное место, которому разрешено импортировать все модули (правило R5) |
| 2 | Противоречие: §4.1 «core/db.py ← все модели», §4.2 «модели — по модулям» | Модели — **в модулях** (это адаптеры хранения); в core живёт только `Base`/engine/сессия + кросс-модульная модель `Photo` (см. §2, R6) |
| 3 | `.importlinter` обновляется в фазе 7, но §6.1 требует `lint-imports` зелёным после каждой фазы (текущие контракты жёстко прописаны по `app.api/app.services/app.models/app.engine`) | Контракты переводятся на новые пути **в той же фазе, что и перенос** (§7, «транзитные контракты») |
| 4 | `tests/engine/test_architecture.py` (AST-законы движка) хардкодит префикс `app.engine` — фаза 2 v1 ломает его молча | Явный шаг в фазе 4: префиксы AST-тестов и их данных переводятся на `app.modules.timesheet` |
| 5 | Фронтенд: `window.App.modules.<name>.<fn>()` убивает статическую проверку `gen_js_globals` + ESLint `no-undef` — инструмент, который исторически поймал регрессию «пропавшие loadNight/loadCars → пустой интерфейс» | Глобалы и реестр **сохраняются** (ADR-0008); реорганизация — только папки/имена файлов, без слияния файлов и без namespace-объекта (§6) |
| 6 | `static/js/modules/*.js` не попали бы в пре-кэш `sw.js`: `tools/bump_version.py` собирает SHELL через нерекурсивный `glob("*")` → PWA ломается | `bump_version.py` переводится на `rglob` + явный шаг в фазе 8; обновляются `index.html`, `eslint.config.mjs`, `tools/*.mjs` |
| 7 | «Каталог прав покрывает require_manager/require_supervisor» — неправда: для закрытия/переоткрытия ночной смены и части операций ключей нет | Фаза 2 — сначала **добавить недостающие ключи** (`night.close` и др., таблица §5.2), потом менять 52 вызова |
| 8 | «can_manage_user перевести на права» — это страж анти-эскалации (ролевая иерархия), а не право; задокументированное исключение ADR-0006 | Остаётся как есть, в `core/auth_guards.py`, с комментарием; в DoD — «не тронут» |
| 9 | «Центральный маппинг ошибок» подаётся как новое строительство | Он **уже есть** (`app/services/errors.py` + 6 хэндлеров в `main.py`, дополнение ADR-0006). Работа — перенос файла в `core/errors.py` и добавление хэндлера `ConfigError` (§5.3) |
| 10 | Спека не упоминает открытый PR #50, который двигает `night_api`, `cars`, `settings` | Фаза 0 — мерж PR #50 и заморозка конфликтующих веток |
| 11 | Мелочи-маркеры слепого обзора: «утверждено 2026-10-20» (завтра), «i18n в core.js» (i18n в проекте нет), «PyYAML удалить из venv» (он и не объявлен) | Убраны; чистка зависимостей оставлена только в части, подтверждённой grep'ом (§8) |
| 12 | Перестройка противоречит ADR-0006 («без big-bang-рефакторинга»), не отменяя его | ADR-0010 (в этом PR) формально **superseded**-ит ADR-0006; исполнение начинается только после его принятия |

**Что из v1 подтвердилось и сохранено:** мёртвые зависимости (pillow, playwright,
PyYAML, bcrypt/passlib в run.sh — `security.py` использует только `pbkdf2_hmac`),
мёртвые обёртки `doc_render.docx_to_pdf`/`pdf_mode` (живые — `pdf_available`/`pdf_status`),
коллизия имён `validate_pattern`, карта переноса модулей (§5.4 ниже — с поправками),
фазовая дисциплина «CI зелёный → коммит → следующая фаза».

---

## 1. Термины

- **Модуль** — самодостаточный гексагон в `app/modules/<name>/`: `domain`, `application`,
  `ports`, `adapters`, `interface`. Тривиальный слой может быть одним файлом
  (`domain.py`, `ports.py`) — имена слоёв обязательны.
- **core** — инфраструктура в `app/core/`: конфигурация, БД-сессия, ошибки, безопасность,
  права, время, наблюдаемость, аудит, медиа. **Не знает о модулях** (R5).
- **composition root** — `app/main.py` + `app/bootstrap.py`: сборка приложения, реестр
  моделей, seed, миграции. Единственное место с правом импортировать всё.
- **Правило «core или module»:** бизнес-правила или свой экран → модуль;
  хранение/транспорт/принуждение → core.

## 2. Целевая структура

```
app/
  core/
    config.py            # app/config.py
    db.py                # app/db.py: engine, SessionLocal, Base (БЕЗ моделей)
    errors.py            # app/services/errors.py (иерархия уже существует)
    security.py          # app/security.py (pbkdf2, без bcrypt)
    auth.py              # Principal, current_principal, сессии (БЕЗ login-роутов)
    auth_guards.py       # can_manage_user — страж иерархии ролей (не право!)
    permissions.py       # каталог PERMISSIONS + require_perm + has_perm
    time.py              # app/deps.py: TZ, now_local, utc_to_local, local_date
    observability.py     # middleware из main.py: request-id, метрики, access-log
    audit.py             # audit() из app/auth.py
    media.py             # app/photos.py + модель Photo (кросс-модульное медиахранилище)
  bootstrap.py           # seed + migrations + реестр моделей (composition root)
  modules/
    timesheet/  employees/  night/  cars/  docs/  notify/  settings/  access/  audit/
      каждый: domain/ application/ ports/ adapters/ interface/ (+ bootstrap.py у timesheet)
  main.py                # composition root: include_router, exception_handler, middleware
```

Модели SQLAlchemy — **в модулях** (`adapters/orm.py` или `adapters/models.py`):
это адаптеры хранения. Исключение — `Photo` (core/media): её используют night, cars
и будущие разделы по строковым `kind`/`ref_id`, не зная друг о друге.

## 3. Правила слоёв (проверяются import-linter после КАЖДОЙ фазы)

| Слой | Содержит | Импортирует |
|------|----------|-------------|
| `domain/` | сущности, чистые функции (без I/O) | stdlib, `core.errors` |
| `application/` | use case'ы | `domain`, `ports`, `core.errors` |
| `ports/` | Protocol-классы, типы | `domain`, `core` |
| `adapters/` | SQLAlchemy, httpx, fs | `ports`, `domain`, `core` |
| `interface/` | FastAPI-роутеры, pydantic-схемы | `application`, `ports`, `core` |

- **R1 (изоляция домена):** `domain/` не импортирует `application/ports/adapters/interface`,
  `core.config`, `core.db`.
- **R2 (тонкий interface):** в `interface/` нет бизнес-логики — парсинг, `Depends`,
  вызов use case'а; ошибки не переводятся в текст руками (см. §5.3).
- **R3 (межмодульно):** модуль A импортирует из B только `B.application.*` и `B.ports.*`.
  `B.domain.*`, `B.adapters.*`, `B.interface.*` — запрещены.
- **R4 (публичная поверхность):** `domain/__init__.py` и `application/__init__.py`
  re-экспортируют публичные символы; импорт — с границы пакета.
- **R5 (ядро не знает модулей):** `core/*` не импортирует `modules.*`, `bootstrap`,
  `main`. Обратное разрешено. Единственный импортёр всех модулей — composition root.
- **R6 (модели):** cross-module `ForeignKey` — только строкой (`"responsibility_services.id"`),
  `relationship()` — только внутри своего модуля; регистрация таблиц — через реестр
  моделей в `bootstrap.py` (явный импорт всех `adapters/orm`). Проверяется AST-тестом
  (расширение `tests/engine/test_architecture.py` на все модули).

## 4. Что НЕ менять

- Логику домена `engine/` — перенос «как есть», только re-export публичного API.
- ADR-0003 (PBKDF2), ADR-0004 (CSRF/CSP), ADR-0008 (SPA без сборки — **включая
  глобальные функции и `gen_js_globals`/`no-undef`**). ADR-0006 — заменяется ADR-0010.
- `can_manage_user` — остаётся ролевым стражем (§0 п.8).
- Тесты — переносятся за своим кодом, семантика проверок не меняется.
- `httpx2`/`httpcore2` в зависимостях (нужны starlette TestClient).
- API-пути и контракты ответов: `docs/openapi.json` после каждой фазы —
  `python tools/export_openapi.py --check` без дельты (теги роутеров не переименовываются
  до финальной фазы; если переименование понадобится — отдельным решением).

## 5. Сквозные конвенции

### 5.1 Время
Единственный источник TZ и «сейчас» — `core/time.py` (перенос `app/deps.py`).
Адаптеры и api не читают TZ из config напрямую. `now_utc()` остаётся в
`services/engine_common` → переезжает в `modules/timesheet/application` (composition-параметр
движка, F-15 — без ClockPort).

### 5.2 Права (фаза 2, до переносов)
Единственный вход — `require_perm(...)` из `core/permissions.py`. Перед удалением
`require_manager`/`require_supervisor` (**44 вызова** на main@b929007 после мержа
PR #50; на старте фазы перепроверить grep'ом) каталог дополняется ключами,
которых не хватает:

| Было | Становится |
|------|-----------|
| `require_supervisor` — закрытие/переоткрытие ночной смены (`night_api` ×3) | **новый ключ `night.close`** (базово: supervisor+) |
| `require_manager` — settings/docs/doublepay/notify | существующие `settings.edit` |
| `require_manager` — сотрудники | существующий `employees.edit` |
| `require_manager` — график/отметки | существующие `schedule.edit`, `punches.manage` |
| `require_manager` в `auth_routes` — impersonation и список сотрудников для него (×2) | **новый ключ `employees.impersonate`** (базово supervisor+); `can_manage_user` остаётся вторым стражем внутри обработчика |
| inline-ветвления `principal.is_manager` (14 шт.: `fact_api` ×4, `punches` ×5, `schedule` ×2, `cars_api` ×1, `photos` ×1) | в этой фазе переводится только ветвление с ключом 1:1 (`cars_api`: видимость неактивных каров → `cars.manage`); остальные — **явно откладываются** списком в фазы 4–6, где каждый модуль сам решает семантику «менеджерской видимости» (иначе фаза разрастается) |

Образец — `night.edit` (PR #50): базовые права ролей не меняются, управляемость появляется.

### 5.3 Ошибки
Иерархия `ServiceError → NotFound/Forbidden/Validation/Conflict/Gone/PayloadTooLarge`
уже существует (`app/services/errors.py`) и уже маппится шестью `@app.exception_handler`
в `main.py`. Перенос в `core/errors.py` — смена путей импорта, не новая механика.
Дополнительно: хэндлер `ConfigError` (домен движка) → 422 с `config_violation_text`
в `main.py`; после этого `domain_error_text()` и ручные `try/except ConfigError` в
7 api-файлах удаляются (фаза 4, вместе с переездом timesheet). Роутерам запрещается
ловить доменные ошибки для «красивого текста» — текст живёт в ошибке/formatting.

## 6. Фронтенд (фаза 8)

```
static/js/
  core.js            # утилиты, api, state, модалки (БЕЗ i18n — его нет)
  app.js             # оболочка, меню, роутинг
  modules/
    timesheet_layers.js   # = section_grid.js (без слияния файлов!)
    timesheet_v4.js       # = section_v4.js
    me.js                 # = section_me.js
    employees.js          # = section_employees.js
    night.js              # = section_night.js
    cars.js               # = section_cars.js
    docs.js               # = section_docs.js
    dicts.js              # = section_dicts.js
    settings.js           # = section_settings.js
```

- **Глобальные функции сохраняются** (ADR-0008): межфайловые вызовы — как сейчас,
  через глобальную область; `tools/gen_js_globals.py` сканирует `static/js/**`
  рекурсивно; ESLint `no-undef` остаётся страховкой от «пропавших» функций разделов.
  Отказ от глобалов в пользу `window.App.modules.*` ОТКЛОНЁН: property-доступ не
  проверяется `no-undef` статически (прецедент — регрессия loadNight/loadCars).
- Файлы НЕ сливаются: `timesheet.js` из трёх файлов на ~2700 строк не создаём —
  перенос 1:1, слияния (если захочется) — отдельным решением после стабилизации.
- Обязательные сопутствующие правки (в этой же фазе):
  `static/index.html` (пути и порядок `<script>`, порядок зависимостей сохраняется:
  cars → night → v4 → settings), `static/sw.js` + `tools/bump_version.py`
  (`local_assets()` → `rglob("*.js")`, SHELL пополняется файлами из `modules/`),
  `eslint.config.mjs` (пути), `tools/gen_js_globals.py` (пути),
  `tools/*.mjs` и `run_*.sh` (чтение скриптов из index.html — проверить),
  `docs/prototypes/*.smoke.mjs` не затрагиваются (автономны).
- Версия статики поднимается `python tools/bump_version.py <дата>a` — в этой же фазе.

## 7. Фазы (строго последовательно; после каждой — проверки §7.1 и отдельный коммит/PR)

**Фаза 0 — подготовка.** Мерж PR #50 — **выполнен** (main@b929007). Осталось:
push+мерж локальной ветки `feat/tabel-cell-code-chips` (на origin её нет — проверено;
упомянута в ревизии внешнего ревьюера) и заморозка веток, трогающих `app/api`, `static/js`.
Базовая фиксация: полный прогон §7.1 зелёный на main (ночной прогон pytest обязателен —
см. `open_shift`-герметичность из PR #50).

**Фаза 1 — чистка (нулевой риск).** §8 целиком: мёртвые зависимости, мёртвые обёртки
`doc_render`, переименование коллизии `validate_pattern`
(`base_schedule.validate_pattern` → `validate_pattern_label`,
`schedule_patterns.validate_pattern` → `validate_cycle_string`), перегенерация лока.

**Фаза 2 — права.** §5.2 целиком: новые ключи каталога, замена 52 вызовов
`require_manager`/`require_supervisor`, удаление обоих из `auth.py`; тесты на новые ключи
(образец — `tests/test_night_edit_perm.py`).

**Фаза 3 — `core/` + composition root.** Перенос по §2 (config, db, errors, security,
auth, auth_guards, permissions, time, observability, audit, media+Photo). Создание
`app/bootstrap.py`: реестр моделей (импорт всех `app.models.*` — пока единый пакет),
seed, migrations. `main.py` импортирует bootstrap. `.importlinter` — транзитные
контракты: `core` не импортирует `app.api/app.services/app.models` (R5 в зачатке);
слой `app.api → app.services → app.models` сохраняется до фаз 4–6.

**Фаза 4 — `modules/timesheet/`.** Перенос `app/engine/**` по слоям + роутеры
(`tabel_api`, `mgmt_api`, `fact_api`, `presence_api`, `punches`, `doublepay`, `schedule`,
`engine_settings_api`) в `interface/` + `tabel_fill`, `schedule_helpers`, `base_schedule`,
`schedule_patterns` (по смыслу: domain/application) + модели (`punch`, `schedule`,
`engine_store`, `directory`) в `adapters/orm.py` + `engine_bootstrap` → `bootstrap.py`.
В ЭТОЙ ЖЕ фазе: `tests/engine/test_architecture.py` — префиксы `app.engine` →
`app.modules.timesheet`; `.importlinter` — контракт изоляции движка на новых путях;
хэндлер `ConfigError` + удаление `domain_error_text` (§5.3).
`app/models/__init__` временно re-экспортирует переехавшие модели (транзит),
чтобы остальные модули не ломались.

**Фаза 5 — `modules/notify/` (эталон).** `app/notify/**` + `notify_api` + модель
`notify.py`. Проверка эталона: структура, R1–R6, публичные `__init__`.

**Фаза 6 — остальные модули, по одному коммиту на модуль:** `employees`
(`employees.py`, `employment.py`, `shiftrev.py`, `names.py`, `groups.py`,
`services/employee_lifecycle.py`), `night` (`night.py`, `night_export.py`, `night_api`,
`services/night_notify.py`, модели), `cars`, `docs` (`docs_api`, `doc_render`,
`pdf_render`, `grid_docx`, `doc_templates`), `settings` (`settings_api`),
`access` (`access_api`, `auth_routes` — login/logout/impersonation как interface
модуля access, модели `access.py`), `audit` (`audit_api`, модели).
После каждого: реестр моделей в bootstrap пополняется, транзитный re-export из
`app/models/__init__` уменьшается; в конце фазы пакет `app/models/` и `app/services/`
удаляются, `app/api/` исчезает.

**Фаза 7 — `main.py` финальный.** Composition root: include_router всех модулей,
полный набор exception_handler, middleware из `core/observability`. Удаление транзитных
контрактов `.importlinter`, финальные контракты R1–R6 (по модулям).

**Фаза 8 — фронтенд.** §6 целиком + смоуки всех сценариев (`run_ui_check` на трёх
ролях, settings/night_zones/night_cars/layers/norms-сценарии, `snapshot` — опционально).

**Фаза 9 — документация.** ARCHITECTURE.md (§3.5 клиент, §3 слои, онбординг-маршрут),
README (структура, quick start), SPEC.md (пути), ADR-0010 → «accepted», ADR-0006 →
«superseded by ADR-0010», `docs/openapi.json` — финальный переэкспорт, `docs/CHANGES-*`
по батчам.

### 7.1 Проверки после КАЖДОЙ фазы

```bash
.venv/bin/ruff check app tests
lint-imports                                  # контракты, обновлённые В ЭТОЙ фазе
.venv/bin/python -m pytest tests/ -q          # днём И ночью (open_shift-герметичность)
python tools/check_api_contract.py
python tools/export_openapi.py --check        # дельты нет
python tools/bump_version.py --check
npm run globals:check && npm run lint
./tools/run_ui_check.sh <порт> admin && ./tools/run_ui_check.sh <порт+1> ivanov
```
С фазы 4 добавляется `./tools/run_settings_scenario.sh`, с фазы 6 — `run_night_zones_scenario.sh`,
с фазы 8 — весь набор сценариев. Провал любого пункта — фаза не коммитится.

## 8. Чистка зависимостей и мёртвого кода (фаза 1)

| Действие | Файл | Подтверждение |
|----------|------|---------------|
| Удалить `pillow>=10.0` | `requirements-pdf.txt` | ни одного `import PIL` в app/tests/tools |
| Удалить `playwright>=1.44` | `requirements-dev.txt` | `tools/screens.py` не существует |
| Удалить установку `bcrypt passlib` | `run.sh` (~58–60) | `security.py` — только `hashlib.pbkdf2_hmac` |
| Удалить комментарий про bcrypt | `requirements.txt` (~15–16) | там же |
| Удалить `doc_render.docx_to_pdf`, `doc_render.pdf_mode` | `app/doc_render.py` | вызовы идут через `pdf_render`; `pdf_available`/`pdf_status` — оставить |
| Переименовать коллизию `validate_pattern` | `base_schedule.py`, `schedule_patterns.py` | две разные функции с одним именем |
| Перегенерировать лок | `requirements.lock.txt` | `pip install -r requirements{,-dev,-pdf}.txt && python tools/freeze_requirements.py` |

Не трогать: `httpx2`/`httpcore2` (starlette TestClient). PyYAML в репозитории не
объявлен — действий не требует.

## 9. Definition of Done (финальная приёмка)

- [ ] Структура §2: `core/` (12 файлов) + `bootstrap.py` + 9 модулей; `app/api`,
      `app/services`, `app/models`, `app/engine` — удалены.
- [ ] §7.1 зелёный целиком, включая ночной прогон pytest.
- [ ] `.importlinter`: финальные контракты R1–R6; транзитных нет.
- [ ] AST-тесты архитектуры покрывают все модули (не только timesheet).
- [ ] Ошибки маппятся только в `main.py`; `domain_error_text` удалена.
- [ ] Права — только `require_perm`; `require_manager`/`require_supervisor` удалены;
      `can_manage_user` не тронут.
- [ ] TZ/now — только `core/time.py`.
- [ ] Фронтенд: `static/js/modules/*.js`, глобалы + `no-undef` сохранены,
      SHELL `sw.js` включает новые пути (`bump_version.py --check` ✓), версия поднята.
- [ ] `docs/openapi.json` — без дельты к коду.
- [ ] Документы фазы 9 обновлены; ADR-0010 accepted, ADR-0006 superseded.
- [ ] Мёртвый код/зависимости §8 удалены; лок перегенерирован.

## 10. Риски и оценка

| Риск | Митигция |
|------|----------|
| Порядок регистрации моделей SQLAlchemy (create_all/selfcheck не видит таблицу) | Явный реестр в `bootstrap.py`; `/api/selfcheck` в §7.1 каждой фазы |
| Кэш service worker отдаёт старую оболочку | `bump_version.py` в фазе 8 + `--check` в каждой фазе |
| Поломка git-истории/blame | Только `git mv` + точечные правки импортов; логика не переписывается |
| Ночная flaky-зона тестов (open_shift) | Ночной прогон pytest в §7.1 (герметичность из PR #50) |
| Затягивание: перестройка «съедает» продуктовые батчи | Фазы 1–2 независимы и полезны сами; между фазами продуктовая работа не блокируется (кроме фаз 3–7, где `app/api` двигается — окно ~1–2 недели, заморозка фичевых веток) |

Оценка объёма: фазы 1–2 — ~0,5 дня; фазы 3–7 — 2–4 дня агентной работы с прогонами;
фаза 8 — ~0,5 дня; фаза 9 — ~0,5 дня. Итого 4–6 рабочих дней, ~15–25 коммитов.
Диффы — преимущественно renames; логика не меняется (кроме §5.2/§5.3 — они покрыты
тестами прав и сценариями).

---

## 11. Приложение (2026-10-20): слияние с ревизией внешнего ревьюера + новые находки

Внешний ревьюер выпустил свою редакцию (`1_EXECUTION-SPEC.md`, «v2»), принявшую
большинство замечаний §0 настоящего документа. Его упаковка в этапы **A** (чистка) /
**B** (права) / **C** (модули, только после ADR-0010) принимается как верхнеуровневая:
A = фаза 1, B = фаза 2, C = фазы 3–9. Ниже — дельта: подтверждённые факты и пробелы,
которые не закрыты НИ в v1, НИ в ревизии ревьюера. При расхождении приоритет у
более конкретного текста.

### 11.1 Утверждения ревизии ревьюера — проверены grep'ом, верны

* `pillow` мёртв: ноль вхождений `PIL`/`ImageReader` в app/tests/tools; PDF-экспорт
  текстовый (в `pdf_render.py` нет кода изображений).
* Обёртки `doc_render.pdf_mode`/`docx_to_pdf` мертвы, включая тесты:
  `test_readonly_pdf` мокает `app.pdf_render.docx_to_pdf` (настоящую);
  `pdf_available`/`pdf_status` живы (`docs_api`) — оставить.
* Список импортёров `validate_pattern` полон: `api/employees.py:16`,
  `services/employee_lifecycle.py:21` (→ `validate_pattern_label`),
  `api/schedule.py:51` (→ `validate_cycle_string`); тесты не ссылаются.
* `domain_error_text` — ровно 29 вызовов в api-роутерах; в центральный маппинг нужно
  направить не только `ConfigError`, но и `DomainError`/`ApplicationError` движка —
  с побайтовым сохранением статусов и текстов ответов (на них завязаны тесты и openapi).
* `PyYAML` — действий в репозитории не требует (никогда не объявлялся).

### 11.2 Новые пробелы (G1–G9)

**G1. Файлы без адреса в карте переноса** (§3.4 ревизии не покрывает):

| Файл | Куда |
|------|------|
| `api/photos_api.py` | роутер при `core/media` (`core/media_api.py`): бизнес-логики нет, только проверка владения |
| `api/auth_routes.py` | `modules/access/interface/` (login/logout/impersonation) |
| `services/punch_plan.py`, `services/engine_common.py` | `modules/timesheet/application/`; `punch_plan` импортирует `auth_routes` → access потребляет его через `timesheet.application` (R3-легально, зафиксировать) |
| `models/common.py` (роли, `MANAGER_ROLES`, `utcnow`) | `core/` — нужен auth/permissions/bootstrap |
| `base_schedule.py` | `modules/timesheet`; `employee_lifecycle` его уже импортирует → employees потребляет через `timesheet.application` (R3) |

**G2. Модуль `docs` — кросс-модульная инфраструктура рендеринга.** Проверено:
`pdf_render.docx_to_pdf` импортируют `night_api:1300` и `schedule:1283`; `grid_docx` —
`schedule:1238,1283`; `doc_render.hours_text` — `schedule:27`; `DOC_TYPES` — `migrations:322`.
Если оставить всё в `docs`, то timesheet/night зависят от `docs.application` (R3), но
timesheet переезжает РАНЬШЕ (фаза C2) — модуля docs ещё нет. Решение: чистый транспорт
рендера (`pdf_render` — конвейер LibreOffice/reportlab) → `core/render.py`; бизнес
документов (`doc_render` — виды заявлений, `grid_docx`, `doc_templates`) → модуль `docs`
с application-фасадом.

**G3. Транзитные импорты между фазами не легализованы.** В C2–C6 модули будут
импортировать ещё не перенесённый legacy (`app.models`, `app.grid_docx`, …). Нужен
явный транзитный контракт `.importlinter`: `modules.* → app.*` разрешён, пока
владеющий модуль не перенесён; `app.* → modules.*` запрещён (кроме bootstrap/main).
Без него `lint-imports` либо красный в середине фазы, либо контракты врут.

**G4. Реестр моделей не назначен.** `schema_report()` (самодиагностика `/api/selfcheck`)
считает `Base.metadata.sorted_tables`: если `adapters/orm` модуля не импортирован
в момент `create_all`, таблица молча выпадает. Нужен `bootstrap/registry.py` — явный
импорт всех ORM-моделей, вызывается из main до `init_db()`; в DoD — число таблиц
совпадает с дорефакторным.

**G5. В правилах ревизии (§3.3) нет R5 и R6** (см. §3 настоящего документа):
R5 «core не импортирует modules» подразумевается, но не законтрактован;
R6 «cross-module FK только строкой, `relationship()` внутри модуля, AST-контроль» —
отсутствует. Текущие кросс-модульные FK (night → responsibility_services, night → users)
уже строковые и без relationship — R6 фиксирует существующую практику как закон.

**G6. Чек-лист фазы (§3.6) неполон.** Добавить: `python tools/export_openapi.py --check`
(при переезде роутеров дрейфуют теги/operationId), `npm run globals:check` и
`npm run lint` (с фазы C6), смоук `run_ui_check` на трёх ролях + сценарии
(`run_settings_scenario`, `run_night_zones_scenario`, …) по затрагиваемому модулю,
и **ночной** прогон pytest как обязательный (герметичность `open_shift` из PR #50 —
ночная flaky-зона, из-за которой этот документ вообще появился).

**G7. Детали этапа B.** `require_manager` в `auth_routes` стережёт impersonation (×2) —
простое удаление оставит эндпоинты без гейта: нужен ключ `employees.impersonate`
(базово supervisor+), `can_manage_user` остаётся вторым стражем. Inline-ветвления
`principal.is_manager` (14 шт.) не покрываются лозунгом «удалить require_*» —
политика в §5.2. Счётчик вызовов: 44 (не 52/54) — перепроверить grep'ом на старте.

**G8. Precondition.** PR #50 смержен (b929007) — готово. Ветка `feat/tabel-cell-code-chips`
на origin отсутствует (проверено `git branch -r`) — она локальная у заказчика/ревьюера:
push+мерж до этапа A, иначе конфликты переноса.

**G9. `bootstrap/` пакетом** (seed.py + migrations.py) — принимается; туда же
`registry.py` (G4).

### 11.3 Итоговая рекомендация

Ревизия ревьюера пригодна как исполнительный документ ПОСЛЕ внесения G1–G9
(в настоящем файле они уже учтены в §2, §3, §5.2, §7). Этапы A и B не требуют ADR и
могут стартовать немедленно отдельными PR; этап C — после принятия ADR-0010
(`docs/adr/0010-modular-monolith-core-modules.md`) и закрытия G8.

---

## 12. Уточнения по итогам фазы C1 (20.10.2026)

Фактический состав `core/` и приёмы, применённые при переносе (дополнение к §2;
детали — `docs/CHANGES-2026-10-20-stage-c1-core.md`):

* `core/` = config, db, errors, security, time, format, roles, identity, auth,
  auth_guards, permissions, audit, media, observability. Добавлены сверх §2:
  **roles** (константы ролей из models/common), **identity** (User + AccessGroup/
  AccessGroupMember/AccessGrant — фундамент аутентификации и прав; управление ими
  останется в модуле access), **format** (safe_sheet_cell, normalize_hex_color —
  из deps.py), **auth_guards** (can_manage_user).
* `utcnow()` переехал из models/common в `core/time`; `slugify_username` — в
  `app/names.py` (домен имен, не время).
* `bootstrap/` — пакет: seed.py, migrations.py, **registry.py** (реестр моделей +
  инъекция провайдеров в core).
* **Инъекция вместо импорта (R5 в действии)**: `core/media.py` получает «прочие
  правила объекта» через `set_rules_provider(load_rules)` (регистрирует bootstrap),
  `core/auth.py` — загрузчик Employee через `set_employee_loader` (runtime-импорта
  моделей каталога в core нет; аннотация — TYPE_CHECKING, единственная строка
  ignore_imports в контракте core-independence).
* Модели User/AccessGroup(Member)/AccessGrant/AuditLog/Photo физически живут в
  core (identity/audit/media); фасад `app/models/__init__` ре-экспортирует их —
  существующие импорты `from ..models import X` не сломались.
* Контракты `.importlinter` (4): слои api→services→models→core; независимость
  api-модулей; изоляция движка (+bootstrap); **core-independence (R5)** — core не
  импортирует приложение.
* `core/media.BASE_DIR` — на один `.parent` глубже (файл переехал из app/ в
  app/core/): data/uploads остаётся в корне проекта.

---

## 13. Уточнения по итогам фазы C2 (20.10.2026)

Фактический состав `modules/timesheet/` и приёмы переноса (детали —
`docs/CHANGES-2026-10-20-stage-c2-timesheet.md`):

* Состав: `domain/ports/adapters/interface` — бывшие слои `app/engine` (перенос
  «как есть») + `application/` пополнен поглощёнными legacy-хелперами
  (engine_common, punch_plan, base_schedule, tabel_fill, schedule_helpers,
  schedule_patterns, doublepay) + `adapters/orm.py` (слияние
  models/{directory,punch,schedule,engine_store}) + `interface/` пополнен
  8 роутерами + `bootstrap.py` (бывший engine_bootstrap).
* `schedule_patterns` — в **application**, не domain: AST-закон 2.4 запрещает
  кириллицу в домене, а там кодовые наборы «р»/«в»/«вых» и тексты ValueError.
* **§5.3 исполнена с поправкой на §11.1 (приоритет конкретного):** центральный
  `ConfigError → 409` (не 422) — статус закреплён
  `test_10_config_error_is_409_not_500` для вкладок; 422 остался у редактора
  настроек (PUT /api/engine-settings) и записи Графика (shift/absence,
  CHK-* уровня 3) — три задокументированных локальных catch на `error_text`.
  `DomainError → 422`, `ApplicationError → 409`. `domain_error_text` удалена;
  тексты — `interface/formatting.error_text` (2.4). Суффиксы-подсказки
  «Исправьте в разделе «Настройки»…» поглощены единым текстом ConfigError
  (тестами/openapi/фронтом не закреплены).
* AST-закон application-слоя: транзит-allowlist из 6 legacy-файлов (свои
  adapters + app.groups/app.employment до C4); `app.core.*` разрешён всем
  (§3); файлы движка — по-прежнему полностью чистые.
* `.importlinter` — 6 контрактов: добавлены timesheet-isolation (правопреемник
  engine-isolation), timesheet-interface-independence и транзитный контракт G3
  (legacy `app.*` ✗ `modules.*`; 11 именованных исключений: фасад models,
  api/employees, api/settings_api, api/auth_routes, services/employee_lifecycle;
  сокращаются в C4–C6). `modules → app-legacy` (groups/employment/doc_render/
  grid_docx/pdf_render/models.night|notify) легализовано тем же G3 до переноса
  владельцев.
* **G2 отложен до C4:** `pdf_render → core/render.py` не выполнялся — транзит
  G3 покрывает зависимость timesheet от app-легаси без срочного переноса.
* **Employee — в `timesheet/adapters/orm.py`** (directory.py перенесён целиком,
  фаза 4 буквально). В C4 классы каталога переезжают в `employees/adapters/orm.py`;
  кросс-модульные `relationship()` таймшита на Employee (Punch.employee
  lazy=joined и др.) — предмет решения по R6 в C4 (строковые FK уже соответствуют).
* Реестр моделей (G4): `registry.ensure_models()` импортирует орм модуля явно;
  число таблиц `Base.metadata` — 45, сверено с main, без изменений.

---

## 14. Уточнения по итогам фазы C3 (20.10.2026)

Фактический состав `modules/notify/` (детали —
`docs/CHANGES-2026-10-20-stage-c3-notify.md`):

* Эталон подтверждён механически: `tests/test_notify_module.py` — 8 AST-проверок
  (слои, чистота domain/ports, направления §3, R6, публичный `__all__` =
  поверхность бывшей `app/notify`). В C7 файл — шаблон для всех модулей (DoD
  «AST-тесты покрывают все модули»).
* Единственный разделённый файл — `templates.py`: чистое (константы,
  `render_template`, `items_block`) → `domain/`, БД-чтение (`template_of`,
  `save_template`, `templates_payload`) → `application/`. Остальное — перенос
  файлов целиком, логика не переписывалась.
* `TransportError` — в `ports/transports.py` (контракт сбоя); транспорты
  (email/telegram) — `adapters/transports/` (единственные выходы в сеть);
  инъекция `bot=`/`mailer=` сохранена (тесты подменяют leaf-функции
  `http_sender`/`smtp_mailer` — пути monkeypatch обновлены).
* **`Setting` переехал в `core/settings_store.py`** (сверх §2, по прецеденту
  `Photo`/core-media): таблицу `settings` используют timesheet, notify, docs и
  будущий settings — владение одним модулем ломало бы R3 у потребителей.
  R5/R6 соблюдены (FK/relationship нет). Состав `engine_store` в timesheet
  уменьшился на Setting.
* `.importlinter` — 8 контрактов: **notify-isolation** (эталон не знает legacy
  и composition root) и **modules-independence** (timesheet ⊥ notify — R3
  механически; транзитные рёбра фасада `app.models` игнорируются до C6).
  Транзитный контракт G3: legacy-потребители доставки (`services/night_notify`,
  `api/night_api`, `night_export`) ходят только в `notify.application.*`.
* Долг (зафиксирован, не правится): application notify вызывает adapters
  (транспорты/orm) напрямую, interface импортирует `send_mail`/`TelegramBot`/orm
  — наследие плоского пакета; формальный ports-контракт отправителя и строгие
  слои — в C7 вместе с финальными контрактами R1–R6.

---

## 15. Уточнения по итогам фазы C4 (20.10.2026)

Все 9 модулей созданы, legacy-пакеты `app/api|services|models` удалены,
структура §2 достигнута (детали — `docs/CHANGES-2026-10-20-stage-c4-modules.md`):

* **Паттерн `application/catalog.py`** — публичная поверхность данных модуля
  (ре-экспорт ORM из adapters): единственная R3-легальная форма доступа к чужим
  моделям; есть у employees, timesheet, night, cars, notify.
* **Отступление: `shiftrev.py` — в timesheet/application**, не в employees
  (оперирует только ShiftType/ShiftRevision; устраняет межмодульное ребро).
* **R6 — осознанный долг**: кросс-модульные `relationship()` (Punch.employee
  lazy=joined, Employee.assigned_car, CarNightCheck.report и др.) сохранены —
  аннотации разрешаются реестром SQLAlchemy, импорты TYPE_CHECKING через
  catalog владельцев. Удаление = изменение бюджетов запросов и поведения
  (test_query_budget) — продуктовый батч «навигация → порты/DTO» после C7.
  Строковые FK соответствуют R6 уже сейчас.
* **G1/G2 закрыты**: photos_api → `core/media_api.py`; pdf_render →
  `core/render.py`; doc_render/grid_docx/doc_templates → `docs.application`.
* **Фаза 7 выполнена в составе C4**: транзитные контракты G3 сняты вместе с
  фасадом; `.importlinter` — 14 контрактов финальной формы (R5, изоляции,
  независимость роутеров ×2, R3-private ×9 с allow_indirect_imports).
* **§5.2 inline `principal.is_manager`** (11 ветвлений в fact_api/punches/
  schedule) перенесены «как есть» — перевод на права требует продуктового
  решения по каждому экрану (список — в CHANGES C4 §2); механически не делается.
* Реестр моделей (G4): `registry.ensure_models()` — явные импорты core-моделей
  и пяти `adapters.orm`; 45 таблиц идентичны дорефакторным.

---

## 16. Уточнения по итогам фазы C6 (20.10.2026)

Фронтенд перенесён в `static/js/modules/` точно по карте §6 (имена 1:1),
детали — `docs/CHANGES-2026-10-20-stage-c6-frontend.md`:

* Глобалы и реестр сохранены (ADR-0008): `gen_js_globals` переведён на `rglob`
  и относительные ключи (`modules/cars.js`), маппинг ESLint `static/js/${file}`
  совместим без правок; файлы НЕ сливались.
* `bump_version.local_assets()` — `rglob` + относительные пути (дефект v1 §0
  п.6 закрыт): SHELL `sw.js` включает все 9 файлов `modules/`; версия статики
  поднята в этой же фазе: **2026-10-20a**.
* `check_api_contract` — `rglob` (вызовы из modules/ сверяются с openapi).
* `ui_harness`/сценарии правок не потребовали (читают `<script src>` из
  index.html); `docs/prototypes/*.smoke.mjs` не затрагивались.
* Порядок подключений в index.html сохранён (cars → night → v4 → settings);
  смоуки на трёх ролях (admin/ivanov/gromova) и все пять сценариев зелёные.

---

## 17. Итоги исполнения и статус Definition of Done (§9) — фаза C7, 20.10.2026

Все фазы исполнены: A (PR #52), B (PR #54), C1 (PR #55), C2 (PR #56), C3 (PR #57),
C4+C5 (PR #58), C6 (PR #59), C7 (PR #60). Батчи — `docs/CHANGES-2026-10-20-stage-c*.md`;
уточнения фаз — приложения §12–§17. DoD:

- [x] **Структура §2**: `core/` (18 файлов — сверх §2 добавлены roles, identity,
      format, auth_guards (§12), settings_store (§14), render (§15/G2), media_api
      (§15/G1)) + `bootstrap/` (seed, migrations, registry) + **9 модулей**;
      `app/api`, `app/services`, `app/models`, `app/engine` — удалены (C4h).
- [x] **§7.1 зелёный целиком**, включая «ночной» прогон pytest (faketime 05:30 Мск:
      700 passed / 4 skipped) и сценарии (settings 76/76, night_zones 87/87,
      night_cars, layers, norms) и ui-смоуки на трёх ролях (C6).
- [x] **`.importlinter`: финальные контракты** — 14 (R5 core, изоляции timesheet/
      notify, независимость роутеров ×2, R3-private ×9); транзитных нет (сняты в C4h).
- [x] **AST-тесты покрывают все модули**: `tests/test_modules_architecture.py`
      (65 проверок: структура, R1, направления §3, R6 с точным allowlist,
      публичная граница notify) + `tests/engine/test_architecture.py` (законы движка).
- [x] **Ошибки маппятся в `main.py`** (ConfigError→409, DomainError→422,
      ApplicationError→409); `domain_error_text` удалена (C2). Три локальных
      catch → 422 сохранены как задокументированное разрешение конфликта §5.3/§11.1
      (статусы закреплены тестами — CHANGES C2 §2).
- [x] **Права — только `require_perm`**; `require_manager`/`require_supervisor`
      удалены (B); `can_manage_user` не тронут (core/auth_guards). Долг §5.2
      закрыт батчем 20.10.2026 (`docs/CHANGES-2026-10-20-debt1-scope-perms.md`):
      11 inline-ветвлений `principal.is_manager` переведены на 5 ключей каталога
      (fact.view_all; punches.view_all/punch_for_others/backfill;
      schedule.view_all + schedule.edit для readonly); аудитория базово прежняя
      (MANAGER_ROLES), управляемость — грантами; страж: в модулях нет чтений
      `is_manager` (тест).
- [x] **TZ/now — `core/time.py`** (долг закрыт батчем 20.10.2026,
      `docs/CHANGES-2026-10-20-debt3-local-date.md`): все `dt.date.today()` в
      timesheet/bootstrap/migrations переведены на `local_date()`; `now_utc()` —
      в `timesheet/application/engine_common` как composition-параметр движка
      (§5.1/F-15 — так и предписано спекой); AST-страж запрещает системное время
      в модулях; граничные тесты полуночи — `tests/test_tz_local_date.py`.
- [x] **Фронтенд**: `static/js/modules/*.js` (9 разделов 1:1), глобалы + `no-undef`
      сохранены (ADR-0008), SHELL `sw.js` включает новые пути (`rglob` в
      bump_version), версия поднята: **2026-10-20a**.
- [x] **`docs/openapi.json`** — без дельты к коду на всех фазах (156 путей).
- [x] **Документы фазы 9 обновлены** (C7): ARCHITECTURE.md (§1/2.2/2.3/3/3.5/6/7/8),
      README (структура, документация), SPEC.md (пути), ADR-0010 — «принят,
      исполнен полностью», ADR-0006 — superseded (C1).
- [x] **Мёртвый код/зависимости §8 удалены** (A); лок перегенерирован (A).
- [x] **R6**: кросс-модульные FK — только строками (AST-проверка всех ORM);
      кросс-границ `relationship()` — 11 связей в точном allowlist
      (`Punch.employee` lazy=joined и др.): задокументированный долг до
      продуктового батча «навигация → порты/DTO» (CHANGES C4 §2, ARCHITECTURE §7).
