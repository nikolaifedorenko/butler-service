"""Переходная ревизия перед введением уникальности блока в 0003.

При обновлении с 0001 очистка выполняется в 0003 по всем полям блока. В базах,
где 0002 уже применили, могло остаться ограничение на сотрудника и период.
"""
from __future__ import annotations

from alembic import op

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    op.drop_constraint('uq_deferred_carry_employee_period', 'deferred_carry', type_='unique', if_exists=True)
