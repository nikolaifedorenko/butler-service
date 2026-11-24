"""Шахматка, задача 18: выгрузка в Excel — обезличенная и полная (§8), журнал аудита."""
from __future__ import annotations

import io

from openpyxl import load_workbook
from sqlalchemy import event, select

from app.core.audit import AuditLog
from app.modules.stays.application.catalog import Logistics
from tests.stays.helpers import API, create_res, make_category, make_guest, uniq

Q = {"first": "2037-02-01", "last": "2037-02-07"}


def _setup(sup, mgr):
    cat = make_category(sup, n_units=2)
    g = make_guest(mgr, "Выгрузкин")
    res = create_res(mgr, cat, "2037-02-02", "2037-02-05", [(g["id"], "main", None, None)],
                     note="=HYPERLINK(\"http://x\")", customer="Заказчиков")
    return cat, g, res


def _cells(content: bytes) -> list[str]:
    wb = load_workbook(io.BytesIO(content))
    return [str(c.value) for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.value is not None]


def test_anon_export_has_no_guest_data(occupancy_client, manager_role_client, manager_client, db):
    cat, g, res = _setup(manager_role_client, manager_client)
    r = occupancy_client.get(f"{API}/export", params={**Q, "kind": "anon"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxml")
    cells = _cells(r.content)
    assert not any("Выгрузкин" in c or "Заказчиков" in c or res["number"] in c for c in cells)
    assert any(cat["units"][0]["label"] == c for c in cells) and "занято" in cells
    wb = load_workbook(io.BytesIO(r.content))
    assert [ws.title for ws in wb.worksheets] == ["Шахматка", "Брони", "Сводка"]
    row = db.scalars(select(AuditLog).where(AuditLog.action == "stays_export").order_by(AuditLog.id.desc())).first()
    assert row.payload == {"kind": "anon", **Q}


def test_full_export_requires_export_and_guests(manager_client, manager_role_client, occupancy_client):
    assert manager_client.get(f"{API}/export", params={**Q, "kind": "full"}).status_code == 403    # старший
    assert occupancy_client.get(f"{API}/export", params={**Q, "kind": "full"}).status_code == 403


def test_full_export_has_names_and_escapes_formulas(manager_role_client, manager_client):
    cat, g, res = _setup(manager_role_client, manager_client)
    r = manager_role_client.get(f"{API}/export", params={**Q, "kind": "full"})
    assert r.status_code == 200
    cells = _cells(r.content)
    assert any("Выгрузкин" in c for c in cells) and any(res["number"] == c for c in cells)
    assert "'=HYPERLINK(\"http://x\")" in cells and "=HYPERLINK(\"http://x\")" not in cells


def test_group_export_keeps_all_bookings_in_order(manager_role_client, manager_client, occupancy_client):
    cat = make_category(manager_role_client, n_units=1)
    label = cat["units"][0]["label"]
    group = manager_client.post(f"{API}/groups", json={"title": "Группа выгрузки"})
    assert group.status_code == 200
    group_id = group.json()["id"]
    number = uniq()
    bookings = [
        ("2037-02-03", f"{number}-B", "Иванов"),
        ("2037-02-03", f"{number}-A", "Яковлев"),
        ("2037-02-03", f"{number}-A", "Николаев"),
        ("2037-02-02", f"{number}-Z", "Петров"),
    ]
    for start, ref, name in bookings:
        guest = make_guest(manager_client, name)
        create_res(manager_client, cat, start, "2037-02-05", [(guest["id"], "main", None, None)],
                   group_id=group_id, number=ref)

    full = manager_role_client.get(f"{API}/export", params={**Q, "kind": "full"})
    assert full.status_code == 200
    wb = load_workbook(io.BytesIO(full.content))
    assert [(row[6], row[7]) for row in wb["Брони"].values if row[0] == label] == [
        (ref, name) for _, ref, name in bookings
    ]
    row = next(row for row in wb["Шахматка"].values if row[0] == label)
    overlap = "Петров\nНиколаев\nЯковлев\nИванов"
    assert row[2:7] == (None, "Петров", overlap, overlap, None)
    summary = next(row for row in wb["Сводка"].values if row[0] == cat["code"])
    assert summary[2:7] == (0, 1, 1, 1, 0)

    anon = occupancy_client.get(f"{API}/export", params={**Q, "kind": "anon"})
    assert anon.status_code == 200
    wb = load_workbook(io.BytesIO(anon.content))
    assert sum(row[0] == label for row in wb["Брони"].values) == len(bookings)
    assert wb["Брони"].max_column == 6
    row = next(row for row in wb["Шахматка"].values if row[0] == label)
    assert row[2:7] == (None, "занято", "занято ×4", "занято ×4", None)
    cells = _cells(anon.content)
    assert not any(ref in cell or name in cell for _, ref, name in bookings for cell in cells)


def test_one_day_full_export_reads_in_window_and_undated_logistics(manager_role_client, manager_client):
    cat = make_category(manager_role_client, n_units=1)
    day = "2037-03-15"
    res = create_res(manager_client, cat, "2037-03-01", "2037-04-01", logistics=[
        {"kind": "transfer", "date": "2037-03-01", "time": "07:40", "description": "Ранний трансфер"},
        {"kind": "transfer", "date": day, "time": "12:00", "description": "Трансфер сегодня"},
        {"kind": "transfer", "date": "2037-04-01", "time": "16:00", "description": "Поздний трансфер"},
        {"kind": "car", "date": None, "time": "", "description": "Машина без даты"},
    ])
    loaded = set()

    def record_logistics(row, _context):
        if row.reservation_id == res["id"]:
            loaded.add(row.description)

    event.listen(Logistics, "load", record_logistics)
    try:
        response = manager_role_client.get(f"{API}/export", params={"first": day, "last": day, "kind": "full"})
    finally:
        event.remove(Logistics, "load", record_logistics)
    assert response.status_code == 200
    wb = load_workbook(io.BytesIO(response.content))
    row = next(row for row in wb["Брони"].values if row[6] == res["number"])
    assert set(row[15].split("; ")) == {"15.03 12:00 Трансфер сегодня", "Машина без даты"}
    assert loaded == {"Трансфер сегодня", "Машина без даты"}


def test_export_window_limit(manager_role_client):
    r = manager_role_client.get(f"{API}/export", params={"first": "2037-01-01", "last": "2037-06-01", "kind": "anon"})
    assert r.status_code == 422
