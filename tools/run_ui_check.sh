#!/usr/bin/env bash
# Смоук интерфейса: поднять сервер на свежей демо-БД, прогнать все разделы в jsdom,
# погасить сервер. Использование: tools/run_ui_check.sh [порт] [логин] [разделы]
# Нужен jsdom: cd tools && npm install jsdom   (в CI ставится автоматически)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PORT="${1:-8141}"
LOGIN="${2:-gromova}"
VIEWS="${3:-grafik,schedule,marks,fact,timesheet,mgmt,employees,me,night,cars,access,audit,settings}"
DB="/tmp/ui_harness.db"
rm -f "$DB" "$DB-wal" "$DB-shm" /tmp/ui_server.log

cd "$ROOT" || exit 1
# Ключ ≥16 символов: приложение отказывается стартовать со слабым SECRET_KEY (app/main.py).
# CSRF здесь НЕ отключаем: смоук идёт через jsdom и настоящий api() из core.js —
# заодно проверяется вся цепочка double-submit (cookie + заголовок X-CSRF-Token).
export DEMO_SEED=1 DATABASE_URL="sqlite:///$DB" SECRET_KEY="harness-secret-key-0123456789abcdef" APP_TZ="Europe/Moscow" PYTHONPATH="$ROOT"
python3 -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --log-level warning >/tmp/ui_server.log 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null' EXIT

UP=0
for i in $(seq 1 200); do
  if ! kill -0 $SRV 2>/dev/null; then echo "❌ сервер умер при старте:"; tail -25 /tmp/ui_server.log; exit 1; fi
  if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$PORT/api/health',timeout=2)" 2>/dev/null; then UP=1; break; fi
  sleep 0.5
done
[ "$UP" = 1 ] || { echo "❌ сервер не ответил за 100 c:"; tail -25 /tmp/ui_server.log; exit 1; }
echo "сервер на :$PORT готов"

node "$HERE/ui_harness.mjs" "http://127.0.0.1:$PORT" "$LOGIN" "$VIEWS"
RC=$?
echo "harness exit=$RC"
exit $RC
