"""Каталоги данных при запуске контейнера не от root (22.10.2026, OPS-02).

* бланки пишутся в templates/ корня проекта — это том compose (после переноса модуля
  20.10.2026 путь съехал в app/modules/docs/templates, и бланки терялись при пересборке);
* каталог без прав на запись (старый том root) останавливает старт понятным текстом.
"""
from __future__ import annotations

from pathlib import Path

import pytest


def test_templates_dir_is_project_templates_volume():
    from app.modules.docs.application.doc_render import TEMPLATES_DIR

    assert Path(__file__).resolve().parents[1] / "templates" == TEMPLATES_DIR


def test_readonly_dir_stops_start_with_hint(monkeypatch):
    from app import main

    main._check_writable_dirs()                          # обычный случай — молча
    monkeypatch.setattr("os.access", lambda path, mode: False)
    with pytest.raises(RuntimeError, match=r"deploy/README\.md §6"):
        main._check_writable_dirs()
