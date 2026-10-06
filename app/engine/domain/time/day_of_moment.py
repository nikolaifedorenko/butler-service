import datetime as dt

from ..types.entities import KIND_OUT
from ._tz import zone


def day_of_moment(t: dt.datetime, kind: str, tz: str) -> dt.date:
    """Правило полуночи: «ушёл» ровно в 00:00 — предыдущий день (= его 24:00)."""
    local = t.astimezone(zone(tz))
    at_midnight = local.time() == dt.time(0, 0)
    return local.date() - dt.timedelta(days=1 if (at_midnight and kind == KIND_OUT) else 0)
