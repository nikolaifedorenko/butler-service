"""Схема «старая SQLite-база после всех миграций» против «чистая база текущего кода».

1. В отдельном git worktree старого коммита (по умолчанию d2e0ea2, 06.10.2026, движок v4)
   выполняется его init_db() на временном файле — это «старая боевая база».
2. На этом же файле выполняется init_db() текущего кода (все migrate_* шаги).
3. На втором временном файле — init_db() текущего кода с нуля.
4. Сравниваются таблицы, колонки (тип, NOT NULL, default), индексы и unique.

    .venv/bin/python docs/audit/scripts/schema_diff.py [old_commit] > docs/audit/04b-schema-diff.md
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PY = sys.executable
TMP = Path(tempfile.mkdtemp(prefix="audit-schema-"))
OLD = sys.argv[1] if len(sys.argv) > 1 else "d2e0ea2"

INIT = ("import os,sys; sys.path.insert(0, os.getcwd()); "
        "from app.main import init_db; init_db()")
DUMP = """
import json, sys
from sqlalchemy import create_engine, inspect
e = create_engine(sys.argv[1]); i = inspect(e); out = {}
for t in sorted(i.get_table_names()):
    out[t] = {
      "columns": {c["name"]: [str(c["type"]), bool(c["nullable"]), str(c.get("default"))] for c in i.get_columns(t)},
      "indexes": sorted([[x["name"], x["column_names"], bool(x["unique"])] for x in i.get_indexes(t)], key=str),
      "unique": sorted([[x["name"], x["column_names"]] for x in i.get_unique_constraints(t)], key=str),
      "fks": sorted([[x["constrained_columns"], x["referred_table"]] for x in i.get_foreign_keys(t)], key=str),
    }
print(json.dumps(out, ensure_ascii=False))
"""


def run(cwd: Path, db: Path, code: str, *args) -> str:
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{db}", SECRET_KEY="audit-secret-key-0123456789",
               NIGHT_SYNC_ENABLED="0", DEMO_SEED="1", PYTHONPATH=str(cwd))
    r = subprocess.run([PY, "-c", code, *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=600)
    if r.returncode:
        raise SystemExit(f"{cwd.name}: {r.stderr[-2000:]}")
    return r.stdout


def main():
    wt = TMP / "old"
    subprocess.run(["git", "-C", str(ROOT), "worktree", "add", "--detach", str(wt), OLD],
                   check=True, capture_output=True)
    try:
        migrated, fresh = TMP / "migrated.db", TMP / "fresh.db"
        run(wt, migrated, INIT)                      # старый код создаёт «боевую» базу
        run(ROOT, migrated, INIT)                    # текущий код мигрирует её
        run(ROOT, fresh, INIT)                       # текущий код с нуля
        a = json.loads(run(ROOT, migrated, DUMP, f"sqlite:///{migrated}"))
        b = json.loads(run(ROOT, fresh, DUMP, f"sqlite:///{fresh}"))
    finally:
        subprocess.run(["git", "-C", str(ROOT), "worktree", "remove", "--force", str(wt)], capture_output=True)
    print(f"# 04b. Схема: старая база `{OLD}` после миграций ↔ чистая база (сгенерировано "
          f"`docs/audit/scripts/schema_diff.py`)\n")
    print("Только SQLite (PostgreSQL не запускался — решение владельца). Тип/NOT NULL/default — "
          "как их видит инспектор SQLAlchemy.\n")
    only_a, only_b = sorted(set(a) - set(b)), sorted(set(b) - set(a))
    print(f"- Таблицы только в мигрированной базе (мусор): {only_a or 'нет'}")
    print(f"- Таблицы только в чистой базе (миграция не создала): {only_b or 'нет'}\n")
    print("| Таблица | Что | Мигрированная | Чистая |")
    print("|---|---|---|---|")
    n = 0
    for t in sorted(set(a) & set(b)):
        ca, cb = a[t]["columns"], b[t]["columns"]
        for col in sorted(set(ca) | set(cb)):
            if ca.get(col) != cb.get(col):
                n += 1
                print(f"| `{t}` | колонка `{col}` | {ca.get(col, '—')} | {cb.get(col, '—')} |")
        for k in ("indexes", "unique", "fks"):
            if a[t][k] != b[t][k]:
                n += 1
                print(f"| `{t}` | {k} | {a[t][k]} | {b[t][k]} |")
    print(f"\n**Расхождений: {n}**")


if __name__ == "__main__":
    main()
