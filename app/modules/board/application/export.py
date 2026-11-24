"""Выгрузка в Excel (§8): обезличенная — для непрофильных служб (объект, даты, статус,
число гостей, категория); полная — с гостями, батлерами и логистикой. Данные берутся из
тех же видов, что и экраны, с уровнем видимости выгрузки — лишнего в файл не попадает."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.exchange.application.tables import Align, Cell, Column, Fill, Sheet, write_xlsx
from app.modules.stays.application.catalog import Logistics, Reservation
from app.modules.stays.application.context import load_context
from app.modules.stays.application.reservations import STATUS_TITLES
from app.modules.stays.application.visibility import Level

from .views import BoardFilters, check_window, units_board

ESCORT_TITLES = {"rules": "по правилам", "required": "требуется", "declined": "отказался"}
BUSY = Fill("DCE6F5")
WRAP = Align(wrap=True)


type BarIndex = dict[tuple[int, dt.date], tuple[dict, ...]]


def occupancy_counts(board: dict, at: BarIndex) -> dict[str, dict[str, int]]:
    """Категория → день → число занятых объектов, включая общие для нескольких броней."""
    cat_of = {u["unit_id"]: u["category"] for u in board["units"]}
    out: dict[str, dict[str, int]] = {}
    for uid, day in at:
        counts = out.setdefault(cat_of[uid], {})
        key = day.isoformat()
        counts[key] = counts.get(key, 0) + 1
    return out


def _bar_order(bar: dict) -> tuple[int, str, int, str, int]:
    number = bar.get("number") or ""
    rid = bar["reservation_id"]
    return bar["start_pos"], number, 0 if number else rid, bar.get("main_guest") or "", rid


def _bar_index(bars: list[dict], first: dt.date, last: dt.date) -> BarIndex:
    """(Объект, день) → все полосы, покрывающие вечер этого дня."""
    at: dict[tuple[int, dt.date], list[dict]] = {}
    lo, hi = first.toordinal(), last.toordinal()
    for bar in sorted(bars, key=_bar_order):
        uid = bar["unit_id"]
        if uid is None:
            continue
        # PM = 2 * ordinal + 1; выезд в AM не занимает вечер того же дня.
        start = max(lo, bar["start_pos"] // 2)
        end = min(hi, (bar["end_pos"] - 1) // 2)
        for ordinal in range(start, end + 1):
            at.setdefault((uid, dt.date.fromordinal(ordinal)), []).append(bar)
    return {key: tuple(entries) for key, entries in at.items()}


def export_xlsx(db: Session, first: dt.date, last: dt.date, kind: Literal["full", "anon"]) -> bytes:
    days = check_window(first, last)
    level: Level = "full" if kind == "full" else "occupancy"
    board = units_board(db, first, last, BoardFilters(), level, include_overlays=False)
    day_titles = [d.strftime("%d.%m") for d in days]

    at = _bar_index(board["bars"], first, last)
    by_rid: dict[int, list[dict]] = {}
    for bar in board["bars"]:
        by_rid.setdefault(bar["reservation_id"], []).append(bar)

    grid = []
    for u in board["units"]:
        cells: list[Cell | None] = []
        for d in days:
            cell_bars = at.get((u["unit_id"], d))
            if not cell_bars:
                cells.append(None)
            elif kind == "full":
                text = "\n".join(b.get("main_guest") or b.get("number") or "занято" for b in cell_bars)
                cells.append(Cell(text, fill=BUSY, align=WRAP if len(cell_bars) > 1 else None))
            else:
                text = f"занято ×{len(cell_bars)}" if len(cell_bars) > 1 else "занято"
                cells.append(Cell(text, fill=BUSY))
        grid.append([u["label"], u["category"], *cells])
    board_sheet = Sheet("Шахматка", header=["Объект", "Категория", *day_titles], rows=grid,
                        columns={i: Column(14) for i in range(3, len(days) + 3)})

    head = ["Объект", "Категория", "Заезд", "Выезд", "Статус", "Гостей"]
    if kind == "full":
        head += ["№ брони", "Гости", "◆", "VIP-код", "Метка", "Заказчик", "Примечание", "Сопровождение", "Батлеры",
                 "Логистика"]
    labels = {u["unit_id"]: u for u in board["units"]}
    rids = sorted(by_rid)
    res = {r.id: r for r in db.scalars(select(Reservation).where(Reservation.id.in_(rids)))} if rids else {}
    butlers: dict[int, dict[str, list[str]]] = {}
    logistics: dict[int, list[str]] = {}
    occupants: dict[int, list[str]] = {}
    if kind == "full" and rids:
        ctx = load_context(db, first, last, None, fund_window_only=True)
        for d in ctx.days():
            for (rid, _g), emps in ctx.cover(d).by_guest.items():
                for e in emps:
                    butlers.setdefault(rid, {}).setdefault(ctx.name(e), []).append(d.strftime("%d.%m"))
        for rid in rids:
            occupants[rid] = sorted({ctx.guest_name(o.guest_id) for o in ctx.occ.get(rid, [])})
        for lg in db.scalars(select(Logistics).where(Logistics.reservation_id.in_(rids),
                                                    or_(Logistics.date.is_(None), Logistics.date.between(first, last)))):
            logistics.setdefault(lg.reservation_id, []).append(
                f"{lg.date.strftime('%d.%m') if lg.date else ''} {lg.time} {lg.description}".strip())
    bookings = []
    for rid in rids:
        r = res[rid]
        bars = by_rid[rid]
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

    counts = occupancy_counts(board, at)
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
