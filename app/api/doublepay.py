"""Дни двойной оплаты (производственный календарь) и периоды работы с ВИП-гостями.

Календарь ведётся вручную: даты из производственного календаря / писем C&B вносятся
сразу на год вперёд и правятся по ходу года. В отмеченные дни переработки выводятся
к оплате кодами ДЯ2/ДН2 (двойной тариф). Отдельные списки — для сменных графиков
(2/2, 3/3…) и для пятидневки (или «для всех»).

ВИП-периоды назначаются конкретному сотруднику («с 01.09 по 14.09 работает с
ВИП-гостем») и действуют вместе с календарём без перемножения: день двойной,
если он есть в календаре ИЛИ покрыт ВИП-периодом.

Любая правка сразу пересчитывает затронутые строки табеля (только те, где есть
часы к выплате), поэтому реестр «Переработки к выплате» всегда актуален.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Principal, audit, require_manager
from ..db import get_db
from ..deps import WD_SHORT
from ..doublepay import (REASON_TITLES, SCOPE_ALL, SCOPE_SHIFT, SCOPE_TITLES, SCOPE_WEEK5,
                         SCOPES, recalc_double_rows)
from ..models import ROLE_ADMIN, ROLE_MANAGER, DoublePayDay, Employee, VipDoublePay, utcnow

router = APIRouter(prefix="/api/doublepay", tags=["doublepay"])


def _guard(principal: Principal) -> None:
    """Писать календарь оплаты может только администратор или менеджер
    (как и корректировки банка): данные приходят из C&B."""
    if principal.role not in (ROLE_ADMIN, ROLE_MANAGER):
        raise HTTPException(status_code=403,
                            detail="Менять дни двойной оплаты может только администратор или менеджер")


def _author_name(principal: Principal) -> str:
    if principal.employee:
        return principal.employee.display_name
    return principal.user.username


def _parse_date(raw: str) -> Optional[dt.date]:
    raw = (raw or "").strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_dates_list(raw: str) -> list[dt.date]:
    """«2026-01-01, 07.01.2026 08.01.2026» → список дат (разделители: запятая, пробел, ;)."""
    out: list[dt.date] = []
    bad: list[str] = []
    for tok in re.split(r"[\s,;]+", (raw or "").strip()):
        if not tok:
            continue
        d = _parse_date(tok)
        if d is None:
            bad.append(tok)
        elif d not in out:
            out.append(d)
    if bad:
        raise HTTPException(status_code=422,
                            detail="Не понял даты: " + ", ".join(bad)
                                   + " (формат: 2026-01-01 или 01.01.2026)")
    return sorted(out)


def _day_dict(d: DoublePayDay) -> dict:
    return {"id": d.id, "date": d.date.isoformat(), "day": d.date.day, "month": d.date.month,
            "year": d.date.year, "weekday": WD_SHORT[d.date.weekday()],
            "is_weekend": d.date.weekday() >= 5,
            "scope": d.scope, "scope_title": SCOPE_TITLES.get(d.scope, d.scope),
            "note": d.note or ""}


def _vip_dict(v: VipDoublePay) -> dict:
    emp = v.employee
    days = (v.end_date - v.start_date).days + 1
    return {"id": v.id, "employee_id": v.employee_id,
            "employee_name": (emp.display_name if emp else f"#{v.employee_id}"),
            "employee_full_name": (emp.full_name if emp else ""),
            "start_date": v.start_date.isoformat(), "end_date": v.end_date.isoformat(),
            "days": days, "note": v.note or "", "author": v.created_by_name or ""}


@router.get("")
def get_doublepay(year: Optional[int] = None, principal: Principal = Depends(require_manager),
                  db: Session = Depends(get_db)):
    """Календарь двойных дней (за год или весь) + ВИП-периоды."""
    q = select(DoublePayDay).order_by(DoublePayDay.date)
    if year:
        q = q.where(DoublePayDay.date >= dt.date(year, 1, 1),
                    DoublePayDay.date <= dt.date(year, 12, 31))
    days = [_day_dict(d) for d in db.scalars(q)]
    vq = select(VipDoublePay).order_by(VipDoublePay.start_date.desc(), VipDoublePay.id.desc())
    if year:
        vq = vq.where(VipDoublePay.start_date <= dt.date(year, 12, 31),
                      VipDoublePay.end_date >= dt.date(year, 1, 1))
    vips = [_vip_dict(v) for v in db.scalars(vq)]
    return {"days": days, "vip": vips, "year": year,
            "scopes": [{"id": s, "title": SCOPE_TITLES[s]} for s in SCOPES],
            "reason_titles": REASON_TITLES}


class DaysIn(BaseModel):
    dates: str = ""                        # список дат: «2026-01-01, 07.01.2026 …»
    start: Optional[str] = None            # …или период start–end…
    end: Optional[str] = None
    weekdays: Optional[list[int]] = None   # …с фильтром по дням недели (0=пн … 6=вс)
    scope: str = SCOPE_ALL                 # shift | week5 | all
    note: str = ""


@router.post("/days")
def add_days(payload: DaysIn, principal: Principal = Depends(require_manager),
             db: Session = Depends(get_db)):
    """Добавить дни двойной оплаты: списком дат или периодом (можно с фильтром
    по дням недели — например все субботы года для пятидневки).
    Существующие даты обновляются (scope/примечание)."""
    _guard(principal)
    if payload.scope not in SCOPES:
        raise HTTPException(status_code=422,
                            detail="scope должен быть одним из: " + ", ".join(SCOPES))
    dates = _parse_dates_list(payload.dates)
    if payload.start or payload.end:
        start = _parse_date(payload.start or "")
        end = _parse_date(payload.end or "")
        if not start or not end:
            raise HTTPException(status_code=422,
                                detail="Период задаётся двумя датами (формат: 2026-01-01)")
        if end < start:
            raise HTTPException(status_code=422, detail="Конец периода раньше начала")
        if (end - start).days > 1200:
            raise HTTPException(status_code=422, detail="Слишком большой период (максимум ~3 года)")
        wd = set(payload.weekdays or [])
        d = start
        while d <= end:
            if not wd or d.weekday() in wd:
                if d not in dates:
                    dates.append(d)
            d += dt.timedelta(days=1)
        dates.sort()
    if not dates:
        raise HTTPException(status_code=422,
                            detail="Не указано ни одной даты: список дат или период")
    note = (payload.note or "").strip()[:255]

    added, updated = 0, 0
    existing = {d.date: d for d in db.scalars(select(DoublePayDay).where(
        DoublePayDay.date.in_(dates)))}
    for d in dates:
        row = existing.get(d)
        if row is None:
            db.add(DoublePayDay(date=d, scope=payload.scope, note=note,
                                created_by=principal.user.id, created_at=utcnow()))
            added += 1
        else:
            row.scope = payload.scope
            row.note = note
            updated += 1
    audit(db, principal, "doublepay_days_add", f"{dates[0]}..{dates[-1]}",
          {"count": len(dates), "added": added, "updated": updated,
           "scope": payload.scope, "note": note,
           "dates": [d.isoformat() for d in dates[:80]]})
    db.commit()
    recalculated = recalc_double_rows(db, dates[0], dates[-1])
    return {"ok": True, "added": added, "updated": updated, "recalculated": recalculated,
            "days": [_day_dict(d) for d in db.scalars(select(DoublePayDay).where(
                DoublePayDay.date.in_(dates)).order_by(DoublePayDay.date))]}


@router.delete("/days/{day_id}")
def delete_day(day_id: int, principal: Principal = Depends(require_manager),
               db: Session = Depends(get_db)):
    _guard(principal)
    row = db.get(DoublePayDay, day_id)
    if row is None:
        raise HTTPException(status_code=404, detail="День не найден")
    data = _day_dict(row)
    date = row.date
    db.delete(row)
    audit(db, principal, "doublepay_day_delete", date.isoformat(), data)
    db.commit()
    recalculated = recalc_double_rows(db, date, date)
    return {"ok": True, "deleted": data, "recalculated": recalculated}


class VipIn(BaseModel):
    employee_id: int
    start_date: str
    end_date: str
    note: str = ""


@router.post("/vip")
def add_vip(payload: VipIn, principal: Principal = Depends(require_manager),
            db: Session = Depends(get_db)):
    """Назначить сотруднику период двойных переработок (работа с ВИП-гостем)."""
    _guard(principal)
    emp = db.get(Employee, payload.employee_id)
    if emp is None or emp.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    start = _parse_date(payload.start_date)
    end = _parse_date(payload.end_date)
    if not start or not end:
        raise HTTPException(status_code=422,
                            detail="Даты задаются в формате 2026-01-01 или 01.01.2026")
    if end < start:
        raise HTTPException(status_code=422, detail="Конец периода раньше начала")
    if (end - start).days > 366:
        raise HTTPException(status_code=422, detail="Слишком длинный период (максимум год)")
    vip = VipDoublePay(employee_id=emp.id, start_date=start, end_date=end,
                       note=(payload.note or "").strip()[:255],
                       created_by=principal.user.id, created_by_name=_author_name(principal),
                       created_at=utcnow())
    db.add(vip)
    audit(db, principal, "vip_doublepay_add", f"employee:{emp.id}",
          {"start": start.isoformat(), "end": end.isoformat(), "note": vip.note,
           "employee": emp.full_name})
    db.commit()
    db.refresh(vip)
    recalculated = recalc_double_rows(db, start, end, employee_ids=[emp.id])
    return {"ok": True, "item": _vip_dict(vip), "recalculated": recalculated}


@router.delete("/vip/{vip_id}")
def delete_vip(vip_id: int, principal: Principal = Depends(require_manager),
               db: Session = Depends(get_db)):
    _guard(principal)
    vip = db.get(VipDoublePay, vip_id)
    if vip is None:
        raise HTTPException(status_code=404, detail="Период не найден")
    data = _vip_dict(vip)
    emp_id, start, end = vip.employee_id, vip.start_date, vip.end_date
    db.delete(vip)
    audit(db, principal, "vip_doublepay_delete", f"employee:{emp_id}", data)
    db.commit()
    recalculated = recalc_double_rows(db, start, end, employee_ids=[emp_id])
    return {"ok": True, "deleted": data, "recalculated": recalculated}
