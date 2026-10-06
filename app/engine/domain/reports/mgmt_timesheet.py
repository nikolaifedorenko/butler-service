import datetime as dt
from typing import Mapping, Sequence

from ..placement.codes import Codes
from ..types.results import DayCard
from .mgmt_row import mgmt_row


def build_mgmt_timesheet(cards: Sequence[DayCard], codes: Codes) -> Mapping[dt.date, Mapping[str, int]]:
    """УТ: итоговые коды по каждому дню периода."""
    return {c.day: mgmt_row(codes, c.day) for c in cards}
