from typing import Sequence

from ..types.results import Reason


def build_exceptions(no_receiver: Sequence[Reason]) -> tuple[Reason, ...]:
    """Бизнес-ситуации расчёта часов в стабильном порядке."""
    return tuple(no_receiver)
