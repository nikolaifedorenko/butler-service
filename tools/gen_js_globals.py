#!/usr/bin/env python3
"""Генератор списка глобальных имён интерфейса для ESLint (правило no-undef).

Зачем: весь фронтенд — обычные скрипты (не ES-модули), поэтому функции и константы
одного файла видны другим через глобальную область. ESLint без списка этих имён
считал бы их «неопределёнными», а со списком начинает ловить настоящие ошибки —
ровно тот класс бага, из-за которого интерфейс показывал пустые разделы:
`navigate()` ссылался на loadNight/loadCars, которых в коде не существовало.

Мост к общей области имён (ADR-0013, раздел 7, шаг 6а): файлы подключаются как ES-модули
(``<script type="module">``), а имена модуля снаружи не видны. Пока разделы не получили явные
``import``/``export``, в конец каждого файла генератор дописывает блок-мост: он публикует
объявления верхнего уровня в ``globalThis``, и остальной код работает, как раньше. Блок
пересобирается этим же скриптом (``--check`` ловит расхождение), а у файла, перешедшего на
``import``/``export``, удаляется целиком.

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
    r"^(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)"
    r"|^(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)"
    r"|^(?:export\s+)?class\s+([A-Za-z_$][\w$]*)",
    re.M,
)


def collect() -> dict[str, str]:
    names: dict[str, str] = {}
    dupes: dict[str, list[str]] = {}
    for js in sorted(JS_DIR.rglob("*.js")):   # рекурсивно: разделы — в js/modules/ (фаза C6)
        rel = js.relative_to(JS_DIR).as_posix()
        text = js.read_text(encoding="utf-8")
        for m in DECL.finditer(text):
            name = next(g for g in m.groups() if g)
            if name in names and names[name] != rel:
                dupes.setdefault(name, [names[name]]).append(rel)
            names.setdefault(name, rel)
    if dupes:
        # const/let с одинаковым именем в двух классических скриптах — это
        # «Identifier has already been declared»: второй файл не выполнится ЦЕЛИКОМ
        details = "".join(f"   {k}: {', '.join(v)}\n" for k, v in sorted(dupes.items()))
        raise SystemExit("✗ одно имя объявлено в нескольких файлах — второй скрипт "
                         "не выполнится целиком (Identifier already declared):\n" + details)
    return dict(sorted(names.items()))


BRIDGE_START = "/* ── мост к общей области имён (генерируется tools/gen_js_globals.py; уйдёт вместе с переходом файла на import/export) ── */"
BRIDGE_END = "/* ── конец моста ── */"
BRIDGE_RE = re.compile(re.escape(BRIDGE_START) + r".*?" + re.escape(BRIDGE_END) + r"\n?", re.S)
DECL_KIND = re.compile(
    r"^(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)"
    r"|^(?:export\s+)?(const|let|var)\s+([A-Za-z_$][\w$]*)"
    r"|^(?:export\s+)?class\s+([A-Za-z_$][\w$]*)",
    re.M,
)


def bridge_block(text: str) -> str:
    """Блок-мост для файла: прямые имена — одним ``Object.assign``, ``let``/``var`` — через
    свойства с геттером и сеттером (присваивание из другого файла должно менять переменную)."""
    direct: list[str] = []
    live: list[str] = []
    for m in DECL_KIND.finditer(BRIDGE_RE.sub("", text)):
        if m.group(1) or m.group(4):
            direct.append(m.group(1) or m.group(4))
        elif m.group(2) in ("let", "var"):
            live.append(m.group(3))
        else:
            direct.append(m.group(3))
    if not direct and not live:
        return ""
    lines = [BRIDGE_START]
    if direct:
        lines.append("Object.assign(globalThis, {\n  " + ",\n  ".join(direct) + ",\n});")
    for name in live:
        lines.append(f"Object.defineProperty(globalThis, '{name}', "
                     f"{{ get: () => {name}, set: (v) => {{ {name} = v; }}, configurable: true }});")
    lines.append(BRIDGE_END)
    return "\n".join(lines) + "\n"


def with_bridge(text: str) -> str:
    body = BRIDGE_RE.sub("", text).rstrip("\n") + "\n"
    block = bridge_block(body)
    return body + ("\n" + block if block else "")


def used_elsewhere(names: dict[str, str]) -> dict[str, list[str]]:
    """Для каждого файла — имена, объявленные в нём, но используемые в ДРУГИХ файлах.

    Нужно для ESLint: no-unused-vars анализирует файл изолированно и считает такие
    имена мёртвыми. Список позволяет не отключать правило целиком — по-настоящему
    неиспользуемые функции (мёртвый код) продолжают находиться.
    """
    texts = {js.relative_to(JS_DIR).as_posix(): js.read_text(encoding="utf-8")
             for js in JS_DIR.rglob("*.js")}
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
    stale = [js for js in sorted(JS_DIR.rglob("*.js"))
             if with_bridge(js.read_text(encoding="utf-8")) != js.read_text(encoding="utf-8")]
    if "--check" in sys.argv:
        if stale:
            print("✗ мост к общей области имён устарел в файлах: "
                  + ", ".join(js.relative_to(JS_DIR).as_posix() for js in stale[:8]))
            print("   Обновите: python3 tools/gen_js_globals.py")
            return 1
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
    for js in stale:
        js.write_text(with_bridge(js.read_text(encoding="utf-8")), encoding="utf-8")
    OUT.write_text(text, encoding="utf-8")
    print(f"✓ tools/js_globals.json: {len(names)} имён из {len(list(JS_DIR.rglob('*.js')))} файлов")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
