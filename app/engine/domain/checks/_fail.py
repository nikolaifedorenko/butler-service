"""Общий выброс нарушения инварианта."""
from __future__ import annotations

from typing import Mapping

from ..types.errors import InvariantViolationError


def fail(code: str, data: Mapping[str, object]) -> None:
    raise InvariantViolationError(code, data)
