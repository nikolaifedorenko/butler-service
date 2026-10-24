"""Шахматка: автораспределение по объектам (PoC §6.3 + группы и корпус, спецификация §4.1)."""
from __future__ import annotations

from datetime import date

from app.modules.stays.domain.allocate import AllocItem, HoldRef, UnitRef, allocate, natural_key
from app.modules.stays.domain.halfday import hold_span, segments

DLX, VIL = 1, 2
CODES = {DLX: "DLX", VIL: "VIL"}


def D(d: int) -> date:
    return date(2026, 9, d)


def item(rid: int, ci: int, co: int, cat: int = DLX, moves=(), pinned=None, number=None, early=False,
         late=False, kind="r"):
    return AllocItem((kind, rid), number or str(rid),
                     tuple(segments(D(ci), D(co), early, late, cat, moves)), pinned or {})


def units(*labels, cat=DLX, building=""):
    return [UnitRef(100 + i, cat, building, 1, lb) for i, lb in enumerate(labels)]


def test_natural_key():
    assert sorted(["4010", "402", "4003", "B-2", "B-10"], key=natural_key) == ["402", "4003", "4010", "B-2", "B-10"]


def test_first_fit_by_natural_label():
    us = [UnitRef(1, DLX, "", 1, "4010"), UnitRef(2, DLX, "", 1, "402"), UnitRef(3, DLX, "", 1, "4003")]
    got, warns = allocate(us, [], [item(7, 2, 5)], CODES)
    assert got[(("r", 7), 0)] == 2 and warns == []


def test_category_order_before_label():
    us = [UnitRef(1, DLX, "", 2, "100"), UnitRef(2, DLX, "", 1, "900")]
    got, _ = allocate(us, [], [item(1, 2, 5)], CODES)
    assert got[(("r", 1), 0)] == 2


def test_longer_first_on_same_start():
    us = units("1", "2")
    got, _ = allocate(us, [], [item(1, 2, 4), item(2, 2, 9)], CODES)
    assert got[(("r", 2), 0)] == 100 and got[(("r", 1), 0)] == 101


def test_checkout_morning_checkin_evening_same_unit():
    us = units("1")
    got, warns = allocate(us, [], [item(1, 2, 5), item(2, 5, 8)], CODES)
    assert got[(("r", 1), 0)] == got[(("r", 2), 0)] == 100 and warns == []


def test_hold_blocks_unit():
    us = units("1", "2")
    got, _ = allocate(us, [HoldRef(100, *hold_span(D(1), D(3)), "OOO")], [item(1, 2, 5)], CODES)
    assert got[(("r", 1), 0)] == 101


def test_pinned_respected_and_conflict_warned():
    us = units("1", "2")
    got, warns = allocate(us, [HoldRef(100, *hold_span(D(1), D(3)), "OOO")],
                          [item(1, 2, 5, pinned={0: 100}, number="555")], CODES)
    assert got[(("r", 1), 0)] == 100
    assert [(w.kind, w.text) for w in warns] == [
        ("pin_conflict", "Бронь 555: закреплённый объект 1 конфликтует с «OOO»")]


def test_pin_wrong_category_released():
    us = units("1") + [UnitRef(200, VIL, "", 1, "4003")]
    got, warns = allocate(us, [], [item(1, 2, 5, pinned={0: 200}, number="9")], CODES)
    assert got[(("r", 1), 0)] == 100
    assert warns[0].kind == "pin_invalid" and warns[0].seg_index == 0
    assert warns[0].text == "Бронь 9: закреплённый объект не подходит — сегмент 1 распределяется автоматически"


def test_move_prefers_other_unit_same_building():
    us = [UnitRef(1, DLX, "1", 1, "1-201"), UnitRef(2, DLX, "2", 1, "2-201"), UnitRef(3, DLX, "1", 1, "1-202")]
    got, _ = allocate(us, [], [item(1, 2, 9, moves=((D(5), DLX),))], CODES)
    assert got[(("r", 1), 0)] == 1 and got[(("r", 1), 1)] == 3


def test_move_keeps_same_unit_when_only_one():
    us = units("1")
    got, _ = allocate(us, [], [item(1, 2, 9, moves=((D(5), DLX),))], CODES)
    assert got[(("r", 1), 0)] == got[(("r", 1), 1)] == 100


def test_no_free_unit_warning_text():
    us = units("1")
    got, warns = allocate(us, [], [item(1, 10, 20), item(777, 18, 21)], CODES)
    assert got[(("r", 777), 0)] is None
    assert [(w.kind, w.key, w.text) for w in warns] == [
        ("unassigned", ("r", 777), "Бронь 777: нет свободных объектов категории DLX на 18.09–21.09")]


def test_idempotent():
    us = units("1", "2", "3")
    items = [item(1, 2, 6), item(2, 3, 9), item(3, 2, 4), item(4, 5, 8)]
    assert allocate(us, [], items, CODES) == allocate(us, [], list(reversed(items)), CODES)


def test_group_takes_one_unit():
    us = units("1", "2")
    got, warns = allocate(us, [], [item(5, 2, 6, kind="g"), item(1, 2, 6)], CODES)
    assert {got[(("g", 5), 0)], got[(("r", 1), 0)]} == {100, 101} and warns == []
    assert [k for k in got if k[0] == ("g", 5)] == [(("g", 5), 0)]   # один объект на всю группу
