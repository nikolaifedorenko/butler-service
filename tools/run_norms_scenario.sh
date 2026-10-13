#!/usr/bin/env bash
# Сценарий норматива «График = 4 слоя» (T1+T3+T4, решения владельца 12.10.2026):
# поднять сервер на свежей демо-БД, пройти пользовательские пути Табеля, Графика
# и словаря смен в jsdom, погасить сервер.
# Использование: tools/run_norms_scenario.sh [порт] [логин]
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PORT="${1:-8195}"
LOGIN="${2:-admin}"
DB="/tmp/norms_scenario.db"
rm -f "$DB" "$DB-wal" "$DB-shm" /tmp/norms_scenario_server.log

cd "$ROOT" || exit 1
export DATABASE_URL="sqlite:///$DB" SECRET_KEY="scenario-secret" APP_TZ="Europe/Moscow" PYTHONPATH="$ROOT"
python3 -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --log-level warning >/tmp/norms_scenario_server.log 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null' EXIT

UP=0
for i in $(seq 1 200); do
  if ! kill -0 $SRV 2>/dev/null; then echo "❌ сервер умер при старте:"; tail -25 /tmp/norms_scenario_server.log; exit 1; fi
  if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$PORT/api/health',timeout=2)" 2>/dev/null; then UP=1; break; fi
  sleep 0.5
done
[ "$UP" = 1 ] || { echo "❌ сервер не ответил за 100 c:"; tail -25 /tmp/norms_scenario_server.log; exit 1; }
echo "сервер на :$PORT готов (сценарий норматива)"

node "$HERE/norms_scenario.mjs" "http://127.0.0.1:$PORT" "$LOGIN"
RC=$?
echo "scenario exit=$RC"
exit $RC
