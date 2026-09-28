#!/usr/bin/env python3
"""Единая точка версионирования статики (кэш-бастинг).

Версия `?v=…` в index.html и `VERSION`/SHELL в sw.js должны совпадать, иначе
пользователи останутся на старом JS (service worker отдаёт оболочку из кэша).
Раньше версию меняли руками в пяти местах — этот скрипт делает то же одной командой
и умеет проверять согласованность (режим --check, используется в CI).

Использование:
    python3 tools/bump_version.py                 # версия = сегодняшняя дата + буква a
    python3 tools/bump_version.py 2026-10-02b     # задать явно
    python3 tools/bump_version.py --check         # только проверка (для CI)
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
INDEX = BASE / "static" / "index.html"
SW = BASE / "static" / "sw.js"
ASSETS_DIR = BASE / "static"

VERSION_RE = re.compile(r"\?v=([\w.\-]+)")


def local_assets() -> list[str]:
    """Все локальные css/js из static/, которые нужно кэшировать оболочке."""
    out = []
    for sub in ("css", "js"):
        for p in sorted((ASSETS_DIR / sub).glob("*")):
            if p.suffix in (".css", ".js"):
                out.append(f"/static/{sub}/{p.name}")
    return out


def current_versions() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {"index.html": [], "sw.js": []}
    found["index.html"] = VERSION_RE.findall(INDEX.read_text(encoding="utf-8"))
    sw = SW.read_text(encoding="utf-8")
    found["sw.js"] = VERSION_RE.findall(sw)
    m = re.search(r"const VERSION = 'tt-([\w.\-]+)'", sw)
    if m:
        found["sw.js"].append(m.group(1))
    return found


def check() -> int:
    found = current_versions()
    all_v = [v for vs in found.values() for v in vs]
    shell = re.findall(r"'(/static/[^']+)'", SW.read_text(encoding="utf-8"))
    shell_plain = [s.split("?v=")[0] for s in shell]
    missing = [a for a in local_assets() if a not in shell_plain]
    problems = []
    if len(set(all_v)) != 1:
        problems.append(f"версии расходятся: {sorted(set(all_v))} "
                        f"(index.html: {sorted(set(found['index.html']))}, "
                        f"sw.js: {sorted(set(found['sw.js']))})")
    if missing:
        problems.append(f"в SHELL (sw.js) нет файлов: {missing}")
    if problems:
        print("✗ Версионирование статики не согласовано:")
        for p in problems:
            print("   -", p)
        print("  Исправление: python3 tools/bump_version.py")
        return 1
    print(f"✓ Версия статики согласована: {all_v[0]} (файлов в SHELL: {len(shell)})")
    return 0


def bump(version: str) -> int:
    if not re.fullmatch(r"[\w.\-]+", version):
        print(f"✗ Некорректная версия: {version!r} (только буквы, цифры, точка, дефис)")
        return 2

    # 1) index.html: все ?v=…
    idx = INDEX.read_text(encoding="utf-8")
    idx_new, n_idx = VERSION_RE.subn(f"?v={version}", idx)
    INDEX.write_text(idx_new, encoding="utf-8")

    # 2) sw.js: VERSION + SHELL (пересобираем список ассетов целиком)
    sw = SW.read_text(encoding="utf-8")
    sw_new = re.sub(r"const VERSION = 'tt-[\w.\-]+'", f"const VERSION = 'tt-{version}'", sw)
    shell_items = ["  '/'"]
    shell_items += [f"  '{a}?v={version}'" for a in local_assets()]
    shell_items += ["  '/manifest.webmanifest'", "  '/static/icons/icon-192.png'",
                    "  '/static/icons/icon-512.png'"]
    block = "const SHELL = [\n" + ",\n".join(shell_items) + ",\n];"
    sw_new, n_shell = re.subn(r"const SHELL = \[.*?\];", block, sw_new, flags=re.S)
    SW.write_text(sw_new, encoding="utf-8")

    print(f"✓ Версия статики: {version}")
    print(f"   index.html — замен ?v=: {n_idx}")
    print(f"   sw.js      — VERSION + SHELL ({len(shell_items)} элементов), замен: {n_shell + 1}")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--check":
        return check()
    if args:
        return bump(args[0])
    today = dt.date.today().isoformat()
    return bump(f"{today}a")


if __name__ == "__main__":
    raise SystemExit(main())
