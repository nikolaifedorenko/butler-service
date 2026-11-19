"""Сессии в базе (ADR-0013, раздел 8): таблица user_sessions вместо подписанных cookie.

Токен сессии — случайная строка; в таблице хранится его SHA-256, отзыв — удаление записи.
Колонка users.token_version (отзыв подписанных токенов счётчиком) больше не нужна. Прежние
cookie перестают действовать (входят заново); хеши паролей PBKDF2 не переносятся — боевых
данных нет (решение владельца), пользователи создаются заново с хешами argon2id.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table('user_sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=True),
    sa.Column('impersonated', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_index(op.f('ix_user_sessions_user_id'), 'user_sessions', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_sessions_expires_at'), 'user_sessions', ['expires_at'], unique=False)
    op.drop_column('users', 'token_version')


def downgrade() -> None:
    op.add_column('users', sa.Column('token_version', sa.Integer(), nullable=False, server_default='0'))
    op.alter_column('users', 'token_version', server_default=None)
    op.drop_index(op.f('ix_user_sessions_expires_at'), table_name='user_sessions')
    op.drop_index(op.f('ix_user_sessions_user_id'), table_name='user_sessions')
    op.drop_table('user_sessions')
