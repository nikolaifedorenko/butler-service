"""Автораспределение по объектам (PoC SPEC §6.3, спецификация §4.1; часть 2 — OOO и блоки §4.2–§4.4).

Чистая функция: данные готовые, БД не видит. Порядок (часть 2 §4.2):

1. OOO — занимает объект безусловно.
2. Заморожено: `AllocItem.fixed` (прошлые части, L1) и части заселённой брони (`in_house`) после
   замороженной, пока её объект подходит по фонду и не занят OOO — блок их не трогает. Заселённая,
   у которой OOO или фонд отняли объект, переезжает здесь же, до слотов: блок не оставляет
   живущего гостя без объекта (закрепление переносится, как в шаге 4).
3. Слоты блоков — по ночам: слот держит объект прошлой ночи, если он свободен, иначе первый
   свободный (обходя объекты, закреплённые за бронями, и обороты HK); не хватило — `block_short`,
   блок не уменьшается.
4. Закрепления броней — если объект свободен на весь остаток сегмента; иначе `pin_conflict` и
   бронь распределяется как обычная (закрепление переносится на новый объект, §4.4).
5. Брони rank 0 (подтверждённые, заселённые), затем rank 1 (предварительные); внутри — раньше
   заезд, длиннее, номер.

Без пинг-понга (§4.3): незаселённая бронь ставится целиком в объект, свободный на весь её кусок
фонда (часть `Piece`; следующая часть сегмента остаётся в том же объекте, если он подходит и
свободен — часть 1, «с границы D — другой объект»); нет свободного — овербукинг `overbooked`,
лоскутов из разных объектов внутри части нет. Заселённая бронь, объект которой отнят с части D
(OOO или фонд), один раз переезжает в объект, свободный с D до конца сегмента; нет — овербукинг
с D (если один объект не покрывает остаток по фонду — самыми длинными кусками, которые покрывает).

Выбор объекта при равных возможностях: закрепление → непрерывность (объект предыдущей части
сегмента; после переезда — другой объект ближе по дереву фонда) → пожелания (`prefs`, больше —
лучше) → HK (не в объект с выездом в этот день, если есть свободный со вчера) → порядок.

Границы версий фонда (спецификация версий §5): объект задан интервалами `UnitSpan`, сегменты
брони приходят частями `Piece`, разрезанными на границах. Объект подходит части, если его
интервал нужной категории покрывает её целиком.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

from .blocks import SlotRef
from .candidates import common_prefix
from .halfday import PIECE_BASE, Piece, overlaps

Key = tuple[str, int]                  # ("r", reservation_id) | ("g", group_id) | ("b", block_id)
SlotKey = tuple[int, int, int, int]    # (блок, категория, слот, ordinal ночи)


@dataclass(frozen=True)
class UnitSpan:
    unit_id: int
    category_id: int
    cat_sort: int
    label: str
    group_path: tuple[int, ...]        # узел дерева фонда от корня; () — без узла
    start_pos: int
    end_pos: int


@dataclass(frozen=True)
class OooRef:
    unit_id: int
    start_pos: int
    end_pos: int
    title: str


@dataclass(frozen=True)
class AllocItem:
    key: Key
    number: str
    segments: tuple[Piece, ...]                                  # части по порядку
    pinned: Mapping[int, int] = field(default_factory=dict)     # seg_index → unit_id
    # замороженные части (прошлое, заселённые): Piece.index → объект или None — не распределяются,
    # но занимают объект и служат «предыдущей частью» для продолжения сегмента
    fixed: Mapping[int, int | None] = field(default_factory=dict)
    rank: int = 0                      # 0 — подтверждённая/заселённая, 1 — предварительная
    in_house: bool = False             # незамороженные части держат объект замороженной (шаг 2)
    prefs: Callable[[UnitSpan], int] | None = None              # счёт выполненных пожеланий


@dataclass(frozen=True)
class AllocWarning:
    # overbooked | block_short | pin_invalid | pin_conflict | category_missing | hold_absent | unit_invalid
    kind: str
    key: Key
    piece_index: int                   # у block_short — ordinal первой ночи
    text: str


def natural_key(s: str) -> tuple:
    """«402» < «4003» < «4010»; «B-2» < «B-10»; чисто числовые — раньше буквенных."""
    return tuple((0, int(t), "") if t.isdigit() else (1, 0, t.lower())
                 for t in re.split(r"(\d+)", s) if t)


def _nearness(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    """Тот же узел (и оба без узла) — ближе всего; иначе длина общего префикса пути."""
    return len(a) + 1 if a == b else common_prefix(a, b)


def _since(p: Piece) -> str:
    return f" с {p.start.strftime('%d.%m')}" if p.index % PIECE_BASE else ""


def pin_invalid(number: str, key: Key, p: Piece) -> AllocWarning:
    """Закреплённый объект не подходит части — она распределяется автоматически."""
    return AllocWarning("pin_invalid", key, p.index, f"Бронь {number}: закреплённый объект не подходит{_since(p)} — "
                                                     f"сегмент {p.seg_index + 1} распределяется автоматически")


def _nights(first: int, last: int) -> str:
    """Ночи first..last (ordinal): «12.11», «10–12.11», «30.10–02.11»."""
    a, z = dt.date.fromordinal(first), dt.date.fromordinal(last)
    if a == z:
        return z.strftime("%d.%m")
    return f"{a.strftime('%d' if (a.year, a.month) == (z.year, z.month) else '%d.%m')}–{z.strftime('%d.%m')}"


def _order(it: AllocItem, run: Sequence[Piece]) -> tuple:
    return (it.rank, run[0].start_pos, -(run[-1].end_pos - run[0].start_pos), natural_key(it.number), it.key,
            run[0].index)


def allocate(spans: Sequence[UnitSpan], ooo: Sequence[OooRef], slots: Sequence[SlotRef],
             items: Sequence[AllocItem], category_codes: Mapping[int, str],
             turnover: Mapping[tuple[int, int], bool]
             ) -> tuple[dict[tuple[Key, int], int | None], dict[SlotKey, int | None], list[AllocWarning]]:
    """Назначения броней по индексу части (`Piece.index`), назначения слотов по ночам и
    предупреждения. `turnover[(объект, ordinal дня)]` — в этот день в объекте выезд (вне расчёта);
    выезды распределённых здесь броней и слотов учитываются сами."""
    ordered = sorted(spans, key=lambda u: (u.cat_sort, natural_key(u.label), u.unit_id, u.start_pos))
    by_cat: dict[int, list[UnitSpan]] = {}
    of_unit: dict[int, list[UnitSpan]] = {}
    for u in ordered:
        by_cat.setdefault(u.category_id, []).append(u)
        of_unit.setdefault(u.unit_id, []).append(u)
    busy: dict[int, list[tuple[int, int, str]]] = {uid: [] for uid in of_unit}
    leaves: set[tuple[int, int]] = set()          # (объект, pos) — конец занятости гостем или слотом
    for o in ooo:
        if o.unit_id in busy:
            busy[o.unit_id].append((o.start_pos, o.end_pos, o.title))

    def occupy(uid: int, a: int, z: int, desc: str) -> None:
        busy.setdefault(uid, []).append((a, z, desc))
        leaves.add((uid, z))

    def free(uid: int, a: int, z: int) -> bool:
        return not any(overlaps(a, z, bs, be) for bs, be, _ in busy.get(uid, ()))

    def covering(cat: int, a: int, z: int) -> list[UnitSpan]:
        """Интервалы категории, покрывающие [a, z] целиком — по одному на объект, по порядку."""
        return [u for u in by_cat.get(cat, ()) if u.start_pos <= a and z <= u.end_pos]

    def fit(uid: int, p: Piece) -> UnitSpan | None:
        return next((u for u in of_unit.get(uid, ()) if u.category_id == p.category_id
                     and u.start_pos <= p.start_pos and p.end_pos <= u.end_pos), None)

    def hk(cands: list[UnitSpan], a: int) -> list[UnitSpan]:
        """Меньше оборотов: не в объект с выездом в день заезда, если есть свободный со вчера."""
        day = a // 2
        morning = day * 2
        calm = [u for u in cands if not turnover.get((u.unit_id, day)) and (u.unit_id, morning) not in leaves]
        return calm if any(free(u.unit_id, morning - 1, morning) for u in calm) else cands

    result: dict[tuple[Key, int], int | None] = {}
    paths: dict[tuple[Key, int], tuple[int, ...]] = {}      # путь узла объекта на этой части
    warnings: list[AllocWarning] = []
    prev_of = {(it.key, p.index): prev for it in items for prev, p in zip(it.segments, it.segments[1:], strict=False)}

    def place(it: AllocItem, p: Piece, u: UnitSpan) -> None:
        occupy(u.unit_id, p.start_pos, p.end_pos, f"бронь {it.number}")
        result[(it.key, p.index)] = u.unit_id
        paths[(it.key, p.index)] = u.group_path

    def runs(it: AllocItem, keep=None) -> list[list[Piece]]:
        """Незамороженные части по сегментам — подряд идущими цепочками (keep — фильтр частей)."""
        out: list[list[Piece]] = []
        prev: Piece | None = None
        for p in it.segments:
            if p.index in it.fixed or (keep is not None and p.index not in keep):
                prev = None
                continue
            if prev is not None and prev.seg_index == p.seg_index:
                out[-1].append(p)
            else:
                out.append([p])
            prev = p
        return out

    by_number = sorted(items, key=lambda i: (natural_key(i.number), i.key))
    # 2. заморожено: прошлые части и части заселённых, пока их объект не отнят OOO или фондом
    for it in by_number:
        for p in it.segments:
            if p.index in it.fixed:
                if (uid := it.fixed[p.index]) is not None:
                    occupy(uid, p.start_pos, p.end_pos, f"бронь {it.number}")
                    paths[(it.key, p.index)] = next((u.group_path for u in of_unit.get(uid, ())
                                                     if u.start_pos <= p.start_pos <= u.end_pos), ())
                result[(it.key, p.index)] = uid

    def hold(it: AllocItem, run: list[Piece]) -> tuple[int, int | None]:
        """Начатый сегмент держит объект предыдущей части, пока тот подходит и свободен:
        (сколько частей удержано, удерживаемый объект или None — удерживать нечего)."""
        prev = prev_of.get((it.key, run[0].index))
        held = result.get((it.key, prev.index)) if prev is not None and prev.seg_index == run[0].seg_index else None
        n = 0
        while held is not None and n < len(run):
            unit = fit(held, run[n])
            if unit is None or not free(held, run[n].start_pos, run[n].end_pos):
                break
            place(it, run[n], unit)
            n += 1
        return n, held

    def runs_after_pin(it: AllocItem, run: list[Piece], uid: int) -> list[list[Piece]]:
        """Закрепление (шаг 4): объект свободен на всю цепочку — бронь в нём; части, которым он не
        подходит по фонду, — pin_invalid. Объект занят — pin_conflict: бронь распределяется как
        обычная, и закрепление переходит на новый объект (§4.4). Возвращает цепочки для обычного
        распределения."""
        ok = {p.index: unit for p in run if (unit := fit(uid, p)) is not None}
        warnings.extend(pin_invalid(it.number, it.key, p) for p in run if p.index not in ok)
        clash = next((desc for p in run if p.index in ok for bs, be, desc in busy.get(uid, ())
                      if overlaps(p.start_pos, p.end_pos, bs, be)), None)
        if clash is None:
            for p in run:
                if p.index in ok:
                    place(it, p, ok[p.index])
            return runs(it, {p.index for p in run if p.index not in ok})
        first = next(p for p in run if p.index in ok)
        warnings.append(AllocWarning(
            "pin_conflict", it.key, first.index,
            f"Бронь {it.number}: закреплённый объект {ok[first.index].label} занят «{clash}» — "
            f"бронь перенесена вместе с закреплением"))
        return [run]

    open_runs: list[tuple[AllocItem, list[Piece]]] = []
    displaced: list[tuple[AllocItem, list[Piece]]] = []
    for it in by_number:
        for run in runs(it):
            # у заселённой — остаток с части, где объект отнят: один переезд до конца сегмента
            n, held = hold(it, run) if it.in_house else (0, None)
            if n < len(run):
                (displaced if held is not None else open_runs).append((it, run[n:]))

    def choose(it: AllocItem, chunk: list[Piece], cands: list[UnitSpan]) -> UnitSpan:
        p0 = chunk[0]
        prev = prev_of.get((it.key, p0.index))
        prev_uid = result.get((it.key, prev.index)) if prev is not None else None
        same_seg = prev is not None and prev.seg_index == p0.seg_index
        for want in (it.pinned.get(p0.seg_index), prev_uid if same_seg else None):
            if (hit := next((u for u in cands if u.unit_id == want), None)) is not None:
                return hit
        if prev is not None and prev_uid is not None and not same_seg and len(cands) > 1:
            # переезд: другой объект, по возможности в том же узле, иначе ближе по дереву (PoC §14.4)
            others = [u for u in cands if u.unit_id != prev_uid] or cands
            prev_path = paths.get((it.key, prev.index), ())
            near = {u.unit_id: _nearness(u.group_path, prev_path) for u in others}
            best = max(near.values())
            cands = [u for u in others if near[u.unit_id] == best] if best else others
        if it.prefs is not None:
            score = {u.unit_id: it.prefs(u) for u in cands}
            top = max(score.values())
            cands = [u for u in cands if score[u.unit_id] == top]
        return hk(cands, p0.start_pos)[0]

    def unplaced(it: AllocItem, p: Piece) -> None:
        result[(it.key, p.index)] = None
        code = category_codes.get(p.category_id, "?")
        if not any(overlaps(u.start_pos, u.end_pos, p.start_pos, p.end_pos) for u in by_cat.get(p.category_id, ())):
            warnings.append(AllocWarning("category_missing", it.key, p.index,
                                         f"Бронь {it.number}: категории {code} нет в фонде "
                                         f"с {p.start.strftime('%d.%m')}"))
        else:
            warnings.append(AllocWarning("overbooked", it.key, p.index,
                                         f"Бронь {it.number}: нет свободных объектов категории {code} на "
                                         f"{p.start.strftime('%d.%m')}–{p.end.strftime('%d.%m')}"))

    def place_run(it: AllocItem, run: list[Piece]) -> None:
        """Цепочка частей сегмента — кусками, каждый целиком в один объект или овербукинг: у
        незаселённой кусок — часть фонда, у переезда заселённой — весь остаток, который покрывает
        один объект."""
        i = 0
        while i < len(run):
            first = run[i]
            reach: dict[int, int] = {}
            for u in covering(first.category_id, first.start_pos, first.end_pos):
                j = i + 1
                while it.in_house and j < len(run) and fit(u.unit_id, run[j]) is not None:
                    j += 1
                reach[u.unit_id] = j
            end = max(reach.values(), default=i)
            if end == i:
                unplaced(it, first)
                i += 1
                continue
            chunk = run[i:end]
            cands = [u for u in covering(first.category_id, first.start_pos, first.end_pos)
                     if reach[u.unit_id] == end and all(free(u.unit_id, p.start_pos, p.end_pos) for p in chunk)]
            if cands:
                uid = choose(it, chunk, cands).unit_id
                for p in chunk:
                    place(it, p, fit(uid, p))
            else:
                for p in chunk:
                    unplaced(it, p)
            i = end

    # 2б. заселённые, у которых OOO или фонд отняли объект, переезжают до слотов блоков: блок
    # не оставляет живущего гостя без объекта (решение владельца «блок заселённого не трогает»)
    for it, run in sorted(displaced, key=lambda t: _order(t[0], t[1])):
        uid = it.pinned.get(run[0].seg_index)
        for rest in (runs_after_pin(it, run, uid) if uid is not None else [run]):
            place_run(it, rest)

    # 3. слоты блоков — по ночам
    pinned_at: dict[int, list[tuple[int, int]]] = {}
    for it, run in open_runs:
        if (uid := it.pinned.get(run[0].seg_index)) is not None:
            pinned_at.setdefault(uid, []).append((run[0].start_pos, run[-1].end_pos))
    slot_units: dict[SlotKey, int | None] = {}
    by_night: dict[int, list[SlotRef]] = {}
    for s in slots:
        for n in range(s.start_pos // 2, s.end_pos // 2):
            by_night.setdefault(n, []).append(s)
    missing: dict[tuple[int, int], dict[int, int]] = {}
    titles: dict[int, str] = {}
    for n in sorted(by_night):
        a, z = 2 * n + 1, 2 * n + 2            # pos(n, PM)..pos(n+1, AM)
        fresh = []
        for s in sorted(by_night[n], key=lambda s: (s.block_id, s.category_id, s.slot)):
            uid = slot_units.get((s.block_id, s.category_id, s.slot, n - 1))
            if uid is not None and any(u.unit_id == uid for u in covering(s.category_id, a, z)) and free(uid, a, z):
                occupy(uid, a, z, f"блок {s.title}")
                slot_units[(s.block_id, s.category_id, s.slot, n)] = uid
            else:
                fresh.append(s)
        for s in fresh:
            cands = [u for u in covering(s.category_id, a, z) if free(u.unit_id, a, z)]
            spare = [u for u in cands if not any(overlaps(a, z, pa, pz) for pa, pz in pinned_at.get(u.unit_id, ()))]
            cands = hk(spare or cands, a)
            key = (s.block_id, s.category_id, s.slot, n)
            if cands:
                occupy(cands[0].unit_id, a, z, f"блок {s.title}")
                slot_units[key] = cands[0].unit_id
            else:
                slot_units[key] = None
                per_night = missing.setdefault((s.block_id, s.category_id), {})
                per_night[n] = per_night.get(n, 0) + 1
                titles[s.block_id] = s.title
    for (block_id, cat), per_night in sorted(missing.items()):
        nights = sorted(per_night)
        start = 0
        for i, n in enumerate(nights):
            if i + 1 < len(nights) and nights[i + 1] == n + 1 and per_night[nights[i + 1]] == per_night[n]:
                continue
            first = nights[start]
            warnings.append(AllocWarning(
                "block_short", ("b", block_id), first,
                f"Блок {titles[block_id]}: не хватает {per_night[n]} {category_codes.get(cat, '?')} на "
                f"{_nights(first, n)}"))
            start = i + 1

    # 4. закрепления броней — если объект свободен на весь остаток сегмента
    todo: list[tuple[AllocItem, list[Piece]]] = []
    pinned_runs = []
    for it, run in open_runs:
        if (uid := it.pinned.get(run[0].seg_index)) is None:
            todo.append((it, run))
        else:
            pinned_runs.append((it, run, uid))
    for it, run, uid in sorted(pinned_runs, key=lambda t: _order(t[0], t[1])):
        todo += [(it, r) for r in runs_after_pin(it, run, uid)]

    # 5. брони: rank 0, затем rank 1
    for it, run in sorted(todo, key=lambda t: _order(t[0], t[1])):
        place_run(it, run)
    return result, slot_units, warnings
