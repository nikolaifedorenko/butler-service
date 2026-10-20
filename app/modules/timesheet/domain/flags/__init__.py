"""Информационные флаги по Графику (6.6): LATE, EARLY_DEPARTURE, OFF_SHIFT_ATTENDANCE.
ABSENCE_GAP и MISSED_DAY удалены (v7/R18, R21) — след «ожидался — не пришёл» несёт
LATE с actual_at = None. Блок не знает о банке, УТ, долге и каскаде; из часового
конвейера получает только plan_equals_fact: Mapping[date, bool]."""
