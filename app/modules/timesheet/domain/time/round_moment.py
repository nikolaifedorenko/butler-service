"""round_moment(t, st) — округление момента до ближайшего кратного шагу от локальной
полуночи; ровно половина шага — вверх (вперёд по времени); результат UTC-aware на сетке
(4.5, RUL-ROUND-MOMENTS)."""
from __future__ import annotations

import datetime as dt

from ..settings.types import Settings
from .local_midnight import local_midnight


def round_moment(t: dt.datetime, st: Settings) -> dt.datetime:
    local = t.astimezone(st.tz)
    midnight = local_midnight(local.date(), st.tz)
    step_seconds = st.step_minutes * 60
    whole, rest = divmod(int((local - midnight).total_seconds()), step_seconds)
    grids = whole + 1 if rest * 2 >= step_seconds else whole
    rounded = midnight + dt.timedelta(minutes=grids * st.step_minutes)
    return rounded.astimezone(dt.timezone.utc)
