"""Выгрузка в Excel (§8): обезличенная — для непрофильных служб (объект, даты, статус,
число гостей, категория); полная — с гостями, батлерами и логистикой. Данные берутся из
тех же видов, что и экраны, с уровнем видимости выгрузки — лишнего в файл не попадает."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.exchange.application.tables import Cell, Column, Fill, Sheet, write_xlsx

from ..adapters.orm import Logistics, Reservation
from ..domain.halfday import PM, pos
from .context import load_context
from .reservations import STATUS_TITLES
from .views import BoardFilters, check_window, units_board

ESCORT_TITLES = {"rules": "по правилам", "required": "требуется", "declined": "отказался"}
BUSY = Fill("DCE6F5")


def occupancy_counts(board: dict, days: list[dt.date]) -> dict[str, dict[str, int]]:
    """Категория → день → занято объектов (ночь дня: полоса покрывает PM даты)."""
    cat_of = {u["unit_id"]: u["category"] for u in board["units"]}
    out: dict[str, dict[str, int]] = {}
    for d in days:
        p = pos(d, PM)
        busy = {b["unit_id"] for b in board["bars"] if b["unit_id"] and b["start_pos"] <= p <= b["end_pos"]}
        for uid in busy:
            out.setdefault(cat_of[uid], {}).setdefault(d.isoformat(), 0)
            out[cat_of[uid]][d.isoformat()] += 1
    return out


def export_xlsx(db: Session, first: dt.date, last: dt.date, kind: Literal["full", "anon"]) -> bytes:
    days = check_window(first, last)
    level = "full" if kind == "full" else "occupancy"
    board = units_board(db, first, last, BoardFilters(), level)
    day_titles = [d.strftime("%d.%m") for d in days]

    grid = []
    for u in board["units"]:
        cells = []
        for d in days:
            p = pos(d, PM)
            bar = next((b for b in board["bars"] if b["unit_id"] == u["unit_id"] and b["start_pos"] <= p <= b["end_pos"]), None)
            if bar is None:
                cells.append(None)
            else:
                text = (bar.get("main_guest") or bar.get("number") or "занято") if kind == "full" else "занято"
                cells.append(Cell(text, fill=BUSY))
        grid.append([u["label"], u["category"], *cells])
    board_sheet = Sheet("Шахматка", header=["Объект", "Категория", *day_titles], rows=grid,
                        columns={i: Column(14) for i in range(3, len(days) + 3)})

    head = ["Объект", "Категория", "Заезд", "Выезд", "Статус", "Гостей"]
    if kind == "full":
        head += ["№ брони", "Гости", "◆", "VIP-код", "Метка", "Заказчик", "Примечание", "Сопровождение", "Батлеры",
                 "Логистика"]
    labels = {u["unit_id"]: u for u in board["units"]}
    rids = sorted({b["reservation_id"] for b in board["bars"]})
    res = {r.id: r for r in db.scalars(select(Reservation).where(Reservation.id.in_(rids)))} if rids else {}
    butlers, logistics, occupants = {}, {}, {}
    if kind == "full" and rids:
        ctx = load_context(db, first, last, None)
        for d in ctx.days():
            for (rid, _g), emps in ctx.cover(d).by_guest.items():
                for e in emps:
                    butlers.setdefault(rid, {}).setdefault(ctx.name(e), []).append(d.strftime("%d.%m"))
        for rid in rids:
            occupants[rid] = sorted({ctx.guest_name(o.guest_id) for o in ctx.occ.get(rid, [])})
        for lg in db.scalars(select(Logistics).where(Logistics.reservation_id.in_(rids))):
            logistics.setdefault(lg.reservation_id, []).append(
                f"{lg.date.strftime('%d.%m') if lg.date else ''} {lg.time} {lg.description}".strip())
    bookings = []
    for rid in rids:
        r = res[rid]
        bars = [b for b in board["bars"] if b["reservation_id"] == rid]
        units = ", ".join(dict.fromkeys(labels[b["unit_id"]]["label"] for b in bars if b["unit_id"] in labels)) or "без объекта"
        cats = ", ".join(dict.fromkeys(labels[b["unit_id"]]["category"] for b in bars if b["unit_id"] in labels))
        values = [units, cats, r.check_in.strftime("%d.%m.%Y"), r.check_out.strftime("%d.%m.%Y"),
                  STATUS_TITLES[r.status], bars[0]["guests_count"]]
        if kind == "full":
            b0 = bars[0]
            values += [r.number, ", ".join(occupants.get(rid, [])), "◆" if b0.get("special") else "", b0.get("vip_code", ""),
                       (b0.get("label") or {}).get("title", ""), r.customer, r.note,
                       ESCORT_TITLES.get(r.escort_mode, r.escort_mode),
                       "; ".join(f"{n}: {', '.join(ds)}" for n, ds in butlers.get(rid, {}).items()),
                       "; ".join(logistics.get(rid, []))]
        bookings.append(values)

    counts = occupancy_counts(board, days)
    totals: dict[str, int] = {}
    for u in board["units"]:
        totals[u["category"]] = totals.get(u["category"], 0) + 1
    summary = [[cat, total, *[counts.get(cat, {}).get(d.isoformat(), 0) for d in days]]
               for cat, total in sorted(totals.items())]
    no_show = db.scalars(select(Reservation.check_in).where(Reservation.status == "no_show",
                                                            Reservation.check_in >= first, Reservation.check_in <= last))
    per_day: dict[dt.date, int] = {}
    for d in no_show:
        per_day[d] = per_day.get(d, 0) + 1
    summary += [[], ["Не заехали", "", *[per_day.get(d, 0) for d in days]]]

    return write_xlsx([board_sheet, Sheet("Брони", header=head, rows=bookings),
                       Sheet("Сводка", header=["Категория", "Объектов", *day_titles], rows=summary)])


BOOKING_COLUMNS = (("Номер", "number"), ("Главный гость", "main_guest"), ("◆", "special"), ("VIP-код", "vip_code"),
                   ("Заезд", "check_in"), ("Выезд", "check_out"), ("Ночей", "nights"), ("Категория", "category"),
                   ("Объект", "unit"), ("Статус", "status_title"), ("Метка", "label"), ("Батлеры", "butlers"),
                   ("РЗ", "early"), ("ПВ", "late"), ("Создана", "created_at"), ("Сопровождение", "escort_mode"))


def _booking_cell(key: str, v):
    if key == "butlers":
        return ", ".join(v)
    if key == "special":
        return "◆" if v else ""
    if key == "escort_mode":
        return ESCORT_TITLES.get(v, v)
    if key == "label":
        return v["title"] if v else ""
    if key in ("early", "late"):
        return "да" if v else ""
    return v


def bookings_xlsx(rows: list[dict]) -> bytes:
    """Список броней (§8) в том порядке и составе колонок, что на экране; лист «Бронирования»."""
    return write_xlsx([Sheet("Бронирования", header=[title for title, _ in BOOKING_COLUMNS],
                             rows=[[_booking_cell(key, row[key]) for _, key in BOOKING_COLUMNS] for row in rows])])
