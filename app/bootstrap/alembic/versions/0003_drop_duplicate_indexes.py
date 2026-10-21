"""Дубли индексов от прежних шагов migrate_night_*: те же колонки, что у индексов моделей.

Старые базы получали индекс и от модели (create_all), и от шага миграции под другим
именем. Сначала гарантируем индекс модели (у таблиц, созданных до index=True, его могло
не быть), затем удаляем дубль. На новых базах дублей нет — команды ничего не меняют.
"""
from __future__ import annotations

from alembic import op

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | None = None
depends_on: str | None = None

# дубль → (индекс модели, таблица, колонка)
DUPLICATES = {
    "ix_night_sections_report": ("ix_night_area_sections_report_id", "night_area_sections", "report_id"),
    "ix_night_items_section": ("ix_night_check_items_section_id", "night_check_items", "section_id"),
    "ix_night_check_items_service": ("ix_night_check_items_service_id", "night_check_items", "service_id"),
    "ix_zone_checklist_items_service": ("ix_zone_checklist_items_service_id", "zone_checklist_items", "service_id"),
    "ix_zone_checklist_items_zone": ("ix_zone_checklist_items_zone_id", "zone_checklist_items", "zone_id"),
    "ix_checklist_overrides_area": ("ix_checklist_overrides_area_id", "checklist_overrides", "area_id"),
    "ix_checklist_overrides_zone_item": ("ix_checklist_overrides_zone_item_id", "checklist_overrides", "zone_item_id"),
}


def upgrade() -> None:
    for dup, (keep, table, column) in DUPLICATES.items():
        op.execute(f"CREATE INDEX IF NOT EXISTS {keep} ON {table} ({column})")
        op.execute(f"DROP INDEX IF EXISTS {dup}")


def downgrade() -> None:
    pass    # дубли не восстанавливаем
