"""Необязательные даты начала и окончания брака."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("guests_links", sa.Column("marriage_start", sa.Date(), nullable=True))
    op.add_column("guests_links", sa.Column("marriage_end", sa.Date(), nullable=True))
    op.create_check_constraint("ck_marriage_start_spouse", "guests_links",
                               "marriage_start IS NULL OR kind = 'spouse'")
    op.create_check_constraint("ck_marriage_end", "guests_links",
                               "marriage_end IS NULL OR (kind = 'spouse' AND former AND "
                               "(marriage_start IS NULL OR marriage_end >= marriage_start))")


def downgrade() -> None:
    op.drop_constraint("ck_marriage_end", "guests_links", type_="check")
    op.drop_constraint("ck_marriage_start_spouse", "guests_links", type_="check")
    op.drop_column("guests_links", "marriage_end")
    op.drop_column("guests_links", "marriage_start")
