#!/usr/bin/env bash
# Снимки интерфейса без браузера: поднять сервер на демо-базе, отрисовать разделы
# настоящим кодом приложения в jsdom, собрать галерею в один самодостаточный HTML.
# Использование: tools/run_snapshot.sh [порт] [файл-результат]
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PORT="${1:-8231}"
OUT="${2:-$ROOT/ui-snapshot.html}"
DB="/tmp/ui_snapshot.db"
rm -f "$DB" "$DB-wal" "$DB-shm"

cd "$ROOT" || exit 1
export DATABASE_URL="sqlite:///$DB" SECRET_KEY="snapshot-secret" APP_TZ="Europe/Moscow" PYTHONPATH="$ROOT"
python3 -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --log-level warning >/tmp/ui_snapshot_server.log 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null' EXIT

for i in $(seq 1 200); do
  if ! kill -0 $SRV 2>/dev/null; then echo "❌ сервер умер при старте:"; tail -20 /tmp/ui_snapshot_server.log; exit 1; fi
  if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$PORT/api/health',timeout=2)" 2>/dev/null; then break; fi
  sleep 0.5
done
echo "сервер на :$PORT готов"

node "$HERE/snapshot.mjs" "http://127.0.0.1:$PORT" "$OUT"
RC=$?
echo "snapshot exit=$RC → $OUT"
exit $RC
