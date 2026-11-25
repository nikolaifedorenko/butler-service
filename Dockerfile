# Образ приложения. База — PostgreSQL: адрес задают POSTGRES_* или DATABASE_URL (app/core/config.py)
FROM ghcr.io/astral-sh/uv:0.13.9 AS uv

FROM python:3.15-slim
# Патчи Debian могут выходить до пересборки базового образа. Обновляем пакеты,
# для которых Trivy нашёл доступные исправления: zlib1g и libzstd1 (CVE-2026-124851).
RUN apt-get update && apt-get install -y --no-install-recommends --only-upgrade zlib1g libzstd1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /srv/timetrack
COPY pyproject.toml uv.lock ./
# Зависимости — ровно из uv.lock (версии и хеши пакетов), без dev-группы; ставятся в Python
# образа. Сам uv в образ не попадает: подключается к шагу сборки из своего образа.
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    UV_PROJECT_ENVIRONMENT=/usr/local UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 \
    uv sync --frozen --no-dev
# pip и setuptools из базового образа приложению не нужны, а их вложенные пакеты (msgpack,
# urllib3, jaraco.context, wheel) — постоянный источник HIGH-уязвимостей в отчёте Trivy:
# убираем, а не обновляем — меньше поверхность
RUN pip uninstall -y setuptools pip
COPY app ./app
COPY static ./static
COPY assets/fonts/DejaVuSans-Bold.ttf ./assets/fonts/DejaVuSans-Bold.ttf
ENV PYTHONUNBUFFERED=1
# не от root (OPS-02): загруженные файлы и бланки — пользователя app; chown до VOLUME, иначе он не сохранится.
# Новые тома получают этого владельца из образа, старые (созданные от root) — deploy/README.md §6
RUN useradd --create-home --uid 10001 app \
    && mkdir -p data templates && chown app:app data templates
USER app
EXPOSE 8000
VOLUME ["/srv/timetrack/data", "/srv/timetrack/templates"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
