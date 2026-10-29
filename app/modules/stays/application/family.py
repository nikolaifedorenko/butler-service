"""Семейное дерево гостей (спека addendum §4): загрузка графа первичных связей «родитель /
супруг» из базы, граф семьи для карточки и родственники среди проживающих. Названия родства —
domain/kinship.py. Ничего не коммитит."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, aliased

from ..adapters.orm import Guest, GuestLink
from ..domain.kinship import FamilyGraph, Person, children_of, kin_of
from .guests import format_phone
from .visibility import Level, at_least

FAMILY_KINDS = ("parent", "spouse")
GENERATIONS = 3          # граф карточки: до прадедов и правнуков (§4)
MAX_HOPS = 6             # двоюродные и свояк — 4 шага; с запасом
MAX_PEOPLE = 200


def _links_touching(db: Session, ids: set[int]) -> list[GuestLink]:
    return list(db.scalars(select(GuestLink).where(
        GuestLink.kind.in_(FAMILY_KINDS),
        or_(GuestLink.guest_a_id.in_(ids), GuestLink.guest_b_id.in_(ids))).order_by(GuestLink.id)))


def graph_of(links) -> FamilyGraph:
    """links — GuestLink или кортежи (a, b, kind, former)."""
    parents: dict[int, tuple[int, ...]] = {}
    spouses: dict[int, tuple[tuple[int, bool], ...]] = {}
    for ln in links:
        a, b, kind, former = ((ln.guest_a_id, ln.guest_b_id, ln.kind, ln.former) if isinstance(ln, GuestLink)
                              else ln)
        if kind == "parent":
            parents[b] = (*parents.get(b, ()), a)
        else:
            spouses[a] = (*spouses.get(a, ()), (b, former))
            spouses[b] = (*spouses.get(b, ()), (a, former))
    return FamilyGraph(parents=parents, spouses=spouses)


def family_links(db: Session, seeds: set[int]) -> list[GuestLink]:
    """Семейные связи всего связного графа семьи seeds, по id."""
    seen, frontier, links = set(seeds), set(seeds), {}
    while frontier:
        nxt = set()
        for ln in _links_touching(db, frontier):
            links[ln.id] = ln
            nxt |= {ln.guest_a_id, ln.guest_b_id} - seen
        seen |= nxt
        frontier = nxt
    return [links[k] for k in sorted(links)]


def family_graph(db: Session, seeds: set[int]) -> FamilyGraph:
    """Связный граф семьи seeds целиком — для проверок «не стать своим предком» и т. п."""
    return graph_of(family_links(db, seeds))


def _family_people(db: Session, gid: int) -> dict[int, int]:
    """Люди графа карточки: человек → поколение относительно гостя (вверх +, вниз −), в
    пределах GENERATIONS и MAX_HOPS шагов, не больше MAX_PEOPLE."""
    gen = {gid: 0}
    frontier = {gid}
    for _ in range(MAX_HOPS):
        if not frontier or len(gen) >= MAX_PEOPLE:
            break
        nxt = set()
        for ln in _links_touching(db, frontier):
            for me, other, delta in ((ln.guest_a_id, ln.guest_b_id, -1), (ln.guest_b_id, ln.guest_a_id, 1)):
                if me not in frontier or other in gen:
                    continue
                g = gen[me] + (delta if ln.kind == "parent" else 0)
                if abs(g) <= GENERATIONS and len(gen) < MAX_PEOPLE:
                    gen[other] = g
                    nxt.add(other)
        frontier = nxt
    return gen


def full_name(g: Guest) -> str:
    return " ".join(p for p in (g.last_name, g.first_name, g.middle_name) if p)


def family(db: Session, gid: int, level: Level) -> dict:
    """Граф семьи для карточки гостя: люди, первичные связи, вычисленные родственники.
    Уровень «с фамилиями» — фамилия и имя; полный — ФИО, телефон, дата рождения (§4)."""
    ids = set(_family_people(db, gid))
    links = list(db.scalars(select(GuestLink).where(
        GuestLink.kind.in_(FAMILY_KINDS), GuestLink.guest_a_id.in_(ids), GuestLink.guest_b_id.in_(ids))
        .order_by(GuestLink.id)))
    people = {g.id: g for g in db.scalars(select(Guest).where(Guest.id.in_(ids)))}
    graph = graph_of(links)
    full = at_least(level, "full")

    def person(g: Guest) -> dict:
        out = {"id": g.id, "name": full_name(g) if full else f"{g.last_name} {g.first_name}".strip(),
               "gender": g.gender, "level": g.level}
        if full:
            out |= {"phone": format_phone(g.phone), "birth_date": g.birth_date.isoformat() if g.birth_date else None}
        return out

    kin = kin_of(gid, {i: Person(i, g.gender) for i, g in people.items()}, graph.parents, graph.spouses)
    return {"people": [person(people[i]) for i in sorted(people)],
            "parents": [[ln.guest_b_id, ln.guest_a_id] for ln in links if ln.kind == "parent"],
            "spouses": [[ln.guest_a_id, ln.guest_b_id, ln.former] for ln in links if ln.kind == "spouse"],
            "kin": [{"person_id": k.person_id, "title": k.title, "degree": k.degree} for k in kin]}


def kin_among(db: Session, present: set[int], seeds: set[int] | None = None) -> dict[int, list[tuple[int, str]]]:
    """Родственники среди проживающих present (табло дня, карточка брони, §4): гость из seeds
    (по умолчанию — все present) → [(родственник из present, кем он приходится гостю)].
    Один запрос: все семейные связи с полом обеих сторон (бюджет SQL табло, §10) — первичных
    связей немного, обход — в памяти."""
    seeds = present if seeds is None else seeds
    if not seeds:
        return {}
    ga, gb = aliased(Guest), aliased(Guest)
    rows = db.execute(select(GuestLink.guest_a_id, GuestLink.guest_b_id, GuestLink.kind, GuestLink.former,
                             ga.gender, gb.gender)
                      .join(ga, ga.id == GuestLink.guest_a_id).join(gb, gb.id == GuestLink.guest_b_id)
                      .where(GuestLink.kind.in_(FAMILY_KINDS))).all()
    graph = graph_of((a, b, kind, former) for a, b, kind, former, _, _ in rows)
    people = {i: Person(i, g) for a, b, _, _, g_a, g_b in rows for i, g in ((a, g_a), (b, g_b))}
    children = children_of(graph.parents)
    out: dict[int, list[tuple[int, str]]] = {}
    for gid in sorted(seeds & set(people)):
        rel = [(k.person_id, k.title) for k in kin_of(gid, people, graph.parents, graph.spouses, children)
               if k.person_id in present]
        if rel:
            out[gid] = rel
    return out
