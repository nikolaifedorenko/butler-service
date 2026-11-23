"""Уникальность блока deferred_carry по сотруднику, периоду, дню, тарифу и минутам."""
from __future__ import annotations

from alembic import op

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_constraint('uq_deferred_carry_employee_period', 'deferred_carry', type_='unique', if_exists=True)
    op.execute("""
        DELETE FROM deferred_carry a USING deferred_carry b
        WHERE a.employee_id = b.employee_id
          AND a.period_start = b.period_start
          AND a.source_day = b.source_day
          AND a.tariff = b.tariff
          AND a.minutes = b.minutes
          AND a.id > b.id
    """)
    op.create_unique_constraint('uq_deferred_carry_block', 'deferred_carry',
                                ['employee_id', 'period_start', 'source_day', 'tariff', 'minutes'])


def downgrade() -> None:
    # Старое ограничение отклонит откат, если у сотрудника несколько блоков в одном периоде.
    op.create_unique_constraint('uq_deferred_carry_employee_period', 'deferred_carry',
                                ['employee_id', 'period_start'])
    op.drop_constraint('uq_deferred_carry_block', 'deferred_carry', type_='unique')
