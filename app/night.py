"""Ночной отчёт: движок смен 20:00–08:00 (Europe/Moscow).

Правила (по ТЗ):
  * отчёт создаётся автоматически ровно на каждую ночную смену — в 20:00;
    если сервер был выключен, отчёт создаётся «задним числом» при старте;
  * список областей и пункты чек-листов ФИКСИРУЮТСЯ снимком на момент создания
    отчёта — правки справочников позже не ломают открытые и закрытые отчёты;
  * закрепление области за батлером рекомендательное: второй может «перехватить»,
    система предупредит и запишет факт перехвата в историю;
  * в 08:00 следующего дня отчёт закрывается сам: все области закрыты → «полный»,
    есть незакрытые → «неполный». После закрытия отчёт только для чтения.

Время смены хранится в локальном времени объекта (naive), как Punch.ts.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .deps import now_local
from .models import (Car, ChecklistItem, NightArea, NightAreaSection, NightCheckItem,
                     NightInterception, NightReport)

SHIFT_START = dt.time(20, 0)   # начало ночной смены
SHIFT_END = dt.time(8, 0)      # автозакрытие
CAR_AREA_NAME = "Проверка электрокаров"   # специальная область обхода каров


def shift_date_at(ts: dt.datetime) -> dt.date:
    """Дате начала смены принадлежит интервал [20:00 Д, 08:00 Д+1)."""
    return (ts - dt.timedelta(hours=12)).date()


def current_shift_date(now: Optional[dt.datetime] = None) -> dt.date:
    if now is None:
        now = now_local()
    elif now.tzinfo is not None:      # наивное время объекта (Europe/Moscow), как в БД
        now = now.replace(tzinfo=None)
    return shift_date_at(now)


def close_deadline(shift_d: dt.date) -> dt.datetime:
    """Момент автозакрытия отчёта за смену D — 08:00 следующих суток."""
    return dt.datetime.combine(shift_d + dt.timedelta(days=1), SHIFT_END)


def ensure_report(db: Session, shift_d: dt.date, *, cars_step: bool = True) -> Optional[NightReport]:
    """Создать отчёт за смену, если его ещё нет (идемпотентно).

    Снимок областей: активные области справочника + их активные пункты.
    Отчёт за текущую (ещё не начавшуюся) смену создаётся только начиная с 20:00,
    чтобы батлеры не видели «будущий» отчёт днём.
    """
    report = db.scalar(select(NightReport).where(NightReport.date == shift_d))
    if report:
        return report
    # не создаём задним числом будущую смену раньше её начала
    if shift_d > current_shift_date() or (shift_d == current_shift_date() and now_local().time() < SHIFT_START):
        return None

    report = NightReport(date=shift_d)
    db.add(report)
    db.flush()

    order = 10
    areas = list(db.scalars(select(NightArea).where(NightArea.active.is_(True))
                            .order_by(NightArea.sort_order, NightArea.id)))
    for area in areas:
        snap = [{"id": it.id, "text": it.text} for it in
                db.scalars(select(ChecklistItem)
                           .where(ChecklistItem.area_id == area.id,
                                  ChecklistItem.active.is_(True))
                           .order_by(ChecklistItem.sort_order, ChecklistItem.id))]
        section = NightAreaSection(
            report_id=report.id, area_id=area.id, name=area.name, category=area.category,
            snapshot_json=json.dumps(snap, ensure_ascii=False), sort_order=order)
        db.add(section)
        db.flush()
        for i, s in enumerate(snap):
            db.add(NightCheckItem(section_id=section.id, item_id=s["id"], text=s["text"],
                                  sort_order=(i + 1) * 10))
        order += 10

    if cars_step:
        db.add(NightAreaSection(report_id=report.id, area_id=None, name=CAR_AREA_NAME,
                                category="cars", snapshot_json="[]", sort_order=order))
    db.commit()
    return report


def sync_reports(db: Session) -> dict:
    """Обслуживание отчётов при обращении к разделу / при старте сервера:
    досоздать пропущенные смены (сервер был выключен) и закрыть наступившие."""
    created: list[str] = []
    closed: list[str] = []
    today = current_shift_date()
    have = {d for (d,) in db.execute(select(NightReport.date).where(NightReport.date <= today))}
    # подтягиваем максимум последних 31 смены («задним числом»)
    start = max(today - dt.timedelta(days=31), today - dt.timedelta(days=min(len(have) + 31, 31)))
    d = start
    while d <= today:
        if d not in have:
            r = ensure_report(db, d)
            if r is not None:
                created.append(d.isoformat())
        d += dt.timedelta(days=1)
    now = now_local()
    for rep in db.scalars(select(NightReport).where(NightReport.status == "open")):
        if now >= close_deadline(rep.date):
            finalize_report(rep)
            closed.append(rep.date.isoformat())
    if created or closed:
        db.commit()
    return {"created": created, "closed": closed}


def finalize_report(rep: NightReport) -> str:
    """Закрыть отчёт: посчитать результат full/partial. Возвращает result."""
    rep.status = "closed"
    rep.closed_at = now_local()
    unfinished = [s for s in rep.areas if s.status != "done"]
    if unfinished or not rep.cars_step_done:
        rep.result = "partial"
    else:
        rep.result = "full"
    return rep.result


# ─────────────────────────── сериализация ───────────────────────────

ANSWER_TITLES = {"": "не отмечено", "ok": "ОК", "bad": "Не ОК"}
SECTION_TITLES = {"free": "свободна", "taken": "в работе", "done": "закрыта"}


def item_dict(it: NightCheckItem) -> dict:
    return {
        "id": it.id, "item_id": it.item_id, "text": it.text, "sort_order": it.sort_order,
        "answer": it.answer, "answer_title": ANSWER_TITLES.get(it.answer, it.answer),
        "comment": it.comment or "",
        "answered_by_name": it.answered_by_name or "",
        "answered_at": it.answered_at.isoformat(timespec="seconds") if it.answered_at else None,
    }


def progress_of(sections: list[NightAreaSection]) -> dict:
    total = len(sections)
    done = sum(1 for s in sections if s.status == "done")
    taken = sum(1 for s in sections if s.status == "taken")
    return {"total": total, "done": done, "taken": taken, "free": total - done - taken}


def section_dict(sec: NightAreaSection, *, with_items: bool = True) -> dict:
    items = sorted(sec.items, key=lambda x: (x.sort_order, x.id))
    answered = sum(1 for i in items if i.answer)
    data = {
        "id": sec.id, "area_id": sec.area_id, "name": sec.name, "category": sec.category,
        "is_cars": sec.area_id is None and sec.category == "cars",
        "status": sec.status, "status_title": SECTION_TITLES.get(sec.status, sec.status),
        "taken_by": sec.taken_by, "taken_by_name": sec.taken_by_name or "",
        "taken_at": sec.taken_at.isoformat(timespec="seconds") if sec.taken_at else None,
        "closed_at": sec.closed_at.isoformat(timespec="seconds") if sec.closed_at else None,
        "items_total": len(items), "items_answered": answered,
        "items_bad": sum(1 for i in items if i.answer == "bad"),
        "items_unanswered": len(items) - answered,
    }
    if with_items:
        data["items"] = [item_dict(i) for i in items]
    return data


def car_checks_of(db, rep: NightReport) -> tuple[list[dict], list[dict]]:
    """Снимок обхода электрокаров за смену + перехваты (нужны и API, и выгрузке DOCX)."""
    from .models import CarNightCheck, NightInterception   # локально — не раздуваем импорт модуля

    out = []
    checks = list(db.scalars(select(CarNightCheck).where(CarNightCheck.report_id == rep.id)
                             .order_by(CarNightCheck.checked_at, CarNightCheck.id)))
    for c in checks:
        taken_after = False
        if c.car_id:
            car = db.get(Car, c.car_id)
            if car is not None and car.last_taken_at and c.checked_at and car.last_taken_at > c.checked_at:
                taken_after = True
        out.append({
            "id": c.id, "car_id": c.car_id, "car_number": c.car_number,
            "checker_name": c.checker_name or "",
            "checked_at": c.checked_at.isoformat(timespec="seconds") if c.checked_at else None,
            "found": bool(c.found), "location": c.location or "",
            "canopy": bool(c.canopy), "charge": c.charge or "", "on_charge": bool(c.on_charge),
            "condition": c.condition or "ok", "trash": bool(c.trash), "clean": bool(c.clean),
            "comment": c.comment or "", "taken_after_check": taken_after,
        })
    interceptions = []
    sections_by_id = {s.id: s for s in rep.areas}
    for x in db.scalars(select(NightInterception).where(NightInterception.report_id == rep.id)
                       .order_by(NightInterception.ts, NightInterception.id)):
        sec = sections_by_id.get(x.section_id)
        interceptions.append({
            "id": x.id,
            "ts": x.ts.isoformat(timespec="seconds") if x.ts else None,
            "area_name": sec.name if sec else f"область #{x.section_id}",
            "from_user_name": x.from_user_name or "", "to_user_name": x.to_user_name or "",
        })
    return out, interceptions


def report_dict(rep: NightReport, *, with_items: bool = True, db=None) -> dict:
    sections = sorted(rep.areas, key=lambda s: (s.sort_order, s.id))
    prog = progress_of(sections)
    data = {
        "id": rep.id, "date": rep.date.isoformat(), "shift_label": rep.shift_label,
        "status": rep.status, "result": rep.result,
        "result_title": {"full": "полный", "partial": "неполный"}.get(rep.result, "—"),
        "closed_at": rep.closed_at.isoformat(timespec="seconds") if rep.closed_at else None,
        "close_reason": rep.close_reason,
        "deadline": close_deadline(rep.date).isoformat(timespec="seconds"),
        "readonly": rep.status == "closed",
        "cars_step_done": rep.cars_step_done,
        "progress": prog,
        "areas": [section_dict(s, with_items=with_items) for s in sections],
    }
    if db is not None:
        data["car_checks"], data["interceptions"] = car_checks_of(db, rep)
    return data
