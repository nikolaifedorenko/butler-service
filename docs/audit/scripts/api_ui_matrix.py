"""Матрица «API ↔ UI»: какие функции static/js вызывают какие маршруты, и наоборот.

В отличие от tools/check_api_contract.py учитывает конкатенацию ('/api/x/' + id),
номер строки и имя функции-вызывателя, и перечисляет вызовы api()/fetch() с
нелитеральным адресом (их нужно проверить глазами).

    .venv/bin/python docs/audit/scripts/api_ui_matrix.py [--json] > docs/audit/02-api-ui.md
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/audit_routes.db")
os.environ.setdefault("SECRET_KEY", "audit-secret-key-0123456789")

from routes_inventory import collect  # noqa: E402

JS = sorted((ROOT / "static").rglob("*.js")) + [ROOT / "static" / "index.html"]
KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "function", "with"}
LIT = re.compile(r"""(['"`])(/api/(?:(?!\1).)*?)\1(\s*\+)?""")
FUNC = re.compile(r"""(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(|"""
                  r"""(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)|"""
                  r"""^\s*([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{""", re.M)
DYN_CALL = re.compile(r"""\b(api|fetch|multipartApi|downloadBlob|apiBlob)\(\s*(?![\s'"`])([^,)]{1,60})""")


def enclosing(text: str, pos: int) -> str:
    name = "(верхний уровень)"
    for m in FUNC.finditer(text, 0, pos):
        cand = m.group(1) or m.group(2) or m.group(3)
        if cand and cand not in KEYWORDS:
            name = cand
    return name


def calls():
    out = []
    for f in JS:
        text = f.read_text(encoding="utf-8")
        for m in LIT.finditer(text):
            raw, concat = m.group(2), bool(m.group(3))
            norm = re.sub(r"\$\{[^}]*\}", "{}", raw).split("?")[0]
            if concat and not norm.endswith("/"):
                norm += "{}"      # '/api/x/' + id или '/api/x?y=' + v
            elif concat:
                norm += "{}"
            norm = norm.rstrip("/") or "/"
            tail = re.split(r"\bapi\(|downloadBlob\(|multipartApi\(|fetch\(", text[m.end():m.end() + 160])[0]
            mm = re.search(r"method:\s*['\"](\w+)['\"]", tail)
            line = text.count("\n", 0, m.start()) + 1
            out.append({"file": os.path.relpath(f, ROOT), "line": line, "func": enclosing(text, m.start()),
                        "path": norm, "raw": raw, "method": mm.group(1).upper() if mm else "ANY"})
    return out


def dynamic_calls():
    out = []
    for f in JS:
        text = f.read_text(encoding="utf-8")
        for m in DYN_CALL.finditer(text):
            arg = m.group(2).strip()
            if arg.startswith(("/", "'", '"', "`")):
                continue
            line = text.count("\n", 0, m.start()) + 1
            out.append({"file": os.path.relpath(f, ROOT), "line": line, "func": enclosing(text, m.start()),
                        "call": f"{m.group(1)}({arg}"})
    return out


def route_rx(path: str) -> re.Pattern:
    return re.compile("^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(path)) + "$")


def main():
    routes = [r for r in collect() if r["path"].startswith("/api/")]
    for r in routes:
        r["rx"] = route_rx(r["path"])
    cs = calls()
    used: dict[tuple, list] = {}
    unmatched = []
    for c in cs:
        sample = c["path"].replace("{}", "1")
        hits = [r for r in routes if c["method"] in ("ANY", r["method"]) and r["rx"].match(sample)]
        if not hits and "{}" in c["path"]:
            # плейсхолдер мог закрыть несколько сегментов ('/api/x/' + a + '/b') — сверяем по префиксу
            pre = c["path"].split("{}")[0]
            hits = [r for r in routes if c["method"] in ("ANY", r["method"])
                    and re.sub(r"\{[^}]+\}", "1", r["path"]).startswith(pre.replace("{}", "1"))]
            c["prefix_match"] = True
        c["routes"] = [(r["method"], r["path"]) for r in hits]
        if not hits:
            unmatched.append(c)
        for r in hits:
            used.setdefault((r["method"], r["path"]), []).append(c)
    if "--json" in sys.argv:
        print(json.dumps({"calls": cs, "dynamic": dynamic_calls(),
                          "unused": [(r["method"], r["path"], r["file"], r["line"], r["func"]) for r in routes
                                     if (r["method"], r["path"]) not in used]}, ensure_ascii=False, indent=1))
        return
    sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    print("# 02. Матрица «API ↔ UI» (сгенерировано `docs/audit/scripts/api_ui_matrix.py`)\n")
    print(f"Коммит `{sha}`. Литералов `/api/…` в JS: **{len(cs)}**; маршрутов `/api/*`: **{len(routes)}**; "
          f"маршрутов без вызова из JS: **{sum(1 for r in routes if (r['method'], r['path']) not in used)}**; "
          f"литералов без маршрута: **{len(unmatched)}**.\n")
    print("Метод `ANY` — метод не найден рядом с литералом (обычно GET или адрес передаётся дальше). "
          "Сопоставление «по префиксу» (★) — путь собирается конкатенацией, проверено вручную в 12-ui-api.md.\n")
    print("## 2.1. Маршрут → кто вызывает\n")
    print("| Метод | Путь | Обработчик | Вызовы из JS (файл:строка → функция) |")
    print("|---|---|---|---|")
    for r in routes:
        cs_r = used.get((r["method"], r["path"]), [])
        who = "<br>".join(sorted({f"`{c['file'].replace('static/js/', '')}:{c['line']}` → `{c['func']}`"
                                  f"{' ★' if c.get('prefix_match') else ''}" for c in cs_r})) or "**— нет вызовов —**"
        print(f"| {r['method']} | `{r['path']}` | `{r['file'].split('/modules/')[-1]}:{r['line']}` | {who} |")
    print("\n## 2.2. Литералы `/api/…` в JS без маршрута\n")
    if not unmatched:
        print("Нет.\n")
    for c in unmatched:
        print(f"- `{c['file']}:{c['line']}` → `{c['func']}`: `{c['method']} {c['raw']}`")
    print("\n## 2.3. Вызовы с нелитеральным адресом (проверить вручную)\n")
    for d in dynamic_calls():
        print(f"- `{d['file']}:{d['line']}` → `{d['func']}`: `{d['call']}`")


if __name__ == "__main__":
    main()
