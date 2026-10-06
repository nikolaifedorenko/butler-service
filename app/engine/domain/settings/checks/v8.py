from ..types import Settings


def check_v8(st: Settings) -> list:
    """В8: шаг расчёта делит 60 без остатка."""
    ok = st.step_minutes > 0 and 60 % st.step_minutes == 0
    return [] if ok else [("V8", {"step_minutes": st.step_minutes})]
