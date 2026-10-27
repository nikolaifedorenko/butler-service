"""Фонд на дату: чтение снимков версий (спецификация stays-fund-versions §3.3).

Версия действует с вечера valid_from: граница — PM этого дня. Единственный читатель
CategoryState / GroupState / UnitState. Ничего не пишет и не коммитит."""
from __future__ import annotations

import datetime as dt
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.orm import (
    Category,
    CategoryState,
    FundVersion,
    GroupState,
    UnitState,
    UnitStateFlag,
)
from ..domain import halfday

INITIAL_DATE = dt.date(2000, 1, 1)


@dataclass(frozen=True)
class CategoryInfo:
    id: int
    code: str
    title: str
    kind: str
    weight: float
    escorted: bool
    sort_order: int


@dataclass(frozen=True)
class GroupInfo:
    id: int
    parent_id: int | None
    title: str
    sort_order: int
    path: tuple[int, ...]       # id от корня, включая сам узел


@dataclass(frozen=True)
class UnitInfo:
    id: int
    label: str
    category_id: int
    group_id: int | None
    floor: str
    flags: frozenset[int]


@dataclass(frozen=True)
class FundSnapshot:
    version_id: int
    valid_from: dt.date
    categories: dict[int, CategoryInfo]
    groups: dict[int, GroupInfo]
    units: dict[int, UnitInfo]

    def branch(self, group_id: int) -> set[int]:
        """Узел и все его потомки."""
        return {g.id for g in self.groups.values() if group_id in g.path}

    def path_titles(self, group_id: int) -> tuple[str, ...]:
        return tuple(self.groups[i].title for i in self.groups[group_id].path)


@dataclass(frozen=True)
class FundTimeline:
    parts: list[tuple[dt.date, FundSnapshot]] = field(default_factory=list)   # по возрастанию даты

    def on(self, day: dt.date) -> FundSnapshot:
        """Снимок, действующий в сутки day (последняя версия с valid_from <= day)."""
        dates = [d for d, _ in self.parts]
        i = bisect_right(dates, day) - 1
        return self.parts[max(i, 0)][1]

    def boundaries(self) -> list[dt.date]:
        """Даты начала версий внутри диапазона (без первой)."""
        return [d for d, _ in self.parts[1:]]

    def snapshots(self) -> list[FundSnapshot]:
        return [s for _, s in self.parts]


def boundary_pos(d: dt.date) -> int:
    """Позиция границы версии с valid_from = d: вечер (PM) этого дня."""
    return halfday.pos(d, halfday.PM)


def _group_paths(rows: list[GroupState]) -> dict[int, GroupInfo]:
    by_id = {r.group_id: r for r in rows}

    def path(gid: int) -> tuple[int, ...]:
        chain: list[int] = []
        seen: set[int] = set()
        while gid is not None and gid in by_id and gid not in seen:
            seen.add(gid)
            chain.append(gid)
            gid = by_id[gid].parent_id
        return tuple(reversed(chain))

    return {r.group_id: GroupInfo(id=r.group_id, parent_id=r.parent_id, title=r.title,
                                  sort_order=r.sort_order, path=path(r.group_id)) for r in rows}


def _load(db: Session, versions: list[tuple[int, dt.date]]) -> list[FundSnapshot]:
    """Снимки перечисленных версий: по одному запросу на тип состояния (IN по всем версиям)."""
    ids = [v for v, _ in versions]
    cats: dict[int, dict[int, CategoryInfo]] = defaultdict(dict)
    for r in db.scalars(select(CategoryState).where(CategoryState.version_id.in_(ids))):
        cats[r.version_id][r.category_id] = CategoryInfo(
            id=r.category_id, code=r.code, title=r.title, kind=r.kind, weight=float(r.weight),
            escorted=bool(r.escorted), sort_order=r.sort_order)
    group_rows: dict[int, list[GroupState]] = defaultdict(list)
    for r in db.scalars(select(GroupState).where(GroupState.version_id.in_(ids))):
        group_rows[r.version_id].append(r)
    flags: dict[tuple[int, int], set[int]] = defaultdict(set)
    for vid, uid, fid in db.execute(
            select(UnitStateFlag.version_id, UnitStateFlag.unit_id, UnitStateFlag.flag_id)
            .where(UnitStateFlag.version_id.in_(ids))):
        flags[(vid, uid)].add(fid)
    units: dict[int, dict[int, UnitInfo]] = defaultdict(dict)
    for r in db.scalars(select(UnitState).where(UnitState.version_id.in_(ids))):
        units[r.version_id][r.unit_id] = UnitInfo(
            id=r.unit_id, label=r.label, category_id=r.category_id, group_id=r.group_id,
            floor=r.floor, flags=frozenset(flags.get((r.version_id, r.unit_id), ())))
    return [FundSnapshot(version_id=vid, valid_from=d, categories=cats[vid],
                         groups=_group_paths(group_rows[vid]), units=units[vid])
            for vid, d in versions]


def fund_for(db: Session, first: dt.date, last: dt.date) -> FundTimeline:
    """Опубликованные версии, действующие в [first, last]: та, что на first, и начатые позже.
    Запросов: версии + категории + узлы + флаги + объекты = 5."""
    rows = db.execute(
        select(FundVersion.id, FundVersion.valid_from)
        .where(FundVersion.status == "published", FundVersion.valid_from <= last)
        .order_by(FundVersion.valid_from)).all()
    start = max((i for i, (_, d) in enumerate(rows) if d <= first), default=0)
    needed = [(vid, d) for vid, d in rows[start:]]
    if not needed:
        return FundTimeline([])
    snaps = _load(db, needed)
    return FundTimeline([(s.valid_from, s) for s in snaps])


def fund_on(db: Session, day: dt.date) -> FundSnapshot:
    return fund_for(db, day, day).on(day)


def snapshot_of(db: Session, version_id: int) -> FundSnapshot:
    """Снимок любой версии, включая черновик."""
    d = db.scalar(select(FundVersion.valid_from).where(FundVersion.id == version_id))
    if d is None:
        raise LookupError(f"версия фонда {version_id} не найдена")
    return _load(db, [(version_id, d)])[0]


def category_exists(db: Session, category_id: int) -> bool:
    """Категория постоянна по id: проверка существования, а не наличия в версии."""
    return db.get(Category, category_id) is not None
