"""stays: номерной фонд версиями «с даты» (спецификация 2026-10-26-stays-fund-versions §3).

Из stays_categories остаётся только id, из stays_units — только id; код, название, вид, вес,
обозначение, категория, этаж переезжают в снимки версии (stays_*_states). Исходная версия
published с valid_from = 2000-01-01 строится из текущих категорий и активных объектов
(неактивные остаются в stays_units — на них могут ссылаться назначения и блоки, но в фонде
их нет). Узлов дерева в исходной версии нет (group_id = NULL). Assignment.seg_index не
меняется. Добавляется stays_settings.in_production (по умолчанию false).

Откат возвращает колонки из самой ранней версии; при нескольких версиях отказывается, чтобы
не потерять историю (STAYS_FUND_DOWNGRADE_FORCE=1 — продолжить, остальные версии пропадут).
"""
from __future__ import annotations

import datetime as dt
import os

import sqlalchemy as sa
from alembic import op

revision: str = '0010'
down_revision: str | None = '0009'
branch_labels: str | None = None
depends_on: str | None = None

INITIAL_FROM = dt.date(2000, 1, 1)


def upgrade() -> None:
    bind = op.get_bind()
    op.create_table('stays_unit_flags',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=80), nullable=False),
        sa.Column('color', sa.String(length=9), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('archived', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('title'))
    op.create_table('stays_fund_groups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'))
    op.create_table('stays_fund_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('valid_from', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('base_version_id', sa.Integer(), nullable=True),
        sa.Column('rev', sa.Integer(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=True),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('draft', 'published')", name='ck_stays_fund_status'),
        sa.ForeignKeyConstraint(['author_id'], ['users.id']),
        sa.ForeignKeyConstraint(['base_version_id'], ['stays_fund_versions.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('valid_from'))
    op.create_table('stays_category_states',
        sa.Column('version_id', sa.Integer(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=16), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('weight', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('escorted', sa.Boolean(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['stays_categories.id']),
        sa.ForeignKeyConstraint(['version_id'], ['stays_fund_versions.id']),
        sa.PrimaryKeyConstraint('version_id', 'category_id'),
        sa.UniqueConstraint('version_id', 'code', name='uq_stays_cat_state_code'))
    op.create_table('stays_group_states',
        sa.Column('version_id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['stays_fund_groups.id']),
        sa.ForeignKeyConstraint(['parent_id'], ['stays_fund_groups.id']),
        sa.ForeignKeyConstraint(['version_id', 'parent_id'],
                                ['stays_group_states.version_id', 'stays_group_states.group_id']),
        sa.ForeignKeyConstraint(['version_id'], ['stays_fund_versions.id']),
        sa.PrimaryKeyConstraint('version_id', 'group_id'))
    op.create_table('stays_unit_states',
        sa.Column('version_id', sa.Integer(), nullable=False),
        sa.Column('unit_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=40), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=True),
        sa.Column('floor', sa.String(length=8), nullable=False),
        sa.ForeignKeyConstraint(['unit_id'], ['stays_units.id']),
        sa.ForeignKeyConstraint(['version_id', 'category_id'],
                                ['stays_category_states.version_id', 'stays_category_states.category_id']),
        sa.ForeignKeyConstraint(['version_id', 'group_id'],
                                ['stays_group_states.version_id', 'stays_group_states.group_id']),
        sa.ForeignKeyConstraint(['version_id'], ['stays_fund_versions.id']),
        sa.PrimaryKeyConstraint('version_id', 'unit_id'),
        sa.UniqueConstraint('version_id', 'label', name='uq_stays_unit_state_label'))
    op.create_table('stays_unit_state_flags',
        sa.Column('version_id', sa.Integer(), nullable=False),
        sa.Column('unit_id', sa.Integer(), nullable=False),
        sa.Column('flag_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['flag_id'], ['stays_unit_flags.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['version_id', 'unit_id'],
                                ['stays_unit_states.version_id', 'stays_unit_states.unit_id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('version_id', 'unit_id', 'flag_id'))
    op.create_index('ix_stays_unit_state_flags_version_flag', 'stays_unit_state_flags',
                    ['version_id', 'flag_id'])
    op.create_table('stays_unit_lineage',
        sa.Column('unit_id', sa.Integer(), nullable=False),
        sa.Column('predecessor_id', sa.Integer(), nullable=False),
        sa.Column('version_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['predecessor_id'], ['stays_units.id']),
        sa.ForeignKeyConstraint(['unit_id'], ['stays_units.id']),
        sa.ForeignKeyConstraint(['version_id'], ['stays_fund_versions.id']),
        sa.PrimaryKeyConstraint('unit_id', 'predecessor_id'))

    # исходная версия из текущих данных
    now = dt.datetime.now()
    versions = sa.table('stays_fund_versions', sa.column('valid_from'), sa.column('status'),
                        sa.column('rev'), sa.column('note'), sa.column('created_at'),
                        sa.column('published_at'))
    op.bulk_insert(versions, [{'valid_from': INITIAL_FROM, 'status': 'published', 'rev': 1,
                               'note': 'Исходный фонд (миграция 0010)', 'created_at': now,
                               'published_at': now}])
    vid = bind.execute(sa.text("SELECT id FROM stays_fund_versions WHERE valid_from = :d"),
                       {'d': INITIAL_FROM}).scalar_one()
    bind.execute(sa.text(
        "INSERT INTO stays_category_states (version_id, category_id, code, title, kind, weight, "
        "escorted, sort_order) SELECT :v, id, code, title, kind, weight, escorted, sort_order "
        "FROM stays_categories"), {'v': vid})
    bind.execute(sa.text(
        "INSERT INTO stays_unit_states (version_id, unit_id, label, category_id, group_id, floor) "
        "SELECT :v, id, label, category_id, NULL, floor FROM stays_units WHERE active"), {'v': vid})

    # из постоянных таблиц уходит всё, кроме id
    op.drop_index('ix_stays_units_category_id', table_name='stays_units', if_exists=True)
    with op.batch_alter_table('stays_units') as batch_op:
        for col in ('label', 'category_id', 'building', 'floor', 'active', 'sort_order'):
            batch_op.drop_column(col)
    with op.batch_alter_table('stays_categories') as batch_op:
        for col in ('code', 'title', 'kind', 'escorted', 'weight', 'sort_order'):
            batch_op.drop_column(col)
    op.add_column('stays_settings', sa.Column('in_production', sa.Boolean(), nullable=False,
                                              server_default=sa.false()))


def downgrade() -> None:
    bind = op.get_bind()
    n = bind.execute(sa.text("SELECT COUNT(*) FROM stays_fund_versions")).scalar_one()
    if n > 1 and os.environ.get('STAYS_FUND_DOWNGRADE_FORCE') != '1':
        raise RuntimeError(
            f"0010: откат оставил бы одну версию фонда из {n}: остальные версии и история "
            "фонда пропадут. Откат схемы не поддерживается — восстановите базу из бэкапа "
            "(deploy/README.md); осознанно продолжить: STAYS_FUND_DOWNGRADE_FORCE=1")
    op.drop_column('stays_settings', 'in_production')

    # колонки возвращаются со значениями по умолчанию; заполняются из самой ранней версии
    op.add_column('stays_categories', sa.Column('code', sa.String(length=16), nullable=False, server_default=''))
    op.add_column('stays_categories', sa.Column('title', sa.String(length=120), nullable=False, server_default=''))
    op.add_column('stays_categories', sa.Column('kind', sa.String(length=16), nullable=False, server_default='room'))
    op.add_column('stays_categories', sa.Column('escorted', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('stays_categories', sa.Column('weight', sa.Numeric(precision=5, scale=2), nullable=False, server_default='1'))
    op.add_column('stays_categories', sa.Column('sort_order', sa.Integer(), nullable=False, server_default='100'))
    op.add_column('stays_units', sa.Column('label', sa.String(length=40), nullable=False, server_default=''))
    op.add_column('stays_units', sa.Column('category_id', sa.Integer(), nullable=True))
    op.add_column('stays_units', sa.Column('building', sa.String(length=40), nullable=False, server_default=''))
    op.add_column('stays_units', sa.Column('floor', sa.String(length=8), nullable=False, server_default=''))
    op.add_column('stays_units', sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('stays_units', sa.Column('sort_order', sa.Integer(), nullable=False, server_default='100'))

    base = bind.execute(sa.text("SELECT id FROM stays_fund_versions ORDER BY valid_from LIMIT 1")).scalar_one_or_none()
    p = {'v': base}
    bind.execute(sa.text(
        "UPDATE stays_categories SET "
        "code = (SELECT s.code FROM stays_category_states s WHERE s.version_id = :v AND s.category_id = stays_categories.id), "
        "title = (SELECT s.title FROM stays_category_states s WHERE s.version_id = :v AND s.category_id = stays_categories.id), "
        "kind = (SELECT s.kind FROM stays_category_states s WHERE s.version_id = :v AND s.category_id = stays_categories.id), "
        "escorted = (SELECT s.escorted FROM stays_category_states s WHERE s.version_id = :v AND s.category_id = stays_categories.id), "
        "weight = (SELECT s.weight FROM stays_category_states s WHERE s.version_id = :v AND s.category_id = stays_categories.id), "
        "sort_order = (SELECT s.sort_order FROM stays_category_states s WHERE s.version_id = :v AND s.category_id = stays_categories.id) "
        "WHERE EXISTS (SELECT 1 FROM stays_category_states s WHERE s.version_id = :v AND s.category_id = stays_categories.id)"), p)
    # категории и объекты, которых нет в исходной версии (заведены позже): значения-заглушки
    bind.execute(sa.text(
        "UPDATE stays_categories SET code = 'cat-' || id, title = 'Категория ' || id WHERE code = ''"))
    bind.execute(sa.text(
        "UPDATE stays_units SET "
        "label = (SELECT s.label FROM stays_unit_states s WHERE s.version_id = :v AND s.unit_id = stays_units.id), "
        "category_id = (SELECT s.category_id FROM stays_unit_states s WHERE s.version_id = :v AND s.unit_id = stays_units.id), "
        "floor = (SELECT s.floor FROM stays_unit_states s WHERE s.version_id = :v AND s.unit_id = stays_units.id), "
        "active = :yes "
        "WHERE EXISTS (SELECT 1 FROM stays_unit_states s WHERE s.version_id = :v AND s.unit_id = stays_units.id)"),
        {**p, 'yes': True})
    bind.execute(sa.text("UPDATE stays_units SET label = 'unit-' || id WHERE label = ''"))
    bind.execute(sa.text(
        "UPDATE stays_units SET category_id = (SELECT MIN(id) FROM stays_categories) WHERE category_id IS NULL"))

    for t in ('stays_unit_lineage', 'stays_unit_state_flags', 'stays_unit_states', 'stays_group_states',
              'stays_category_states', 'stays_fund_versions', 'stays_fund_groups', 'stays_unit_flags'):
        op.drop_table(t)

    with op.batch_alter_table('stays_categories') as batch_op:
        batch_op.create_unique_constraint('uq_stays_categories_code', ['code'])
        for col in ('code', 'title', 'kind', 'escorted', 'weight', 'sort_order'):
            batch_op.alter_column(col, server_default=None)
    with op.batch_alter_table('stays_units') as batch_op:
        batch_op.alter_column('category_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_stays_units_category', 'stays_categories', ['category_id'], ['id'])
        batch_op.create_unique_constraint('uq_stays_units_label', ['label'])
        batch_op.create_index('ix_stays_units_category_id', ['category_id'])
        for col in ('label', 'building', 'floor', 'active', 'sort_order'):
            batch_op.alter_column(col, server_default=None)
