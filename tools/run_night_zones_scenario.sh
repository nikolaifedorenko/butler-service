#!/usr/bin/env bash
# Сценарий ночного обхода v2 (зоны → объекты → чек-листы): поднять сервер на свежей демо-БД, пройти
# путь батлера по уровням обхода в jsdom, погасить сервер.
# Проверяет трёхуровневую навигацию (зоны → объекты → чек-лист), чек-лист зоны,
# индивидуальные правки объекта и справочники.
# Использование: tools/run_night_zones_scenario.sh [порт] [логин]
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PORT="${1:-8144}"
LOGIN="${2:-gromova}"
DB="/tmp/night_zones_scenario.db"
rm -f "$DB" "$DB-wal" "$DB-shm" /tmp/night_zones_scenario_server.log

cd "$ROOT" || exit 1

# Часовой пояс объекта подбираем так, чтобы «сейчас» было ~23:00 — середина ночной
# смены 20:00–08:00. Иначе сценарий работал бы только ночью: днём отчёт текущей
# смены уже закрыт (автозакрытие в 08:00), а будущая смена ещё не создана, и шаг
# «Проверка электрокаров» открывается только для чтения. В CI прогон запускается
# в произвольное время, поэтому пояс вычисляется, а не задаётся константой.
# Etc/GMT±N использует ОБРАТНЫЙ знак: Etc/GMT-5 = UTC+5.
APP_TZ="$(python3 - <<'PY'
import datetime as dt
shift = (23 - dt.datetime.now(dt.timezone.utc).hour) % 24
if shift > 12:
    shift -= 24                       # ближайший эквивалент в диапазоне −12…+12
print("Etc/UTC" if shift == 0 else f"Etc/GMT{-shift:+d}")
PY
)"
export APP_TZ

# Ключ ≥16 символов (см. app/main.py); CSRF отключён, как в других сценариях:
# запросы идут из node без браузерной пары «cookie + заголовок». Сам механизм CSRF
# покрыт tests/test_csrf.py и смоуком интерфейса (run_ui_check.sh).
export DEMO_SEED=1 DATABASE_URL="sqlite:///$DB" SECRET_KEY="scenario-secret-key-0123456789abcdef" CSRF_ENABLED=0 PYTHONPATH="$ROOT"
echo "часовой пояс сценария: $APP_TZ (локальное время ≈ 23:00 — смена идёт)"
python3 -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --log-level warning >/tmp/night_zones_scenario_server.log 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null' EXIT

UP=0
for i in $(seq 1 200); do
  if ! kill -0 $SRV 2>/dev/null; then echo "❌ сервер умер при старте:"; tail -25 /tmp/night_zones_scenario_server.log; exit 1; fi
  if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$PORT/api/health',timeout=2)" 2>/dev/null; then UP=1; break; fi
  sleep 0.5
done
[ "$UP" = 1 ] || { echo "❌ сервер не ответил за 100 c:"; tail -25 /tmp/night_zones_scenario_server.log; exit 1; }
echo "сервер на :$PORT готов (сценарий зон ночного обхода)"

node "$HERE/night_zones_scenario.mjs" "http://127.0.0.1:$PORT" "$LOGIN"
RC=$?
echo "scenario exit=$RC"
exit $RC
