from typing import Sequence

from ..codes_registry.invariant_codes import I11, I14
from ..settings.types import Settings
from ..types.results import Cut
from ._fail import fail_if


def check_cascade(need: int, cuts: Sequence[Cut], residual: int, st: Settings) -> None:
    """И14: изъятия целыми гранулами, paid = taken·weight; И11 (частично): need = C + R, R ≥ 0."""
    for c in cuts:
        fail_if(c.taken_minutes <= 0 or c.taken_minutes % st.step_minutes, I14, cut=c)
        fail_if(c.paid_minutes != c.taken_minutes * st.weights[c.tariff], I14, cut=c)
    fail_if(residual < 0 or need != sum(c.paid_minutes for c in cuts) + residual, I11,
            need=need, residual=residual)
