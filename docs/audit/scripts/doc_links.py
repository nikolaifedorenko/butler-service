"""Битые ссылки на файлы в документации: пути вида `app/…`, `docs/…`, `static/…`,
`tools/…`, `tests/…`, `deploy/…` в *.md, которых нет в репозитории.

    .venv/bin/python docs/audit/scripts/doc_links.py
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PATH_RE = re.compile(r"(?<![\w/.-])((?:app|docs|static|tools|tests|deploy|templates|assets)/[\w./\-*{}<>]+)")


def main():
    missing = defaultdict(set)
    for md in sorted(ROOT.rglob("*.md")):
        rel = md.relative_to(ROOT)
        if rel.parts[0] in (".venv", "node_modules") or rel.as_posix().startswith("docs/audit/"):
            continue
        for lineno, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            for m in PATH_RE.finditer(line):
                p = m.group(1).rstrip(".,:;)`'\"")
                if any(ch in p for ch in "*{}<>") or p.endswith("/"):
                    continue
                p = p.split(":")[0].split("#")[0]
                if not (ROOT / p).exists():
                    missing[str(rel)].add((p, lineno))
    total = 0
    for doc, items in sorted(missing.items()):
        print(f"\n## {doc} ({len(items)})")
        for p, ln in sorted(items, key=lambda x: x[1]):
            total += 1
            print(f"- строка {ln}: `{p}`")
    print(f"\n# всего битых ссылок: {total}")


if __name__ == "__main__":
    main()
