"""deferred_carry: одна строка на пару «сотрудник + период-получатель».

Запись в deferred_carry — сначала DELETE по паре, потом INSERT (sql_closings.py);
до индекса гонка двух записей могла оставить две строки на одну пару, и чтение
переносов (sql_closings.py:145) отдавало обе — дубль попадал во вход следующего
периода дважды. Индекс закрепляет инвариант «переносов на пару — одна строка» на
уровне базы. Дубли, оставшиеся от прежних гонок, миграция схлопывает: остаётся
строка с меньшим id (переносы однотипны, потеря записи невозможна).
"""
from __future__ import annotations

from alembic import op

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM deferred_carry a USING deferred_carry b "
        "WHERE a.employee_id = b.employee_id AND a.period_start = b.period_start "
        "AND a.id > b.id")
    op.create_unique_constraint('uq_deferred_carry_employee_period', 'deferred_carry',
                                ['employee_id', 'period_start'])


def downgrade() -> None:
    op.drop_constraint('uq_deferred_carry_employee_period', 'deferred_carry', type_='unique')
