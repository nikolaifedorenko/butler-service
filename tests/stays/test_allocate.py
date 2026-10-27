"""Шахматка: автораспределение по объектам (PoC §6.3 + группы и корпус, спецификация §4.1;
границы версий фонда — спецификация версий §5)."""
from __future__ import annotations

from datetime import date

from app.modules.stays.domain.allocate import AllocItem, HoldRef, UnitSpan, allocate, natural_key
from app.modules.stays.domain.halfday import AM, PM, hold_span, pieces, pos, segments

DLX, VIL = 1, 2
CODES = {DLX: "DLX", VIL: "VIL"}


def D(d: int) -> date:
    return date(2026, 9, d)


LO, HI = pos(date(2026, 8, 1), AM), pos(date(2026, 10, 31), PM)     # окно: один интервал на объект


def item(rid: int, ci: int, co: int, cat: int = DLX, moves=(), pinned=None, number=None, early=False,
         late=False, kind="r", bounds=()):
    segs = segments(D(ci), D(co), early, late, cat, moves)
    return AllocItem((kind, rid), number or str(rid), tuple(pieces(segs, bounds)), pinned or {})


def span(uid: int, cat: int, label: str, path=(), sort=1, lo=LO, hi=HI) -> UnitSpan:
    return UnitSpan(uid, cat, sort, label, path, lo, hi)


def units(*labels, cat=DLX, path=()):
    return [span(100 + i, cat, lb, path) for i, lb in enumerate(labels)]


def test_natural_key():
    assert sorted(["4010", "402", "4003", "B-2", "B-10"], key=natural_key) == ["402", "4003", "4010", "B-2", "B-10"]


def test_first_fit_by_natural_label():
    us = [span(1, DLX, "4010"), span(2, DLX, "402"), span(3, DLX, "4003")]
    got, warns = allocate(us, [], [item(7, 2, 5)], CODES)
    assert got[(("r", 7), 0)] == 2 and warns == []


def test_category_order_before_label():
    us = [span(1, DLX, "100", sort=2), span(2, DLX, "900")]
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
    us = units("1") + [span(200, VIL, "4003")]
    got, warns = allocate(us, [], [item(1, 2, 5, pinned={0: 200}, number="9")], CODES)
    assert got[(("r", 1), 0)] == 100
    assert warns[0].kind == "pin_invalid" and warns[0].piece_index == 0
    assert warns[0].text == "Бронь 9: закреплённый объект не подходит — сегмент 1 распределяется автоматически"


def test_move_prefers_other_unit_same_group():
    us = [span(1, DLX, "1-201", (10, 1)), span(2, DLX, "2-201", (10, 2)),
          span(3, DLX, "1-202", (10, 1))]
    got, _ = allocate(us, [], [item(1, 2, 9, moves=((D(5), DLX),))], CODES)
    assert got[(("r", 1), 0)] == 1 and got[(("r", 1), 1000)] == 3


def test_move_prefers_common_ancestor_when_group_has_no_other_unit():
    """В узле больше нет объекта — ближайший по дереву (длиннее общий префикс пути)."""
    us = [span(1, DLX, "1-201", (10, 1)), span(2, DLX, "2-201", (20, 5)),
          span(3, DLX, "3-202", (10, 2))]
    got, _ = allocate(us, [], [item(1, 2, 9, moves=((D(5), DLX),))], CODES)
    assert got[(("r", 1), 0)] == 1 and got[(("r", 1), 1000)] == 3


def test_move_keeps_same_unit_when_only_one():
    us = units("1")
    got, _ = allocate(us, [], [item(1, 2, 9, moves=((D(5), DLX),))], CODES)
    assert got[(("r", 1), 0)] == got[(("r", 1), 1000)] == 100


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


B = pos(D(10), PM)                 # граница версии: версия с 10.09 действует с вечера 10.09


def test_piece_keeps_unit_across_unchanged_boundary():
    """Объект 1 разрезан границей без изменений; бронь 2 начала в объекте 2 и остаётся в нём,
    хотя после границы объект 1 свободен и первый по порядку."""
    us = [span(100, DLX, "1", hi=B - 1), span(100, DLX, "1", lo=B), span(101, DLX, "2")]
    got, warns = allocate(us, [], [item(1, 2, 10), item(2, 5, 15, bounds=[B])], CODES)
    assert got[(("r", 1), 0)] == 100
    assert got[(("r", 2), 0)] == got[(("r", 2), 1)] == 101 and warns == []


def test_unit_category_change_moves_reservation_from_D():
    us = [span(100, DLX, "1", hi=B - 1), span(100, VIL, "1", lo=B), span(101, DLX, "2")]
    got, warns = allocate(us, [], [item(1, 5, 15, bounds=[B])], CODES)
    assert got[(("r", 1), 0)] == 100 and got[(("r", 1), 1)] == 101 and warns == []


def test_pin_invalid_only_after_boundary():
    us = [span(100, DLX, "1", hi=B - 1), span(100, VIL, "1", lo=B), span(101, DLX, "2")]
    got, warns = allocate(us, [], [item(1, 5, 15, bounds=[B], pinned={0: 100}, number="9")], CODES)
    assert got[(("r", 1), 0)] == 100 and got[(("r", 1), 1)] == 101
    assert [(w.kind, w.piece_index, w.text) for w in warns] == [
        ("pin_invalid", 1,
         "Бронь 9: закреплённый объект не подходит с 10.09 — сегмент 1 распределяется автоматически")]


def test_category_missing_warning():
    us = [span(100, DLX, "1"), span(200, VIL, "V1", hi=B - 1)]
    got, warns = allocate(us, [], [item(1, 5, 15, cat=VIL, bounds=[B], number="31")], CODES)
    assert got[(("r", 1), 0)] == 200 and got[(("r", 1), 1)] is None
    assert [(w.kind, w.key, w.piece_index, w.text) for w in warns] == [
        ("category_missing", ("r", 1), 1, "Бронь 31: категории VIL нет в фонде с 10.09")]


def test_move_prefers_same_group_then_common_prefix():
    """Переезд: другой объект; сначала тот же узел, иначе самый длинный общий префикс пути —
    по пути прежнего объекта на предыдущей части (с границы версии объект 1 в другом узле)."""
    us = [span(1, DLX, "1-201", (10, 1), hi=B - 1), span(1, DLX, "1-201", (20, 5, 1), lo=B),
          span(2, DLX, "2-201", (20, 5)), span(3, DLX, "1-202", (10, 1)),
          span(4, DLX, "3-202", (20, 5, 1, 7))]
    early = item(1, 2, 9, moves=((D(5), DLX),), bounds=[B])
    late = item(2, 12, 20, moves=((D(15), DLX),), bounds=[B])
    got, _ = allocate(us, [], [early, late], CODES)
    assert got[(("r", 1), 0)] == 1 and got[(("r", 1), 1000)] == 3      # тот же узел (10, 1) до границы
    assert got[(("r", 2), 0)] == 1 and got[(("r", 2), 1000)] == 4      # общий префикс с (20, 5, 1)


def test_continuation_not_taken_by_piece_whose_unit_changed_category():
    """C (длиннее) обрабатывается первой на границе, её объект 2 стал VIL — она не забирает
    объект 1, в котором продолжается A."""
    us = [span(100, DLX, "1", hi=B - 1), span(100, DLX, "1", lo=B),
          span(101, DLX, "2", hi=B - 1), span(101, VIL, "2", lo=B), span(102, DLX, "3")]
    a = item(1, 5, 15, bounds=[B], number="50")
    c = item(2, 6, 20, bounds=[B], number="10")
    got, warns = allocate(us, [], [a, c], CODES)
    assert got[(("r", 1), 0)] == got[(("r", 1), 1)] == 100
    assert got[(("r", 2), 0)] == 101 and got[(("r", 2), 1)] == 102 and warns == []
