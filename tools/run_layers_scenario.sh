#!/usr/bin/env bash
# Сценарий T5 «График = 4 слоя» (навигация, слои, сетка «Номера»):
# поднять сервер на свежей демо-БД, пройти пользовательские пути в jsdom,
# погасить сервер. Использование: tools/run_layers_scenario.sh [порт] [логин]
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PORT="${1:-8194}"
LOGIN="${2:-admin}"
DB="/tmp/layers_scenario.db"
rm -f "$DB" "$DB-wal" "$DB-shm" /tmp/layers_scenario_server.log

cd "$ROOT" || exit 1
# Ключ ≥16 символов (см. app/main.py); CSRF отключён, как в tests/conftest.py:
# сценарий дёргает API напрямую из node, без браузерной пары «cookie + заголовок».
# Сам механизм CSRF покрыт tests/test_csrf.py и смоуком интерфейса (run_ui_check.sh).
export DEMO_SEED=1 DATABASE_URL="sqlite:///$DB" SECRET_KEY="scenario-secret-key-0123456789abcdef" CSRF_ENABLED=0 APP_TZ="Europe/Moscow" PYTHONPATH="$ROOT"
python3 -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --log-level warning >/tmp/layers_scenario_server.log 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null' EXIT

UP=0
for i in $(seq 1 200); do
  if ! kill -0 $SRV 2>/dev/null; then echo "❌ сервер умер при старте:"; tail -25 /tmp/layers_scenario_server.log; exit 1; fi
  if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$PORT/api/health',timeout=2)" 2>/dev/null; then UP=1; break; fi
  sleep 0.5
done
[ "$UP" = 1 ] || { echo "❌ сервер не ответил за 100 c:"; tail -25 /tmp/layers_scenario_server.log; exit 1; }
echo "сервер на :$PORT готов (сценарий «График = 4 слоя»)"

node "$HERE/layers_scenario.mjs" "http://127.0.0.1:$PORT" "$LOGIN"
RC=$?
echo "scenario exit=$RC"
exit $RC
