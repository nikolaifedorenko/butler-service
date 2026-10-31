"""stays: пол гостя и первичные семейные связи (спецификация 2026-10-28-stays-part1-addendum §3, §4).

Гость получает пол (m | f | '' — не указан), связь — признак «бывшие» (для супругов). Связь
`child` заменяется на `parent`; переноса данных нет (боевой базы нет): строки `child` удаляются.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = '0014'
down_revision: str | None = '0013'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column('stays_guests', sa.Column('gender', sa.String(length=1), nullable=False, server_default=''))
    op.add_column('stays_guest_links', sa.Column('former', sa.Boolean(), nullable=False,
                                                 server_default=sa.false()))
    with op.batch_alter_table('stays_guests') as batch_op:
        batch_op.alter_column('gender', server_default=None)
    with op.batch_alter_table('stays_guest_links') as batch_op:
        batch_op.alter_column('former', server_default=None)
    op.execute("DELETE FROM stays_guest_links WHERE kind = 'child'")


def downgrade() -> None:
    op.execute("DELETE FROM stays_guest_links WHERE kind = 'parent'")
    with op.batch_alter_table('stays_guest_links') as batch_op:
        batch_op.drop_column('former')
    with op.batch_alter_table('stays_guests') as batch_op:
        batch_op.drop_column('gender')
