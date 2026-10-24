"""Примечание при внесении в Табель на диапазон (рецензия аудита 22.10.2026, P2).

Модалка ячейки всегда показывает «Примечание», но при «до числа» запрос шёл в
/api/tabel/bulk без него, а в BulkIn поля не было — текст молча пропадал. Как у одиночной
ячейки: непустое примечание записывается в каждую ячейку, пустое существующие не трогает.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, select

DAYS = [dt.date(2029, 5, d) for d in (7, 8, 9)]


def test_bulk_writes_note_to_every_cell(admin_client, db):
    from app.modules.employees.application import Employee
    from app.modules.timesheet.adapters.orm import TabelDay

    emp = next(e for e in db.scalars(select(Employee)) if "Иванов" in e.display_name)
    body = {"employee_ids": [emp.id], "dates": [d.isoformat() for d in DAYS], "code": "В"}
    try:
        r = admin_client.post("/api/tabel/bulk", json=body | {"note": "письмо C&B №12"})
        assert r.status_code == 200 and r.json()["ok"], r.text
        notes = lambda: [db.scalar(select(TabelDay.note).where(  # noqa: E731
            TabelDay.employee_id == emp.id, TabelDay.date == d)) for d in DAYS]
        assert notes() == ["письмо C&B №12"] * 3
        # повторная массовка без примечания его не стирает
        assert admin_client.post("/api/tabel/bulk", json=body).status_code == 200
        db.expire_all()
        assert notes() == ["письмо C&B №12"] * 3
    finally:
        db.rollback()
        db.execute(delete(TabelDay).where(TabelDay.employee_id == emp.id, TabelDay.date.in_(DAYS)))
        db.commit()
