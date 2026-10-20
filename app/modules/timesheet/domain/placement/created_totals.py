"""created_totals(codes) — контрольная сумма физических минут (собственные + входящие)
для INV-MINUTES-CONSERVED (6.3, стадия 6)."""
from __future__ import annotations

from .codes import Codes


def created_totals(codes: Codes) -> int:
    return codes.total()
