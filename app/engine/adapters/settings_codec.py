"""JSON-представление справочников (хранение версии настроек в БД и редактор в UI)."""
from __future__ import annotations

from dataclasses import replace

from ..domain.settings.defaults import default_settings
from ..domain.settings.types import Category, DayCodePolicy, Group, PlacementPolicy, Settings, Window


def _hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def _min(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def _segs(items) -> tuple:
    return tuple((_min(a), _min(b)) for a, b in items)


def to_payload(st: Settings) -> dict:
    return {
        "step_minutes": st.step_minutes, "late_limit_minutes": st.late_limit_minutes,
        "day_limit_minutes": st.day_limit_minutes, "double_weight": st.double_weight, "tz": st.tz,
        "day_codes": [{"code": p.code, "title": p.title, "carries_hours": p.carries_hours,
                       "accepts_ut": p.accepts_ut, "counts_in_ut": p.counts_in_ut,
                       "plan_equals_fact_auto": p.plan_equals_fact_auto,
                       "activity_requires_review": p.activity_requires_review} for p in st.day_codes.values()],
        "windows": [{"code": w.code, "hours": w.plan_minutes / 60,
                     "segments": [[_hhmm(a), _hhmm(b)] for a, b in w.segments]} for w in st.windows.values()],
        "categories": [{"name": c.name, "segments": [[_hhmm(a), _hhmm(b)] for a, b in c.segments],
                        "tariffs": {str(k): v for k, v in c.tariffs.items()}} for c in st.categories],
        "weights": dict(st.weights), "cascade_order": list(st.cascade_order),
        "placement_order": list(st.placement.tariff_order),
        "groups": [{"name": g.name, "title": g.title, "plan_equals_fact_auto": g.plan_equals_fact_auto}
                   for g in st.groups.values()],
    }


def _window_key(w: Window) -> str:
    h = w.plan_minutes
    return f"{w.code} {h // 60}" if h % 60 == 0 else f"{w.code} {h / 60:g}"


def from_payload(data: dict, version: str) -> Settings:
    base = default_settings()
    codes = {d["code"]: DayCodePolicy(d["code"], bool(d["carries_hours"]), bool(d["accepts_ut"]),
                                      bool(d["counts_in_ut"]), bool(d.get("plan_equals_fact_auto")),
                                      bool(d.get("activity_requires_review")), d.get("title", ""))
             for d in data.get("day_codes", [])} or base.day_codes
    wins = [Window(w["code"], round(float(w["hours"]) * 60), _segs(w["segments"])) for w in data.get("windows", [])]
    cats = tuple(Category(c["name"], _segs(c["segments"]), {int(k): v for k, v in c["tariffs"].items()})
                 for c in data.get("categories", [])) or base.categories
    groups = {g["name"]: Group(g["name"], bool(g.get("plan_equals_fact_auto")), g.get("title", ""))
              for g in data.get("groups", [])} or base.groups
    return replace(base, day_codes=codes, windows={_window_key(w): w for w in wins} or base.windows,
                   categories=cats, weights=data.get("weights") or base.weights,
                   cascade_order=tuple(data.get("cascade_order") or base.cascade_order),
                   placement=PlacementPolicy(tuple(data.get("placement_order") or base.placement.tariff_order)),
                   groups=groups, step_minutes=int(data.get("step_minutes", base.step_minutes)),
                   late_limit_minutes=int(data.get("late_limit_minutes", base.late_limit_minutes)),
                   day_limit_minutes=int(data.get("day_limit_minutes", base.day_limit_minutes)),
                   double_weight=int(data.get("double_weight", base.double_weight)),
                   tz=data.get("tz", base.tz), versions=(version,))
