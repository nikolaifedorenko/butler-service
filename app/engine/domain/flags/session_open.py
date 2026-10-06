import datetime as dt

from ..codes_registry.flag_codes import SESSION_OPEN
from ..types.results import Flag


def session_open_flag(day: dt.date, open_since: dt.datetime | None) -> Flag | None:
    """SESSION_OPEN на день day, если на исходный now сессия открыта."""
    return Flag(day, SESSION_OPEN, {"open_since": open_since}) if open_since else None
