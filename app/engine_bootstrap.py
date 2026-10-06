"""Подготовка данных движка v4 при старте: версия справочников, Табель из Графика, уборка
устаревших правил старого движка (спец. 17: переключатели удаляются из настроек)."""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .engine.adapters.settings_codec import to_payload
from .engine.domain.settings.defaults import default_settings
from .models import EngineSettingsVersion, Setting, TabelDay

# правила старого движка, которых в v4 нет (округление длительностей, ворота, автозакрытие …)
OBSOLETE_RULES = ("round_mode", "count_early_arrival", "count_late_departure", "min_session_min",
                  "auto_close_missing_out", "late_by_raw_time", "night_start", "night_end",
                  "round_step_min", "grace_minutes")


def _initial_payload(db: Session) -> dict:
    payload = to_payload(default_settings())
    old = {s.key: s.value for s in db.scalars(select(Setting).where(Setting.key.in_(OBSOLETE_RULES)))}
    try:
        step = int(float(old.get("round_step_min", 60)))
        payload["step_minutes"] = step if step > 0 and 60 % step == 0 else 60
        payload["late_limit_minutes"] = int(float(old.get("grace_minutes", 5)))
    except ValueError:
        pass
    return payload


def bootstrap_engine(db: Session, first: dt.date | None = None, last: dt.date | None = None) -> None:
    if not db.scalar(select(func.count(EngineSettingsVersion.id))):
        db.add(EngineSettingsVersion(valid_from=dt.date(2000, 1, 1), payload_json=json.dumps(
            _initial_payload(db), ensure_ascii=False), note="Стартовое наполнение Т1–Т7, Т9, Т-Группы",
            created_by_name="system"))
        db.flush()
    db.execute(delete(Setting).where(Setting.key.in_(OBSOLETE_RULES)))
    if not db.scalar(select(func.count(TabelDay.id))):
        from .api.tabel_api import ensure_tabel_filled
        today = dt.date.today()
        ensure_tabel_filled(db, first or (today.replace(day=1) - dt.timedelta(days=62)).replace(day=1),
                            last or (today.replace(day=28) + dt.timedelta(days=40)))
    db.flush()
