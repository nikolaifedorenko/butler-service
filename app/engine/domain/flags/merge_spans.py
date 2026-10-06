from typing import Iterable


def merge_spans(spans: Iterable[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    """Слить пересекающиеся и примыкающие отрезки."""
    out: list[list[int]] = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return tuple((a, b) for a, b in out)
