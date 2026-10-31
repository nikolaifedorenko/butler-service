"""stays: справочник видов категорий (спецификация 2026-10-28-stays-part1-addendum §1).

Вид категории был строкой stays_category_states.kind из четырёх значений в коде (villa,
estate, apartment, room); теперь — ссылка kind_id на справочник stays_category_kinds
(название, порядок, «раскрывать на шахматке», архив). Переноса данных нет (боевой базы нет),
но существующая база с демо-данными поднимается: если категории в версиях фонда уже есть,
справочник получает четыре прежних вида, строки переводятся в их id, колонка kind удаляется.
Пустая база справочник не получает — виды заводит демо-сид или экран «Фонд → Виды».

Откат возвращает строку kind по названию вида (вид не из четырёх прежних — «room»).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = '0012'
down_revision: str | None = '0011'
branch_labels: str | None = None
depends_on: str | None = None

# прежние значения fund.KINDS: код, название, раскрывать на шахматке (копия — ревизия не
# зависит от кода модуля)
LEGACY = (("villa", "вилла", True), ("estate", "имение", True), ("apartment", "апартаменты", True),
          ("room", "номер", False))


def upgrade() -> None:
    bind = op.get_bind()
    op.create_table('stays_category_kinds',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=40), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('expanded', sa.Boolean(), nullable=False),
        sa.Column('archived', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('title'))
    op.add_column('stays_category_states', sa.Column('kind_id', sa.Integer(), nullable=True))
    if bind.execute(sa.text("SELECT COUNT(*) FROM stays_category_states")).scalar_one():
        kinds = sa.table('stays_category_kinds', sa.column('title'), sa.column('sort_order'),
                         sa.column('expanded'), sa.column('archived'))
        op.bulk_insert(kinds, [{'title': t, 'sort_order': i * 10, 'expanded': e, 'archived': False}
                               for i, (_c, t, e) in enumerate(LEGACY)])
        ids = {t: i for i, t in bind.execute(sa.text("SELECT id, title FROM stays_category_kinds"))}
        for code, title, _e in LEGACY:
            bind.execute(sa.text("UPDATE stays_category_states SET kind_id = :k WHERE kind = :c"),
                         {'k': ids[title], 'c': code})
        bind.execute(sa.text("UPDATE stays_category_states SET kind_id = :k WHERE kind_id IS NULL"),
                     {'k': ids["номер"]})
    with op.batch_alter_table('stays_category_states') as batch_op:
        batch_op.alter_column('kind_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_stays_category_states_kind', 'stays_category_kinds', ['kind_id'], ['id'])
        batch_op.drop_column('kind')


def downgrade() -> None:
    bind = op.get_bind()
    op.add_column('stays_category_states', sa.Column('kind', sa.String(length=16), nullable=False,
                                                     server_default='room'))
    for code, title, _e in LEGACY:
        bind.execute(sa.text(
            "UPDATE stays_category_states SET kind = :c WHERE kind_id IN "
            "(SELECT id FROM stays_category_kinds WHERE title = :t)"), {'c': code, 't': title})
    with op.batch_alter_table('stays_category_states') as batch_op:
        batch_op.drop_constraint('fk_stays_category_states_kind', type_='foreignkey')
        batch_op.drop_column('kind_id')
        batch_op.alter_column('kind', server_default=None)
    op.drop_table('stays_category_kinds')
