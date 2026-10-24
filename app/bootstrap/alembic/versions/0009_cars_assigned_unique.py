"""cars.assigned_to: частичный unique — за сотрудником закреплено не больше одного кара.

То же правило, что для держателя (0004, CONC-01): assign_employee проверял «уже закреплён»
чтением, и параллельные запросы его обходили (рецензия аудита 22.10.2026, P1). Если в базе
уже есть сотрудник с двумя закреплёнными карами, индекс не создаётся: данные не трогаем,
в лог идёт предупреждение со списком, сервис стартует как раньше.
"""
from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision: str = '0009'
down_revision: str | None = '0008'
branch_labels: str | None = None
depends_on: str | None = None

WHERE = sa.text("assigned_to IS NOT NULL")


def upgrade() -> None:
    dups = op.get_bind().execute(sa.text(
        "SELECT assigned_to FROM cars WHERE assigned_to IS NOT NULL "
        "GROUP BY assigned_to HAVING COUNT(*) > 1")).scalars().all()
    if dups:
        # shortcut: при дублях ревизия проходит без индекса; создать вручную после снятия лишних закреплений
        logging.getLogger("uvicorn.error").warning(
            "0009: индекс ux_cars_assigned_to НЕ создан — за сотрудниками %s закреплено больше "
            "одного кара. Снимите лишние закрепления и выполните: CREATE UNIQUE INDEX "
            "ux_cars_assigned_to ON cars (assigned_to) WHERE assigned_to IS NOT NULL", dups)
        return
    op.create_index("ux_cars_assigned_to", "cars", ["assigned_to"], unique=True,
                    if_not_exists=True, sqlite_where=WHERE, postgresql_where=WHERE)


def downgrade() -> None:
    op.drop_index("ux_cars_assigned_to", table_name="cars", if_exists=True)
