from ..types import Settings


def check_v3(st: Settings) -> list:
    """В3: окно не пустое, начало ≠ конец, границы в пределах суток."""
    return [("V3", {"value": key, "segment": seg}) for key, w in st.windows.items()
            for seg in (w.segments or ((0, 0),)) if not 0 <= seg[0] < seg[1] <= 1440]
