"""OOO — объект не в продаже (часть 2 §3.1, §7): создание, правка, удаление и список. Ничего не
коммитит — commit в роутере; пересчёт распределения и предпросмотр делает общий run_operation."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.employees.application.catalog import Employee

from ..adapters.orm import Ooo
from ..domain.halfday import ooo_span, overlaps
from . import allocation
from .fund import FundConflict, FundError
from .fund_versions import fund_for, unit_exists
from .views import BoardFilters, ViewError, fund_match

SORTS = ("unit", "category", "start", "end", "reason", "author", "created_at")
MAX_LIMIT = 200
MAX_DAYS = 3660


class OooInvalid(FundError):
    """Ошибка ввода → 422."""


class OooConflict(FundConflict):
    """Пересечение OOO или устаревшая версия → 409."""


def _d(v) -> str | None:
    return v.isoformat() if isinstance(v, dt.date) else v


def ooo_dict(o: Ooo) -> dict:
    return {"id": o.id, "unit_id": o.unit_id, "start": _d(o.start), "end": _d(o.end),
            "start_half": o.start_half, "end_half": o.end_half, "reason": o.reason, "version": o.version}


def validate(db: Session, data: dict, own_id: int | None) -> None:
    """Объект есть и состоит в фонде на все дни OOO; интервал корректен; с другим OOO того же объекта
    не пересекается (выезд утром и OOO с вечера в тот же день — не пересечение)."""
    if not unit_exists(db, data["unit_id"]):
        raise OooInvalid("Объект не найден")
    start, end = data["start"], data["end"]
    if end < start:
        raise OooInvalid("Конец OOO раньше начала")
    if start == end and (data["start_half"], data["end_half"]) != ("AM", "PM"):
        raise OooInvalid("OOO в пределах одних суток — «с утра» и «до вечера» (целые сутки)")
    a, z = ooo_span(start, data["start_half"], end, data["end_half"])
    if z < a:
        raise OooInvalid("Конец OOO раньше начала")
    if (end - start).days > MAX_DAYS:
        raise OooInvalid("OOO длиннее десяти лет")
    fund = fund_for(db, start - dt.timedelta(days=1), end)
    spans = allocation.unit_spans(fund, a, z)
    gaps = allocation.absent_parts(spans, data["unit_id"], a, z)
    if gaps:
        (ga, gz) = gaps[0]
        u = fund.unit(data["unit_id"], start)
        raise OooInvalid(f"объекта {u.label if u is not None else '№' + str(data['unit_id'])} нет в фонде "
                         f"{allocation.day_label(ga)}–{allocation.day_label(gz)}")
    for o in db.scalars(select(Ooo).where(Ooo.unit_id == data["unit_id"], Ooo.start <= end, Ooo.end >= start)):
        if o.id != own_id and overlaps(a, z, *ooo_span(o.start, o.start_half, o.end, o.end_half)):
            raise OooConflict(f"Пересекается с другим OOO этого объекта: {o.start.strftime('%d.%m')}–"
                              f"{o.end.strftime('%d.%m')}")


def save_ooo(db: Session, data: dict, oid: int | None, author_id: int | None = None) -> tuple[Ooo, dict]:
    """Создать (oid None) или изменить OOO; для правки data["version"] — версия, открытая в форме."""
    if oid is None:
        validate(db, data, None)
        o = Ooo(author_id=author_id)
        db.add(o)
        before: dict = {}
    else:
        o = db.get(Ooo, oid)
        if o is None:
            raise OooInvalid("OOO не найден")
        if data.get("version") != o.version:
            raise OooConflict("OOO изменили — обновите")
        validate(db, data, oid)
        before = ooo_dict(o)
        o.version += 1
    o.unit_id, o.start, o.end = data["unit_id"], data["start"], data["end"]
    o.start_half, o.end_half, o.reason = data["start_half"], data["end_half"], data["reason"]
    db.flush()
    allocation.run_allocation(db)
    return o, before


def delete_ooo(db: Session, oid: int, version: int) -> dict:
    o = db.get(Ooo, oid)
    if o is None:
        raise OooInvalid("OOO не найден")
    if version != o.version:
        raise OooConflict("OOO изменили — обновите")
    before = ooo_dict(o)
    db.delete(o)
    db.flush()
    allocation.run_allocation(db)
    return before


@dataclass(frozen=True)
class OooQuery:
    first: dt.date | None = None
    last: dt.date | None = None
    filters: BoardFilters = field(default_factory=BoardFilters)
    sort: str = "start"
    dir: Literal["asc", "desc"] = "asc"
    offset: int = 0
    limit: int = MAX_LIMIT

    def __post_init__(self) -> None:
        if (self.first is None) != (self.last is None):
            raise ViewError("Период задаётся парой first и last")
        if self.first is not None and self.last < self.first:
            raise ViewError("Конец периода раньше начала")
        if self.sort not in SORTS:
            raise ViewError("Неизвестная колонка сортировки")
        if self.dir not in ("asc", "desc"):
            raise ViewError("Направление сортировки — asc или desc")
        if self.offset < 0 or not 1 <= self.limit <= MAX_LIMIT:
            raise ViewError(f"limit — от 1 до {MAX_LIMIT}, offset — не меньше 0")


def _check_days(fund, o: Ooo, q: OooQuery) -> list[dt.date]:
    """Дни OOO в периоде, на которых фонд меняется (начало и границы версий): объект и категория
    читаются по фонду дня, а фильтры узла и категории — «или» по этим дням."""
    a, z = (max(o.start, q.first), min(o.end, q.last)) if q.first else (o.start, o.end)
    return [a, *(d for d in fund.boundaries() if a < d <= z)]


def list_ooo(db: Session, q: OooQuery) -> dict:
    stmt = select(Ooo)
    if q.first:
        stmt = stmt.where(Ooo.start <= q.last, Ooo.end >= q.first)
    rows = list(db.scalars(stmt))
    if not rows:
        return {"total": 0, "rows": []}
    fund = fund_for(db, min(o.start for o in rows) - dt.timedelta(days=1), max(o.end for o in rows))
    f = q.filters
    authors = _authors(db, {o.author_id for o in rows if o.author_id})
    items = []
    for o in rows:
        days = _check_days(fund, o, q)
        if not fund.parts:
            continue
        if (f.group_ids or f.category_ids or f.flag_ids or f.kind_ids or f.floor) and not any(
                fund_match(fund.on(d), o.unit_id, None, f) for d in days):
            continue
        u = fund.unit(o.unit_id, days[0])
        cat = fund.category(u.category_id, days[0]) if u is not None else None
        group = ""
        if u is not None and u.group_id in fund.on(days[0]).groups:
            group = " / ".join(fund.on(days[0]).path_titles(u.group_id))
        row = {**ooo_dict(o), "unit": u.label if u is not None else f"№{o.unit_id}",
               "category_id": u.category_id if u is not None else None, "category": cat.code if cat else "",
               "group": group, "author": authors.get(o.author_id, ""), "created_at": o.created_at.isoformat(timespec="minutes")}
        if f.q.strip() and f.q.strip().lower() not in f"{row['reason']} {row['unit']}".lower():
            continue
        items.append(row)
    items.sort(key=lambda r: (r["start"], r["unit"].lower(), r["id"]))
    key = {"unit": lambda r: r["unit"].lower(), "category": lambda r: r["category"].lower(),
           "start": lambda r: (r["start"], r["start_half"] == "PM"), "end": lambda r: (r["end"], r["end_half"] == "PM"),
           "reason": lambda r: r["reason"].lower(), "author": lambda r: r["author"].lower(),
           "created_at": lambda r: r["created_at"]}[q.sort]
    items.sort(key=key, reverse=q.dir == "desc")
    return {"total": len(items), "rows": items[q.offset:q.offset + q.limit]}


def _authors(db: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    from app.core.identity import User
    return {uid: short or full or name for uid, name, short, full in db.execute(
        select(User.id, User.username, Employee.short_name, Employee.full_name)
        .outerjoin(Employee, Employee.id == User.employee_id).where(User.id.in_(ids)))}


