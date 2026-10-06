from ..types import Settings


def check_v5(st: Settings) -> list:
    """В5: для каждой категории и каждого веса определён код УТ из Т5."""
    weights = {1, st.double_weight}
    return [("V5", {"category": c.name, "weight": w}) for c in st.categories for w in sorted(weights)
            if c.tariffs.get(w) not in st.weights]
