"""Дополнение шахматки, задача B1: вычисление родства по первичным связям «родитель / супруг»
(спека addendum §4) — по тесту на каждое название, по полу и без пола."""
from __future__ import annotations

import pytest

from app.modules.stays.domain.kinship import FamilyGraph, Person, check_parent, check_spouse, kin_of

X = 1


def _build(x_gender: str, steps):
    """Граф от гостя X по шагам: ("U", пол) — новый родитель текущего, ("D", пол) — новый ребёнок
    текущего, ("S", пол[, бывшие]) — новый супруг текущего. Возвращает (people, parents, spouses, Y)."""
    people = {X: Person(X, x_gender)}
    parents: dict[int, tuple[int, ...]] = {}
    spouses: dict[int, tuple[tuple[int, bool], ...]] = {}
    cur = X
    for n, step in enumerate(steps, start=2):
        kind, gender, *rest = step
        people[n] = Person(n, gender)
        if kind == "U":
            parents[cur] = (*parents.get(cur, ()), n)
        elif kind == "D":
            parents[n] = (cur,)
        else:
            former = bool(rest and rest[0])
            spouses[cur] = (*spouses.get(cur, ()), (n, former))
            spouses[n] = (*spouses.get(n, ()), (cur, former))
        cur = n
    return people, parents, spouses, cur


def _title(x_gender: str, steps) -> str | None:
    people, parents, spouses, y = _build(x_gender, steps)
    found = {k.person_id: k for k in kin_of(X, people, parents, spouses)}
    return found[y].title if y in found else None


U, D, S = "U", "D", "S"
# (путь от X к Y: шаги с полом; пол X; ожидаемое название Y для X)
CASES = [
    # родители / дети
    ([(U, "m")], "", "отец"), ([(U, "f")], "", "мать"), ([(U, "")], "", "родитель"),
    ([(D, "m")], "", "сын"), ([(D, "f")], "", "дочь"), ([(D, "")], "", "ребёнок"),
    # сиблинги (общий родитель)
    ([(U, ""), (D, "m")], "", "брат"), ([(U, ""), (D, "f")], "", "сестра"), ([(U, ""), (D, "")], "", "сиблинг"),
    # деды / внуки
    ([(U, ""), (U, "m")], "", "дедушка"), ([(U, ""), (U, "f")], "", "бабушка"),
    ([(U, ""), (U, "")], "", "прародитель"),
    ([(D, ""), (D, "m")], "", "внук"), ([(D, ""), (D, "f")], "", "внучка"),
    ([(D, ""), (D, "")], "", "ребёнок ребёнка"),
    # прадеды / правнуки
    ([(U, ""), (U, ""), (U, "m")], "", "прадедушка"), ([(U, ""), (U, ""), (U, "f")], "", "прабабушка"),
    ([(U, ""), (U, ""), (U, "")], "", "родитель прародителя"),
    ([(D, ""), (D, ""), (D, "m")], "", "правнук"), ([(D, ""), (D, ""), (D, "f")], "", "правнучка"),
    ([(D, ""), (D, ""), (D, "")], "", "ребёнок ребёнка ребёнка"),
    # дяди / тёти, племянники
    ([(U, ""), (U, ""), (D, "m")], "", "дядя"), ([(U, ""), (U, ""), (D, "f")], "", "тётя"),
    ([(U, ""), (U, ""), (D, "")], "", "сиблинг родителя"),
    ([(U, ""), (D, ""), (D, "m")], "", "племянник"), ([(U, ""), (D, ""), (D, "f")], "", "племянница"),
    ([(U, ""), (D, ""), (D, "")], "", "ребёнок сиблинга"),
    # двоюродные
    ([(U, ""), (U, ""), (D, ""), (D, "m")], "", "двоюродный брат"),
    ([(U, ""), (U, ""), (D, ""), (D, "f")], "", "двоюродная сестра"),
    ([(U, ""), (U, ""), (D, ""), (D, "")], "", "двоюродный сиблинг"),
    # дальше — степень
    ([(U, ""), (U, ""), (U, ""), (D, "m")], "", "родственник (4-я степень)"),
    ([(U, ""), (U, ""), (U, ""), (U, "f")], "", "родственник (4-я степень)"),
    # супруги
    ([(S, "m")], "f", "муж"), ([(S, "f")], "m", "жена"), ([(S, "")], "", "супруг(а)"),
    ([(S, "m", True)], "f", "бывший муж"), ([(S, "f", True)], "m", "бывшая жена"),
    ([(S, "", True)], "", "бывший(ая) супруг(а)"),
    # родители супруга: свёкор/свекровь — родители мужа (для жены), тесть/тёща — родители жены
    ([(S, "m"), (U, "m")], "f", "свёкор"), ([(S, "m"), (U, "f")], "f", "свекровь"),
    ([(S, "m"), (U, "")], "f", "родитель мужа"),
    ([(S, "f"), (U, "m")], "m", "тесть"), ([(S, "f"), (U, "f")], "m", "тёща"),
    ([(S, "f"), (U, "")], "m", "родитель жены"),
    ([(S, ""), (U, "m")], "f", "свёкор"),            # пол супруга не указан — по полу гостя
    ([(S, "f"), (U, "f")], "", "тёща"),              # пол гостя не указан — по полу супруга
    ([(S, ""), (U, "")], "", "родитель супруга(и)"),
    ([(S, ""), (U, "m")], "", "отец супруга(и)"), ([(S, ""), (U, "f")], "", "мать супруга(и)"),
    # супруг ребёнка: зять (муж дочери), невестка (жена сына)
    ([(D, "f"), (S, "m")], "", "зять"), ([(D, "m"), (S, "f")], "", "невестка"),
    ([(D, ""), (S, "")], "", "супруг(а) ребёнка"),
    # сиблинги супруга: деверь/золовка — мужа, шурин/свояченица — жены
    ([(S, "m"), (U, ""), (D, "m")], "f", "деверь"), ([(S, "m"), (U, ""), (D, "f")], "f", "золовка"),
    ([(S, "m"), (U, ""), (D, "")], "f", "сиблинг мужа"),
    ([(S, "f"), (U, ""), (D, "m")], "m", "шурин"), ([(S, "f"), (U, ""), (D, "f")], "m", "свояченица"),
    ([(S, "f"), (U, ""), (D, "")], "m", "сиблинг жены"),
    ([(S, ""), (U, ""), (D, "m")], "", "брат супруга(и)"), ([(S, ""), (U, ""), (D, "f")], "", "сестра супруга(и)"),
    ([(S, ""), (U, ""), (D, "")], "", "сиблинг супруга(и)"),
    # супруг сиблинга: зять (муж сестры), невестка (жена брата)
    ([(U, ""), (D, "f"), (S, "m")], "", "зять"), ([(U, ""), (D, "m"), (S, "f")], "", "невестка"),
    ([(U, ""), (D, ""), (S, "")], "", "супруг(а) сиблинга"),
    # свояк — муж сестры жены; прочие супруги сиблингов супруга — описательно
    ([(S, "f"), (U, ""), (D, "f"), (S, "m")], "m", "свояк"),
    ([(S, "m"), (U, ""), (D, "m"), (S, "f")], "f", "супруг(а) сиблинга супруга(и)"),
    ([(S, ""), (U, ""), (D, ""), (S, "")], "", "супруг(а) сиблинга супруга(и)"),
]


@pytest.mark.parametrize(("steps", "x_gender", "title"), CASES, ids=[c[2] + "/" + (c[1] or "-") for c in CASES])
def test_kinship_title(steps, x_gender, title):
    assert _title(x_gender, steps) == title


def test_every_contract_name_covered():
    """Каждое название из списка спеки §4 (по полу и нейтральное) есть в таблице выше."""
    names = {c[2] for c in CASES}
    contract = {"мать", "отец", "родитель", "сын", "дочь", "ребёнок", "брат", "сестра", "сиблинг", "бабушка",
                "дедушка", "прародитель", "внук", "внучка", "ребёнок ребёнка", "прабабушка", "прадедушка",
                "правнук", "правнучка", "тётя", "дядя", "племянник", "племянница", "двоюродный брат",
                "двоюродная сестра", "муж", "жена", "супруг(а)", "бывший муж", "бывшая жена", "свёкор",
                "свекровь", "тесть", "тёща", "зять", "невестка", "деверь", "золовка", "шурин", "свояченица",
                "свояк", "родитель супруга(и)", "супруг(а) ребёнка", "сиблинг супруга(и)"}
    assert contract <= names


def test_half_siblings_are_brother_and_sister():
    """Общий только один родитель — всё равно брат/сестра."""
    people = {i: Person(i, g) for i, g in ((1, "m"), (2, "f"), (3, "m"), (4, "f"), (5, "m"))}
    parents = {1: (2, 3), 4: (2, 5)}
    kin = {k.person_id: k.title for k in kin_of(1, people, parents, {})}
    assert kin[4] == "сестра"
    assert {k.person_id: k.title for k in kin_of(4, people, parents, {})}[1] == "брат"


def test_former_spouse_gives_no_in_laws():
    people, parents, spouses, _ = _build("m", [(S, "f", True), (U, "f")])
    kin = {k.person_id: k.title for k in kin_of(X, people, parents, spouses)}
    assert kin == {2: "бывшая жена"}


def test_blood_wins_over_in_law_and_degree_via():
    people, parents, spouses, y = _build("", [(U, ""), (U, ""), (D, ""), (D, "f")])
    kin = {k.person_id: k for k in kin_of(X, people, parents, spouses)}
    assert kin[y].degree == 4 and kin[y].via == (2, 3, 4)
    assert X not in kin


def _owner_family():
    """Иван (m) и Мария (f) — супруги; у Ивана родители и бабушка, у Марии родители; их сын Пётр."""
    ivan, maria, petr, ivan_mother, ivan_grandma, maria_father, maria_mother = range(1, 8)
    people = {ivan: Person(ivan, "m"), maria: Person(maria, "f"), petr: Person(petr, "m"),
              ivan_mother: Person(ivan_mother, "f"), ivan_grandma: Person(ivan_grandma, "f"),
              maria_father: Person(maria_father, "m"), maria_mother: Person(maria_mother, "f")}
    parents = {ivan: (ivan_mother,), ivan_mother: (ivan_grandma,), maria: (maria_father, maria_mother)}
    spouses = {ivan: ((maria, False),), maria: ((ivan, False),)}
    return people, parents, spouses


def test_owner_example_son_is_great_grandson_of_ivans_grandmother():
    people, parents, spouses = _owner_family()
    parents = {**parents, 3: (1, 2)}      # одна новая связь — сын Пётр у Ивана и Марии
    titles = lambda who: {k.person_id: k.title for k in kin_of(who, people, parents, spouses)}  # noqa: E731
    assert titles(5)[3] == "правнук"              # для бабушки Ивана
    assert titles(6)[3] == "внук" and titles(7)[3] == "внук"   # для родителей Марии
    assert titles(3)[5] == "прабабушка" and titles(3)[7] == "бабушка"
    assert titles(4)[2] == "невестка" and titles(2)[4] == "свекровь" and titles(1)[7] == "тёща"


def test_cannot_be_own_ancestor():
    g = FamilyGraph(parents={2: (1,), 3: (2,)}, spouses={})
    assert check_parent(1, 3, g) == "Нельзя стать своим предком: этот гость — потомок ребёнка"
    assert check_parent(1, 1, g) == "Гость не может быть родителем самому себе"
    assert check_parent(4, 3, g) is None


def test_third_parent_refused_in_domain():
    g = FamilyGraph(parents={3: (1, 2)}, spouses={})
    assert check_parent(3, 4, g) == "У ребёнка не больше двух родителей"


def test_spouse_cannot_be_descendant():
    g = FamilyGraph(parents={2: (1,), 3: (2,)}, spouses={})
    msg = "Супругом нельзя сделать своего предка или потомка"
    assert check_spouse(1, 3, g) == msg and check_spouse(3, 1, g) == msg
    assert check_spouse(3, 4, g) is None
    # обратное: супруги уже есть — родительская связь не делает одного предком другого
    married = FamilyGraph(parents={2: (1,)}, spouses={1: ((3, False),), 3: ((1, False),)})
    assert check_parent(3, 2, married) == "Супруги не могут стать предком и потомком друг друга"


def test_checks_terminate_on_cyclic_graph():
    """Защита от зацикленных данных: обходы с посещёнными, без бесконечного цикла."""
    g = FamilyGraph(parents={1: (2,), 2: (1,)}, spouses={})
    assert check_spouse(1, 3, g) is None
    people = {1: Person(1, "m"), 2: Person(2, "f")}
    assert kin_of(1, people, g.parents, {})
