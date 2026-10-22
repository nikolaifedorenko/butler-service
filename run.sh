#!/usr/bin/env bash
# ───────────────────────────────────────────────────────────────────────────
#  Запуск «Батлер Сервис» (TimeTrack)
#    ./run.sh            — установка зависимостей (при необходимости) + старт
#    ./run.sh --reinstall — принудительно переустановить зависимости
#    PORT=9000 ./run.sh   — другой порт
#
#  Скрипт сам создаёт .venv, доустанавливает недостающие пакеты и проверяет,
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

# ── 1. Python ─────────────────────────────────────────────────────────────
PYBIN=""
for c in python3.13 python3.12 python3.11 python3.10 python3 python; do
  if command -v "$c" >/dev/null 2>&1; then
    if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
      PYBIN="$c"; break
    fi
  fi
done
[ -n "$PYBIN" ] || fail "Не найден Python 3.10+ . Установите: https://www.python.org/downloads/  (или: brew install python@3.12)"
say "Python: $($PYBIN -V 2>&1) ($(command -v "$PYBIN"))"

# ── 2. Виртуальное окружение ──────────────────────────────────────────────
if [ ! -x .venv/bin/python ] || [ $REINSTALL -eq 1 ]; then
  say "Создаю виртуальное окружение .venv ..."
  [ $REINSTALL -eq 1 ] && rm -rf .venv
  "$PYBIN" -m venv .venv || fail "Не удалось создать .venv. Попробуйте: $PYBIN -m venv --clear .venv"
fi
PY=.venv/bin/python
"$PY" -m pip install -q --upgrade pip >/dev/null 2>&1 || true

# ── 3. Обязательные зависимости ───────────────────────────────────────────
install_core() { "$PY" -m pip install -q -r requirements.txt; }
# httpx в проверке: транспорт Telegram из requirements.txt; старое venv, созданное
# до переноса httpx в обязательные зависимости, должно дозаказаться само.
if ! "$PY" -c 'import fastapi, uvicorn, sqlalchemy, docx, openpyxl, httpx' 2>/dev/null || [ $REINSTALL -eq 1 ]; then
  say "Устанавливаю зависимости (requirements.txt) — первый раз это может занять минуту ..."
  if ! install_core; then
    say "Обычная установка не удалась, пробую по одному пакету ..."
    ok=1
    while read -r pkg; do
      case "$pkg" in ''|'#'*) continue;; esac
      "$PY" -m pip install -q "$pkg" || { say "  ! не установился: $pkg"; ok=0; }
    done < requirements.txt
    [ $ok -eq 1 ] || fail "Часть пакетов не установилась. Проверьте интернет и повторите: ./.venv/bin/pip install -r requirements.txt"
  fi
fi

# ── 4.5 SECRET_KEY: создаём .env с надёжным ключом, если его ещё нет ─────────
# Приложение откажется стартовать со слабым ключом (см. app/main.py), поэтому
# при первом запуске генерируем надёжный ключ автоматически — локальный старт
# остаётся «из коробки», но сессии уже нельзя подделать.
if [ ! -f .env ]; then
  say "Создаю .env из .env.example с надёжным SECRET_KEY ..."
  SECRET="$("$PY" -c 'import secrets; print(secrets.token_hex(32))')"
  sed "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET}|" .env.example > .env
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
