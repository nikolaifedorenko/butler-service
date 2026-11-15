"""Фикстура conftest ``_dates_at_run_time``: константы из DATES_AT_RUN_TIME присваиваются
заново перед тестами файла — прогон через полночь не оставляет в них вчерашнюю дату."""
from __future__ import annotations

import itertools

_assigned = itertools.count()
STAMP = next(_assigned)              # 0 при импорте, 1 после повторного присваивания
DERIVED = STAMP * 10
UNLISTED = next(_assigned)           # в списке нет — не трогается
DATES_AT_RUN_TIME = ("STAMP", "DERIVED")


def test_listed_constants_are_reassigned_in_file_order():
    assert (STAMP, DERIVED) == (2, 20)


def test_unlisted_constants_keep_import_value():
    assert UNLISTED == 1
