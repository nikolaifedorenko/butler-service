"""Черновик фонда и публикация версий (спецификация stays-fund-versions §4).

Единственный писатель снимков (CategoryState / GroupState / UnitState / UnitStateFlag).
Черновик — полная копия снимка базовой версии; действия правят копию, публикация делает её
версией. Каждая запись начинается с lock_module и сверяет rev черновика (409 при
одновременной правке). Ничего не коммитит — commit в роутере.

Черновик на дату уже опубликованной версии (Plan, Decision 1) заменяет её снимок при публикации:
valid_from уникален только среди опубликованных, у черновика остаётся его настоящая дата,
base_version_id указывает на заменяемую версию."""
from __future__ import annotations

import datetime as dt
import math
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete, func, insert, literal, select, update
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.time import local_date, now_local

from ..adapters.orm import (
    Category,
    CategoryKind,
    CategoryState,
    FundGroup,
    FundVersion,
    GroupState,
    Reservation,
    Unit,
    UnitFlag,
    UnitLineage,
    UnitState,
    UnitStateFlag,
)
from . import allocation as _allocation
from . import reservations
from .fund import FundConflict, FundError
from .fund_versions import INITIAL_DATE, FundSnapshot, fund_on, snapshot_of
from .fund_xlsx import SHEET_CATEGORIES, SHEET_FLAGS, SHEET_TREE, SHEET_UNITS, FileError, ParsedFund
from .locking import lock_module

# ── черновик ───────────────────────────────────────────────────────────────


def current_draft(db: Session) -> FundVersion | None:
    return db.scalar(select(FundVersion).where(FundVersion.status == "draft"))


def check_rev(draft: FundVersion, rev: int) -> None:
    if draft.rev != rev:
        raise FundConflict("черновик изменён другим пользователем — обновите страницу")


def bump(draft: FundVersion) -> None:
    draft.rev += 1


def _published_on(db: Session, day: dt.date) -> FundVersion | None:
    return db.scalar(select(FundVersion).where(FundVersion.status == "published",
                                               FundVersion.valid_from == day))


def _copy_states(db: Session, src: int, dst: int) -> None:
    """Полная копия снимка версии src в версию dst (порядок учитывает составные FK)."""
    for model, cols in (
        (CategoryState, ("category_id", "code", "title", "kind_id", "weight", "escorted", "sort_order")),
        (GroupState, ("group_id", "parent_id", "title", "sort_order")),
        (UnitState, ("unit_id", "label", "category_id", "group_id", "floor")),
        (UnitStateFlag, ("unit_id", "flag_id")),
    ):
        sel = select(literal(dst), *(getattr(model, c) for c in cols)).where(model.version_id == src)
        db.execute(insert(model).from_select(["version_id", *cols], sel))


def _drop_states(db: Session, version_id: int) -> None:
    for model in (UnitStateFlag, UnitState, GroupState, CategoryState):
        db.execute(delete(model).where(model.version_id == version_id))


def open_draft(db: Session, valid_from: dt.date, author_id: int | None, note: str = "") -> FundVersion:
    lock_module(db)
    if current_draft(db) is not None:
        raise FundConflict("черновик фонда уже существует — работайте в нём или дождитесь коллегу")
    if valid_from < local_date():
        raise FundError("дата версии не может быть в прошлом")
    same = _published_on(db, valid_from)
    base = same or db.scalar(select(FundVersion).where(
        FundVersion.status == "published", FundVersion.valid_from <= valid_from)
        .order_by(FundVersion.valid_from.desc()).limit(1)) or db.scalar(
        select(FundVersion).where(FundVersion.status == "published").order_by(FundVersion.valid_from).limit(1))
    if base is None:
        raise FundError("в фонде нет ни одной версии")
    draft = FundVersion(valid_from=valid_from, status="draft",
                        base_version_id=base.id, rev=1, author_id=author_id, note=note)
    db.add(draft)
    db.flush()
    _copy_states(db, base.id, draft.id)
    db.flush()
    return draft


def _draft(db: Session, rev: int) -> FundVersion:
    """Первое действие каждой записи: замок модуля, черновик, сверка rev."""
    lock_module(db)
    draft = current_draft(db)
    if draft is None:
        raise FundConflict("черновика фонда нет — откройте его")
    check_rev(draft, rev)
    return draft


def move_draft_date(db: Session, rev: int, valid_from: dt.date) -> None:
    draft = _draft(db, rev)
    if valid_from < local_date():
        raise FundError("дата версии не может быть в прошлом")
    if _published_on(db, valid_from) is not None:
        raise FundConflict("на эту дату уже есть версия — удалите черновик и откройте новый на эту дату")
    on_new = db.scalar(select(FundVersion.id).where(
        FundVersion.status == "published", FundVersion.valid_from <= valid_from)
        .order_by(FundVersion.valid_from.desc()).limit(1))
    if on_new != draft.base_version_id:    # другая база: снимок черновика не учёл бы её правки (§4.4)
        raise FundConflict("между датами есть другая версия фонда — удалите черновик и откройте новый "
                           "с нужной даты")
    draft.valid_from = valid_from
    bump(draft)
    db.flush()


# ── вспомогательное ────────────────────────────────────────────────────────


SORT_RANGE = (-100_000, 100_000)


def _sort_order(data: dict, current: int | None) -> int:
    """Порядок сортировки: целое в SORT_RANGE (как в API); не задан — прежний, у нового — 100."""
    v = data.get("sort_order", 100 if current is None else current)
    try:
        n = None if isinstance(v, bool) else int(str(v).strip())
    except ValueError:
        n = None
    if n is None or not SORT_RANGE[0] <= n <= SORT_RANGE[1]:
        raise FundError(f"порядок: целое число от {SORT_RANGE[0]} до {SORT_RANGE[1]}")
    return n


def _text(data: dict, key: str, current: str | None, limit: int, what: str) -> str:
    v = str(data.get(key, current) or "").strip()
    if not v:
        raise FundError(f"{what}: укажите значение")
    if len(v) > limit:
        raise FundError(f"{what}: не длиннее {limit} символов")
    return v


def _cat(db: Session, vid: int, category_id: int | None) -> CategoryState:
    row = db.get(CategoryState, (vid, category_id)) if category_id is not None else None
    if row is None:
        raise FundError("категории нет в черновике")
    return row


def _grp(db: Session, vid: int, group_id: int | None) -> GroupState | None:
    if group_id is None:
        return None
    row = db.get(GroupState, (vid, group_id))
    if row is None:
        raise FundError("узла дерева нет в черновике")
    return row


def _unit(db: Session, vid: int, unit_id: int) -> UnitState:
    row = db.get(UnitState, (vid, unit_id))
    if row is None:
        raise FundError("объекта нет в черновике")
    return row


def _unit_flags(db: Session, vid: int, unit_id: int) -> set[int]:
    return set(db.scalars(select(UnitStateFlag.flag_id).where(
        UnitStateFlag.version_id == vid, UnitStateFlag.unit_id == unit_id)))


def _put_flags(db: Session, vid: int, unit_id: int, flags: list[int], inherited: frozenset[int] = frozenset()) -> None:
    """inherited — флаги, унаследованные от исходных объектов: им архивность не мешает."""
    want = set(flags)
    have = _unit_flags(db, vid, unit_id)
    known = {f.id: f for f in db.scalars(select(UnitFlag).where(UnitFlag.id.in_(want)))} if want else {}
    for fid in want - have:
        if fid not in known:
            raise FundError(f"флага {fid} нет в справочнике")
        if known[fid].archived and fid not in inherited:
            raise FundError(f"флаг «{known[fid].title}» в архиве")
    if have - want:
        db.execute(delete(UnitStateFlag).where(
            UnitStateFlag.version_id == vid, UnitStateFlag.unit_id == unit_id,
            UnitStateFlag.flag_id.in_(have - want)))
    db.add_all(UnitStateFlag(version_id=vid, unit_id=unit_id, flag_id=f) for f in want - have)


def _free_label(db: Session, vid: int, label: str, own: int | None = None) -> None:
    taken = db.scalar(select(UnitState.unit_id).where(UnitState.version_id == vid, UnitState.label == label))
    if taken is not None and taken != own:
        raise FundConflict(f"обозначение «{label}» уже занято")


def _remove_unit(db: Session, vid: int, unit_id: int) -> None:
    db.execute(delete(UnitStateFlag).where(UnitStateFlag.version_id == vid, UnitStateFlag.unit_id == unit_id))
    db.execute(delete(UnitState).where(UnitState.version_id == vid, UnitState.unit_id == unit_id))
    db.flush()


# ── категории ──────────────────────────────────────────────────────────────


def _kind_for(db: Session, kind_id, current: int | None) -> int:
    """Вид категории из справочника: обязателен; архивный — только тот, что уже стоит у категории
    (новой категории и смене вида архивный вид не дают)."""
    if kind_id is None:
        raise FundError("вид категории: укажите значение")
    kind = db.get(CategoryKind, kind_id) if isinstance(kind_id, int) and not isinstance(kind_id, bool) else None
    if kind is None:
        raise FundError("вида категории нет в справочнике")
    if kind.archived and kind.id != current:
        raise FundError(f"вид «{kind.title}» в архиве")
    return kind.id


def save_category(db: Session, rev: int, data: dict, category_id: int | None) -> int:
    draft = _draft(db, rev)
    row = _cat(db, draft.id, category_id) if category_id is not None else None
    code = _text(data, "code", row.code if row else None, 16, "код категории")
    title = _text(data, "title", row.title if row else None, 120, "название категории")
    kind = _kind_for(db, data.get("kind_id", row.kind_id if row else None), row.kind_id if row else None)
    try:
        weight = Decimal(str(data.get("weight", row.weight if row else 1)))
    except InvalidOperation:
        raise FundError("вес категории — число") from None
    if weight <= 0:
        raise FundError("вес категории должен быть больше нуля")
    taken = db.scalar(select(CategoryState.category_id).where(
        CategoryState.version_id == draft.id, CategoryState.code == code))
    if taken is not None and taken != category_id:
        raise FundConflict(f"код категории «{code}» уже занят")
    if row is None:
        cat = Category()
        db.add(cat)
        db.flush()
        category_id = cat.id
        row = CategoryState(version_id=draft.id, category_id=category_id)
        db.add(row)
    row.code, row.title, row.kind_id, row.weight = code, title, kind, weight
    row.escorted = bool(data.get("escorted", row.escorted if row.escorted is not None else False))
    row.sort_order = _sort_order(data, row.sort_order)
    bump(draft)
    db.flush()
    return category_id


def retire_category(db: Session, rev: int, category_id: int) -> None:
    draft = _draft(db, rev)
    _cat(db, draft.id, category_id)
    if db.scalar(select(func.count()).select_from(UnitState).where(
            UnitState.version_id == draft.id, UnitState.category_id == category_id)):
        raise FundConflict("в категории есть объекты — сначала переведите или выведите их")
    db.execute(delete(CategoryState).where(CategoryState.version_id == draft.id,
                                           CategoryState.category_id == category_id))
    bump(draft)
    db.flush()


# ── дерево ─────────────────────────────────────────────────────────────────


def save_group(db: Session, rev: int, data: dict, group_id: int | None) -> int:
    draft = _draft(db, rev)
    row = _grp(db, draft.id, group_id)
    title = _text(data, "title", row.title if row else None, 120, "название узла")
    parent_id = data.get("parent_id", row.parent_id if row else None)
    _grp(db, draft.id, parent_id)
    if "/" in title:
        raise FundError("в названии узла нельзя использовать «/»")
    twin = db.scalar(select(GroupState.group_id).where(
        GroupState.version_id == draft.id, GroupState.parent_id == parent_id, GroupState.title == title))
    if twin is not None and twin != group_id:
        raise FundConflict("в этом узле уже есть подузел с таким названием")
    if group_id is not None:
        seen, cur = set(), parent_id
        while cur is not None:
            if cur == group_id or cur in seen:
                raise FundError("узел нельзя вложить в самого себя или своего потомка")
            seen.add(cur)
            cur = db.get(GroupState, (draft.id, cur)).parent_id
    if row is None:
        g = FundGroup()
        db.add(g)
        db.flush()
        group_id = g.id
        row = GroupState(version_id=draft.id, group_id=group_id)
        db.add(row)
    row.title, row.parent_id = title, parent_id
    row.sort_order = _sort_order(data, row.sort_order)
    bump(draft)
    db.flush()
    return group_id


def retire_group(db: Session, rev: int, group_id: int) -> None:
    draft = _draft(db, rev)
    _grp(db, draft.id, group_id)
    if db.scalar(select(func.count()).select_from(UnitState).where(
            UnitState.version_id == draft.id, UnitState.group_id == group_id)):
        raise FundConflict("в узле есть объекты — сначала переместите или выведите их")
    if db.scalar(select(func.count()).select_from(GroupState).where(
            GroupState.version_id == draft.id, GroupState.parent_id == group_id)):
        raise FundConflict("в узле есть подузлы — сначала переместите или выведите их")
    db.execute(delete(GroupState).where(GroupState.version_id == draft.id, GroupState.group_id == group_id))
    bump(draft)
    db.flush()


# ── объекты ────────────────────────────────────────────────────────────────


def _new_unit(db: Session, vid: int, label: str, category_id: int | None, group_id: int | None,
              floor: str, flags: list[int], inherited: frozenset[int] = frozenset()) -> int:
    label = _text({"label": label}, "label", None, 40, "обозначение объекта")
    _cat(db, vid, category_id)
    _grp(db, vid, group_id)
    _free_label(db, vid, label)
    u = Unit()
    db.add(u)
    db.flush()
    db.add(UnitState(version_id=vid, unit_id=u.id, label=label, category_id=category_id,
                     group_id=group_id, floor=str(floor or "")[:8]))
    db.flush()
    _put_flags(db, vid, u.id, flags, inherited)
    return u.id


def save_unit(db: Session, rev: int, data: dict, unit_id: int | None) -> int:
    draft = _draft(db, rev)
    if unit_id is None:
        uid = _new_unit(db, draft.id, data.get("label", ""), data.get("category_id"), data.get("group_id"),
                        data.get("floor", ""), list(data.get("flags", [])))
    else:
        row = _unit(db, draft.id, unit_id)
        label = _text(data, "label", row.label, 40, "обозначение объекта")
        _free_label(db, draft.id, label, own=unit_id)
        category_id = data.get("category_id", row.category_id)
        group_id = data.get("group_id", row.group_id)
        _cat(db, draft.id, category_id)
        _grp(db, draft.id, group_id)
        row.label, row.category_id, row.group_id = label, category_id, group_id
        row.floor = str(data.get("floor", row.floor) or "")[:8]
        if "flags" in data:
            _put_flags(db, draft.id, unit_id, list(data["flags"]))
        uid = unit_id
    bump(draft)
    db.flush()
    return uid


def retire_unit(db: Session, rev: int, unit_id: int) -> None:
    draft = _draft(db, rev)
    _unit(db, draft.id, unit_id)
    _remove_unit(db, draft.id, unit_id)
    bump(draft)


def split_unit(db: Session, rev: int, unit_id: int, parts: list[dict]) -> list[int]:
    draft = _draft(db, rev)
    src = _unit(db, draft.id, unit_id)
    if len(parts) < 2:
        raise FundError("для деления нужно минимум две части")
    flags = sorted(_unit_flags(db, draft.id, unit_id))
    base = (src.label, src.category_id, src.group_id, src.floor)
    _remove_unit(db, draft.id, unit_id)
    ids = []
    for p in parts:
        new_id = _new_unit(db, draft.id, p.get("label", ""), p.get("category_id", base[1]),
                           p.get("group_id", base[2]), p.get("floor", base[3]), flags,
                           frozenset(flags))
        db.add(UnitLineage(unit_id=new_id, predecessor_id=unit_id, version_id=draft.id))
        ids.append(new_id)
    bump(draft)
    db.flush()
    return ids


def merge_units(db: Session, rev: int, unit_ids: list[int], data: dict) -> int:
    draft = _draft(db, rev)
    unit_ids = list(dict.fromkeys(unit_ids))     # повтор id — одна строка происхождения
    if len(unit_ids) < 2:
        raise FundError("для объединения нужно минимум два объекта")
    rows = [_unit(db, draft.id, u) for u in unit_ids]
    groups, cats = {r.group_id for r in rows}, {r.category_id for r in rows}
    if len(groups) > 1 and "group_id" not in data:
        raise FundError("у объектов разные узлы — выберите узел результата")
    if len(cats) > 1 and "category_id" not in data:
        raise FundError("у объектов разные категории — выберите категорию результата")
    flags = sorted(set().union(*(_unit_flags(db, draft.id, u) for u in unit_ids)))
    floors = {r.floor for r in rows}
    for u in unit_ids:
        _remove_unit(db, draft.id, u)
    new_id = _new_unit(db, draft.id, data.get("label", ""), data.get("category_id", rows[0].category_id),
                       data.get("group_id", rows[0].group_id),
                       data.get("floor", rows[0].floor if len(floors) == 1 else ""), flags,
                       frozenset(flags))
    db.add_all(UnitLineage(unit_id=new_id, predecessor_id=u, version_id=draft.id) for u in unit_ids)
    bump(draft)
    db.flush()
    return new_id


def set_flag(db: Session, rev: int, flag_id: int, unit_ids: list[int], value: bool) -> None:
    draft = _draft(db, rev)
    flag = db.get(UnitFlag, flag_id)
    if flag is None:
        raise FundError("флага нет в справочнике")
    if value and flag.archived:
        raise FundError(f"флаг «{flag.title}» в архиве")
    for u in dict.fromkeys(unit_ids):             # повтор id — одна строка флага
        _unit(db, draft.id, u)
        have = db.get(UnitStateFlag, (draft.id, u, flag_id)) is not None
        if value and not have:
            db.add(UnitStateFlag(version_id=draft.id, unit_id=u, flag_id=flag_id))
        elif not value and have:
            db.execute(delete(UnitStateFlag).where(
                UnitStateFlag.version_id == draft.id, UnitStateFlag.unit_id == u,
                UnitStateFlag.flag_id == flag_id))
    bump(draft)
    db.flush()


# ── разница ────────────────────────────────────────────────────────────────


@dataclass
class FundDiff:
    units: list[dict] = field(default_factory=list)
    categories: list[dict] = field(default_factory=list)
    groups: list[dict] = field(default_factory=list)
    flags: list[dict] = field(default_factory=list)

    def empty(self) -> bool:
        return not (self.units or self.categories or self.groups or self.flags)


def _entries(before: dict[int, dict], after: dict[int, dict]) -> list[dict]:
    out = []
    for i in sorted(before.keys() | after.keys()):
        if i not in before:
            out.append({"id": i, "kind": "added", "before": {}, "after": after[i]})
        elif i not in after:
            out.append({"id": i, "kind": "retired", "before": before[i], "after": {}})
        elif before[i] != after[i]:
            out.append({"id": i, "kind": "changed", "before": before[i], "after": after[i]})
    return out


def _plain(s: FundSnapshot):
    def cat(c):
        return {"code": c.code, "title": c.title, "kind_id": c.kind_id, "weight": c.weight,
                "escorted": c.escorted, "sort_order": c.sort_order}

    def grp(g):
        return {"parent_id": g.parent_id, "title": g.title, "sort_order": g.sort_order}

    def unit(u):
        return {"label": u.label, "category_id": u.category_id, "group_id": u.group_id, "floor": u.floor}
    return ({i: cat(c) for i, c in s.categories.items()}, {i: grp(g) for i, g in s.groups.items()},
            {i: unit(u) for i, u in s.units.items()}, {i: sorted(u.flags) for i, u in s.units.items()})


def diff(db: Session, base_id: int, other_id: int) -> FundDiff:
    bc, bg, bu, bf = _plain(snapshot_of(db, base_id))
    oc, og, ou, of = _plain(snapshot_of(db, other_id))
    units = _entries(bu, ou)
    for e in units:
        if e["kind"] != "changed":                     # у нового / выведенного объекта флаги в карточке
            side = bf if e["kind"] == "retired" else of
            e["before" if e["kind"] == "retired" else "after"]["flags"] = side[e["id"]]
    flags = [{"id": i, "kind": "changed", "before": {"flags": bf[i]}, "after": {"flags": of[i]}}
             for i in sorted(bf.keys() & of.keys()) if bf[i] != of[i]]
    return FundDiff(units=units, categories=_entries(bc, oc), groups=_entries(bg, og), flags=flags)


# ── перенос в поздние версии (§4.4) ────────────────────────────────────────

# сущность → (модель, ключ, поля в версии); порядок — порядок составных FK
_STATE = {
    "category": (CategoryState, "category_id", ("code", "title", "kind_id", "weight", "escorted", "sort_order")),
    "group": (GroupState, "group_id", ("parent_id", "title", "sort_order")),
    "unit": (UnitState, "unit_id", ("label", "category_id", "group_id", "floor")),
}
_NAME = {"category": "code", "group": "title", "unit": "label"}


@dataclass
class _Fund:
    """Снимок версии изменяемыми словарями: сущность → id → поля; флаги объектов — множества."""
    rows: dict[str, dict[int, dict]]
    flags: dict[int, set[int]]


def _load_fund(db: Session, vid: int) -> _Fund:
    rows = {}
    for kind, (model, key, cols) in _STATE.items():
        rows[kind] = {r[0]: dict(zip(cols, r[1:], strict=True)) for r in db.execute(
            select(getattr(model, key), *(getattr(model, c) for c in cols)).where(model.version_id == vid))}
    flags: dict[int, set[int]] = {u: set() for u in rows["unit"]}
    for uid, fid in db.execute(select(UnitStateFlag.unit_id, UnitStateFlag.flag_id)
                               .where(UnitStateFlag.version_id == vid)):
        flags[uid].add(fid)
    return _Fund(rows, flags)


def _depth(groups: dict[int, dict], gid: int) -> int:
    n, seen = 0, set()
    while gid is not None and gid in groups and gid not in seen:
        seen.add(gid)
        gid, n = groups[gid]["parent_id"], n + 1
    return n


def _store_fund(db: Session, vid: int, f: _Fund) -> None:
    """Переписать снимок версии целиком: удаление до вставки снимает конфликты UNIQUE при обмене
    обозначениями, узлы вставляются от корня (FK на родителя в той же версии)."""
    _drop_states(db, vid)
    db.flush()
    groups = f.rows["group"]
    order = {"group": sorted(groups, key=lambda g: (_depth(groups, g), g))}
    for kind, (model, key, _cols) in _STATE.items():
        rows = f.rows[kind]
        values = [{"version_id": vid, key: i, **rows[i]} for i in order.get(kind, sorted(rows))]
        if values:
            db.execute(insert(model), values)
    pairs = [{"version_id": vid, "unit_id": u, "flag_id": fl} for u in sorted(f.flags) for fl in sorted(f.flags[u])]
    if pairs:
        db.execute(insert(UnitStateFlag), pairs)
    db.flush()


def _conflict(f: _Fund, kind: str, i: int, row: dict) -> str | None:
    """Что мешает записать строку row сущности i в снимок f (составные FK, UNIQUE, цикл дерева)."""
    if kind == "unit":
        if row["category_id"] not in f.rows["category"]:
            return "категории объекта в этой версии нет"
        if row["group_id"] is not None and row["group_id"] not in f.rows["group"]:
            return "узла объекта в этой версии нет"
        if any(j != i and u["label"] == row["label"] for j, u in f.rows["unit"].items()):
            return f"обозначение «{row['label']}» уже занято"
    elif kind == "category":
        if any(j != i and c["code"] == row["code"] for j, c in f.rows["category"].items()):
            return f"код категории «{row['code']}» уже занят"
    else:
        groups, cur, seen = f.rows["group"], row["parent_id"], set()
        if cur is not None and cur not in groups:
            return "родительского узла в этой версии нет"
        while cur is not None and cur in groups and cur not in seen:
            if cur == i:
                return "узел оказался бы в своём потомке"
            seen.add(cur)
            cur = groups[cur]["parent_id"]
    return None


def _busy(f: _Fund, kind: str, i: int) -> str | None:
    """Что мешает вывести сущность i из снимка f."""
    if kind == "category" and any(u["category_id"] == i for u in f.rows["unit"].values()):
        return "в категории этой версии есть объекты"
    if kind == "group":
        if any(u["group_id"] == i for u in f.rows["unit"].values()):
            return "в узле этой версии есть объекты"
        if any(g["parent_id"] == i for g in f.rows["group"].values()):
            return "в узле этой версии есть подузлы"
    return None


def _plain_value(v):
    return float(v) if isinstance(v, Decimal) else v


def _propagate(base: _Fund, draft: _Fund, later: _Fund, version: FundVersion, out: PublishResult) -> bool:
    """Правило §4.4 для одной поздней версии, поле за полем относительно базы черновика.
    Пишет строки отчёта в out; True — снимок поздней версии изменился."""
    b, d, v = base.rows, draft.rows, later.rows
    changed = False

    def note(bucket: list, kind: str, i: int, fld: str | None, **extra) -> None:
        row = d[kind].get(i) or b[kind].get(i) or v[kind].get(i) or {}
        bucket.append({"version_id": version.id, "valid_from": version.valid_from.isoformat(), "entity": kind,
                       "id": i, "name": row.get(_NAME[kind]), "field": fld, **extra})

    # правки и добавления: категории, узлы (от корня), объекты — FK ссылаются на уже перенесённое
    for kind, (_m, _k, cols) in _STATE.items():
        ids = sorted(d[kind], key=lambda g: (_depth(d["group"], g), g)) if kind == "group" else sorted(d[kind])
        for i in ids:
            if i not in b[kind]:                                         # добавлено в черновике
                problem = _conflict(later, kind, i, d[kind][i])
                if problem:
                    note(out.skipped, kind, i, None, reason=problem)
                    continue
                v[kind][i] = dict(d[kind][i])
                if kind == "unit":
                    later.flags[i] = set(draft.flags[i])
                note(out.propagated, kind, i, None, action="added")
                changed = True
                continue
            fields = [c for c in cols if b[kind][i][c] != d[kind][i][c]]
            if fields and i not in v[kind]:
                note(out.kept, kind, i, None, value=None, reason="в этой версии этого нет")
                continue
            for c in fields:
                if v[kind][i][c] != b[kind][i][c]:                       # поздняя версия меняла поле сама
                    note(out.kept, kind, i, c, value=_plain_value(v[kind][i][c]))
                    continue
                problem = _conflict(later, kind, i, {**v[kind][i], c: d[kind][i][c]})
                if problem:
                    note(out.skipped, kind, i, c, reason=problem)
                    continue
                v[kind][i][c] = d[kind][i][c]
                note(out.propagated, kind, i, c, action="changed", value=_plain_value(d[kind][i][c]))
                changed = True
    # флаги объектов: каждая отметка — отдельное поле «да/нет»
    for u in sorted(b["unit"].keys() & d["unit"].keys()):
        flips = base.flags[u] ^ draft.flags[u]
        if not flips:
            continue
        if u not in v["unit"]:
            note(out.kept, "unit", u, "flags", value=None, reason="в этой версии этого нет")
            continue
        for fl in sorted(flips):
            on = fl in draft.flags[u]
            if (fl in later.flags[u]) != on:                             # иначе версия уже такая
                (later.flags[u].add if on else later.flags[u].discard)(fl)
                note(out.propagated, "unit", u, "flags", action="changed", flag_id=fl, value=on)
                changed = True
    # выведенное: объекты, узлы (от листьев), категории — только если поздняя версия их не меняла
    for kind in ("unit", "group", "category"):
        gone = sorted((i for i in b[kind] if i not in d[kind] and i in v[kind]),
                      key=lambda i: (-_depth(b["group"], i) if kind == "group" else 0, i))
        for i in gone:
            if v[kind][i] != b[kind][i] or (kind == "unit" and later.flags[i] != base.flags[i]):
                note(out.kept, kind, i, None, value=None, reason="версия меняла его сама")
                continue
            problem = _busy(later, kind, i)
            if problem:
                note(out.skipped, kind, i, None, reason=problem)
                continue
            del v[kind][i]
            if kind == "unit":
                del later.flags[i]
            note(out.propagated, kind, i, None, action="retired")
            changed = True
    return changed


def _propagate_later(db: Session, draft: FundVersion, out: PublishResult) -> None:
    later = list(db.scalars(select(FundVersion).where(FundVersion.status == "published",
                                                      FundVersion.valid_from > draft.valid_from)
                            .order_by(FundVersion.valid_from)))
    if not later or draft.base_version_id is None:
        return
    db.flush()
    base, mine = _load_fund(db, draft.base_version_id), _load_fund(db, draft.id)
    for v in later:
        snap = _load_fund(db, v.id)
        if _propagate(base, mine, snap, v, out):
            _store_fund(db, v.id, snap)
    db.expire_all()


# ── перевод броней на категорию (§4.3) ─────────────────────────────────────


@dataclass(frozen=True)
class Transfer:
    reservation_id: int
    category_id: int


def _transfer(db: Session, principal, version: FundVersion, t: Transfer, categories: set[int]) -> dict:
    """Заезд с D и позже — бронь целиком в категорию; бронь, живущая на D, — переезд с D.
    Записывается тем же путём, что и правка формы: журнал брони «было → стало»."""
    day = version.valid_from
    r = db.get(Reservation, t.reservation_id)
    if r is None:
        raise FundError("бронь для перевода не найдена")
    who = f"бронь {r.number or r.id}"
    if t.category_id not in categories:
        raise FundError(f"{who}: категории перевода нет в фонде с {day:%d.%m.%Y}")
    if r.check_out <= day:
        raise FundError(f"{who}: выезд до {day:%d.%m.%Y} — переводить нечего")
    whole = r.check_in >= day
    if whole:
        doc = reservations.doc_of(db, r, category_id=t.category_id)
    else:
        doc = reservations.doc_of(db, r)
        doc["moves"] = sorted([m for m in doc["moves"] if m["move_date"] != day]
                              + [{"move_date": day, "category_id": t.category_id}], key=lambda m: m["move_date"])
    # члены группы получают ту же категорию и переезды (save_reservation) — журнал и им
    group = list(db.scalars(select(Reservation).where(Reservation.group_id == r.group_id,
                                                      Reservation.id != r.id))) if r.group_id else []
    others = [(m, reservations.reservation_snapshot(db, m)) for m in group]
    saved, before = reservations.save_reservation(db, doc, r.id, r.version)
    for m, was in [(saved, before), *others]:
        change = reservations.diff_of(was, db, m)
        if change or m is saved:
            audit(db, principal, "stays_reservation", f"reservation:{m.id}",
                  {"diff": change, "fund_version": version.id})
    return {"reservation_id": saved.id, "number": saved.number, "category_id": t.category_id,
            "since": None if whole else day.isoformat()}


# ── публикация и удаление ──────────────────────────────────────────────────


@dataclass
class PublishResult:
    version: FundVersion
    propagated: list[dict] = field(default_factory=list)   # перенесено в поздние версии
    kept: list[dict] = field(default_factory=list)         # поздняя версия меняла сама — оставлено
    skipped: list[dict] = field(default_factory=list)      # конфликт — не перенесено
    fund_diff: dict = field(default_factory=dict)          # черновик против базы
    transfers: list[dict] = field(default_factory=list)


def publish(db: Session, principal, rev: int | None = None, propagate: bool = True,
            transfers: Sequence[Transfer] = ()) -> PublishResult:
    """rev — ревизия, которую видел автор; сверяется уже под замком модуля, как в каждой записи.
    propagate — перенести правки в опубликованные версии после даты черновика (§4.4);
    transfers — перевод броней на категорию с даты версии (§4.3). Всё — одной транзакцией."""
    lock_module(db)
    draft = current_draft(db)
    if draft is None:
        raise FundConflict("черновика фонда нет")
    if rev is not None:
        db.refresh(draft)                  # после замка: правка коллеги могла bump-нуть rev
        check_rev(draft, rev)
    day = draft.valid_from
    if day < local_date():
        raise FundConflict("дата черновика прошла — сдвиньте на сегодня или позже")
    change = asdict(diff(db, draft.base_version_id, draft.id)) if draft.base_version_id else {}
    out = PublishResult(version=draft, fund_diff=change)
    if propagate:
        _propagate_later(db, draft, out)   # до замены снимка: база — ещё прежний снимок
    target = _published_on(db, day)
    if target is not None:                              # замена снимка версии на ту же дату
        _drop_states(db, target.id)
        db.flush()
        _copy_states(db, draft.id, target.id)
        db.execute(update(UnitLineage).where(UnitLineage.version_id == draft.id).values(version_id=target.id))
        db.execute(update(FundVersion).where(FundVersion.base_version_id == draft.id)
                   .values(base_version_id=target.id))
        _drop_states(db, draft.id)
        db.delete(draft)
        target.author_id, target.note = draft.author_id, draft.note
        version = target
    else:
        draft.status = "published"
        version = draft
    version.published_at = now_local()
    version.rev = 1
    out.version = version
    db.flush()
    db.info.pop(_allocation.CACHE_KEY, None)            # фонд другой — прежнее состояние распределения не годится
    if transfers:
        categories = set(fund_on(db, day).categories)
        out.transfers = [_transfer(db, principal, version, t, categories) for t in transfers]
    _allocation.run_allocation(db)
    audit(db, principal, "stays_fund_version", f"fund_version:{version.id}",
          {"valid_from": day.isoformat(), "diff": change, "propagated": out.propagated, "kept": out.kept,
           "skipped": out.skipped, "transfers": out.transfers})
    return out


def delete_version(db: Session, version_id: int) -> None:
    lock_module(db)
    v = db.get(FundVersion, version_id)
    if v is None:
        raise FundError("версии фонда нет")
    if v.status == "published":
        first = db.scalar(select(func.min(FundVersion.valid_from)).where(FundVersion.status == "published"))
        if v.valid_from == first:
            raise FundConflict("исходную версию фонда удалить нельзя")
        if v.valid_from <= local_date():
            raise FundConflict("действующую и прошедшие версии удалить нельзя")
    if db.scalar(select(func.count()).select_from(FundVersion).where(
            FundVersion.status == "draft", FundVersion.base_version_id == v.id)) and v.status == "published":
        raise FundConflict("на эту версию опирается черновик — сначала удалите черновик")
    _drop_states(db, v.id)
    db.execute(delete(UnitLineage).where(UnitLineage.version_id == v.id))
    db.execute(update(FundVersion).where(FundVersion.base_version_id == v.id).values(base_version_id=None))
    db.flush()
    was_published = v.status == "published"
    db.delete(v)
    db.flush()
    if was_published:
        _allocation.run_allocation(db)


# ── начальная загрузка ─────────────────────────────────────────────────────


def seed_initial(db: Session, categories: list[dict], groups: list[dict], flags: list[dict],
                 units: list[dict]) -> None:
    """Заполняет исходную версию (INITIAL_DATE) напрямую, минуя черновик. Только для демо-сида
    и начальной загрузки. Ключи — как в телах API: категория — code/title/kind_id/escorted/weight/
    sort_order; узел — path (названия от корня; недостающие предки заводятся сами) и sort_order;
    флаг — title/color/sort_order; объект — label, category (код), path, floor, flags (названия).
    FundConflict, если в исходной версии уже есть объекты."""
    lock_module(db)
    vid = db.scalar(select(FundVersion.id).where(FundVersion.valid_from == INITIAL_DATE,
                                                 FundVersion.status == "published"))
    if vid is None:
        raise FundError("исходной версии фонда нет")
    if db.scalar(select(func.count()).select_from(UnitState).where(UnitState.version_id == vid)):
        raise FundConflict("в исходной версии уже есть объекты")
    cats: dict[str, int] = {}
    for i, c in enumerate(categories):
        cats[c["code"]] = cid = _add(db, Category())
        db.add(CategoryState(version_id=vid, category_id=cid, code=c["code"], title=c["title"],
                             kind_id=c["kind_id"], escorted=bool(c.get("escorted", False)),
                             weight=Decimal(str(c.get("weight", 1))), sort_order=c.get("sort_order", i * 10)))
    nodes: dict[tuple[str, ...], int] = {}

    def node(path: tuple[str, ...], sort_order: int | None = None) -> int:
        if path not in nodes:
            if "/" in path[-1]:
                raise FundError("в названии узла нельзя использовать «/»")
            parent = node(path[:-1]) if len(path) > 1 else None
            nodes[path] = gid = _add(db, FundGroup())
            db.add(GroupState(version_id=vid, group_id=gid, parent_id=parent, title=path[-1],
                              sort_order=100 if sort_order is None else sort_order))
        return nodes[path]

    for i, g in enumerate(groups):
        node(tuple(g["path"]), g.get("sort_order", i * 10))
    flag_ids: dict[str, int] = {t: fid for fid, t in db.execute(select(UnitFlag.id, UnitFlag.title))}
    for f in flags:
        if f["title"] not in flag_ids:
            flag_ids[f["title"]] = save_flag(db, f, None)
    db.flush()
    pending = []
    for u in units:
        uid = _add(db, Unit())
        group = node(tuple(u["path"])) if u.get("path") else None
        db.add(UnitState(version_id=vid, unit_id=uid, label=u["label"], category_id=cats[u["category"]],
                         group_id=group, floor=str(u.get("floor", ""))[:8]))
        pending.extend((uid, flag_ids[t]) for t in u.get("flags", ()))
    db.flush()
    db.add_all(UnitStateFlag(version_id=vid, unit_id=uid, flag_id=fid) for uid, fid in pending)
    db.flush()


def _add(db: Session, row) -> int:
    db.add(row)
    db.flush()
    return row.id


# ── файл фонда в черновик (§9.2) ───────────────────────────────────────────


class FundFileError(FundError):
    """Файл не применён: все ошибки списком с листом и строкой; ничего не записано (вызывающий
    откатывает транзакцию — вместе с открытием черновика)."""

    def __init__(self, errors: list[FileError]) -> None:
        super().__init__("; ".join(f"{e.sheet}:{e.row} {e.message}" for e in errors))
        self.errors = errors


def kind_titles(kinds: Sequence[CategoryKind]) -> list[str]:
    """Названия видов, которые можно указать в файле (без архивных) — для текста ошибки."""
    return [k.title for k in kinds if not k.archived]


def unknown_kind_message(title: str, kinds: Sequence[CategoryKind]) -> str:
    """Ошибка «вида нет в справочнике»; пустой справочник — подсказка, где его завести."""
    names = kind_titles(kinds)
    if not names:
        return f"вид «{title}» — справочник видов пуст: сначала заведите вид на вкладке «Виды»"
    return f"вид «{title}» — нет в справочнике видов: " + ", ".join(names)


_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
_WEIGHT_MAX = Decimal("999.99")                 # Numeric(5, 2)


def _file_weight(w: float) -> Decimal | None:
    if not math.isfinite(w):
        return None
    d = Decimal(str(w)).quantize(Decimal("0.01"))
    return d if Decimal(0) < d <= _WEIGHT_MAX else None


@dataclass
class _FlagPlan:
    """Что файл делает со справочником флагов: колонка «Объектов» → флаг и правки справочника."""
    column: dict[str, int | None] = field(default_factory=dict)   # название → id; None — новый флаг
    rename: dict[int, str] = field(default_factory=dict)          # id → новое название
    recolour: dict[int, str] = field(default_factory=dict)        # id → новый цвет
    new_color: dict[str, str] = field(default_factory=dict)       # новый флаг → цвет с листа


def _plan_flags(parsed: ParsedFund, dictionary: dict[int, UnitFlag], err) -> _FlagPlan:
    """Флаги файла → флаги справочника. Строка листа «Флаги» с ID — тот флаг (новое название,
    цвет). Колонка «Объектов» без строки на листе: прежнее название флага, переименованного на
    листе, — этот флаг; название флага справочника, которого на листе нет, — он; иначе новый
    флаг — если это однозначно (на листе нет переименованного флага, потерявшего колонку)."""
    by_title = {f.title: f for f in dictionary.values()}
    on_sheet = {f.id: f for f in parsed.flags if f.row_no and f.id is not None}
    plan = _FlagPlan()
    for f in parsed.flags:
        if f.id is not None and f.id not in dictionary:
            err(SHEET_FLAGS, f.row_no, f"ID {f.id} нет в справочнике флагов — ID не меняют; "
                                       "новому флагу оставьте ID пустым")
        if len(f.title) > 80:
            err(SHEET_FLAGS if f.row_no else SHEET_UNITS, f.row_no or 1,
                f"название флага «{f.title[:20]}…» длиннее 80 символов")
        if f.color and not _COLOR.fullmatch(f.color):
            err(SHEET_FLAGS, f.row_no, f"цвет «{f.color}» — ожидается #RRGGBB")
    for fid, f in on_sheet.items():
        if (d := dictionary.get(fid)) is None:
            continue
        plan.column[f.title] = fid
        if d.title != f.title:
            plan.rename[fid] = f.title
        if f.color and d.color != f.color:
            plan.recolour[fid] = f.color
    for f in parsed.flags:
        if f.id is not None:
            continue
        d = by_title.get(f.title)
        if d is None or (d.id in on_sheet and f.row_no):      # новое название или новая строка листа
            plan.column[f.title] = None
            if f.color:
                plan.new_color[f.title] = f.color
            continue
        plan.column[f.title] = d.id                          # прежнее название / флаг не на листе
        if f.color and d.color != f.color:
            plan.recolour[d.id] = f.color

    headers = parsed.flag_columns
    mapped: dict[int, str] = {}
    for h in headers:
        fid = plan.column.get(h)
        if fid is None:
            continue
        if fid in mapped:
            err(SHEET_UNITS, 1, f"колонка флага «{h}» не совпадает с листом «Флаги»: флаг ID {fid} "
                                f"там называется «{on_sheet[fid].title if fid in on_sheet else dictionary[fid].title}», "
                                f"и колонка «{mapped[fid]}» — тоже он; оставьте одну колонку")
        mapped.setdefault(fid, h)
    lost = [fid for fid in plan.rename if fid not in mapped]  # переименован на листе, колонки нет
    sheet_titles = {f.title for f in parsed.flags if f.row_no}
    for h in headers:
        if lost and plan.column.get(h, 0) is None and h not in sheet_titles:
            err(SHEET_UNITS, 1, f"колонка флага «{h}» не совпадает с листом «Флаги»: это новый флаг или "
                                f"переименованный «{dictionary[lost[0]].title}» → «{on_sheet[lost[0]].title}»? Назовите колонку как на листе")
    final = {fid: plan.rename.get(fid, d.title) for fid, d in dictionary.items()}
    for fid, title in plan.rename.items():
        twin = next((i for i, t in final.items() if t == title and i != fid), None)
        if twin is not None:
            err(SHEET_FLAGS, on_sheet[fid].row_no, f"флаг «{title}» уже есть в справочнике (ID {twin})")
    return plan


def apply_file(db: Session, rev: int, parsed: ParsedFund) -> tuple[FundDiff, dict]:
    """Разобранный файл фонда → снимок черновика (§9.2): строка с ID — та же сущность (меняется
    всё, что изменено), пустой ID — новая, сущность черновика без строки в файле выводится,
    «Из чего» у новой строки — lineage. ID, которого нет в черновике (на листе «Флаги» — в
    справочнике), — ошибка. Сначала проверка всего файла, затем запись; при любой ошибке —
    FundFileError и ничего не записано. Справочник флагов не версионируется: переименование и
    цвет флага и новые флаги применяются к нему сразу, как правка справочника, и при удалении
    черновика не откатываются; флаг без строки в файле не удаляется. Возвращает разницу
    черновика с его базой и правки справочника {created, renamed, recoloured}."""
    draft = _draft(db, rev)
    have = _load_fund(db, draft.id)
    hc, hg, hu = have.rows["category"], have.rows["group"], have.rows["unit"]
    errors: list[FileError] = []

    def err(sheet: str, row: int, msg: str) -> None:
        errors.append(FileError(sheet, row, msg))

    def unknown(sheet: str, row: int, i: int) -> None:
        err(sheet, row, f"ID {i} нет в фонде на дату черновика — ID не меняют; новой записи оставьте ID пустым")

    dictionary = {f.id: f for f in db.scalars(select(UnitFlag))}
    plan = _plan_flags(parsed, dictionary, err)
    kinds = list(db.scalars(select(CategoryKind).order_by(CategoryKind.sort_order, CategoryKind.id)))
    kind_by_title = {k.title.casefold(): k for k in kinds}

    cats: dict[int, dict] = {}                   # ParsedCategory.row_no → поля
    for c in parsed.categories:
        if c.id is not None and c.id not in hc:
            unknown(SHEET_CATEGORIES, c.row_no, c.id)
        if len(c.code) > 16:
            err(SHEET_CATEGORIES, c.row_no, "код категории длиннее 16 символов")
        if len(c.title) > 120:
            err(SHEET_CATEGORIES, c.row_no, "название категории длиннее 120 символов")
        if c.kind:
            k = kind_by_title.get(c.kind.casefold())
            kind = k.id if k is not None else None
            if k is None:
                err(SHEET_CATEGORIES, c.row_no, unknown_kind_message(c.kind, kinds))
            elif k.archived and not (c.id in hc and hc[c.id]["kind_id"] == k.id):
                err(SHEET_CATEGORIES, c.row_no, f"вид «{k.title}» в архиве")
        elif c.id in hc:
            kind = hc[c.id]["kind_id"]                     # пусто — вид категории не меняется
        else:
            kind = None
            err(SHEET_CATEGORIES, c.row_no, "не указан вид категории")
        weight = _file_weight(c.weight)
        if weight is None:
            err(SHEET_CATEGORIES, c.row_no, f"вес {c.weight} — ожидается число больше 0 и не больше {_WEIGHT_MAX}")
        cats[c.row_no] = {"code": c.code, "title": c.title, "kind_id": kind, "weight": weight,
                          "escorted": c.escorted, "sort_order": c.sort_order}
    for g in parsed.groups:
        if g.id is not None and g.id not in hg:
            unknown(SHEET_TREE, g.row_no, g.id)
        if len(g.path[-1]) > 120:
            err(SHEET_TREE, g.row_no, "название узла длиннее 120 символов")
    for u in parsed.units:
        if u.id is not None and u.id not in hu:
            unknown(SHEET_UNITS, u.row_no, u.id)
        if len(u.label) > 40:
            err(SHEET_UNITS, u.row_no, "номер объекта длиннее 40 символов")
        if len(u.floor) > 8:
            err(SHEET_UNITS, u.row_no, "этаж длиннее 8 символов")
        for p in u.predecessors:
            if p not in hu:
                err(SHEET_UNITS, u.row_no, f"«Из чего»: ID {p} нет в фонде на дату черновика")
        had = have.flags.get(u.id, set()) if u.id is not None else set().union(
            *(have.flags.get(p, set()) for p in u.predecessors))
        for t in sorted(u.flags):
            f = dictionary.get(plan.column.get(t))
            if f is not None and f.archived and f.id not in had:
                err(SHEET_UNITS, u.row_no, f"флаг «{t}» в архиве")
    if errors:
        raise FundFileError(errors)

    # запись: справочник флагов, новые id, снимок черновика целиком, lineage
    changes: dict[str, list[dict]] = {"created": [], "renamed": [], "recoloured": []}
    was = {fid: dictionary[fid].title for fid in plan.rename}
    for fid in plan.rename:              # сначала временные названия: обмен названиями — без UNIQUE
        dictionary[fid].title = f"\u2063{fid}"
    db.flush()
    for fid, title in plan.rename.items():
        changes["renamed"].append({"id": fid, "from": was[fid], "to": title})
        dictionary[fid].title = title
    for fid, color in plan.recolour.items():
        changes["recoloured"].append({"id": fid, "from": dictionary[fid].color, "to": color})
        dictionary[fid].color = color
    db.flush()
    flag_ids = dict(plan.column)
    for title, fid in plan.column.items():
        if fid is None:
            color = plan.new_color.get(title)
            flag_ids[title] = save_flag(db, {"title": title, **({"color": color} if color else {})}, None)
            changes["created"].append({"id": flag_ids[title], "title": title})

    want = _Fund({"category": {}, "group": {}, "unit": {}}, {})
    code_id: dict[str, int] = {}
    for c in parsed.categories:
        cid = c.id if c.id is not None else _add(db, Category())
        want.rows["category"][cid] = cats[c.row_no]
        code_id[c.code] = cid
    path_id: dict[tuple[str, ...], int] = {}
    for g in sorted(parsed.groups, key=lambda g: len(g.path)):         # родитель раньше потомка
        gid = g.id if g.id is not None else _add(db, FundGroup())
        path_id[g.path] = gid
        want.rows["group"][gid] = {"parent_id": path_id[g.path[:-1]] if len(g.path) > 1 else None,
                                   "title": g.path[-1], "sort_order": g.sort_order}
    lineage: list[UnitLineage] = []
    for u in parsed.units:
        uid = u.id if u.id is not None else _add(db, Unit())
        want.rows["unit"][uid] = {"label": u.label, "category_id": code_id[u.category_code],
                                  "group_id": path_id[u.group_path] if u.group_path else None, "floor": u.floor}
        want.flags[uid] = {flag_ids[t] for t in u.flags}
        lineage += [UnitLineage(unit_id=uid, predecessor_id=p, version_id=draft.id)
                    for p in dict.fromkeys(u.predecessors)]
    if want != have:                     # без правок снимок не трогаем
        _store_fund(db, draft.id, want)
    db.add_all(lineage)
    bump(draft)
    db.flush()
    change = diff(db, draft.base_version_id, draft.id) if draft.base_version_id is not None else FundDiff()
    return change, changes


# ── справочник флагов (вне черновика) ──────────────────────────────────────


def save_flag(db: Session, data: dict, flag_id: int | None) -> int:
    lock_module(db)
    row = db.get(UnitFlag, flag_id) if flag_id is not None else None
    if flag_id is not None and row is None:
        raise FundError("флага нет в справочнике")
    title = _text(data, "title", row.title if row else None, 80, "название флага")
    taken = db.scalar(select(UnitFlag.id).where(UnitFlag.title == title))
    if taken is not None and taken != flag_id:
        raise FundConflict(f"флаг «{title}» уже есть")
    if row is None:
        row = UnitFlag()
        db.add(row)
    row.title = title
    row.color = str(data.get("color", row.color or "#3b6fd8"))[:9]
    row.sort_order = _sort_order(data, row.sort_order)
    db.flush()
    return row.id


def archive_flag(db: Session, flag_id: int, archived: bool) -> None:
    lock_module(db)
    row = db.get(UnitFlag, flag_id)
    if row is None:
        raise FundError("флага нет в справочнике")
    row.archived = archived
    db.flush()


def delete_flag(db: Session, flag_id: int) -> None:
    lock_module(db)
    row = db.get(UnitFlag, flag_id)
    if row is None:
        raise FundError("флага нет в справочнике")
    if db.scalar(select(func.count()).select_from(UnitStateFlag).where(UnitStateFlag.flag_id == flag_id)):
        raise FundConflict("флаг используется — отправьте его в архив")
    db.delete(row)
    db.flush()



# ── справочник видов категорий (вне черновика) ─────────────────────────────


def _kind_row(db: Session, kind_id: int) -> CategoryKind:
    row = db.get(CategoryKind, kind_id)
    if row is None:
        raise FundError("вида нет в справочнике")
    return row


def save_kind(db: Session, data: dict, kind_id: int | None) -> int:
    lock_module(db)
    row = _kind_row(db, kind_id) if kind_id is not None else None
    title = _text(data, "title", row.title if row else None, 40, "название вида")
    folded = title.casefold()                     # как в файле: без учёта регистра
    taken = next((k.id for k in db.scalars(select(CategoryKind)) if k.title.casefold() == folded), None)
    if taken is not None and taken != kind_id:
        raise FundConflict(f"вид «{title}» уже есть")
    if row is None:
        row = CategoryKind(archived=False)
        db.add(row)
    row.title = title
    row.sort_order = _sort_order(data, row.sort_order)
    row.expanded = bool(data.get("expanded", row.expanded or False))
    db.flush()
    return row.id


def archive_kind(db: Session, kind_id: int, archived: bool) -> None:
    lock_module(db)
    _kind_row(db, kind_id).archived = archived
    db.flush()


def delete_kind(db: Session, kind_id: int) -> None:
    """Вид, на который ссылается категория хоть одной версии фонда (и черновика), не удаляется — 409."""
    lock_module(db)
    row = _kind_row(db, kind_id)
    if db.scalar(select(func.count()).select_from(CategoryState).where(CategoryState.kind_id == kind_id)):
        raise FundConflict("вид используется — отправьте его в архив")
    db.delete(row)
    db.flush()
