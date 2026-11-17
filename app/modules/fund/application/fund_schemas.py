"""Модели ответов fund, которые нужны и другим модулям (публикация версии показывает ту же разницу)."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from app.core.schemas import ApiModel

JsonDict = dict[str, Any]


class DiffEntryOut(ApiModel):
    """Строка разницы фондов: что добавлено, изменено или выведено."""

    id: int
    kind: str
    before: JsonDict
    after: JsonDict
    from_: Optional[list[str]] = Field(None, alias="from")     # у нового объекта — из кого он получился


class FundDiffOut(ApiModel):
    categories: list[DiffEntryOut]
    groups: list[DiffEntryOut]
    units: list[DiffEntryOut]
    flags: list[DiffEntryOut]
