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

from app.core.time import now_local
from app.models import Car  # транзит G3: до модуля cars (фаза C4c)
from app.modules.notify.application.catalog import ResponsibilityService

from ..adapters.orm import (
    ChecklistItem,
    ChecklistOverride,
    NightArea,
    NightAreaSection,
    NightCheckItem,
    NightInterception,
    NightReport,
    NightZone,
    ZoneChecklistItem,
)

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


def services_map(db: Session) -> dict[int, str]:
    """Названия ответственных служб одним запросом: {id: name}."""
    return {s.id: s.name for s in db.scalars(select(ResponsibilityService))}


def service_dict(svc: ResponsibilityService, *, items_total: int = 0) -> dict:
    """Служба справочника: каналы доставки, ящик, закреплённые чаты, число пунктов.

    ready_* — можно ли отправлять этим каналом (канал включён и заполнен получатель):
    интерфейс показывает предупреждение, пока служба не готова, а этап 5 не шлёт
    в пустоту. Чаты закрепляются из общего каталога Telegram («Настройки → Чаты и
    Почта»), поэтому здесь только их id.
    """
    try:
        chats = json.loads(svc.chat_ids or "[]")
        if not isinstance(chats, list):
            chats = []
    except ValueError:
        chats = []
    return {
        "id": svc.id, "name": svc.name, "sort_order": svc.sort_order,
        "active": bool(svc.active),
        "use_telegram": bool(svc.use_telegram), "use_email": bool(svc.use_email),
        "email_to": svc.email_to or "", "email_copy": svc.email_copy or "",
        "chat_ids": chats, "note": svc.note or "", "items_total": items_total,
        "ready_telegram": bool(svc.use_telegram and chats),
        "ready_email": bool(svc.use_email and (svc.email_to or "").strip()),
        "ready": bool((svc.use_telegram and chats) or (svc.use_email and (svc.email_to or "").strip())),
        "created_at": svc.created_at.isoformat(timespec="seconds") if svc.created_at else None,
    }


def effective_items(db: Session, area: NightArea) -> list[dict]:
    """Эффективный чек-лист объекта (v2): шаблон зоны + свои пункты − отключённые.

    Порядок: сначала пункты шаблона зоны (ZoneChecklistItem), затем свои пункты
    объекта (ChecklistItem.area_id) — внутри групп по sort_order. Для пункта шаблона
    учитываются индивидуальные правки объекта (ChecklistOverride): disabled — пункт
    не проверяется у этого объекта, text — своя формулировка.

    Возвращает снимок для отчёта: [{"id", "src": "zone"|"area", "text", "overridden",
    "service_id", "service_name", "service_own"}], где id — id пункта шаблона зоны
    или своего пункта (различаются по src), а служба — ответственный получатель
    недостатка по этому пункту (service_own=True — у объекта своя служба, а не
    как в шаблоне зоны).
    """
    out: list[dict] = []
    svc_names = services_map(db)
    if area.zone_id:
        zone_items = list(db.scalars(
            select(ZoneChecklistItem)
            .where(ZoneChecklistItem.zone_id == area.zone_id, ZoneChecklistItem.active.is_(True))
            .order_by(ZoneChecklistItem.sort_order, ZoneChecklistItem.id)))
        ovs = ({o.zone_item_id: o for o in db.scalars(
            select(ChecklistOverride).where(ChecklistOverride.area_id == area.id))}
            if zone_items else {})
        for it in zone_items:
            ov = ovs.get(it.id)
            if ov is not None and ov.disabled:
                continue                       # у этого объекта пункт не проверяется
            sid = ov.service_id if (ov is not None and ov.service_id) else it.service_id
            out.append({"id": it.id, "src": "zone", "text": (ov.text if ov is not None and ov.text
                                                             else it.text),
                        "overridden": bool(ov is not None and ov.text),
                        "service_id": sid, "service_name": svc_names.get(sid or 0, ""),
                        "service_own": bool(ov is not None and ov.service_id)})
    for it in db.scalars(select(ChecklistItem)
                         .where(ChecklistItem.area_id == area.id, ChecklistItem.active.is_(True))
                         .order_by(ChecklistItem.sort_order, ChecklistItem.id)):
        out.append({"id": it.id, "src": "area", "text": it.text, "overridden": False,
                    "service_id": it.service_id, "service_name": svc_names.get(it.service_id or 0, ""),
                    "service_own": False})
    return out


def ensure_report(db: Session, shift_d: dt.date, *, cars_step: bool = True) -> Optional[NightReport]:
    """Создать отчёт за смену, если его ещё нет (идемпотентно).

    Снимок областей: активные области справочника + их активные пункты.
    Отчёт за текущую (ещё не начавшуюся) смену создаётся только начиная с 20:00,
    чтобы батлеры не видели «будущий» отчёт днём.
    """
    report = db.scalar(select(NightReport).where(NightReport.date == shift_d))
    if report:
        return report
    # Будущую смену раньше её начала не создаём. Сравниваем именно с моментом старта
    # смены (20:00 даты shift_d), а не с «сегодняшней» датой: иначе смена, идущая
    # сейчас (например 02:00 ночи), осталась бы без отчёта при старте сервера
    # после 20:00 — ночная бригада видела бы пустой раздел до самого закрытия.
    if now_local() < dt.datetime.combine(shift_d, SHIFT_START):
        return None

    report = NightReport(date=shift_d)
    db.add(report)
    db.flush()

    order = 10
    areas = list(db.scalars(select(NightArea).where(NightArea.active.is_(True))
                            .order_by(NightArea.sort_order, NightArea.id)))
    zones = {z.id: z.name for z in db.scalars(select(NightZone))}
    for area in areas:
        # чек-лист объекта = шаблон зоны + свои пункты − отключённые (снимком в отчёт)
        snap = effective_items(db, area)
        section = NightAreaSection(
            report_id=report.id, area_id=area.id, name=area.name, category=area.category,
            zone_id=area.zone_id, zone_name=zones.get(area.zone_id, area.category or ""),
            snapshot_json=json.dumps(snap, ensure_ascii=False), sort_order=order)
        db.add(section)
        db.flush()
        for i, s in enumerate(snap):
            db.add(NightCheckItem(section_id=section.id,
                                  item_id=s["id"] if s["src"] == "area" else None,
                                  zone_item_id=s["id"] if s["src"] == "zone" else None,
                                  text=s["text"], sort_order=(i + 1) * 10,
                                  service_id=s.get("service_id"),
                                  service_name=s.get("service_name") or ""))
        order += 10

    if cars_step:
        db.add(NightAreaSection(report_id=report.id, area_id=None, name=CAR_AREA_NAME,
                                category="cars", snapshot_json="[]", sort_order=order))
    db.commit()
    return report


# sync_reports() дёргается на каждый запрос раздела (в т.ч. на каждый тик поллинга),
# а работа у него «разовая»: досоздать пропущенные смены и закрыть наступившие.
# Поэтому внутри процесса повторяем не чаще раза в интервал — иначе каждый запрос
# платит за несколько выборок и, на SQLite, конкурирует за блокировку с отметками.
SYNC_INTERVAL_SECONDS = 120
_last_sync: dict[str, float] = {"ts": 0.0}


def sync_reports(db: Session, *, force: bool = False) -> dict:
    """Обслуживание отчётов при обращении к разделу / при старте сервера:
    досоздать пропущенные смены (сервер был выключен) и закрыть наступившие.

    Повторные вызовы чаще SYNC_INTERVAL_SECONDS пропускаются (force=True — пропустить
    ограничение: используется при старте сервера и в тестах)."""
    import time

    now_ts = time.monotonic()
    if not force and now_ts - _last_sync["ts"] < SYNC_INTERVAL_SECONDS:
        return {"created": [], "closed": [], "skipped": True}
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
    _last_sync["ts"] = now_ts
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
        # ответственная служба — снимком: переименование службы не меняет закрытые смены
        "service_id": it.service_id, "service_name": it.service_name or "",
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
        # зона — снимком: у старых отчётов zone_name пустой, тогда группируем по категории
        "zone_id": sec.zone_id, "zone_name": sec.zone_name or sec.category or "",
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


def refresh_free_section(db: Session, area: NightArea) -> int:
    """Пересобрать чек-лист объекта в ОТКРЫТЫХ сменах, где объект ещё не взят в работу.

    Применяется после правок шаблона зоны и индивидуальных правок объекта: там, где
    батлер ещё не начал проверку (status="free"), снимок безопасно пересобрать целиком;
    начатые и закрытые области не трогаем — иначе потерялись бы отметки. Возвращает
    число пересобранных областей.
    """
    snap = effective_items(db, area)
    touched = 0
    for sec in db.scalars(select(NightAreaSection)
                          .join(NightReport, NightReport.id == NightAreaSection.report_id)
                          .where(NightAreaSection.area_id == area.id,
                                 NightReport.status == "open",
                                 NightAreaSection.status == "free")):
        sec.snapshot_json = json.dumps(snap, ensure_ascii=False)
        for ni in list(sec.items):
            db.delete(ni)
        db.flush()
        for i, item in enumerate(snap):
            db.add(NightCheckItem(section_id=sec.id,
                                  item_id=item["id"] if item["src"] == "area" else None,
                                  zone_item_id=item["id"] if item["src"] == "zone" else None,
                                  text=item["text"], sort_order=(i + 1) * 10,
                                  service_id=item.get("service_id"),
                                  service_name=item.get("service_name") or ""))
        touched += 1
    return touched


def zones_progress(section_dicts: list[dict]) -> list[dict]:
    """Прогресс по зонам — считается из уже сериализованных областей отчёта (без SQL).

    Зона «Без зоны» (zone_id None) собирается для объектов, у которых зона не задана;
    шаг «Проверка электрокаров» в зоны не входит — это отдельный шаг.
    """
    order: list = []
    by: dict = {}
    for s in section_dicts:
        if s.get("is_cars"):
            continue
        zid = s.get("zone_id")
        z = by.get(zid)
        if z is None:
            z = by[zid] = {"zone_id": zid, "name": s.get("zone_name") or "Без зоны",
                           "areas_total": 0, "done": 0, "taken": 0, "free": 0,
                           "items_total": 0, "items_answered": 0, "items_bad": 0,
                           "items_unanswered": 0}
            order.append(zid)
        z["areas_total"] += 1
        if s.get("status") in ("done", "taken", "free"):
            z[s["status"]] += 1
        z["items_total"] += s.get("items_total", 0)
        z["items_answered"] += s.get("items_answered", 0)
        z["items_bad"] += s.get("items_bad", 0)
        z["items_unanswered"] += s.get("items_unanswered", 0)
    return [by[k] for k in order]


def zone_dict(zone: NightZone, *, areas_total: int = 0, items_total: int = 0) -> dict:
    """Зона справочника (для экрана настроек и списка зон)."""
    return {"id": zone.id, "name": zone.name, "sort_order": zone.sort_order,
            "active": bool(zone.active), "areas_total": areas_total,
            "items_total": items_total,
            "created_at": zone.created_at.isoformat(timespec="seconds") if zone.created_at else None}


def duty_of(rep: NightReport) -> str:
    """Ночные батлеры смены для плейсхолдера {duty} в сообщении службам.

    Берём тех, кто реально вёл обход: закреплял области и отмечал пункты. График
    здесь не источник истины — смену мог подменить другой батлер (перехват области),
    а получателю важно, к кому идти с вопросом.
    """
    names = {s.taken_by_name for s in rep.areas if s.taken_by_name}
    for sec in rep.areas:
        for it in sec.items:
            if it.answered_by_name:
                names.add(it.answered_by_name)
    return ", ".join(sorted(names)) or "—"


def defects_of(db: Session, rep: NightReport) -> dict:
    """Недостатки смены для консолидированной отправки службам (этап 5).

    В отчёт попадают три рода позиций:
      * «Не ОК» — батлер отметил замечание (комментарий обязателен по смыслу обхода,
        но не по схеме: отправляем и без него);
      * «Не проверено» — пункт остался без ответа (решение владельца: включать
        в отчёт отдельным блоком);
      * «Исправлено после отправки» — пункт уже уходил службе, а потом батлер
        отметил «ОК». Из отчёта такая позиция НЕ исчезает (иначе получатель
        остался бы с неизвестно чем), но повторно ничего не отправляем и сообщение
        не отзываем — решение владельца от 19.10.2026.

    Отправленное помечается (dispatched_at/dispatch_id) и повторно не уходит.

    Возвращает {"items": [...], "counts": {...}}; группировку по службам делает
    app/notify/recipients.py — домен не знает про транспорт.
    """
    from app.core.media import photos_of

    sections = [s for s in sorted(rep.areas, key=lambda x: (x.sort_order, x.id))
                if not (s.area_id is None and s.category == "cars")]
    rows: list[NightCheckItem] = []
    for sec in sections:
        rows.extend(sorted(sec.items, key=lambda x: (x.sort_order, x.id)))
    media = photos_of(db, "night_item", [r.id for r in rows]) or {}

    items: list[dict] = []
    for ni in rows:
        unchecked = not ni.answer
        dispatched = bool(ni.dispatched_at)
        if ni.answer != "bad" and not unchecked and not dispatched:
            continue
        fixed_after = bool(dispatched and ni.answer == "ok")
        kind = "bad" if ni.answer == "bad" else ("unchecked" if unchecked else "fixed")
        items.append({
            "id": ni.id,
            "kind": kind,
            "kind_title": {"bad": "Не ОК", "unchecked": "Не проверено",
                           "fixed": "Исправлено после отправки"}[kind],
            "section_id": ni.section_id,
            "area_id": ni.section.area_id if ni.section else None,
            "area": ni.section.name if ni.section else "",
            "zone": (ni.section.zone_name or ni.section.category or "") if ni.section else "",
            "text": ni.text,
            "comment": ni.comment or "",
            "service_id": ni.service_id,
            "service_name": ni.service_name or "",
            "answered_by_name": ni.answered_by_name or "",
            "answered_at": ni.answered_at.isoformat(timespec="seconds") if ni.answered_at else None,
            "media": media.get(ni.id, []),
            "dispatched": dispatched,
            "dispatched_at": ni.dispatched_at.isoformat(timespec="seconds") if ni.dispatched_at else None,
            "dispatch_id": ni.dispatch_id,
            "fixed_after_dispatch": fixed_after,
            # отправляем только то, что ещё не уходило и не исправлено после отправки
            "sendable": not dispatched and not fixed_after,
        })
    return {
        "items": items,
        "counts": {
            "total": len(items),
            "bad": sum(1 for i in items if i["kind"] == "bad"),
            "unchecked": sum(1 for i in items if i["kind"] == "unchecked"),
            "fixed_after_dispatch": sum(1 for i in items if i["kind"] == "fixed"),
            "sendable": sum(1 for i in items if i["sendable"]),
            "dispatched": sum(1 for i in items if i["dispatched"]),
            "without_service": sum(1 for i in items if i["sendable"] and not i["service_id"]),
        },
    }


def car_checks_of(db, rep: NightReport) -> tuple[list[dict], list[dict]]:
    """Снимок обхода электрокаров за смену + перехваты (нужны и API, и выгрузке DOCX)."""
    from app.core.media import photos_of
    from app.models import CarNightCheck  # транзит G3: до модуля cars (C4c)

    out = []
    checks = list(db.scalars(select(CarNightCheck).where(CarNightCheck.report_id == rep.id)
                             .order_by(CarNightCheck.checked_at, CarNightCheck.id)))
    pmap = photos_of(db, "car_check", [c.id for c in checks])
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
            "found_location": c.found_location or "", "moved": bool(c.moved),
            "canopy": bool(c.canopy), "charge": c.charge or "", "on_charge": bool(c.on_charge),
            "condition": c.condition or "ok", "trash": bool(c.trash), "clean": bool(c.clean),
            "comment": c.comment or "", "taken_after_check": taken_after,
            "photos": pmap.get(c.id, []),
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
    data["zones"] = zones_progress(data["areas"])
    if db is not None:
        data["car_checks"], data["interceptions"] = car_checks_of(db, rep)
    return data
