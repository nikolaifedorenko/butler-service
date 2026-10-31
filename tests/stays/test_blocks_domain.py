"""Шахматка, часть 2: слоты блоков и их раскладка по объектам (спецификация OOO и блоков §4.1–§4.3)."""
from __future__ import annotations

from datetime import date

from app.modules.stays.domain.allocate import AllocItem, OooRef, UnitSpan, allocate
from app.modules.stays.domain.blocks import SlotRef, slots
from app.modules.stays.domain.halfday import AM, PM, pieces, pos, segments

DLX = 1
CODES = {DLX: "DLX"}
LO, HI = pos(date(2026, 8, 1), AM), pos(date(2026, 10, 31), PM)


def D(d: int) -> date:
    return date(2026, 9, d)


def night(d: int) -> tuple[int, int]:
    """Ночь D — от вечера D до утра D+1."""
    return pos(D(d), PM), pos(D(d + 1), AM)


def units(n: int):
    return [UnitSpan(100 + i, DLX, 1, str(i + 1), (), LO, HI) for i in range(n)]


def grid(block: int, first: int, last: int, qty: int = 1) -> dict:
    return {(block, DLX, D(d)): qty for d in range(first, last + 1)}


def booking(rid, ci, co, number=None, rank=0, in_house=False, bounds=(), fixed=None):
    ps = tuple(pieces(segments(D(ci), D(co), False, False, DLX, ()), bounds))
    return AllocItem(("r", rid), number or str(rid), ps, {}, fixed or {}, rank=rank, in_house=in_house)


def run(n_units, sl, items=(), ooo=()):
    return allocate(units(n_units), list(ooo), sl, list(items), CODES, {})


def test_slots_from_variable_quantity():
    """Слот k существует в ночи, где остаток ≥ k; непрерывные ночи — один SlotRef."""
    got = slots({(7, DLX, D(10)): 2, (7, DLX, D(11)): 1, (7, DLX, D(12)): 2}, {7: "Гендир"})
    assert got == [SlotRef(7, DLX, 1, pos(D(10), PM), pos(D(13), AM), "Гендир"),
                   SlotRef(7, DLX, 2, pos(D(10), PM), pos(D(11), AM), "Гендир"),
                   SlotRef(7, DLX, 2, pos(D(12), PM), pos(D(13), AM), "Гендир")]
    # разрыв в датах режет слот; без названий — пустое
    assert slots({(1, DLX, D(1)): 1, (1, DLX, D(3)): 1}) == [
        SlotRef(1, DLX, 1, *night(1), ""), SlotRef(1, DLX, 1, *night(3), "")]


def test_two_blocks_same_category_take_two_units():
    sl = slots({**grid(1, 10, 11), **grid(2, 10, 11)}, {1: "А", 2: "Б"})
    _, placed, warns = run(2, sl)
    assert placed == {(1, DLX, 1, D(10).toordinal()): 100, (1, DLX, 1, D(11).toordinal()): 100,
                      (2, DLX, 1, D(10).toordinal()): 101, (2, DLX, 1, D(11).toordinal()): 101}
    assert warns == []


def test_slot_keeps_unit_when_free():
    """В ночь 10 объект 1 под OOO — слот в объекте 2; с ночи 11 объект 1 свободен и первый
    по порядку, но слот держится объекта 2."""
    sl = slots(grid(1, 10, 12), {1: "Г"})
    _, placed, warns = run(2, sl, ooo=[OooRef(100, *night(10), "ремонт")])
    assert [placed[(1, DLX, 1, D(d).toordinal())] for d in (10, 11, 12)] == [101, 101, 101]
    assert warns == []


def test_slot_moves_when_busy():
    """Объект слота занят OOO с ночи 12 — слот переезжает; блок не уменьшается и не теряется."""
    sl = slots(grid(1, 10, 13), {1: "Г"})
    _, placed, warns = run(2, sl, ooo=[OooRef(100, pos(D(12), PM), pos(D(14), AM), "ремонт")])
    assert [placed[(1, DLX, 1, D(d).toordinal())] for d in (10, 11, 12, 13)] == [100, 100, 101, 101]
    assert warns == []


def test_block_short_never_shrinks():
    nights = {**grid(1, 10, 11, qty=2), (1, DLX, D(12)): 3}
    _, placed, warns = run(1, slots(nights, {1: "Гендир"}))
    assert placed[(1, DLX, 1, D(12).toordinal())] == 100
    assert placed[(1, DLX, 2, D(10).toordinal())] is None and placed[(1, DLX, 3, D(12).toordinal())] is None
    assert len(placed) == 2 + 2 + 3                         # все слоты на месте — с объектом или без
    assert [(w.kind, w.key, w.text) for w in warns] == [
        ("block_short", ("b", 1), "Блок Гендир: не хватает 1 DLX на 10–11.09"),
        ("block_short", ("b", 1), "Блок Гендир: не хватает 2 DLX на 12.09")]


def test_block_displaces_confirmed_created_earlier():
    """Блок главнее брони, даже если бронь появилась раньше; бронь — овербукинг целиком."""
    got, placed, warns = run(1, slots(grid(9, 11, 11), {9: "Г"}), [booking(1, 10, 13)])
    assert placed == {(9, DLX, 1, D(11).toordinal()): 100}
    assert got == {(("r", 1), 0): None}
    assert [(w.kind, w.key) for w in warns] == [("overbooked", ("r", 1))]


def test_block_never_moves_in_house():
    """Все объекты заняты заселёнными гостями: block_short, гости на месте, овербукинга нет."""
    T = pos(D(8), PM)                                        # «сегодня»: прошлое заморожено
    a = booking(1, 5, 15, in_house=True, bounds=[T], fixed={0: 100})
    b = booking(2, 6, 14, in_house=True, bounds=[T], fixed={0: 101})
    got, placed, warns = run(2, slots(grid(3, 10, 11), {3: "Гендир"}), [a, b])
    assert got == {(("r", 1), 0): 100, (("r", 1), 1): 100, (("r", 2), 0): 101, (("r", 2), 1): 101}
    assert set(placed.values()) == {None}
    assert [(w.kind, w.text) for w in warns] == [("block_short", "Блок Гендир: не хватает 1 DLX на 10–11.09")]


def test_slot_avoids_unit_pinned_by_booking():
    """Слот при выборе обходит объект, закреплённый за бронью, если есть другой свободный."""
    b = booking(1, 9, 13)
    pinned = AllocItem(b.key, b.number, b.segments, {0: 100})
    got, placed, warns = run(2, slots(grid(4, 10, 11), {4: "Г"}), [pinned])
    assert got == {(("r", 1), 0): 100} and set(placed.values()) == {101} and warns == []
