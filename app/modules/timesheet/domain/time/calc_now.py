"""calc_now(now, st) — now_calc тем же правилом округления, что и отметки (4.4)."""
from __future__ import annotations

import datetime as dt

from ..settings.types import Settings
from .round_moment import round_moment


def calc_now(now: dt.datetime, st: Settings) -> dt.datetime:
    return round_moment(now, st)
