"""sacrifice_order(codes, st) — порядок обхода каскада (6.3, стадия 11): тарифы по
CFG-CASCADE; внутри тарифа — по source_day; затем по placed_day (размещённые по
возрастанию даты, неразмещённые последними). Размещённые и неразмещённые участвуют
на равных."""
from __future__ import annotations

import datetime as dt

from ..placement.codes import CodeBlock, Codes
from ..settings.types import Settings


def sacrifice_order(codes: Codes, st: Settings) -> tuple[CodeBlock, ...]:
    order = {t: i for i, t in enumerate(st.cascade_order)}
    last = dt.date.max
    return tuple(sorted(codes.blocks(), key=lambda b: (order.get(b.tariff, len(order)),
                                                       b.source_day, b.placed_day or last)))
