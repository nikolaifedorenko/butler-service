"""merge_same_blocks(blocks) — объединить блоки с одинаковыми source_day и tariff
(6.3, стадия 8, шаг 2; CFG-PLACEMENT «Объединение блоков»)."""
from __future__ import annotations

from typing import Sequence

from .codes import CodeBlock


def merge_same_blocks(blocks: Sequence[CodeBlock]) -> tuple[CodeBlock, ...]:
    merged: dict[tuple, int] = {}
    for b in blocks:
        merged[(b.source_day, b.tariff)] = merged.get((b.source_day, b.tariff), 0) + b.minutes
    return tuple(CodeBlock(s, t, None, m) for (s, t), m in merged.items())
