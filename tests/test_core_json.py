"""Колонки JSON (ADR-0013, раздел 3): в коде — словарь или список, в базе — JSONB."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select, text

from app.core.audit import AuditLog
from app.core.db import ORDER_KEY, Base, Json, OrderedJson, plain_json
from app.core.time import now


def _probe(db, payload: dict) -> AuditLog:
    row = AuditLog(actor_name="t", action="core_json_probe", target="x", payload=payload, ts=now())
    db.add(row)
    db.commit()
    return row


def _stored(db, row_id: int) -> dict:
    return db.execute(text("SELECT payload FROM audit_log WHERE id = :id"), {"id": row_id}).scalar_one()


def test_new_object_has_empty_json_values_before_flush():
    from app.modules.guests.application.catalog import Guest

    g = Guest(last_name="Проба")
    assert (g.preferences, g.special_dates, g.fields) == ({}, [], {})
    assert Guest(last_name="Вторая").preferences is not g.preferences


def test_value_changed_in_place_is_saved_when_assigned_back(db):
    row = _probe(db, {"list": [1], "nested": {"a": 1}})
    try:
        value = row.payload
        value["nested"]["a"] = 2
        value["list"].append(3)
        row.payload = value
        db.commit()
        assert _stored(db, row.id) == {"list": [1, 3], "nested": {"a": 2}}
    finally:
        db.delete(row)
        db.commit()


def test_reading_does_not_write(db, sql_counter):
    row = _probe(db, {"a": 1})
    try:
        db.expire_all()
        got = db.scalar(select(AuditLog).where(AuditLog.id == row.id))
        assert got.payload == {"a": 1}
        assert not db.is_modified(got)
        with sql_counter() as counter:
            db.commit()
        assert not any(statement.upper().startswith("UPDATE") for statement in counter["by_statement"])
    finally:
        db.delete(db.get(AuditLog, row.id))
        db.commit()


def test_text_is_stored_readable_and_searchable(db):
    row = _probe(db, {"имя": "Орлов", "n": 1})
    try:
        found = db.scalar(text("SELECT id FROM audit_log WHERE id = :id AND payload::text ILIKE '%орлов%'"),
                          {"id": row.id})
        assert found == row.id
        assert db.scalar(text("SELECT payload ->> 'имя' FROM audit_log WHERE id = :id"), {"id": row.id}) == "Орлов"
    finally:
        db.delete(row)
        db.commit()


def test_plain_json_copies_and_turns_dates_into_strings():
    source = {"day": dt.date(2026, 11, 15), "items": [{"n": 1}]}
    out = plain_json(source)
    assert out == {"day": "2026-11-15", "items": [{"n": 1}]}
    out["items"][0]["n"] = 2
    assert source["items"][0]["n"] == 1


def test_settings_document_keeps_key_order(db):
    """Порядок ключей документа и его разделов хранится явно и возвращается при чтении."""
    from app.modules.timesheet.adapters.orm import EngineSettingsVersion

    payload = {"я": 1, "b": 2, "ааа": 3, "a": {"zz": 1, "ё": 2, "b": {"y": 1, "x": 2}}}
    ver = EngineSettingsVersion(valid_from=dt.date(2099, 1, 1), payload=payload, note="core_json_probe")
    db.add(ver)
    db.commit()
    try:
        db.expire_all()
        loaded = db.get(EngineSettingsVersion, ver.id).payload
        assert list(loaded) == ["я", "b", "ааа", "a"] and ORDER_KEY not in loaded
        assert list(loaded["a"]) == ["zz", "ё", "b"]
        stored = db.execute(text("SELECT payload FROM engine_settings_versions WHERE id = :id"),
                            {"id": ver.id}).scalar_one()
        assert stored[ORDER_KEY][""] == ["я", "b", "ааа", "a"] and stored[ORDER_KEY]["a"] == ["zz", "ё", "b"]
        assert loaded == payload
    finally:
        db.delete(db.get(EngineSettingsVersion, ver.id))
        db.commit()


def test_ordered_json_reads_a_document_without_order():
    """Документ, записанный без явного порядка, читается как есть."""
    column = OrderedJson()
    assert column.process_result_value({"b": 1, "a": 2}, None) == {"b": 1, "a": 2}
    assert column.process_result_value(None, None) is None
    assert column.process_bind_param([1, 2], None) == [1, 2]


def test_reading_settings_does_not_change_stored_version(db):
    """Расчёт дополняет документ настроек своими ключами — в копии, а не в строке базы."""
    from app.modules.timesheet.adapters.sql_settings import SqlSettingsAdapter, base_version
    from app.modules.timesheet.application.months import month_period

    period = month_period(2026, 11)
    version = base_version(db, period.start)
    before = set(version.payload)
    SqlSettingsAdapter(db).load(period)
    assert set(version.payload) == before and "versions" not in version.payload
    assert not db.is_modified(version)


def test_base_cycle_is_one_jsonb_row_with_group_order(db):
    """Базовый цикл — одна строка со словарём блоков в JSONB; порядок блоков сохраняется."""
    from app.modules.timesheet.adapters.orm import BaseScheduleConfig
    from app.modules.timesheet.application.base_schedule import load_base_config, save_base_config

    before = load_base_config(db)
    try:
        groups = {"Смена 2": {"value": "Я 12"}, "Смена 1": {"value": "Я 12"}, "Пятидневка": {"off_weekdays": [5, 6]}}
        save_base_config(db, {"cycle": "3/3", "anchor": "2025-02-03", "groups": groups})
        db.commit()
        db.expire_all()
        loaded = load_base_config(db)
        assert (loaded["cycle"], loaded["anchor"]) == ("3/3", "2025-02-03")
        assert list(loaded["groups"]) == ["Смена 2", "Смена 1", "Пятидневка"] and loaded["groups"] == groups
        assert db.scalar(text("SELECT count(*) FROM base_schedule_config")) == 1
        assert db.scalar(text("SELECT count(*) FROM settings WHERE key LIKE 'base\\_%' ESCAPE '\\'")) == 0
        assert isinstance(db.get(BaseScheduleConfig, 1).groups, dict)
    finally:
        save_base_config(db, before)
        db.commit()


def test_schema_stores_json_as_jsonb(db):
    """Каждая колонка Json — jsonb; JSON в тексте и тип json не используются."""
    expected = {}
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, Json):
                expected[f"{table.name}.{column.name}"] = "jsonb"
    assert len(expected) == 19
    assert {"engine_settings_versions.payload", "base_schedule_config.groups"} <= set(expected)
    actual = dict(db.execute(text(
        "SELECT table_name || '.' || column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'public' AND data_type IN ('json', 'jsonb')")).all())
    assert actual == expected
    text_json = db.execute(text(
        "SELECT table_name || '.' || column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND column_name LIKE '%\\_json' ESCAPE '\\'")).scalars().all()
    assert text_json == []
