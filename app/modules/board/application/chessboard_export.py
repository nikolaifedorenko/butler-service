"""Печатное представление видимой пользователю шахматки."""
from __future__ import annotations

import re
from calendar import monthrange
from collections import defaultdict
from datetime import date

from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import transaction
from app.core.errors import UpstreamError
from app.core.permissions import principal_permissions
from app.modules.exchange.application import chessboard
from app.modules.stays.application.reservations import STATUS_TITLES
from app.modules.stays.application.view_filters import BoardFilters, ViewError
from app.modules.stays.application.visibility import required_level

from . import views

NEUTRAL = "A9C5F4"
OOO = "F1B9C0"
BLOCK = "DAC1ED"


def _color(raw: str) -> str:
    value = raw.removeprefix("#")
    if re.fullmatch(r"[0-9A-Fa-f]{3}", value):
        value = "".join(char * 2 for char in value)
    return value[:6].upper() if re.fullmatch(r"[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?", value) else NEUTRAL


def _time(pos: int) -> str:
    ordinal, half = divmod(pos, 2)
    when = "вечер" if half else "утро"
    return f"{date.fromordinal(ordinal):%d.%m.%Y}, {when}"


def _fields(bar: dict, unit: str) -> chessboard.Fields:
    fields: chessboard.Fields = []
    if "number" in bar:
        fields.extend([("Гость", bar["surname"]), ("Бронь", bar["number"])])
    fields.extend([
        ("Объект", unit), ("С", _time(bar["start_pos"])), ("По", _time(bar["end_pos"])),
        ("Гостей", bar["guests_count"]), ("Статус", STATUS_TITLES.get(bar["status"], bar["status"])),
    ])
    if bar.get("overbooked"):
        fields.append(("Размещение", "Овербукинг"))
    for title, key in (("VIP-код", "vip_code"), ("Заказчик", "customer"), ("Примечание", "note")):
        if bar.get(key):
            value = " ".join(str(bar[key]).replace("\t", " ").splitlines())
            fields.append((title, value))
    if bar.get("label"):
        fields.append(("Метка", bar["label"]["title"]))
    return fields


def _changes(unit: dict) -> str:
    changes = []
    for key, field, title in (("labels", "label", "Объект"), ("categories", "code", "Категория")):
        labels = unit[key]
        if len(labels) > 1:
            text = labels[0][field] + "".join(
                f" → {item[field]} с {date.fromisoformat(item['from']):%d.%m}" for item in labels[1:]
            )
            changes.append(f"{title}:\t{text}")
    return "\n".join(changes)


def _workbook(data: dict, first: date, last: date) -> chessboard.Chessboard:
    full = data["visibility"] == "full"
    names = data["visibility"] != "occupancy"
    rooms = {
        u["unit_id"]: chessboard.Room(
            u["label"], u["category"],
            off=[(date.fromisoformat(a).toordinal(), date.fromisoformat(b).toordinal()) for a, b, _ in u["off"]],
            changes=_changes(u),
        )
        for u in data["units"]
    }
    categories = {cat["category_id"]: cat["code"] for u in data["units"] for cat in u["categories"]}
    lo, hi = 2 * first.toordinal(), 2 * last.toordinal() + 1
    legend: dict[str, str] = {}
    by_reservation: dict[int, list[dict]] = defaultdict(list)
    unassigned: dict[int, chessboard.Room] = {}
    for bar in data["bars"]:
        if bar["end_pos"] < lo or bar["start_pos"] > hi:
            continue
        rid = bar["reservation_id"]
        by_reservation[rid].append(bar)
        room = rooms.get(bar["unit_id"])
        if room is None:
            room = unassigned.setdefault(rid, chessboard.Room("Без объекта", "Не распределено"))
        label = bar.get("label") or {}
        color = _color(label.get("color") or "")
        caption = bar.get("surname") or bar.get("number") or f"{bar['guests_count']} гост."
        if bar["start_pos"] < lo:
            caption = f"‹ {caption}"
        if bar["end_pos"] > hi:
            caption = f"{caption} ›"
        legend.setdefault(label.get("title") or "Бронь без метки", color)
        room.bands.append(chessboard.Band(bar["start_pos"], bar["end_pos"], caption, color, _fields(bar, room.label)))

    for collection, name, color in (("holds", "OOO", OOO), ("blocks", "Блок", BLOCK)):
        for entry in data[collection]:
            legend.setdefault(name, color)
            fields: chessboard.Fields = [
                ("Статус", name), ("Объект", rooms[entry["unit_id"]].label),
                ("С", _time(entry["start_pos"])), ("По", _time(entry["end_pos"])),
            ]
            if names and entry.get("title"):
                fields.append(("Причина" if collection == "holds" else "Название", entry["title"]))
            rooms[entry["unit_id"]].bands.append(
                chessboard.Band(entry["start_pos"], entry["end_pos"], name, color, fields),
            )
    if any(room.off for room in rooms.values()):
        legend["Вне фонда или фильтра"] = "D9E0E7"
    if not legend:
        legend = {"Бронь без метки": NEUTRAL, "OOO": OOO, "Блок": BLOCK}

    headings = (["Бронь", "Гость"] if names else []) + ["Объект", "Категория", "Заезд", "Выезд", "Гостей", "Статус"]
    if names:
        headings += ["Метка", "VIP-код"]
    if full:
        headings += ["Заказчик", "Примечание"]
    bookings: list[list[chessboard.Value]] = []
    for bars in sorted(by_reservation.values(), key=lambda entries: (entries[0]["booking_start_pos"],
                                                                        entries[0].get("number", ""),
                                                                        entries[0]["reservation_id"])):
        b = bars[0]
        units = dict.fromkeys(rooms[x["unit_id"]].label if x["unit_id"] in rooms else "Без объекта" for x in bars)
        cats = dict.fromkeys(categories.get(x["category_id"], "") for x in bars)
        values: list[chessboard.Value] = [b["number"], b["surname"]] if names else []
        values += [", ".join(units), ", ".join(filter(None, cats)), _time(b["booking_start_pos"]),
                   _time(b["booking_end_pos"]), b["guests_count"], STATUS_TITLES.get(b["status"], b["status"])]
        if names:
            values += [(b.get("label") or {}).get("title", ""), b["vip_code"]]
        if full:
            values += [b["customer"], b["note"]]
        bookings.append(values)

    return chessboard.Chessboard(
        [date.fromisoformat(day) for day in data["days"]], [*rooms.values(), *unassigned.values()],
        legend, headings, bookings, data["criteria"],
    )


def export_view(db: Session, principal: Principal, first: date, last: date, filters: BoardFilters,
                kind: str, *, for_print: bool = False) -> bytes:
    month_end = date(first.year, first.month, monthrange(first.year, first.month)[1])
    if first.day != 1 or last != month_end:
        raise ViewError("Для выгрузки шахматки выберите один месяц")
    with transaction(db):
        level = required_level(db, principal)
        perms = principal.gate_permissions if principal.gate_permissions is not None else principal_permissions(db, principal)
        # Просмотр фамилий сам по себе не даёт выгружать их в Excel.
        if kind == "xlsx" and "stays.export" not in perms:
            level = "occupancy"
        data = views.units_board(db, first, last, filters, level, for_export=True)
        workbook = _workbook(data, first, last)
    # Некоторые просмотрщики рисуют значки примечаний даже в предпросмотре печати.
    content, notes = chessboard.write(workbook, include_notes=not (kind == "pdf" and for_print))
    if kind == "pdf":
        try:
            content = chessboard.to_pdf(content, notes)
        except chessboard.PdfUnavailable as exc:
            raise UpstreamError(f"Не удалось собрать PDF шахматки: {exc} Можно выгрузить XLSX.") from exc
    with transaction(db):
        audit(db, principal, "stays_export", f"board:{kind}", {
            "kind": kind, "visibility": level, "first": first.isoformat(), "last": last.isoformat(),
        })
    return content
