from ..types import Settings


def check_v7(st: Settings) -> list:
    """В7: все веса Т5 > 0."""
    return [("V7", {"tariff": t, "weight": w}) for t, w in st.weights.items() if w <= 0]
