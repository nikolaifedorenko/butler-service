from collections import Counter
from datetime import date
from io import BytesIO

import pytest
from openpyxl import load_workbook
from pypdf import PdfReader

from app.core.config import settings
from app.modules.exchange.application import chessboard
from tests.stays.helpers import API


@pytest.mark.parametrize("client_name, names, full", [
    ("occupancy_client", False, False), ("names_client", False, False),
    ("mgmt_client", False, False), ("manager_role_client", True, True),
])
def test_chessboard_workbook_retains_role_visibility(request, demo_small, client_name, names, full):
    client = request.getfixturevalue(client_name)
    response = client.get(f"{API}/board/units/export", params={
        "first": "2029-02-01", "last": "2029-02-28", "category_ids": demo_small.cat["id"],
    })
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    book = load_workbook(BytesIO(response.content))
    assert book.sheetnames == ["Шахматка", "Легенда", "Список броней"]
    sheet = book["Шахматка"]
    assert sheet.freeze_panes == "B5" and sheet.page_setup.orientation == "landscape"
    assert any(cell.comment and "\t" in cell.comment.text for row in sheet for cell in row)
    assert sum(1 for row in book["Список броней"].values if row[0]) == 6
    strings = [str(c.value) for sh in book for row in sh for c in row if c.value is not None]
    strings += [c.comment.text for row in sheet for c in row if c.comment]
    content = "\n".join(strings)
    assert (demo_small.guests[0]["last_name"] in content) == names
    assert (demo_small.res[0]["number"] in content) == names
    assert ("Заметка" in content) == full


def test_chessboard_export_pdf_from_same_workbook(manager_role_client, demo_small):
    if not settings.gotenberg_url:
        pytest.skip("GOTENBERG_URL для проверки LibreOffice")
    params = {"first": "2029-02-01", "last": "2029-02-28", "category_ids": demo_small.cat["id"]}
    path = f"{API}/board/units/export"
    xlsx = load_workbook(BytesIO(manager_role_client.get(path, params=params).content))
    response = manager_role_client.get(path, params={**params, "format": "pdf"})
    assert response.status_code == 200, response.text[:300] if response.status_code != 200 else ""
    pages = PdfReader(BytesIO(response.content)).pages
    assert len(pages) == 3
    assert all(abs(float(p.mediabox.width) - 841.89) < 1 and abs(float(p.mediabox.height) - 595.28) < 1
               for p in pages)
    assert "Легенда меток" in pages[1].extract_text()
    assert "Список броней" in pages[2].extract_text()
    comments = Counter(c.comment.text for row in xlsx["Шахматка"] for c in row if c.comment)
    pdf_comments = [ref.get_object() for ref in pages[0]["/Annots"] if ref.get_object()["/Subtype"] == "/Text"]
    assert Counter(str(a["/Contents"]) for a in pdf_comments) == comments
    assert all(not int(a["/F"]) & 4 and a["/AP"]["/N"] for a in pdf_comments)

    printable = manager_role_client.get(path, params={**params, "format": "pdf", "for_print": "true"})
    assert printable.status_code == 200
    print_pages = PdfReader(BytesIO(printable.content)).pages
    assert all(not page.get("/Annots") for page in print_pages)
    assert [page.extract_text() for page in print_pages] == [page.extract_text() for page in pages]


def test_chessboard_export_can_download_xlsx_without_pdf_service(occupancy_client, demo_small, monkeypatch):
    monkeypatch.setattr(settings, "gotenberg_url", "")
    params = {"first": "2029-02-01", "last": "2029-02-28", "category_ids": demo_small.cat["id"]}
    path = f"{API}/board/units/export"
    pdf = occupancy_client.get(path, params={**params, "format": "pdf"})
    assert pdf.status_code == 502
    assert "Можно выгрузить XLSX" in pdf.json()["detail"]
    assert occupancy_client.get(path, params=params).status_code == 200


@pytest.mark.parametrize("client_name, names", [("occupancy_client", False), ("names_client", True)])
def test_chessboard_pdf_uses_view_permissions(request, demo_small, client_name, names):
    if not settings.gotenberg_url:
        pytest.skip("GOTENBERG_URL для проверки LibreOffice")
    client = request.getfixturevalue(client_name)
    response = client.get(f"{API}/board/units/export", params={
        "first": "2029-02-01", "last": "2029-02-28", "category_ids": demo_small.cat["id"], "format": "pdf",
    })
    assert response.status_code == 200
    pages = PdfReader(BytesIO(response.content)).pages
    text = "\n".join(page.extract_text() for page in pages)
    notes = "\n".join(str(obj["/Contents"]) for page in pages for ref in page.get("/Annots", [])
                      if (obj := ref.get_object()).get("/Subtype") == "/Text")
    assert (demo_small.guests[0]["last_name"] in notes) == names
    assert (demo_small.res[0]["number"] in text + notes) == names
    assert "Заметка" not in text + notes


def test_collision_keeps_full_surname_and_one_room_label():
    first = date(2029, 2, 1)
    slot = 2 * first.toordinal()
    workbook, _ = chessboard.write(chessboard.Chessboard(
        [first, date(2029, 2, 2)], [chessboard.Room("=4003", "VEG", [
            chessboard.Band(slot + 1, slot + 2, "Константинопольский", "A9C5F4", [("Номер", 4003)]),
            chessboard.Band(slot + 2, slot + 3, "OOO", "F1B9C0", [("Причина", "Работы")]),
        ])], {"OOO": "F1B9C0"}, ["Объект", "Гость"], [["=4003", "Константинопольский"]],
    ))
    s = load_workbook(BytesIO(workbook))["Шахматка"]
    assert "A6:A7" in s.merged_cells
    assert s["A6"].data_type == "s"
    assert s["C6"].value == "Константинопольский"
    assert s["C6"].alignment.horizontal == "left" and s["C6"].comment.text == "Номер:\t4003"
    assert s["D7"].value == "OOO" and s["D7"].comment.text == "Причина:\tРаботы"
