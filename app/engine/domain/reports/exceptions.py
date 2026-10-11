"""build_exceptions(no_receiver_records) — отчёт об исключениях (сигнатура зафиксирована
в v7.1): NO_RECEIVER — единственный код; канонический порядок — по стадии, дате и
порядку тарифов CFG-PLACEMENT (3.4) — уже обеспечен collect_deferred."""
from __future__ import annotations

from typing import Sequence

from ..types.results import Reason


def build_exceptions(no_receiver_records: Sequence[Reason]) -> tuple[Reason, ...]:
    return tuple(no_receiver_records)
