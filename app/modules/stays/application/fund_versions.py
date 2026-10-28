"""Фонд на дату: чтение снимков версий (спецификация stays-fund-versions §3.3).

Версия действует с вечера valid_from: граница — PM этого дня. Единственный читатель
CategoryState / GroupState / UnitState. Ничего не пишет и не коммитит."""
from __future__ import annotations

import datetime as dt
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from ..adapters.orm import (
    Category,
    CategoryState,
    FundVersion,
    GroupState,
    Unit,
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

    def unit_path(self, unit_id: int | None) -> tuple[int, ...]:
        """Путь узла объекта от корня; объект без узла (или не в фонде) — пустой путь."""
        u = self.units.get(unit_id)
        return self.groups[u.group_id].path if u is not None and u.group_id in self.groups else ()


@dataclass(frozen=True)
class FundTimeline:
    parts: list[tuple[dt.date, FundSnapshot]] = field(default_factory=list)   # по возрастанию даты
    _dates: list[dt.date] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        # on() зовётся на каждый объект и день шахматки — даты границ считаются один раз
        object.__setattr__(self, "_dates", [d for d, _ in self.parts])

    def on(self, day: dt.date) -> FundSnapshot:
        """Снимок, действующий в сутки day (последняя версия с valid_from <= day)."""
        i = bisect_right(self._dates, day) - 1
        return self.parts[max(i, 0)][1]

    def boundaries(self) -> list[dt.date]:
        """Даты начала версий внутри диапазона (без первой)."""
        return self._dates[1:]

    def snapshots(self) -> list[FundSnapshot]:
        return [s for _, s in self.parts]

    def _near(self, day: dt.date) -> list[FundSnapshot]:
        """Снимок дня, затем более ранние, затем более поздние — для подписи сущности,
        которой в фонде дня нет (выведена или ещё не заведена)."""
        i = max(bisect_right(self._dates, day) - 1, 0)
        snaps = self.snapshots()
        return snaps[i::-1] + snaps[i + 1:]

    def unit(self, unit_id: int | None, day: dt.date) -> UnitInfo | None:
        """Объект на день; нет в фонде дня — ближайшее его состояние в диапазоне."""
        if self.parts and unit_id in (here := self.on(day)).units:
            return here.units[unit_id]
        return next((s.units[unit_id] for s in self._near(day) if unit_id in s.units), None)

    def category(self, category_id: int, day: dt.date) -> CategoryInfo | None:
        """Категория на день; нет в фонде дня — ближайшее её состояние в диапазоне."""
        if self.parts and category_id in (here := self.on(day)).categories:
            return here.categories[category_id]
        return next((s.categories[category_id] for s in self._near(day) if category_id in s.categories), None)


def boundary_pos(d: dt.date) -> int:
    """Позиция границы версии с valid_from = d: вечер (PM) этого дня."""
    return halfday.pos(d, halfday.PM)


def version_cuts(db: Session) -> list[int]:
    """Границы всех опубликованных версий (позиции половинок). По ним режут сегменты на части и
    распределение, и виды: индекс части (Assignment.seg_index) не зависит от окна чтения."""
    return [boundary_pos(d) for d in db.scalars(
        select(FundVersion.valid_from).where(FundVersion.status == "published"))]


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


def _category_info(r: CategoryState) -> CategoryInfo:
    return CategoryInfo(id=r.category_id, code=r.code, title=r.title, kind=r.kind, weight=float(r.weight),
                        escorted=bool(r.escorted), sort_order=r.sort_order)


def _load(db: Session, versions: list[tuple[int, dt.date]],
          cats: dict[int, dict[int, CategoryInfo]] | None = None) -> list[FundSnapshot]:
    """Снимки перечисленных версий: по одному запросу на тип состояния (IN по всем версиям);
    флаги объектов — в том же запросе, что и объекты. cats — уже прочитанные категории."""
    ids = [v for v, _ in versions]
    if cats is None:
        cats = defaultdict(dict)
        for r in db.scalars(select(CategoryState).where(CategoryState.version_id.in_(ids))):
            cats[r.version_id][r.category_id] = _category_info(r)
    group_rows: dict[int, list[GroupState]] = defaultdict(list)
    for r in db.scalars(select(GroupState).where(GroupState.version_id.in_(ids))):
        group_rows[r.version_id].append(r)
    unit_rows: dict[tuple[int, int], UnitState] = {}
    flags: dict[tuple[int, int], set[int]] = defaultdict(set)
    for r, fid in db.execute(
            select(UnitState, UnitStateFlag.flag_id)
            .outerjoin(UnitStateFlag, and_(UnitStateFlag.version_id == UnitState.version_id,
                                           UnitStateFlag.unit_id == UnitState.unit_id))
            .where(UnitState.version_id.in_(ids))):
        unit_rows[(r.version_id, r.unit_id)] = r
        if fid is not None:
            flags[(r.version_id, r.unit_id)].add(fid)
    units: dict[int, dict[int, UnitInfo]] = defaultdict(dict)
    for (vid, uid), r in unit_rows.items():
        units[vid][uid] = UnitInfo(id=uid, label=r.label, category_id=r.category_id, group_id=r.group_id,
                                   floor=r.floor, flags=frozenset(flags.get((vid, uid), ())))
    return [FundSnapshot(version_id=vid, valid_from=d, categories=cats.get(vid, {}),
                         groups=_group_paths(group_rows[vid]), units=units[vid])
            for vid, d in versions]


def fund_for(db: Session, first: dt.date, last: dt.date) -> FundTimeline:
    """Опубликованные версии, действующие в [first, last]: та, что на first, и начатые позже.
    Запросов 3: версии с категориями (внешнее соединение) + узлы + объекты с флагами —
    фонд читают все виды, и бюджет SQL шахматки и табло дня (≤ 30) это учитывает."""
    published = FundVersion.status == "published"
    on_first = select(func.max(FundVersion.valid_from)).where(published, FundVersion.valid_from <= first)
    rows = db.execute(
        select(FundVersion.id, FundVersion.valid_from, CategoryState)
        .outerjoin(CategoryState, CategoryState.version_id == FundVersion.id)
        .where(published, FundVersion.valid_from <= last,
               FundVersion.valid_from >= func.coalesce(on_first.scalar_subquery(), dt.date.min))
        .order_by(FundVersion.valid_from)).all()
    if not rows:
        return FundTimeline([])
    versions = list(dict.fromkeys((vid, d) for vid, d, _ in rows))
    cats: dict[int, dict[int, CategoryInfo]] = defaultdict(dict)
    for vid, _d, c in rows:
        if c is not None:
            cats[vid][c.category_id] = _category_info(c)
    snaps = _load(db, versions, cats)
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


def unit_exists(db: Session, unit_id: int) -> bool:
    """Объект постоянен по id: проверка существования, а не наличия в версии."""
    return db.get(Unit, unit_id) is not None
