"""pending_blocks(codes) — блоки с placed_day = None (6.3, стадия 8, шаг 1)."""
from __future__ import annotations

from .codes import CodeBlock, Codes


def pending_blocks(codes: Codes) -> tuple[CodeBlock, ...]:
    return tuple(b for b in codes.blocks() if b.placed_day is None)
