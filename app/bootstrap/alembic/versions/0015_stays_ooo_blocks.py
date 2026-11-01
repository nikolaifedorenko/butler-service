"""stays: OOO по половинам суток, блоки по категориям, пожелания гостей (OOO и блоки, §3).

Таблица stays_holds заменяется тремя: stays_ooo, stays_blocks (+ stays_block_nights) и
stays_guest_prefs. Переноса данных нет (боевой базы нет): прежние блоки и OOO не переносятся.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = '0015'
down_revision: str | None = '0014'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table('stays_holds', schema=None) as batch_op:
        batch_op.drop_index('ix_stays_holds_unit_start')
    op.drop_table('stays_holds')

    op.create_table('stays_ooo',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('unit_id', sa.Integer(), nullable=False),
    sa.Column('start', sa.Date(), nullable=False),
    sa.Column('end', sa.Date(), nullable=False),
    sa.Column('start_half', sa.String(length=2), nullable=False),
    sa.Column('end_half', sa.String(length=2), nullable=False),
    sa.Column('reason', sa.String(length=120), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('author_id', sa.Integer(), nullable=True),
    sa.CheckConstraint("start_half IN ('AM', 'PM')", name='ck_stays_ooo_start_half'),
    sa.CheckConstraint("end_half IN ('AM', 'PM')", name='ck_stays_ooo_end_half'),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['unit_id'], ['stays_units.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('stays_ooo', schema=None) as batch_op:
        batch_op.create_index('ix_stays_ooo_unit_start', ['unit_id', 'start'], unique=False)

    op.create_table('stays_blocks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=120), nullable=False),
    sa.Column('start', sa.Date(), nullable=False),
    sa.Column('end', sa.Date(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('author_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    op.create_table('stays_block_nights',
    sa.Column('block_id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('night', sa.Date(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.CheckConstraint('quantity >= 1', name='ck_stays_block_nights_quantity'),
    sa.ForeignKeyConstraint(['block_id'], ['stays_blocks.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['category_id'], ['stays_categories.id'], ),
    sa.PrimaryKeyConstraint('block_id', 'category_id', 'night')
    )

    op.create_table('stays_guest_prefs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('guest_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=8), nullable=False),
    sa.Column('ref_id', sa.Integer(), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.CheckConstraint("kind IN ('group', 'flag', 'unit')", name='ck_stays_guest_prefs_kind'),
    sa.ForeignKeyConstraint(['guest_id'], ['stays_guests.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('stays_guest_prefs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_stays_guest_prefs_guest_id'), ['guest_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('stays_guest_prefs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_stays_guest_prefs_guest_id'))
    op.drop_table('stays_guest_prefs')
    op.drop_table('stays_block_nights')
    op.drop_table('stays_blocks')
    with op.batch_alter_table('stays_ooo', schema=None) as batch_op:
        batch_op.drop_index('ix_stays_ooo_unit_start')
    op.drop_table('stays_ooo')

    op.create_table('stays_holds',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('unit_id', sa.Integer(), nullable=False),
    sa.Column('start', sa.Date(), nullable=False),
    sa.Column('end', sa.Date(), nullable=False),
    sa.Column('kind', sa.String(length=8), nullable=False),
    sa.Column('title', sa.String(length=120), nullable=False),
    sa.ForeignKeyConstraint(['unit_id'], ['stays_units.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('stays_holds', schema=None) as batch_op:
        batch_op.create_index('ix_stays_holds_unit_start', ['unit_id', 'start'], unique=False)
