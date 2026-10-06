import datetime as dt

from ._tz import zone


def round_moment(t: dt.datetime, step: int, tz: str) -> dt.datetime:
    """Р2: до ближайшего кратного шагу от локальной полуночи; ровно половина — вверх."""
    local = t.astimezone(zone(tz))
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    micros = (local - midnight) // dt.timedelta(microseconds=1)
    q = step * 60_000_000
    rounded = (micros + q // 2) // q * q
    return (midnight + dt.timedelta(microseconds=rounded)).astimezone(dt.timezone.utc)
