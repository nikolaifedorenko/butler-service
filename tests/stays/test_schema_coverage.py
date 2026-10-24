"""Ревью этапа 1: строка покрытия ссылается на гостя, а не на запись проживающего."""
from __future__ import annotations

from sqlalchemy import inspect


def test_coverage_guests_table(db):
    insp = inspect(db.get_bind())
    names = set(insp.get_table_names())
    assert "stays_coverage_guests" in names and "stays_coverage_occupants" not in names
    cols = {c["name"] for c in insp.get_columns("stays_coverage_guests")}
    assert cols == {"coverage_id", "guest_id"}


def test_guest_search_text_not_indexed(db):
    idx = {i["name"] for i in inspect(db.get_bind()).get_indexes("stays_guests")}
    assert "ix_stays_guests_search_text" not in idx
