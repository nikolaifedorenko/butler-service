"""pair_marks — чистое ядро сопряжения (4.3, v7/R31, R32): «пришёл» открывает сессию,
«ушёл» закрывает, в исходном порядке; без настроек и состояния.

Граничные отметки: opening_mark = «пришёл» начинает первую сессию; opening_mark = «ушёл»
игнорируется; незакрытый «пришёл» — открытая сессия (end = None), обрезается по горизонту
либо закрывается closing_mark типа «ушёл»; closing_mark = «пришёл» игнорируется.
Пустая выборка допустима. Починка последовательности запрещена."""
from __future__ import annotations

import datetime as dt
from typing import Sequence

from ..types.entities import CalcMark, Mark, Session
from ._marks import is_in, moment_of
from .check_punch_sequence import check_punch_sequence


def _clipped(session: Session, horizon: dt.datetime | None) -> Session | None:
    if horizon is None:
        return session
    end = horizon if session.end is None else min(session.end, horizon)
    return None if session.start >= end else Session(session.start, end)


def _closed(start: dt.datetime, closing_mark) -> Session:
    end = moment_of(closing_mark) if closing_mark is not None and not is_in(closing_mark) else None
    return Session(start, end)


def pair_marks(marks: Sequence[Mark | CalcMark], opening_mark: Mark | CalcMark | None = None,
               closing_mark: Mark | CalcMark | None = None,
               horizon: dt.datetime | None = None) -> tuple[Session, ...]:
    check_punch_sequence(marks, opening_mark)
    sessions: list[Session] = []
    start = moment_of(opening_mark) if opening_mark is not None and is_in(opening_mark) else None
    for mark in marks:
        if is_in(mark):
            start = moment_of(mark)
        elif start is not None:
            sessions.append(Session(start, moment_of(mark)))
            start = None
    if start is not None:
        sessions.append(_closed(start, closing_mark))
    return tuple(s for s in (_clipped(sess, horizon) for sess in sessions) if s is not None)
