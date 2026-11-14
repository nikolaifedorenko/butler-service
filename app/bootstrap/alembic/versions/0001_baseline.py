"""Начальная схема (ADR-0013, раздел 3): все таблицы и справочные строки одной ревизией.

Заменяет ревизии 0001–0020 прежней истории (13.11.2026): боевых данных не было, базы,
созданные ими, не обновляются и создаются заново. Справочные строки — те, что прежние
ревизии вставляли в пустую базу: встроенные роли, роли просмотра шахматки с правами,
настройки шахматки и исходная версия фонда.
"""
from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from alembic import op

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table('access_groups',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('car_locations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('builtin', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('departments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('engine_settings_versions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=False),
    sa.Column('payload_json', sa.Text(), nullable=False),
    sa.Column('note', sa.String(length=255), nullable=False),
    sa.Column('created_by_name', sa.String(length=120), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_engine_settings_versions_valid_from'), 'engine_settings_versions', ['valid_from'], unique=False)
    op.create_table('login_attempts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=80), nullable=False),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_login_attempts_key'), 'login_attempts', ['key'], unique=False)
    op.create_index(op.f('ix_login_attempts_ts'), 'login_attempts', ['ts'], unique=False)
    op.create_table('night_reports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('shift_label', sa.String(length=80), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('closed_at', sa.DateTime(), nullable=True),
    sa.Column('close_reason', sa.String(length=16), nullable=False),
    sa.Column('reopened_at', sa.DateTime(), nullable=True),
    sa.Column('result', sa.String(length=16), nullable=False),
    sa.Column('cars_step_done', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_night_reports_date'), 'night_reports', ['date'], unique=True)
    op.create_table('night_zones',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('notify_chats',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('chat_id', sa.BigInteger(), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('username', sa.String(length=120), nullable=False),
    sa.Column('kind', sa.String(length=24), nullable=False),
    sa.Column('first_seen', sa.DateTime(), nullable=False),
    sa.Column('last_seen', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notify_chats_chat_id'), 'notify_chats', ['chat_id'], unique=True)
    op.create_table('notify_templates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('domain', sa.String(length=32), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notify_templates_domain'), 'notify_templates', ['domain'], unique=True)
    op.create_table('responsibility_services',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('use_telegram', sa.Boolean(), nullable=False),
    sa.Column('use_email', sa.Boolean(), nullable=False),
    sa.Column('email_to', sa.String(length=200), nullable=False),
    sa.Column('email_copy', sa.String(length=400), nullable=False),
    sa.Column('chat_ids', sa.Text(), nullable=False),
    sa.Column('note', sa.String(length=300), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('roles',
    sa.Column('code', sa.String(length=20), nullable=False),
    sa.Column('title', sa.String(length=80), nullable=False),
    sa.Column('rank', sa.Integer(), nullable=False),
    sa.Column('max_assignable_rank', sa.Integer(), nullable=False),
    sa.Column('builtin', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('code')
    )
    op.create_table('settings',
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('shift_types',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('start_time', sa.String(length=5), nullable=False),
    sa.Column('end_time', sa.String(length=5), nullable=False),
    sa.Column('overnight', sa.Boolean(), nullable=False),
    sa.Column('color', sa.String(length=16), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('is_working', sa.Boolean(), nullable=False),
    sa.Column('counts_as_worked', sa.Boolean(), nullable=False),
    sa.Column('is_default_off', sa.Boolean(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('punch_in_allowed', sa.Boolean(), nullable=False),
    sa.Column('punch_out_allowed', sa.Boolean(), nullable=False),
    sa.Column('doc_type', sa.String(length=40), nullable=False),
    sa.Column('archived_at', sa.Date(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_table('statement_kinds',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('builtin', sa.Boolean(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_table('stays_categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('stays_category_kinds',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=40), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('expanded', sa.Boolean(), nullable=False),
    sa.Column('archived', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('title')
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
    op.create_table('stays_fund_groups',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('stays_groups',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=120), nullable=False),
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
    sa.Column('special_factor', sa.Numeric(precision=4, scale=2), nullable=False),
    sa.Column('daily_limit', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('replacement_codes', sa.String(length=120), nullable=False),
    sa.Column('in_production', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('stays_unit_flags',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=80), nullable=False),
    sa.Column('color', sa.String(length=9), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('archived', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('title')
    )
    op.create_table('stays_units',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('stays_vip_codes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=8), nullable=False),
    sa.Column('title', sa.String(length=80), nullable=False),
    sa.Column('escorted', sa.Boolean(), nullable=False),
    sa.Column('factor', sa.Numeric(precision=4, scale=2), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('archived', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_table('subdivisions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('employees',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('full_name', sa.String(length=200), nullable=False),
    sa.Column('short_name', sa.String(length=120), nullable=False),
    sa.Column('full_name_genitive', sa.String(length=220), nullable=False),
    sa.Column('position', sa.String(length=120), nullable=False),
    sa.Column('phone', sa.String(length=40), nullable=False),
    sa.Column('tab_number', sa.String(length=40), nullable=False),
    sa.Column('hired_at', sa.Date(), nullable=True),
    sa.Column('emergency_name', sa.String(length=200), nullable=False),
    sa.Column('emergency_phone', sa.String(length=40), nullable=False),
    sa.Column('telegram', sa.String(length=64), nullable=False),
    sa.Column('email', sa.String(length=120), nullable=False),
    sa.Column('dismissed_at', sa.Date(), nullable=True),
    sa.Column('nationality', sa.String(length=120), nullable=False),
    sa.Column('subdivision', sa.String(length=160), nullable=False),
    sa.Column('department_id', sa.Integer(), nullable=True),
    sa.Column('schedule_group', sa.String(length=80), nullable=False),
    sa.Column('group_color', sa.String(length=16), nullable=False),
    sa.Column('schedule_pattern', sa.String(length=60), nullable=False),
    sa.Column('schedule_anchor', sa.Date(), nullable=True),
    sa.Column('balance_hours', sa.Float(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('deleted_at', sa.Date(), nullable=True),
    sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('night_areas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('zone_id', sa.Integer(), nullable=True),
    sa.Column('category', sa.String(length=80), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['zone_id'], ['night_zones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_night_areas_zone_id'), 'night_areas', ['zone_id'], unique=False)
    op.create_table('shift_revisions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('shift_type_id', sa.Integer(), nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=False),
    sa.Column('code', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('start_time', sa.String(length=5), nullable=False),
    sa.Column('end_time', sa.String(length=5), nullable=False),
    sa.Column('overnight', sa.Boolean(), nullable=False),
    sa.Column('color', sa.String(length=16), nullable=False),
    sa.Column('is_working', sa.Boolean(), nullable=False),
    sa.Column('counts_as_worked', sa.Boolean(), nullable=False),
    sa.Column('is_default_off', sa.Boolean(), nullable=False),
    sa.Column('doc_type', sa.String(length=40), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['shift_type_id'], ['shift_types.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_shift_revisions_shift_type_id'), 'shift_revisions', ['shift_type_id'], unique=False)
    op.create_table('stays_reservations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('number', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('check_in', sa.Date(), nullable=False),
    sa.Column('check_out', sa.Date(), nullable=False),
    sa.Column('early', sa.Boolean(), nullable=False),
    sa.Column('late', sa.Boolean(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('paid_category_id', sa.Integer(), nullable=True),
    sa.Column('label_id', sa.Integer(), nullable=True),
    sa.Column('customer', sa.String(length=160), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('vip_code_id', sa.Integer(), nullable=True),
    sa.Column('escort_mode', sa.String(length=8), nullable=False),
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
    sa.ForeignKeyConstraint(['paid_category_id'], ['stays_categories.id'], ),
    sa.ForeignKeyConstraint(['vip_code_id'], ['stays_vip_codes.id'], name='fk_stays_reservations_vip_code'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_stays_res_dates', 'stays_reservations', ['check_in', 'check_out'], unique=False)
    op.create_index(op.f('ix_stays_reservations_group_id'), 'stays_reservations', ['group_id'], unique=False)
    op.create_index(op.f('ix_stays_reservations_number'), 'stays_reservations', ['number'], unique=False)
    op.create_table('zone_checklist_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('zone_id', sa.Integer(), nullable=False),
    sa.Column('text', sa.String(length=300), nullable=False),
    sa.Column('service_id', sa.Integer(), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['service_id'], ['responsibility_services.id'], ),
    sa.ForeignKeyConstraint(['zone_id'], ['night_zones.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_zone_checklist_items_service_id'), 'zone_checklist_items', ['service_id'], unique=False)
    op.create_index(op.f('ix_zone_checklist_items_zone_id'), 'zone_checklist_items', ['zone_id'], unique=False)
    op.create_table('block_assignments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=False),
    sa.Column('group', sa.String(length=80), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('pattern_json', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('employee_id', 'group', 'start_date', name='uq_block_emp_group_start')
    )
    op.create_index(op.f('ix_block_assignments_employee_id'), 'block_assignments', ['employee_id'], unique=False)
    op.create_table('checklist_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('area_id', sa.Integer(), nullable=False),
    sa.Column('text', sa.String(length=300), nullable=False),
    sa.Column('service_id', sa.Integer(), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['area_id'], ['night_areas.id'], ),
    sa.ForeignKeyConstraint(['service_id'], ['responsibility_services.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_checklist_items_area_id'), 'checklist_items', ['area_id'], unique=False)
    op.create_index(op.f('ix_checklist_items_service_id'), 'checklist_items', ['service_id'], unique=False)
    op.create_table('checklist_overrides',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('area_id', sa.Integer(), nullable=False),
    sa.Column('zone_item_id', sa.Integer(), nullable=False),
    sa.Column('text', sa.String(length=300), nullable=False),
    sa.Column('disabled', sa.Boolean(), nullable=False),
    sa.Column('service_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['area_id'], ['night_areas.id'], ),
    sa.ForeignKeyConstraint(['service_id'], ['responsibility_services.id'], ),
    sa.ForeignKeyConstraint(['zone_item_id'], ['zone_checklist_items.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('area_id', 'zone_item_id', name='uq_checklist_override_area_item')
    )
    op.create_index(op.f('ix_checklist_overrides_area_id'), 'checklist_overrides', ['area_id'], unique=False)
    op.create_index(op.f('ix_checklist_overrides_zone_item_id'), 'checklist_overrides', ['zone_item_id'], unique=False)
    op.create_table('day_modifiers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=32), nullable=False),
    sa.Column('value', sa.String(length=8), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=True),
    sa.Column('group', sa.String(length=80), nullable=False),
    sa.Column('date', sa.Date(), nullable=True),
    sa.Column('period_start', sa.Date(), nullable=True),
    sa.Column('note', sa.String(length=255), nullable=False),
    sa.Column('created_by_name', sa.String(length=120), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_day_modifiers_date'), 'day_modifiers', ['date'], unique=False)
    op.create_index(op.f('ix_day_modifiers_period_start'), 'day_modifiers', ['period_start'], unique=False)
    op.create_table('deferred_carry',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=False),
    sa.Column('period_start', sa.Date(), nullable=False),
    sa.Column('source_day', sa.Date(), nullable=False),
    sa.Column('tariff', sa.String(length=12), nullable=False),
    sa.Column('minutes', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_deferred_carry_employee_id'), 'deferred_carry', ['employee_id'], unique=False)
    op.create_index(op.f('ix_deferred_carry_period_start'), 'deferred_carry', ['period_start'], unique=False)
    op.create_table('emergency_contacts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('phone', sa.String(length=40), nullable=False),
    sa.Column('relation', sa.String(length=60), nullable=False),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_emergency_contacts_employee_id'), 'emergency_contacts', ['employee_id'], unique=False)
    op.create_table('period_closings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=False),
    sa.Column('period_start', sa.Date(), nullable=False),
    sa.Column('period_end', sa.Date(), nullable=False),
    sa.Column('step_minutes', sa.Integer(), nullable=False),
    sa.Column('previous_step_minutes', sa.Integer(), nullable=False),
    sa.Column('bank_open_minutes', sa.Integer(), nullable=False),
    sa.Column('deferred_in_json', sa.Text(), nullable=False),
    sa.Column('closing_bank_minutes', sa.Integer(), nullable=False),
    sa.Column('settings_versions', sa.String(length=255), nullable=False),
    sa.Column('result_json', sa.Text(), nullable=False),
    sa.Column('flags_json', sa.Text(), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('closed_by_name', sa.String(length=120), nullable=False),
    sa.Column('closed_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('employee_id', 'period_start', name='uq_closing_emp_period')
    )
    op.create_index(op.f('ix_period_closings_employee_id'), 'period_closings', ['employee_id'], unique=False)
    op.create_table('position_history',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.String(length=120), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_position_history_employee_id'), 'position_history', ['employee_id'], unique=False)
    op.create_table('stays_assignments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('reservation_id', sa.Integer(), nullable=False),
    sa.Column('seg_index', sa.Integer(), nullable=False),
    sa.Column('unit_id', sa.Integer(), nullable=True),
    sa.Column('pinned', sa.Boolean(), nullable=False),
    sa.Column('start_pos', sa.Integer(), nullable=True),
    sa.Column('pin_unit_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['pin_unit_id'], ['stays_units.id'], name='fk_stays_assignments_pin_unit'),
    sa.ForeignKeyConstraint(['reservation_id'], ['stays_reservations.id'], ),
    sa.ForeignKeyConstraint(['unit_id'], ['stays_units.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('reservation_id', 'seg_index', name='uq_stays_assignment')
    )
    op.create_index(op.f('ix_stays_assignments_unit_id'), 'stays_assignments', ['unit_id'], unique=False)
    op.create_table('stays_companions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('reservation_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.ForeignKeyConstraint(['reservation_id'], ['stays_reservations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_stays_companions_reservation_id'), 'stays_companions', ['reservation_id'], unique=False)
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
    op.create_index(op.f('ix_stays_coverage_day'), 'stays_coverage', ['day'], unique=False)
    op.create_index('ix_stays_coverage_emp_day', 'stays_coverage', ['employee_id', 'day'], unique=False)
    op.create_index(op.f('ix_stays_coverage_reservation_id'), 'stays_coverage', ['reservation_id'], unique=False)
    op.create_table('stays_escorts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('employee_id')
    )
    op.create_table('stays_guests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('last_name', sa.String(length=80), nullable=False),
    sa.Column('first_name', sa.String(length=80), nullable=False),
    sa.Column('middle_name', sa.String(length=80), nullable=False),
    sa.Column('phone', sa.String(length=24), nullable=False),
    sa.Column('email', sa.String(length=120), nullable=False),
    sa.Column('birth_date', sa.Date(), nullable=True),
    sa.Column('gender', sa.String(length=1), nullable=False),
    sa.Column('vip_code_id', sa.Integer(), nullable=True),
    sa.Column('special', sa.Boolean(), nullable=False),
    sa.Column('preferences_json', sa.Text(), nullable=False),
    sa.Column('special_dates_json', sa.Text(), nullable=False),
    sa.Column('fields_json', sa.Text(), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('external_id', sa.String(length=64), nullable=True),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('created_by_employee_id', sa.Integer(), nullable=True),
    sa.Column('search_text', sa.String(length=1000), nullable=False),
    sa.Column('name_text', sa.String(length=400), server_default='', nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_employee_id'], ['employees.id'], name='fk_stays_guests_created_by'),
    sa.ForeignKeyConstraint(['vip_code_id'], ['stays_vip_codes.id'], name='fk_stays_guests_vip_code'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_stays_guests_created_by_employee_id'), 'stays_guests', ['created_by_employee_id'], unique=False)
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
    op.create_index(op.f('ix_stays_logistics_reservation_id'), 'stays_logistics', ['reservation_id'], unique=False)
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
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('password_hash', sa.String(length=256), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('token_version', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_table('access_grants',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('group_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('permission', sa.String(length=48), nullable=False),
    sa.Column('effect', sa.String(length=8), nullable=False),
    sa.ForeignKeyConstraint(['group_id'], ['access_groups.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_access_grants_group_id'), 'access_grants', ['group_id'], unique=False)
    op.create_index(op.f('ix_access_grants_user_id'), 'access_grants', ['user_id'], unique=False)
    op.create_table('access_group_members',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('group_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['group_id'], ['access_groups.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('group_id', 'user_id', name='uq_access_member')
    )
    op.create_index(op.f('ix_access_group_members_group_id'), 'access_group_members', ['group_id'], unique=False)
    op.create_index(op.f('ix_access_group_members_user_id'), 'access_group_members', ['user_id'], unique=False)
    op.create_table('audit_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.Column('actor_id', sa.Integer(), nullable=True),
    sa.Column('actor_name', sa.String(length=120), nullable=False),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('target', sa.String(length=200), nullable=False),
    sa.Column('payload_json', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_log_ts'), 'audit_log', ['ts'], unique=False)
    op.create_table('bank_adjustments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=False),
    sa.Column('hours', sa.Float(), nullable=False),
    sa.Column('effective_date', sa.Date(), nullable=False),
    sa.Column('reason_code', sa.String(length=32), nullable=False),
    sa.Column('note', sa.String(length=255), nullable=False),
    sa.Column('author_id', sa.Integer(), nullable=True),
    sa.Column('author_name', sa.String(length=120), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bank_adjustments_employee_id'), 'bank_adjustments', ['employee_id'], unique=False)
    op.create_table('cars',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('number', sa.String(length=40), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('location', sa.String(length=160), nullable=False),
    sa.Column('charge', sa.String(length=16), nullable=False),
    sa.Column('on_charge', sa.Boolean(), nullable=False),
    sa.Column('canopy', sa.Boolean(), nullable=False),
    sa.Column('condition', sa.String(length=16), nullable=False),
    sa.Column('trash', sa.Boolean(), nullable=False),
    sa.Column('clean', sa.Boolean(), nullable=False),
    sa.Column('has_key', sa.Boolean(), nullable=False),
    sa.Column('holder_user_id', sa.Integer(), nullable=True),
    sa.Column('holder_name', sa.String(length=120), nullable=False),
    sa.Column('assigned_to', sa.Integer(), nullable=True),
    sa.Column('note', sa.String(length=255), nullable=False),
    sa.Column('last_checked_at', sa.DateTime(), nullable=True),
    sa.Column('last_taken_at', sa.DateTime(), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['assigned_to'], ['employees.id'], ),
    sa.ForeignKeyConstraint(['holder_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cars_number'), 'cars', ['number'], unique=True)
    op.create_index('ux_cars_assigned_to', 'cars', ['assigned_to'], unique=True, postgresql_where=sa.text('assigned_to IS NOT NULL'))
    op.create_index('ux_cars_holder_user_id', 'cars', ['holder_user_id'], unique=True, postgresql_where=sa.text('holder_user_id IS NOT NULL'))
    op.create_table('double_pay_days',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('scope', sa.String(length=16), nullable=False),
    sa.Column('note', sa.String(length=255), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_double_pay_days_date'), 'double_pay_days', ['date'], unique=True)
    op.create_table('employment_periods',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('note', sa.String(length=255), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_employment_periods_employee_id'), 'employment_periods', ['employee_id'], unique=False)
    op.create_table('night_area_sections',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('report_id', sa.Integer(), nullable=False),
    sa.Column('area_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('category', sa.String(length=80), nullable=False),
    sa.Column('zone_id', sa.Integer(), nullable=True),
    sa.Column('zone_name', sa.String(length=160), nullable=False),
    sa.Column('snapshot_json', sa.Text(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('taken_by', sa.Integer(), nullable=True),
    sa.Column('taken_by_name', sa.String(length=120), nullable=False),
    sa.Column('taken_at', sa.DateTime(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('closed_at', sa.DateTime(), nullable=True),
    sa.Column('closed_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['area_id'], ['night_areas.id'], ),
    sa.ForeignKeyConstraint(['closed_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['report_id'], ['night_reports.id'], ),
    sa.ForeignKeyConstraint(['taken_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['zone_id'], ['night_zones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('report_id', 'area_id', name='uq_night_section_area')
    )
    op.create_index(op.f('ix_night_area_sections_report_id'), 'night_area_sections', ['report_id'], unique=False)
    op.create_index('ix_night_area_sections_zone', 'night_area_sections', ['zone_id'], unique=False)
    op.create_table('notify_dispatches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('domain', sa.String(length=32), nullable=False),
    sa.Column('ref_id', sa.Integer(), nullable=False),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.Column('actor_user_id', sa.Integer(), nullable=True),
    sa.Column('actor_name', sa.String(length=120), nullable=False),
    sa.Column('recipient_id', sa.Integer(), nullable=True),
    sa.Column('recipient_name', sa.String(length=160), nullable=False),
    sa.Column('channel', sa.String(length=16), nullable=False),
    sa.Column('target', sa.String(length=200), nullable=False),
    sa.Column('subject', sa.String(length=200), nullable=False),
    sa.Column('cc_json', sa.Text(), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('items_json', sa.Text(), nullable=False),
    sa.Column('media_json', sa.Text(), nullable=False),
    sa.Column('media_count', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('sending_at', sa.DateTime(), nullable=True),
    sa.Column('error', sa.Text(), nullable=False),
    sa.Column('external_id', sa.String(length=120), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['recipient_id'], ['responsibility_services.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notify_dispatches_domain'), 'notify_dispatches', ['domain'], unique=False)
    op.create_index(op.f('ix_notify_dispatches_recipient_id'), 'notify_dispatches', ['recipient_id'], unique=False)
    op.create_index(op.f('ix_notify_dispatches_ref_id'), 'notify_dispatches', ['ref_id'], unique=False)
    op.create_index(op.f('ix_notify_dispatches_ts'), 'notify_dispatches', ['ts'], unique=False)
    op.create_table('photos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('ref_id', sa.Integer(), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('path', sa.String(length=400), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.Column('media_type', sa.String(length=8), nullable=False),
    sa.Column('uploaded_by', sa.Integer(), nullable=True),
    sa.Column('uploaded_by_name', sa.String(length=120), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_photos_kind'), 'photos', ['kind'], unique=False)
    op.create_index('ix_photos_kind_ref', 'photos', ['kind', 'ref_id'], unique=False)
    op.create_index(op.f('ix_photos_ref_id'), 'photos', ['ref_id'], unique=False)
    op.create_table('punches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=False),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.Column('kind', sa.String(length=4), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('note', sa.String(length=255), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_punches_emp_ts', 'punches', ['employee_id', 'ts'], unique=False)
    op.create_index(op.f('ix_punches_employee_id'), 'punches', ['employee_id'], unique=False)
    op.create_index(op.f('ix_punches_ts'), 'punches', ['ts'], unique=False)
    op.create_table('schedule_absences',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=False),
    sa.Column('start_utc', sa.DateTime(), nullable=False),
    sa.Column('end_utc', sa.DateTime(), nullable=False),
    sa.Column('kind_id', sa.Integer(), nullable=True),
    sa.Column('note', sa.String(length=255), nullable=False),
    sa.Column('doc_type', sa.String(length=40), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
    sa.ForeignKeyConstraint(['kind_id'], ['shift_types.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_sched_abs_emp_start', 'schedule_absences', ['employee_id', 'start_utc'], unique=False)
    op.create_index('ix_sched_abs_start', 'schedule_absences', ['start_utc'], unique=False)
    op.create_index(op.f('ix_schedule_absences_employee_id'), 'schedule_absences', ['employee_id'], unique=False)
    op.create_table('schedule_shifts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('start_utc', sa.DateTime(), nullable=False),
    sa.Column('end_utc', sa.DateTime(), nullable=False),
    sa.Column('source', sa.String(length=10), nullable=False),
    sa.Column('shift_type_id', sa.Integer(), nullable=True),
    sa.Column('note', sa.String(length=255), nullable=False),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
    sa.ForeignKeyConstraint(['shift_type_id'], ['shift_types.id'], ),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_sched_shifts_emp_date', 'schedule_shifts', ['employee_id', 'date'], unique=False)
    op.create_index('ix_sched_shifts_start', 'schedule_shifts', ['start_utc'], unique=False)
    op.create_index(op.f('ix_schedule_shifts_date'), 'schedule_shifts', ['date'], unique=False)
    op.create_index(op.f('ix_schedule_shifts_employee_id'), 'schedule_shifts', ['employee_id'], unique=False)
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
    op.create_table('stays_coverage_guests',
    sa.Column('coverage_id', sa.Integer(), nullable=False),
    sa.Column('guest_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['coverage_id'], ['stays_coverage.id'], ),
    sa.ForeignKeyConstraint(['guest_id'], ['stays_guests.id'], ),
    sa.PrimaryKeyConstraint('coverage_id', 'guest_id')
    )
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
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['base_version_id'], ['stays_fund_versions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('uq_stays_fund_one_draft', 'stays_fund_versions', ['status'], unique=True, postgresql_where=sa.text("status = 'draft'"))
    op.create_index('uq_stays_fund_published_from', 'stays_fund_versions', ['valid_from'], unique=True, postgresql_where=sa.text("status = 'published'"))
    op.create_table('stays_guest_links',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('guest_a_id', sa.Integer(), nullable=False),
    sa.Column('guest_b_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('former', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['guest_a_id'], ['stays_guests.id'], ),
    sa.ForeignKeyConstraint(['guest_b_id'], ['stays_guests.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('guest_a_id', 'guest_b_id', 'kind', name='uq_stays_guest_link')
    )
    op.create_index(op.f('ix_stays_guest_links_guest_a_id'), 'stays_guest_links', ['guest_a_id'], unique=False)
    op.create_index(op.f('ix_stays_guest_links_guest_b_id'), 'stays_guest_links', ['guest_b_id'], unique=False)
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
    op.create_index(op.f('ix_stays_guest_prefs_guest_id'), 'stays_guest_prefs', ['guest_id'], unique=False)
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
    op.create_index(op.f('ix_stays_occupants_guest_id'), 'stays_occupants', ['guest_id'], unique=False)
    op.create_index(op.f('ix_stays_occupants_reservation_id'), 'stays_occupants', ['reservation_id'], unique=False)
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
    sa.CheckConstraint("end_half IN ('AM', 'PM')", name='ck_stays_ooo_end_half'),
    sa.CheckConstraint("start_half IN ('AM', 'PM')", name='ck_stays_ooo_start_half'),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['unit_id'], ['stays_units.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_stays_ooo_unit_start', 'stays_ooo', ['unit_id', 'start'], unique=False)
    op.create_table('tabel_days',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('code', sa.String(length=12), nullable=False),
    sa.Column('plan_minutes', sa.Integer(), nullable=False),
    sa.Column('note', sa.String(length=255), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('employee_id', 'date', name='uq_tabel_emp_date')
    )
    op.create_index(op.f('ix_tabel_days_date'), 'tabel_days', ['date'], unique=False)
    op.create_index(op.f('ix_tabel_days_employee_id'), 'tabel_days', ['employee_id'], unique=False)
    op.create_table('vip_double_pay',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('note', sa.String(length=255), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_by_name', sa.String(length=120), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_vip_double_pay_employee_id'), 'vip_double_pay', ['employee_id'], unique=False)
    op.create_table('car_history',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('car_id', sa.Integer(), nullable=False),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.Column('action', sa.String(length=24), nullable=False),
    sa.Column('actor_user_id', sa.Integer(), nullable=True),
    sa.Column('actor_name', sa.String(length=120), nullable=False),
    sa.Column('person', sa.String(length=120), nullable=False),
    sa.Column('with_key', sa.Boolean(), nullable=True),
    sa.Column('location', sa.String(length=160), nullable=False),
    sa.Column('details_json', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['car_id'], ['cars.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_car_history_car_id'), 'car_history', ['car_id'], unique=False)
    op.create_index('ix_car_history_car_ts', 'car_history', ['car_id', 'ts'], unique=False)
    op.create_table('car_night_checks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('report_id', sa.Integer(), nullable=False),
    sa.Column('car_id', sa.Integer(), nullable=False),
    sa.Column('car_number', sa.String(length=40), nullable=False),
    sa.Column('checker_user_id', sa.Integer(), nullable=True),
    sa.Column('checker_name', sa.String(length=120), nullable=False),
    sa.Column('checked_at', sa.DateTime(), nullable=False),
    sa.Column('found', sa.Boolean(), nullable=False),
    sa.Column('found_location', sa.String(length=160), nullable=False),
    sa.Column('location', sa.String(length=160), nullable=False),
    sa.Column('moved', sa.Boolean(), nullable=False),
    sa.Column('canopy', sa.Boolean(), nullable=False),
    sa.Column('charge', sa.String(length=16), nullable=False),
    sa.Column('on_charge', sa.Boolean(), nullable=False),
    sa.Column('condition', sa.String(length=8), nullable=False),
    sa.Column('trash', sa.Boolean(), nullable=False),
    sa.Column('clean', sa.Boolean(), nullable=False),
    sa.Column('comment', sa.Text(), nullable=False),
    sa.ForeignKeyConstraint(['car_id'], ['cars.id'], ),
    sa.ForeignKeyConstraint(['checker_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['report_id'], ['night_reports.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_car_night_checks_car_id'), 'car_night_checks', ['car_id'], unique=False)
    op.create_index(op.f('ix_car_night_checks_report_id'), 'car_night_checks', ['report_id'], unique=False)
    op.create_table('night_check_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('section_id', sa.Integer(), nullable=False),
    sa.Column('item_id', sa.Integer(), nullable=True),
    sa.Column('zone_item_id', sa.Integer(), nullable=True),
    sa.Column('text', sa.String(length=300), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('service_id', sa.Integer(), nullable=True),
    sa.Column('service_name', sa.String(length=160), nullable=False),
    sa.Column('answer', sa.String(length=8), nullable=False),
    sa.Column('comment', sa.Text(), nullable=False),
    sa.Column('answered_by', sa.Integer(), nullable=True),
    sa.Column('answered_by_name', sa.String(length=120), nullable=False),
    sa.Column('answered_at', sa.DateTime(), nullable=True),
    sa.Column('dispatch_id', sa.Integer(), nullable=True),
    sa.Column('dispatched_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['answered_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['dispatch_id'], ['notify_dispatches.id'], ),
    sa.ForeignKeyConstraint(['item_id'], ['checklist_items.id'], ),
    sa.ForeignKeyConstraint(['section_id'], ['night_area_sections.id'], ),
    sa.ForeignKeyConstraint(['service_id'], ['responsibility_services.id'], ),
    sa.ForeignKeyConstraint(['zone_item_id'], ['zone_checklist_items.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_night_check_items_section_id'), 'night_check_items', ['section_id'], unique=False)
    op.create_index(op.f('ix_night_check_items_service_id'), 'night_check_items', ['service_id'], unique=False)
    op.create_index('ix_night_check_items_zone_item', 'night_check_items', ['zone_item_id'], unique=False)
    op.create_table('night_interceptions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('report_id', sa.Integer(), nullable=False),
    sa.Column('section_id', sa.Integer(), nullable=False),
    sa.Column('from_user_id', sa.Integer(), nullable=True),
    sa.Column('from_user_name', sa.String(length=120), nullable=False),
    sa.Column('to_user_id', sa.Integer(), nullable=True),
    sa.Column('to_user_name', sa.String(length=120), nullable=False),
    sa.Column('ts', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['from_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['report_id'], ['night_reports.id'], ),
    sa.ForeignKeyConstraint(['section_id'], ['night_area_sections.id'], ),
    sa.ForeignKeyConstraint(['to_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_night_interceptions_report_id'), 'night_interceptions', ['report_id'], unique=False)
    op.create_index(op.f('ix_night_interceptions_section_id'), 'night_interceptions', ['section_id'], unique=False)
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
    op.create_table('stays_category_states',
    sa.Column('version_id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=16), nullable=False),
    sa.Column('title', sa.String(length=120), nullable=False),
    sa.Column('kind_id', sa.Integer(), nullable=False),
    sa.Column('weight', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('escorted', sa.Boolean(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['stays_categories.id'], ),
    sa.ForeignKeyConstraint(['kind_id'], ['stays_category_kinds.id'], ),
    sa.ForeignKeyConstraint(['version_id'], ['stays_fund_versions.id'], ),
    sa.PrimaryKeyConstraint('version_id', 'category_id'),
    sa.UniqueConstraint('version_id', 'code', name='uq_stays_cat_state_code')
    )
    op.create_table('stays_group_states',
    sa.Column('version_id', sa.Integer(), nullable=False),
    sa.Column('group_id', sa.Integer(), nullable=False),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('title', sa.String(length=120), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('escorted', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['group_id'], ['stays_fund_groups.id'], ),
    sa.ForeignKeyConstraint(['parent_id'], ['stays_fund_groups.id'], ),
    sa.ForeignKeyConstraint(['version_id', 'parent_id'], ['stays_group_states.version_id', 'stays_group_states.group_id'], ),
    sa.ForeignKeyConstraint(['version_id'], ['stays_fund_versions.id'], ),
    sa.PrimaryKeyConstraint('version_id', 'group_id')
    )
    op.create_table('stays_unit_lineage',
    sa.Column('unit_id', sa.Integer(), nullable=False),
    sa.Column('predecessor_id', sa.Integer(), nullable=False),
    sa.Column('version_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['predecessor_id'], ['stays_units.id'], ),
    sa.ForeignKeyConstraint(['unit_id'], ['stays_units.id'], ),
    sa.ForeignKeyConstraint(['version_id'], ['stays_fund_versions.id'], ),
    sa.PrimaryKeyConstraint('unit_id', 'predecessor_id')
    )
    op.create_table('stays_unit_states',
    sa.Column('version_id', sa.Integer(), nullable=False),
    sa.Column('unit_id', sa.Integer(), nullable=False),
    sa.Column('label', sa.String(length=40), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('group_id', sa.Integer(), nullable=True),
    sa.Column('floor', sa.String(length=8), nullable=False),
    sa.ForeignKeyConstraint(['unit_id'], ['stays_units.id'], ),
    sa.ForeignKeyConstraint(['version_id', 'category_id'], ['stays_category_states.version_id', 'stays_category_states.category_id'], ),
    sa.ForeignKeyConstraint(['version_id', 'group_id'], ['stays_group_states.version_id', 'stays_group_states.group_id'], ),
    sa.ForeignKeyConstraint(['version_id'], ['stays_fund_versions.id'], ),
    sa.PrimaryKeyConstraint('version_id', 'unit_id'),
    sa.UniqueConstraint('version_id', 'label', name='uq_stays_unit_state_label')
    )
    op.create_table('stays_unit_state_flags',
    sa.Column('version_id', sa.Integer(), nullable=False),
    sa.Column('unit_id', sa.Integer(), nullable=False),
    sa.Column('flag_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['flag_id'], ['stays_unit_flags.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['version_id', 'unit_id'], ['stays_unit_states.version_id', 'stays_unit_states.unit_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('version_id', 'unit_id', 'flag_id')
    )
    op.create_index('ix_stays_unit_state_flags_version_flag', 'stays_unit_state_flags', ['version_id', 'flag_id'], unique=False)
    _reference_rows()


def _reference_rows() -> None:
    roles = sa.table("roles", sa.column("code"), sa.column("title"), sa.column("rank"),
                     sa.column("max_assignable_rank"), sa.column("builtin"))
    op.bulk_insert(roles, [
        {"code": "admin", "title": "Администратор", "rank": 100, "max_assignable_rank": 100, "builtin": True},
        {"code": "manager", "title": "Менеджер", "rank": 80, "max_assignable_rank": 80, "builtin": True},
        {"code": "supervisor", "title": "Старший / супервайзер", "rank": 60, "max_assignable_rank": 10,
         "builtin": True},
        {"code": "employee", "title": "Сотрудник", "rank": 10, "max_assignable_rank": -1, "builtin": True},
        # уровень 20: выше сотрудника — роли назначает менеджер, а не старший (max_assignable 10)
        {"code": "mgmt_view", "title": "Руководство: только просмотр", "rank": 20, "max_assignable_rank": -1,
         "builtin": False},
        {"code": "occupancy", "title": "Загрузка без гостей", "rank": 20, "max_assignable_rank": -1,
         "builtin": False},
    ])
    grants = sa.table("access_grants", sa.column("role"), sa.column("permission"), sa.column("effect"))
    op.bulk_insert(grants, [
        {"role": "mgmt_view", "permission": "stays.view", "effect": "allow"},
        {"role": "mgmt_view", "permission": "stays.guests", "effect": "allow"},
        {"role": "occupancy", "permission": "stays.occupancy", "effect": "allow"},
    ])
    op.bulk_insert(sa.table("stays_settings", sa.column("id"), sa.column("daily_limit"),
                            sa.column("replacement_codes"), sa.column("special_factor")),
                   [{"id": 1, "daily_limit": 8, "replacement_codes": "ОТ,ДО,Б,ОВ,К", "special_factor": 2}])
    now = dt.datetime.now()
    op.bulk_insert(sa.table("stays_fund_versions", sa.column("valid_from"), sa.column("status"), sa.column("rev"),
                            sa.column("note"), sa.column("created_at"), sa.column("published_at")),
                   [{"valid_from": dt.date(2000, 1, 1), "status": "published", "rev": 1, "note": "Исходный фонд",
                     "created_at": now, "published_at": now}])


def downgrade() -> None:
    op.drop_index('ix_stays_unit_state_flags_version_flag', table_name='stays_unit_state_flags')
    op.drop_table('stays_unit_state_flags')
    op.drop_table('stays_unit_states')
    op.drop_table('stays_unit_lineage')
    op.drop_table('stays_group_states')
    op.drop_table('stays_category_states')
    op.drop_table('stays_block_nights')
    op.drop_index(op.f('ix_night_interceptions_section_id'), table_name='night_interceptions')
    op.drop_index(op.f('ix_night_interceptions_report_id'), table_name='night_interceptions')
    op.drop_table('night_interceptions')
    op.drop_index('ix_night_check_items_zone_item', table_name='night_check_items')
    op.drop_index(op.f('ix_night_check_items_service_id'), table_name='night_check_items')
    op.drop_index(op.f('ix_night_check_items_section_id'), table_name='night_check_items')
    op.drop_table('night_check_items')
    op.drop_index(op.f('ix_car_night_checks_report_id'), table_name='car_night_checks')
    op.drop_index(op.f('ix_car_night_checks_car_id'), table_name='car_night_checks')
    op.drop_table('car_night_checks')
    op.drop_index('ix_car_history_car_ts', table_name='car_history')
    op.drop_index(op.f('ix_car_history_car_id'), table_name='car_history')
    op.drop_table('car_history')
    op.drop_index(op.f('ix_vip_double_pay_employee_id'), table_name='vip_double_pay')
    op.drop_table('vip_double_pay')
    op.drop_index(op.f('ix_tabel_days_employee_id'), table_name='tabel_days')
    op.drop_index(op.f('ix_tabel_days_date'), table_name='tabel_days')
    op.drop_table('tabel_days')
    op.drop_index('ix_stays_ooo_unit_start', table_name='stays_ooo')
    op.drop_table('stays_ooo')
    op.drop_index(op.f('ix_stays_occupants_reservation_id'), table_name='stays_occupants')
    op.drop_index(op.f('ix_stays_occupants_guest_id'), table_name='stays_occupants')
    op.drop_table('stays_occupants')
    op.drop_index(op.f('ix_stays_guest_prefs_guest_id'), table_name='stays_guest_prefs')
    op.drop_table('stays_guest_prefs')
    op.drop_index(op.f('ix_stays_guest_links_guest_b_id'), table_name='stays_guest_links')
    op.drop_index(op.f('ix_stays_guest_links_guest_a_id'), table_name='stays_guest_links')
    op.drop_table('stays_guest_links')
    op.drop_index('uq_stays_fund_published_from', table_name='stays_fund_versions', postgresql_where=sa.text("status = 'published'"))
    op.drop_index('uq_stays_fund_one_draft', table_name='stays_fund_versions', postgresql_where=sa.text("status = 'draft'"))
    op.drop_table('stays_fund_versions')
    op.drop_table('stays_coverage_guests')
    op.drop_table('stays_blocks')
    op.drop_index(op.f('ix_schedule_shifts_employee_id'), table_name='schedule_shifts')
    op.drop_index(op.f('ix_schedule_shifts_date'), table_name='schedule_shifts')
    op.drop_index('ix_sched_shifts_start', table_name='schedule_shifts')
    op.drop_index('ix_sched_shifts_emp_date', table_name='schedule_shifts')
    op.drop_table('schedule_shifts')
    op.drop_index(op.f('ix_schedule_absences_employee_id'), table_name='schedule_absences')
    op.drop_index('ix_sched_abs_start', table_name='schedule_absences')
    op.drop_index('ix_sched_abs_emp_start', table_name='schedule_absences')
    op.drop_table('schedule_absences')
    op.drop_index(op.f('ix_punches_ts'), table_name='punches')
    op.drop_index(op.f('ix_punches_employee_id'), table_name='punches')
    op.drop_index('ix_punches_emp_ts', table_name='punches')
    op.drop_table('punches')
    op.drop_index(op.f('ix_photos_ref_id'), table_name='photos')
    op.drop_index('ix_photos_kind_ref', table_name='photos')
    op.drop_index(op.f('ix_photos_kind'), table_name='photos')
    op.drop_table('photos')
    op.drop_index(op.f('ix_notify_dispatches_ts'), table_name='notify_dispatches')
    op.drop_index(op.f('ix_notify_dispatches_ref_id'), table_name='notify_dispatches')
    op.drop_index(op.f('ix_notify_dispatches_recipient_id'), table_name='notify_dispatches')
    op.drop_index(op.f('ix_notify_dispatches_domain'), table_name='notify_dispatches')
    op.drop_table('notify_dispatches')
    op.drop_index('ix_night_area_sections_zone', table_name='night_area_sections')
    op.drop_index(op.f('ix_night_area_sections_report_id'), table_name='night_area_sections')
    op.drop_table('night_area_sections')
    op.drop_index(op.f('ix_employment_periods_employee_id'), table_name='employment_periods')
    op.drop_table('employment_periods')
    op.drop_index(op.f('ix_double_pay_days_date'), table_name='double_pay_days')
    op.drop_table('double_pay_days')
    op.drop_index('ux_cars_holder_user_id', table_name='cars', postgresql_where=sa.text('holder_user_id IS NOT NULL'))
    op.drop_index('ux_cars_assigned_to', table_name='cars', postgresql_where=sa.text('assigned_to IS NOT NULL'))
    op.drop_index(op.f('ix_cars_number'), table_name='cars')
    op.drop_table('cars')
    op.drop_index(op.f('ix_bank_adjustments_employee_id'), table_name='bank_adjustments')
    op.drop_table('bank_adjustments')
    op.drop_index(op.f('ix_audit_log_ts'), table_name='audit_log')
    op.drop_table('audit_log')
    op.drop_index(op.f('ix_access_group_members_user_id'), table_name='access_group_members')
    op.drop_index(op.f('ix_access_group_members_group_id'), table_name='access_group_members')
    op.drop_table('access_group_members')
    op.drop_index(op.f('ix_access_grants_user_id'), table_name='access_grants')
    op.drop_index(op.f('ix_access_grants_group_id'), table_name='access_grants')
    op.drop_table('access_grants')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_table('users')
    op.drop_table('stays_moves')
    op.drop_index(op.f('ix_stays_logistics_reservation_id'), table_name='stays_logistics')
    op.drop_table('stays_logistics')
    op.drop_index(op.f('ix_stays_guests_created_by_employee_id'), table_name='stays_guests')
    op.drop_table('stays_guests')
    op.drop_table('stays_escorts')
    op.drop_index(op.f('ix_stays_coverage_reservation_id'), table_name='stays_coverage')
    op.drop_index('ix_stays_coverage_emp_day', table_name='stays_coverage')
    op.drop_index(op.f('ix_stays_coverage_day'), table_name='stays_coverage')
    op.drop_table('stays_coverage')
    op.drop_index(op.f('ix_stays_companions_reservation_id'), table_name='stays_companions')
    op.drop_table('stays_companions')
    op.drop_index(op.f('ix_stays_assignments_unit_id'), table_name='stays_assignments')
    op.drop_table('stays_assignments')
    op.drop_index(op.f('ix_position_history_employee_id'), table_name='position_history')
    op.drop_table('position_history')
    op.drop_index(op.f('ix_period_closings_employee_id'), table_name='period_closings')
    op.drop_table('period_closings')
    op.drop_index(op.f('ix_emergency_contacts_employee_id'), table_name='emergency_contacts')
    op.drop_table('emergency_contacts')
    op.drop_index(op.f('ix_deferred_carry_period_start'), table_name='deferred_carry')
    op.drop_index(op.f('ix_deferred_carry_employee_id'), table_name='deferred_carry')
    op.drop_table('deferred_carry')
    op.drop_index(op.f('ix_day_modifiers_period_start'), table_name='day_modifiers')
    op.drop_index(op.f('ix_day_modifiers_date'), table_name='day_modifiers')
    op.drop_table('day_modifiers')
    op.drop_index(op.f('ix_checklist_overrides_zone_item_id'), table_name='checklist_overrides')
    op.drop_index(op.f('ix_checklist_overrides_area_id'), table_name='checklist_overrides')
    op.drop_table('checklist_overrides')
    op.drop_index(op.f('ix_checklist_items_service_id'), table_name='checklist_items')
    op.drop_index(op.f('ix_checklist_items_area_id'), table_name='checklist_items')
    op.drop_table('checklist_items')
    op.drop_index(op.f('ix_block_assignments_employee_id'), table_name='block_assignments')
    op.drop_table('block_assignments')
    op.drop_index(op.f('ix_zone_checklist_items_zone_id'), table_name='zone_checklist_items')
    op.drop_index(op.f('ix_zone_checklist_items_service_id'), table_name='zone_checklist_items')
    op.drop_table('zone_checklist_items')
    op.drop_index(op.f('ix_stays_reservations_number'), table_name='stays_reservations')
    op.drop_index(op.f('ix_stays_reservations_group_id'), table_name='stays_reservations')
    op.drop_index('ix_stays_res_dates', table_name='stays_reservations')
    op.drop_table('stays_reservations')
    op.drop_index(op.f('ix_shift_revisions_shift_type_id'), table_name='shift_revisions')
    op.drop_table('shift_revisions')
    op.drop_index(op.f('ix_night_areas_zone_id'), table_name='night_areas')
    op.drop_table('night_areas')
    op.drop_table('employees')
    op.drop_table('subdivisions')
    op.drop_table('stays_vip_codes')
    op.drop_table('stays_units')
    op.drop_table('stays_unit_flags')
    op.drop_table('stays_settings')
    op.drop_table('stays_labels')
    op.drop_table('stays_groups')
    op.drop_table('stays_fund_groups')
    op.drop_table('stays_fields')
    op.drop_table('stays_category_kinds')
    op.drop_table('stays_categories')
    op.drop_table('statement_kinds')
    op.drop_table('shift_types')
    op.drop_table('settings')
    op.drop_table('roles')
    op.drop_table('responsibility_services')
    op.drop_index(op.f('ix_notify_templates_domain'), table_name='notify_templates')
    op.drop_table('notify_templates')
    op.drop_index(op.f('ix_notify_chats_chat_id'), table_name='notify_chats')
    op.drop_table('notify_chats')
    op.drop_table('night_zones')
    op.drop_index(op.f('ix_night_reports_date'), table_name='night_reports')
    op.drop_table('night_reports')
    op.drop_index(op.f('ix_login_attempts_ts'), table_name='login_attempts')
    op.drop_index(op.f('ix_login_attempts_key'), table_name='login_attempts')
    op.drop_table('login_attempts')
    op.drop_index(op.f('ix_engine_settings_versions_valid_from'), table_name='engine_settings_versions')
    op.drop_table('engine_settings_versions')
    op.drop_table('departments')
    op.drop_table('car_locations')
    op.drop_table('access_groups')
