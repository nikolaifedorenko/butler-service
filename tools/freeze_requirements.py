#!/usr/bin/env python3
"""Пинннинг зависимостей: requirements.lock.txt из установленного окружения.

В requirements*.txt намеренно стоят «>=» (проект ставится на машины заказчика без
интернета/с разными Python), но для воспроизводимой сборки и CI нужен лок-файл.
Скрипт обходит граф зависимостей от корней (requirements.txt, -dev, -pdf) через
метаданные установленных пакетов и фиксирует точные версии.

Использование:
    pip install -r requirements.txt -r requirements-dev.txt -r requirements-pdf.txt
    python3 tools/freeze_requirements.py            # записать requirements.lock.txt
    python3 tools/freeze_requirements.py --check    # сверить с текущим окружением (CI)
"""
from __future__ import annotations

import re
import sys
from importlib import metadata
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ROOTS = ["requirements.txt", "requirements-dev.txt", "requirements-pdf.txt"]
LOCK = BASE / "requirements.lock.txt"
NAME_RE = re.compile(r"^\s*([A-Za-z0-9_.\-\[\]]+)")


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def root_packages() -> list[str]:
    out: list[str] = []
    for rel in ROOTS:
        path = BASE / rel
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            m = NAME_RE.match(line)
            if m:
                out.append(m.group(1).split("[")[0])
    return out


def closure(roots: list[str]) -> dict[str, str]:
    """Все пакеты (корни + транзитивные) → установленная версия."""
    wanted = {canonical(r) for r in roots}
    found: dict[str, str] = {}
    queue = list(wanted)
    while queue:
        name = queue.pop()
        if name in found:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        norm = canonical(dist.metadata["Name"] or name)
        found[norm] = dist.version
        for req in dist.requires or []:
            if "extra ==" in req:            # опциональные extras не тянем
                continue
            if re.search(r"python_version\s*<", req):
                continue
            m = NAME_RE.match(req)
            if m:
                dep = canonical(m.group(1).split("[")[0])
                if dep not in found:
                    queue.append(dep)
    return found


def render(pins: dict[str, str], roots: list[str]) -> str:
    root_set = {canonical(r) for r in roots}
    lines = [
        "# Лок-файл зависимостей (сгенерирован tools/freeze_requirements.py — не править руками).",
        "# Назначение: воспроизводимая сборка в CI и на сервере. В requirements*.txt остаются",
        "# «>=» — для установки на машины с другим Python/ОС; для точной сборки:",
        "#   pip install -r requirements.lock.txt",
        f"# Python {sys.version_info.major}.{sys.version_info.minor}",
        "",
        "# ── прямые зависимости ──",
    ]
    for name in sorted(root_set & set(pins)):
        lines.append(f"{name}=={pins[name]}")
    lines += ["", "# ── транзитивные ──"]
    for name in sorted(set(pins) - root_set):
        lines.append(f"{name}=={pins[name]}")
    return "\n".join(lines) + "\n"


def main() -> int:
    roots = root_packages()
    pins = closure(roots)
    if not pins:
        print("✗ ничего не найдено: сначала установите зависимости (см. README)")
        return 1
    text = render(pins, roots)
    if "--check" in sys.argv:
        if not LOCK.exists():
            print("✗ requirements.lock.txt отсутствует — сгенерируйте: "
                  "python3 tools/freeze_requirements.py")
            return 1
        current = LOCK.read_text(encoding="utf-8")
        cur_pins = dict(re.findall(r"^([A-Za-z0-9_.\-]+)==([\w.]+)$", current, re.M))
        diff = {k for k in set(cur_pins) | set(pins) if cur_pins.get(k) != pins.get(k)}
        if diff:
            print(f"✗ лок-файл расходится с окружением ({len(diff)} пакетов):")
            for k in sorted(diff)[:15]:
                print(f"   {k}: lock={cur_pins.get(k)!r} env={pins.get(k)!r}")
            print("  Обновите: python3 tools/freeze_requirements.py")
            return 1
        print(f"✓ requirements.lock.txt соответствует окружению ({len(pins)} пакетов)")
        return 0
    LOCK.write_text(text, encoding="utf-8")
    print(f"✓ {LOCK.name}: {len(pins)} пакетов "
          f"({len(set(canonical(r) for r in roots) & set(pins))} прямых)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
