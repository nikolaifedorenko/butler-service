"""Восстановление сохранённых SettleResult/FlagsResult из JSON-словарей (7.2: чтение
закрытого периода из хранилища без пересчёта)."""
from __future__ import annotations

import datetime as dt

from ..domain.codes_registry.reason_codes import ALL_STEPS
from ..domain.types.entities import DeferredBlock
from ..domain.types.results import Cut, DayCard, Flag, FlagsResult, Reason, SettleResult


def _date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def _dt(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value)


def _reason(d: dict) -> Reason:
    data = dict(d["data"])
    for key in ("day", "source_day", "placed_day"):
        if isinstance(data.get(key), str):
            data[key] = _date(data[key])
    for key in ("expected_at", "actual_at", "first_presence_at"):
        if isinstance(data.get(key), str):
            data[key] = _dt(data[key])
    assert d["step"] in ALL_STEPS
    return Reason(d["step"], d["code"], data)


def _card(d: dict) -> DayCard:
    return DayCard(_date(d["day"]), d["timesheet_value"], d["plan_minutes"],
                   d["full_fact_minutes"], d["work_minutes"], d["overtime_minutes"],
                   d["debt_minutes"], d["codes"], d["pays_overtime"],
                   d["plan_equals_fact_applied"])


def _cut(d: dict) -> Cut:
    return Cut(_date(d["source_day"]),
               _date(d["placed_day"]) if d["placed_day"] else None,
               d["tariff"], d["taken_minutes"], d["paid_minutes"])


def _deferred(d: dict) -> DeferredBlock:
    return DeferredBlock(_date(d["source_day"]), d["tariff"], d["minutes"])


def result_from_dict(d: dict) -> SettleResult:
    return SettleResult(
        cards=tuple(_card(c) for c in d["cards"]),
        mgmt_timesheet={_date(day): dict(row) for day, row in d["mgmt_timesheet"].items()},
        bank_open_minutes=d["bank_open_minutes"],
        bank_open_normalized_minutes=d["bank_open_normalized_minutes"],
        bank_adjustments_minutes=d["bank_adjustments_minutes"],
        bank_closed_minutes=d["bank_closed_minutes"],
        credited_to_bank_minutes=d["credited_to_bank_minutes"],
        paid_with_bank_minutes=d["paid_with_bank_minutes"],
        total_debt_minutes=d["total_debt_minutes"],
        residual_debt_minutes=d["residual_debt_minutes"],
        cuts=tuple(_cut(c) for c in d["cuts"]),
        deferred_blocks=tuple(_deferred(b) for b in d["deferred_blocks"]),
        exceptions=tuple(_reason(r) for r in d["exceptions"]),
        trace=tuple(_reason(r) for r in d["trace"]))


def _flag(d: dict) -> Flag:
    data = dict(d["data"])
    for key in ("expected_at", "actual_at", "first_presence_at"):
        if isinstance(data.get(key), str):
            data[key] = _dt(data[key])
    for key in ("shift_segments", "absence_intervals"):
        if key in data:
            data[key] = tuple((_dt(s), _dt(e)) for s, e in data[key])
    return Flag(_date(d["day"]), d["code"], data)


def flags_from_dict(d: dict) -> FlagsResult:
    return FlagsResult(tuple(_flag(f) for f in d["flags"]))
