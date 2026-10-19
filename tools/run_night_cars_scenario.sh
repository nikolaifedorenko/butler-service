#!/usr/bin/env bash
# Сценарий шага «Проверка электрокаров»: поднять сервер на свежей демо-БД, создать
# открытый отчёт текущей смены, пройти путь батлера в jsdom, погасить сервер.
# Проверяет, что окно ночной отметки кара совпадает с окном возврата кара
# (чекбоксы состояния, место списком, фото) и что отметка с фото сохраняется.
# Использование: tools/run_night_cars_scenario.sh [порт] [логин]
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PORT="${1:-8143}"
LOGIN="${2:-gromova}"
DB="/tmp/night_cars_scenario.db"
rm -f "$DB" "$DB-wal" "$DB-shm" /tmp/night_cars_scenario_server.log

cd "$ROOT" || exit 1
# Ключ ≥16 символов (см. app/main.py); CSRF отключён, как в других сценариях:
# запросы идут из node без браузерной пары «cookie + заголовок». Сам механизм CSRF
# покрыт tests/test_csrf.py и смоуком интерфейса (run_ui_check.sh).
export DATABASE_URL="sqlite:///$DB" SECRET_KEY="scenario-secret-key-0123456789abcdef" CSRF_ENABLED=0 APP_TZ="Europe/Moscow" PYTHONPATH="$ROOT"
python3 -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --log-level warning >/tmp/night_cars_scenario_server.log 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null' EXIT

UP=0
for i in $(seq 1 200); do
  if ! kill -0 $SRV 2>/dev/null; then echo "❌ сервер умер при старте:"; tail -25 /tmp/night_cars_scenario_server.log; exit 1; fi
  if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$PORT/api/health',timeout=2)" 2>/dev/null; then UP=1; break; fi
  sleep 0.5
done
[ "$UP" = 1 ] || { echo "❌ сервер не ответил за 100 c:"; tail -25 /tmp/night_cars_scenario_server.log; exit 1; }
echo "сервер на :$PORT готов (сценарий обхода электрокаров)"

# Отчёт текущей смены. ensure_report() не создаёт смену раньше 20:00 (батлеры не
# должны видеть «будущий» отчёт днём), а сценарий обязан работать в любое время
# суток — в CI он запускается днём. Поэтому «сейчас» на время создания сдвигаем
# внутрь смены (23:00 даты смены): тот же приём, что и в тестах с freezegun.
python3 - <<'PY' || { echo "❌ не удалось создать отчёт смены"; tail -25 /tmp/night_cars_scenario_server.log; exit 1; }
import datetime as dt
import time

from app import night
from app.db import SessionLocal

db = SessionLocal()
try:
    real_now = night.now_local
    shift_d = night.current_shift_date()
    rep = None
    for attempt in range(5):          # сервер держит соединение — ждём освобождения БД
        try:
            night.now_local = lambda: dt.datetime.combine(shift_d, dt.time(23, 0))
            rep = night.ensure_report(db, shift_d)
            break
        except Exception as e:        # noqa: BLE001 — «database is locked» и прочее
            db.rollback()
            if attempt == 4:
                raise
            time.sleep(0.4)
        finally:
            night.now_local = real_now
    assert rep is not None, "отчёт смены не создан"
    print(f"отчёт ночной смены: id={rep.id} от {shift_d} (статус {rep.status})")
finally:
    db.close()
PY

node "$HERE/night_cars_scenario.mjs" "http://127.0.0.1:$PORT" "$LOGIN"
RC=$?
echo "scenario exit=$RC"
exit $RC
