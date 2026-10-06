def available_bank(opening_normalized: int, adjustments: int, credited: int) -> int:
    """4.8: открытие_норм + корректировки + зачислено."""
    return opening_normalized + adjustments + credited
