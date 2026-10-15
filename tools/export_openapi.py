#!/usr/bin/env python3
"""Экспорт/проверка OpenAPI-контракта (docs/openapi.json).

Контракт API — артефакт в репозитории: внешний потребитель видит схему без
поднятия сервера, а CI (--check) ловит незамеченные breaking-изменения —
diff схемы виден прямо в PR.

Использование:
    python3 tools/export_openapi.py           # перезаписать docs/openapi.json
    python3 tools/export_openapi.py --check   # сверить с кодом (CI); 1 = разошёлся

БД и сеть не нужны: схема собирается из маршрутов FastAPI без обращения к БД
(lifespan не запускается, подключение ленивое).
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

# окружение — до импорта app.*: значения ни на что не влияют (схема статична),
# но Settings требует секрет и URL
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.gettempdir()}/openapi_export.db")
os.environ.setdefault("SECRET_KEY", "openapi-export-only-not-a-secret")
os.environ.setdefault("CSRF_ENABLED", "0")

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "docs" / "openapi.json"


def _spec_text() -> str:
    from app.main import app

    spec = app.openapi()
    return json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    text = _spec_text()
    if "--check" in sys.argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print(f"✗ {OUT.relative_to(ROOT)} разошёлся с кодом — схема API изменилась.")
            print("  Обновите: python3 tools/export_openapi.py  (и проверьте diff на breaking-изменения)")
            return 1
        n = len(json.loads(current).get("paths", {}))
        print(f"✓ {OUT.name} актуален ({n} путей)")
        return 0
    OUT.write_text(text, encoding="utf-8")
    n = len(json.loads(text).get("paths", {}))
    print(f"✓ {OUT.relative_to(ROOT)} записан ({n} путей)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
