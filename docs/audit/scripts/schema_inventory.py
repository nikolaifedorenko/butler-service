"""Таблицы из Base.metadata: модуль-владелец, колонки, FK, unique, индексы.

    .venv/bin/python docs/audit/scripts/schema_inventory.py > docs/audit/04-schema.md
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/audit_routes.db")
os.environ.setdefault("SECRET_KEY", "audit-secret-key-0123456789")

from sqlalchemy import UniqueConstraint  # noqa: E402

from app.bootstrap.registry import ensure_models  # noqa: E402
from app.core.db import Base  # noqa: E402

ensure_models()
owner = {m.class_.__tablename__: (m.class_.__module__, m.class_.__name__) for m in Base.registry.mappers}
sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
tables = Base.metadata.sorted_tables
print("# 04. Модели и схема (сгенерировано `docs/audit/scripts/schema_inventory.py`)\n")
print(f"Коммит `{sha}`. Таблиц в `Base.metadata`: **{len(tables)}**. Сравнение «старая база после миграций "
      "↔ чистая» — в [04b-schema-diff.md](04b-schema-diff.md); шаги миграций — в 15-db-engine.md.\n")
print("| Таблица | Модель (модуль) | Колонок | FK → | Unique | Индексы |")
print("|---|---|---|---|---|---|")
for t in tables:
    mod, cls = owner.get(t.name, ("?", "?"))
    fks = sorted({f"{fk.parent.name}→{fk.column.table.name}" for fk in t.foreign_keys})
    uniq = [",".join(c.name for c in con.columns) for con in t.constraints if isinstance(con, UniqueConstraint)]
    uniq += [c.name for c in t.columns if c.unique]
    idx = sorted(f"{i.name}({','.join(c.name for c in i.columns)})" for i in t.indexes)
    print(f"| `{t.name}` | `{cls}` ({mod.replace('app.', '')}) | {len(t.columns)} | {', '.join(fks) or '—'} | "
          f"{'; '.join(uniq) or '—'} | {', '.join(idx) or '—'} |")
