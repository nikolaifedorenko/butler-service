from ..settings.types import Settings
from ..types.results import DayCard
from .codes import Codes


def free_capacity(card: DayCard, codes: Codes, st: Settings) -> int:
    """Лимит Т7 − план − Σ размещённых кодов дня."""
    return max(0, st.day_limit_minutes - card.plan_minutes - codes.placed_total(card.day))
