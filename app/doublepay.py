"""Дни двойной оплаты: производственный календарь + периоды работы с ВИП-гостями.

Правила компании:
  * стоимость рабочего дня одинаковая всегда; вдвое оплачиваются ТОЛЬКО переработки;
  * в «двойной» день часы сверх официального окна идут к оплате кодами ДЯ2/ДН2 (×2);
  * списания (опоздания, ранние уходы, отгулы), ложащиеся на двойные часы, снимают их
    ВПОЛОВИНУ: 8 одинарных часов оплаты = 4 часа ДЯ2 (см. settle_overtime в timesheet.py);
    если же списание гасится часами обычных дней — оно считается 1=1;
  * календарь двойных дней задаётся вручную (данные из производственного календаря /
    писем C&B) — сразу на год вперёд, с возможностью правки в середине года;
    отдельно для сменных графиков (2/2, 3/3…) и для пятидневки (или «для всех»);
  * периоды ВИП-гостей назначаются конкретному сотруднику вручную и ДООПРЕДЕЛЯЮТ
    календарь: день «двойной», если он есть в календаре ИЛИ покрыт ВИП-периодом
    (тарифы не складываются и не перемножаются — всегда ×2).

Какой список календаря относится к сотруднику, решается по его шаблону графика
в эту дату: «Пятидневка» (kind=week5) → список пятидневки; остальные блоки
(Смена 1/2, Другие смены: 2/2, 3/3, 1/3, ручные…) → список сменных графиков.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .base_schedule import pattern_for_date
from .models import DoublePayDay, Employee, TimesheetRow, VipDoublePay

SCOPE_SHIFT = "shift"     # сменные графики (2/2, 3/3, сутки через трое…)
SCOPE_WEEK5 = "week5"     # пятидневка
SCOPE_ALL = "all"         # все сотрудники
SCOPES = (SCOPE_SHIFT, SCOPE_WEEK5, SCOPE_ALL)
SCOPE_TITLES = {
    SCOPE_SHIFT: "сменные графики (2/2, 3/3…)",
    SCOPE_WEEK5: "пятидневка",
    SCOPE_ALL: "все сотрудники",
}

REASON_CALENDAR = "calendar"   # день двойной оплаты из производственного календаря
REASON_VIP = "vip"             # работа с ВИП-гостем
REASON_TITLES = {
    REASON_CALENDAR: "День двойной оплаты (производственный календарь)",
    REASON_VIP: "Работа с ВИП-гостем — двойные переработки",
}


def employee_list_kind(db: Session, emp: Employee, date: dt.date, cfg: Optional[dict] = None,
                       index=None) -> str:
    """Какой список календаря применяется к сотруднику в дату: 'week5' или 'shift'.

    `index` — предзагруженные записи блоков (base_schedule.BlockIndex): без него
    в циклах по дням на каждую дату уходит запрос к block_assignments.
    """
    pat = pattern_for_date(db, emp, date, cfg, index=index)
    return "week5" if pat.get("kind") == "week5" else "shift"


def scope_applies(db: Session, emp: Employee, date: dt.date, scope: str,
                  cfg: Optional[dict] = None, index=None) -> bool:
    """Действует ли день календаря с этим scope на сотрудника в эту дату."""
    if scope == SCOPE_ALL:
        return True
    if scope not in (SCOPE_SHIFT, SCOPE_WEEK5):
        return False
    kind = employee_list_kind(db, emp, date, cfg, index=index)   # cfg обязателен в циклах
    return (kind == "week5") if scope == SCOPE_WEEK5 else (kind == "shift")


class DoubleContext:
    """Календарь двойной оплаты и ВИП-периоды, загруженные ДВУМЯ запросами на диапазон.

    Зачем: reason_for() вызывается для каждого дня каждого сотрудника и без контекста
    делает два точечных запроса (ВИП-период + день календаря). На пересчёте месяца
    для 50 сотрудников это ~3 тысячи запросов.
    """

    def __init__(self, cal: dict[dt.date, str], vip_by_emp: dict[int, list[VipDoublePay]]):
        self._cal = cal
        self._vip = vip_by_emp

    @classmethod
    def load(cls, db: Session, start: dt.date, end: dt.date) -> "DoubleContext":
        cal = {d.date: (d.scope or SCOPE_ALL) for d in db.scalars(select(DoublePayDay).where(
            DoublePayDay.date >= start, DoublePayDay.date <= end))}
        vip_by_emp: dict[int, list[VipDoublePay]] = {}
        for v in db.scalars(select(VipDoublePay).where(
                VipDoublePay.start_date <= end, VipDoublePay.end_date >= start)):
            vip_by_emp.setdefault(v.employee_id, []).append(v)
        return cls(cal, vip_by_emp)

    def has_vip(self, emp_id: int, date: dt.date) -> bool:
        return any(v.start_date <= date <= v.end_date for v in self._vip.get(emp_id, ()))

    def day_scope(self, date: dt.date) -> Optional[str]:
        return self._cal.get(date)


def reason_for(db: Session, emp: Employee, date: dt.date, cfg: Optional[dict] = None,
               index=None, ctx: Optional[DoubleContext] = None) -> str:
    """'' | 'vip' | 'calendar' — почему переработки этого дня оплачиваются вдвое.

    ВИП-период важнее календаря только для подписи: на тариф не влияет —
    день в любом случае двойной (×2), а не ×4.

    `ctx` — предзагруженный календарь/ВИП-периоды (см. DoubleContext), `index` —
    предзагруженные блоки: оба нужны в циклах по дням, чтобы не ходить в БД.
    """
    if ctx is not None:
        if ctx.has_vip(emp.id, date):
            return REASON_VIP
        scope = ctx.day_scope(date)
        if scope is not None and scope_applies(db, emp, date, scope, cfg, index=index):
            return REASON_CALENDAR
        return ""
    vip = db.scalar(select(VipDoublePay).where(
        VipDoublePay.employee_id == emp.id,
        VipDoublePay.start_date <= date,
        VipDoublePay.end_date >= date).limit(1))
    if vip is not None:
        return REASON_VIP
    day = db.scalar(select(DoublePayDay).where(DoublePayDay.date == date))
    if day is not None and scope_applies(db, emp, date, day.scope, cfg, index=index):
        return REASON_CALENDAR
    return ""


def calendar_map(db: Session, start: dt.date, end: dt.date) -> dict[dt.date, str]:
    """Дни календаря двойной оплаты за период: дата → scope."""
    return {d.date: (d.scope or SCOPE_ALL) for d in db.scalars(select(DoublePayDay).where(
        DoublePayDay.date >= start, DoublePayDay.date <= end))}


def double_map_for(db: Session, emp_ids, start: dt.date, end: dt.date,
                   cfg: Optional[dict] = None) -> dict[tuple[int, str], str]:
    """(employee_id, ISO-дата) → 'vip' | 'calendar' — для маркеров в табеле за месяц.
    Считается «вживую» по календарю и ВИП-периодам, поэтому всегда актуально."""
    cal = calendar_map(db, start, end)
    vips = db.scalars(select(VipDoublePay).where(
        VipDoublePay.start_date <= end, VipDoublePay.end_date >= start)).all()
    out: dict[tuple[int, str], str] = {}
    for emp_id in emp_ids:
        emp = db.get(Employee, emp_id)
        if emp is None:
            continue
        for v in vips:
            if v.employee_id != emp.id:
                continue
            d = max(v.start_date, start)
            while d <= min(v.end_date, end):
                out[(emp.id, d.isoformat())] = REASON_VIP
                d += dt.timedelta(days=1)
        for cdate, scope in cal.items():
            key = (emp.id, cdate.isoformat())
            if key in out:
                continue
            if scope_applies(db, emp, cdate, scope, cfg):
                out[key] = REASON_CALENDAR
    return out


def recalc_double_rows(db: Session, start: dt.date, end: dt.date,
                       employee_ids: Optional[list[int]] = None, commit: bool = True) -> int:
    """Точечный пересчёт после правки календаря/ВИП-периодов.

    Пересчитываются только строки табеля, которые могли измениться: где есть
    (или были) часы к выплате либо отметка «день двойной». Дни без переработок
    правка календаря не затрагивает — их не трогаем (быстро даже на целом годе).
    """
    from .timesheet import recalc_day

    q = select(TimesheetRow).where(
        TimesheetRow.date >= start, TimesheetRow.date <= end,
        or_(TimesheetRow.pay_ot_day != 0, TimesheetRow.pay_ot_night != 0,
            TimesheetRow.pay_ot_day2 != 0, TimesheetRow.pay_ot_night2 != 0,
            TimesheetRow.double_reason != ""))
    if employee_ids:
        q = q.where(TimesheetRow.employee_id.in_(set(employee_ids)))
    rows = db.scalars(q).all()
    count = 0
    for r in rows:
        emp = db.get(Employee, r.employee_id)
        if emp is None:
            continue
        recalc_day(db, emp, r.date, commit=False)
        count += 1
    if commit:
        db.commit()
    return count
