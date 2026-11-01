"""Правила сопровождения, задача 1: справочник VIP-кодов, коэффициент «Особого гостя», ревизия 0017."""
from __future__ import annotations

import io
from decimal import Decimal

import pytest
from openpyxl import load_workbook
from sqlalchemy import delete, select

from app.modules.stays.adapters.orm import Guest, Reservation, StaysSettings, VipCode

from .helpers import API
from .test_fund_schema import iso_engine  # noqa: F401 — фикстура миграционного теста

PREFIX = "9"      # коды теста — девятка и три знака; демо-коды (03, 13, 14) начинаются иначе


def _free() -> str:
    from app.core.db import SessionLocal

    with SessionLocal() as s:
        taken = set(s.scalars(select(VipCode.code)))
    return next(c for c in (f"{PREFIX}{n:03d}" for n in range(1000)) if c not in taken)


@pytest.fixture(autouse=True)
def _clean(db):
    """Коды теста (начинаются с 9) и ссылки на них снимаются."""
    yield
    db.rollback()
    mine = select(VipCode.id).where(VipCode.code.like(PREFIX + "%"))
    for model in (Guest, Reservation):
        for row in db.scalars(select(model).where(model.vip_code_id.in_(mine))):
            row.vip_code_id = None
    db.flush()
    db.execute(delete(VipCode).where(VipCode.code.like(PREFIX + "%")))
    db.commit()


def _new(c, **body) -> dict:
    r = c.post(f"{API}/vip-codes", json={"code": _free(), "title": "Тест", **body})
    assert r.status_code == 200, r.text
    return r.json()


def _listed(c) -> dict:
    return {x["id"]: x for x in c.get(f"{API}/fund").json()["vip_codes"]}


def test_code_text_rules(manager_role_client):
    c = manager_role_client
    a = _new(c, code="9001")
    assert a["code"] == "9001"
    zero = c.post(f"{API}/vip-codes", json={"code": " 0903 "}).json()      # пробелы по краям срезаются
    assert zero["code"] == "0903"
    short = c.post(f"{API}/vip-codes", json={"code": "903"}).json()
    assert short["code"] == "903" and short["id"] != zero["id"]            # «0903» ≠ «903»
    assert c.post(f"{API}/vip-codes", json={"code": "A3"}).status_code == 422
    assert c.post(f"{API}/vip-codes", json={"code": "123456789"}).status_code == 422
    assert c.post(f"{API}/vip-codes", json={"code": ""}).status_code == 422
    assert c.post(f"{API}/vip-codes", json={"code": "1 2"}).status_code == 422
    for x in (zero, short):
        c.delete(f"{API}/vip-codes/{x['id']}")


def test_normalize_code_unit():
    from app.modules.stays.application.fund import FundError
    from app.modules.stays.application.vip_codes import normalize_code

    assert normalize_code(" 03 ") == "03" and normalize_code("3") == "3"
    for bad in ("", "A3", "123456789", "1 2", "٣"):          # пробел внутри и арабская цифра — не код
        with pytest.raises(FundError):
            normalize_code(bad)


def test_code_unique_409(manager_role_client):
    c = manager_role_client
    a = _new(c)
    assert c.post(f"{API}/vip-codes", json={"code": a["code"]}).status_code == 409
    b = _new(c)
    assert c.put(f"{API}/vip-codes/{b['id']}", json={"code": a["code"]}).status_code == 409
    assert c.put(f"{API}/vip-codes/{a['id']}", json={"code": a["code"], "title": "Новое"}).status_code == 200


def test_factor_min_0_1(manager_role_client):
    c = manager_role_client
    assert c.post(f"{API}/vip-codes", json={"code": _free(), "factor": 0.09}).status_code == 422
    assert c.post(f"{API}/vip-codes", json={"code": _free(), "factor": 0}).status_code == 422
    assert c.post(f"{API}/vip-codes", json={"code": _free(), "factor": 99.5}).status_code == 422
    ok = _new(c, factor=0.1)
    assert ok["factor"] == 0.1
    top = _new(c, factor=99, escorted=True)
    assert _listed(c)[top["id"]] == {**top, "escorted": True, "factor": 99.0}


def test_code_crud_and_fund_listing(manager_role_client, manager_client):
    c = manager_role_client
    a = _new(c, title="Простое", escorted=True, factor=1.5, sort_order=5)
    assert a == {"id": a["id"], "code": a["code"], "title": "Простое", "escorted": True, "factor": 1.5,
                 "sort_order": 5, "archived": False}
    assert c.put(f"{API}/vip-codes/{a['id']}", json={"code": a["code"], "title": "Иное"}).status_code == 200
    assert _listed(manager_client)[a["id"]]["title"] == "Иное"          # читать — и без stays.setup
    assert c.put(f"{API}/vip-codes/{a['id']}/archive", json={"archived": True}).status_code == 200
    assert _listed(c)[a["id"]]["archived"] is True                      # архивные в списке остаются
    assert c.put(f"{API}/vip-codes/999999", json={"code": "1"}).status_code == 422
    assert c.delete(f"{API}/vip-codes/{a['id']}").status_code == 200
    assert a["id"] not in _listed(c)
    assert c.delete(f"{API}/vip-codes/{a['id']}").status_code == 422
    codes = [x["code"] for x in c.get(f"{API}/fund").json()["vip_codes"]]
    order = {x["code"]: (x["sort_order"], x["code"]) for x in c.get(f"{API}/fund").json()["vip_codes"]}
    assert codes == sorted(codes, key=order.get)                        # порядок: sort_order, code


def test_archive_used_code_ok_delete_409(manager_role_client, db):
    c = manager_role_client
    used_by_guest, used_by_res, free = _new(c), _new(c), _new(c)
    g = db.scalar(select(Guest).limit(1))
    r = db.scalar(select(Reservation).limit(1))
    old = (g.vip_code_id, r.vip_code_id)
    g.vip_code_id, r.vip_code_id = used_by_guest["id"], used_by_res["id"]
    db.commit()
    try:
        for x in (used_by_guest, used_by_res):
            d = c.delete(f"{API}/vip-codes/{x['id']}")
            assert d.status_code == 409 and "архив" in d.json()["detail"]
            assert c.put(f"{API}/vip-codes/{x['id']}/archive", json={"archived": True}).status_code == 200
            assert c.put(f"{API}/vip-codes/{x['id']}/archive", json={"archived": False}).status_code == 200
        assert c.delete(f"{API}/vip-codes/{free['id']}").status_code == 200
    finally:
        g.vip_code_id, r.vip_code_id = old
        db.commit()


def test_check_selectable(manager_role_client, db):
    from app.modules.stays.application.fund import FundError
    from app.modules.stays.application.vip_codes import check_selectable

    c = manager_role_client
    live, old = _new(c), _new(c)
    c.put(f"{API}/vip-codes/{old['id']}/archive", json={"archived": True})
    db.expire_all()
    check_selectable(db, None, None)
    check_selectable(db, live["id"], None)
    check_selectable(db, old["id"], old["id"])               # архивный, уже стоящий, — можно оставить
    with pytest.raises(FundError, match="архив"):
        check_selectable(db, old["id"], None)
    with pytest.raises(FundError, match="архив"):
        check_selectable(db, old["id"], live["id"])
    with pytest.raises(FundError):
        check_selectable(db, 999999, None)


def test_codes_need_setup_perm(manager_client, employee_client, manager_role_client):
    """stays.edit (старший батлер) и батлер: чтение есть, запись — 403."""
    code = _new(manager_role_client)
    for other in (manager_client, employee_client):
        assert other.post(f"{API}/vip-codes", json={"code": _free()}).status_code == 403
        assert other.put(f"{API}/vip-codes/{code['id']}", json={"code": code["code"]}).status_code == 403
        assert other.put(f"{API}/vip-codes/{code['id']}/archive", json={"archived": True}).status_code == 403
        assert other.delete(f"{API}/vip-codes/{code['id']}").status_code == 403
    assert code["id"] in _listed(manager_role_client)


def test_codes_audited(manager_role_client, db):
    from app.core.audit import AuditLog

    code = _new(manager_role_client)
    row = db.scalars(select(AuditLog).where(AuditLog.action == "stays_vip_code",
                                            AuditLog.target == f"vip_code:{code['id']}")
                         .order_by(AuditLog.id.desc())).first()
    assert row is not None and code["code"] in row.payload_json


@pytest.fixture()
def _settings(db):
    row = db.get(StaysSettings, 1)
    saved = (row.vip_bonus, row.vvip_bonus, row.special_factor, row.daily_limit, row.replacement_codes)
    yield
    db.rollback()
    row = db.get(StaysSettings, 1)
    row.vip_bonus, row.vvip_bonus, row.special_factor, row.daily_limit, row.replacement_codes = saved
    db.commit()


def test_special_factor_default_and_save(manager_role_client, db, _settings):
    c = manager_role_client
    assert db.get(StaysSettings, 1).special_factor == Decimal("2")
    assert c.get(f"{API}/fund").json()["settings"]["special_factor"] == 2.0
    base = {"daily_limit": 8, "replacement_codes": "ОТ"}
    r = c.put(f"{API}/settings", json={**base, "special_factor": 2.5})
    assert r.status_code == 200 and r.json()["special_factor"] == 2.5
    assert c.get(f"{API}/fund").json()["settings"]["special_factor"] == 2.5
    # надбавки и коэффициент не заданы — остаются прежними
    r = c.put(f"{API}/settings", json={**base, "daily_limit": 9})
    assert r.status_code == 200
    body = r.json()
    assert (body["special_factor"], body["vip_bonus"], body["vvip_bonus"], body["daily_limit"]) == (2.5, 1.0, 2.0, 9.0)
    for bad in (0.09, 0, 99.01, -1):
        assert c.put(f"{API}/settings", json={**base, "special_factor": bad}).status_code == 422
    assert c.put(f"{API}/settings", json={**base, "special_factor": 0.1}).status_code == 200
    assert c.put(f"{API}/settings", json={**base, "special_factor": 99}).status_code == 200
    # прежний вызов с надбавками работает
    assert c.put(f"{API}/settings", json={**base, "vip_bonus": 3, "vvip_bonus": 4}).json()["vip_bonus"] == 3.0


def test_migration_copies_declined_and_level(iso_engine):  # noqa: F811
    """0016 → 0017 на данных: declined_butler → escort_mode, vip/vvip → special; новые колонки на
    месте, откат их снимает, повторный подъём снова переносит."""
    from alembic import command
    from sqlalchemy import inspect, text

    from app.bootstrap.schema_version import config

    engine = iso_engine
    command.downgrade(config(), "0016")
    try:
        assert "stays_vip_codes" not in inspect(engine).get_table_names()
        with engine.begin() as c:
            v = c.execute(text("SELECT id FROM stays_fund_versions WHERE valid_from = '2000-01-01'")).scalar_one()
            c.execute(text("INSERT INTO stays_categories (id) VALUES (9401)"))
            c.execute(text("INSERT INTO stays_category_kinds (id, title, sort_order, expanded, archived) "
                           "VALUES (9401, 'k', 1, 0, 0)"))
            c.execute(text("INSERT INTO stays_category_states (version_id, category_id, code, title, kind_id, "
                           "weight, escorted, sort_order) VALUES (:v, 9401, 'MIG17', 'M', 9401, 1, 0, 1)"), {"v": v})
            for gid, level in ((9401, "regular"), (9402, "vip"), (9403, "vvip")):
                c.execute(text("INSERT INTO stays_guests (id, last_name, first_name, middle_name, phone, email, "
                               "gender, level, preferences_json, special_dates_json, fields_json, note, source, "
                               "search_text, created_at, updated_at) VALUES (:i, 'Г', '', '', '', '', '', :l, "
                               "'{}', '[]', '{}', '', '', '', '2026-01-01', '2026-01-01')"), {"i": gid, "l": level})
            for rid, declined in ((9401, 0), (9402, 1)):
                c.execute(text("INSERT INTO stays_reservations (id, number, status, check_in, check_out, early, "
                               "late, category_id, customer, note, declined_butler, fields_json, source, version, "
                               "search_text, created_at, updated_at) VALUES (:i, '', 'confirmed', '2037-01-01', "
                               "'2037-01-02', 0, 0, 9401, '', '', :d, '{}', '', 1, '', '2026-01-01', '2026-01-01')"),
                          {"i": rid, "d": declined})
        command.upgrade(config(), "head")
        with engine.connect() as c:
            assert dict(c.execute(text("SELECT id, special FROM stays_guests WHERE id >= 9401")).all()) == {
                9401: 0, 9402: 1, 9403: 1}
            assert dict(c.execute(text("SELECT id, escort_mode FROM stays_reservations WHERE id >= 9401")).all()) == {
                9401: "rules", 9402: "declined"}
            assert c.execute(text("SELECT vip_code_id FROM stays_reservations WHERE id = 9401")).scalar_one() is None
            assert float(c.execute(text("SELECT special_factor FROM stays_settings")).scalar_one()) == 2.0
            c.execute(text("SELECT escorted FROM stays_group_states LIMIT 1")).all()
        insp = inspect(engine)
        for table, col in (("stays_guests", "special"), ("stays_reservations", "escort_mode"),
                           ("stays_settings", "special_factor"), ("stays_group_states", "escorted")):
            assert insp.get_columns(table) and not [x for x in insp.get_columns(table)
                                                    if x["name"] == col][0]["default"]      # server_default снят
        command.downgrade(config(), "0016")
        insp = inspect(engine)
        assert "stays_vip_codes" not in insp.get_table_names()
        assert not {"vip_code_id", "special"} & {x["name"] for x in insp.get_columns("stays_guests")}
        assert not {"vip_code_id", "escort_mode"} & {x["name"] for x in insp.get_columns("stays_reservations")}
        assert "special_factor" not in {x["name"] for x in insp.get_columns("stays_settings")}
        assert "escorted" not in {x["name"] for x in insp.get_columns("stays_group_states")}
    finally:
        command.upgrade(config(), "head")
    with engine.connect() as c:
        assert dict(c.execute(text("SELECT id, escort_mode FROM stays_reservations WHERE id >= 9401")).all()) == {
            9401: "rules", 9402: "declined"}


def test_reset_backs_up_vip_codes(manager_role_client, db):
    """Справочник кодов — в WIPE (стирается вместе с гостями и бронями), его копия — лист в файле копии."""
    from app.modules.stays.application import fund_reset as fr

    code = _new(manager_role_client, title="Копия", escorted=True, factor=1.5)
    db.expire_all()
    assert VipCode in fr.WIPE
    wb = load_workbook(io.BytesIO(fr.backup_bytes(db)))
    ws = wb[fr.raw_sheet_names()["stays_vip_codes"]]
    head = [x.value for x in ws[1]]
    assert head == ["id", "code", "title", "escorted", "factor", "sort_order", "archived"]
    rows = {r[0].value: [x.value for x in r] for r in ws.iter_rows(min_row=2)}
    assert rows[code["id"]][1:] == [code["code"], "Копия", 1, 1.5, 100, 0]


def test_demo_has_codes_03_13_14(tmp_path):
    """Демо на свежей базе (отдельный процесс: откаты миграций в других тестах пересоздают таблицы
    общей тестовой базы, и коды демо в ней пропадают): коды 03, 13, 14 и никакого «3»."""
    import os
    import sqlite3
    import subprocess
    import sys
    from pathlib import Path

    db = tmp_path / "demo.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}", "DEMO_SEED": "1", "NIGHT_SYNC_ENABLED": "0"}
    r = subprocess.run([sys.executable, "-m", "app.bootstrap.migrate"], env=env,
                       cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    con = sqlite3.connect(db)
    try:
        got = {c: (t, bool(e), f, bool(a)) for c, t, e, f, a in con.execute(
            "SELECT code, title, escorted, factor, archived FROM stays_vip_codes")}
    finally:
        con.close()
    assert set(got) == {"03", "13", "14"}
    assert got["03"][1] and got["13"][1] and not got["14"][1]
    assert not any(v[3] for v in got.values())
