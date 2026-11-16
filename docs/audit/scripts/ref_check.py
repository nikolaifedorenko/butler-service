"""Проверка ссылок `путь:строки` в docs/audit/*.md: файл существует, строки в пределах файла.

Короткие имена (`night_api.py:948`) сопоставляются с единственным файлом репозитория с таким
именем; неоднозначные и ненайденные печатаются.

    .venv/bin/python docs/audit/scripts/ref_check.py
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REF = re.compile(r"`?([\w./-]+\.(?:py|js|md|yml|conf|json|html|txt|toml|mjs|sh))`?:(\d+)(?:-(\d+))?((?:,\d+(?:-\d+)?)*)")
FILES = [p for p in ROOT.rglob("*") if p.is_file() and ".venv" not in p.parts and ".git" not in p.parts
         and "node_modules" not in p.parts]
BY_NAME: dict[str, list[Path]] = {}
for p in FILES:
    BY_NAME.setdefault(p.name, []).append(p)


def resolve(name: str) -> list[Path]:
    direct = ROOT / name
    if direct.is_file():
        return [direct]
    cands = [p for p in BY_NAME.get(Path(name).name, []) if str(p).endswith(name)]
    return cands


def main():
    bad = ok = 0
    for md in sorted((ROOT / "docs" / "audit").glob("*.md")):
        for lineno, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            for m in REF.finditer(line):
                name, a, b, rest = m.group(1), int(m.group(2)), m.group(3), m.group(4)
                nums = [a] + ([int(b)] if b else []) + [int(x) for x in re.findall(r"\d+", rest or "")]
                cands = resolve(name)
                if len(cands) != 1:
                    if name.startswith(("app/", "static/", "tests/", "tools/", "docs/", "deploy/")) or cands:
                        print(f"{md.name}:{lineno}: `{name}` — {'не найден' if not cands else 'неоднозначно: ' + ', '.join(str(c.relative_to(ROOT)) for c in cands[:3])}")
                        bad += 1
                    continue
                n = sum(1 for _ in cands[0].open(encoding="utf-8", errors="ignore"))
                if max(nums) > n:
                    print(f"{md.name}:{lineno}: `{name}:{max(nums)}` — в файле {n} строк")
                    bad += 1
                else:
                    ok += 1
    print(f"# ссылок проверено: {ok}, проблем: {bad}")


if __name__ == "__main__":
    main()
