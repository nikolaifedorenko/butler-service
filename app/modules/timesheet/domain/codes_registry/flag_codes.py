"""Реестр флагов (6.6, v7): три кода. ABSENCE_GAP и MISSED_DAY удалены (R18/R21) —
след «ожидался — не пришёл» несёт LATE с actual_at = None.
Порядок ALL — канон сортировки FlagsResult (3.4)."""

LATE = "LATE"
EARLY_DEPARTURE = "EARLY_DEPARTURE"
OFF_SHIFT_ATTENDANCE = "OFF_SHIFT_ATTENDANCE"

ALL = (LATE, EARLY_DEPARTURE, OFF_SHIFT_ATTENDANCE)
