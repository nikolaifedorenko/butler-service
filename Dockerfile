# Простой контейнер TimeTrack: приложение + SQLite в томе (или PostgreSQL — POSTGRES_* / DATABASE_URL)
FROM python:3.15-slim
# Системные пакеты базового образа: патчи безопасности Debian выходят раньше, чем пересобирается
# сам образ (Trivy 08.11.2026: два HIGH в zlib1g, исправление deb13u1 уже в репозитории).
# Обновляем только zlib1g — остальной состав образа не двигаем
RUN apt-get update && apt-get install -y --no-install-recommends --only-upgrade zlib1g \
    && rm -rf /var/lib/apt/lists/*
# pip из базового образа несёт вложенные msgpack/urllib3 со старыми версиями (Trivy 08.11.2026:
# CVE-2026-114613, CVE-2026-97687, CVE-2026-97689) — свежий pip приносит исправленные
RUN pip install --no-cache-dir --upgrade pip \
    && rm -f /usr/local/lib/python3.15/site-packages/pip/_vendor/bom.cdx.json
# (SBOM-файл самого pip перечисляет вложенный pkg_resources как «setuptools 70.3.0» — Trivy
#  принимает это за установленный пакет и ловит CVE-2025-47273 (ложное срабатывание, 08.11.2026);
#  файл справочный, pip его не читает)
WORKDIR /srv/timetrack
COPY requirements.txt requirements-postgres.txt requirements.lock.txt ./
# версии — ровно те, что проверены CI (lock как constraints: dev-пакеты в образ не попадают)
RUN pip install --no-cache-dir -r requirements.txt -c requirements.lock.txt
# Драйвер PostgreSQL — обязателен: прод-профилю (docker-compose.prod.yml) он нужен, и сбой
# установки должен ронять сборку, а не всплывать при первом запуске (раньше `|| echo` его глотал)
RUN pip install --no-cache-dir -r requirements-postgres.txt
# setuptools из базового образа не нужен приложению (все пакеты — колёса, ни одна зависимость
# его не импортирует), а его вложенные jaraco.context и wheel — HIGH-уязвимости (Trivy,
# 25.10.2026): убираем, а не обновляем — меньше поверхность и не гонимся за версиями
RUN pip uninstall -y setuptools
COPY app ./app
COPY static ./static
COPY assets ./assets
ENV PYTHONUNBUFFERED=1
# SQLite по умолчанию — в томе data/: раньше файл ложился в рабочую папку и пропадал при
# пересоздании контейнера. Заданный DATABASE_URL или POSTGRES_HOST главнее (app/core/config.py)
ENV SQLITE_PATH=/srv/timetrack/data/timetrack.db
# не от root (OPS-02): данные и бланки — пользователя app; chown до VOLUME, иначе он не сохранится.
# Новые тома получают этого владельца из образа, старые (созданные от root) — deploy/README.md §6
RUN useradd --create-home --uid 10001 app \
    && mkdir -p data templates && chown app:app data templates
USER app
EXPOSE 8000
VOLUME ["/srv/timetrack/data", "/srv/timetrack/templates"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
