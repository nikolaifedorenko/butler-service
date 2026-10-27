"""Шахматка, задача 13: домен покрытия — кто кого ведёт, шаблоны, нагрузка, предупреждения, подбор."""
from __future__ import annotations

from datetime import date

from app.modules.stays.domain.candidates import rank_candidates
from app.modules.stays.domain.coverage import fill_template, resolve_day
from app.modules.stays.domain.load import day_loads
from app.modules.stays.domain.types import Line, StayDay
from app.modules.stays.domain.warnings import day_warnings
from app.modules.stays.ports.duty import DutyDay

D = date(2030, 5, 4)
ON, OFFD = DutyDay(True, None, False), DutyDay(False, None, False)
A, B, X, Y = 1, 2, 3, 4
CODES = frozenset({"ОТ", "Б"})


def stay(rid=10, unit=100, guests=None, weight=4.0, escorted=True, declined=False, group=None, path=(1,)):
    return StayDay(D, rid, group, unit, path, weight, escorted, declined, guests or {50: "regular"})


def line(emp, rid=10, guests=(), group=None, lid=1):
    return Line(lid, D, emp, None if group else rid, group, frozenset(guests), "manual", False)


def days(n):
    return [date(2030, 5, i) for i in range(4, 4 + n)]


def test_pair_template_follows_shifts():
    d1, d2, d3 = days(3)
    duty = {(A, d1): ON, (B, d2): ON}
    assert fill_template("pair", [d1, d2, d3], (A, B), duty, set()) == [(d1, A), (d2, B)]


def test_pair_both_on_shift_takes_a():
    (d1,) = days(1)
    assert fill_template("pair", [d1], (A, B), {(A, d1): ON, (B, d1): ON}, set()) == [(d1, A)]


def test_single_every_day_even_off_shift():
    d1, d2 = days(2)
    assert fill_template("single", [d1, d2], (X,), {}, set()) == [(d1, X), (d2, X)]


def test_template_keeps_busy_days():
    d1, d2 = days(2)
    assert fill_template("single", [d1, d2], (X,), {}, {d1}) == [(d2, X)]


def test_explicit_guests_override_whole_booking():
    s = stay(guests={50: "vvip", 51: "regular", 52: "regular"})
    cover = resolve_day([s], [line(X, lid=1), line(Y, guests=[51], lid=2)])
    assert cover.by_guest[(10, 50)] == (X,) and cover.by_guest[(10, 51)] == (Y,) and cover.by_guest[(10, 52)] == (X,)
    assert cover.uncovered == {} and cover.double == []


def test_group_line_covers_all_group_stays():
    s1, s2 = stay(rid=10, group=7, guests={50: "regular"}), stay(rid=11, group=7, guests={60: "regular"})
    cover = resolve_day([s1, s2], [line(X, group=7)])
    assert cover.by_guest == {(10, 50): (X,), (11, 60): (X,)}


def test_double_explicit_warns():
    s = stay(guests={50: "regular"})
    cover = resolve_day([s], [line(X, guests=[50], lid=1), line(Y, guests=[50], lid=2)])
    assert cover.double == [(10, 50, (X, Y))]


def test_uncovered_guests_listed():
    s = stay(guests={50: "regular", 51: "regular"})
    cover = resolve_day([s], [line(X, guests=[50])])
    assert cover.uncovered == {10: (51,)}


def test_move_day_butler_follows_guest():
    """«На что смотреть» №2: в день переезда объект — новый, вес считается один раз."""
    s = stay(unit=200)                     # StayDay уже несёт объект ночи (новый)
    cover = resolve_day([s], [line(X)])
    assert day_loads([s], cover, 1.0, 2.0) == {X: 4.0}


def test_weight_split_and_vip_bonus():
    s = stay(guests={50: "vvip", 51: "regular", 52: "regular"})
    cover = resolve_day([s], [line(X, guests=[50], lid=1), line(Y, guests=[51, 52], lid=2)])
    assert day_loads([s], cover, 1.0, 2.0) == {X: 4.0, Y: 2.0}       # 4/2 + 2 (VVIP) и 4/2


def test_shared_guest_bonus_split():
    s = stay(guests={50: "vip"})
    cover = resolve_day([s], [line(X, lid=1), line(Y, lid=2)])
    assert day_loads([s], cover, 1.0, 2.0) == {X: 2.5, Y: 2.5}
    assert cover.double == [(10, 50, (X, Y))]          # два «целиком» на одного гостя — предупреждение


def test_group_unit_weight_once():
    s1, s2 = stay(rid=10, group=7, guests={50: "regular"}), stay(rid=11, group=7, guests={60: "regular"})
    cover = resolve_day([s1, s2], [line(X, group=7)])
    assert day_loads([s1, s2], cover, 1.0, 2.0) == {X: 4.0}


def _warn(stays, lines, duty, limit=8.0):
    cover = resolve_day(stays, lines)
    loads = day_loads(stays, cover, 1.0, 2.0)
    return [(w.kind, w.employee_id, w.reservation_id) for w in day_warnings(D, stays, lines, cover, loads, duty, limit, CODES)]


def test_hole_and_not_for_declined_or_unescorted():
    assert _warn([stay()], [], {}) == [("hole", None, 10)]
    assert _warn([stay(declined=True)], [], {}) == []
    assert _warn([stay(escorted=False)], [], {}) == []


def test_off_shift_and_overload():
    s1, s2 = stay(rid=10, unit=100), stay(rid=11, unit=101, weight=6.0)
    got = _warn([s1, s2], [line(X, rid=10, lid=1), line(X, rid=11, lid=2)], {})
    assert ("off_shift", X, None) in got and ("overload", X, None) in got


def test_vacation_is_replacement_not_off_shift():
    """«На что смотреть» №3: код отпуска — «нужна подмена», без «вне смены»."""
    got = _warn([stay()], [line(X)], {(X, D): DutyDay(False, "ОТ", False)})
    assert got == [("need_replacement", X, 10)]


def test_on_shift_clean():
    assert _warn([stay()], [line(X)], {(X, D): ON}) == []


def test_candidates_order_knows_guest_first():
    duty = {(e, D): ON for e in (A, B, X)}
    got = rank_candidates(D, {50}, 100, (1,), [A, B, X], duty, {A: 0.0, B: 0.0, X: 4.0}, 4.0, 8.0,
                          known={X: {50}}, places={B: {("unit", 100)}}, replacement_codes=CODES)
    assert [c.employee_id for c in got] == [X, B, A]
    assert got[0].knows_guest and got[1].same_place and got[0].load_after == 8.0


def test_candidates_same_unit_then_same_group_then_closer():
    """Тот же объект → тот же узел → ближе по дереву (длиннее общий префикс) → меньше нагрузка."""
    duty = {(e, D): ON for e in (A, B, X, Y)}
    places = {A: {("unit", 100), ("path", (7, 8, 9))}, B: {("unit", 101), ("path", (7, 8, 9))},
              X: {("unit", 102), ("path", (7, 3))}}
    got = rank_candidates(D, {50}, 100, (7, 8, 9), [Y, X, B, A], duty, {A: 3.0, B: 2.0, X: 1.0}, 1.0, 8.0,
                          known={}, places=places, replacement_codes=CODES)
    assert [c.employee_id for c in got] == [A, B, X, Y]
    assert [c.same_place for c in got] == [True, True, False, False]


def test_candidates_exclude_overload_absent_and_off():
    duty = {(A, D): ON, (B, D): DutyDay(False, "ОТ", False), (Y, D): DutyDay(True, None, True)}
    got = rank_candidates(D, {50}, 100, (1,), [A, B, X, Y], duty, {A: 6.0, Y: 0.0}, 4.0, 8.0,
                          known={}, places={}, replacement_codes=CODES)
    assert [(c.employee_id, c.note) for c in got] == [(Y, "есть отлучка в смене")]
