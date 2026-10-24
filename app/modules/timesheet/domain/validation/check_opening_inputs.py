"""CHK-DEFERRED-IN и CHK-OPENING (5.3): входящие блоки minutes > 0, кратны
previous_step_minutes, source_day < period.start, тариф есть в CFG-WEIGHTS текущих
настроек; previous_step_minutes > 0 и делит 60; каждая Adjustment.period равна
рассчитываемому периоду — ошибка, не фильтр (v7/R9).

Тариф блока заморожен прошлым периодом, а веса берутся из настроек текущего: после
переименования категории (ДН → НОЧЬ) блок «ДН» дошёл бы до каскада и уронил расчёт
KeyError'ом (рецензия аудита 22.10.2026, §2.2) — ловим на стадии 1."""
from __future__ import annotations

from typing import Collection, Sequence

from ..types.entities import Adjustment, DeferredBlock, Period
from ..types.errors import InvalidInputDataError


def _deferred_violations(deferred_in: Sequence[DeferredBlock], period: Period,
                         previous_step_minutes: int, tariffs: Collection[str]) -> tuple:
    out = []
    for b in deferred_in:
        if b.minutes <= 0 or b.minutes % previous_step_minutes or b.source_day >= period.start \
                or b.tariff not in tariffs:
            out.append({"source_day": b.source_day, "tariff": b.tariff, "minutes": b.minutes})
    return tuple(out)


def _adjustment_violations(adjustments: Sequence[Adjustment], period: Period) -> tuple:
    return tuple({"period_start": a.period.start, "period_end": a.period.end,
                  "amount_minutes": a.amount_minutes, "reason_code": a.reason_code}
                 for a in adjustments if a.period != period)


def check_opening_inputs(deferred_in: Sequence[DeferredBlock], adjustments: Sequence[Adjustment],
                         period: Period, previous_step_minutes: int,
                         tariffs: Collection[str]) -> None:
    violations = _deferred_violations(deferred_in, period, previous_step_minutes, tariffs)
    if violations:
        unknown = sorted({v["tariff"] for v in violations if v["tariff"] not in tariffs})
        raise InvalidInputDataError("CHK-DEFERRED-IN", {"violations": violations,
                                                        "unknown_tariffs": tuple(unknown)})
    if previous_step_minutes <= 0 or 60 % previous_step_minutes:
        raise InvalidInputDataError("CHK-OPENING",
                                    {"previous_step_minutes": previous_step_minutes})
    violations = _adjustment_violations(adjustments, period)
    if violations:
        raise InvalidInputDataError("CHK-OPENING", {"adjustments": violations})
