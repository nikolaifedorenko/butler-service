"""Кодек Settings ↔ JSON-payload версии справочников (EngineSettingsVersion).

Payload хранит строки справочников как данные; «человеческие» подписи (title) лежат
рядом со строкой CFG-DAY-CODES и при сборке Settings игнорируются (домен их не знает).
"""
from __future__ import annotations

import datetime as dt
import json

from ..domain.settings.defaults import default_settings
from ..domain.settings.types import (
    MOD_PLAN_EQUALS_FACT,
    Category,
    DayCodePolicy,
    GlobalDefaults,
    Group,
    ModifierEntry,
    Settings,
    Window,
)
from ..domain.types.entities import Period


def _bool(raw) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw) in ("1", "true", "yes", "Да")


def _value(name: str, raw):
    if name == MOD_PLAN_EQUALS_FACT:
        return {"1": "yes", "0": "no", "auto": "auto", "yes": "yes", "no": "no"}.get(str(raw), "no")
    return _bool(raw)


def from_payload(payload: dict) -> Settings:
    base = default_settings()
    tz = payload.get("tz") or str(base.tz)
    from zoneinfo import ZoneInfo
    return Settings(
        tz=ZoneInfo(tz),
        period_granularity=payload.get("period_granularity", base.period_granularity),
        step_minutes=int(payload.get("step_minutes", base.step_minutes)),
        late_limit_minutes=int(payload.get("late_limit_minutes", base.late_limit_minutes)),
        day_limit_minutes=int(payload.get("day_limit_minutes", base.day_limit_minutes)),
        day_code_policy={code: DayCodePolicy(_bool(row["carries_hours"]), _bool(row["accepts_ut"]),
                                             _bool(row["counts_in_ut"]),
                                             _bool(row.get("plan_equals_fact_auto", False)))
                         for code, row in payload.get("day_code_policy", {}).items()},
        windows={key: Window(int(w["start_minute"]), int(w["end_minute"]))
                 for key, w in payload.get("windows", {}).items()},
        categories=tuple(Category(c["code"], int(c["start_minute"]), int(c["end_minute"]))
                         for c in payload.get("categories", [])),
        weights={code: int(w) for code, w in payload.get("weights", {}).items()},
        cascade_order=tuple(payload.get("cascade_order", base.cascade_order)),
        placement_order=tuple(payload.get("placement_order", base.placement_order)),
        groups={name: Group() for name in payload.get("groups", [])},
        modifiers=tuple(_modifier(m) for m in payload.get("modifiers", [])),
        global_defaults=_defaults(payload.get("global_defaults", {})),
        versions=tuple(payload.get("versions", ())))


def _modifier(m: dict) -> ModifierEntry:
    period = None
    if m.get("period_start"):
        period = Period(dt.date.fromisoformat(m["period_start"]),
                        dt.date.fromisoformat(m["period_end"]))
    return ModifierEntry(m["name"], _value(m["name"], m["value"]),
                         employee_id=str(m["employee_id"]) if m.get("employee_id") else None,
                         group=m.get("group") or None,
                         day=dt.date.fromisoformat(m["day"]) if m.get("day") else None,
                         period=period)


def _defaults(raw: dict) -> GlobalDefaults:
    out = {}
    for key in ("double_overtime", "pays_overtime"):
        out[key] = None if raw.get(key) is None else _bool(raw[key])
    pef = raw.get("plan_equals_fact")
    out["plan_equals_fact"] = None if pef is None else _value(MOD_PLAN_EQUALS_FACT, pef)
    return GlobalDefaults(**out)


def to_payload(st: Settings) -> dict:
    return {
        "tz": str(st.tz),
        "period_granularity": st.period_granularity,
        "step_minutes": st.step_minutes,
        "late_limit_minutes": st.late_limit_minutes,
        "day_limit_minutes": st.day_limit_minutes,
        "day_code_policy": {code: {"carries_hours": p.carries_hours, "accepts_ut": p.accepts_ut,
                                   "counts_in_ut": p.counts_in_ut,
                                   "plan_equals_fact_auto": p.plan_equals_fact_auto}
                            for code, p in st.day_code_policy.items()},
        "windows": {key: {"start_minute": w.start_minute, "end_minute": w.end_minute}
                    for key, w in st.windows.items()},
        "categories": [{"code": c.code, "start_minute": c.start_minute, "end_minute": c.end_minute}
                       for c in st.categories],
        "weights": dict(st.weights),
        "cascade_order": list(st.cascade_order),
        "placement_order": list(st.placement_order),
        "groups": list(st.groups),
        "global_defaults": {"double_overtime": st.global_defaults.double_overtime,
                            "pays_overtime": st.global_defaults.pays_overtime,
                            "plan_equals_fact": st.global_defaults.plan_equals_fact},
    }


def payload_json(st: Settings) -> str:
    return json.dumps(to_payload(st), ensure_ascii=False)
