"""Общие параметры запроса изменяющих операций шахматки (§4.6)."""
from __future__ import annotations

from fastapi import Query

PREVIEW = Query(False, alias="preview", description="Только показать, что изменится, без сохранения")
