#!/usr/bin/env python3
"""Генератор списка глобальных имён интерфейса для ESLint (правило no-undef).

Зачем: весь фронтенд — обычные скрипты (не ES-модули), поэтому функции и константы
одного файла видны другим через глобальную область. ESLint без списка этих имён
считал бы их «неопределёнными», а со списком начинает ловить настоящие ошибки —
ровно тот класс бага, из-за которого интерфейс показывал пустые разделы:
`navigate()` ссылался на loadNight/loadCars, которых в коде не существовало.

Список генерируется, а не пишется руками:
    python3 tools/gen_js_globals.py           # записать tools/js_globals.json
    python3 tools/gen_js_globals.py --check   # сверить с файлом (для CI)
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

BASE = pathlib.Path(__file__).resolve().parent.parent
JS_DIR = BASE / "static" / "js"
OUT = pathlib.Path(__file__).resolve().parent / "js_globals.json"

# объявления верхнего уровня: function/async function/const/let/var/class
DECL = re.compile(
    r"^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)"
    r"|^(?:const|let|var)\s+([A-Za-z_$][\w$]*)"
    r"|^class\s+([A-Za-z_$][\w$]*)",
    re.M,
)


def collect() -> dict[str, str]:
    names: dict[str, str] = {}
    dupes: dict[str, list[str]] = {}
    for js in sorted(JS_DIR.glob("*.js")):
        text = js.read_text(encoding="utf-8")
        for m in DECL.finditer(text):
            name = next(g for g in m.groups() if g)
            if name in names and names[name] != js.name:
                dupes.setdefault(name, [names[name]]).append(js.name)
            names.setdefault(name, js.name)
    if dupes:
        # const/let с одинаковым именем в двух классических скриптах — это
        # «Identifier has already been declared»: второй файл не выполнится ЦЕЛИКОМ
        details = "".join(f"   {k}: {', '.join(v)}\n" for k, v in sorted(dupes.items()))
        raise SystemExit("✗ одно имя объявлено в нескольких файлах — второй скрипт "
                         "не выполнится целиком (Identifier already declared):\n" + details)
    return dict(sorted(names.items()))


def used_elsewhere(names: dict[str, str]) -> dict[str, list[str]]:
    """Для каждого файла — имена, объявленные в нём, но используемые в ДРУГИХ файлах.

    Нужно для ESLint: no-unused-vars анализирует файл изолированно и считает такие
    имена мёртвыми. Список позволяет не отключать правило целиком — по-настоящему
    неиспользуемые функции (мёртвый код) продолжают находиться.
    """
    texts = {js.name: js.read_text(encoding="utf-8") for js in JS_DIR.glob("*.js")}
    out: dict[str, list[str]] = {fname: [] for fname in texts}
    for name, owner in names.items():
        pattern = re.compile(r"(?<![\w$.])" + re.escape(name) + r"(?![\w$])")
        for fname, text in texts.items():
            if fname == owner:
                continue
            if pattern.search(text):
                out[owner].append(name)
                break
    return {k: sorted(v) for k, v in sorted(out.items())}


def main() -> int:
    names = collect()
    payload = {
        "_comment": "Сгенерировано tools/gen_js_globals.py — не править руками. "
                    "Глобальные имена интерфейса для ESLint (no-undef) и списки "
                    "имён, используемых между файлами (no-unused-vars).",
        "globals": {name: "readonly" for name in names},
        "by_file": names,
        "used_elsewhere": used_elsewhere(names),
    }
    text = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
    if "--check" in sys.argv:
        if not OUT.exists():
            print("✗ tools/js_globals.json отсутствует — сгенерируйте: "
                  "python3 tools/gen_js_globals.py")
            return 1
        current = OUT.read_text(encoding="utf-8")
        if current != text:
            old = json.loads(current).get("by_file", {})
            added = sorted(set(names) - set(old))
            removed = sorted(set(old) - set(names))
            print("✗ список глобальных имён разошёлся с кодом")
            if added:
                print("   добавились:", ", ".join(added[:12]))
            if removed:
                print("   исчезли:", ", ".join(removed[:12]))
            print("   Обновите: python3 tools/gen_js_globals.py")
            return 1
        print(f"✓ js_globals.json актуален ({len(names)} имён)")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"✓ tools/js_globals.json: {len(names)} имён из {len(list(JS_DIR.glob('*.js')))} файлов")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
