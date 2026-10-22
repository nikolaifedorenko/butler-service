# История изменений

Свежие записи сверху. Новая запись — на каждый батч: дата, тема, PR, что изменилось и как
проверено. Подробные описания батчей до 22.10.2026 — в [`docs/archive/changes/`](docs/archive/changes/).
Решения с обоснованием — в [`docs/adr/`](docs/adr/).

PR — https://github.com/nikolaifedorenko/butler-service/pull/<номер>.

## 22.10.2026

### После внешнего ревью: PDF без LibreOffice, журнал отметок, чистка
* **PDF — один путь, встроенный рендер.** Путь LibreOffice удалён (`core/render.py`, лимит
  `LO_SLOTS`, подсказки в `run.sh`/`setup_macos.sh`, тест с поддельным soffice). Встроенный
  рендер научился картинкам из абзацев и ячеек таблиц (размер из документа, не шире колонки):
  раньше в Docker-образе, где LibreOffice не было, PDF ночного отчёта выходил без фото.
  `reportlab` и `pillow` — обязательные зависимости (`requirements-pdf.txt` удалён).
* **Журнал отметок для менеджера** («Отметки» → под доской, `punches_journal.js`): все отметки
  месяца с фильтром по сотруднику, отметка за сотрудника — сейчас или задним числом (забытый
  уход), отмена с подтверждением. Бэкенд, права и аудит были готовы — не было кнопок.
  Проверено вживую: отметка задним числом и её отмена.
* **«Мои отметки» у учётки без сотрудника** (администратор) больше не показывают отметки всех
  сотрудников как свои.
* **Чистка.** Удалены legacy-шаги миграций (`bootstrap/migrations.py`, ветка в `init_db`, штамп
  baseline и 11 их тестов): база без Alembic теперь не стартует, а объясняет, что делать
  (`test_base_before_alembic_refuses_to_start`). `seed_statement_kinds` — в `bootstrap/seed.py`.
  Удалены мёртвые `POST /api/employees/{id}/deactivate`, `GET /api/mgmt/periods`,
  `view_schedule()`, `ShiftView.is_archived`, шаблон `PREV_DEFAULT_TPL_TIME_OFF`.
* **Документы и конфиги.** `cd butler-service` вместо `cd timetrack`, пути `app.modules.timesheet…`
  в GUIDE, без ручных цифр в INSTALL и ARCHITECTURE, ADR-0002 о удалении legacy-пути.
  `doc_links` проверяет и точечные пути модулей (`app.engine.…`). ESLint — `--max-warnings=0`
  (два мёртвых имени удалены), `.gitignore` — `*.lock`, мёртвая строка ruff-конфига удалена.

### Фаза 6 аудита, шаги 6.5–6.6: разрез больших файлов, PDF и вложения рассылки
* **6.5 (ARCH-02).** `night/interface/night_api.py` (1344 строки) разложен по задачам:
  `night_dicts_api` (справочники), `night_shift_api` (ход смены), `night_dispatch_api`
  (недостатки и отправка службам), `night_report_api` (кары, закрытие, выгрузка), общая часть —
  `night_common`; `night_api.py` подключает их в прежнем порядке. Маршруты и OpenAPI совпали
  со снимком «до» один в один. `static/js/modules/settings.js` (2413 строк) — по файлу на экран:
  `settings_<экран>.js` регистрирует свой экран через `registerModule`, в `settings.js` осталась
  оболочка (687 строк). Загрузка проверена в прямом и обратном порядке файлов.
* **6.6 (PERF-04).** Не больше двух LibreOffice на процесс (`core/render.LO_SLOTS`): занят
  дольше 30 с — PDF собирает встроенный рендер, а не новый процесс; у каждого запуска свой
  профиль (два soffice с общим профилем не работают параллельно). В Docker-образе LibreOffice
  нет — это для установки без Docker (`deploy/README.md` §7). Вложения рассылки — пути к файлам:
  Telegram получает файл потоком с диска, письмо читает его только при сборке (раньше все
  вложения, до 10 видео по 50 МБ, читались в память заранее).
* Проверки: стражи `sync_reports` и потоковой загрузки читают весь пакет `night/interface`;
  новый `test_render_limits.py` (поддельный soffice). pytest 892 passed на SQLite и PostgreSQL 16;
  смоук под тремя ролями и пять UI-сценариев — 0 провалов.

### Фаза 6 аудита, шаги 6.3–6.4: тесты рискованного, пакетная загрузка Табеля и Факта
* **6.3 (ARCH-03).** Новые тесты: двойная оплата (`test_doublepay.py`: календарь и ВИП-период →
  модификатор «Двойные переработки» по группам графиков, все отказы API), замки и фоновый поток
  (`test_background_locks.py`: «соседний воркер» держит замок через отдельное соединение
  PostgreSQL или отдельный дескриптор файла, поэтому ветки PostgreSQL проверяет CI-джоб
  postgres), отказ «неизвестная роль». Покрытие по SQLite и PostgreSQL вместе:
  `startup_lock` — 100 %, двойная оплата — 99–100 %, фоновый поток — 97 %, `auth_guards` — 100 %.
  Удалён мёртвый код `application/doublepay.py` (`reason_for`, `DoubleContext`,
  `scope_applies`, `employee_list_kind`): расчёт идёт через `adapters/sql_settings.py`.
* **6.4 (PERF-02).** Табель и Факт за месяц больше не делают запросы на каждого сотрудника:
  блокировка периода — `lock_marks`/`lock_states` одним запросом (Табель, заполнение из
  циклов и Графика, сброс месяца), отметки и периоды занятости — `prefetch` адаптеров.
  На демо-данных: Табель 96 → 31 SQL, Факт 64 → 23; при +60 сотрудниках — 456 → 31 и
  304 → 23. Ответы совпадают с точечными (`test_batch_loading.py`). Бюджеты запросов в
  `test_query_budget.py` — для Табеля, Факта, каров, настроек, аудита; рост штата проверяется
  на Графике, Табеле и Факте с допуском 3 запроса (ловит даже один запрос на сотрудника).
  УТ (`/api/mgmt`, 14 SQL на сотрудника) не менялся: конвейер считает каждого отдельно.
* Проверки: pytest 891 passed на SQLite и PostgreSQL 16; смоук под тремя ролями и пять
  UI-сценариев — 0 провалов; мутации (Табель и Факт без пакетной загрузки) ловятся бюджетами.

### Фаза 6 аудита, шаги 6.1–6.2: документация — один источник на тему
* **6.1 (DOC-01, DOC-02, DOC-04).** Исправлены битые ссылки в живых документах (README, SECURITY,
  NOTICE, AUTH, INSTALL, SPEC, ARCHITECTURE). Новый `tools/doc_links.py` проверяет их в CI;
  исторические документы (архив, аудит, `PROPOSAL-*`, ADR-0006 и ADR-0010) не проверяются.
  Ручные цифры «N тестов» убраны. В `AUTH.md` исправлено число итераций PBKDF2 (600 000, ADR-0003)
  и описан `can_manage_user` по уровням ролей. В `.env.example` добавлены `SESSION_TTL_HOURS`,
  `CSRF_ENABLED`, `MIGRATE_ON_START`, `NIGHT_SYNC_*`, `PDF_FONT`. В `deploy/README.md` §2 —
  обязательная смена демо-паролей на базе, созданной с демо-сидом.
* **6.2.** Этот файл вместо 27 файлов `docs/CHANGES-*` (перенесены в `docs/archive/changes/`).
  Выполненная `EXECUTION-SPEC-v2.md` — в `docs/archive/`. Тексты перенесены без переписывания:
  * прод-развёртывание — только в `deploy/README.md`: туда переехали установка без Docker из
    `docs/INSTALL.md` §2 (теперь §7) и «Продакшен-заметки» README (§8);
  * README сокращён с 56 до 11 КБ: вкладки, правила расчёта и справочники администратора —
    в новом `docs/GUIDE.md`, структура репозитория — в `docs/architecture/ARCHITECTURE.md` §9.
* Проверки: `doc_links` — 0 битых ссылок; pytest, линтеры и проверки инструментов зелёные.

### Фаза 5 аудита, часть 2: манифест модуля, роли как данные — PR #71
Модули описаны манифестами `app/modules/<имя>/manifest.py` (5.3, ADR-0012); меню и экраны
Настроек — из манифестов через `/api/auth/me` и `registerModule` (5.4, ADR-0008). Таблица
`roles`, иерархия по уровням, свои роли (5.5, ADR-0011). Пилот 5.8 заменён пробным модулем
в тестах. → [подробно](docs/archive/changes/CHANGES-2026-10-22-phase5-part2.md)

### Фаза 5 аудита, часть 1: деплой, лимит входа, транзакции — PR #71
Отдельный шаг деплоя `migrate` (5.2, ADR-0002), лимит входа в таблице `login_attempts` (5.7,
ADR-0005), сервисы без `commit` и аудит в той же транзакции (5.6).
→ [подробно](docs/archive/changes/CHANGES-2026-10-22-phase5-part1.md)

### Фаза 4 аудита: мёртвый код, наследие v4, хардкод — PR #70
Закрыты DEAD-01…04, DB-03, OPS-04, остаток HARD-02; удалены пять скрытых операций Графика (В-7).
→ [подробно](docs/archive/changes/CHANGES-2026-10-22-phase4-cleanup.md)

### Фаза 3 аудита: единые права, расхождения интерфейса и API — PR #70
Закрыты AUTHZ-05, DOC-03, UI-01, UI-02, BUG-02, BUG-03, ARCH-03 (матрица прав), UI-04.
→ [подробно](docs/archive/changes/CHANGES-2026-10-22-phase3-authz.md)

### Outbox рассылки и контейнер не от root — PR #70
Отправка службам через очередь (CONC-02), приложение в контейнере не от root (OPS-02), бланки
снова сохраняются в том. → [подробно](docs/archive/changes/CHANGES-2026-10-22-outbox-nonroot.md)

### Фаза 2 аудита: параллельные запросы и производительность — PR #70
Закрыты CONC-01…04, AUTHZ-08, UI-03, HARD-01, часть HARD-02, PERF-01.
→ [подробно](docs/archive/changes/CHANGES-2026-10-22-phase2-concurrency.md)

## 21.10.2026

### Фаза 1 аудита: решения владельца — PR #70
Закрыты AUTHZ-09, BUG-01, OPS-03, доделан AUTHZ-01 (В-3, В-4, В-8, В-12).
→ [подробно](docs/archive/changes/CHANGES-2026-10-21-phase1-owner-decisions.md)

### Фаза 1 аудита: безопасность и права — PR #70
Закрыты SEC-01…03, OPS-01, часть OPS-02, AUTHZ-01…04, 06, 07, 10; каждая дыра подтверждена
запуском до и после. → [подробно](docs/archive/changes/CHANGES-2026-10-21-security-phase1.md)

### Миграции: PostgreSQL, обновление старых баз, переход на Alembic — PR #70
Закрыты DB-01, DB-02, DB-04, DB-06, DB-07; пересмотрен ADR-0002.
→ [подробно](docs/archive/changes/CHANGES-2026-10-21-migrations-alembic.md)

### Внешнее ревью, P1: прочее — PR #69
Четыре находки вне движка и фронтенда: аудит, уведомления, валидации, медиа.
→ [подробно](docs/archive/changes/CHANGES-2026-10-21-review-p1-misc.md)

### Внешнее ревью, P1: фронтенд — PR #68
Шесть находок в клиентских скриптах. → [подробно](docs/archive/changes/CHANGES-2026-10-21-review-p1-frontend.md)

### Внешнее ревью, P1: таймшит и движок — PR #67
Семь находок в модуле timesheet. → [подробно](docs/archive/changes/CHANGES-2026-10-21-review-p1-timesheet.md)

## 20.10.2026

### Внешнее ревью, P1: ночной отчёт и электрокары — PR #66
Пять находок; записи убраны из GET-запросов, синхронизацию ночных отчётов ведёт фоновый поток.
→ [подробно](docs/archive/changes/CHANGES-2026-10-20-review-p1-night-cars.md)

### Внешнее ревью, P0 — PR #65
Четыре из пяти находок P0 и два бытовых дефекта. → [подробно](docs/archive/changes/CHANGES-2026-10-20-review-p0.md)

### Долг №2: кросс-модульные relationship удалены (R6) — PR #64
→ [подробно](docs/archive/changes/CHANGES-2026-10-20-debt2-r6-relationships.md)

### Долг №1: «менеджерская видимость» — ключами прав — PR #62
→ [подробно](docs/archive/changes/CHANGES-2026-10-20-debt1-scope-perms.md)

### Долг №3: «сегодня» только из `core/time` — PR #61
→ [подробно](docs/archive/changes/CHANGES-2026-10-20-debt3-local-date.md)

### Модульная перестройка, этап C (ADR-0010) — PR #55–#60
C1 — `core/` и composition root (#55), C2 — модуль `timesheet` (#56), C3 — `notify`, эталон (#57),
C4 — остальные модули и удаление legacy-пакетов (#58), C6 — фронтенд `static/js/modules/` (#59),
C7 — документация и AST-покрытие (#60). Спецификация — [`docs/archive/EXECUTION-SPEC-v2.md`](docs/archive/EXECUTION-SPEC-v2.md).
→ подробно: [C1](docs/archive/changes/CHANGES-2026-10-20-stage-c1-core.md),
[C2](docs/archive/changes/CHANGES-2026-10-20-stage-c2-timesheet.md),
[C3](docs/archive/changes/CHANGES-2026-10-20-stage-c3-notify.md),
[C4](docs/archive/changes/CHANGES-2026-10-20-stage-c4-modules.md),
[C6](docs/archive/changes/CHANGES-2026-10-20-stage-c6-frontend.md),
[C7](docs/archive/changes/CHANGES-2026-10-20-stage-c7-docs.md)

### Этап B: единые права через `require_perm` — PR #54
Ролевые зависимости удалены, единственный вход проверки прав — каталог `PERMISSIONS`.
→ [подробно](docs/archive/changes/CHANGES-2026-10-20-stage-b-permissions.md)

## 19.10.2026

### Единый центр настроек — PR #50
Справочники объекта (ночной обход, электрокары) переехали в «Настройки».
→ [подробно](docs/archive/changes/CHANGES-2026-10-19-settings-ia.md)

### Ночной отчёт v2, этап 1: зоны, объекты, чек-лист зоны — PR #44
→ [подробно](docs/archive/changes/CHANGES-2026-10-19-night-report-v2.md)

## 18.10.2026

### Упрощение «Настроек»: независимые справочники — PR #41
Значение рабочего дня — у сотрудника, компактный список кодов Табеля.
→ [подробно](docs/archive/changes/CHANGES-2026-10-18-settings-simplify.md)
