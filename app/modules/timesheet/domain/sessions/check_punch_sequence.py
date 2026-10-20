"""CHK-PUNCH-SEQUENCE (5.3, уровень 2; v7/R31): линейная проверка чередования
«пришёл»/«ушёл» в последовательности opening_mark ++ marks. Выполняется ядром
pair_marks, а не стадией 1. Починка последовательности запрещена (12.22)."""
from __future__ import annotations

from typing import Sequence

from ..types.entities import CalcMark, Mark
from ..types.errors import InvalidInputDataError
from ._marks import is_in, kind_of, moment_of

CHK_PUNCH_SEQUENCE = "CHK-PUNCH-SEQUENCE"


def _violation(index: int, mark, previous) -> InvalidInputDataError:
    return InvalidInputDataError(CHK_PUNCH_SEQUENCE, {
        "index": index, "at": moment_of(mark), "kind": kind_of(mark),
        "previous_at": None if previous is None else moment_of(previous)})


def check_punch_sequence(marks: Sequence[Mark | CalcMark],
                         opening_mark: Mark | CalcMark | None = None) -> None:
    """«пришёл» при открытой сессии и «ушёл» вне открытой сессии недопустимы;
    единственный «ушёл», не являющийся нарушением, — opening_mark (игнорируется, R32)."""
    session_open = opening_mark is not None and is_in(opening_mark)
    previous = opening_mark
    for index, mark in enumerate(marks):
        if is_in(mark) == session_open:
            raise _violation(index, mark, previous)
        session_open = is_in(mark)
        previous = mark
