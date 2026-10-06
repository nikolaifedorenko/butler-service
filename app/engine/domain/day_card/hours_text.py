def hours_text(minutes: int) -> str:
    """Часы значения Табеля: 720 → «12», 450 → «7.5» (ключ справочника Т2, не текст для UI)."""
    return str(minutes // 60) if minutes % 60 == 0 else f"{minutes / 60:g}"
