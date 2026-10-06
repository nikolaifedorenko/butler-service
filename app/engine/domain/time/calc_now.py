import datetime as dt

from ..settings.types import Settings
from .round_moment import round_moment


def calc_now(now: dt.datetime, st: Settings) -> dt.datetime:
    """now_calc — то же правило, что для отметок (4.4)."""
    return round_moment(now, st.step_minutes, st.tz)
