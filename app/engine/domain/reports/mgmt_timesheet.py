"""build_mgmt_timesheet(cards, codes) — ровно один ключ на каждый день периода; дню без
размещённых кодов — пустой Mapping (3.4, каноническая форма)."""
from __future__ import annotations

import datetime as dt
from typing import Mapping, Sequence

from ..placement.codes import Codes
from ..types.results import DayCard
from .mgmt_row import mgmt_row


def build_mgmt_timesheet(cards: Sequence[DayCard],
                         codes: Codes) -> Mapping[dt.date, Mapping[str, int]]:
    return {card.day: mgmt_row(codes, card.day) for card in cards}
