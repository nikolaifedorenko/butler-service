"""stays: начало части назначения (stays_assignments.start_pos).

Заселённый гость, у которого OOO отнимает объект с ночи D, переезжает с D — посреди части фонда.
Позиция начала части хранится в строке: читатели режут сегменты по границам версий и по этим
позициям, поэтому переезд виден везде одинаково. Переноса данных нет: пусто — граница версии.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = '0016'
down_revision: str | None = '0015'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table('stays_assignments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('start_pos', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('stays_assignments', schema=None) as batch_op:
        batch_op.drop_column('start_pos')
