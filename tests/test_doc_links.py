"""tools/doc_links.py (аудит, шаг 6.1): ловит несуществующий путь и битую относительную
ссылку, но пропускает внешние ссылки, шаблоны путей и файлы из .gitignore. Файл, который есть
только на диске автора (не под git, как docs/audit/), — тоже битая ссылка: в CI его нет."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_broken_links_are_found_and_exceptions_skipped(tmp_path):
    spec = importlib.util.spec_from_file_location("doc_links", ROOT / "tools" / "doc_links.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    md = ROOT / "docs" / "_doc_links_probe.md"      # внутри репозитория: ссылки считаются от docs/
    local_only = ROOT / "docs" / "_doc_links_local_only.md"
    local_only.write_text("есть только на диске", encoding="utf-8")
    md.write_text(
        "есть: `app/main.py`, [SPEC](SPEC.md), [сайт](https://example.com), `app/modules/<имя>/`\n"
        "из .gitignore: `deploy/backup-ssh/id_ed25519`\n"
        "нет: `app/nope.py` и [старый](archive/nope.md)\n"
        "не под git: [локальный](_doc_links_local_only.md)\n"
        "модули: `app.modules.timesheet.adapters.factory.build_ports`, `app.main:app`, "
        "`app.engine.adapters.factory.build_ports`\n", encoding="utf-8")
    try:
        assert mod.broken(md) == [(3, "app/nope.py"), (3, "archive/nope.md"),
                                  (4, "_doc_links_local_only.md"),
                                  (5, "app.engine.adapters.factory.build_ports")]
    finally:
        md.unlink()
        local_only.unlink()
