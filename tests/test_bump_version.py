"""tools/bump_version.py (аудит 22.10.2026, UI-04): --check ловит правку оболочки без новой
версии, а ключ вместо версии (`--help`) не записывается в index.html и sw.js."""
from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def tool(tmp_path, monkeypatch):
    shutil.copytree(ROOT / "static", tmp_path / "static")
    spec = importlib.util.spec_from_file_location("bump_version", ROOT / "tools" / "bump_version.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "INDEX", tmp_path / "static" / "index.html")
    monkeypatch.setattr(mod, "SW", tmp_path / "static" / "sw.js")
    monkeypatch.setattr(mod, "ASSETS_DIR", tmp_path / "static")
    return mod


def test_check_catches_js_change_without_bump(tool):
    assert tool.check() == 0
    app_js = tool.ASSETS_DIR / "js" / "app.js"
    app_js.write_text(app_js.read_text(encoding="utf-8") + "\n// правка\n", encoding="utf-8")
    assert tool.check() == 1
    assert tool.bump("2099-01-01a") == 0
    assert tool.check() == 0


def test_flag_is_not_written_as_version(tool, monkeypatch):
    before = tool.SW.read_text(encoding="utf-8")
    for flag in ("--help", "-x"):
        monkeypatch.setattr("sys.argv", ["bump_version.py", flag])
        tool.main()
    assert tool.SW.read_text(encoding="utf-8") == before


def test_new_module_script_is_added_by_bump(tool):
    """Шаг 5.4: файл раздела нового модуля попадает в index.html без ручной правки."""
    (tool.ASSETS_DIR / "js" / "modules" / "zz_probe.js").write_text("'use strict';\n", encoding="utf-8")
    assert tool.check() == 1
    assert tool.bump("2099-01-01a") == 0
    assert '<script src="/static/js/modules/zz_probe.js?v=2099-01-01a"></script>' in \
        tool.INDEX.read_text(encoding="utf-8")
    assert tool.check() == 0
