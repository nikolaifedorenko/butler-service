"""notify_dispatches.sending_at: outbox рассылки (CONC-02).

Строка журнала пишется до сети: queued → sending → sent | failed. sending_at — когда
строку взяли в отправку; застрявшие в sending дольше срока (процесс упал посреди
доставки) фоновый отправщик помечает «статус неизвестен», а не шлёт повторно.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # база до Alembic штампуется 0001 и проходит ревизии заново — колонка может уже быть
    if "sending_at" in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("notify_dispatches")}:
        return
    with op.batch_alter_table('notify_dispatches', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sending_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('notify_dispatches', schema=None) as batch_op:
        batch_op.drop_column('sending_at')
