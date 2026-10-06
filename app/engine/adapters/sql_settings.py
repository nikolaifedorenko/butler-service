"""SettingsPort: версия справочников по сроку действия + модификаторы Т4 из БД прототипа.

Источники модификаторов «Двойные переработки»: дни двойной оплаты (DoublePayDay, по scope —
все / сменные блоки / пятидневка) и периоды ВИП-гостей (VipDoublePay, сотрудник + день).
Прочие модификаторы — таблица day_modifiers.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import replace

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...groups import GROUP_FIVEDAY, GROUP_OTHER, GROUP_SHIFT1, GROUP_SHIFT2
from ...models import DayModifier, DoublePayDay, EngineSettingsVersion, Employee, VipDoublePay
from ..domain.settings.defaults import default_settings
from ..domain.settings.types import AUTO, MOD_DOUBLE, Modifier, Settings  # noqa: F401
from ..domain.settings.validate import validate_settings
from ..domain.types.entities import Period
from ._db import days_of
from .settings_codec import from_payload
from .sql_timesheet import employee_group

SCOPE_GROUPS = {"shift": (GROUP_SHIFT1, GROUP_SHIFT2, GROUP_OTHER), "week5": (GROUP_FIVEDAY,)}


def _value(raw: str) -> object:
    return AUTO if raw == AUTO else raw in ("1", "true", "yes")


def base_version(db: Session, on: dt.date) -> EngineSettingsVersion | None:
    return db.scalar(select(EngineSettingsVersion).where(EngineSettingsVersion.valid_from <= on)
                     .order_by(EngineSettingsVersion.valid_from.desc(), EngineSettingsVersion.id.desc()).limit(1))


class SqlSettingsAdapter:
    def __init__(self, db: Session):
        self.db = db
        self._cache: dict = {}

    def _modifiers(self, period: Period) -> list[Modifier]:
        out = [Modifier(m.name, _value(m.value), str(m.employee_id) if m.employee_id else None,
                        m.group or None, m.date) for m in self.db.scalars(select(DayModifier).where(or_(
                            (DayModifier.date >= period.start) & (DayModifier.date <= period.end),
                            DayModifier.period_start == period.start)).order_by(DayModifier.id))]
        for d in self.db.scalars(select(DoublePayDay).where(DoublePayDay.date >= period.start,
                                                            DoublePayDay.date <= period.end)):
            groups = SCOPE_GROUPS.get(d.scope, (None,))
            out += [Modifier(MOD_DOUBLE, True, None, g, d.date) for g in groups]
        for v in self.db.scalars(select(VipDoublePay).where(VipDoublePay.start_date <= period.end,
                                                            VipDoublePay.end_date >= period.start)):
            out += [Modifier(MOD_DOUBLE, True, str(v.employee_id), None, day)
                    for day in days_of(max(v.start_date, period.start), min(v.end_date, period.end))]
        return out

    def load(self, period: Period) -> Settings:
        if period in self._cache:
            return self._cache[period]
        ver = base_version(self.db, period.start)
        st = from_payload(json.loads(ver.payload_json), f"settings:{ver.id}") if ver else default_settings()
        mods = self._modifiers(period)
        known = set(st.groups)
        groups = {str(e.id): employee_group(e, known) for e in self.db.scalars(select(Employee))}
        digest = hashlib.sha1(repr(sorted(map(repr, mods))).encode()).hexdigest()[:10]
        st = validate_settings(replace(st, modifiers=tuple(mods), employee_groups=groups,
                                      versions=(st.versions[0], f"modifiers:{digest}")))
        self._cache[period] = st
        return st
