from ..settings.types import Category, Settings


def category_of(minute: int, st: Settings) -> Category:
    """Категория Т3, которой принадлежит минута суток [m, m+1)."""
    return next(c for c in st.categories for a, b in c.segments if a <= minute < b)
