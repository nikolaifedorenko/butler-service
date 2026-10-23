"""Шахматка: модель половинок суток и сегменты (PoC SPEC §5; пять рабочих примеров §5.4)."""
from __future__ import annotations

from datetime import date

from app.modules.stays.domain.halfday import (
    AM,
    PM,
    hold_span,
    overlaps,
    segment_on,
    segments,
    validate_dates,
)


def p(d: int, h: int) -> int:
    return date(2026, 9, d).toordinal() * 2 + h


def D(d: int) -> date:
    return date(2026, 9, d)


def test_poc_1_plain():
    (s,) = segments(D(2), D(18), False, False, 1, ())
    assert (s.start_pos, s.end_pos) == (p(2, PM), p(18, AM))


def test_poc_2_early_late():
    (s,) = segments(D(17), D(21), True, True, 1, ())
    assert (s.start_pos, s.end_pos) == (p(17, AM), p(21, PM))


def test_poc_3_move():
    a, b = segments(D(17), D(25), False, False, 1, ((D(21), 2),))
    assert (a.index, a.category_id, a.start, a.end, a.start_pos, a.end_pos) == (0, 1, D(17), D(21), p(17, 1), p(21, 0))
    assert (b.index, b.category_id, b.start, b.end, b.start_pos, b.end_pos) == (1, 2, D(21), D(25), p(21, 1), p(25, 0))


def test_early_and_late_only_on_edge_segments():
    a, b = segments(D(17), D(25), True, True, 1, ((D(21), 2),))
    assert (a.start_pos, a.end_pos, b.start_pos, b.end_pos) == (p(17, 0), p(21, 0), p(21, 1), p(25, 1))


def test_moves_sorted():
    segs = segments(D(1), D(10), False, False, 1, ((D(7), 3), (D(4), 2)))
    assert [(s.category_id, s.start, s.end) for s in segs] == [(1, D(1), D(4)), (2, D(4), D(7)), (3, D(7), D(10))]


def test_poc_4_checkout_then_checkin_same_day():
    assert not overlaps(p(2, 1), p(18, 0), p(18, 1), p(20, 0))
    assert overlaps(p(2, 1), p(18, 0), p(18, 0), p(20, 0))


def test_poc_5_ooo():
    assert hold_span(D(1), D(12)) == (p(1, 0), p(12, 1))
    assert overlaps(*hold_span(D(1), D(12)), p(12, 1), p(15, 0))


def test_segment_on_move_day():
    segs = segments(D(17), D(25), False, False, 1, ((D(21), 2),))
    assert segment_on(segs, D(21), AM).index == 0
    assert segment_on(segs, D(21), PM).index == 1
    assert segment_on(segs, D(17), AM) is None
    assert segment_on(segs, D(25), PM) is None


def test_validate_dates():
    assert validate_dates(D(5), D(5), ()) == ["Выезд должен быть позже заезда"]
    assert validate_dates(D(5), D(9), (D(5),)) == ["Дата переезда вне проживания"]
    assert validate_dates(D(5), D(9), (D(9),)) == ["Дата переезда вне проживания"]
    assert validate_dates(D(5), D(9), (D(7), D(7))) == ["Две даты переезда совпадают"]
    assert validate_dates(D(5), D(9), (D(6), D(8))) == []
