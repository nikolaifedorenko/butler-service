#!/bin/bash
# ══════════════════════════════════════════════════════════════════
#  TimeTrack — установка на macOS (Apple Silicon и Intel) для теста
#  Запуск:  ./setup_macos.sh          (подготовка окружения)
#           ./run.sh                  (старт сервера)
# ══════════════════════════════════════════════════════════════════
set -e
cd "$(dirname "$0")"

echo "── 1/4 Проверка Python ─────────────────────────────"
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 не найден."
  echo "Установите:  xcode-select --install   (или:  brew install python@3.12)"
  exit 1
fi
OK=$(python3 -c 'import sys; print(1 if sys.version_info[:2] >= (3, 10) else 0)')
if [ "$OK" != "1" ]; then
  echo "Нужен Python 3.10+, у вас: $(python3 --version)."
  echo "Установите свежий:  brew install python@3.12"
  exit 1
fi
echo "OK: $(python3 --version)"

echo "── 2/4 Виртуальное окружение и зависимости ─────────"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  echo "создано .venv"
fi
./.venv/bin/python -m pip install --upgrade --quiet pip
if ! ./.venv/bin/python -m pip install --quiet -r requirements.txt; then
  echo "Не удалось установить зависимости целиком — ставлю по одному пакету ..."
  while read -r pkg; do
    case "$pkg" in ''|'#'*) continue;; esac
    ./.venv/bin/python -m pip install --quiet "$pkg" || echo "  ! не установился: $pkg"
  done < requirements.txt
fi
./.venv/bin/python -c 'import fastapi, uvicorn, sqlalchemy, docx, openpyxl' 2>/dev/null \
  || { echo "ОШИБКА: базовые пакеты не установлены. Проверьте интернет и повторите."; exit 1; }
echo "зависимости установлены"

# PDF-движок — по желанию: без него документы печатаются через DOCX/браузер
if ! command -v soffice >/dev/null 2>&1 \
   && [ ! -x /Applications/LibreOffice.app/Contents/MacOS/soffice ]; then
  echo "Ставлю необязательный PDF-движок (reportlab) ..."
  ./.venv/bin/python -m pip install --quiet -r requirements-pdf.txt \
    && echo "PDF-движок установлен" \
    || echo "  – не установился (бывает на самом новом Python). Не критично:" \
       "    заявления будут скачиваться в DOCX, а печать работает и без PDF." \
       "    Точный PDF даёт LibreOffice:  brew install --cask libreoffice"
fi

echo "── 3/4 Конфигурация .env ───────────────────────────"
if [ ! -f .env ]; then
  cp .env.example .env
  SECRET=$(./.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')
  # меняем SECRET_KEY на случайный (sed с учётом особенностей macOS)
  ./.venv/bin/python - "$SECRET" <<'PY'
import pathlib, sys
secret = sys.argv[1]
p = pathlib.Path(".env")
text = p.read_text()
lines = []
for line in text.splitlines():
    if line.startswith("SECRET_KEY="):
        line = f"SECRET_KEY={secret}"
    lines.append(line)
p.write_text("\n".join(lines) + "\n")
PY
  echo "создан .env со случайным SECRET_KEY"
else
  echo ".env уже есть — оставляю как есть"
fi

echo "── 4/4 Готово ──────────────────────────────────────"
cat <<'EOF'

Запуск сервера:
    ./run.sh
Откройте в браузере:  http://127.0.0.1:8000

Демо-входы (пароль у всех demo1234):
    admin · smirnov · gromova · ivanov · petrov

Тест с iPhone (та же сеть Wi-Fi):
    ipconfig getifaddr en0        # IP мака, например 192.168.1.42
    ./run.sh                      # сервер слушает 0.0.0.0
    на телефоне: http://192.168.1.42:8000  (можно «Поделиться → На экран Домой»)

Сброс демо-данных:  остановите сервер (Ctrl+C) и удалите файл timetrack.db
Остановка:         Ctrl+C в терминале с ./run.sh
EOF
