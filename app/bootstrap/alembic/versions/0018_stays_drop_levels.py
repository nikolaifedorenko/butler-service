"""stays: убраны уровни VIP/VVIP, отказ от батлера и надбавки (спецификация 2026-10-27-stays-escort-rules-design).

Снимает колонки, которые заменила ревизия 0017: stays_guests.level, stays_reservations.declined_butler,
stays_settings.vip_bonus и vvip_bonus. Откат возвращает их с прежними значениями по умолчанию
(level 'regular', declined_butler false, vip_bonus 1, vvip_bonus 2) и восстанавливает по новым полям:
special → level 'vip', escort_mode 'declined' → declined_butler.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = '0018'
down_revision: str | None = '0017'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table('stays_guests') as batch_op:
        batch_op.drop_column('level')
    with op.batch_alter_table('stays_reservations') as batch_op:
        batch_op.drop_column('declined_butler')
    with op.batch_alter_table('stays_settings') as batch_op:
        batch_op.drop_column('vip_bonus')
        batch_op.drop_column('vvip_bonus')


def downgrade() -> None:
    with op.batch_alter_table('stays_guests') as batch_op:
        batch_op.add_column(sa.Column('level', sa.String(length=8), nullable=False, server_default='regular'))
    with op.batch_alter_table('stays_reservations') as batch_op:
        batch_op.add_column(sa.Column('declined_butler', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
    with op.batch_alter_table('stays_settings') as batch_op:
        batch_op.add_column(sa.Column('vip_bonus', sa.Numeric(precision=5, scale=2), nullable=False,
                                      server_default='1'))
        batch_op.add_column(sa.Column('vvip_bonus', sa.Numeric(precision=5, scale=2), nullable=False,
                                      server_default='2'))
    op.execute(sa.text("UPDATE stays_guests SET level = 'vip' WHERE special = :t").bindparams(t=True))
    op.execute(sa.text("UPDATE stays_reservations SET declined_butler = :t WHERE escort_mode = 'declined'")
               .bindparams(t=True))
    with op.batch_alter_table('stays_guests') as batch_op:
        batch_op.alter_column('level', existing_type=sa.String(length=8), server_default=None)
    with op.batch_alter_table('stays_reservations') as batch_op:
        batch_op.alter_column('declined_butler', existing_type=sa.Boolean(), server_default=None)
    with op.batch_alter_table('stays_settings') as batch_op:
        batch_op.alter_column('vip_bonus', existing_type=sa.Numeric(precision=5, scale=2), server_default=None)
        batch_op.alter_column('vvip_bonus', existing_type=sa.Numeric(precision=5, scale=2), server_default=None)
