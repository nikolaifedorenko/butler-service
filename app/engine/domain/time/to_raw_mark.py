from ..settings.types import Settings
from ..types.entities import CalcMark, Mark
from .day_of_moment import day_of_moment


def to_raw_mark(mark: Mark, st: Settings) -> CalcMark:
    """Исходное представление в общем протоколе «момент + тип + день» (без округления)."""
    return CalcMark(source=mark, at_calc=mark.at_utc, day=day_of_moment(mark.at_utc, mark.kind, st.tz))
