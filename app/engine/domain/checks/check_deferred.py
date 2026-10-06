from typing import Sequence

from ..codes_registry.invariant_codes import I13
from ..types.entities import DeferredBlock
from ._fail import fail_if


def check_deferred(blocks: Sequence[DeferredBlock], step: int) -> None:
    """И13: каждый исходящий блок > 0 и кратен шагу."""
    for b in blocks:
        fail_if(b.minutes <= 0 or b.minutes % step, I13, block=b)
