#!/usr/bin/env bash
# Сервер для сценариев Playwright: свежая демо-база PostgreSQL и uvicorn на переднем плане.
# Использование: tools/e2e_server.sh [порт]   (запускает playwright.config.mjs; нужен `docker compose up -d db`)
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PORT="${1:-8180}"
cd "$ROOT"
export DEMO_SEED=1 DATABASE_URL="$(python3 "$HERE/scenario_db.py" "e2e")"
# ключ ≥16 символов: приложение отказывается стартовать со слабым SECRET_KEY (app/main.py);
# свой на каждый запуск, в репозитории ключей нет
SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
export SECRET_KEY APP_TZ="Europe/Moscow" PYTHONPATH="$ROOT"
exec python3 -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --log-level warning
