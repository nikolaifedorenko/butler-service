#!/usr/bin/env bash
# Сервер для сценариев Playwright: свежая демо-база PostgreSQL и uvicorn на переднем плане.
# Использование: tools/e2e_server.sh [порт]   (запускает playwright.config.mjs; нужен `docker compose up -d db`)
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PORT="${1:-8180}"
cd "$ROOT"
export DEMO_SEED=1 DATABASE_URL="$(python3 "$HERE/scenario_db.py" "e2e")"
# ключ ≥16 символов: приложение отказывается стартовать со слабым SECRET_KEY (app/main.py)
export SECRET_KEY="e2e-secret-key-0123456789abcdef" APP_TZ="Europe/Moscow" PYTHONPATH="$ROOT"
exec python3 -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --log-level warning
