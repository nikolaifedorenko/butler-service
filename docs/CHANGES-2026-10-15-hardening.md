# Изменения 15.10.2026 — очистка репозитория, безопасность, наблюдаемость, прод-профиль

Батч по итогам аудита (`ROADMAP-butler-service.md`,
`AUDIT-quality-cleanup-2026-10-15.md`): закрыты пункты P0/P1, которые можно
было сделать без изменения расчётной модели. Движок v7.1 не тронут; поведение
вкладок не изменилось. Версия приложения введена в `settings.app_version`
(старт с `0.1.0`, bump при релизе вместе с тегом).

## 1. Очистка репозитория

Инвентаризация `git ls-files` + grep по всем ссылкам (CI, package.json, README,
docs, tools):

- удалены 7 мёртвых скриптов `tools/` (никем не вызываются): `smoke_dicts`,
  `smoke_doublepay`, `smoke_fixes` (заменены pytest), `debug_clicks`,
  `screen_docs`, `screen_genitive`, `proto_layers_smoke.mjs`;
- **прототип «График = 4 слоя» выведен из CI**: T5 реализована (PR #11),
  нормативные примеры владельца зафиксированы боевыми проверками
  (`test_grafik_norms` 15 + `smoke:norms` 72 + `smoke:layers` 50), генератор
  прототипа в репозитории отсутствовал — файл невоспроизводим. Удалены шаг CI,
  `smoke:proto`, сам смоук; HTML перемещён в архив;
- устаревшие документы — в `docs/archive/` с индексом: `overtime_ai_tz_v3.md`
  (заменён spec v7.1), `AUDIT-2026-09-27.md` (аудит удалённого legacy-движка),
  оба прототипа. Ссылки в активных доках обновлены, исторические CHANGES не
  переписывались;
- `tests/test_zz_genitive.py` → `test_genitive.py` (zz-костыль порядка импортов
  устарел после централизации окружения в conftest);
- `.gitignore`: добавлены `.hypothesis/`, `.ruff_cache/`, `.pytest_cache/`;
- README: счётчик проверок актуализирован.

## 2. Безопасность

- **PBKDF2-HMAC-SHA256: 120 000 → 600 000 итераций** (OWASP). Ленивая миграция:
  `needs_rehash()` + пересчёт хеша при успешном входе — пароли не сбрасываются
  (ADR-0003).
- **CSP** по фактическому содержимому интерфейса: `script-src 'self'` (inline-
  скриптов и onclick нет), `style-src 'self' 'unsafe-inline'` (300+ inline-атрибутов
  style — компромисс без сборки), `object-src/base-uri/form-action` закрыты,
  `frame-ancestors 'none'`, `img-src 'self' data: blob:`. Флаг `CSP_REPORT_ONLY=1`
  для раскатки. **Permissions-Policy**: geolocation/microphone/camera/payment
  выключены. **HSTS** — только по TLS (ADR-0004).
- **Демо-вход «войти как сотрудник» по умолчанию ВЫКЛЮЧЕН**
  (`allow_impersonation: False`); `.env.example` и тесты включают явно,
  docker-compose(prod) — `0`.
- **X-Forwarded-For** для rate-limit читается только при `TRUST_PROXY_HEADERS=1`
  (за своим доверенным прокси) — иначе заголовок подделывается клиентом.
- **Межпроцессный замок отметок**: `SELECT … FOR UPDATE` на строку сотрудника
  внутри `_punch_locked` — при нескольких воркерах на Postgres гонка
  «прочитал состояние — вставил отметку» закрыта (SQLite форсу игнорирует, там
  писатели сериализуются WAL+busy_timeout). `threading.Lock` оставлен как
  дешёвая защита внутри процесса.
- Порядок middleware пересобран (csrf → security_headers → request_context):
  заголовки безопасности и `X-Request-ID` попадают и на 403-ответы CSRF.
- `LICENSE` (MIT) + `NOTICE.md` (шрифты: DejaVu — Bitstream Vera; Manrope,
  Playfair Display — OFL 1.1; зависимости) + `SECURITY.md` (приватный канал
  сообщений об уязвимостях, поддерживаемые версии, границы демо-режимов).
- Тесты: `tests/test_security_hardening.py` (7) — параметры хеша, rehash при
  входе, заголовки, Report-Only-переключатель, default-off демо-входа, XFF.

## 3. Наблюдаемость

- **Сквозной `X-Request-ID`**: принимается от прокси (санитизация: белый список
  символов, ≤64 — защита от log-injection) или генерируется; возвращается в
  ответе.
- **`LOG_JSON=1`**: access-лог одной JSON-строкой (ts/method/path/status/
  duration_ms/route/request_id/ip); health и metrics не логируются (шум
  healthcheck'ов); в проде uvicorn с `--no-access-log`.
- **`METRICS_ENABLED=1` → `GET /metrics`** (prometheus-client, новая опциональная
  зависимость; импорт guarded). Метка маршрута — шаблон роутера, не сырой путь
  (кардинальность). По умолчанию 404 — метрики не публичны; в prod-nginx
  дополнительно `deny all`.
- **`GET /api/health` углублён**: проверяет БД (`SELECT 1`), возвращает версию;
  503 при недоступной БД — healthcheck'и контейнера/балансировщика стали
  содержательными. Текст ошибки БД наружу не отдаётся (только тип исключения).
- `settings.app_version` — в `FastAPI(version=…)`, health и OpenAPI-схеме.
- Тесты: `tests/test_observability.py` (4).

## 4. Цепочка поставок и контракт API

- **Dependabot** (`.github/dependabot.yml`): еженедельные PR для pip / npm /
  github-actions.
- **CI-аудит известных CVE**: `pip-audit` (python-джоб) и `npm audit
  --audit-level=high` (frontend-джоб); пока `continue-on-error` — после
  инвентаризации находок флаг снять.
- **`docs/openapi.json` — контракт API как артефакт** (127 путей):
  `tools/export_openapi.py` (+`--check`), шаг CI «Контракт OpenAPI не разошёлся
  с кодом» — breaking-изменения видны в diff'е PR.

## 5. Прод-профиль развёртывания

`docker-compose.prod.yml` + `deploy/` (nginx.conf, README):

- **nginx**: TLS 1.2/1.3, HTTP→HTTPS, ACME-webroot, gzip, `client_max_body_size
  8m`, `proxy_read_timeout 200s` (PDF через LibreOffice до 180 с), `/metrics` —
  deny all, проброс `X-Forwarded-*` и `X-Request-ID`;
- **PostgreSQL 16** (healthcheck) + `psycopg2-binary` в образе
  (`requirements-postgres.txt`);
- **app**: uvicorn `--workers N --proxy-headers --no-access-log`, боевые флаги
  (COOKIE_SECURE=1, ALLOW_IMPERSONATION=0, TRUST_PROXY_HEADERS=1, LOG_JSON=1,
  METRICS_ENABLED=1); наружу не публикуется;
- **backup**: `pg_dumpall | gzip` ежесуточно в `./backups`, ротация 14 копий;
  восстановление описано в `deploy/README.md`.

Локальная разработка не затронута: `./run.sh` (SQLite) и одиночный
`docker-compose.yml` работают как прежде.

## 6. Документация решений

`docs/adr/` (ADR-0001…0007): записи решений — миграции (Alembic отложен),
хеширование паролей, CSRF/CSP, rate-limit in-memory, прагматичная граница
чистой архитектуры, формат сессионного токена. Риск-таблица ARCHITECTURE.md:
«SQLite в проде» закрыт прод-профилем.

## Проверки

- pytest: **492 passed, 1 skipped** (было 481: +7 security, +4 observability);
- ruff / eslint / node --check / js_globals / bump_version: чисто;
- смоук интерфейса (3 роли) и сценарии settings (62) / norms (72) / layers (50):
  зелёные; шаг proto-смока удалён вместе с прототипом;
- lock-файл перегенерирован (`freeze_requirements.py`, 48 пакетов);
- YAML compose/workflow валидны; docker build — в CI (локально в песочнице
  недоступен).

##Breaking-ноты для деплоя

- Приложение **не стартует** без валидного `SECRET_KEY` (с 14.10.2026) —
  прод-окружения обязаны задать ключ; `change-me*` из старых `.env` отклоняется.
- Демо-вход «как сотрудник» по умолчанию выключен — демо-стендам нужен
  `ALLOW_IMPERSONATION=1`.
- CSP блокирующая по умолчанию; при неожиданностях в браузере — временный
  `CSP_REPORT_ONLY=1` и разбор отчётов консоли.
- Хеши паролей обновляются прозрачно при входе; принудительного сброса нет.
