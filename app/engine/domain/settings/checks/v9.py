from ..types import Settings


def check_v9(st: Settings) -> list:
    """В9: для кода, не несущего часы, плановые часы (окна Т2) не заданы."""
    return [("V9", {"value": key}) for key, w in st.windows.items()
            if w.code in st.day_codes and not st.day_codes[w.code].carries_hours]
