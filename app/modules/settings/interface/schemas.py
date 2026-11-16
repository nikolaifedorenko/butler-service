"""Модели ответов экрана «Настройки»."""
from __future__ import annotations

from typing import Any, Optional

from app.core.schemas import ApiModel


class RuleItemOut(ApiModel):
    key: str
    value: Any
    default: Any
    description: str
    type: str


class CountsOut(ApiModel):
    """Сколько данных в системе."""

    employees: int
    users: int
    schedule_shifts: int
    punches: int
    tabel_days: int
    period_closings: int


class EngineVersionOut(ApiModel):
    id: Optional[int]
    valid_from: Optional[str]
    note: str
    on: str                         # дата, на которую показана версия


class ModifierOut(ApiModel):
    name: str
    title: str
    hint: str
    value: Any


class LimitsOut(ApiModel):
    step_minutes: Optional[int]
    late_limit_minutes: Optional[int]
    period_granularity: Optional[str]


class UpcomingVersionOut(ApiModel):
    id: int
    valid_from: str
    note: str


class EngineDefaultsOut(ApiModel):
    """Глобальные значения движка расчёта из версии, действующей сегодня."""

    version: EngineVersionOut
    modifiers: list[ModifierOut]
    limits: LimitsOut
    upcoming_versions: list[UpcomingVersionOut]     # версии, которые вступят позже


class SettingsOut(ApiModel):
    rules: dict[str, Any]
    items: list[RuleItemOut]
    counts: CountsOut
    base: dict[str, Any]            # базовый цикл объекта
    doc: dict[str, Any]             # реквизиты и тексты заявлений
    engine_defaults: EngineDefaultsOut


class DocSavedOut(ApiModel):
    ok: bool = True
    doc: dict[str, Any]


class BaseSavedOut(ApiModel):
    ok: bool = True
    base: dict[str, Any]


class RulesSavedOut(ApiModel):
    ok: bool = True
    rules: dict[str, Any]
