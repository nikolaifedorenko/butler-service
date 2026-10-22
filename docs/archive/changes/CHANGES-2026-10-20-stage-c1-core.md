# Изменения 20.10.2026 — этап C, фаза C1: `core/` + composition root

Исполнение `docs/archive/EXECUTION-SPEC-v2.md` (фаза 3; ADR-0010 принят владельцем —
PR #51 смержен). Первый шаг модульного рефакторинга: инфраструктурное ядро
выделено в `app/core/`, composition root — в `app/bootstrap/` + `app/main.py`.
Поведение приложения и контракты API не изменились (openapi — без дельты).

## 1. Что переехало

| Новый путь | Из чего |
|------------|---------|
| `app/core/config.py` | `app/config.py` |
| `app/core/db.py` | `app/db.py` (engine, SessionLocal, Base, get_db) |
| `app/core/errors.py` | `app/services/errors.py` (иерархия ServiceError) |
| `app/core/security.py` | `app/security.py` |
| `app/core/time.py` | `app/deps.py` (TZ, now_local, local_date, utc_to_local, month_name, WD_SHORT, weekday_short) + `utcnow()` из `models/common.py` |
| `app/core/format.py` | из `app/deps.py`: `safe_sheet_cell`, `normalize_hex_color` |
| `app/core/roles.py` | из `models/common.py`: ROLE_*, MANAGER_ROLES |
| `app/core/identity.py` | `User` (из `models/directory.py`) + `AccessGroup`/`AccessGroupMember`/`AccessGrant` (из `models/access.py`) |
| `app/core/auth.py` | `app/auth.py` (Principal, current_principal, optional_principal) |
| `app/core/auth_guards.py` | `can_manage_user` (из `app/auth.py`) |
| `app/core/audit.py` | `audit()` (из `app/auth.py`) + модель `AuditLog` (из `models/audit.py`) |
| `app/core/permissions.py` | `app/permissions.py` |
| `app/core/media.py` | `app/photos.py` + модель `Photo` (из `models/media.py`) |
| `app/core/observability.py` | middleware из `app/main.py`: CSRF, заголовки безопасности/CSP, request-id/лог/метрики + `/metrics` (подключение — `observability.register(app)`, порядок сохранён) |
| `app/bootstrap/seed.py` | `app/seed.py` |
| `app/bootstrap/migrations.py` | `app/migrations.py` |
| `app/bootstrap/registry.py` | новое: реестр моделей + инъекция провайдеров в core |
| `app/names.py` | += `slugify_username`, `TRANSLIT` (из `app/deps.py` — домен имён, не времени) |

Удалены: `app/models/common.py`, `app/models/access.py`, `app/models/audit.py`,
`app/models/media.py` (содержимое — в core). Фасад `app/models/__init__.py`
ре-экспортирует переехавшие символы: существующие импорты `from ..models import X`
не сломались, все модели по-прежнему регистрируются в `Base.metadata` до `create_all`.

## 2. Ключевые решения (R5 — core не импортирует приложение)

* **Инъекция вместо импорта.** `core/media.py` читает лимиты медиа из «прочих
  правил объекта» через провайдера: `set_rules_provider(schedule_helpers.load_rules)`
  регистрирует `bootstrap/registry.wire()`. Аналогично `core/auth.py` — загрузчик
  сотрудника (`set_employee_loader`) вместо `db.get(Employee, …)`; аннотация
  `Principal.employee` — TYPE_CHECKING. Без провайдера действуют дефолты — core
  работоспособен в изоляции.
* **`wire()` вызывается дважды**: при импорте `main` (до первого запроса) и в
  `init_db()` (тесты/скрипты). Идемпотентно.
* **Identity-модели в core**: User и гранты — фундамент аутентификации/прав, их
  используют core.auth и core.permissions; управление грантами (интерфейс «Права
  доступа») останется в модуле `access` (фаза C4) и будет импортировать модели из
  core — направление «модуль → core» разрешено.
* **`core/media.BASE_DIR`** — на один `.parent` глубже (файл переехал из `app/`
  в `app/core/`): `data/uploads` остаётся в корне проекта, загруженные файлы не теряются.
* **Связь `User.employee`** объявлена строкой и разрешается реестром SQLAlchemy:
  Employee остаётся в моделях каталога (будущий модуль employees), core его не импортирует.

## 3. Контракты импортов (.importlinter — 4 штуки, все зелёные)

1. Слои: `api → services → models → core` (core добавлен нижним слоем).
2. Независимость api-модулей (без изменений).
3. Изоляция движка v7.1: `app.engine` не знает про api/services/main/**bootstrap**.
4. **core-independence (R5)**: core не импортирует api, services, models, engine,
   notify, bootstrap, main и корневые модули приложения. Единственное исключение —
   `app.core.auth -> app.models` (TYPE_CHECKING-аннотация; в runtime — инъекция).

## 4. Тесты и проверки

* `tests/test_permissions_unification.py` — проверка отсутствия ролевых зависимостей
  переведена на `app.core.auth` + контроль, что `app/auth.py` больше не существует.
* Прочие тесты — механическая замена путей импортов (`app.photos` → `app.core.media` и т.п.);
  семантика проверок не менялась. AST-законы движка (`tests/engine/test_architecture.py`)
  не затрагивались: engine по-прежнему изолирован.
* Прогоны: pytest **637 passed / 0 failed / 2 skipped**; ruff ✓; lint-imports **4/4**;
  `check_api_contract` ✓; `export_openapi --check` — **без дельты** (156 путей);
  `bump_version --check` ✓; `gen_js_globals --check` ✓ (фронтенд не менялся);
  сценарий настроек **76/76**; ui-смоук (admin) — 0 пустых разделов, 0 ошибок консоли.

## 5. Дальше по плану (EXECUTION-SPEC-v2 §7)

* C2 — `modules/timesheet/` (engine + 8 роутеров + табельные хелперы + модели
  punch/schedule/engine_store/directory): в той же фазе — префиксы AST-тестов,
  контракт изоляции движка на новых путях, хэндлер `ConfigError` и удаление
  `domain_error_text`.
* C3 — `modules/notify/` (эталон), C4 — остальные модули, C5 — main.py финальный,
  C6 — фронтенд (`static/js/modules/` + `rglob` в bump_version), C7 — документация.
