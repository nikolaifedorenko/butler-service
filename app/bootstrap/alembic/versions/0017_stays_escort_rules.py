"""stays: правила сопровождения — справочник VIP-кодов, «особый гость», режим сопровождения брони
(спецификация 2026-10-27-stays-escort-rules-design §3).

Только добавляет: справочник stays_vip_codes; у гостя vip_code_id и special, у брони vip_code_id и
escort_mode (rules | required | declined), у настроек special_factor, у узла фонда escorted. Старые
колонки (level, declined_butler, vip_bonus, vvip_bonus) остаются до отдельной ревизии. Перенос:
declined_butler → escort_mode = 'declined'; level vip / vvip → special = true.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = '0017'
down_revision: str | None = '0016'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table('stays_vip_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=8), nullable=False),
        sa.Column('title', sa.String(length=80), nullable=False),
        sa.Column('escorted', sa.Boolean(), nullable=False),
        sa.Column('factor', sa.Numeric(precision=4, scale=2), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('archived', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'))
    with op.batch_alter_table('stays_guests') as batch_op:
        batch_op.add_column(sa.Column('vip_code_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('special', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.create_foreign_key('fk_stays_guests_vip_code', 'stays_vip_codes', ['vip_code_id'], ['id'])
    with op.batch_alter_table('stays_reservations') as batch_op:
        batch_op.add_column(sa.Column('vip_code_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('escort_mode', sa.String(length=8), nullable=False,
                                      server_default='rules'))
        batch_op.create_foreign_key('fk_stays_reservations_vip_code', 'stays_vip_codes',
                                    ['vip_code_id'], ['id'])
    with op.batch_alter_table('stays_settings') as batch_op:
        batch_op.add_column(sa.Column('special_factor', sa.Numeric(precision=4, scale=2), nullable=False,
                                      server_default='2'))
    with op.batch_alter_table('stays_group_states') as batch_op:
        batch_op.add_column(sa.Column('escorted', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute(sa.text("UPDATE stays_reservations SET escort_mode = 'declined' WHERE declined_butler"))
    op.execute(sa.text("UPDATE stays_guests SET special = :t WHERE level IN ('vip', 'vvip')")
               .bindparams(t=True))
    with op.batch_alter_table('stays_guests') as batch_op:
        batch_op.alter_column('special', existing_type=sa.Boolean(), server_default=None)
    with op.batch_alter_table('stays_reservations') as batch_op:
        batch_op.alter_column('escort_mode', existing_type=sa.String(length=8), server_default=None)
    with op.batch_alter_table('stays_settings') as batch_op:
        batch_op.alter_column('special_factor', existing_type=sa.Numeric(precision=4, scale=2),
                              server_default=None)
    with op.batch_alter_table('stays_group_states') as batch_op:
        batch_op.alter_column('escorted', existing_type=sa.Boolean(), server_default=None)


def downgrade() -> None:
    with op.batch_alter_table('stays_group_states') as batch_op:
        batch_op.drop_column('escorted')
    with op.batch_alter_table('stays_settings') as batch_op:
        batch_op.drop_column('special_factor')
    with op.batch_alter_table('stays_reservations') as batch_op:
        batch_op.drop_constraint('fk_stays_reservations_vip_code', type_='foreignkey')
        batch_op.drop_column('escort_mode')
        batch_op.drop_column('vip_code_id')
    with op.batch_alter_table('stays_guests') as batch_op:
        batch_op.drop_constraint('fk_stays_guests_vip_code', type_='foreignkey')
        batch_op.drop_column('special')
        batch_op.drop_column('vip_code_id')
    op.drop_table('stays_vip_codes')
