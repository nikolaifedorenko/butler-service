def overlap(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Длина пересечения двух полуинтервалов."""
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))
