"""Блоки — резерв на категорию без привязки к объекту (часть 2 §3.2, §7): сетка «категория × ночь →
остаток», помощник «заполнить» и быстрая правка, список с нехваткой. Ничего не коммитит — commit в
роутере; пересчёт распределения и предпросмотр делает общий run_operation."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..adapters.orm import Block, BlockNight
from . import allocation
from .fund import FundConflict, FundError
from .fund_versions import fund_for
from .views import ViewError

SORTS = ("title", "start", "end", "nights", "placed", "short", "created_at")
MAX_LIMIT = 200
MAX_NIGHTS = 366
MAX_QUANTITY = 500                       # остаток на категорию и ночь
TOP = 3                                  # категорий в строке списка: «VEG до 5, IMP 2»

Grid = dict[int, dict[dt.date, int]]


class BlockInvalid(FundError):
    """Ошибка ввода → 422."""


class BlockNotFound(BlockInvalid):
    """Записи нет → 404."""

    status = 404


class BlockConflict(FundConflict):
    """Блок изменили с момента открытия → 409."""


def _d(v) -> str | None:
    return v.isoformat() if isinstance(v, dt.date) else v


def _nights_of(a: dt.date, b: dt.date):
    d = a
    while d < b:
        yield d
        d += dt.timedelta(days=1)


def grid_of(db: Session, block_id: int) -> Grid:
    out: Grid = {}
    for n in db.scalars(select(BlockNight).where(BlockNight.block_id == block_id).order_by(BlockNight.night)):
        out.setdefault(n.category_id, {})[n.night] = n.quantity
    return out


def grid_json(grid: Grid) -> dict:
    return {str(c): {_d(n): q for n, q in sorted(by.items())} for c, by in sorted(grid.items()) if by}


def block_dict(db: Session, b: Block, grid: Grid | None = None) -> dict:
    return {"id": b.id, "title": b.title, "start": _d(b.start), "end": _d(b.end), "version": b.version,
            "grid": grid_json(grid if grid is not None else grid_of(db, b.id))}


def _check_dates(title: str, start: dt.date, end: dt.date) -> None:
    if not title.strip():
        raise BlockInvalid("Укажите название блока")
    if end <= start:
        raise BlockInvalid("Блок — не короче одной ночи: конец позже начала")
    if (end - start).days > MAX_NIGHTS:
        raise BlockInvalid(f"Блок — не длиннее {MAX_NIGHTS} ночей")


def _check_grid(db: Session, start: dt.date, end: dt.date, grid: Grid) -> None:
    """Ночи — внутри [start, end); категория строки есть в фонде в эту ночь (версия дня)."""
    nights = {n for by in grid.values() for n in by}
    if not nights:
        return
    for by in grid.values():
        for n, q in by.items():
            if not 0 <= q <= MAX_QUANTITY:
                raise BlockInvalid(f"Остаток — от 0 до {MAX_QUANTITY}")
            if not start <= n < end:
                raise BlockInvalid(f"Ночь {n.strftime('%d.%m.%Y')} вне блока {start.strftime('%d.%m')}–"
                                   f"{end.strftime('%d.%m')}")
    fund = fund_for(db, min(nights), max(nights))
    for cid, by in grid.items():
        for n, q in sorted(by.items()):
            if q and (not fund.parts or fund.parts[0][0] > n or cid not in fund.on(n).categories):
                raise BlockInvalid(f"Категории №{cid} нет в фонде на ночь {n.strftime('%d.%m.%Y')}")


def _write(db: Session, b: Block, grid: Grid) -> None:
    db.execute(delete(BlockNight).where(BlockNight.block_id == b.id))
    db.add_all(BlockNight(block_id=b.id, category_id=c, night=n, quantity=q)
               for c, by in grid.items() for n, q in by.items() if q > 0)
    db.flush()


def _get(db: Session, bid: int, version: int | None) -> Block:
    b = db.get(Block, bid)
    if b is None:
        raise BlockNotFound("Блок не найден")
    if version != b.version:
        raise BlockConflict("Блок изменили — обновите")
    return b


def save_block(db: Session, data: dict, bid: int | None, author_id: int | None = None) -> tuple[Block, dict, list]:
    """Создать блок (bid None) или изменить: сетка целиком. grid не передан при правке — прежняя
    сетка, из которой при сужении дат уходят ночи вне нового интервала (третье значение — они)."""
    start, end = data["start"], data["end"]
    _check_dates(data["title"], start, end)
    if bid is None:
        b, before, old = Block(title=data["title"], start=start, end=end, author_id=author_id), {}, {}
        db.add(b)
        db.flush()
    else:
        b = _get(db, bid, data.get("version"))
        old = grid_of(db, bid)
        before = block_dict(db, b, old)
        b.version += 1
    grid: Grid = data["grid"] if data.get("grid") is not None else old
    dropped = []
    if data.get("grid") is None:
        kept: Grid = {}
        for c, by in grid.items():
            for n, q in by.items():
                if start <= n < end:
                    kept.setdefault(c, {})[n] = q
                else:
                    dropped.append({"category_id": c, "night": _d(n), "quantity": q})
        grid = kept
    _check_grid(db, start, end, grid)
    b.title, b.start, b.end = data["title"], start, end
    _write(db, b, grid)
    allocation.run_allocation(db)
    return b, before, dropped


def set_nights(db: Session, bid: int, version: int, category_id: int, first: dt.date, last: dt.date,
               quantity: int) -> tuple[Block, dict]:
    """Помощник «заполнить» и быстрая правка: ночи first..last (включительно) категории получают
    остаток quantity; 0 — убрать ночи."""
    b = _get(db, bid, version)
    if last < first:
        raise BlockInvalid("Последняя ночь раньше первой")
    if quantity < 0 or quantity > MAX_QUANTITY:
        raise BlockInvalid(f"Остаток — от 0 до {MAX_QUANTITY}")
    if not (b.start <= first and last < b.end):          # до построения диапазона ночей
        raise BlockInvalid(f"Ночи вне блока {b.start.strftime('%d.%m')}–{b.end.strftime('%d.%m')}")
    grid = grid_of(db, bid)
    before = block_dict(db, b, grid)
    new = {n: quantity for n in _nights_of(first, last + dt.timedelta(days=1))}
    if quantity:
        _check_grid(db, b.start, b.end, {category_id: new})
    by = grid.setdefault(category_id, {})
    for n, q in new.items():
        if q:
            by[n] = q
        else:
            by.pop(n, None)
    b.version += 1
    _write(db, b, grid)
    allocation.run_allocation(db)
    return b, before


def delete_block(db: Session, bid: int, version: int) -> dict:
    b = _get(db, bid, version)
    before = block_dict(db, b)
    db.execute(delete(BlockNight).where(BlockNight.block_id == bid))
    db.delete(b)
    db.flush()
    allocation.run_allocation(db)
    return before


def shortage(state: allocation.AllocationState, bid: int) -> list[dict]:
    """Нехватка блока: диапазоны ночей, где объектов категории не хватило под слоты."""
    return [{"category_id": w.category_id, "first": dt.date.fromordinal(w.piece_index).isoformat(),
             "last": dt.date.fromordinal(w.last).isoformat(), "missing": w.missing}
            for w in state.warnings if w.kind == "block_short" and w.key == ("b", bid)]


def block_card(db: Session, bid: int) -> dict:
    b = db.get(Block, bid)
    if b is None:
        raise LookupError("Блок не найден")
    grid = grid_of(db, bid)
    short = shortage(allocation.current_state(db), bid)
    return {**_row(b, grid, short, _codes(db, {b.id: grid}, [b])), **block_dict(db, b, grid), "short": short}


@dataclass(frozen=True)
class BlockQuery:
    first: dt.date | None = None
    last: dt.date | None = None
    category_ids: tuple[int, ...] = ()
    short_only: bool = False
    q: str = ""
    sort: str = "start"
    dir: Literal["asc", "desc"] = "asc"
    offset: int = 0
    limit: int = MAX_LIMIT

    def __post_init__(self) -> None:
        if (self.first is None) != (self.last is None):
            raise ViewError("Период задаётся парой first и last")
        if self.first is not None and self.last < self.first:
            raise ViewError("Конец периода раньше начала")
        if self.sort not in SORTS:
            raise ViewError("Неизвестная колонка сортировки")
        if self.dir not in ("asc", "desc"):
            raise ViewError("Направление сортировки — asc или desc")
        if self.offset < 0 or not 1 <= self.limit <= MAX_LIMIT:
            raise ViewError(f"limit — от 1 до {MAX_LIMIT}, offset — не меньше 0")


def _row(b: Block, grid: Grid, short: list[dict], codes: dict[int, str]) -> dict:
    total = sum(q for by in grid.values() for q in by.values())
    missing = sum(s["missing"] * ((dt.date.fromisoformat(s["last"]) - dt.date.fromisoformat(s["first"])).days + 1)
                  for s in short)
    top = sorted(((max(by.values()), cid) for cid, by in grid.items() if by), key=lambda t: (-t[0], codes.get(t[1], "")))
    return {"id": b.id, "title": b.title, "start": _d(b.start), "end": _d(b.end), "nights": (b.end - b.start).days,
            "top": [{"category_id": cid, "code": codes.get(cid, "?"), "max": m} for m, cid in top[:TOP]],
            "placed": total - missing, "missing": missing, "short": missing > 0}


def _codes(db: Session, grids: dict[int, Grid], blocks: list[Block]) -> dict[int, str]:
    """Коды категорий по фонду первой ночи блока, где категория есть (иначе — ближайший снимок)."""
    if not grids:
        return {}
    fund = fund_for(db, min(b.start for b in blocks), max(b.end for b in blocks))
    codes: dict[int, str] = {}
    for b in blocks:
        for cid in grids[b.id]:
            if cid not in codes:
                c = fund.category(cid, b.start)
                if c is not None:
                    codes[cid] = c.code
    return codes


def list_blocks(db: Session, q: BlockQuery) -> dict:
    stmt = select(Block)
    if q.first:
        stmt = stmt.where(Block.start <= q.last, Block.end > q.first)
    blocks = list(db.scalars(stmt))
    if not blocks:
        return {"total": 0, "rows": []}
    grids: dict[int, Grid] = {b.id: {} for b in blocks}
    for n in db.scalars(select(BlockNight).where(BlockNight.block_id.in_([b.id for b in blocks]))):
        grids[n.block_id].setdefault(n.category_id, {})[n.night] = n.quantity
    state = allocation.current_state(db)
    codes = _codes(db, grids, blocks)
    rows = []
    for b in blocks:
        grid = grids[b.id]
        if q.category_ids and not any(c in q.category_ids and any(
                (q.first is None or q.first <= n <= q.last) for n in by) for c, by in grid.items()):
            continue
        if q.q.strip() and q.q.strip().lower() not in b.title.lower():
            continue
        row = _row(b, grid, shortage(state, b.id), codes)
        if q.short_only and not row["short"]:
            continue
        row["created_at"] = b.created_at.isoformat(timespec="minutes")
        rows.append(row)
    rows.sort(key=lambda r: (r["start"], r["title"].lower(), r["id"]))
    rows.sort(key=lambda r: r["title"].lower() if q.sort == "title" else r[q.sort], reverse=q.dir == "desc")
    return {"total": len(rows), "rows": rows[q.offset:q.offset + q.limit]}
