"""CHK-WEIGHTS-POSITIVE: все веса CFG-WEIGHTS — целые, > 0 (5.3)."""
from __future__ import annotations

from ..types import Settings
from ._violations import Violation

CHK_WEIGHTS_POSITIVE = "CHK-WEIGHTS-POSITIVE"


def check_weights_positive(st: Settings) -> list[Violation]:
    return [(CHK_WEIGHTS_POSITIVE, {"code": code, "weight": w})
            for code, w in st.weights.items() if not isinstance(w, int) or isinstance(w, bool) or w <= 0]
