from ..types import Settings


def check_v2(st: Settings) -> list:
    """В2: длина окна Т2 равна плановым часам значения."""
    return [("V2", {"value": key, "window_minutes": w.length, "plan_minutes": w.plan_minutes})
            for key, w in st.windows.items() if w.length != w.plan_minutes]
