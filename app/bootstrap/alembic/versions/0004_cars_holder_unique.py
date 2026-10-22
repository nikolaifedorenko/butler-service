"""cars.holder_user_id: частичный unique — у человека не больше одного кара (CONC-01).

Правило «один сотрудник — один кар» код проверял чтением, и параллельные запросы его обходили.
Если в базе уже есть держатель двух каров, индекс не создаётся: данные не трогаем, в лог
идёт предупреждение со списком, сервис стартует как раньше.
"""
from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | None = None
depends_on: str | None = None

WHERE = sa.text("holder_user_id IS NOT NULL")


def upgrade() -> None:
    dups = op.get_bind().execute(sa.text(
        "SELECT holder_user_id FROM cars WHERE holder_user_id IS NOT NULL "
        "GROUP BY holder_user_id HAVING COUNT(*) > 1")).scalars().all()
    if dups:
        # shortcut: при дублях ревизия проходит без индекса; создать вручную после возврата лишних каров
        logging.getLogger("uvicorn.error").warning(
            "0004: индекс ux_cars_holder_user_id НЕ создан — у пользователей %s больше одного кара. "
            "Оформите возврат лишних каров и выполните: CREATE UNIQUE INDEX ux_cars_holder_user_id "
            "ON cars (holder_user_id) WHERE holder_user_id IS NOT NULL", dups)
        return
    # if_not_exists: старая база без таблицы cars получает её (и индекс) от create_all до ревизий
    op.create_index("ux_cars_holder_user_id", "cars", ["holder_user_id"], unique=True,
                    if_not_exists=True, sqlite_where=WHERE, postgresql_where=WHERE)


def downgrade() -> None:
    op.drop_index("ux_cars_holder_user_id", table_name="cars", if_exists=True)
