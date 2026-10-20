"""SettingsPort: версия справочников по сроку действия + модификаторы CFG-MODIFIERS
из day_modifiers, дней двойной оплаты (DoublePayDay) и ВИП-периодов (VipDoublePay).
Валидация уровня 1 — при загрузке (5.3): ConfigError сообщает все нарушения разом."""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.employees.application import GROUP_FIVEDAY, GROUP_OTHER, GROUP_SHIFT1, GROUP_SHIFT2

from ..domain.settings.types import MOD_DOUBLE, Settings
from ..domain.settings.validate import validate_settings
from ..domain.types.entities import Period
from .orm import DayModifier, DoublePayDay, EngineSettingsVersion, VipDoublePay
from .settings_codec import from_payload

SCOPE_GROUPS = {"shift": (GROUP_SHIFT1, GROUP_SHIFT2, GROUP_OTHER),
                "week5": (GROUP_FIVEDAY,), "all": (None,)}


def base_version(db: Session, on: dt.date) -> EngineSettingsVersion | None:
    return db.scalar(select(EngineSettingsVersion)
                     .where(EngineSettingsVersion.valid_from <= on)
                     .order_by(EngineSettingsVersion.valid_from.desc(),
                               EngineSettingsVersion.id.desc()).limit(1))


def _dedupe(entries: list[dict]) -> list[dict]:
    """Идентичные записи из разных источников (день двойной оплаты + ручной модификатор)
    схлопываются; записи одного уровня с разными значениями — конфликт (CHK-MODIFIER-CONFLICT)."""
    seen: dict[tuple, dict] = {}
    for entry in entries:
        key = (entry["name"], str(entry["value"]), entry.get("employee_id"), entry.get("group"),
               entry.get("day"), entry.get("period_start"), entry.get("period_end"))
        seen.setdefault(key, entry)
    return list(seen.values())


def _modifier_rows(db: Session, period: Period, granularity: str) -> list[dict]:
    out = []
    rows = db.scalars(select(DayModifier).where(or_(
        (DayModifier.date >= period.start) & (DayModifier.date <= period.end),
        (DayModifier.period_start <= period.end) & (DayModifier.period_start.is_not(None)))
    ).order_by(DayModifier.id))
    for m in rows:
        if m.period_start is not None and not (m.period_start <= period.end
                                               and _period_end(m, granularity) >= period.start):
            continue
        out.append({"name": m.name, "value": m.value,
                    "employee_id": m.employee_id, "group": m.group or None,
                    "day": m.date.isoformat() if m.date else None,
                    "period_start": m.period_start.isoformat() if m.period_start else None,
                    "period_end": _period_end(m, granularity).isoformat()
                    if m.period_start else None})
    for d in db.scalars(select(DoublePayDay).where(DoublePayDay.date >= period.start,
                                                   DoublePayDay.date <= period.end)):
        for group in SCOPE_GROUPS.get(d.scope, (None,)):
            out.append({"name": MOD_DOUBLE, "value": "1", "employee_id": None,
                        "group": group, "day": d.date.isoformat(),
                        "period_start": None, "period_end": None})
    for v in db.scalars(select(VipDoublePay).where(VipDoublePay.start_date <= period.end,
                                                   VipDoublePay.end_date >= period.start)):
        out.append({"name": MOD_DOUBLE, "value": "1", "employee_id": v.employee_id,
                    "group": None, "day": None,
                    "period_start": max(v.start_date, period.start).isoformat(),
                    "period_end": min(v.end_date, period.end).isoformat()})
    return _dedupe(out)


def _month_end(start: dt.date) -> dt.date:
    nxt = dt.date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return nxt - dt.timedelta(days=1)


def _period_end(m: DayModifier, granularity: str) -> dt.date:
    """Конец периода записи: месяц либо половина месяца по гранулярности (R36)."""
    start = m.period_start
    if start.day == 16:
        return _month_end(start)
    if start.day == 1 and granularity != "month":
        return dt.date(start.year, start.month, 15)
    return _month_end(start)


class SqlSettingsAdapter:
    def __init__(self, db: Session):
        self.db = db
        self._cache: dict[Period, Settings] = {}

    def load(self, period: Period) -> Settings:
        if period in self._cache:
            return self._cache[period]
        version = base_version(self.db, period.start)
        payload = json.loads(version.payload_json) if version else {}
        payload["versions"] = [f"v{version.id}"] if version else ["defaults"]
        payload.setdefault("modifiers", [])
        granularity = payload.get("period_granularity", "month")
        payload["modifiers"] = (payload.get("static_modifiers", [])
                                + _modifier_rows(self.db, period, granularity))
        st = from_payload(payload)
        validate_settings(st)
        self._cache[period] = st
        return st
