from typing import Sequence

from ..types.results import Reason


def build_trace(*stages: Sequence[Reason]) -> tuple[Reason, ...]:
    """Трассировка в порядке выполнения стадий."""
    return tuple(r for stage in stages for r in stage)
