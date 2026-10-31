"""Семейное дерево гостей (спека addendum §4): храним только первичные связи «родитель» и
«супруг» (с признаком «бывшие»), родство вычисляется обходом графа.

* Кровное родство — через ближайшего общего предка: i шагов вверх от гостя, j вниз до
  родственника; (1, 0) — родитель, (1, 1) — брат/сестра (достаточно одного общего родителя),
  (2, 2) — двоюродные и т. д. Названия — до прародителей и правнуков; дальше —
  «родственник (N-я степень)», N = i + j.
* Свойственники — только через действующего супруга (бывший не даёт свойственников) и только
  названные в спеке: родители, сиблинги и свояк со стороны супруга, супруги детей и сиблингов.
* Название — по полу родственника (m / f); пол не указан — нейтральное описательное
  («родитель супруга(и)», «ребёнок ребёнка»); для правнука без пола — «ребёнок ребёнка ребёнка»,
  для прадеда — «родитель прародителя».
* degree — число шагов «родитель / ребёнок» на пути; брак шагом не считается (супруг — 0).

Обходы — с множеством посещённых: зацикленные данные не дают бесконечного обхода."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Mapping

Parents = Mapping[int, tuple[int, ...]]
Spouses = Mapping[int, tuple[tuple[int, bool], ...]]


@dataclass(frozen=True)
class Person:
    id: int
    gender: str          # 'm' | 'f' | '' (не указан)


@dataclass(frozen=True)
class Kin:
    person_id: int       # кто — родственник
    title: str           # кем он приходится гостю: «мать», «невестка», …
    degree: int
    via: tuple[int, ...]  # промежуточные люди на пути от гостя к родственнику


@dataclass(frozen=True)
class FamilyGraph:
    parents: Parents     # ребёнок → его родители (не больше двух)
    spouses: Spouses     # гость → ((супруг, бывшие), …), в обе стороны


def _by(gender: str, m: str, f: str, n: str) -> str:
    return m if gender == "m" else f if gender == "f" else n


# (шагов вверх, шагов вниз) → (м, ж, без пола)
BLOOD = {
    (1, 0): ("отец", "мать", "родитель"),
    (0, 1): ("сын", "дочь", "ребёнок"),
    (1, 1): ("брат", "сестра", "сиблинг"),
    (2, 0): ("дедушка", "бабушка", "прародитель"),
    (0, 2): ("внук", "внучка", "ребёнок ребёнка"),
    (3, 0): ("прадедушка", "прабабушка", "родитель прародителя"),
    (0, 3): ("правнук", "правнучка", "ребёнок ребёнка ребёнка"),
    (2, 1): ("дядя", "тётя", "сиблинг родителя"),
    (1, 2): ("племянник", "племянница", "ребёнок сиблинга"),
    (2, 2): ("двоюродный брат", "двоюродная сестра", "двоюродный сиблинг"),
}


def blood_title(up: int, down: int, gender: str) -> str:
    names = BLOOD.get((up, down))
    return _by(gender, *names) if names else f"родственник ({up + down}-я степень)"


def parent_title(gender: str) -> str:
    return blood_title(1, 0, gender)


def child_title(gender: str) -> str:
    return blood_title(0, 1, gender)


def spouse_title(gender: str, former: bool) -> str:
    if former:
        return _by(gender, "бывший муж", "бывшая жена", "бывший(ая) супруг(а)")
    return _by(gender, "муж", "жена", "супруг(а)")


def _children(parents: Parents) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for child, ps in sorted(parents.items()):
        for p in ps:
            out.setdefault(p, []).append(child)
    return out


def _walk(start: int, step) -> dict[int, tuple[int, ...]]:
    """Обход в ширину: человек → кратчайший путь от start (start включён)."""
    paths = {start: (start,)}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        for nxt in step(cur):
            if nxt not in paths:
                paths[nxt] = (*paths[cur], nxt)
                queue.append(nxt)
    return paths


def _current_spouses(spouses: Spouses, pid: int) -> list[int]:
    return [s for s, former in spouses.get(pid, ()) if not former]


def children_of(parents: Parents) -> dict[int, list[int]]:
    """Обратная карта «родитель → дети» — построить один раз для многих вызовов kin_of."""
    return _children(parents)


def kin_of(person_id: int, people: Mapping[int, Person], parents: Parents, spouses: Spouses,
           children: Mapping[int, list[int]] | None = None) -> list[Kin]:
    """Все родственники гостя с названиями — кем каждый приходится гостю. children — готовая
    карта children_of(parents) (иначе строится здесь)."""
    def gender(pid: int) -> str:
        p = people.get(pid)
        return p.gender if p else ""

    children = _children(parents) if children is None else children
    down = lambda p: children.get(p, ())      # noqa: E731
    found: dict[int, Kin] = {}

    # кровные: общий предок C — i вверх, j вниз; ближайший (i + j, затем i)
    best: dict[int, tuple[int, int, tuple[int, ...]]] = {}
    ancestors = _walk(person_id, lambda p: parents.get(p, ()))
    for c, up_path in sorted(ancestors.items(), key=lambda kv: (len(kv[1]), kv[0])):
        i = len(up_path) - 1
        for y, down_path in _walk(c, down).items():
            j = len(down_path) - 1
            if y == person_id:
                continue
            key = (i + j, i)
            if y not in best or key < best[y][:2]:
                best[y] = (i + j, i, (*up_path, *down_path[1:]))
    for y, (total, i, path) in best.items():
        found[y] = Kin(y, blood_title(i, total - i, gender(y)), total, path[1:-1])

    def add(y: int, title: str, degree: int, via: tuple[int, ...]) -> None:
        if y != person_id and y not in found:
            found[y] = Kin(y, title, degree, via)

    for s, former in spouses.get(person_id, ()):
        add(s, spouse_title(gender(s), former), 0, ())

    def siblings(pid: int) -> list[tuple[int, int]]:
        """(сиблинг, общий родитель)."""
        out = {}
        for p in parents.get(pid, ()):
            for b in children.get(p, ()):
                if b != pid and b not in out:
                    out[b] = p
        return sorted(out.items())

    candidates: list[tuple[int, int, str, tuple[int, ...]]] = []   # (степень, кто, название, через)
    # супруги детей: зять — муж дочери, невестка — жена сына
    for c in children.get(person_id, ()):
        for t in _current_spouses(spouses, c):
            candidates.append((1, t, _by(gender(t), "зять", "невестка", "супруг(а) ребёнка"), (c,)))
    # супруги сиблингов: зять — муж сестры, невестка — жена брата
    for b, p in siblings(person_id):
        for t in _current_spouses(spouses, b):
            candidates.append((2, t, _by(gender(t), "зять", "невестка", "супруг(а) сиблинга"), (p, b)))
    # со стороны действующего супруга
    for s in _current_spouses(spouses, person_id):
        # муж или жена: по полу супруга, без него — по полу гостя
        side = gender(s) or {"m": "f", "f": "m"}.get(gender(person_id), "")
        for p in parents.get(s, ()):
            g = gender(p)
            title = (_by(g, "свёкор", "свекровь", "родитель мужа") if side == "m" else
                     _by(g, "тесть", "тёща", "родитель жены") if side == "f" else
                     _by(g, "отец супруга(и)", "мать супруга(и)", "родитель супруга(и)"))
            candidates.append((1, p, title, (s,)))
        for b, p in siblings(s):
            g = gender(b)
            title = (_by(g, "деверь", "золовка", "сиблинг мужа") if side == "m" else
                     _by(g, "шурин", "свояченица", "сиблинг жены") if side == "f" else
                     _by(g, "брат супруга(и)", "сестра супруга(и)", "сиблинг супруга(и)"))
            candidates.append((2, b, title, (s, p)))
            for t in _current_spouses(spouses, b):
                if t == s:
                    continue
                svoyak = side == "f" and g == "f" and gender(t) == "m"    # муж сестры жены
                candidates.append((2, t, "свояк" if svoyak else "супруг(а) сиблинга супруга(и)", (s, p, b)))
    for degree, y, title, via in sorted(candidates, key=lambda c: (c[0], c[1])):
        add(y, title, degree, via)
    return sorted(found.values(), key=lambda k: (k.degree, k.person_id))


def _ancestors(graph: FamilyGraph, pid: int) -> set[int]:
    return set(_walk(pid, lambda p: graph.parents.get(p, ()))) - {pid}


def _descendants(graph: FamilyGraph, pid: int) -> set[int]:
    children = _children(graph.parents)
    return set(_walk(pid, lambda p: children.get(p, ()))) - {pid}


def check_parent(child: int, parent: int, graph: FamilyGraph) -> str | None:
    """Можно ли сделать parent родителем child: текст ошибки или None."""
    if child == parent:
        return "Гость не может быть родителем самому себе"
    have = graph.parents.get(child, ())
    if parent in have:
        return None
    if len(have) >= 2:
        return "У ребёнка не больше двух родителей"
    lower = _descendants(graph, child) | {child}
    if parent in lower:
        return "Нельзя стать своим предком: этот гость — потомок ребёнка"
    upper = _ancestors(graph, parent) | {parent}
    for a in upper:
        if any(s in lower for s, _ in graph.spouses.get(a, ())):
            return "Супруги не могут стать предком и потомком друг друга"
    return None


def check_spouse(a: int, b: int, graph: FamilyGraph) -> str | None:
    """Можно ли сделать a и b супругами: текст ошибки или None."""
    if a == b:
        return "Гость не может быть супругом самому себе"
    if b in _ancestors(graph, a) or b in _descendants(graph, a):
        return "Супругом нельзя сделать своего предка или потомка"
    return None
