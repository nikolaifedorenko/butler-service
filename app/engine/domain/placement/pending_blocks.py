from .codes import CodeBlock, Codes


def pending_blocks(codes: Codes) -> tuple[CodeBlock, ...]:
    """Блоки с placed_day = None."""
    return tuple(b for b in codes.blocks() if b.placed_day is None)
