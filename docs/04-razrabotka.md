# 4. Разработка и проверки

## 4.1 Окружение

* Python 3.15, менеджер зависимостей `uv` (`pyproject.toml` + `uv.lock`, с хешами пакетов).
* Node ≥ 22 — для ESLint, jsdom-сценариев и Playwright (jsdom 30+ тянет undici 7, который на
  Node 20 падает).
* Docker — для PostgreSQL.

```bash
docker compose up -d db          # PostgreSQL на 127.0.0.1:54329
uv sync                          # окружение из uv.lock, с dev-группой
source .venv/bin/activate
npm install                      # ESLint, jsdom, Playwright
npx playwright install chromium  # один раз
```

Запуск приложения без контейнера на базе из compose:

```bash
POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=54329 POSTGRES_USER=postgres POSTGRES_PASSWORD=dev \
POSTGRES_DB=postgres DEMO_SEED=1 \
python -m uvicorn app.main:app --port 8000
```

## 4.2 Тесты

```bash
python -m pytest tests/ -q                     # весь набор; параллельно (pytest-xdist), у каждого потока своя база
python -m pytest tests/engine -q               # движок: приёмочные примеры EX-01…EX-55, инварианты
python -m ruff check .                         # линтер Python
```

* Тестам нужен PostgreSQL по адресу `TEST_DATABASE_SERVER`
  (по умолчанию `postgresql+psycopg2://postgres:dev@127.0.0.1:54329`); у каждого потока своя схема.
* Каталоги `tests/<модуль>/` повторяют модули; сквозные тесты лежат в корне `tests/`.
* Бюджет SQL-запросов: тесты `*_budget*` фиксируют число запросов на эндпоинт. Каждый запрос API
  читает сессию из базы — это один запрос в бюджете.
* Архитектурные законы: `tests/test_modules_architecture.py`, `tests/engine/test_architecture.py`
  и `lint-imports` (`.importlinter`). Число прямых `commit`, `HTTPException` и эндпоинтов без модели
  ответа по модулям фиксирует `tests/test_transactions.py` — оно может только уменьшаться.
* Покрытие в CI: приложение ≥ 90 %, ядро расчёта ≥ 95 %.

## 4.3 Проверки интерфейса

| Команда | Что проверяет |
|---|---|
| `npm run lint` | ESLint: `no-undef`, неиспользуемое, запрет `innerHTML` / `insertAdjacentHTML` / `unsafeHTML` |
| `npx playwright test` | сценарии в настоящем браузере (`e2e/`); три сервера на свежих демо-базах (`tools/e2e_server.sh`): основной, «сценарии» (длинные пути с изменением данных: настройки, фонд, норматив Табеля и Графика, «График = 4 слоя» — `e2e/scenarios/`) и «ночной» (пояс подобран так, что идёт ночная смена: ночной обход, электрокары). Один проект: `--project=scenarios` |
| `./tools/run_ui_check.sh 8141 gromova` | смоук в jsdom: обход разделов под ролью (порт, логин) |
| `./tools/run_stays_scenario.sh 8148 admin` | шахматка: бронь, предпросмотр, батлеры, табло |
| `python tools/bump_version.py <версия> / --check` | версия статики в `index.html` и `sw.js` |
| `python tools/check_api_contract.py --verbose` | интерфейс не вызывает несуществующих маршрутов |

После любой правки JS или CSS перед коммитом нужно поднять версию (`bump_version.py 2026-11-19b`),
иначе CI падает на `--check`. Новый файл модуля добавляется в `static/index.html` и в список
оболочки `static/sw.js` — это делает тот же скрипт.

## 4.4 Контракты и документы

| Что | Как обновить | Проверка в CI |
|---|---|---|
| `docs/openapi.json` | `python tools/export_openapi.py` | `export_openapi.py --check` |
| лок-файл зависимостей | `uv lock` | `uv lock --check` |
| контракты import-linter | `python tools/gen_importlinter.py` | согласованность со списком модулей |
| ссылки в документах | — | `python tools/doc_links.py` (пути `app/…`, `docs/…`, относительные ссылки) |

Описания маршрутов в OpenAPI берутся из докстрингов: правка докстринга роутера меняет
`openapi.json`.

## 4.5 CI

`.github/workflows/ci.yml`, четыре задания: Python (ruff, mypy ядра расчёта, pytest с покрытием,
контракты, OpenAPI, самодиагностика схемы, `pip-audit`), JavaScript (синтаксис, `npm audit`,
ESLint, jsdom-смоук, Playwright, сценарии разделов), сборка Docker-образа, gitleaks.

## 4.6 Правила кода

* История решений не пишется в комментарии и докстринги: она в git и ADR. Комментарий объясняет
  «почему» текущего кода.
* Правило слоёв — [документ 2](02-arhitektura.md), раздел 2.4–2.5; роутер не коммитит и не бросает
  `HTTPException`, операция прикладного слоя владеет транзакцией.
* Новый эндпоинт: модель запроса, модель ответа (`ApiModel`), право через `require_perm`.
* Разметка интерфейса — только шаблонами lit-html ([документ 6](06-interfeys.md)).
* Решение с последствиями — отдельный ADR в `docs/adr/`.

## 4.7 Как добавить

**Модуль.** Каталог `app/modules/<имя>/` со слоями и `manifest.py` (слой, меню, права, задачи);
`bootstrap/modules.py` находит манифест сам, правок в `main.py` и каталогах прав не нужно;
пересоберите контракты (`tools/gen_importlinter.py`).

**Экран интерфейса.** Файл `static/js/modules/<имя>.js` с `registerModule({ views: … })` или
`registerModule({ screens: … })` (экраны Настроек); подключение — `bump_version.py`; пункт меню и
право — в манифесте модуля на сервере.

**Фоновая задача.** `JobSpec` в манифесте модуля; обработчик — функция `(db, payload)`.
