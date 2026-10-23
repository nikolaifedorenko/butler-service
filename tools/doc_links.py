#!/usr/bin/env python3
"""Битые ссылки в живых документах (шаг 6.1 аудита, DOC-01): пути вида `app/…`, `docs/…`,
`static/…`, `tools/…`, `tests/…`, `deploy/…`, относительные markdown-ссылки `[…](…)` на файлы,
которых нет в репозитории, и точечные пути модулей `app.x.y[.функция]`, которых нет в коде.

Исторические документы описывают структуру на свою дату и не проверяются: архив, материалы
аудита, предложения `PROPOSAL-*`, ADR-0006 (заменён) и ADR-0010 (описывает прежнюю структуру).

Использование:
    python3 tools/doc_links.py      # список битых ссылок; код 1, если они есть (CI)
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HISTORICAL = ("docs/archive/", "docs/audit/", "docs/PROPOSAL-", "docs/superpowers/plans/",
              "docs/adr/0006-", "docs/adr/0010-")
PATH_RE = re.compile(r"(?<![\w/.-])((?:app|docs|static|tools|tests|deploy|templates|assets)/[\w./\-*{}<>]+)")
LINK_RE = re.compile(r"\]\(([^)\s#]+)(?:#[^)]*)?\)")
DOTTED_RE = re.compile(r"(?<![\w/.-])(app(?:\.\w+)+)(?![\w/-])")


def living_docs() -> list[Path]:
    # только файлы под git: локальные .venv и node_modules не мешают
    out = subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [ROOT / f for f in out.stdout.split() if not f.startswith(HISTORICAL)]


def _tracked() -> set[Path]:
    """Файлы под git и их каталоги: локальный незакоммиченный файл (например, docs/audit/)
    в CI отсутствует — ссылка на него битая, хотя у автора проверка прошла бы."""
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    files = {ROOT / f for f in out.stdout.splitlines()}
    return files | {d for f in files for d in f.parents}


TRACKED: set[Path] = set()


def _missing(path: Path) -> bool:
    """Файла нет под git и он не из .gitignore (ключи бэкапа, .env — их создаёт оператор)."""
    if not TRACKED:
        TRACKED.update(_tracked())
    if path.resolve() in TRACKED:
        return False
    # «каталог/» — правило .gitignore для каталога не совпадает с путём без косой черты
    return all(subprocess.run(["git", "check-ignore", "-q", p], cwd=ROOT).returncode != 0
               for p in (str(path), f"{path}/"))


def _module_missing(dotted: str) -> bool:
    """app.a.b.name: самая длинная часть — модуль или пакет под git, после неё — не больше одного
    имени (функция, класс). Так ловятся пути переехавших модулей (`app.engine.…`)."""
    if not TRACKED:
        TRACKED.update(_tracked())
    parts = dotted.split(".")
    for i in range(len(parts), 0, -1):
        base = ROOT.joinpath(*parts[:i])
        if base.with_suffix(".py") in TRACKED or base in TRACKED:
            return len(parts) - i > 1
    return True


def broken(md: Path) -> list[tuple[int, str]]:
    found = []
    for lineno, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
        for m in PATH_RE.finditer(line):
            p = m.group(1).rstrip(".,:;)`'\"")
            if any(ch in p for ch in "*{}<>") or p.endswith("/"):
                continue                              # шаблоны путей вида app/modules/<имя>/
            p = p.split(":")[0].split("#")[0]
            if _missing(ROOT / p):
                found.append((lineno, p))
        for m in DOTTED_RE.finditer(line):
            if _module_missing(m.group(1)):
                found.append((lineno, m.group(1)))
        for m in LINK_RE.finditer(line):
            target = m.group(1)
            if re.match(r"[a-z]+:", target) or target.startswith("/"):
                continue                              # внешние ссылки и маршруты приложения
            if _missing(md.parent / target):
                found.append((lineno, target))
    return found


def main() -> int:
    total = 0
    for md in living_docs():
        for lineno, p in broken(md):
            print(f"{md.relative_to(ROOT)}:{lineno}: {p}")
            total += 1
    if total:
        print(f"✗ битых ссылок в живых документах: {total}")
        return 1
    print("✓ битых ссылок в живых документах нет")
    return 0


if __name__ == "__main__":
    sys.exit(main())
