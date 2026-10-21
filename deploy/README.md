# Прод-развёртывание (docker-compose.prod.yml)

Референс-стек: **nginx (TLS) → приложение (uvicorn, N воркеров) → PostgreSQL 16**,
плюс ежедневные бэкапы. Локальная разработка — по-прежнему `./run.sh` (SQLite),
знакомство — `docker-compose.yml` (один контейнер).

## 1. Подготовка

```bash
cp .env.example .env
# в .env обязательно:
#   SECRET_KEY=$(openssl rand -hex 32)
#   POSTGRES_PASSWORD=<надёжный пароль>
#   ADMIN_PASSWORD=<пароль admin>   # первый старт на пустой базе; демо-учёток в проде нет
mkdir -p certs backups certbot-www
# сертификаты Let's Encrypt:
#   certs/fullchain.pem, certs/privkey.pem
```

Для первого выпуска сертификата (когда HTTPS ещё нет) временно запускайте только
nginx с :80 — `location /.well-known/acme-challenge/` уже настроен
(`certbot certonly --webroot -w ./certbot-www -d ваш-домен`).

## 2. Запуск и проверка

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps        # все сервисы healthy
curl -k https://localhost/api/health                # {"ok": true, "db": "ok", "version": …}
```

Приложение наружу не публикуется — только через nginx. `/metrics` (Prometheus)
заблокирован в nginx (`deny all`) и доступен лишь из внутренней сети compose —
скрейпер поднимайте там же или снимите блокировку для своих IP.

## 3. Флаги (переменные окружения app)

| Флаг | Прод-значение | Смысл |
|---|---|---|
| `COOKIE_SECURE` | `1` | cookie только по TLS |
| `ALLOW_IMPERSONATION` | `1` | демо-вход «как сотрудник» включён по умолчанию (решение владельца 15.10.2026); `0` — выключить |
| `TRUST_PROXY_HEADERS` | `1` | IP для rate-limit берётся из X-Forwarded-For (доверяем своему nginx) |
| `LOG_JSON` | `1` | структурированный access-лог (uvicorn стартует с `--no-access-log`) |
| `METRICS_ENABLED` | `1` | `/metrics` для внутреннего скрейпера |
| `UVICORN_WORKERS` | `2` | воркеры приложения; корректность при N>1 обеспечена (инициализация схемы — под замком `app/core/startup_lock.py`: `pg_advisory_lock`, второй воркер ждёт первого; фоновая синхронизация ночных отчётов — один раунд на всех под неблокирующим `try_lock("night-sync")`; замок отметок — `SELECT … FOR UPDATE`, CSRF stateless). Rate-limit входа считается per-worker — при жёстких требованиях выносите в Redis (ADR-0005) |
| `NIGHT_SYNC_ENABLED` | `1` | фоновая синхронизация ночных отчётов (досоздание смен, автозакрытие в 08:00): поток в lifespan, GET-запросы разделов — чистое чтение. `0` — выключить поток (останется только стартовый прогон `init_db`) |
| `NIGHT_SYNC_SECONDS` | `60` | период фонового раунда (минимум 5). Автозакрытие и появление отчёта в 20:00 запаздывают не больше чем на период |
| `CSP_REPORT_ONLY` | `0` | при раскатке можно временно `1` — браузер предупреждает, но не блокирует |

## 4. Бэкапы и восстановление

Сервис `backup` раз в сутки (`BACKUP_INTERVAL`, по умолчанию 86400 с) делает
`pg_dumpall | gzip` в `./backups/`, хранит последние `BACKUP_KEEP` (14) копий.

Восстановление:

```bash
gunzip -c backups/timetrack-2026-10-15-030000.sql.gz | \
  docker compose -f docker-compose.prod.yml exec -T db psql -U timetrack -d postgres
docker compose -f docker-compose.prod.yml restart app
```

Каталог `./backups` регулярно копируйте **на другой носитель/хост** — бэкап рядом
с базой не защищает от потери диска. В базе персональные данные: храните копии
зашифрованными (например, `age`/`gpg` поверх `.sql.gz`).

Загруженные бланки заявлений и фото живут в томах `app_templates`/`app_data` —
их резервное копирование настройте средствами хоста (docker run --rm -v …  tar).

## 5. Обновление версии

```bash
git fetch && git checkout <тег-релиза>
docker compose -f docker-compose.prod.yml up -d --build
curl -k https://localhost/api/health   # version должен совпасть с тегом
```

Схема БД мигрируется при старте автоматически: ревизии Alembic
`app/bootstrap/alembic/versions`. Базу, созданную до 21.10.2026, первый старт новой версии
доводит прежними шагами и штампует (ADR-0002). Перед обновлением сделайте бэкап.
