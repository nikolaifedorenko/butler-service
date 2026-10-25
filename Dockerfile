# Простой контейнер TimeTrack: приложение + SQLite в томе (или PostgreSQL — POSTGRES_* / DATABASE_URL)
FROM python:3.11-slim
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
