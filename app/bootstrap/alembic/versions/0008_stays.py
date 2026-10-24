"""stays: модуль «Шахматка» — фонд, гости, брони, покрытие батлерами (спецификация
docs/superpowers/specs/2026-10-23-stays-chessboard-design.md, §3).

Кроме таблиц ревизия заводит строку настроек stays_settings(id=1) и две роли как данные
(ADR-0011): «Руководство: только просмотр» и «Загрузка без гостей» (§7) с их грантами.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = '0008'
down_revision: str | None = '0007'
branch_labels: str | None = None
depends_on: str | None = None

# снимок ролей модуля на 23.10.2026: (код, название, права)
ROLES = (
    ("mgmt_view", "Руководство: только просмотр", ("stays.view", "stays.guests")),
    ("occupancy", "Загрузка без гостей", ("stays.occupancy",)),
)


def upgrade() -> None:
    bind = op.get_bind()
    # база до Alembic штампуется 0001 после create_all текущих моделей — таблицы могут уже быть
    if "stays_categories" not in sa.inspect(bind).get_table_names():
        _create_tables()
    if not bind.execute(sa.text("SELECT 1 FROM stays_settings WHERE id = 1")).first():
        op.bulk_insert(sa.table("stays_settings", sa.column("id"), sa.column("vip_bonus"),
                                sa.column("vvip_bonus"), sa.column("daily_limit"),
                                sa.column("replacement_codes")),
                       [{"id": 1, "vip_bonus": 1, "vvip_bonus": 2, "daily_limit": 8,
                         "replacement_codes": "ОТ,ДО,Б,ОВ,К"}])
    have = {code for (code,) in bind.execute(sa.text("SELECT code FROM roles"))}
    roles = sa.table("roles", sa.column("code"), sa.column("title"), sa.column("rank"),
                     sa.column("max_assignable_rank"), sa.column("builtin"))
    grants = sa.table("access_grants", sa.column("role"), sa.column("permission"),
                      sa.column("effect"))
    # уровень 20: выше сотрудника — роли назначает менеджер, а не старший (max_assignable 10)
    for code, title, perms in ROLES:
        if code in have:
            continue
        op.bulk_insert(roles, [{"code": code, "title": title, "rank": 20,
                                "max_assignable_rank": -1, "builtin": False}])
        op.bulk_insert(grants, [{"role": code, "permission": p, "effect": "allow"} for p in perms])


def _create_tables() -> None:
        op.create_table('stays_categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=16), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('escorted', sa.Boolean(), nullable=False),
        sa.Column('weight', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
        )
        op.create_table('stays_fields',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('target', sa.String(length=12), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('kind', sa.String(length=8), nullable=False),
        sa.Column('choices_json', sa.Text(), nullable=False),
        sa.Column('searchable', sa.Boolean(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('target', 'code', name='uq_stays_field')
        )
        op.create_table('stays_groups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_table('stays_guests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('last_name', sa.String(length=80), nullable=False),
        sa.Column('first_name', sa.String(length=80), nullable=False),
        sa.Column('middle_name', sa.String(length=80), nullable=False),
        sa.Column('phone', sa.String(length=24), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=False),
        sa.Column('birth_date', sa.Date(), nullable=True),
        sa.Column('level', sa.String(length=8), nullable=False),
        sa.Column('preferences_json', sa.Text(), nullable=False),
        sa.Column('special_dates_json', sa.Text(), nullable=False),
        sa.Column('fields_json', sa.Text(), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('external_id', sa.String(length=64), nullable=True),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('search_text', sa.String(length=1000), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_table('stays_labels',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=80), nullable=False),
        sa.Column('color', sa.String(length=9), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('title')
        )
        op.create_table('stays_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vip_bonus', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('vvip_bonus', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('daily_limit', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('replacement_codes', sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_table('stays_guest_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('guest_a_id', sa.Integer(), nullable=False),
        sa.Column('guest_b_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(['guest_a_id'], ['stays_guests.id'], ),
        sa.ForeignKeyConstraint(['guest_b_id'], ['stays_guests.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('guest_a_id', 'guest_b_id', 'kind', name='uq_stays_guest_link')
        )
        with op.batch_alter_table('stays_guest_links', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_stays_guest_links_guest_a_id'), ['guest_a_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_stays_guest_links_guest_b_id'), ['guest_b_id'], unique=False)

        op.create_table('stays_reservations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('number', sa.String(length=40), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('check_in', sa.Date(), nullable=False),
        sa.Column('check_out', sa.Date(), nullable=False),
        sa.Column('early', sa.Boolean(), nullable=False),
        sa.Column('late', sa.Boolean(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.Column('paid_by', sa.String(length=120), nullable=False),
        sa.Column('label_id', sa.Integer(), nullable=True),
        sa.Column('customer', sa.String(length=160), nullable=False),
        sa.Column('purpose', sa.String(length=160), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('declined_butler', sa.Boolean(), nullable=False),
        sa.Column('fields_json', sa.Text(), nullable=False),
        sa.Column('external_id', sa.String(length=64), nullable=True),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('search_text', sa.String(length=1000), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['stays_categories.id'], ),
        sa.ForeignKeyConstraint(['group_id'], ['stays_groups.id'], ),
        sa.ForeignKeyConstraint(['label_id'], ['stays_labels.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('stays_reservations', schema=None) as batch_op:
            batch_op.create_index('ix_stays_res_dates', ['check_in', 'check_out'], unique=False)
            batch_op.create_index(batch_op.f('ix_stays_reservations_group_id'), ['group_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_stays_reservations_number'), ['number'], unique=False)

        op.create_table('stays_units',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=40), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.Column('building', sa.String(length=40), nullable=False),
        sa.Column('floor', sa.String(length=8), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['stays_categories.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('label')
        )
        with op.batch_alter_table('stays_units', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_stays_units_category_id'), ['category_id'], unique=False)

        op.create_table('stays_assignments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reservation_id', sa.Integer(), nullable=False),
        sa.Column('seg_index', sa.Integer(), nullable=False),
        sa.Column('unit_id', sa.Integer(), nullable=True),
        sa.Column('pinned', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['reservation_id'], ['stays_reservations.id'], ),
        sa.ForeignKeyConstraint(['unit_id'], ['stays_units.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reservation_id', 'seg_index', name='uq_stays_assignment')
        )
        with op.batch_alter_table('stays_assignments', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_stays_assignments_unit_id'), ['unit_id'], unique=False)

        op.create_table('stays_companions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reservation_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(['reservation_id'], ['stays_reservations.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('stays_companions', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_stays_companions_reservation_id'), ['reservation_id'], unique=False)

        op.create_table('stays_coverage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('reservation_id', sa.Integer(), nullable=True),
        sa.Column('group_id', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(length=8), nullable=False),
        sa.Column('overnight', sa.Boolean(), nullable=False),
        sa.Column('comment', sa.String(length=255), nullable=False),
        sa.CheckConstraint('(reservation_id IS NULL) <> (group_id IS NULL)', name='ck_stays_coverage_target'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
        sa.ForeignKeyConstraint(['group_id'], ['stays_groups.id'], ),
        sa.ForeignKeyConstraint(['reservation_id'], ['stays_reservations.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('stays_coverage', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_stays_coverage_day'), ['day'], unique=False)
            batch_op.create_index('ix_stays_coverage_emp_day', ['employee_id', 'day'], unique=False)
            batch_op.create_index(batch_op.f('ix_stays_coverage_reservation_id'), ['reservation_id'], unique=False)

        op.create_table('stays_escorts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('employee_id')
        )
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

        op.create_table('stays_logistics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reservation_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=12), nullable=False),
        sa.Column('date', sa.Date(), nullable=True),
        sa.Column('time', sa.String(length=5), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(['reservation_id'], ['stays_reservations.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('stays_logistics', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_stays_logistics_reservation_id'), ['reservation_id'], unique=False)

        op.create_table('stays_moves',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reservation_id', sa.Integer(), nullable=False),
        sa.Column('move_date', sa.Date(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['stays_categories.id'], ),
        sa.ForeignKeyConstraint(['reservation_id'], ['stays_reservations.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reservation_id', 'move_date', name='uq_stays_move')
        )
        op.create_table('stays_occupants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reservation_id', sa.Integer(), nullable=False),
        sa.Column('guest_id', sa.Integer(), nullable=False),
        sa.Column('date_from', sa.Date(), nullable=False),
        sa.Column('date_to', sa.Date(), nullable=False),
        sa.Column('role', sa.String(length=8), nullable=False),
        sa.ForeignKeyConstraint(['guest_id'], ['stays_guests.id'], ),
        sa.ForeignKeyConstraint(['reservation_id'], ['stays_reservations.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('stays_occupants', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_stays_occupants_guest_id'), ['guest_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_stays_occupants_reservation_id'), ['reservation_id'], unique=False)

        op.create_table('stays_coverage_guests',
        sa.Column('coverage_id', sa.Integer(), nullable=False),
        sa.Column('guest_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['coverage_id'], ['stays_coverage.id'], ),
        sa.ForeignKeyConstraint(['guest_id'], ['stays_guests.id'], ),
        sa.PrimaryKeyConstraint('coverage_id', 'guest_id')
        )


def downgrade() -> None:
    bind = op.get_bind()
    codes = tuple(c for c, _, _ in ROLES)
    bind.execute(sa.text("DELETE FROM access_grants WHERE role IN :c").bindparams(
        sa.bindparam("c", expanding=True)), {"c": codes})
    bind.execute(sa.text("DELETE FROM roles WHERE code IN :c").bindparams(
        sa.bindparam("c", expanding=True)), {"c": codes})
    op.drop_table('stays_coverage_guests')
    with op.batch_alter_table('stays_occupants', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_stays_occupants_reservation_id'))
        batch_op.drop_index(batch_op.f('ix_stays_occupants_guest_id'))

    op.drop_table('stays_occupants')
    op.drop_table('stays_moves')
    with op.batch_alter_table('stays_logistics', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_stays_logistics_reservation_id'))

    op.drop_table('stays_logistics')
    with op.batch_alter_table('stays_holds', schema=None) as batch_op:
        batch_op.drop_index('ix_stays_holds_unit_start')

    op.drop_table('stays_holds')
    op.drop_table('stays_escorts')
    with op.batch_alter_table('stays_coverage', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_stays_coverage_reservation_id'))
        batch_op.drop_index('ix_stays_coverage_emp_day')
        batch_op.drop_index(batch_op.f('ix_stays_coverage_day'))

    op.drop_table('stays_coverage')
    with op.batch_alter_table('stays_companions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_stays_companions_reservation_id'))

    op.drop_table('stays_companions')
    with op.batch_alter_table('stays_assignments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_stays_assignments_unit_id'))

    op.drop_table('stays_assignments')
    with op.batch_alter_table('stays_units', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_stays_units_category_id'))

    op.drop_table('stays_units')
    with op.batch_alter_table('stays_reservations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_stays_reservations_number'))
        batch_op.drop_index(batch_op.f('ix_stays_reservations_group_id'))
        batch_op.drop_index('ix_stays_res_dates')

    op.drop_table('stays_reservations')
    with op.batch_alter_table('stays_guest_links', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_stays_guest_links_guest_b_id'))
        batch_op.drop_index(batch_op.f('ix_stays_guest_links_guest_a_id'))

    op.drop_table('stays_guest_links')
    op.drop_table('stays_settings')
    op.drop_table('stays_labels')
    op.drop_table('stays_guests')
    op.drop_table('stays_groups')
    op.drop_table('stays_fields')
    op.drop_table('stays_categories')
