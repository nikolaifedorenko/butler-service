import datetime as dt
from typing import Protocol, Sequence

from ..domain.types.entities import Mark


class PunchPort(Protocol):
    def marks_between(self, employee_id: str, from_utc: dt.datetime, to_utc: dt.datetime) -> Sequence[Mark]: ...
    def last_mark_before(self, employee_id: str, at_utc: dt.datetime) -> Mark | None: ...
