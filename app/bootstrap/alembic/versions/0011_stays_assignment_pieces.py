"""stays: назначения по частям сегментов (спецификация 2026-10-26-stays-fund-versions §5).

Границы версий фонда режут сегмент брони на части; stays_assignments.seg_index становится
индексом части: seg_index * 1000 + n (PIECE_BASE в domain/halfday.py). Существующие строки —
сегменты без границ — становятся первыми частями: seg_index * 1000.

Откат: строки продолжений (seg_index % 1000 != 0) удаляются, первая часть становится сегментом
(seg_index / 1000). Это безопасный вариант: у первой части — объект и закрепление сегмента
на его начало; объект продолжения за границей версии в старой модели некуда записать, а
следующий запуск распределения пересчитает сегмент целиком.
"""
from __future__ import annotations

from alembic import op

revision: str = '0011'
down_revision: str | None = '0010'
branch_labels: str | None = None
depends_on: str | None = None

PIECE_BASE = 1000              # копия константы: ревизия не зависит от кода модуля


def upgrade() -> None:
    # уникальность (reservation_id, seg_index) не нарушается и построчно: сегментов меньше 1000
    op.execute(f"UPDATE stays_assignments SET seg_index = seg_index * {PIECE_BASE}")


def downgrade() -> None:
    op.execute(f"DELETE FROM stays_assignments WHERE seg_index % {PIECE_BASE} <> 0")
    op.execute(f"UPDATE stays_assignments SET seg_index = seg_index / {PIECE_BASE}")   # целочисленно
