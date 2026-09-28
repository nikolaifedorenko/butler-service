"""
Движок расчёта отработанного времени (версия 2: посессии и покалендарно).

Контуры учёта:
  * ФАКТ/БАНК (внутренний): сессия относится к дню начала; если хвост сессии накрывает
    плановое окно следующего дня (ночь → день), сессия делится по границе плана.
  * РЕЕСТР К ВЫПЛАТЕ (внешний контур): часы сессий раскладываются по КАЛЕНДАРНЫМ дням
    и из них вычитается официальное окно дня; остаток — начисления ДЯ/ДН по дням.
  * Округление кратно часу (nearest/floor/ceil), ДН = 22:00–06:00, ДЯ = 06:00–22:00.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .base_schedule import effective_entry_shift, partial_window
from .deps import local_date
from .models import (BankAdjustment, Employee, Punch, ScheduleEntry, Setting, ShiftType,
                     TimesheetRow, utcnow)
from .shiftrev import ShiftCatalog, ShiftView, view_at

# ──────────────────────────── правила расчёта ────────────────────────────
DEFAULT_RULES = {
    "round_mode": "nearest",
    "round_step_min": "60",
    "count_early_arrival": "0",
    "count_late_departure": "1",
    "min_session_min": "10",
    "auto_close_missing_out": "1",
    "grace_minutes": "5",
    "night_start": "22:00",
    "night_end": "06:00",
    "late_by_raw_time": "0",
    "timeoff_default_hours": "8",
    "photo_retention_days": "180",
}

RULE_DESCRIPTIONS = {
    "round_mode": "Округление факта: nearest — к ближайшему часу, floor — вниз, ceil — вверх",
    "round_step_min": "Шаг округления в минутах (60 = учёт кратен часу)",
    "count_early_arrival": "Засчитывать часы до начала смены в факт и банк (0 — нет, 1 — да)",
    "count_late_departure": "Засчитывать часы после конца смены в факт и банк (0/1)",
    "min_session_min": "Минимальная длина сессии в минутах (меньше — игнорируется)",
    "auto_close_missing_out": "Закрывать смену плановым временем, если сотрудник не нажал «Ушёл с работы»",
    "grace_minutes": "Допустимое опоздание в минутах, при котором статус остаётся «без опоздания»",
    "night_start": "Начало ночного периода (ДН), ст. 96 ТК РФ",
    "night_end": "Конец ночного периода (ДН)",
    "late_by_raw_time": "Опоздание/ранний уход: 0 — по округлённому времени (как в табеле), 1 — по точной отметке",
    "timeoff_default_hours": "Сколько часов списывать из банка за «выходной за часы», "
                             "если смена сотрудника не определена (обычно 8 или 12)",
    "photo_retention_days": "Хранение фото ночных отчётов и электрокаров в днях (0 — хранить всегда)",
}

BOOL_RULES = {"count_early_arrival", "count_late_departure", "auto_close_missing_out", "late_by_raw_time"}
INT_RULES = {"round_step_min", "min_session_min", "grace_minutes", "photo_retention_days"}

# окно приёма отметок вокруг смены (техническая константа, не настраивается)
WINDOW_BEFORE_H = 4
WINDOW_AFTER_H = 6

# официальное «номинальное» дневное окно для ночных смен в внешнем контуре
OFFICIAL_DAY_START = "08:00"


def coerce_rules(raw: dict) -> dict:
    out: dict = {}
    for key, default in DEFAULT_RULES.items():
        val = raw.get(key, default)
        if key in BOOL_RULES:
            out[key] = val if isinstance(val, bool) else str(val).strip().lower() in {"1", "true", "yes", "on"}
        elif key in INT_RULES:
            try:
                out[key] = int(float(val))
            except (TypeError, ValueError):
                out[key] = int(default)
        else:
            out[key] = str(val)
    return out


def load_rules(db: Session) -> dict:
    raw = {s.key: s.value for s in db.scalars(select(Setting))}
    return coerce_rules(raw)


def rule_options() -> list[dict]:
    return [
        {"key": k, "value": DEFAULT_RULES[k], "description": RULE_DESCRIPTIONS.get(k, ""),
         "type": "bool" if k in BOOL_RULES else ("int" if k in INT_RULES else "str")}
        for k in DEFAULT_RULES
    ]


# ──────────────────────────── утилиты времени ────────────────────────────
def parse_hhmm(value: str) -> tuple[int, int]:
    try:
        h, m = value.split(":")
        return int(h), int(m)
    except Exception:
        return 0, 0


def at(day: dt.date, hhmm: str, plus_days: int = 0) -> dt.datetime:
    h, m = parse_hhmm(hhmm)
    return dt.datetime(day.year, day.month, day.day, h, m) + dt.timedelta(days=plus_days)


def round_dt(value: dt.datetime, step_min: int, mode: str) -> dt.datetime:
    step = max(1, int(step_min))
    midnight = value.replace(hour=0, minute=0, second=0, microsecond=0)
    mins = (value - midnight).total_seconds() / 60.0
    if mode == "floor":
        rounded = (int(mins) // step) * step
    elif mode == "ceil":
        rounded = int(mins) if mins % step == 0 else -((-int(mins)) // step) * step
    else:
        rounded = int((mins + step / 2.0) // step) * step
    return midnight + dt.timedelta(minutes=rounded)


def is_night_minute(minutes: int, ns: int, ne: int) -> bool:
    return (minutes >= ns or minutes < ne) if ns > ne else (ns <= minutes < ne)


def split_intervals(intervals: list[tuple[dt.datetime, dt.datetime]], night_start: str, night_end: str
                    ) -> tuple[float, float]:
    ns_h, ns_m = parse_hhmm(night_start)
    ne_h, ne_m = parse_hhmm(night_end)
    ns, ne = ns_h * 60 + ns_m, ne_h * 60 + ne_m
    day = night = 0.0
    for start, end in intervals:
        cur = start
        while cur < end:
            nxt = min(cur + dt.timedelta(hours=1), end)
            part = (nxt - cur).total_seconds() / 3600.0
            if is_night_minute(cur.hour * 60 + cur.minute, ns, ne):
                night += part
            else:
                day += part
            cur = nxt
    return round(day, 2), round(night, 2)


def split_day_night(start: dt.datetime, end: dt.datetime, night_start: str, night_end: str) -> tuple[float, float]:
    return split_intervals([(start, end)], night_start, night_end)


def shift_window(shift: Optional[ShiftType], date: dt.date, rules: dict):
    if not shift or shift.kind != "work" or not shift.start_time or not shift.end_time:
        return None, None
    start = at(date, shift.start_time)
    s_min = parse_hhmm(shift.start_time)[0] * 60 + parse_hhmm(shift.start_time)[1]
    e_min = parse_hhmm(shift.end_time)[0] * 60 + parse_hhmm(shift.end_time)[1]
    plus = 1 if (shift.overnight or e_min <= s_min) else 0
    return start, at(date, shift.end_time, plus)


def official_window(shift: Optional[ShiftType], date: dt.date) -> tuple[Optional[dt.datetime], Optional[dt.datetime]]:
    """Окно, которое внешний (официальный) контур считает «уже оплаченным» днём date:
    для обычной смены — её часы; для ночной — номинальное дневное окно той же длительности."""
    if not shift or shift.kind != "work":
        return None, None
    if not shift.overnight:
        return shift_window(shift, date, {})
    start = at(date, OFFICIAL_DAY_START)
    return start, start + dt.timedelta(hours=shift.planned_hours)


def entry_shift(db: Session, entry: Optional[ScheduleEntry],
                catalog: Optional[ShiftCatalog] = None):
    """Смена ячейки — такой, какой она была в дату ячейки.

    Если словарь смен потом изменили (другие часы, другое название), отработанные
    дни считаются по прежним значениям: их хранит история ревизий (ShiftRevision).

    `catalog` — предзагруженный словарь смен и ревизий: в циклах по ячейкам
    (сетка месяца, пересчёт диапазона) убирает запрос на каждую ячейку.
    """
    if entry is None:
        return None
    rel = catalog.by_id(entry.shift_type_id) if catalog is not None else None
    if rel is None:
        rel = entry.shift_type
        if rel is None or rel.id != entry.shift_type_id:
            rel = db.get(ShiftType, entry.shift_type_id)
    return view_at(db, rel, entry.date, catalog=catalog)


# ──────────────────── частичное отсутствие (отпросился на пару часов) ────────────────────
def authorized_gap(entry: Optional[ScheduleEntry], date: dt.date) -> Optional[tuple[dt.datetime, dt.datetime]]:
    """Согласованное окно, когда сотрудник НЕ работает внутри своей смены
    («отпросился с 14:00 до 16:00»). Окно может переходить полночь (ночная смена)."""
    if entry is None:
        return None
    ft, ut = (entry.from_time or "").strip(), (entry.until_time or "").strip()
    if not ft or not ut:
        return None
    try:
        f_h, f_m = (int(x) for x in ft.split(":"))
        u_h, u_m = (int(x) for x in ut.split(":"))
    except ValueError:
        return None
    start = dt.datetime(date.year, date.month, date.day, f_h, f_m)
    plus = 1 if (u_h * 60 + u_m) <= (f_h * 60 + f_m) else 0
    end = dt.datetime(date.year, date.month, date.day, u_h, u_m) + dt.timedelta(days=plus)
    if end <= start:
        return None
    return start, end


def subtract_holes(window: Optional[tuple[dt.datetime, dt.datetime]], holes) -> list[tuple[dt.datetime, dt.datetime]]:
    """Окно плана минус согласованные отсутствия → сегменты, которые нужно отработать."""
    if not window:
        return []
    out = [window]
    for hole in holes:
        new = []
        for a, b in out:
            hs, he = hole
            if b <= hs or a >= he:
                new.append((a, b))
                continue
            if a < hs:
                new.append((a, hs))
            if b > he:
                new.append((he, b))
        out = new
    return [(a, b) for a, b in out if b > a]


def plan_segments(shift, date: dt.date, entry: Optional[ScheduleEntry], rules: dict
                  ) -> list[tuple[dt.datetime, dt.datetime]]:
    """Сегменты планового окна дня с учётом согласованного отсутствия."""
    ws, we = shift_window(shift, date, rules) if (shift and shift.kind == "work") else (None, None)
    if not ws:
        return []
    gap = authorized_gap(entry, date)
    return subtract_holes((ws, we), [gap] if gap else [])


def official_segments(shift, date: dt.date, entry: Optional[ScheduleEntry]
                      ) -> list[tuple[dt.datetime, dt.datetime]]:
    """Сегменты официального (уже оплаченного) окна дня минус согласованное отсутствие."""
    ow_s, ow_e = official_window(shift, date) if (shift and shift.kind == "work") else (None, None)
    if not ow_s:
        return []
    gap = authorized_gap(entry, date)
    return subtract_holes((ow_s, ow_e), [gap] if gap else [])


def gap_hours(entry: Optional[ScheduleEntry], date: dt.date) -> float:
    """Длительность согласованного отсутствия в часах (точно, без округления)."""
    gap = authorized_gap(entry, date)
    return round((gap[1] - gap[0]).total_seconds() / 3600.0, 2) if gap else 0.0


def round_hours(value: float, rules: dict) -> float:
    """Округление часов по шагу учёта (обычно кратно часу)."""
    step_min = max(1, int(rules.get("round_step_min") or 60))
    step_h = step_min / 60.0
    mode = rules.get("round_mode", "nearest")
    n = value / step_h
    if mode == "floor":
        n = int(n // 1)
    elif mode == "ceil":
        n = int(n) if abs(n - int(n)) < 1e-9 else int(n) + 1
    else:
        n = int(n + 0.5)
    return round(n * step_h, 2)


# ──────────────────────────── сессии и куски ────────────────────────────
def pair_sessions(punches: list[Punch], rules: dict) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    ordered = sorted(punches, key=lambda p: p.ts)
    sessions: list[dict] = []
    open_in: Optional[Punch] = None
    for p in ordered:
        if p.kind == "IN":
            if open_in is None:
                open_in = p
            else:
                warnings.append(f"Повторная отметка «Пришёл» в {p.ts:%H:%M} — смена уже открыта с {open_in.ts:%H:%M}")
        else:
            if open_in is None:
                warnings.append(f"Отметка «Ушёл» в {p.ts:%H:%M} без «Пришёл» — проигнорирована")
                continue
            sessions.append({"in": open_in, "out": p})
            open_in = None
    if open_in is not None:
        sessions.append({"in": open_in, "out": None})
    return sessions, warnings


def _merge_intervals(intervals):
    """Склеить пересекающиеся интервалы (чтобы часы не считались дважды)."""
    out = []
    for a, b in sorted(intervals, key=lambda x: x[0]):
        if out and a <= out[-1][1]:
            if b > out[-1][1]:
                out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return out


def _hours_of(intervals) -> float:
    return round(sum((b - a).total_seconds() / 3600.0 for a, b in intervals), 2)


def _subtract(intervals, hole):
    out = []
    hs, he = hole
    for a, b in intervals:
        if b <= hs or a >= he:
            out.append((a, b))
            continue
        if a < hs:
            out.append((a, hs))
        if b > he:
            out.append((he, b))
    return out


def day_pieces(db: Session, emp: Employee, date: dt.date, rules: dict,
               index=None, catalog: Optional[ShiftCatalog] = None,
               entry_map: Optional[dict] = None, punches_by_day: Optional[dict] = None,
               cfg: Optional[dict] = None, employed: Optional[bool] = None) -> dict:
    """
    Куски отработанного времени, относящиеся к дню date:
      pieces      — для факта/банка: плановые куски своего дня + «свободный» остаток сессии,
                    начавшейся в этот день; хвост, накрытый планом следующего дня, уходит туда;
      worked_cal  — пересечения сессий с календарным днём (для внешнего контура выплаты);
      plans       — планы дней date-1..date+1 (окна для разреза и статусов).
    """
    plans = {}
    for off in (-1, 0, 1):
        d = date + dt.timedelta(days=off)
        entry, shift = effective_entry_shift(db, emp.id, d, emp, index=index,
                                             catalog=catalog, entry_map=entry_map,
                                             cfg=cfg, employed=employed)
        ws, we = shift_window(shift, d, rules) if shift and shift.kind == "work" else (None, None)
        plans[d] = {"entry": entry, "shift": shift, "ws": ws, "we": we,
                    "segments": plan_segments(shift, d, entry, rules),
                    "gap": authorized_gap(entry, d), "auth_hours": gap_hours(entry, d),
                    "partial": partial_window(entry)}

    if punches_by_day is not None:
        # отметки уже выбраны одним запросом на диапазон: собираем окно date-1..date+1
        mine = punches_by_day.get(emp.id) or {}
        punches = []
        for off in (-1, 0, 1):
            punches.extend(mine.get(date + dt.timedelta(days=off), ()))
        punches.sort(key=lambda x: x.ts)
    else:
        lo = dt.datetime(date.year, date.month, date.day) - dt.timedelta(days=1)
        hi = dt.datetime(date.year, date.month, date.day) + dt.timedelta(days=2)
        punches = list(db.scalars(select(Punch).where(
            Punch.employee_id == emp.id, Punch.ts >= lo, Punch.ts < hi).order_by(Punch.ts)))
    sessions, warnings = pair_sessions(punches, rules)

    pieces: list[dict] = []
    worked_cal: list[tuple[dt.datetime, dt.datetime]] = []
    day_start = dt.datetime(date.year, date.month, date.day)
    day_end = day_start + dt.timedelta(days=1)
    unclosed = False

    for sess in sessions:
        raw_in = sess["in"].ts
        raw_out = sess["out"].ts if sess["out"] else None
        raw_out_orig = raw_out
        auto_closed = False
        if raw_out is None:
            host_day = None
            for d, pl in plans.items():
                if pl["ws"] and pl["we"] and pl["ws"] - dt.timedelta(hours=WINDOW_BEFORE_H) <= raw_in <= pl["we"] + dt.timedelta(hours=WINDOW_AFTER_H):
                    host_day = d
                    break
            if host_day is None:
                host_day = raw_in.date()
            host_segs = plans.get(host_day, {}).get("segments") or []
            host_we = host_segs[-1][1] if host_segs else plans.get(host_day, {}).get("we")
            if host_we and rules["auto_close_missing_out"]:
                raw_out = max(host_we, raw_in)
                raw_out_orig = None
                auto_closed = True
                warnings.append(f"Нет отметки «Ушёл с работы» — смена закрыта плановым временем {raw_out:%H:%M}")
            else:
                unclosed = True
                warnings.append("Смена не закрыта: сотрудник не нажал «Ушёл с работы»")
                continue
        if raw_out <= raw_in:
            warnings.append("Отметка «Ушёл» раньше «Пришёл» — сессия пропущена")
            continue
        rs = round_dt(raw_in, rules["round_step_min"], rules["round_mode"])
        re = round_dt(raw_out, rules["round_step_min"], rules["round_mode"])
        if re <= rs:
            warnings.append("После округления сессия обнулилась")
            continue

        inter = (max(rs, day_start), min(re, day_end))
        if inter[0] < inter[1]:
            worked_cal.append(inter)

        rem = [(rs, re)]
        for d in (date - dt.timedelta(days=1), date, date + dt.timedelta(days=1)):
            pl = plans[d]
            segments = pl.get("segments") or ([(pl["ws"], pl["we"])] if pl.get("ws") else [])
            for hole in segments:
                new_rem = []
                for a, b in rem:
                    cut = (max(a, hole[0]), min(b, hole[1]))
                    if cut[0] < cut[1]:
                        pieces.append({"start": cut[0], "end": cut[1], "kind": "plan", "day": d,
                                       "seg_start": hole[0].isoformat(timespec="minutes"),
                                       "seg_end": hole[1].isoformat(timespec="minutes"),
                                       "sess_in": rs, "sess_out": re, "raw_in": raw_in, "raw_out": raw_out,
                                       "auto_closed": auto_closed,
                                       "note": sess["out"].note if sess["out"] else ""})
                    new_rem.extend(_subtract([(a, b)], hole))
                rem = new_rem
        for a, b in rem:
            pieces.append({"start": a, "end": b, "kind": "cal", "day": rs.date(),
                           "sess_in": rs, "sess_out": re, "raw_in": raw_in, "raw_out": raw_out,
                           "auto_closed": auto_closed,
                           "note": sess["out"].note if sess["out"] else ""})

    # «Свободные» куски (вне плановых окон) фильтруем по настройкам, но окно берём
    # для ТОГО дня, к которому кусок отнесён — иначе переработка сегодняшнего вечера
    # ошибочно принималась за «ранний приход до завтрашней смены» и терялась.
    for p in pieces:
        if p["kind"] != "cal":
            continue
        pl = plans.get(p["day"]) or {}
        p_ws, p_we = pl.get("ws"), pl.get("we")
        if p_ws and p["end"] <= p_ws and not rules["count_early_arrival"]:
            p["drop"] = True
        if p_we and p["start"] >= p_we and not rules["count_late_departure"]:
            p["drop"] = True
        if (p["end"] - p["start"]).total_seconds() / 60.0 < rules["min_session_min"]:
            p["drop"] = True
    pieces = [p for p in pieces if not p.get("drop")]
    mine = [p for p in pieces if p["day"] == date]
    # склейка полностью пересекающихся дублей
    mine.sort(key=lambda p: p["start"])
    merged: list[dict] = []
    for pc in mine:
        if merged and pc["start"] < merged[-1]["end"] and pc["kind"] == merged[-1]["kind"]:
            if pc["end"] > merged[-1]["end"]:
                merged[-1]["end"] = pc["end"]
            warnings.append("Пересекающиеся отметки объединены (двойные часы исключены)")
            continue
        merged.append(pc)
    return {"pieces": merged, "worked_cal": worked_cal, "plans": plans,
            "warnings": warnings, "unclosed": unclosed}


# ──────────────────────────── расчёт дня ────────────────────────────
def compute_day(employee: Employee, date: dt.date, entry: Optional[ScheduleEntry],
                data: dict, rules: dict, shift: Optional[ShiftType] = None) -> dict:
    rules = coerce_rules(rules)
    plans = data["plans"]
    plan = plans.get(date, {})
    if shift is None:
        shift = plan.get("shift")
    ws, we = plan.get("ws"), plan.get("we")
    if entry is None:
        entry = plan.get("entry")
    pieces = data["pieces"]
    note = entry.note if entry else ""

    # план дня = окно смены минус согласованное отсутствие («отпросился с 14:00 до 16:00»)
    segments = plan.get("segments")
    if segments is None:
        segments = plan_segments(shift, date, entry, rules) if (shift and shift.kind == "work") else []
    gap = plan.get("gap") if "gap" in plan else authorized_gap(entry, date)
    partial = plan.get("partial") if "partial" in plan else partial_window(entry)
    auth_total = gap_hours(entry, date)

    row: dict = {
        "employee_id": employee.id, "date": date,
        "shift_type_id": shift.id if shift else None,
        "code": (shift.tzh_code or shift.display_code) if shift else "НЕ",
        "planned_hours": 0.0, "fact_hours": 0.0, "day_hours": 0.0, "night_hours": 0.0,
        "ot_hours": 0.0, "ot_note": "", "deficit_hours": 0.0, "timeoff_hours": 0.0,
        "pay_ot_day": 0.0, "pay_ot_night": 0.0, "late_hours": 0.0, "early_hours": 0.0,
        "pay_ot_day2": 0.0, "pay_ot_night2": 0.0, "double_reason": "",
        "unused_hours": 0.0, "gap_hours": 0.0, "auth_hours": 0.0,
        "fact_in": None, "fact_out": None, "planned_start": ws, "planned_end": we,
        "status": "off", "detail_json": "[]", "note": note or "",
    }
    detail: dict = {"sessions": [], "warnings": list(data["warnings"]),
                    "plan_segments": [[a.isoformat(timespec="minutes"), b.isoformat(timespec="minutes")]
                                      for a, b in segments],
                    "gaps": [], "partial": None}

    is_work = bool(shift and shift.kind == "work")

    if (not is_work and shift and shift.kind == "absence"
            and shift.code not in ("OFF", "TIMEOFF_HOURS") and pieces):
        row["status"] = "absence"
        row["fact_hours"] = 0.0
        detail["warnings"].append("Отметки в день больничного/отпуска не учитываются в часах")
        row["detail_json"] = json.dumps(detail, ensure_ascii=False)
        return row

    # ── сколько согласованного отсутствия реально использовано ──
    auth_used = auth_total
    if gap and auth_total:
        worked_in_gap = _merge_intervals([
            (max(a, gap[0]), min(b, gap[1])) for a, b in data["worked_cal"]
            if min(b, gap[1]) > max(a, gap[0])])
        used_gap = _hours_of(worked_in_gap)
        auth_used = round(max(0.0, auth_total - used_gap), 2)
        if used_gap > 0:
            detail["warnings"].append(
                f"Согласованное отсутствие использовано не полностью: сотрудник работал "
                f"{gap[0]:%H:%M}–{gap[1]:%H:%M} {used_gap:g} ч")
    row["auth_hours"] = auth_used
    if partial and auth_total:
        detail["partial"] = {
            "from": partial[0], "until": partial[1],
            "reason": (partial[2].name if partial[2] else ""),
            "reason_code": (partial[2].code if partial[2] else ""),
            "hours": auth_total, "used_hours": auth_used,
            "deduct_bank": bool(partial[2] and partial[2].deduct_from_bank),
        }

    planned_hours = shift.planned_hours if is_work else 0.0
    if is_work and auth_used:
        planned_hours = round(max(0.0, planned_hours - auth_used), 2)
    row["planned_hours"] = planned_hours

    # ── внешний контур: начисления по календарному дню минус официальное окно ──
    # день двойной оплаты (производственный календарь / ВИП-гость): переработки
    # идут кодами ДЯ2/ДН2 (двойной тариф); часы внутри официального окна как
    # обычно — стоимость дня не меняется, двойные только переработки
    double_reason = str(data.get("double_reason") or "")
    row["double_reason"] = double_reason
    if shift is None or not (shift.kind == "absence" and shift.code not in ("OFF", "TIMEOFF_HOURS")):
        ow_segs = official_segments(shift, date, entry) if is_work else []
        extra = data["worked_cal"]
        for seg in ow_segs:
            extra = _subtract(extra, seg)
        # сколько официального окна НЕ отработано (опоздания, ранние уходы);
        # согласованное отсутствие из окна исключено: за него часы снимаются с банка, а не из зарплаты;
        # для неявок (отметок нет) списание не создаём: их официальный табель оформляет отдельно
        if pieces and ow_segs:
            worked_in_window = _merge_intervals([
                (max(a, s0), min(b, s1)) for a, b in data["worked_cal"] for s0, s1 in ow_segs
                if min(b, s1) > max(a, s0)])
            total_w = _hours_of(ow_segs)
            done_w = _hours_of(worked_in_window)
            row["unused_hours"] = round(max(0.0, total_w - done_w), 2)
        if extra:
            pd, pn = split_intervals(extra, rules["night_start"], rules["night_end"])
            if double_reason:
                row["pay_ot_day2"], row["pay_ot_night2"] = pd, pn
            else:
                row["pay_ot_day"], row["pay_ot_night"] = pd, pn

    if not pieces:
        if is_work:
            if date > local_date():
                row["status"] = "planned"
            elif auth_used and auth_used >= planned_hours:
                # весь день согласованно отсутствовал (отпросился на всю смену)
                row["status"] = "absence"
                if partial and partial[2] is not None:
                    row["code"] = partial[2].tzh_code or partial[2].display_code or row["code"]
                    if partial[2].deduct_from_bank:
                        row["timeoff_hours"] = round_hours(auth_used, rules)
                        detail["warnings"].append(
                            f"Согласованное отсутствие {partial[0]}–{partial[1]}: "
                            f"списано {row['timeoff_hours']:g} ч из банка часов")
                    else:
                        detail["warnings"].append(
                            f"Согласованное отсутствие {partial[0]}–{partial[1]} на всю смену")
            else:
                row["status"] = "no_punch"
                row["deficit_hours"] = planned_hours
                detail["warnings"].append("Отметок нет — в табеле неявка (НН), требуется ручная корректировка")
        elif shift and shift.code == "TIMEOFF_HOURS":
            default_off = data.get("timeoff_default")
            row["timeoff_hours"] = round(float(default_off if default_off else
                                                 (rules.get("timeoff_default_hours") or 8)), 2)
            row["status"] = "absence"
            detail["warnings"].append(
                f"Выходной за ранее отработанные часы: списано {row['timeoff_hours']:g} ч из банка часов")
        elif shift and not shift.is_working:
            row["status"] = "off" if shift.is_default_off else "absence"
        row["code"] = row["code"] or ((shift.tzh_code or shift.display_code) if shift else "НЕ")
        row["detail_json"] = json.dumps(detail, ensure_ascii=False)
        return row

    intervals = [(p["start"], p["end"]) for p in pieces]
    total = round(sum((b - a).total_seconds() / 3600.0 for a, b in intervals), 2)
    day_h, night_h = split_intervals(intervals, rules["night_start"], rules["night_end"])
    fact_in = min(p["raw_in"] for p in pieces)
    outs = [p["raw_out"] for p in pieces if p.get("raw_out")]
    fact_out = max(outs) if outs else max(p["end"] for p in pieces)
    row.update({"fact_hours": total, "day_hours": day_h, "night_hours": night_h,
                "fact_in": fact_in, "fact_out": fact_out})

    ot_notes = [p["note"] for p in pieces if p.get("note")]
    if ot_notes:
        row["ot_note"] = " | ".join(dict.fromkeys(ot_notes))

    # ── статусы и списания по плановым сегментам ──
    if is_work:
        plan_pieces = [p for p in pieces if p["kind"] == "plan"]
        grace = dt.timedelta(minutes=rules["grace_minutes"])
        min_gap = dt.timedelta(minutes=max(1, rules["min_session_min"]))
        late_h = early_h = gap_h = 0.0
        late_ref = early_ref = None
        inner_gaps: list[tuple[dt.datetime, dt.datetime]] = []

        for seg in segments:
            cov = _merge_intervals([(max(p["start"], seg[0]), min(p["end"], seg[1]))
                                    for p in plan_pieces
                                    if p["end"] > seg[0] and p["start"] < seg[1]])
            if not cov:
                # сегмент не отработан совсем — это недоработка, а не опоздание
                continue
            if cov[0][0] - seg[0] > grace:
                late_h += (cov[0][0] - seg[0]).total_seconds() / 3600.0
                late_ref = late_ref or (cov[0][0], seg[0])
            if seg[1] - cov[-1][1] > grace:
                early_h += (seg[1] - cov[-1][1]).total_seconds() / 3600.0
                early_ref = early_ref or (cov[-1][1], seg[1])
            for (a1, b1), (a2, _) in zip(cov, cov[1:]):
                if a2 - b1 > min_gap:
                    inner_gaps.append((b1, a2))

        if rules.get("late_by_raw_time") and plan_pieces and segments:
            raw_ins = [p["raw_in"] for p in plan_pieces]
            raw_outs = [p["raw_out"] for p in plan_pieces if p.get("raw_out")]
            if raw_ins and min(raw_ins) > segments[0][0] + grace:
                late_h = max(late_h, (min(raw_ins) - segments[0][0]).total_seconds() / 3600.0)
                late_ref = late_ref or (min(raw_ins), segments[0][0])
            if raw_outs and max(raw_outs) < segments[-1][1] - grace:
                early_h = max(early_h, (segments[-1][1] - max(raw_outs)).total_seconds() / 3600.0)
                early_ref = early_ref or (max(raw_outs), segments[-1][1])

        late, early = late_h > 0, early_h > 0
        if late and late_ref:
            row["late_hours"] = round(late_h, 2)
            detail["warnings"].append(
                f"Опоздание на {int(round(late_h * 60))} мин (план {late_ref[1]:%H:%M})")
        if early and early_ref:
            row["early_hours"] = round(early_h, 2)
            detail["warnings"].append(
                f"Ранний уход на {int(round(early_h * 60))} мин (план {early_ref[1]:%H:%M})")
        if inner_gaps:
            gap_h = _hours_of(inner_gaps)
            row["gap_hours"] = round(gap_h, 2)
            detail["gaps"] = [[a.isoformat(timespec="minutes"), b.isoformat(timespec="minutes")]
                              for a, b in inner_gaps]
            detail["warnings"].append(
                "Перерыв в работе " + ", ".join(f"{a:%H:%M}–{b:%H:%M}" for a, b in inner_gaps)
                + f" ({gap_h:g} ч) — не согласован, часы не начислены")

        # согласованное отсутствие: план уменьшен, отклонений нет, часы (если нужно) — с банка
        if partial and auth_used:
            reason = partial[2]
            if reason is not None and reason.deduct_from_bank:
                row["timeoff_hours"] = round_hours(auth_used, rules)
                detail["warnings"].append(
                    f"Согласованное отсутствие {partial[0]}–{partial[1]} ({auth_used:g} ч): "
                    f"списано {row['timeoff_hours']:g} ч из банка часов")
            else:
                detail["warnings"].append(
                    f"Согласованное отсутствие {partial[0]}–{partial[1]} ({auth_used:g} ч) — "
                    f"план уменьшен, опозданием и ранним уходом не считается")

        diff = round(total - planned_hours, 2)
        if diff > 0:
            row["ot_hours"] = diff
        elif diff < 0:
            row["deficit_hours"] = round(-diff, 2)
        if data["unclosed"]:
            row["status"] = "unclosed"
        elif late and early:
            row["status"] = "late_early"
        elif late:
            row["status"] = "late"
        elif early:
            row["status"] = "early"
        elif inner_gaps:
            row["status"] = "gap"
        else:
            row["status"] = "ok"
    else:
        # работа в выходной / в «выходной за часы» / вне графика
        row["ot_hours"] = total
        row["code"] = "Я" if shift and shift.code in ("OFF", "TIMEOFF_HOURS") else "НЕ"
        row["status"] = "work_off" if shift and shift.code in ("OFF", "TIMEOFF_HOURS") else "work_no_plan"
        if shift and shift.code == "TIMEOFF_HOURS":
            row["timeoff_hours"] = 0.0
            detail["warnings"].append("Выходной за часы отменён: сотрудник работал, часы начислены, банк не списывается")
        elif shift and shift.code == "OFF":
            detail["warnings"].append("Работа в выходной день: часы начислены как переработка")
        else:
            detail["warnings"].append("Смены в графике нет — часы посчитаны по отметкам, требуется решение менеджера")
        if data["unclosed"]:
            row["status"] = "unclosed"

    for p in pieces:
        detail["sessions"].append({
            "in_raw": p["raw_in"].isoformat(timespec="minutes"),
            "out_raw": (p["raw_out"] or p["end"]).isoformat(timespec="minutes"),
            "in_rounded": p["start"].isoformat(timespec="minutes"),
            "out_rounded": p["end"].isoformat(timespec="minutes"),
            "hours": round((p["end"] - p["start"]).total_seconds() / 3600.0, 2),
            "day": split_intervals([(p["start"], p["end"])], rules["night_start"], rules["night_end"])[0],
            "night": split_intervals([(p["start"], p["end"])], rules["night_start"], rules["night_end"])[1],
            "piece": p["kind"], "auto_closed": p["auto_closed"], "note": p.get("note", ""),
            "out_punch_id": None,
        })
    row["detail_json"] = json.dumps(detail, ensure_ascii=False)
    return row


# ──────────────────────────── пересчёт ────────────────────────────
def recalc_day(db: Session, employee: Employee, date: dt.date, rules: Optional[dict] = None,
               entry: Optional[ScheduleEntry] = None, commit: bool = True,
               index=None, catalog: Optional[ShiftCatalog] = None,
               entry_map: Optional[dict] = None, punches_by_day: Optional[dict] = None,
               double_ctx=None, row_map: Optional[dict] = None,
               base_cfg: Optional[dict] = None, employed: Optional[bool] = None) -> TimesheetRow:
    """Пересчитать и сохранить строку дня.

    Параметры index/catalog/entry_map/punches_by_day/double_ctx/row_map —
    предзагруженные данные: обязательны в циклах (recalc_range), иначе на каждый
    день уходит около десяти точечных запросов.
    """
    rules = coerce_rules(rules or load_rules(db))
    data = day_pieces(db, employee, date, rules, index=index, catalog=catalog,
                      entry_map=entry_map, punches_by_day=punches_by_day,
                      cfg=base_cfg, employed=employed)
    # день двойной оплаты (календарь/ВИП) — переработки пойдут кодами ДЯ2/ДН2
    from .doublepay import reason_for
    data["double_reason"] = reason_for(db, employee, date, cfg=base_cfg, index=index,
                                       ctx=double_ctx)
    if entry is None:
        entry = data["plans"][date]["entry"]
    shift = entry_shift(db, entry, catalog=catalog) if entry else data["plans"][date]["shift"]
    if shift is not None and shift.code == "TIMEOFF_HOURS":
        # «выходной за часы» списывает столько, сколько длилась бы смена по графику
        from .base_schedule import base_shift
        virtual = base_shift(db, employee, date, cfg=base_cfg, employed=employed,
                             index=index, catalog=catalog)
        if virtual is not None and virtual.kind == "work":
            data["timeoff_default"] = round(virtual.planned_hours, 2)
    computed = compute_day(employee, date, entry, data, rules, shift=shift)

    key = (employee.id, date)
    if row_map is not None:
        row = row_map.get(key)
    else:
        row = db.scalar(select(TimesheetRow).where(
            TimesheetRow.employee_id == employee.id, TimesheetRow.date == date))
    if row is None:
        row = TimesheetRow(employee_id=employee.id, date=date)
        db.add(row)
        if row_map is not None:
            row_map[key] = row
    for k, v in computed.items():
        setattr(row, k, v)
    row.updated_at = utcnow()
    if commit:
        db.commit()
        db.refresh(row)
    return row


def recalc_range(db: Session, start: dt.date, end: dt.date, employee_ids: Optional[list[int]] = None,
                 commit: bool = True) -> int:
    """Пересчитать диапазон.

    Все справочники и сырые данные грузятся ОДИН раз на диапазон: без этого на
    каждую пару «сотрудник × день» уходило ~10 точечных запросов (месяц на 50
    сотрудниках — около 12 тысяч запросов и 5 секунд).
    """
    from .base_schedule import BlockIndex, base_shift, load_base_config
    from .doublepay import DoubleContext

    rules = load_rules(db)
    cfg = load_base_config(db)
    emps = db.scalars(select(Employee).where(Employee.deleted_at.is_(None))).all()
    if employee_ids:
        wanted = set(employee_ids)
        emps = [e for e in emps if e.id in wanted]
    if not emps:
        return 0
    emp_ids = [e.id for e in emps]

    from .employment import employed_on, periods_of

    catalog = ShiftCatalog.load(db)
    index = BlockIndex.load(db, emp_ids)
    double_ctx = DoubleContext.load(db, start, end)
    # периоды работы — одним запросом на всех: иначе is_employed() ходит в БД на каждый день
    periods_by_emp: dict[int, list] = {}
    if len(emp_ids) == 1:
        periods_by_emp[emp_ids[0]] = periods_of(db, emp_ids[0])
    else:
        from .models import EmploymentPeriod
        for p in db.scalars(select(EmploymentPeriod).where(
                EmploymentPeriod.employee_id.in_(emp_ids))):
            periods_by_emp.setdefault(p.employee_id, []).append(p)
    # окно на день шире в обе стороны: план и отметки соседних дней участвуют в разрезе сессий
    lo, hi = start - dt.timedelta(days=1), end + dt.timedelta(days=1)
    entry_map: dict[tuple[int, dt.date], ScheduleEntry] = {}
    for e in db.scalars(select(ScheduleEntry).where(
            ScheduleEntry.employee_id.in_(emp_ids),
            ScheduleEntry.date >= lo, ScheduleEntry.date <= hi)):
        entry_map[(e.employee_id, e.date)] = e
    punches_by_day: dict[int, dict[dt.date, list[Punch]]] = {}
    for p in db.scalars(select(Punch).where(
            Punch.employee_id.in_(emp_ids),
            Punch.ts >= dt.datetime(lo.year, lo.month, lo.day),
            Punch.ts < dt.datetime(hi.year, hi.month, hi.day) + dt.timedelta(days=1))):
        punches_by_day.setdefault(p.employee_id, {}).setdefault(p.ts.date(), []).append(p)
    for mine in punches_by_day.values():
        for items in mine.values():
            items.sort(key=lambda x: x.ts)
    row_map: dict[tuple[int, dt.date], TimesheetRow] = {
        (r.employee_id, r.date): r for r in db.scalars(select(TimesheetRow).where(
            TimesheetRow.employee_id.in_(emp_ids),
            TimesheetRow.date >= start, TimesheetRow.date <= end))}

    count = 0
    day = start
    while day <= end:
        for emp in emps:
            has_entry = (emp.id, day) in entry_map
            has_punch = bool(punches_by_day.get(emp.id, {}).get(day))
            employed = employed_on(periods_by_emp.get(emp.id, ()), day) \
                if periods_by_emp.get(emp.id) else None
            if (not has_entry and not has_punch
                    and base_shift(db, emp, day, cfg, employed=employed,
                                   index=index, catalog=catalog) is None):
                continue
            recalc_day(db, emp, day, rules=rules, commit=False, index=index, catalog=catalog,
                       entry_map=entry_map, punches_by_day=punches_by_day,
                       double_ctx=double_ctx, row_map=row_map,
                       base_cfg=cfg, employed=employed)
            count += 1
        day += dt.timedelta(days=1)
    if commit:
        db.commit()
    return count


def month_bounds(year: int, month: int) -> tuple[dt.date, dt.date]:
    first = dt.date(year, month, 1)
    nxt = dt.date(year + 1, 1, 1) if month == 12 else dt.date(year, month + 1, 1)
    return first, nxt - dt.timedelta(days=1)


# ──────────────────────────── банк часов (накопительно) ────────────────────────────
def bank_as_of(db: Session, employee: Employee, as_of: dt.date) -> float:
    """Банк часов на дату: стартовый баланс + переработки/списания + ручные корректировки."""
    rows = db.scalars(select(TimesheetRow).where(
        TimesheetRow.employee_id == employee.id, TimesheetRow.date <= as_of)).all()
    delta = sum(r.ot_hours - r.timeoff_hours - r.deficit_hours for r in rows)
    delta += sum(a.hours for a in db.scalars(select(BankAdjustment).where(
        BankAdjustment.employee_id == employee.id, BankAdjustment.effective_date <= as_of)))
    return round(employee.balance_hours + delta, 2)


# ──────────────────────────── зачёт переработок со сквозным долгом ────────────────────────────
# корзины начислений к выплате: (ключ кредита, код в реестре, множитель тарифа).
# Порядок списания: сначала одинарные дневные, потом ночные, и только затем двойные —
# «двойные» часы берегутся: списание по возможности гасится обычными днями 1=1.
PAY_BUCKETS = (("dya", "ДЯ", 1.0), ("dn", "ДН", 1.0),
               ("dya2", "ДЯ2", 2.0), ("dn2", "ДН2", 2.0))


def _credit_item(c: dict) -> dict:
    item = {"date": c["date"]}
    for key, _, _ in PAY_BUCKETS:
        item[key] = round(float(c.get(key) or 0.0), 2)
    return item


def _credit_left(item: dict) -> bool:
    return any(item[key] > 0 for key, _, _ in PAY_BUCKETS)


def _eat_bucket(item: dict, key: str, mult: float, amount: float
                ) -> tuple[float, float, float]:
    """Списать из корзины key столько, сколько можно покрыть суммой `amount`
    (в одинарных часах оплаты). Двойные часы съедаются ВПОЛОВИНУ: чтобы снять
    8 часов оплаты, достаточно убрать 4 часа ДЯ2 — стоимость дня одинаковая,
    двойные только переработки.
    Возвращает (остаток к списанию, снято оплаты в одинарных, снято часов кода)."""
    avail = item.get(key, 0.0)
    if avail <= 0 or amount <= 0:
        return amount, 0.0, 0.0
    pay_take = min(amount, round(avail * mult, 2))
    code_take = round(pay_take / mult, 2)
    if abs(avail - code_take) < 1e-9:
        code_take = avail                       # съедаем корзину без float-пыли
    item[key] = round(avail - code_take, 2)
    return round(amount - pay_take, 2), pay_take, code_take


def _log_take(log: list[dict], debit_date: str, kind: str, credit_date,
              label: str, pay_take: float, code_take: float) -> None:
    log.append({"debit_date": debit_date, "kind": kind, "credit_date": credit_date,
                "from": label, "hours": pay_take, "credit_hours": code_take})


def settle_overtime(credits: list[dict], debits: list[dict], carry_in: float = 0.0
                    ) -> tuple[list[dict], list[dict], dict]:
    """
    Хронологический зачёт: списания гасят самые ранние переработки — сначала дневные
    одинарные часы (ДЯ), затем ночные (ДН), затем двойные (ДЯ2/ДН2 — вполовину:
    8 часов оплаты = 4 часа ДЯ2). Непокрытое списание становится ДОЛГОМ (carry)
    и гасит переработки следующих месяцев (долг тоже съедает двойные часы вполовину).
    credits: [{"date","dya","dn","dya2","dn2"}] — ключи «2» можно не передавать;
    debits:  [{"date","hours","kind"}] — часы списания всегда в одинарном эквиваленте.
    Возвращает (log, remain, totals):
      totals.pay_total — сумма к выплате в одинарных часах (ДЯ2/ДН2 считаются как 2),
      totals.pay_hours — сколько всего часов кодов осталось в реестре.
    """
    pool: list[dict] = []
    debt = round(carry_in, 2)
    log: list[dict] = []
    dates = sorted({c["date"] for c in credits} | {d["date"] for d in debits})
    for day in dates:
        for c in sorted([x for x in credits if x["date"] == day], key=lambda x: x["date"]):
            item = _credit_item(c)
            if debt > 0:
                # долг прошлых периодов гасит это начисление (корзины по порядку)
                for key, label, mult in PAY_BUCKETS:
                    if debt <= 0:
                        break
                    debt, pay_take, code_take = _eat_bucket(item, key, mult, debt)
                    if pay_take > 0:
                        _log_take(log, "долг прошлых периодов", "Долг", c["date"],
                                  label, pay_take, code_take)
            if _credit_left(item):
                pool.append(item)
        for deb in sorted([x for x in debits if x["date"] == day], key=lambda x: x["date"]):
            left = round(float(deb["hours"]), 2)
            # корзина за корзиной: внутри корзины — хронологически (pool уже отсортирован)
            for key, label, mult in PAY_BUCKETS:
                if left <= 0:
                    break
                for cred in pool:
                    if left <= 0:
                        break
                    left, pay_take, code_take = _eat_bucket(cred, key, mult, left)
                    if pay_take > 0:
                        _log_take(log, deb["date"], deb["kind"], cred["date"],
                                  label, pay_take, code_take)
            if left > 0:
                debt = round(debt + left, 2)
                log.append({"debit_date": deb["date"], "kind": deb["kind"], "credit_date": None,
                            "from": "—", "hours": left, "credit_hours": left, "uncovered": True,
                            "note": "долг уйдёт в следующие месяцы"})
    pool = [c for c in pool if _credit_left(c)]
    totals = {
        "credit_dya": round(sum(float(c.get("dya") or 0.0) for c in credits), 2),
        "credit_dn": round(sum(float(c.get("dn") or 0.0) for c in credits), 2),
        "credit_dya2": round(sum(float(c.get("dya2") or 0.0) for c in credits), 2),
        "credit_dn2": round(sum(float(c.get("dn2") or 0.0) for c in credits), 2),
        "debit": round(sum(float(d["hours"]) for d in debits), 2),
        "pay_dya": round(sum(c["dya"] for c in pool), 2),
        "pay_dn": round(sum(c["dn"] for c in pool), 2),
        "pay_dya2": round(sum(c["dya2"] for c in pool), 2),
        "pay_dn2": round(sum(c["dn2"] for c in pool), 2),
        "debt_out": debt,
    }
    totals["pay_hours"] = round(totals["pay_dya"] + totals["pay_dn"]
                                + totals["pay_dya2"] + totals["pay_dn2"], 2)
    totals["pay_total"] = round(totals["pay_dya"] + totals["pay_dn"]
                                + 2.0 * (totals["pay_dya2"] + totals["pay_dn2"]), 2)
    return log, pool, totals
