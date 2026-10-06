from ..types import Settings


def check_v4(st: Settings) -> list:
    """В4: категории Т3 покрывают сутки без дыр и перекрытий."""
    segs = sorted(s for c in st.categories for s in c.segments)
    cursor, bad = 0, []
    for start, end in segs:
        if start != cursor or end <= start:
            bad.append(("V4", {"at_minute": cursor, "segment": (start, end)}))
        cursor = max(cursor, end)
    return bad + ([("V4", {"at_minute": cursor, "segment": None})] if cursor != 1440 else [])
