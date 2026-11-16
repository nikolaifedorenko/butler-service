"""Матрица «право ↔ маршрут ↔ элемент UI» + проверки по РОЛИ (а не праву) в бэке и фронте.

    .venv/bin/python docs/audit/scripts/perm_matrix.py > docs/audit/03-perm-matrix.md
"""
from __future__ import annotations

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

from app.core.permissions import PERMISSIONS, ROLE_DEFAULTS  # noqa: E402

JS = sorted((ROOT / "static" / "js").rglob("*.js"))
ROLE_JS = re.compile(r"role\s*[!=]==?\s*['\"]\w+['\"]|\.is_manager|isManager|\.is_admin")
ROLE_PY = re.compile(r"principal\.role\b|\.is_manager\b|\.is_admin\b")


def js_uses(key: str) -> list[str]:
    out = []
    for f in JS:
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"['\"]" + re.escape(key) + r"['\"]", line):
                out.append(f"`{f.relative_to(ROOT / 'static' / 'js')}:{i}`")
    return out


def main():
    rows = collect()
    sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    print("# 03. Матрица «право ↔ маршрут ↔ UI» (сгенерировано `docs/audit/scripts/perm_matrix.py`)\n")
    print(f"Коммит `{sha}`. Источник прав — `app/core/permissions.py` (`PERMISSIONS`, `ROLE_DEFAULTS`). "
          "«UI» — строки JS, где ключ права встречается литералом (обычно `can('…')`, реестр экранов "
          "настроек или пунктов меню).\n")
    print("| Право | admin | manager | supervisor | employee | Маршруты (метод путь) | UI (файл:строка) |")
    print("|---|---|---|---|---|---|---|")
    unused = []
    for p in PERMISSIONS:
        k = p["key"]
        rs = [f"{r['method']} `{r['path']}`" for r in rows if any(a == f"perm:{k}" or
              (a.startswith("perm:") and k in a[5:].split("|")) for a in r["auth"])]
        ui = js_uses(k)
        if not rs and not ui:
            unused.append(k)
        roles = ["✔" if k in ROLE_DEFAULTS[r] else "" for r in ("admin", "manager", "supervisor", "employee")]
        print(f"| `{k}` — {p['title']} | " + " | ".join(roles) +
              f" | {'<br>'.join(rs) or '—'} | "
              f"{', '.join(ui) or '—'} |")
    print("\nПраво без маршрута и без UI: " + (", ".join(f"`{k}`" for k in unused) or "нет") + "\n")
    print("## Маршруты без права (только вход или вообще без входа)\n")
    for r in rows:
        if not any(a.startswith("perm:") for a in r["auth"]) and r["path"].startswith("/api/"):
            print(f"- {r['method']} `{r['path']}` — `{', '.join(r['auth'])}` — `{r['file']}:{r['line']}`")
    print("\n## Проверки по РОЛИ, а не по праву: бэкенд\n")
    for f in sorted((ROOT / "app").rglob("*.py")):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if ROLE_PY.search(line) and not line.strip().startswith("#") and "def " not in line \
                    and "core/auth.py" not in str(f) and "auth_guards.py" not in str(f):
                print(f"- `{f.relative_to(ROOT)}:{i}`: `{line.strip()[:120]}`")
    print("\n## Проверки по РОЛИ, а не по праву: фронтенд\n")
    for f in JS:
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if ROLE_JS.search(line) and not line.strip().startswith(("//", "/*", "*")):
                print(f"- `{f.relative_to(ROOT)}:{i}`: `{line.strip()[:120]}`")


if __name__ == "__main__":
    main()
