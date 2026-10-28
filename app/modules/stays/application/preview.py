"""Предпросмотр «что будет, если» (§4.6): операция выполняется тем же кодом, картина
снимается до и после, при предпросмотре транзакция запроса откатывается целиком — поэтому
предпросмотр и сохранение не могут разойтись.

Откат всей транзакции, а не SAVEPOINT: pysqlite без особой настройки SAVEPOINT не держит,
а сессия запроса, кроме этой операции, ничего не содержит."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Callable, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import local_date

from ..adapters.orm import Reservation
from ..domain.halfday import PIECE_BASE
from ..ports.duty import DutyPort
from . import allocation
from .context import load_context
from .fund_versions import fund_day, fund_for
from .locking import lock_module

T = TypeVar("T")
# (вид, день, батлер, бронь, текст)
WarningKey = tuple[str, str | None, int | None, int | None, str]


@dataclass(frozen=True)
class Snapshot:
    units: dict[tuple[int, int], int | None]
    warnings: frozenset[WarningKey]
    reservations: frozenset[int]
    coverage: dict[tuple[dt.date, int, int], tuple[int, ...]] = field(default_factory=dict)
    loads: dict[tuple[int, dt.date], float] = field(default_factory=dict)
    names: dict = field(default_factory=dict)          # подписи батлеров и гостей для разницы
    limit: float = 0.0
    spans: dict[tuple[int, int], tuple[int, int]] = field(default_factory=dict)   # часть → (start_pos, end_pos)


Window = tuple[dt.date, dt.date]


def take_snapshot(db: Session, window: Window | None = None, duty: DutyPort | None = None) -> Snapshot:
    """Размещение и предупреждения распределения; с окном — ещё покрытие, нагрузка и
    предупреждения покрытия по дням окна (§4.6 «дельта покрытия»)."""
    db.flush()
    state = allocation.current_state(db)
    warns = set()
    for w in state.warnings:
        for rid in state.members[w.key] or [None]:         # предупреждение блока — без брони
            warns.add((w.kind, None, None, rid, w.text))
    snap = Snapshot(dict(state.units), frozenset(warns), frozenset(db.scalars(select(Reservation.id))),
                    spans=dict(state.spans))
    if window is None:
        return snap
    ctx = load_context(db, window[0], window[1], duty)
    coverage, loads = {}, {}
    for d in ctx.days():
        coverage.update({(d, rid, g): emps for (rid, g), emps in ctx.cover(d).by_guest.items()})
        loads.update({(e, d): round(v, 2) for e, v in ctx.loads(d).items()})
        warns |= {(w.kind, d.isoformat(), w.employee_id, w.reservation_id, ctx.warning_text(w))
                  for w in ctx.warnings(d)}
    names = {("e", e): n for e, n in ctx.staff.items()} | {("g", g): ctx.guest_name(g) for g in ctx.guests}
    return Snapshot(snap.units, frozenset(warns), snap.reservations, coverage, loads, names, ctx.limit, snap.spans)


def _warning(k: WarningKey, known: frozenset[int]) -> dict:
    kind, day, employee_id, rid, text = k
    return {"kind": kind, "day": day, "employee_id": employee_id,
            "reservation_id": rid if rid in known else None, "new": rid is not None and rid not in known,
            "text": text}


def _changed_pieces(before: Snapshot, after: Snapshot) -> list[tuple[tuple[int, int], int | None, int | None, int]]:
    """Части, у которых сменился объект: (ключ, был, стал, start_pos части).

    Индекс части зависит от границ версий фонда: публикация с даты D добавляет границу, и
    часть «после» с тем же индексом — уже другой отрезок сегмента. Поэтому каждая часть «после»
    сравнивается с частями «до» той же брони и сегмента, которые она покрывает; строка — только
    если объект действительно сменился. Часть «до», которую не покрывает ни одна часть «после»
    (бронь удалена, сегмент сократился), с объектом — «объект → без объекта»."""
    def by_seg(snap: Snapshot) -> dict[tuple[int, int], list[tuple[int, int, int | None, tuple[int, int]]]]:
        out: dict = {}
        for key, uid in snap.units.items():
            span = snap.spans.get(key)
            if span is None:
                continue
            out.setdefault((key[0], key[1] // PIECE_BASE), []).append((span[0], span[1], uid, key))
        return out

    was_by, now_by = by_seg(before), by_seg(after)
    out = []
    covered: set[tuple[int, int]] = set()
    for seg, now_pieces in now_by.items():
        old = sorted(was_by.get(seg, []))
        for a, z, now, key in sorted(now_pieces):
            over = [o for o in old if o[0] <= z and a <= o[1]]
            covered.update(o[3] for o in over)
            if not over:
                if now is not None:
                    out.append((key, None, now, a))
                continue
            moved = next((o for o in over if o[2] != now), None)
            if moved is not None:
                out.append((key, moved[2], now, max(a, moved[0])))
    for old in was_by.values():
        for a, _z, was, key in old:
            if key not in covered and was is not None:
                out.append((key, was, None, a))
    return sorted(out, key=lambda x: (x[0][0], x[3]))


def diff(db: Session, before: Snapshot, after: Snapshot) -> dict:
    numbers = dict(db.execute(select(Reservation.id, Reservation.number)).all())
    changed = _changed_pieces(before, after)
    # обозначения объектов — по фонду начала изменившегося отрезка (версия действует с вечера даты)
    starts = {i: dt.date.fromordinal(start // 2) for i, (_k, _w, _n, start) in enumerate(changed)}
    fund_days = {i: fund_day(start) for i, (_k, _w, _n, start) in enumerate(changed)}
    dates = list(fund_days.values()) or [local_date()]
    fund = fund_for(db, min(dates), max(dates)) if changed else None

    def label(uid: int | None, day: dt.date) -> str | None:
        u = fund.unit(uid, day) if fund is not None and uid is not None else None
        return u.label if u is not None else None

    seg_starts: dict[tuple[int, int], int] = {}          # (бронь, сегмент) → начало сегмента
    for k, (a, _z) in (before.spans | after.spans).items():
        seg = (k[0], k[1] // PIECE_BASE)
        seg_starts[seg] = min(a, seg_starts.get(seg, a))
    moved = []
    for i, (key, was, now, start) in enumerate(changed):
        # у новой брони id при предпросмотре и сохранении разные (последовательность PG
        # не откатывается) — она помечается «новая», без id
        new = key[0] not in before.reservations
        seg_start = seg_starts.get((key[0], key[1] // PIECE_BASE), start)
        moved.append({"reservation_id": None if new else key[0], "new": new,
                      "number": numbers.get(key[0], ""), "seg_index": key[1] // PIECE_BASE,
                      "since": starts[i].isoformat() if start > seg_start else None,
                      "from_unit": was, "to_unit": now,
                      "from_label": label(was, fund_days[i]), "to_label": label(now, fund_days[i])})
    return {"moved": moved,
            "warnings_added": [_warning(k, before.reservations) for k in
                               sorted(after.warnings - before.warnings, key=lambda k: repr(k[:3] + k[4:]))],
            "warnings_removed": [_warning(k, before.reservations) for k in sorted(before.warnings - after.warnings, key=repr)],
            "coverage_changes": _coverage_changes(before, after),
            "load_changes": [{"employee_id": e, "employee": after.names.get(("e", e)) or before.names.get(("e", e), ""),
                              "day": d.isoformat(), "before": before.loads.get((e, d), 0.0),
                              "after": after.loads.get((e, d), 0.0), "limit": after.limit or before.limit}
                             for e, d in sorted(set(before.loads) | set(after.loads), key=lambda k: (k[1], k[0]))
                             if before.loads.get((e, d), 0.0) != after.loads.get((e, d), 0.0)]}


def _coverage_changes(before: Snapshot, after: Snapshot) -> list[dict]:
    """Кто из батлеров по дням теряет и получает каких гостей."""
    acc: dict[tuple[dt.date, int], dict[str, list]] = {}
    for key in set(before.coverage) | set(after.coverage):
        d, _rid, g = key
        was, now = set(before.coverage.get(key, ())), set(after.coverage.get(key, ()))
        for e in now - was:
            acc.setdefault((d, e), {"gained": [], "lost": []})["gained"].append(g)
        for e in was - now:
            acc.setdefault((d, e), {"gained": [], "lost": []})["lost"].append(g)
    names = before.names | after.names
    return [{"day": d.isoformat(), "employee_id": e, "employee": names.get(("e", e), ""),
             "gained": sorted(names.get(("g", g), "гость брони") for g in v["gained"]),
             "lost": sorted(names.get(("g", g), "гость брони") for g in v["lost"])}
            for (d, e), v in sorted(acc.items(), key=lambda x: (x[0][0], x[0][1]))]


def run_operation(db: Session, op: Callable[[], T], window: Window | None = None,
                  duty: DutyPort | None = None) -> tuple[T, dict]:
    """Выполнить op и снять разницу. op пишет и журнал аудита, и возвращает уже
    сериализованный результат: после отката ORM-объекты просрочены. Фиксирует или
    откатывает транзакцию обработчик (commit — только в обработчиках)."""
    lock_module(db)                              # до первого чтения состояния (ревью этапа 2, I1)
    db.info.pop(allocation.CACHE_KEY, None)
    before = take_snapshot(db, window, duty)
    result = op()
    return result, diff(db, before, take_snapshot(db, window, duty))
