from ..types.errors import InvariantViolationError


def fail_if(condition: bool, code: str, **data) -> None:
    """Бросить InvariantViolationError(code, data), если условие нарушения выполнено."""
    if condition:
        raise InvariantViolationError(code, data)
