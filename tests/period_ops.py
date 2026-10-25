"""Закрытие и пересчёт периода ОДНОМУ сотруднику — для тестов.

API закрывает и пересчитывает период только у всего штата («всё или ничего», решение
владельца 25.10.2026), а тестовая база общая на прогон: сотрудники других тестов
заблокировали бы закрытие. Здесь — те же use case'ы, что вызывает API, напрямую;
ответ в прежнем формате {"done": [...], "errors": [...]}.
"""
from __future__ import annotations


def period_action(kind: str, employee_id: int, year: int, month: int) -> dict:
    from app.core.db import SessionLocal
    from app.modules.timesheet.application.close_period import close_period
    from app.modules.timesheet.application.engine_common import engine_ports, now_utc
    from app.modules.timesheet.application.errors import ApplicationError
    from app.modules.timesheet.application.months import month_period
    from app.modules.timesheet.application.recalculate import recalculate
    from app.modules.timesheet.domain.types.errors import DomainError
    from app.modules.timesheet.interface.formatting import error_text

    action = close_period if kind == "close" else recalculate
    now = now_utc()
    with SessionLocal() as db:
        try:
            view = action(str(employee_id), month_period(year, month), now,
                          engine_ports(db, None, now))
        except (DomainError, ApplicationError, ValueError) as exc:
            db.rollback()
            return {"done": [], "errors": [{"employee_id": employee_id, "error": error_text(exc)}]}
    return {"done": [{"employee_id": employee_id,
                      "bank_closed": round(view.settle.bank_closed_minutes / 60, 2)}], "errors": []}
