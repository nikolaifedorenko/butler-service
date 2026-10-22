#!/usr/bin/env python3
"""Контракты .importlinter, которые зависят от списка модулей (шаг 5.4 аудита, ADR-0012).

Модули — пакеты app/modules/*/ с manifest.py. Всё ниже маркера в .importlinter генерируется:
изоляция эталона notify (не импортирует другие модули вовсе) и R3 — приватные
domain/adapters/interface каждого модуля. Новый модуль попадает в контракты без ручной правки.

Использование:
    python3 tools/gen_importlinter.py           # перезаписать сгенерированную часть
    python3 tools/gen_importlinter.py --check   # только проверка (CI); 1 — файл устарел
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / ".importlinter"
MARKER = "; ── ниже — генерирует tools/gen_importlinter.py из app/modules/*/manifest.py, руками не править ──\n"
ISOLATED = ("notify",)          # эталон C3: модуль не знает ни composition root, ни другие модули


def modules() -> list[str]:
    return sorted(p.parent.name for p in (ROOT / "app" / "modules").glob("*/manifest.py"))


def _list(names) -> str:
    return "".join(f"    {n}\n" for n in names)


def generated(mods: list[str]) -> str:
    out = []
    for m in ISOLATED:
        out.append(f"[importlinter:contract:{m}-isolation]\n"
                   f"name = Эталон (C3): {m} не знает про composition root и другие модули\n"
                   f"type = forbidden\nsource_modules =\n{_list([f'app.modules.{m}'])}"
                   f"forbidden_modules =\n{_list(['app.bootstrap', 'app.main'])}"
                   f"{_list(f'app.modules.{o}' for o in mods if o != m)}"
                   "allow_indirect_imports = True\n")
    for m in mods:
        out.append(f"[importlinter:contract:{m}-private]\n"
                   f"name = R3: domain/adapters/interface {m} приватны\n"
                   f"type = forbidden\nsource_modules =\n"
                   f"{_list(f'app.modules.{o}' for o in mods if o != m)}"
                   f"forbidden_modules =\n"
                   f"{_list(f'app.modules.{m}.{layer}' for layer in ('domain', 'adapters', 'interface'))}"
                   "allow_indirect_imports = True\n")
    return "\n".join(out)


def main() -> int:
    text = CONFIG.read_text(encoding="utf-8")
    if MARKER not in text:
        print(f"✗ В {CONFIG.name} нет маркера сгенерированной части")
        return 1
    new = text.split(MARKER)[0] + MARKER + "\n" + generated(modules())
    if sys.argv[1:] == ["--check"]:
        if new != text:
            print("✗ .importlinter не совпадает со списком модулей. "
                  "Исправление: python3 tools/gen_importlinter.py")
            return 1
        print(f"✓ .importlinter согласован с модулями ({len(modules())})")
        return 0
    CONFIG.write_text(new, encoding="utf-8")
    print(f"✓ .importlinter: контракты для {len(modules())} модулей")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
