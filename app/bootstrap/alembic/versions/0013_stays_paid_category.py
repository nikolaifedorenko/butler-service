"""stays: «Оплата за» — категория, «Повод визита» удалён (спецификация 2026-10-28-stays-part1-addendum §5).

Бронь вместо свободного текста paid_by получает ссылку paid_category_id на постоянную категорию
(пусто — оплата за категорию самой брони); текстовый purpose удаляется. Переноса данных нет
(боевой базы нет): прежний текст не сопоставить с категориями.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = '0013'
down_revision: str | None = '0012'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table('stays_reservations') as batch_op:
        batch_op.add_column(sa.Column('paid_category_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_stays_reservations_paid_category', 'stays_categories',
                                    ['paid_category_id'], ['id'])
        batch_op.drop_column('paid_by')
        batch_op.drop_column('purpose')


def downgrade() -> None:
    with op.batch_alter_table('stays_reservations') as batch_op:
        batch_op.add_column(sa.Column('paid_by', sa.String(length=120), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('purpose', sa.String(length=160), nullable=False, server_default=''))
    with op.batch_alter_table('stays_reservations') as batch_op:
        batch_op.drop_constraint('fk_stays_reservations_paid_category', type_='foreignkey')
        batch_op.drop_column('paid_category_id')
        batch_op.alter_column('paid_by', server_default=None)
        batch_op.alter_column('purpose', server_default=None)
