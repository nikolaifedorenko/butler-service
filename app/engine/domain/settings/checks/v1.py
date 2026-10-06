from ..types import Settings


def check_v1(st: Settings) -> list:
    """В1: каждое значение Табеля, несущее часы, имеет строку в Т2 (на уровне справочника —
    у каждого кода с часами есть хотя бы одно окно; конкретные значения дня — в settle())."""
    with_windows = {w.code for w in st.windows.values()}
    return [("V1", {"code": c}) for c, p in st.day_codes.items()
            if p.carries_hours and c not in with_windows]
