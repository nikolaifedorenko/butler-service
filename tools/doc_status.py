#!/usr/bin/env python3
"""Статус-заголовки живых документов (карта документации: docs/README.md, правила
жизненного цикла).

Каждый живой `.md` (вне исторических каталогов) обязан в первых строках иметь
`**Статус:**` с допустимым значением. Допустимые статусы: норматив, живая справка,
реализованная спека (дата, PR), черновик, заменён (→ куда), принят ДД.ММ.ГГГГ (ADR),
реестр действующих решений (decisions.md), архив (дата). «Редакция» гейтом не
проверяется: она обязательна для нормативов, спек и реестров, но живые справки
обновляются непрерывно.

Исторические документы описывают структуру на свою дату и не проверяются: архив,
материалы аудита (тот же список, что в tools/doc_links.py).

Использование:
    python3 tools/doc_status.py     # список нарушений; код 1, если они есть (CI)
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HISTORICAL = ("docs/archive/", "docs/audit/")
STATUS_RE = re.compile(r"^\*\*Статус:\*\*\s*(\S.*)$")
ALLOWED = ("норматив", "живая справка", "реализованная спека", "черновик",
           "заменён", "архив", "принят", "реестр действующих решений")
HEAD_LINES = 15


def living_docs() -> list[Path]:
    # только файлы под git: локальные .venv и node_modules не мешают
    out = subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [ROOT / f for f in out.stdout.split() if not f.startswith(HISTORICAL)]


def check(path: Path) -> str | None:
    try:
        head = path.read_text(encoding="utf-8").splitlines()[:HEAD_LINES]
    except UnicodeDecodeError:
        return "файл не читается как UTF-8"
    for line in head:
        m = STATUS_RE.match(line)
        if not m:
            continue
        value = m.group(1).strip()
        if value.lower().startswith(ALLOWED):
            return None
        return f"недопустимый статус: {value!r} (можно: {', '.join(ALLOWED)})"
    return f"нет заголовка **Статус:** в первых {HEAD_LINES} строках"


def main() -> int:
    problems = [(p, err) for p in living_docs() if (err := check(p))]
    if not problems:
        print("✓ статус-заголовки есть во всех живых документах")
        return 0
    for p, err in problems:
        print(f"{p.relative_to(ROOT)}: {err}")
    print(f"\nНайдено нарушений: {len(problems)}. Правила — в docs/README.md.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
