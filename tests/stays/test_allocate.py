"""Шахматка: автораспределение по объектам (PoC §6.3 + группы и корпус, спецификация §4.1;
границы версий фонда — спецификация версий §5)."""
from __future__ import annotations

from datetime import date

from app.modules.stays.domain.allocate import AllocItem, OooRef, UnitSpan, allocate, natural_key
from app.modules.stays.domain.halfday import AM, PM, hold_span, ooo_span, pieces, pos, segments

DLX, VIL = 1, 2
CODES = {DLX: "DLX", VIL: "VIL"}


def D(d: int) -> date:
    return date(2026, 9, d)


LO, HI = pos(date(2026, 8, 1), AM), pos(date(2026, 10, 31), PM)     # окно: один интервал на объект


def item(rid: int, ci: int, co: int, cat: int = DLX, moves=(), pinned=None, number=None, early=False,
         late=False, kind="r", bounds=(), rank=0, in_house=False, fixed=None, prefs=None):
    segs = segments(D(ci), D(co), early, late, cat, moves)
    return AllocItem((kind, rid), number or str(rid), tuple(pieces(segs, bounds)), pinned or {}, fixed or {},
                     rank=rank, in_house=in_house, prefs=prefs)


def span(uid: int, cat: int, label: str, path=(), sort=1, lo=LO, hi=HI) -> UnitSpan:
    return UnitSpan(uid, cat, sort, label, path, lo, hi)


def units(*labels, cat=DLX, path=()):
    return [span(100 + i, cat, lb, path) for i, lb in enumerate(labels)]


def run(us, ooo, items, turnover=None):
    """Брони без блоков: (назначения, предупреждения)."""
    got, placed, warns = allocate(us, ooo, [], items, CODES, turnover or {})
    assert placed == {}
    return got, warns


def test_natural_key():
    assert sorted(["4010", "402", "4003", "B-2", "B-10"], key=natural_key) == ["402", "4003", "4010", "B-2", "B-10"]


def test_first_fit_by_natural_label():
    us = [span(1, DLX, "4010"), span(2, DLX, "402"), span(3, DLX, "4003")]
    got, warns = run(us, [], [item(7, 2, 5)])
    assert got[(("r", 7), 0)] == 2 and warns == []


def test_category_order_before_label():
    us = [span(1, DLX, "100", sort=2), span(2, DLX, "900")]
    got, _ = run(us, [], [item(1, 2, 5)])
    assert got[(("r", 1), 0)] == 2


def test_longer_first_on_same_start():
    us = units("1", "2")
    got, _ = run(us, [], [item(1, 2, 4), item(2, 2, 9)])
    assert got[(("r", 2), 0)] == 100 and got[(("r", 1), 0)] == 101


def test_checkout_morning_checkin_evening_same_unit():
    us = units("1")
    got, warns = run(us, [], [item(1, 2, 5), item(2, 5, 8)])
    assert got[(("r", 1), 0)] == got[(("r", 2), 0)] == 100 and warns == []


def test_hold_blocks_unit():
    us = units("1", "2")
    got, _ = run(us, [OooRef(100, *hold_span(D(1), D(3)), "OOO")], [item(1, 2, 5)])
    assert got[(("r", 1), 0)] == 101


def test_pin_transferred_on_move():
    """OOO поверх закреплённой брони (§4.4): бронь переезжает, без pin_invalid — закрепление
    переносится на новый объект; конфликт виден предупреждением."""
    us = units("1", "2")
    got, warns = run(us, [OooRef(100, *hold_span(D(1), D(3)), "OOO")],
                     [item(1, 2, 5, pinned={0: 100}, number="555")])
    assert got[(("r", 1), 0)] == 101
    assert [(w.kind, w.text) for w in warns] == [
        ("pin_conflict", "Бронь 555: закреплённый объект 1 занят «OOO» — бронь перенесена вместе с закреплением")]


def test_pin_conflict_without_free_unit_keeps_pin_text():
    """Закреплённый объект под OOO и другого свободного нет: овербукинг, закрепление сохранено (§4.4)."""
    got, warns = run(units("1"), [OooRef(100, *hold_span(D(3), D(3)), "OOO")],
                     [item(1, 2, 5, pinned={0: 100}, number="556")])
    assert got[(("r", 1), 0)] is None
    assert [(w.kind, w.text) for w in warns] == [
        ("pin_conflict", "Бронь 556: закреплённый объект 1 занят «OOO» — свободного объекта нет: бронь без объекта, "
                         "закрепление сохранено"),
        ("overbooked", "Бронь 556: нет свободных объектов категории DLX на 02.09–05.09")]


def test_pin_wrong_category_released():
    us = units("1") + [span(200, VIL, "4003")]
    got, warns = run(us, [], [item(1, 2, 5, pinned={0: 200}, number="9")])
    assert got[(("r", 1), 0)] == 100
    assert warns[0].kind == "pin_invalid" and warns[0].piece_index == 0
    assert warns[0].text == "Бронь 9: закреплённый объект не подходит — сегмент 1 распределяется автоматически"


def test_move_prefers_other_unit_same_group():
    us = [span(1, DLX, "1-201", (10, 1)), span(2, DLX, "2-201", (10, 2)),
          span(3, DLX, "1-202", (10, 1))]
    got, _ = run(us, [], [item(1, 2, 9, moves=((D(5), DLX),))])
    assert got[(("r", 1), 0)] == 1 and got[(("r", 1), 1000)] == 3


def test_move_prefers_common_ancestor_when_group_has_no_other_unit():
    """В узле больше нет объекта — ближайший по дереву (длиннее общий префикс пути)."""
    us = [span(1, DLX, "1-201", (10, 1)), span(2, DLX, "2-201", (20, 5)),
          span(3, DLX, "3-202", (10, 2))]
    got, _ = run(us, [], [item(1, 2, 9, moves=((D(5), DLX),))])
    assert got[(("r", 1), 0)] == 1 and got[(("r", 1), 1000)] == 3


def test_move_keeps_same_unit_when_only_one():
    us = units("1")
    got, _ = run(us, [], [item(1, 2, 9, moves=((D(5), DLX),))])
    assert got[(("r", 1), 0)] == got[(("r", 1), 1000)] == 100


def test_no_free_unit_warning_text():
    us = units("1")
    got, warns = run(us, [], [item(1, 10, 20), item(777, 18, 21)])
    assert got[(("r", 777), 0)] is None
    assert [(w.kind, w.key, w.text) for w in warns] == [
        ("overbooked", ("r", 777), "Бронь 777: нет свободных объектов категории DLX на 18.09–21.09")]


def test_idempotent():
    us = units("1", "2", "3")
    items = [item(1, 2, 6), item(2, 3, 9), item(3, 2, 4), item(4, 5, 8)]
    assert run(us, [], items) == run(us, [], list(reversed(items)))


def test_group_takes_one_unit():
    us = units("1", "2")
    got, warns = run(us, [], [item(5, 2, 6, kind="g"), item(1, 2, 6)])
    assert {got[(("g", 5), 0)], got[(("r", 1), 0)]} == {100, 101} and warns == []
    assert [k for k in got if k[0] == ("g", 5)] == [(("g", 5), 0)]   # один объект на всю группу


B = pos(D(10), PM)                 # граница версии: версия с 10.09 действует с вечера 10.09


def test_piece_keeps_unit_across_unchanged_boundary():
    """Объект 1 разрезан границей без изменений; бронь 2 начала в объекте 2 и остаётся в нём,
    хотя после границы объект 1 свободен и первый по порядку."""
    us = [span(100, DLX, "1", hi=B - 1), span(100, DLX, "1", lo=B), span(101, DLX, "2")]
    got, warns = run(us, [], [item(1, 2, 10), item(2, 5, 15, bounds=[B])])
    assert got[(("r", 1), 0)] == 100
    assert got[(("r", 2), 0)] == got[(("r", 2), 1)] == 101 and warns == []


def test_unit_category_change_moves_reservation_from_D():
    us = [span(100, DLX, "1", hi=B - 1), span(100, VIL, "1", lo=B), span(101, DLX, "2")]
    got, warns = run(us, [], [item(1, 5, 15, bounds=[B])])
    assert got[(("r", 1), 0)] == 100 and got[(("r", 1), 1)] == 101 and warns == []


def test_unit_category_change_in_house_moves_from_D():
    us = [span(100, DLX, "1", hi=B - 1), span(100, VIL, "1", lo=B), span(101, DLX, "2")]
    got, warns = run(us, [], [item(1, 5, 15, bounds=[B], in_house=True, fixed={0: 100})])
    assert got[(("r", 1), 0)] == 100 and got[(("r", 1), 1)] == 101 and warns == []


def test_in_house_move_by_fund_chunks_when_no_unit_covers_rest():
    """Заселённый с D: ни один объект не покрывает остаток по фонду целиком — самыми длинными
    кусками (объект 3 до второй границы, затем объект 2)."""
    B2 = pos(D(12), PM)
    us = [span(100, DLX, "1", hi=B - 1), span(100, VIL, "1", lo=B), span(101, DLX, "2", lo=B2),
          span(102, DLX, "3", hi=B2 - 1)]
    guest = item(1, 5, 15, bounds=[pos(D(7), PM), B, B2], in_house=True, fixed={0: 100})
    got, warns = run(us, [], [guest])
    assert [got[(("r", 1), i)] for i in range(4)] == [100, 100, 102, 101] and warns == []


def test_pin_invalid_only_after_boundary():
    us = [span(100, DLX, "1", hi=B - 1), span(100, VIL, "1", lo=B), span(101, DLX, "2")]
    got, warns = run(us, [], [item(1, 5, 15, bounds=[B], pinned={0: 100}, number="9")])
    assert got[(("r", 1), 0)] == 100 and got[(("r", 1), 1)] == 101
    assert [(w.kind, w.piece_index, w.text) for w in warns] == [
        ("pin_invalid", 1,
         "Бронь 9: закреплённый объект не подходит с 10.09 — сегмент 1 распределяется автоматически")]


def test_category_missing_warning():
    us = [span(100, DLX, "1"), span(200, VIL, "V1", hi=B - 1)]
    got, warns = run(us, [], [item(1, 5, 15, cat=VIL, bounds=[B], number="31")])
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
    got, _ = run(us, [], [early, late])
    assert got[(("r", 1), 0)] == 1 and got[(("r", 1), 1000)] == 3      # тот же узел (10, 1) до границы
    assert got[(("r", 2), 0)] == 1 and got[(("r", 2), 1000)] == 4      # общий префикс с (20, 5, 1)


def test_continuation_not_taken_by_piece_whose_unit_changed_category():
    """C позже A по заезду; её объект 2 с границы стал VIL — она не забирает объект 1, в котором
    продолжается A."""
    us = [span(100, DLX, "1", hi=B - 1), span(100, DLX, "1", lo=B),
          span(101, DLX, "2", hi=B - 1), span(101, VIL, "2", lo=B), span(102, DLX, "3")]
    a = item(1, 5, 15, bounds=[B], number="50")
    c = item(2, 6, 20, bounds=[B], number="10")
    got, warns = run(us, [], [a, c])
    assert got[(("r", 1), 0)] == got[(("r", 1), 1)] == 100
    assert got[(("r", 2), 0)] == 101 and got[(("r", 2), 1)] == 102 and warns == []


def test_fixed_piece_keeps_continuation_and_blocks_pins():
    """Замороженная часть занимает объект раньше закреплений и служит предыдущей частью:
    продолжение сегмента за границей остаётся в том же объекте; закрепление поверх — конфликт."""
    us = units("1", "2")
    b = pos(D(5), PM)
    it = item(1, 2, 9, bounds=[b], number="9")
    frozen = AllocItem(it.key, it.number, it.segments, {}, {0: 101})
    pinned = item(2, 3, 4, pinned={0: 101}, number="1")
    got, warns = run(us, [], [frozen, pinned])
    assert got[(("r", 1), 0)] == got[(("r", 1), 1)] == 101
    assert [w.kind for w in warns] == ["pin_conflict"]


def test_fixed_piece_without_unit_stays_unplaced():
    it = item(1, 2, 9)
    got, warns = run(units("1"), [], [AllocItem(it.key, it.number, it.segments, {}, {0: None})])
    assert got == {(("r", 1), 0): None} and warns == []


# ── часть 2: приоритеты, без пинг-понга, пожелания, HK (спецификация OOO и блоков §4.2–§4.3) ──

def test_tentative_loses_first():
    """Подтверждённая и предварительная бронь конкурируют за последний объект после блока:
    без объекта остаётся предварительная, хотя она раньше и по заезду, и по номеру."""
    from app.modules.stays.domain.blocks import slots
    sl = slots({(1, DLX, D(10)): 1, (1, DLX, D(11)): 1}, {1: "Г"})
    tentative = item(1, 9, 12, rank=1)
    confirmed = item(2, 10, 12)
    got, placed, warns = allocate(units("1", "2"), [], sl, [tentative, confirmed], CODES, {})
    assert set(placed.values()) == {100}
    assert got == {(("r", 2), 0): 101, (("r", 1), 0): None}
    assert [(w.kind, w.key) for w in warns] == [("overbooked", ("r", 1))]


def test_ooo_moves_not_in_house_whole_stay():
    """OOO на одну ночь в середине проживания: незаселённая бронь целиком во втором объекте,
    а не 1 → 2 → 1; свободный после OOO первый объект достаётся следующей броне."""
    us = units("1", "2")
    got, warns = run(us, [OooRef(100, pos(D(8), PM), pos(D(9), AM), "ремонт")], [item(1, 5, 15), item(2, 10, 12)])
    assert got == {(("r", 1), 0): 101, (("r", 2), 0): 100} and warns == []


def test_ooo_moves_in_house_once_until_end():
    """Заселённый: прошлое и сегодня не трогаются; с первой ночи OOO (8-я) — один переезд в
    объект, свободный до выезда (3: объект 2 занят 11-го), без возврата после конца OOO."""
    T, Dn = pos(D(5), PM), pos(D(8), PM)
    guest = item(1, 2, 12, in_house=True, bounds=[T, Dn], fixed={0: 100})
    ooo = [OooRef(100, pos(D(8), PM), pos(D(10), AM), "ремонт"), OooRef(101, *hold_span(D(11), D(11)), "покраска")]
    got, warns = run(units("1", "2", "3"), ooo, [guest])
    assert [got[(("r", 1), i)] for i in (0, 1, 2)] == [100, 100, 102] and warns == []


def test_ooo_in_house_without_unit_overbooked_from_D():
    T, Dn = pos(D(5), PM), pos(D(8), PM)
    guest = item(1, 2, 12, in_house=True, bounds=[T, Dn], fixed={0: 100}, number="5")
    got, warns = run(units("1"), [OooRef(100, pos(D(8), PM), pos(D(9), AM), "ремонт")], [guest])
    assert [got[(("r", 1), i)] for i in (0, 1, 2)] == [100, 100, None]
    assert [(w.kind, w.piece_index) for w in warns] == [("overbooked", 2)]


def test_no_patchwork_overbooked_instead():
    """Первый объект свободен только в начале проживания, второй — только в конце: овербукинг,
    а не «лоскуты» 1 → 2; закончившийся овербукинг не мешает следующей броне."""
    ooo = [OooRef(100, pos(D(9), PM), pos(D(10), AM), "а"), OooRef(101, pos(D(6), PM), pos(D(7), AM), "б")]
    got, warns = run(units("1", "2"), ooo, [item(1, 5, 12, number="8"), item(2, 12, 14)])
    assert got == {(("r", 1), 0): None, (("r", 2), 0): 100}
    assert [(w.kind, w.piece_index, w.text) for w in warns] == [
        ("overbooked", 0, "Бронь 8: нет свободных объектов категории DLX на 05.09–12.09")]


def test_preferences_win_over_hk():
    turnover = {(101, D(5).toordinal()): True}
    got, _ = run(units("1", "2"), [], [item(1, 5, 8, prefs=lambda u: int(u.unit_id == 101))], turnover)
    assert got[(("r", 1), 0)] == 101


def test_preferences_best_score_wins():
    got, _ = run(units("1", "2", "3"), [], [item(1, 5, 8, prefs=lambda u: {100: 1, 101: 0, 102: 2}[u.unit_id])])
    assert got[(("r", 1), 0)] == 102


def test_hk_avoids_turnover_when_choice():
    """Оборот из входа (выезд вне расчёта) и из распределения (бронь 1 выезжает 5-го)."""
    got, _ = run(units("1", "2", "3"), [], [item(1, 2, 5), item(2, 5, 8)], {(101, D(5).toordinal()): True})
    assert got[(("r", 1), 0)] == 100 and got[(("r", 2), 0)] == 102


def test_hk_allows_turnover_when_no_choice():
    """Свободный со вчера объект занят — оборот допускается."""
    us = units("1", "2")
    got, warns = run(us, [], [item(1, 2, 5), item(2, 3, 9), item(3, 5, 8)])
    assert got[(("r", 2), 0)] == 101 and got[(("r", 3), 0)] == 100 and warns == []


def test_ooo_halfday_checkout_then_ooo_same_day():
    """Выезд утром 5-го и OOO с вечера 5-го до утра 7-го; заезд вечером 7-го — без конфликта."""
    ooo = [OooRef(100, *ooo_span(D(5), "PM", D(7), "AM"), "ремонт")]
    got, warns = run(units("1"), ooo, [item(1, 2, 5), item(2, 7, 9)])
    assert got == {(("r", 1), 0): 100, (("r", 2), 0): 100} and warns == []
