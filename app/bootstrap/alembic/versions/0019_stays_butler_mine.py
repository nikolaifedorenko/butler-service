"""stays: права батлера на профиль и бронь своих гостей (спецификация 2026-10-27-stays-butler-mine-design §3–§4).

У гостя — created_by_employee_id (батлер, заведший профиль через семейное дерево: такой гость — его
«свой»). Право stays.edit_mine делится на два: каждая строка access_grants с ним заменяется парой
stays.mine_guest_edit и stays.mine_res_edit с теми же group_id, user_id, role и effect. Откат —
обратно: одна строка stays.edit_mine на пару (по group_id, user_id, role, effect), колонка снимается.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = '0019'
down_revision: str | None = '0018'
branch_labels: str | None = None
depends_on: str | None = None

OLD = 'stays.edit_mine'
NEW = ('stays.mine_guest_edit', 'stays.mine_res_edit')
_COLS = 'group_id, user_id, role, effect'


def upgrade() -> None:
    with op.batch_alter_table('stays_guests') as batch_op:
        batch_op.add_column(sa.Column('created_by_employee_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_stays_guests_created_by', 'employees', ['created_by_employee_id'], ['id'])
        batch_op.create_index('ix_stays_guests_created_by_employee_id', ['created_by_employee_id'], unique=False)
    for perm in NEW:
        op.execute(sa.text(f"INSERT INTO access_grants ({_COLS}, permission) "
                           f"SELECT {_COLS}, :new FROM access_grants WHERE permission = :old")
                   .bindparams(new=perm, old=OLD))
    op.execute(sa.text("DELETE FROM access_grants WHERE permission = :old").bindparams(old=OLD))


def downgrade() -> None:
    # пара → одна строка; разошедшиеся после подъёма гранты (только одно из двух) тоже дают старое право
    op.execute(sa.text(f"INSERT INTO access_grants ({_COLS}, permission) "
                       f"SELECT DISTINCT {_COLS}, :old FROM access_grants WHERE permission IN (:a, :b)")
               .bindparams(old=OLD, a=NEW[0], b=NEW[1]))
    op.execute(sa.text("DELETE FROM access_grants WHERE permission IN (:a, :b)").bindparams(a=NEW[0], b=NEW[1]))
    with op.batch_alter_table('stays_guests') as batch_op:
        batch_op.drop_index('ix_stays_guests_created_by_employee_id')
        batch_op.drop_constraint('fk_stays_guests_created_by', type_='foreignkey')
        batch_op.drop_column('created_by_employee_id')
