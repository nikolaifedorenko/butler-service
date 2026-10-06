from .codes import Codes


def created_totals(codes: Codes) -> int:
    """Контрольная сумма физических минут для И17 (входящие нормализованные + созданные)."""
    return codes.total()
