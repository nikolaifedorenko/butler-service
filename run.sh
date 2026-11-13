#!/usr/bin/env bash
# ───────────────────────────────────────────────────────────────────────────
#  Запуск «Батлер Сервис» (TimeTrack)
#    ./run.sh            — установка зависимостей (при необходимости) + старт
#    ./run.sh --reinstall — принудительно переустановить зависимости
#    PORT=9000 ./run.sh   — другой порт
#
#  Скрипт сам создаёт .venv (через uv), ставит пакеты из uv.lock и проверяет,
#  что приложение действительно запускается. Ошибки пишет по-русски.
# ───────────────────────────────────────────────────────────────────────────
set -u
cd "$(dirname "$0")"
PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
REINSTALL=0
[ "${1:-}" = "--reinstall" ] && REINSTALL=1

say()  { printf '%s\n' "$*"; }
fail() { printf '\n\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# ── 1. uv: ставит нужный Python и зависимости ровно из uv.lock ────────────
command -v uv >/dev/null 2>&1 || fail "Не найден uv. Установите: https://docs.astral.sh/uv/getting-started/installation/  (или: brew install uv)"
[ $REINSTALL -eq 1 ] && rm -rf .venv
say "Проверяю зависимости (uv sync) — первый раз это может занять минуту ..."
uv sync --frozen --no-dev || fail "Зависимости не установились. Проверьте интернет и повторите: uv sync --frozen --no-dev"
PY=.venv/bin/python
say "Python: $($PY -V 2>&1)"

# ── 4.5 SECRET_KEY: создаём .env с надёжным ключом, если его ещё нет ─────────
# Приложение откажется стартовать со слабым ключом (см. app/main.py), поэтому
# при первом запуске генерируем надёжный ключ автоматически — локальный старт
# остаётся «из коробки», но сессии уже нельзя подделать.
if [ ! -f .env ]; then
  say "Создаю .env из .env.example с надёжным SECRET_KEY ..."
  SECRET="$("$PY" -c 'import secrets; print(secrets.token_hex(32))')"
  # ключ Fernet шифрования секретов уведомлений (urlsafe base64 от 32 байт)
  NKEY="$("$PY" -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
  sed -e "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET}|" -e "s|^NOTIFY_SECRET_KEY=.*|NOTIFY_SECRET_KEY=${NKEY}|" \
    .env.example > .env
fi

# ── 5. Контрольная проверка импорта приложения ────────────────────────────
say "Проверяю запуск приложения ..."
if ! "$PY" -c 'import app.main' 2>import_err.txt; then
  sed 's/^/    /' import_err.txt >&2
  rm -f import_err.txt
  fail "Приложение не импортируется. Чаще всего помогает: ./run.sh --reinstall"
fi
rm -f import_err.txt

# ── 6. Старт ──────────────────────────────────────────────────────────────
IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}')
say ""
say "  TimeTrack запущен:"
say "    на этом компьютере : http://127.0.0.1:${PORT}"
[ -n "${IP:-}" ] && say "    в локальной сети   : http://${IP}:${PORT}"
say ""
say "  Остановить — Ctrl+C"
say ""
# локальный запуск — с демо-данными (docs/INSTALL.md); DEMO_SEED=0 — пустая база с ADMIN_PASSWORD
export DEMO_SEED="${DEMO_SEED:-1}"
exec "$PY" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
