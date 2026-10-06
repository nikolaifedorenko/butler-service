"""Представления для HTTP: PeriodView / сохранённый результат → словари для интерфейса."""
from __future__ import annotations

from ..application.period_view import PeriodView
from .formatting import FLAG_SEVERITY, FLAG_TITLES, flag_text, reason_text
from .serialize import plain


def _h(minutes) -> float:
    return round((minutes or 0) / 60, 2)


def flag_dicts(flags: list[dict], tz: str) -> list[dict]:
    return [{"day": f["day"], "code": f["code"], "title": FLAG_TITLES.get(f["code"], f["code"]),
             "severity": FLAG_SEVERITY.get(f["code"], "muted"), "text": flag_text(f["code"], f["data"], tz)}
            for f in flags]


def result_view(result: dict, flags: list[dict], tz: str, detail: bool = False) -> dict:
    """result — сериализованный SettleResult (plain); flags — сериализованные флаги."""
    tariffs: dict[str, float] = {}
    ut = {}
    for day, row in result["mgmt_timesheet"].items():
        ut[day] = {t: _h(m) for t, m in row.items() if m}
        for t, m in row.items():
            tariffs[t] = round(tariffs.get(t, 0) + _h(m), 2)
    cards = [{"day": c["day"], "value": c["timesheet_value"], "plan": _h(c["plan_minutes"]),
              "fact": _h(c["full_fact_minutes"]), "work": _h(c["work_minutes"]), "ot": _h(c["overtime_minutes"]),
              "debt": _h(c["debt_minutes"]), "codes": {t: _h(m) for t, m in c["codes"].items()},
              "pays_overtime": c["pays_overtime"], "open_at_start": c["open_at_start"],
              "open_at_end": c["open_at_end"], "plan_equals_fact": c["plan_equals_fact_applied"]}
             for c in result["cards"]]
    out = {
        "ut": ut, "totals": tariffs, "cards": cards,
        "bank": {"open": _h(result["bank_open_minutes"]), "open_normalized": _h(result["bank_open_normalized_minutes"]),
                 "adjustments": _h(result["bank_adjustments_minutes"]), "credited": _h(result["credited_to_bank_minutes"]),
                 "paid": _h(result["paid_with_bank_minutes"]), "closed": _h(result["bank_closed_minutes"])},
        "debt": {"total": _h(result["total_debt_minutes"]), "residual": _h(result["residual_debt_minutes"]),
                 "cut": _h(sum(c["paid_minutes"] for c in result["cuts"]))},
        "plan_total": round(sum(c["plan"] for c in cards), 2), "fact_total": round(sum(c["fact"] for c in cards), 2),
        "deferred": [{"source_day": b["source_day"], "tariff": b["tariff"], "hours": _h(b["minutes"])}
                     for b in result["deferred_blocks"]],
        "open_session_since": result["open_session_since_utc"],
        "exceptions": [reason_text(r["code"], r["data"]) for r in result["exceptions"]],
        "flags": flag_dicts(flags, tz),
    }
    if detail:
        out["trace"] = [{"step": r["step"], "code": r["code"], "text": reason_text(r["code"], r["data"]),
                         "data": r["data"]} for r in result["trace"]]
        out["cuts"] = [{**c, "taken_hours": _h(c["taken_minutes"]), "paid_hours": _h(c["paid_minutes"])}
                       for c in result["cuts"]]
    return out


def period_view_dict(view: PeriodView, tz: str, detail: bool = False) -> dict:
    return result_view(plain(view.settle), plain(view.flags.flags), tz, detail)
