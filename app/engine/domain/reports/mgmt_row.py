import datetime as dt

from ..placement.codes import Codes


def mgmt_row(codes: Codes, day: dt.date) -> dict[str, int]:
    """Размещённые в день коды, агрегированные по тарифу."""
    row: dict[str, int] = {}
    for b in (b for b in codes.blocks() if b.placed_day == day):
        row[b.tariff] = row.get(b.tariff, 0) + b.minutes
    return row
