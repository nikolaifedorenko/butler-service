# Карта документации

**Статус:** живая справка — индекс всех документов репозитория

Единственная точка входа в документацию: что где лежит, какой у документа статус и для
кого он. Содержимое не пересказывается — только указатели.

## Правила жизненного цикла

Каждый живой `.md` (вне `docs/archive/`) начинается статус-заголовком:

```
**Статус:** <статус>
**Редакция:** <N> от <ДД.ММ.ГГГГ>   # обязательна для нормативов, спек и реестров
```

Допустимые статусы:

| Статус | Смысл |
|---|---|
| норматив | по документу пишется код; расхождение «код vs норматив» — баг одного из них |
| живая справка | описывает текущее состояние; обновляется непрерывно, редакция не нумеруется |
| реализованная спека (дата, PR) | спека внедрена; текст — историческая фиксация замысла |
| черновик | готовится, на код не влияет |
| заменён (→ куда) | не действует; оставлен как указатель |
| принят ДД.ММ.ГГГГ | для ADR; при пересмотре — «заменён ADR-NNNN» |
| реестр действующих решений | для `decisions.md`: только действующие решения, без логов отмен |
| архив (дата) | только для файлов в `docs/archive/` |

* Архивирование — перенос файла (`git mv`) + строка в [`archive/README.md`](archive/README.md);
  исторические документы не правятся.
* Реестры `decisions.md` хранят **только действующие решения** (без логов отмен):
  отменённое решение удаляется из реестра, факт отмены остаётся в архивной спеке/CHANGELOG.
* CI-гейты: [`tools/doc_links.py`](../tools/doc_links.py) — битые ссылки;
  [`tools/doc_status.py`](../tools/doc_status.py) — наличие и валидность статус-заголовков.

## Точка входа и журналы

| Документ | Роль | Для кого |
|---|---|---|
| [`README.md`](../README.md) | корень проекта: позиционирование, быстрый старт | все |
| `docs/README.md` | эта карта | все |
| [`CHANGELOG.md`](../CHANGELOG.md) | журнал batчей: дата, тема, PR, проверка | владелец, разработчики |
| [`NOTICE.md`](../NOTICE.md) | сторонние компоненты; лицензионная позиция | владелец |
| [`docs/openapi.json`](openapi.json) | контракт API (сверяется с кодом в CI) | разработчики |

## Нормативы и реестры решений — `docs/specs/`

На каждый модуль — `spec.md` (норматив действующего поведения) и `decisions.md`
(реестр действующих решений в родной нумерации модуля).

| Модуль | Спека | Решения | ID решений |
|---|---|---|---|
| timesheet — Табель, переработки, банк часов | [`spec.md`](specs/timesheet/spec.md) (v7.2) | [`decisions.md`](specs/timesheet/decisions.md) | R1–R40, Н1–Н7, О1 |
| stays — «Шахматка» | [`spec.md`](specs/stays/spec.md) | [`decisions.md`](specs/stays/decisions.md) | S1–S63 |
| night — ночной отчёт | [`spec.md`](specs/night/spec.md) | [`decisions.md`](specs/night/decisions.md) | N1–N7 (лат.) |
| notify — уведомления | [`spec.md`](specs/notify/spec.md) | [`decisions.md`](specs/notify/decisions.md) | NT1–NT9 |
| cars — автопарк | [`spec.md`](specs/cars/spec.md) | [`decisions.md`](specs/cars/decisions.md) | C1–C5 |
| docs — документы (.docx) | [`spec.md`](specs/docs/spec.md) | [`decisions.md`](specs/docs/decisions.md) | DOC1–DOC3 |
| access — права и роли | [`spec.md`](specs/access/spec.md) | [`decisions.md`](specs/access/decisions.md) | AC1–AC5 |
| audit — журнал аудита | [`spec.md`](specs/audit/spec.md) | [`decisions.md`](specs/audit/decisions.md) | AU1–AU3 |
| employees — сотрудники | [`spec.md`](specs/employees/spec.md) | [`decisions.md`](specs/employees/decisions.md) | E1–E5 |
| settings — раздел настроек | [`spec.md`](specs/settings/spec.md) | [`decisions.md`](specs/settings/decisions.md) | ST1–ST6 |
| platform — сквозное (core, deploy, ИБ) | — | [`decisions.md`](specs/platform/decisions.md) | P1–P16 + индекс ADR |

> Нумерации «Н1–Н7» timesheet (кириллическая Н, приложение А.12 спеки) и «N1–N7» night
> (латинская N) независимы и визуально похожи: в ссылках всегда указывайте модуль
> («night N3» ≠ «timesheet Н3»).

## Приложение, руководства, эксплуатация

| Документ | Роль | Для кого |
|---|---|---|
| [`docs/SPEC.md`](SPEC.md) | обзор приложения: модель данных, API, вкладки (нормы — в `docs/specs/`) | разработчики |
| [`docs/GUIDE.md`](GUIDE.md) | руководство: вкладки, правила расчёта, администрирование | пользователи, админы |
| [`docs/INSTALL.md`](INSTALL.md) | установка: локально, сервер, Docker, бэкапы | админы |
| [`docs/AUTH.md`](AUTH.md) | аутентификация и сессии | разработчики |
| [`docs/TEMPLATES.md`](TEMPLATES.md) | шаблоны кадровых документов .docx | админы |
| [`SECURITY.md`](../SECURITY.md) | политика безопасности, уровни ПДн | владелец, разработчики |
| [`deploy/README.md`](../deploy/README.md) | прод-развёртывание (nginx, uvicorn, PostgreSQL 16, бэкапы) | админы |

## Архитектура

* [`docs/architecture/ARCHITECTURE.md`](architecture/ARCHITECTURE.md) — архитектурный разбор
  (модульный монолит `core/` + `modules/`, слои, данные, фронтенд, деплой).

| ADR | Тема | Статус |
|---|---|---|
| [0001](adr/0001-record-architecture-decisions.md) | записи архитектурных решений | принят |
| [0002](adr/0002-migrations-alembic-deferred.md) | миграции схемы: Alembic | принят (пересмотрен 21.10.2026) |
| [0003](adr/0003-password-hashing-pbkdf2-600k.md) | хеширование паролей: PBKDF2 600k | принят |
| [0004](adr/0004-csrf-double-submit-and-csp.md) | CSRF double-submit; CSP | принят |
| [0005](adr/0005-rate-limit-in-memory.md) | rate-limit входа | принят (пересмотрен 22.10.2026) |
| [0006](adr/0006-pragmatic-clean-boundary.md) | прагматичная граница чистой архитектуры | заменён → ADR-0010 |
| [0007](adr/0007-session-token-format.md) | сессионный токен: подписной формат, не JWT | принят |
| [0008](adr/0008-frontend-bez-sborki.md) | фронтенд без сборки | принят |
| [0009](adr/0009-edinoye-okno-otmetok.md) | единое окно отметок | принят |
| [0010](adr/0010-modular-monolith-core-modules.md) | модульный монолит `core/` + `modules/` | принят |
| [0011](adr/0011-roles-as-data.md) | роли и права как данные | принят |
| [0012](adr/0012-module-manifest.md) | манифест модуля | принят |

## Архив — `docs/archive/`

Исторические документы: не действуют, не правятся, хранятся полностью
(состав и причины переноса — [`archive/README.md`](archive/README.md)):

* `specs-stays/` — исходные 7 спек «Шахматки» (консолидированы в `specs/stays/spec.md`);
* `proposals/` — реализованные предложения (ночной отчёт v2, информационная архитектура настроек);
* `changes/` — подробные описания батчей до 22.10.2026;
* `plans-stays/`, `prototypes/` — планы и прототипы проектирования «Шахматки»;
* `overtime_spec_v7_1_final.md` — копия v7.1 (действующий норматив — `specs/timesheet/spec.md`);
* `EXECUTION-SPEC-v2.md` — спецификация модульного перезапуска (исполнена).
