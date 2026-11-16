"""Эвристический поиск XSS: интерполяции `${…}` в HTML-шаблонах JS без esc().

Шаблонная строка считается HTML, если в ней есть `<тег`. Интерполяция считается
безопасной, если начинается с известной экранирующей/числовой функции или явно
числовая. Остальное — кандидаты для ручной проверки (поле из БД с текстом
пользователя = уязвимость).

    .venv/bin/python docs/audit/scripts/xss_scan.py
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SAFE = re.compile(r"^\s*(esc|cssColor|hours|hhmm|dateRu|durationRu|plural|withAlpha|textOn|Number|"
                  r"Math\.|encodeURIComponent|JSON\.stringify|fmt\w*|\+|\d|[\w.]+\.length\b|"
                  r"[\w.]+\.(id|count|total|year|month|day|minutes|hours)\s*$|i\s*$|idx\s*$|n\s*$)")


def templates(text: str):
    """Позиции шаблонных литералов верхнего уровня (с учётом вложенных `${ `…` }`)."""
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "'\"":
            j = i + 1
            while j < n and text[j] != ch:
                j += 2 if text[j] == "\\" else 1
            i = j + 1
            continue
        if ch == "/" and text[i:i + 2] == "//":
            i = text.find("\n", i)
            i = n if i < 0 else i
            continue
        if ch == "`":
            start, j, depth = i, i + 1, 0
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j:j + 2] == "${":
                    depth += 1
                    j += 2
                    continue
                if text[j] == "}" and depth:
                    depth -= 1
                elif text[j] == "`" and not depth:
                    break
                j += 1
            yield start, j
            i = j + 1
            continue
        i += 1


def interpolations(lit: str):
    i = 0
    while True:
        k = lit.find("${", i)
        if k < 0:
            return
        depth, j = 1, k + 2
        while j < len(lit) and depth:
            depth += {"{": 1, "}": -1}.get(lit[j], 0)
            j += 1
        yield lit[k + 2:j - 1]
        i = j


def main():
    total = 0
    for f in sorted((ROOT / "static" / "js").rglob("*.js")):
        text = f.read_text(encoding="utf-8")
        for s, e in templates(text):
            lit = text[s:e + 1]
            if not re.search(r"<[a-zA-Z]", lit):
                continue
            for expr in interpolations(lit):
                e1 = " ".join(expr.split())
                if SAFE.match(e1) or "`" in e1 or e1.startswith(("'", '"')):
                    continue
                if re.search(r"\?\s*['\"`]", e1) and not re.search(r"\b\w+\.(name|title|note|comment|text)\b", e1):
                    continue          # тернарник с литералами
                line = text.count("\n", 0, s) + 1 + lit[:lit.find(expr)].count("\n")
                total += 1
                print(f"{f.relative_to(ROOT)}:{line}: ${{{e1[:110]}}}")
    print(f"# кандидатов: {total}")


if __name__ == "__main__":
    main()
