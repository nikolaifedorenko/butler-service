# Простой контейнер TimeTrack: приложение + SQLite в томе
FROM python:3.11-slim
WORKDIR /srv/timetrack
COPY requirements.txt requirements-pdf.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# PDF-движок необязателен: если под этот Python нет готовых сборок — образ всё равно соберётся
RUN pip install --no-cache-dir -r requirements-pdf.txt || echo "PDF-движок не установлен (не критично)"
COPY app ./app
COPY static ./static
COPY assets ./assets
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
VOLUME ["/srv/timetrack/data", "/srv/timetrack/templates"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
