"""stays: текст поиска гостя только по ФИО (решение 8 финального ревью части 4).

Ниже полного уровня видимости поиск гостей, шахматки, табло и «Броней» ищет только по ФИО и номеру
брони: search_text содержит телефон, почту и поля с флагом «искать» — по нему можно было бы
подобрать номер чужого гостя. Колонка name_text заполняется для всех гостей (нижний регистр Python:
SQLite lower() кириллицу не понижает); дальше её пишет модель при каждой записи профиля.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = '0020'
down_revision: str | None = '0019'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table('stays_guests') as batch_op:
        batch_op.add_column(sa.Column('name_text', sa.String(length=400), server_default='', nullable=False))
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, last_name, first_name, middle_name FROM stays_guests")).all()
    upd = sa.text("UPDATE stays_guests SET name_text = :t WHERE id = :id")
    for gid, last, first, middle in rows:
        conn.execute(upd, {"id": gid, "t": " ".join(p for p in (last, first, middle) if p).lower()[:400]})


def downgrade() -> None:
    with op.batch_alter_table('stays_guests') as batch_op:
        batch_op.drop_column('name_text')
