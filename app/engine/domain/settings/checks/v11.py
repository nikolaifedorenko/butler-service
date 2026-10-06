from ..types import Settings


def check_v11(st: Settings) -> list:
    """В11: порядок тарифов Т9 содержит все коды Т5, без повторов."""
    order = st.placement.tariff_order
    ok = sorted(order) == sorted(st.weights) and len(set(order)) == len(order)
    return [] if ok else [("V11", {"placement": order, "tariffs": tuple(st.weights)})]
