#!/usr/bin/env python3
"""Единая точка версионирования статики (кэш-бастинг).

Версии `?v=…` в index.html и print_page.py и `VERSION`/SHELL в sw.js должны совпадать, иначе
пользователи останутся на старом JS (service worker отдаёт оболочку из кэша).
Раньше версию меняли руками в пяти местах — этот скрипт делает то же одной командой
и умеет проверять согласованность (режим --check, используется в CI).

--check сверяет и содержимое: bump записывает в sw.js хеш css/js оболочки и index.html
(без ?v=), и правка JS без новой версии ловится в CI (UI-04, аудит 22.10.2026).

Список <script> в index.html тоже собирается здесь (шаг 5.4): core.js, app.js и все
static/js/modules/*.js — файл раздела нового модуля подключается без правки index.html.

Использование:
    python3 tools/bump_version.py                 # версия = сегодняшняя дата + буква a
    python3 tools/bump_version.py 2026-10-02b     # задать явно
    python3 tools/bump_version.py --check         # только проверка (для CI)
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
INDEX = BASE / "static" / "index.html"
SW = BASE / "static" / "sw.js"
PRINT_PAGE = BASE / "app" / "modules" / "docs" / "application" / "print_page.py"
ASSETS_DIR = BASE / "static"
PRINT_CHILD = "/static/js/print-page.js"

VERSION_RE = re.compile(r"\?v=([\w.\-]+)")
PRINT_SRC_RE = re.compile(r"""(?P<tag><script\b[^<>]*?\ssrc=(?P<quote>\\?["']))(?P<url>[^"'\\]*)(?P=quote)""")
HASH_RE = re.compile(r"// содержимое оболочки: ([0-9a-f]+)")
SCRIPTS_RE = re.compile(r"(<!-- скрипты:.*?-->\n).*?(<!-- /скрипты -->)", re.S)


def local_assets() -> list[str]:
    """Все локальные css/js из static/, которые нужно кэшировать оболочке.

    Рекурсивно (rglob): разделы живут в static/js/modules/ (фаза C6,
    EXECUTION-SPEC-v2 §6) — нерекурсивный glob оставлял бы PWA без оболочки.
    """
    out = []
    for sub in ("css", "js", "vendor"):
        for p in sorted((ASSETS_DIR / sub).rglob("*")):
            if p.suffix in (".css", ".js"):
                out.append("/static/" + p.relative_to(ASSETS_DIR).as_posix())
    return out


CLASSIC_SCRIPTS = {"/static/js/ui/theme.js", PRINT_CHILD}  # обычные скрипты (не модули): версия — в адресе


def versioned(asset: str) -> bool:
    """Версия ``?v=`` — у стилей и обычных скриптов. Модули подключают друг друга по адресу без версии
    (import ... from './core.js'): адрес с ?v= был бы другим модулем и выполнился бы дважды. Свежесть
    модулей держит ``Cache-Control: no-cache`` у статики (app/main.py) и новая версия кэша sw.js."""
    return asset.endswith(".css") or asset in CLASSIC_SCRIPTS


def shell_url(asset: str, version: str) -> str:
    return f"{asset}?v={version}" if versioned(asset) else asset


def scripts_block(version: str) -> str:
    """Теги <script type="module"> оболочки: ядро, затем файлы разделов. Модули выполняются по
    порядку в документе после разбора страницы; порядок файлов разделов не важен (ADR-0008)."""
    mods = sorted((ASSETS_DIR / "js" / "modules").glob("*.js"))
    srcs = ["js/core.js", "js/app.js"] + [f"js/modules/{p.name}" for p in mods]
    return "".join(f'<script type="module" src="/static/{s}"></script>\n' for s in srcs)


def with_scripts(html: str, version: str) -> str:
    return SCRIPTS_RE.sub(lambda m: m.group(1) + scripts_block(version) + m.group(2), html)


def assets_hash() -> str:
    """Хеш оболочки: ключи и содержимое css/js из SHELL и index.html без значения ?v=."""
    h = hashlib.sha256()
    for a in local_assets():
        h.update(shell_url(a, "").encode())
        h.update((ASSETS_DIR / a.removeprefix("/static/")).read_bytes())
    h.update(VERSION_RE.sub("?v=", INDEX.read_text(encoding="utf-8")).encode())
    return h.hexdigest()[:16]


def current_versions() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
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
    if len(set(all_v)) != 1 or not all(found.values()):
        versions = ", ".join(f"{file}: {sorted(set(values))}" for file, values in found.items())
        problems.append(f"версии расходятся: {versions}")
    print_keys = [asset for asset in shell if asset.partition("?")[0] == PRINT_CHILD]
    version = all_v[0] if all_v else ""
    expected = shell_url(PRINT_CHILD, version)
    renderer = [m["url"] for m in PRINT_SRC_RE.finditer(PRINT_PAGE.read_text(encoding="utf-8"))]
    if renderer != [expected]:
        problems.append("в print_page.py нужен точный адрес скрипта печати с текущей версией")
    if print_keys != [expected]:
        problems.append("в SHELL (sw.js) нужен только ключ скрипта печати с текущей версией")
    if missing:
        problems.append(f"в SHELL (sw.js) нет файлов: {missing}")
    idx = INDEX.read_text(encoding="utf-8")
    if not SCRIPTS_RE.search(idx) or with_scripts(idx, version) != idx:
        problems.append("список <script> в index.html не совпадает с static/js/modules/*.js")
    stamp = HASH_RE.search(SW.read_text(encoding="utf-8"))
    if not stamp or stamp.group(1) != assets_hash():
        problems.append("css/js или index.html изменились после последнего bump — "
                        "без новой версии браузеры останутся на старой оболочке")
    if problems:
        print("✗ Версионирование статики не согласовано:")
        for p in problems:
            print("   -", p)
        print("  Исправление: python3 tools/bump_version.py <дата><буква>")
        return 1
    print(f"✓ Версия статики согласована: {all_v[0]} (файлов в SHELL: {len(shell)})")
    return 0


def bump(version: str) -> int:
    if not re.fullmatch(r"[\w.\-]+", version):
        print(f"✗ Некорректная версия: {version!r} (только буквы, цифры, точка, дефис)")
        return 2

    print_page, n_print = PRINT_SRC_RE.subn(lambda m: m["tag"] + shell_url(PRINT_CHILD, version) + m["quote"],
                                           PRINT_PAGE.read_text(encoding="utf-8"))
    if n_print != 1:
        print("✗ В print_page.py должен быть один адрес скрипта печати")
        return 1

    # 1) index.html: список <script> и все ?v=…
    idx = with_scripts(INDEX.read_text(encoding="utf-8"), version)
    idx_new, n_idx = VERSION_RE.subn(f"?v={version}", idx)
    INDEX.write_text(idx_new, encoding="utf-8")

    # 2) sw.js: VERSION + SHELL (пересобираем список ассетов целиком)
    sw = SW.read_text(encoding="utf-8")
    sw_new = re.sub(r"const VERSION = 'tt-[\w.\-]+'", f"const VERSION = 'tt-{version}'", sw)
    shell_items = ["  '/'"]
    shell_items += [f"  '{shell_url(a, version)}'" for a in local_assets()]
    shell_items += ["  '/manifest.webmanifest'", "  '/static/icons/icon-192.png'",
                    "  '/static/icons/icon-512.png'"]
    block = "const SHELL = [\n" + ",\n".join(shell_items) + ",\n];"
    sw_new, n_shell = re.subn(r"const SHELL = \[.*?\];", block, sw_new, flags=re.S)
    stamp = f"// содержимое оболочки: {assets_hash()}"
    sw_new = HASH_RE.sub(stamp, sw_new) if HASH_RE.search(sw_new) else \
        sw_new.replace("\nconst SHELL = [", f"\n{stamp}\nconst SHELL = [", 1)
    SW.write_text(sw_new, encoding="utf-8")
    PRINT_PAGE.write_text(print_page, encoding="utf-8")

    print(f"✓ Версия статики: {version}")
    print(f"   index.html — замен ?v=: {n_idx}")
    print(f"   sw.js      — VERSION + SHELL ({len(shell_items)} элементов), замен: {n_shell + 1}")
    print(f"   print_page.py — замен адреса скрипта: {n_print}")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--check":
        return check()
    if args and args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if args and args[0].startswith("-"):      # раньше «--help» записывался как версия
        print(f"✗ Неизвестный ключ: {args[0]}\n{__doc__}")
        return 2
    if args:
        return bump(args[0])
    today = dt.date.today().isoformat()
    return bump(f"{today}a")


if __name__ == "__main__":
    raise SystemExit(main())
