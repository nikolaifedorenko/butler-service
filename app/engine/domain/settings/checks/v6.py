from ..types import Settings


def check_v6(st: Settings) -> list:
    """В6: Т6 содержит все коды Т5, без повторов."""
    ok = sorted(st.cascade_order) == sorted(st.weights) and len(set(st.cascade_order)) == len(st.cascade_order)
    return [] if ok else [("V6", {"cascade": st.cascade_order, "tariffs": tuple(st.weights)})]
