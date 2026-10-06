from ..settings.types import Settings
from ..types.entities import CalcMark, Mark
from .day_of_moment import day_of_moment
from .round_moment import round_moment


def to_calc_mark(mark: Mark, st: Settings) -> CalcMark:
    """Округлить момент, затем определить расчётный день по округлённому моменту (4.5)."""
    at = round_moment(mark.at_utc, st.step_minutes, st.tz)
    return CalcMark(source=mark, at_calc=at, day=day_of_moment(at, mark.kind, st.tz))
