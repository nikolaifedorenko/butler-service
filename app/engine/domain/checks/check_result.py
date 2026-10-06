from dataclasses import dataclass

from ..codes_registry.invariant_codes import I5, I8, I11, I15, I17
from ..types.results import SettleResult
from ._fail import fail_if


@dataclass(frozen=True)
class Totals:
    incoming_and_created: int     # нормализованные входящие + созданные (стадия 6)
    credited_taken: int           # снятые неоплачиваемые, физические (стадия 7)


def check_result(r: SettleResult, totals: Totals, mode: str) -> None:
    """И5, И8, И11, И15, И17 после стадии 14."""
    a = r.bank_open_normalized_minutes + r.bank_adjustments_minutes + r.credited_to_bank_minutes
    t = sum(c.debt_minutes for c in r.cards) + max(0, -a)
    p, c, rr = r.paid_with_bank_minutes, sum(x.paid_minutes for x in r.cuts), r.residual_debt_minutes
    fail_if(r.total_debt_minutes != t, I5, total=r.total_debt_minutes, expected=t)
    if mode == "close":
        fail_if(r.bank_closed_minutes != max(0, a) - p - rr, I8, bank=r.bank_closed_minutes)
        fail_if(t != p + c + rr or rr < 0 or not 0 <= p <= min(t, max(0, a)), I11, t=t, p=p, c=c, r=rr)
    else:
        fail_if(p != 0 or r.cuts or rr != t or r.bank_closed_minutes != a, I15)
    placed = sum(m for row in r.mgmt_timesheet.values() for m in row.values())
    outgoing = sum(b.minutes for b in r.deferred_blocks)
    cut = sum(x.taken_minutes for x in r.cuts)
    fail_if(totals.incoming_and_created != placed + outgoing + totals.credited_taken + cut, I17,
            created=totals.incoming_and_created, placed=placed, outgoing=outgoing, cut=cut)
