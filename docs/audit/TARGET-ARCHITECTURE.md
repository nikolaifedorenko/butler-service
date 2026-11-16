# Целевая архитектура под расширение (этап 3)

Это эволюция, а не переписывание. Сохраняются движок v7.1, модульный монолит (ADR-0010),
фронтенд без сборки (ADR-0008), собственный токен (ADR-0007), CSRF и CSP (ADR-0004),
имперсонация по умолчанию (решение владельца). Пересматриваются ADR-0002 (Alembic — пора) и
ADR-0005 (лимит входа — в БД). У каждого предложения указаны ID находок, которые оно закрывает.

## 1. Модуль, который регистрирует себя сам

### 1.1. Сколько мест правится сейчас
Чтобы добавить поддомен сегодня, нужно вручную править (проверено по коду):

| # | Файл | Что добавить |
|---|---|---|
| 1 | `app/main.py:31-58,233-250` | импорт роутеров и `include_router` |
| 2 | `app/main.py:78-113` | вызов своих `migrate_*` в `_init_db_steps` |
| 3 | `app/bootstrap/registry.py:14-26` | импорт `adapters.orm` (иначе таблица молча не создастся) |
| 4 | `app/bootstrap/migrations.py` | `ADD COLUMN` для новых колонок и data-миграции |
| 5 | `app/bootstrap/seed.py` | демо-данные |
| 6 | `app/core/permissions.py:22-80` | ключи в `PERMISSIONS`, наборы `_EMPLOYEE`/`_SUPERVISOR`, `ROLE_DEFAULTS` |
| 7 | `app/modules/audit/interface/audit_api.py:23` | `ACTION_TITLES` для действий модуля |
| 8 | `app/modules/notify/domain/templates.py:14-30` | `DOMAIN_TITLES`, `DEFAULT_TEMPLATES`, `PLACEHOLDERS`, если модуль шлёт сообщения |
| 9 | `.importlinter` | контракт R3 модуля и строки в общих контрактах (`:55,88,106,124`) |
| 10 | `tests/test_modules_architecture.py:21` | кортеж `MODULES` |
| 11 | `static/index.html:132-152` | тег `<script>` |
| 12 | `static/sw.js:5-22` | строка в `SHELL` (версию правит `tools/bump_version.py`) |
| 13 | `tools/js_globals.json` | перегенерация `gen_js_globals.py` |
| 14 | `static/js/app.js:46-61` | пункт меню в `visibleTabs()` и ветка навигации |
| 15 | `static/js/modules/settings.js:55-76` | экран в `SETTINGS_SCREENS` |
| 16 | `docs/openapi.json` | перегенерация `tools/export_openapi.py` |

### 1.2. Манифест модуля
Каждый модуль объявляет о себе в одном файле `app/modules/<name>/manifest.py`:

```python
MODULE = ModuleManifest(
    name="guests", title="Гости и сопровождение",
    routers=["app.modules.guests.interface.guests_api:router"],
    models="app.modules.guests.adapters.orm",
    permissions=[Perm("guests.view", "Гости", "Просмотр гостей"),
                 Perm("guests.edit", "Гости", "Карточки и проживания"),
                 Perm("guests.assign", "Гости", "Назначение батлеров")],
    role_defaults={"supervisor": {"guests.view", "guests.edit", "guests.assign"},
                   "employee": {"guests.view"}},
    audit_actions={"guest_stay_create": "Гости: заезд", "guest_assign": "Гости: назначение"},
    notify_domains={"guests": NotifyDomain(title="Гости — запросы", template="…", placeholders=…)},
    menu=[MenuItem(id="guests", title="Гости", perm="guests.view", order=55)],
    settings_screens=[Screen(id="guests", title="Гости", group="Объект", perm="guests.view")],
    static=["js/modules/guests.js"],
    alembic_versions="app/modules/guests/migrations",
    seed="app.modules.guests.bootstrap:seed_demo",
    jobs=[],          # фоновые задачи: Job(name, period_s, fn) — исполняет общий планировщик под try_lock
)
```

`app/bootstrap/modules.py` находит манифесты (`pkgutil.iter_modules(app.modules)` + атрибут
`MODULE`; выключение через env `DISABLED_MODULES`) и из них:
- регистрирует роутеры и модели (пункты 1 и 3 исчезают);
- собирает каталог прав и базовые права ролей (пункт 6), заголовки аудита (7) и домены
  уведомлений (8);
- отдаёт фронту `GET /api/app/manifest` для вошедшего: пункты меню и экраны настроек, которые
  он имеет право видеть, и список скриптов с версией.

**Фронтенд без сборщика (ADR-0008 сохраняется).** `core.js` по манифесту подгружает скрипты
модулей динамическим `<script src="…?v=…">` (без бандлера и без ES-модулей). Каждый файл модуля
вызывает `registerModule({id, render, screens: {guests: renderGuestsScreen}})`. Меню
(`app.js`) и реестр настроек (`settings.js`) строятся из `GET /api/app/manifest` плюс
`registerModule`, а не из захардкоженных массивов (пункты 11, 14, 15). Бонус — сотрудник не
скачивает экраны, на которые у него нет прав (PERF-03).

**Генерируемые артефакты.** `tools/bump_version.py` строит `SHELL` в `sw.js` из манифестов
(12); `tools/gen_importlinter.py --check` строит секции контрактов R3 из списка модулей (9);
`tests/test_modules_architecture.py` читает список модулей из манифестов (10). CI проверяет
актуальность так же, как сейчас `gen_js_globals --check` (13, 16).

Итог: новый модуль — это новые файлы в `app/modules/<name>/`, `static/js/modules/<name>.js` и
`tests/modules/<name>/`, без правки существующих файлов.
Закрывает: ARCH-02 (частично), PERF-03, DOC-01/02 (генерация вместо ручных списков).
Стоимость: M–L (3–5 дней), поэтапно: сначала бэкенд-манифест, затем фронт.

## 2. Права: одна модель
1. **Только `require_perm` и проверка объекта.** Никаких `principal.role` и `is_manager` в
   модулях и никаких проверок роли во фронте. Страж — AST-тест: `principal.role`, `is_manager`
   и `is_admin` запрещены вне `core/auth_guards.py`, а `role ===` — в `static/js` (кроме
   формы выбора роли). Закрывает AUTHZ-05, UI-02, DOC-03.
2. **Права объявляет модуль** (манифест, §1.2); `core/permissions.py` хранит только механику.
3. **Роли как данные.** Таблицы `roles(code, title, rank, max_assignable_rank, builtin)` и
   `role_permissions(role_code, permission, effect)`. `ROLE_DEFAULTS` из манифестов становится
   сидом встроенных ролей. `can_manage_user` превращается в правило «можно назначать и править
   роли с `rank ≤ max_assignable_rank`» (admin 100/100, manager 80/80, supervisor 60/10,
   employee 10/−1): поведение совпадает с нынешним `auth_guards.py:33-53`. Новая роль
   («Ночной супервайзер», «Бухгалтерия») заводится в UI без правки кода.
4. **Объектный уровень.** Шаблон, который уже есть в коде (`punches.view_all`, `fact.view_all`,
   `schedule.view_all`), закрепить общим правилом: `<раздел>.view` даёт «своё», а
   `<раздел>.view_all` — «всё». Политика объекта живёт в модуле:
   `policy.can_view(principal, obj)`. Закрывает AUTHZ-06, AUTHZ-07, AUTHZ-09.
5. **Кэш прав на запрос.** Одна зависимость `perms = Depends(request_permissions)`: FastAPI
   кэширует её в пределах запроса. `require_perm` и `has_perm` читают её, а не считают заново
   (сейчас 1–2 расчёта по 3–4 SQL, 16.2).
6. **Единый источник для UI.** `/api/auth/me.permissions` уже есть, `can()` во фронте тоже.
   Остаётся убрать 8 ролевых проверок (UI-02).
7. **Миграция без потери настроек заказчика.**
   (а) снимок `effective_permissions` всех пользователей до миграции (скрипт);
   (б) новые ключи вместо ролевых проверок AUTHZ-05 получают ту же аудиторию в `ROLE_DEFAULTS`;
   (в) `AccessGrant(role=…)` переносятся в `role_permissions`, групповые и индивидуальные гранты
   не трогаются;
   (г) снимок после миграции обязан совпасть с (а) с поправкой только на новые ключи. Это
   проверяет тест миграции.
   Стоимость: M (2–3 дня). ADR: новый ADR-0011 «Роли и права как данные».

## 3. Миграции: Alembic (пересмотр ADR-0002)
Почему сейчас: DB-01 и DB-02 показали, что самодельные идемпотентные шаги не проверяются ни на
PostgreSQL, ни на старых схемах; таблицы версий нет, «что уже применено» угадывается по наличию
колонок. Стоимость пересмотра — M (2–3 дня) плюс CI на PostgreSQL.
1. **Baseline.** `alembic revision --autogenerate` на пустой базе = ревизия `0001_baseline`,
   равная текущему `Base.metadata`. Для SQLite включить `render_as_batch=True`.
2. **Существующие базы.** Один раз выполнить нынешний `init_db` текущего кода (с исправленными
   DB-01 и DB-02), затем `alembic stamp 0001_baseline`. Старые `migrate_*` переезжают в модуль
   `legacy_bootstrap` и вызываются только при отсутствии `alembic_version`.
3. **Data-миграции** — обычные ревизии; у модулей свои `version_locations` (манифест §1.2).
4. **Отдельный шаг деплоя.** Сервис `migrate` в compose
   (`command: python -m app.bootstrap.migrate`; `app` — `depends_on: migrate:
   service_completed_successfully`). Воркеры DDL не выполняют, а при `current != head`
   останавливаются с понятной ошибкой. `startup_lock` остаётся страховкой для ручного запуска.
5. **Проверка.** CI: `alembic upgrade head` на SQLite и `postgres:16`; `alembic check`
   (autogenerate без изменений); тест обновления с дампа прошлого релиза.
Закрывает: DB-01, DB-02, DB-03, DB-05, ARCH-03 (частично).

## 4. Старт и фоновые задачи
- `python -m app.bootstrap.migrate`: миграции, `bootstrap_engine`, сид **только** при
  `DEMO_SEED=1`, создание первого администратора из env (`ADMIN_USERNAME`, `ADMIN_PASSWORD`) с
  обязательной сменой пароля. Закрывает SEC-02.
- В `lifespan` остаются проверка ключа, проверка версии схемы и запуск планировщика.
- Планировщик — обобщение `bootstrap/night_sync.py`: список `Job` из манифестов, каждый раунд
  под `try_lock(job.name)`. Задачи: синхронизация ночных отчётов, очистка медиа раз в сутки
  (BUG-01), отправщик outbox уведомлений (CONC-02).

## 5. Транзакции и ошибки
- Зависимость `uow` открывает сессию и коммитит в конце запроса, если не было исключения.
  Сервисы не вызывают `commit`, аудит пишется той же сессией (а значит в той же транзакции).
  Закрывает ARCH-01.
- Массовые операции (закрытие периода на N сотрудников) — явный цикл UoW внутри одного
  сервиса, аудит на сотрудника внутри его транзакции.
- Сервисы бросают `core/errors.*`; правила вроде `_guard_bank`, `_guard_open`, `doublepay._guard`
  переезжают в сервисы и политики модуля.
- Страж: grep-тест «`db.commit()` только в `core/uow.py`, `bootstrap/`, `timesheet/adapters/sql_uow.py`».

## 6. Состояние между воркерами
| Что | Сейчас | Куда | Цена |
|---|---|---|---|
| Лимит входа | dict в памяти воркера | таблица `login_attempts(key, ts)`, ключи `ip:` и `user:`, чистка задачей; плюс SEC-01 в nginx | S, +1 INSERT на неудачный вход |
| Замок отметок | `threading.Lock` + `FOR UPDATE` | только `FOR UPDATE` (lock процесса лишний) | S |
| Операции с каром | без блокировки | условный `UPDATE … WHERE status IN (…)` + частичный unique (CONC-01) | S |
| Рассылка | сеть внутри запроса | outbox `notify_dispatches(status)` + задача-отправщик (CONC-02) | M |
| Троттлинг синхронизации | `_last_sync` | удалить: планировщик + `try_lock` | S |
| Версии настроек | без контроля | `base_version_id` → 409 (CONC-03) | S |

**Когда понадобится Redis:** больше одного хоста приложения и нагрузка выше ~50 запросов в
секунду, или живые обновления доски вместо поллинга раз в 30 с (pub/sub). При нагрузке одного
объекта PostgreSQL справляется со всем перечисленным.

## 7. Тесты как часть модуля
1. **Матрица «роль × маршрут» из манифестов.** Обобщение `docs/audit/scripts/authz_matrix.py`:
   для каждой встроенной роли и каждого маршрута модуля ожидаемый 403 или «не 403» выводится из
   `role_defaults` и `require_perm`; плюс прогон с индивидуальными deny и allow. Тест падает,
   если в теле обработчика осталась ролевая проверка (EXP-ROLEGRANT превращается в регрессионный
   тест). Закрывает ARCH-03, AUTHZ-05.
2. **CI на PostgreSQL** — матрица `db: [sqlite, postgres16]` (DB-04).
3. **Тест обновления схемы** с дампа прошлого релиза (DB-01).
4. **Контракт API ↔ JS.** Нынешний `check_api_contract.py` сверяет пути; добавить
   `response_model` для ответов модулей и проверку полей, которые читает JS (первые кандидаты —
   экраны настроек и ночного отчёта).
5. **Бюджет запросов** на каждый экран модуля (`tests/modules/<name>/test_query_budget.py`,
   PERF-01, PERF-02).
6. Шаблон `tests/modules/<name>/` создаётся генератором модуля (`tools/new_module.py`) вместе с
   каркасом пакетов.

## 8. Проверка на живом примере: модуль «Гости и сопровождение»
**Допущения** (файла `docs/PROPOSAL-GUEST-SERVICE-2026-10-20.md` в репозитории нет, пример
построен по названию): гость (карточка, VIP-признак, предпочтения); проживание (заезд и выезд,
вилла или номер); назначение батлера на проживание на даты; запросы гостя (что, когда, статус).
Батлер видит только своих гостей. Супервайзер назначает. Назначать можно только того, кто по
Табелю и Графику на смене.

**Шаги в целевой структуре:**
1. `python tools/new_module.py guests` создаёт каркас: `app/modules/guests/{domain,application,
   ports,adapters,interface}/`, `manifest.py`, `migrations/`, `tests/modules/guests/`,
   `static/js/modules/guests.js`.
2. **Модели** `adapters/orm.py`: `Guest`, `Stay(guest_id, unit, arrive_at, depart_at)`,
   `Assignment(stay_id, employee_id, date_from, date_to)` и unique
   `(stay_id, employee_id, date_from)`. Ревизия Alembic `guests_0001` в
   `app/modules/guests/migrations/`.
3. **Права** в манифесте: `guests.view` (своё), `guests.view_all`, `guests.edit`,
   `guests.assign`. Базовые права: employee — `guests.view`; supervisor и выше — все. В
   «Правах доступа» ключи появляются сами, роли получают их через `role_permissions`.
4. **Чтение Табеля через сервисный слой.** Модуль `timesheet` публикует запрос
   `app/modules/timesheet/application/public.py: on_shift(db, day) -> list[OnShift(employee_id,
   start_utc, end_utc)]` (сегодня такие данные собирает `presence_board`). `guests` импортирует
   только `app.modules.timesheet.application.public`, контракт import-linter разрешает модулям
   именно этот путь. Ни `tabel_days`, ни `schedule_shifts` модуль `guests` не читает.
5. **Сервис** `application/assign.py`: `assign(uow, principal, stay_id, employee_id, dates)` →
   проверка `guests.assign` → `timesheet.public.on_shift` на каждую дату → запись → аудит
   `guest_assign` в той же транзакции.
6. **Экран настроек** «Гости» (типы запросов, VIP-правила) объявлен в манифесте;
   `static/js/modules/guests.js` вызывает `registerModule({id: 'guests', render: renderGuests,
   screens: {guests: renderGuestsSettings}})`.
7. **Уведомления.** Домен `guests` с шаблоном в манифесте: запрос гостя отправляется
   назначенному батлеру в Telegram через outbox.
8. **Тесты.** Матрица прав генерируется сама; плюс `test_assign_requires_on_shift`, бюджет
   запросов списка гостей.

**Какие существующие файлы не правятся:** `app/main.py`, `app/bootstrap/registry.py`,
`app/core/permissions.py`, `audit_api.py`, `notify/domain/templates.py`, `.importlinter`
(генерируется), `tests/test_modules_architecture.py`, `static/index.html`, `static/sw.js`
(генерируется), `static/js/app.js`, `static/js/modules/settings.js`. Правится только
`app/modules/timesheet/application/public.py` — новый публичный запрос, который пригодится и
другим модулям.
