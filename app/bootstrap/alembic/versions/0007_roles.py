"""roles: роли как данные (ADR-0011) — встроенные четыре и свои.

Встроенные роли заводятся здесь же: без них не работает иерархия can_manage_user. Права
ролей остаются грантами access_grants(role=…) поверх прав по умолчанию из манифестов —
настройки заказчика переносить не нужно.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | None = None
depends_on: str | None = None

# снимок core/roles.BUILTIN_ROLES на 22.10.2026: ревизия не зависит от будущих правок кода
BUILTIN = (
    ("admin", "Администратор", 100, 100),
    ("manager", "Менеджер", 80, 80),
    ("supervisor", "Старший / супервайзер", 60, 10),
    ("employee", "Сотрудник", 10, -1),
)


def upgrade() -> None:
    bind = op.get_bind()
    # база до Alembic штампуется 0001 после create_all текущих моделей — таблица может уже быть
    if "roles" not in sa.inspect(bind).get_table_names():
        op.create_table('roles',
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=80), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('max_assignable_rank', sa.Integer(), nullable=False),
        sa.Column('builtin', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('code')
        )
    have = {code for (code,) in bind.execute(sa.text("SELECT code FROM roles"))}
    roles = sa.table("roles", sa.column("code"), sa.column("title"), sa.column("rank"),
                     sa.column("max_assignable_rank"), sa.column("builtin"))
    op.bulk_insert(roles, [{"code": c, "title": t, "rank": r, "max_assignable_rank": m, "builtin": True}
                           for c, t, r, m in BUILTIN if c not in have])


def downgrade() -> None:
    op.drop_table('roles')
