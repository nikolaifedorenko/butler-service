"""Шахматка: схема модуля (ревизия 0008) и встроенные роли модуля."""
from __future__ import annotations

from sqlalchemy import inspect, select


def test_stays_tables_created(db):
    names = set(inspect(db.get_bind()).get_table_names())
    assert {"stays_categories", "stays_units", "stays_ooo", "stays_blocks", "stays_block_nights", "stays_guest_prefs", "stays_labels", "stays_guests",
            "stays_guest_links", "stays_groups", "stays_reservations", "stays_moves",
            "stays_assignments", "stays_occupants", "stays_companions", "stays_logistics",
            "stays_escorts", "stays_coverage", "stays_coverage_guests", "stays_fields",
            "stays_settings"} <= names


def test_stays_settings_row_seeded(db):
    from app.modules.stays.adapters.orm import StaysSettings
    s = db.get(StaysSettings, 1)
    assert (float(s.vip_bonus), float(s.vvip_bonus), float(s.daily_limit)) == (1.0, 2.0, 8.0)
    assert s.replacement_codes == "ОТ,ДО,Б,ОВ,К"


def test_stays_roles_as_data(db):
    from app.core.identity import AccessGrant, Role
    from app.core.permissions import role_permissions
    roles = {r.code: r for r in db.scalars(select(Role))}
    assert roles["mgmt_view"].title == "Руководство: только просмотр"
    assert roles["occupancy"].title == "Загрузка без гостей"
    assert {"stays.view", "stays.guests"} <= role_permissions(db, "mgmt_view")
    occ = role_permissions(db, "occupancy")
    assert "stays.occupancy" in occ and "stays.view" not in occ
    assert db.scalars(select(AccessGrant).where(AccessGrant.role == "occupancy")).first()
