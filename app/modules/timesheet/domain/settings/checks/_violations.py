"""Общий тип нарушения конфигурации: (код проверки, минимальный контекст)."""
from __future__ import annotations

from typing import Mapping

Violation = tuple[str, Mapping[str, object]]
