"""Инвентаризация маршрутов: метод, путь, функция, def/async, авторизация, сущности, audit().

Запуск из корня репозитория (код приложения не меняется, БД не трогается):
    DATABASE_URL=sqlite:////tmp/audit_routes.db SECRET_KEY=audit-secret-key-0123456789 \
        .venv/bin/python docs/audit/scripts/routes_inventory.py > docs/audit/01-routes.md
Флаг --json печатает сырые данные (для других скриптов аудита).
"""
from __future__ import annotations

import ast
import inspect
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/audit_routes.db")
os.environ.setdefault("SECRET_KEY", "audit-secret-key-0123456789")

from fastapi.routing import APIRoute  # noqa: E402

from app.core.db import Base  # noqa: E402
from app.main import app  # noqa: E402

MODELS = {m.class_.__name__: m.class_.__tablename__ for m in Base.registry.mappers}
ROLE_MARKERS = ("is_manager", "is_admin", ".role", "impersonated", "can_manage_user",
                "has_perm(", "principal_permissions(", "effective_permissions(")


def dep_auth(dependant) -> list[str]:
    """Механизмы авторизации из дерева зависимостей маршрута."""
    out: list[str] = []
    for d in dependant.dependencies:
        call = d.call
        qn = getattr(call, "__qualname__", "")
        if qn.startswith("require_perm.<locals>"):
            keys = next(c.cell_contents for c in call.__closure__ if isinstance(c.cell_contents, tuple))
            out.append("perm:" + "|".join(keys))
        elif qn in ("current_principal", "optional_principal"):
            out.append(qn)
        else:
            sub = dep_auth(d)
            if sub:
                out.extend(f"{qn}>{s}" for s in sub)
    return out


def func_ast(fn):
    try:
        src = textwrap.dedent(inspect.getsource(fn))
    except (OSError, TypeError):
        return None
    return ast.parse(src)


def scan(fn, depth=0, seen=None):
    """Рекурсивно (до 3 уровней, только функции app.*) ищет audit(), commit, модели, проверки ролей."""
    seen = seen if seen is not None else set()
    key = (getattr(fn, "__module__", ""), getattr(fn, "__qualname__", ""))
    res = {"audit": None, "commit": False, "models": set(), "role": set()}
    if key in seen or not key[0].startswith("app.") or depth > 3:
        return res
    seen.add(key)
    tree = func_ast(fn)
    if tree is None:
        return res
    src = ast.unparse(tree)
    for m in ROLE_MARKERS:
        if m in src and depth == 0:
            res["role"].add(m.strip(".(") )
    g = getattr(fn, "__globals__", {})
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in MODELS:
            res["models"].add(node.id)
        if isinstance(node, ast.Call):
            f = node.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if name == "audit":
                res["audit"] = depth if res["audit"] is None else min(res["audit"], depth)
            if name == "commit":
                res["commit"] = True
            target = g.get(name) if isinstance(f, ast.Name) else None
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                mod = g.get(f.value.id)
                target = getattr(mod, f.attr, None) if inspect.ismodule(mod) else None
            if inspect.isfunction(target):
                sub = scan(target, depth + 1, seen)
                if sub["audit"] is not None:
                    res["audit"] = sub["audit"] if res["audit"] is None else min(res["audit"], sub["audit"])
                res["commit"] |= sub["commit"]
                res["models"] |= sub["models"]
    return res


def flat_routes(routes, prefix=""):
    """FastAPI ≥0.150 хранит include_router как _IncludedRouter — разворачиваем."""
    for r in routes:
        ctx = getattr(r, "include_context", None)
        if ctx is not None:
            assert not ctx.dependencies, "зависимости уровня include_router не учитываются"
            yield from flat_routes(ctx.included_router.routes, prefix + ctx.prefix)
        else:
            yield prefix, r


def collect():
    rows = []
    for prefix, r in flat_routes(app.routes):
        assert not prefix
        if not isinstance(r, APIRoute):
            continue
        fn = r.endpoint
        file = inspect.getsourcefile(fn)
        line = inspect.getsourcelines(fn)[1]
        s = scan(fn)
        for method in sorted(r.methods - {"HEAD"}):
            rows.append({
                "method": method, "path": r.path,
                "file": os.path.relpath(file, ROOT), "line": line, "func": fn.__name__,
                "async": inspect.iscoroutinefunction(fn),
                "auth": dep_auth(r.dependant) or ["нет"],
                "role_checks": sorted(s["role"]),
                "models": sorted(s["models"]),
                "audit": s["audit"], "commit": s["commit"],
                "in_schema": r.include_in_schema,
            })
    return rows


def main():
    rows = collect()
    if "--json" in sys.argv:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return
    print("# 01. Маршруты API (сгенерировано `docs/audit/scripts/routes_inventory.py`)\n")
    print(f"Коммит: `{subprocess.run(['git', '-C', str(ROOT), 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()}`. "
          f"Всего строк «метод + путь»: **{len(rows)}**, уникальных путей: "
          f"**{len({r['path'] for r in rows})}**, `async def`: **{sum(r['async'] for r in rows)}**.\n")
    print("Легенда. **Авторизация**: `perm:a|b` — `require_perm` (хотя бы одно право); "
          "`current_principal` — любой вошедший; `нет` — без входа. **Роль в теле** — в обработчике "
          "встречаются проверки роли/прав вручную (`is_admin`, `.role`, `has_perm`, `can_manage_user`, "
          "`impersonated`). **audit** — глубина вызова `audit()` от обработчика (0 — прямо в нём, "
          "1–3 — во вложенном сервисе; `—` — не найден в пределах 3 уровней). "
          "**Сущности** — ORM-классы, упомянутые в обработчике и вызываемых им функциях app.* (до 3 уровней).\n")
    print("| # | Метод | Путь | Файл:строка → функция | async | Авторизация | Роль в теле | audit | commit | Сущности |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(rows, 1):
        print(f"| {i} | {r['method']} | `{r['path']}` | `{r['file']}:{r['line']}` → `{r['func']}` | "
              f"{'**async**' if r['async'] else 'def'} | {', '.join('`'+a+'`' for a in r['auth'])} | "
              f"{', '.join(r['role_checks']) or ''} | {'—' if r['audit'] is None else r['audit']} | "
              f"{'да' if r['commit'] else ''} | {', '.join(r['models'])} |")


if __name__ == "__main__":
    main()
