#!/usr/bin/env bash
# Сервер для сценариев Playwright: свежая демо-база PostgreSQL и uvicorn на переднем плане.
# Использование: tools/e2e_server.sh [порт] [имя базы] [night]   (запускает playwright.config.mjs; нужен `docker compose up -d db`)
# night — часовой пояс подбирается так, чтобы «сейчас» было ~23:00: идёт ночная смена 20:00–08:00, и сценарии
# ночного обхода работают в любое время суток (Etc/GMT±N использует ОБРАТНЫЙ знак: Etc/GMT-5 = UTC+5).
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PORT="${1:-8180}"
DB="${2:-e2e}"
MODE="${3:-}"
cd "$ROOT"
export DEMO_SEED=1 DATABASE_URL="$(python3 "$HERE/scenario_db.py" "$DB")"
APP_TZ="Europe/Moscow"
if [ "$MODE" = "night" ]; then
  APP_TZ="$(python3 - <<'PY'
import datetime as dt
shift = (23 - dt.datetime.now(dt.timezone.utc).hour) % 24
if shift > 12:
    shift -= 24
print("Etc/UTC" if shift == 0 else f"Etc/GMT{-shift:+d}")
PY
)"
fi
export APP_TZ PYTHONPATH="$ROOT"
exec python3 -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --log-level warning
