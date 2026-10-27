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
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete, func, insert, literal, select, update
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.time import local_date, now_local

from ..adapters.orm import (
    Category,
    CategoryState,
    FundGroup,
    FundVersion,
    GroupState,
    Unit,
    UnitFlag,
    UnitLineage,
    UnitState,
    UnitStateFlag,
)
from . import allocation as _allocation
from .fund import KINDS, FundConflict, FundError
from .fund_versions import FundSnapshot, snapshot_of
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
        (CategoryState, ("category_id", "code", "title", "kind", "weight", "escorted", "sort_order")),
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
        raise FundError("черновика фонда нет — откройте его")
    check_rev(draft, rev)
    return draft


def move_draft_date(db: Session, rev: int, valid_from: dt.date) -> None:
    draft = _draft(db, rev)
    if valid_from < local_date():
        raise FundError("дата версии не может быть в прошлом")
    if _published_on(db, valid_from) is not None:
        raise FundConflict("на эту дату уже есть версия — удалите черновик и откройте новый на эту дату")
    draft.valid_from = valid_from
    bump(draft)
    db.flush()


# ── вспомогательное ────────────────────────────────────────────────────────


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


def save_category(db: Session, rev: int, data: dict, category_id: int | None) -> int:
    draft = _draft(db, rev)
    row = _cat(db, draft.id, category_id) if category_id is not None else None
    code = _text(data, "code", row.code if row else None, 16, "код категории")
    title = _text(data, "title", row.title if row else None, 120, "название категории")
    kind = data.get("kind", row.kind if row else "room")
    if kind not in KINDS:
        raise FundError("вид категории: " + ", ".join(KINDS))
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
    row.code, row.title, row.kind, row.weight = code, title, kind, weight
    row.escorted = bool(data.get("escorted", row.escorted if row.escorted is not None else False))
    row.sort_order = int(data.get("sort_order", row.sort_order if row.sort_order is not None else 100))
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
    row.sort_order = int(data.get("sort_order", row.sort_order if row.sort_order is not None else 100))
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
    if len(set(unit_ids)) < 2:
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
    for u in unit_ids:
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
        return {"code": c.code, "title": c.title, "kind": c.kind, "weight": c.weight,
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


# ── публикация и удаление ──────────────────────────────────────────────────


def publish(db: Session, principal) -> FundVersion:
    lock_module(db)
    draft = current_draft(db)
    if draft is None:
        raise FundError("черновика фонда нет")
    day = draft.valid_from
    if day < local_date():
        raise FundConflict("дата черновика прошла — сдвиньте на сегодня или позже")
    change = asdict(diff(db, draft.base_version_id, draft.id)) if draft.base_version_id else {}
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
    db.flush()
    _allocation.run_allocation(db)
    audit(db, principal, "stays_fund_version", f"fund_version:{version.id}",
          {"valid_from": day.isoformat(), "diff": change})
    return version


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
    row.sort_order = int(data.get("sort_order", row.sort_order if row.sort_order is not None else 100))
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

