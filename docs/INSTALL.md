# Установка и развертывание Батлер Сервис

## 1. Локальная машина (любая ОС)

### Требования
* Python **3.10+** (проверка: `python3 --version`);
* ~200 МБ места; интернет для установки зависимостей (однократно).

### Шаги (Linux / macOS)
```bash
# 1. Распакуйте/склонируйте проект и зайдите в папку
cd timetrack

# 2. Виртуальное окружение (рекомендуется)
python3 -m venv .venv
source .venv/bin/activate

# 3. Зависимости (ядро; PDF-движок — по желанию, см. ниже)
pip install -r requirements.txt

# 4. Конфигурация
cp .env.example .env
#   отредактируйте .env: SECRET_KEY (openssl rand -hex 32), APP_TZ — ваш часовой пояс

# 5. Запуск
./run.sh                                  # или: python3 -m uvicorn app.main:app --port 8000
```
`./run.sh` сам проверит Python, создаст `.venv`, **доустановит недостающие пакеты**,
убедится, что приложение импортируется, и покажет адрес (включая IP для телефона).
Полезные режимы:

| Команда | Что делает |
|---|---|
| `./run.sh` | обычный запуск (при необходимости чинит зависимости) |
| `./run.sh --reinstall` | пересоздать `.venv` и поставить всё заново |
| `PDF=off ./run.sh` | быстрый старт, не пытаясь ставить PDF-движок |
| `PORT=9000 ./run.sh` | другой порт |
Откройте **http://127.0.0.1:8000** — при первом запуске создастся `timetrack.db`
и заполнится демо-данными (10 сотрудников, 3 блока графика, отметки за ~1,5 месяца).

### Шаги (Windows)
```powershell
cd timetrack
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        # затем отредактируйте .env в блокноте
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
(`run.sh` — bash-скрипт, в Windows используйте команду выше или WSL.)

### Демо-доступы (пароль `demo1234`)
`admin` (администратор), `smirnov` (менеджер), `gromova` (старший батлер),
`ivanov`, `petrov`, `volkov` (сотрудники; `volkov` — «Другие смены», 3/3 ночные).
Полный список — на экране входа («Демо-доступы»).

### Полезное
* **Сброс демо-данных:** остановите сервер и удалите `timetrack.db`, затем запустите снова.
* **Тесты:** `python3 -m pytest tests/ -q` (76 проверок: движок, API, новые сценарии).
* **PDF заявлений — необязательная возможность.** Сервер делает PDF одним из двух способов:
  1. **LibreOffice** (лучший вариант: PDF получается один в один с вашим .docx-бланком) —
     `brew install --cask libreoffice` (macOS) / `sudo apt install libreoffice-writer` (Linux);
  2. **встроенный рендер** — `pip install -r requirements-pdf.txt` (reportlab; шрифты DejaVu
     уже лежат в `assets/fonts/`).

  Если ни то, ни другое не установлено, приложение **не ломается**: кнопка «DOCX» скачивает готовый
  документ (открывается в Word/Pages/LibreOffice и печатается напрямую), а «Печать заявления»
  печатает через браузер. Кнопка «PDF» в этом случае честно сообщает, чего не хватает.
  Текущий режим виден в Настройки → Шаблоны документов и в `GET /api/docs/templates` (`pdf`).

  > Почему PDF вынесен отдельно: на самых новых версиях Python (например 3.14) готовых
  > сборок reportlab может не быть, и pip начинает компилировать его из исходников.
  > Раньше это роняло всю установку зависимостей; теперь ядро ставится всегда,
  > а PDF-движок — только если соберётся.
* **Обновление версии:** просто перезапустите сервер (`./run.sh`) — схема БД мигрирует
  автоматически при старте, данные сохраняются. Проверка схемы: http://127.0.0.1:8000/api/selfcheck.
  Если после обновления появились странные ошибки кэша — очистите кэш браузера или откройте
  страницу в режиме инкогнито (файлы `app.js`/`app.css` подключены с версией `?v=…`).

### Если сервер не стартует

| Ошибка в терминале | Что делать |
|---|---|
| `ModuleNotFoundError: No module named 'docx'` (или `fastapi`, `uvicorn`, `openpyxl`) | зависимости не установлены/установлены частично: `./run.sh` (доустановит сам) или `./run.sh --reinstall` |
| `error: can't combine options ...` / `Failed building wheel for reportlab` | это про **необязательный** PDF-движок: он уже вынесен в `requirements-pdf.txt`, просто пропустите его (`PDF=off ./run.sh`). Печать и DOCX работают без него |
| `Address already in use` | порт занят: `PORT=8010 ./run.sh` или остановите прошлый процесс |
| `Permission denied` при запуске `./run.sh` | `chmod +x run.sh setup_macos.sh` |
| Белый экран в браузере | откройте консоль (F12) и `server.log`; чаще всего — кэш, лечится `Cmd+Shift+R` |

Диагностика одной командой: `./run.sh --reinstall` — пересоздаст окружение и покажет,
какой пакет не ставится.
* **UI-смоук:** `python3 tools/smoke_ui.py` (нужен Playwright: `pip install playwright
  && python3 -m playwright install chromium`).
* **Swagger API:** http://127.0.0.1:8000/api/docs
* **Телефон в той же сети:** запустите с `--host 0.0.0.0` и откройте
  `http://<IP-компьютера>:8000` (интерфейс адаптивный, ставится на главный экран как PWA).
* **Другой порт:** `PORT=8080 ./run.sh` или `--port 8080`.

---

## 2. Сервер (Ubuntu 22.04/24.04, systemd + nginx + HTTPS)

### 2.1. Подготовка
```bash
sudo apt update && sudo apt install -y python3-venv python3-pip nginx certbot python3-certbot-nginx
sudo useradd -r -m -d /opt/timetrack -s /usr/sbin/nologin timetrack
sudo mkdir -p /opt/timetrack && sudo chown timetrack:timetrack /opt/timetrack
# скопируйте файлы проекта в /opt/timetrack (scp, rsync, git clone…)
```

### 2.2. Окружение и зависимости
```bash
sudo -u timetrack python3 -m venv /opt/timetrack/.venv
sudo -u timetrack /opt/timetrack/.venv/bin/pip install -r /opt/timetrack/requirements.txt
sudo -u timetrack cp /opt/timetrack/.env.example /opt/timetrack/.env
sudo -u timetrack nano /opt/timetrack/.env     # SECRET_KEY=<(openssl rand -hex 32>), APP_TZ
```

### 2.3. PostgreSQL (рекомендуется для боевого режима)
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

### 2.4. systemd-сервис
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

### 2.5. nginx + HTTPS
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

### 2.6. Docker (альтернатива)
```bash
docker compose up -d --build        # SQLite в томе tt_data, порт 8000
SECRET_KEY=$(openssl rand -hex 32) COOKIE_SECURE=1 docker compose up -d --build
```

### 2.7. Эксплуатация
* **Бэкапы:** SQLite — копия файла `timetrack.db` (лучше через `sqlite3 db ".backup …"`);
  PostgreSQL — `pg_dump timetrack > dump.sql` по cron. Храните также `.env` (SECRET_KEY).
* **Обновление:** заменить файлы → `pip install -r requirements.txt` →
  `systemctl restart timetrack`. Таблицы добавляются автоматически; при изменении схемы
  колонок (редко) может понадобиться пересоздание БД из бэкапа — см. «Ограничения» в SPEC.md.
* **Логи:** `journalctl -u timetrack`; аудит действий пользователей — в разделе «Настройки»
  и таблице `audit_log`.
* **Доступ с телефонов:** домен + HTTPS; интерфейс — PWA («Добавить на главный экран»).

---

## 3. Первый вход и настройка под себя
1. Войдите под `admin`, смените демо-пароли: «Сотрудники» → «Изменить» → новый пароль.
2. Задайте сотрудников, группы графика («Смена 1», «Смена 2», «Администрация») и цвета должностей.
3. В «Настройках» добавьте нужные смены (часы) и проверьте правила расчёта (округление, окна отметок).
4. Заполните график на месяц («Заполнить графиком»: цикл, сдвиг фазы, только пустые ячейки).
5. Раздайте сотрудникам логины; покажите кнопку «Пришёл на работу» (раздел «Мои отметки»).
