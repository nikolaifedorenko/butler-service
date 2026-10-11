"""TimesheetStorePort поверх tabel_days (16.5): запись строки Табеля. Валидацию записи
выполняет application доменными проверочными функциями (v7.1/F-16); code="" — очистить
ячейку (UI предупреждает о пропусках, расчёт проверяет полноту — RUL-TIMESHEET-COVERS-PERIOD)."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import TabelDay, utcnow
from ._db import emp_pk


class SqlTimesheetStore:
    def __init__(self, db: Session):
        self.db = db

    def save_day(self, employee_id: str, day: dt.date, code: str,
                 plan_minutes: int | None) -> None:
        emp = emp_pk(employee_id)
        row = self.db.scalar(select(TabelDay).where(TabelDay.employee_id == emp,
                                                    TabelDay.date == day))
        if not code:
            if row is not None:
                self.db.delete(row)
            self.db.flush()
            return
        if row is None:
            row = TabelDay(employee_id=emp, date=day)
            self.db.add(row)
        row.code = code
        row.plan_minutes = int(plan_minutes or 0)
        row.source = "manual"
        row.updated_at = utcnow()
        self.db.flush()
