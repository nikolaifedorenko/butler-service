"""stays: начало части назначения и объект закрепления без объекта (stays_assignments).

start_pos — начало части (позиция половинки). Заселённый гость, у которого OOO отнимает объект с
ночи D, переезжает с D — посреди части фонда; распределение пишет start_pos каждой строки, а
читатели режут сегменты по границам версий и по этим позициям, поэтому переезд виден везде
одинаково. pin_unit_id — объект закрепления у закреплённой части, оставшейся без объекта
(овербукинг под OOO): закрепление сохраняется и вернёт бронь, когда объект освободится (§4.4).
Переноса данных нет.
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
        batch_op.add_column(sa.Column('pin_unit_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_stays_assignments_pin_unit', 'stays_units', ['pin_unit_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('stays_assignments', schema=None) as batch_op:
        batch_op.drop_constraint('fk_stays_assignments_pin_unit', type_='foreignkey')
        batch_op.drop_column('pin_unit_id')
        batch_op.drop_column('start_pos')
