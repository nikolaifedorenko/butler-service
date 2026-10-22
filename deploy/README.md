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
#   BACKUP_AGE_RECIPIENT=age1…      # открытый ключ шифрования бэкапов, BACKUP_REMOTE — второй сервер (§4)
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

**Обязательно после первого входа:** если база создавалась до 21.10.2026 или с `DEMO_SEED=1`,
в ней есть демо-учётки с паролем `demo1234` (`admin`, `smirnov` и другие). Проверьте вход под
ними и смените пароли («Сотрудники» → «Изменить») или увольте лишние учётки. На новой базе без
`DEMO_SEED` создаётся только `admin` с паролем из `ADMIN_PASSWORD`.

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
| `MIGRATE_ON_START` | `0` | воркеры схему не мигрируют, а сверяют ревизию: миграции, справочники и первого администратора готовит сервис `migrate` (`python -m app.bootstrap.migrate`) до старта `app` |
| `UVICORN_WORKERS` | `2` | воркеры приложения; корректность при N>1 обеспечена (схему готовит сервис `migrate` до старта воркеров, ручной запуск страхует замок `app/core/startup_lock.py`; фоновая синхронизация ночных отчётов — один раунд на всех под неблокирующим `try_lock("night-sync")`; очередь отправки службам — под `try_lock("night-dispatch")`, доотправка очереди (outbox) — один процесс под `try_lock("notify-outbox")`; замок отметок — `SELECT … FOR UPDATE`, CSRF stateless). лимит входа — общий, в таблице `login_attempts` (ADR-0005) |
| `NIGHT_SYNC_ENABLED` | `1` | фоновая синхронизация ночных отчётов (досоздание смен, автозакрытие в 08:00): поток в lifespan, GET-запросы разделов — чистое чтение. `0` — выключить поток (останется только стартовый прогон `init_db`) |
| `NIGHT_SYNC_SECONDS` | `60` | период фонового раунда (минимум 5). Автозакрытие и появление отчёта в 20:00 запаздывают не больше чем на период |
| `API_DOCS` | `0` | Swagger `/api/docs` и схема `/api/openapi.json` выключены: полная карта API без входа облегчает разведку. Для отладки — `1` |
| `CSP_REPORT_ONLY` | `0` | при раскатке можно временно `1` — браузер предупреждает, но не блокирует |

## 4. Бэкапы и восстановление

Сервис `backup` раз в сутки (`BACKUP_INTERVAL`, по умолчанию 86400 с) делает
`pg_dumpall | gzip`, **шифрует** копию ключом age и кладёт в `./backups/` (последние
`BACKUP_KEEP` = 14), затем копирует на **второй сервер** (`deploy/backup.sh`). На боевом
сервере лежит только открытый ключ: им копию можно зашифровать, но нельзя прочитать.
Без `BACKUP_AGE_RECIPIENT` сервис не стартует — незашифрованных копий нет.

**Подготовка (один раз):**

1. Ключ шифрования — на своём компьютере, не на сервере (`brew install age` / `apt install age`):
   ```bash
   age-keygen -o butler-backup-key.txt     # закрытый ключ: в сейф / менеджер паролей, копию — офлайн
   age-keygen -y butler-backup-key.txt     # открытый ключ age1… → в .env: BACKUP_AGE_RECIPIENT=age1…
   ```
   **Без закрытого ключа копию не восстановить никак.** Потеряли ключ — потеряли все копии.
2. Второй сервер: пользователь с доступом только по SSH-ключу и каталог под копии, на нём
   нужен `rsync`. На боевом сервере:
   ```bash
   mkdir -p deploy/backup-ssh && ssh-keygen -t ed25519 -N "" -f deploy/backup-ssh/id_ed25519
   ssh-keyscan backup-host > deploy/backup-ssh/known_hosts      # сверьте отпечаток вручную
   # содержимое deploy/backup-ssh/id_ed25519.pub — в ~/.ssh/authorized_keys пользователя на втором сервере
   ```
   В `.env`: `BACKUP_REMOTE=user@backup-host:/srv/butler-backups/`. Каталог `deploy/backup-ssh/`
   в git не попадает. На втором сервере остаются те же 14 последних копий (`rsync --delete`).

**Проверка восстановления — раз в месяц**, там, где лежит закрытый ключ:

```bash
deploy/restore_check.sh timetrack-2026-10-21-030000.sql.gz.age butler-backup-key.txt
```

Скрипт поднимает временный PostgreSQL, восстанавливает копию и показывает число
пользователей, сотрудников, отметок и ревизию схемы.

**Восстановление боевой базы** (копию и ключ принести на сервер временно, ключ потом удалить):

```bash
age -d -i butler-backup-key.txt timetrack-2026-10-21-030000.sql.gz.age | gunzip | \
  docker compose -f docker-compose.prod.yml exec -T db psql -U timetrack -d postgres
docker compose -f docker-compose.prod.yml restart app
```

Загруженные бланки заявлений и фото живут в томах `app_templates`/`app_data` —
их резервное копирование настройте средствами хоста (docker run --rm -v …  tar).

## 5. Обновление версии

```bash
git fetch && git checkout <тег-релиза>
docker compose -f docker-compose.prod.yml up -d --build
curl -k https://localhost/api/health   # version должен совпасть с тегом
```

Схему БД обновляет сервис `migrate`: он запускается первым (`python -m app.bootstrap.migrate`,
ревизии Alembic `app/bootstrap/alembic/versions`), и только после его успешного завершения
стартует `app`. Базу, созданную до 21.10.2026, он доводит прежними шагами и штампует
(ADR-0002). Если `migrate` упал, `app` не стартует — смотрите
`docker compose -f docker-compose.prod.yml logs migrate`. Перед обновлением сделайте бэкап.

## 6. Приложение в контейнере — не от root

С 22.10.2026 приложение работает от пользователя `app` (uid 10001). Новые тома
(`app_data` и `app_templates`, в `docker-compose.yml` — `tt_data` и `tt_templates`) получают
этого владельца из образа сами. Тома, созданные раньше, принадлежат root: приложение не
стартует и пишет в лог «Нет прав на запись в …». Передайте их один раз:

```bash
docker compose -f docker-compose.prod.yml run --rm --user root app \
  chown -R app:app /srv/timetrack/data /srv/timetrack/templates
```

Для `docker-compose.yml` — та же команда без `-f docker-compose.prod.yml` и с сервисом
`timetrack` вместо `app`. Если вместо томов смонтированы каталоги хоста:
`sudo chown -R 10001:10001 ./data ./templates`.

## 7. Без Docker: Ubuntu 22.04/24.04, systemd + nginx + HTTPS

### 7.1. Подготовка
```bash
sudo apt update && sudo apt install -y python3-venv python3-pip nginx certbot python3-certbot-nginx
sudo useradd -r -m -d /opt/timetrack -s /usr/sbin/nologin timetrack
sudo mkdir -p /opt/timetrack && sudo chown timetrack:timetrack /opt/timetrack
# скопируйте файлы проекта в /opt/timetrack (scp, rsync, git clone…)
```

### 7.2. Окружение и зависимости
```bash
sudo -u timetrack python3 -m venv /opt/timetrack/.venv
sudo -u timetrack /opt/timetrack/.venv/bin/pip install -r /opt/timetrack/requirements.txt
sudo -u timetrack cp /opt/timetrack/.env.example /opt/timetrack/.env
sudo -u timetrack nano /opt/timetrack/.env     # SECRET_KEY=<(openssl rand -hex 32>), APP_TZ
```

### 7.3. PostgreSQL (рекомендуется для боевого режима)
```bash
sudo apt install -y postgresql
sudo -u postgres psql <<'SQL'
CREATE USER timetrack WITH PASSWORD 'STRONG_PASSWORD';
CREATE DATABASE timetrack OWNER timetrack;
SQL
sudo -u timetrack /opt/timetrack/.venv/bin/pip install psycopg2-binary
# в .env:  DATABASE_URL=postgresql+psycopg2://timetrack:STRONG_PASSWORD@127.0.0.1:5432/timetrack
```
Таблицы создаются автоматически при старте (`create_all`). Для SQLite ничего делать не нужно.

### 7.4. systemd-сервис
```ini
# /etc/systemd/system/timetrack.service
[Unit]
Description=Батлер Сервис — учёт рабочего времени
After=network.target postgresql.service

[Service]
User=timetrack
Group=timetrack
WorkingDirectory=/opt/timetrack
EnvironmentFile=/opt/timetrack/.env
ExecStart=/opt/timetrack/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now timetrack
systemctl status timetrack          # journalctl -u timetrack -f  — логи
```

### 7.5. nginx + HTTPS
```nginx
# /etc/nginx/sites-available/timetrack
server {
    listen 80;
    server_name time.example.ru;

    client_max_body_size 20m;

    location /static/ {
        alias /opt/timetrack/static/;
        expires 7d;
        add_header Cache-Control "public";
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
```bash
sudo ln -s /etc/nginx/sites-available/timetrack /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d time.example.ru        # выпустит сертификат и включит HTTPS
# после HTTPS: в .env раскомментируйте COOKIE_SECURE=1 и: sudo systemctl restart timetrack
```

### 7.6. Docker (альтернатива)
```bash
DEMO_SEED=1 docker compose up -d --build   # демо: SQLite в томе tt_data, порт 8000, пароль demo1234
ADMIN_PASSWORD=<пароль admin> SECRET_KEY=$(openssl rand -hex 32) COOKIE_SECURE=1 docker compose up -d --build
```
Приложение в контейнере работает не от root (пользователь `app`). Тома, созданные до
22.10.2026, нужно один раз передать этому пользователю — команда в `deploy/README.md` §6.

### 7.7. Эксплуатация
* **Бэкапы:** SQLite — копия файла `timetrack.db` (лучше через `sqlite3 db ".backup …"`);
  PostgreSQL — `pg_dump timetrack > dump.sql` по cron. Храните также `.env` (SECRET_KEY).
* **Обновление:** заменить файлы → `pip install -r requirements.txt` →
  `systemctl restart timetrack`. Таблицы добавляются автоматически; при изменении схемы
  колонок (редко) может понадобиться пересоздание БД из бэкапа — см. «Ограничения» в SPEC.md.
* **Логи:** `journalctl -u timetrack`; аудит действий пользователей — в разделе «Настройки»
  и таблице `audit_log`.
* **Доступ с телефонов:** домен + HTTPS; интерфейс — PWA («Добавить на главный экран»).

## 8. Заметки по эксплуатации

* **Референс-прод-стек**: `docker-compose.prod.yml` — nginx (TLS, gzip, лимиты) +
  PostgreSQL 16 + приложение в несколько воркеров + ежедневные бэкапы. Пошагово —
  разделы 1–6 выше. Для знакомства достаточно одиночного
  `docker-compose.yml` (SQLite), для разработки — `./run.sh`.
* БД: SQLite по умолчанию (WAL + `busy_timeout`); для боевого режима
  `DATABASE_URL=postgresql://…` в `.env` (драйвер уже в образе,
  `requirements-postgres.txt`).
* Часовой пояс объекта: `APP_TZ` (по умолчанию `Europe/Moscow`) — должен совпадать
  с `Settings.tz` движка; DST намеренно не поддерживается (локальные сутки = 1440 мин,
  решение владельца R24).
* `SECRET_KEY` — обязательно задайте уникальный: с пустым/коротким/примерным ключом
  приложение **отказывается стартовать** (см. `app/main.py`).
* Боевые флаги по умолчанию безопасны: CSP блокирующая, `/metrics` выключен.
  Демо-вход «как сотрудник» включён по умолчанию (решение владельца от
  15.10.2026) — `ALLOW_IMPERSONATION=0` выключает. За reverse-proxy включите
  `TRUST_PROXY_HEADERS=1`; при раскатке CSP можно временно перевести в
  `CSP_REPORT_ONLY=1`.
* Наблюдаемость: `LOG_JSON=1` — структурированный access-лог; сквозной
  `X-Request-ID`; `GET /api/health` проверяет БД (503 при недоступности) и
  возвращает версию; `METRICS_ENABLED=1` — Prometheus-метрики `/metrics`.
* Атомарность закрытий обеспечивает `UnitOfWork` (commit/rollback); конкурентное
  повторное закрытие исключает уникальный ключ `(employee_id, period_start)`;
  отметки при нескольких воркерах защищены строковым замком БД (`FOR UPDATE`).
* Бэкапы: в прод-профиле — автоматические (`./backups`, pg_dumpall ежесуточно,
  восстановление — см. `deploy/README.md`); на SQLite регулярно копируйте файл БД.
  В базе — персональные данные: храните копии зашифрованными.
* Зарплатный модуль намеренно не ведётся; информационный план строки Табеля —
  зарплатный атрибут, денежный расчёт добавляется отдельным слоем поверх данных УТ.
