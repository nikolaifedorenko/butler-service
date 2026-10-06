from ..types import Settings


def check_v10(st: Settings) -> list:
    """В10: все границы окон Т2 и категорий Т3 кратны шагу от начала суток."""
    step = st.step_minutes or 1
    bounds = [(k, b) for k, w in st.windows.items() for s in w.segments for b in s]
    bounds += [(c.name, b) for c in st.categories for s in c.segments for b in s]
    return [("V10", {"owner": owner, "minute": b, "step": step}) for owner, b in bounds if b % step]
