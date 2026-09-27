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
if ! "$PY" -c 'import fastapi, uvicorn, sqlalchemy, docx, openpyxl' 2>/dev/null || [ $REINSTALL -eq 1 ]; then
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
# bcrypt — желателен, но не критичен (есть запасной pbkdf2-sha256)
"$PY" -c 'import bcrypt' 2>/dev/null || "$PY" -m pip install -q bcrypt passlib 2>/dev/null \
  || say "  (bcrypt не установился — пароли будут на pbkdf2-sha256, это нормально)"

# ── 4. Необязательный PDF-движок (не блокирует запуск) ────────────────────
# PDF=off ./run.sh — вообще не пытаться ставить PDF-движок (быстрый старт)
PDF_TRIED=.venv/.pdf-tried
if [ "${PDF:-auto}" != "off" ] && [ ! -f "$PDF_TRIED" ] \
   && ! "$PY" -c 'import reportlab' 2>/dev/null \
   && ! command -v soffice >/dev/null 2>&1 \
   && [ ! -x /Applications/LibreOffice.app/Contents/MacOS/soffice ]; then
  say "Пробую поставить необязательный PDF-движок (reportlab) — один раз, без него тоже всё работает ..."
  if "$PY" -m pip install -q -r requirements-pdf.txt 2>/dev/null; then
    say "  ✓ PDF-движок установлен"
  else
    say "  – не установился (на новом Python это бывает): документы будут печататься через DOCX/браузер"
  fi
  touch "$PDF_TRIED"   # больше не повторяем попытку при каждом запуске
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
exec "$PY" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
