# Простой контейнер TimeTrack: приложение + SQLite в томе
FROM python:3.11-slim
WORKDIR /srv/timetrack
COPY requirements.txt requirements-pdf.txt requirements-postgres.txt requirements.lock.txt ./
# версии — ровно те, что проверены CI (lock как constraints: dev-пакеты в образ не попадают)
RUN pip install --no-cache-dir -r requirements.txt -c requirements.lock.txt
# PDF-движок необязателен: если под этот Python нет готовых сборок — образ всё равно соберётся
RUN pip install --no-cache-dir -r requirements-pdf.txt -c requirements.lock.txt || echo "PDF-движок не установлен (не критично)"
# Драйвер PostgreSQL: нужен прод-профилю (docker-compose.prod.yml); на SQLite просто не используется
RUN pip install --no-cache-dir -r requirements-postgres.txt || echo "PostgreSQL-драйвер не установлен (SQLite работает без него)"
COPY app ./app
COPY static ./static
COPY assets ./assets
ENV PYTHONUNBUFFERED=1
# не от root (OPS-02): данные и бланки — пользователя app; chown до VOLUME, иначе он не сохранится.
# Новые тома получают этого владельца из образа, старые (созданные от root) — deploy/README.md §6
RUN useradd --create-home --uid 10001 app \
    && mkdir -p data templates && chown app:app data templates
USER app
EXPOSE 8000
VOLUME ["/srv/timetrack/data", "/srv/timetrack/templates"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
