"""Ошибки сценариев (не домена): нарушение правил закрытия и пересчёта (7.2)."""


class ApplicationError(Exception):
    code = "APPLICATION_ERROR"


class PeriodAlreadyClosedError(ApplicationError):
    code = "PERIOD_ALREADY_CLOSED"


class PeriodNotClosedError(ApplicationError):
    code = "PERIOD_NOT_CLOSED"


class RecalculationForbiddenError(ApplicationError):
    code = "RECALCULATION_FORBIDDEN"
