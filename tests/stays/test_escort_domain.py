"""Правила сопровождения, задача 3: нужен ли батлер (§4.1) и вес места с коэффициентами (§4.2) —
чистые функции домена."""
from __future__ import annotations

from datetime import date

from app.modules.stays.domain.coverage import resolve_day
from app.modules.stays.domain.escort import EscortNeed, escort_need, place_weight
from app.modules.stays.domain.load import day_loads
from app.modules.stays.domain.types import Line, StayDay

D = date(2030, 5, 4)
X, Y = 3, 4
NO = ("Вилла", False)


def need(mode="rules", category=NO, nodes=(), code=None, specials=()):
    return escort_need(mode, category=category, nodes=nodes, code=code, specials=specials)


def test_each_rule_alone():
    assert need() == EscortNeed(False, ())
    assert need(category=("Вилла", True)) == EscortNeed(True, ("категория Вилла",))
    assert need(nodes=[("Корпус", False), ("Винные виллы", True)]) == EscortNeed(True, ("узел Винные виллы",))
    assert need(code=("13", "полноценное", True)) == EscortNeed(True, ("код 13 — полноценное",))
    assert need(code=("14", "без батлера", False)) == EscortNeed(False, ())
    assert need(specials=["Петров А."]) == EscortNeed(True, ("◆ Особый гость Петров А.",))


def test_rules_are_or():
    got = need(category=("Вилла", True), nodes=[("Винные виллы", True)], code=("13", "полное", True),
               specials=["Петров А."])
    assert got.required and len(got.reasons) == 4


def test_node_escorted_category_not_needs():
    """Узел с сопровождением и категория без — нужно («или», §2)."""
    assert need(category=("Номер", False), nodes=[("Японские виллы", True)]).required


def test_required_overrides():
    assert need("required") == EscortNeed(True, ("отмечено вручную",))
    assert need("required", category=("Вилла", True)) == EscortNeed(True, ("отмечено вручную",))


def test_declined_overrides_special_and_code():
    got = need("declined", code=("13", "полное", True), specials=["Петров А."])
    assert got == EscortNeed(False, ("гость отказался",), declined=True)


def test_declined_without_rules_not_flagged():
    """Отказ там, где батлер и так не нужен, — не «отказался» на табло, а «не нужен»."""
    assert need("declined") == EscortNeed(False, ("гость отказался",), declined=False)


def test_reasons_text_and_order():
    got = need(category=("Вилла", True), nodes=[("Корпус", True), ("Винные виллы", True)],
               code=("03", "VIP", True), specials=["Петров А.", "Орлова М."])
    assert got.reasons == ("категория Вилла", "узел Корпус", "узел Винные виллы", "код 03 — VIP",
                           "◆ Особый гость Петров А.", "◆ Особый гость Орлова М.")


def test_place_weight_product():
    assert place_weight(2.0, [2.0], True, 1.5) == 6.0           # 2 × 2 × 1,5


def test_place_weight_max_code_one_place():
    """Две брони в одной вилле: код ×2 и без кода — 2 × 2 = 4; без кодов — 1."""
    assert place_weight(2.0, [2.0], False, 2.0) == 4.0
    assert place_weight(2.0, [], False, 2.0) == 2.0


def stay(rid, unit=100, guests=None, weight=2.0, code_factor=None, group=None):
    return StayDay(D, rid, group, unit, (1,), weight, EscortNeed(True, ("категория Вилла",)), code_factor,
                   guests if guests is not None else {50 + rid: False})


def line(emp, rid, lid):
    return Line(lid, D, emp, rid, None, frozenset(), "manual", False)


def test_special_once():
    """Два «Особых» в одной вилле при коэффициенте 2.0 — вес ×2, а не ×4."""
    s = stay(10, guests={50: True, 51: True})
    assert day_loads([s], resolve_day([s], [line(X, 10, 1)]), 2.0) == {X: 4.0}


def test_place_weight_rounded():
    assert place_weight(1.1, [3.0], False, 2.0) == 3.3


def test_load_split_evenly_two_butlers():
    """Вилла (2) с бронями кода ×2 и без кода, «Особый» (×1,5) — вес 6 на двоих поровну."""
    s1, s2 = stay(10, code_factor=2.0, guests={50: True}, group=7), stay(11, guests={60: False}, group=7)
    cover = resolve_day([s1, s2], [line(X, 10, 1), line(Y, 11, 2)])
    assert day_loads([s1, s2], cover, 1.5) == {X: 3.0, Y: 3.0}


def test_place_without_unit_is_own_place():
    s1, s2 = stay(10, unit=None, code_factor=2.0), stay(11, unit=None)
    cover = resolve_day([s1, s2], [line(X, 10, 1), line(X, 11, 2)])
    assert day_loads([s1, s2], cover, 2.0) == {X: 6.0}          # 2 × 2 + 2
