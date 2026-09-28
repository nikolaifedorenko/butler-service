#!/usr/bin/env python3
"""Смоук батча 2: расширяемые виды заявлений в UI.

Сценарий: панель «Виды заявлений и шаблоны» → создать вид через модалку →
привязать к смене (API) → назначить отсутствие Соколовой → в модалке ячейки
видны кнопки печати → скачать DOCX → удалить вид (смены отвязываются) → уборка.
"""
import datetime as dt
import sys
from zoneinfo import ZoneInfo

import httpx
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OK, FAIL = 0, 0


def check(name, cond, extra=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} {extra}")


today = dt.datetime.now(ZoneInfo("Europe/Moscow")).date()
TODAY = today.isoformat()
EMP_ID = 2          # Соколова (Пятидневка)
SUF = dt.datetime.now().strftime("%H%M%S")   # уникальность между запусками
CODE = f"mat_aid_ui_{SUF}"
SHIFT_CODE = f"MAT_AID_UI_{SUF}"
KIND_NAME1 = "Заявление на материальную помощь (смоук)"
KIND_NAME2 = "Матпомощь (смоук, переименован)"

api = httpx.Client(base_url=BASE, timeout=20)
api.post("/api/auth/login", json={"username": "admin", "password": "demo1234"})
kinds_before = {k["code"] for k in api.get("/api/docs/kinds").json()["kinds"]}

with sync_playwright() as p:
    browser = p.chromium.launch(args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"])
    page = browser.new_page(viewport={"width": 1440, "height": 960}, accept_downloads=True)
    page.goto(BASE, wait_until="networkidle")
    page.fill("#login-username", "admin")
    page.fill("#login-password", "demo1234")
    page.click("#login-form button[type=submit], #login-form .btn-primary")
    page.wait_for_selector("#app:not(.hidden)", timeout=10000)

    # ── панель видов заявлений ──
    page.click('[data-view="settings"]')
    page.wait_for_selector("#s-add-kind", timeout=10000)
    txt = page.inner_text("#view-settings")
    check("панель «Виды заявлений и шаблоны»", "виды заявлений и шаблоны" in txt.lower())
    check("старая панель бланков убрана", "шаблоны документов компании" not in txt.lower())
    check("встроенные виды в таблице", all(x in txt for x in
          ("vacation_paid", "time_off_request", "встроенный")))
    check("справка по плейсхолдерам", page.query_selector("#s-kind-help") is not None)
    page.screenshot(path="tools/screens/batch2_kinds.png")

    # ── создать вид через модалку ──
    page.click("#s-add-kind")
    page.wait_for_selector("#k-code", timeout=5000)
    page.fill("#k-code", CODE)
    page.fill("#k-name", KIND_NAME1)
    page.fill("#k-text", "{director}\n{company}\nот {full_name_genitive}\n\nЗАЯВЛЕНИЕ\n\n"
                         "Прошу оказать мне материальную помощь.\n\n{today}  ____ / {short_name} /")
    page.screenshot(path="tools/screens/batch2_kindmodal.png")
    page.click("#modal [data-save]")
    page.wait_for_function(
        "() => document.querySelector('#view-settings').innerText.includes('%s')" % CODE,
        timeout=8000)
    check("вид создан через UI", True)

    # ── справка по плейсхолдерам открывается ──
    page.click("#s-kind-help")
    page.wait_for_selector("#modal table.data", timeout=5000)
    ph = page.inner_text("#modal")
    check("справка содержит {full_name_genitive}", "full_name_genitive" in ph)
    page.click("#modal [data-ok]")

    # ── переименование через «Изменить» ──
    page.click(f"tr:has-text('{CODE}') [data-kind]")
    page.wait_for_selector("#k-name", timeout=5000)
    check("код у существующего вида неизменяем",
          page.eval_on_selector("#k-code", "e => e.disabled"))
    page.fill("#k-name", KIND_NAME2)
    page.click("#modal [data-save]")
    page.wait_for_function(
        "() => document.querySelector('#view-settings').innerText.includes('переименован')",
        timeout=8000)
    check("вид переименован", True)

# ── привязка к смене и печать из ячейки (API + UI) ──
r = api.post("/api/shift-types", json={
    "code": SHIFT_CODE, "name": "Матпомощь (смоук)", "short_code": "МУ",
    "kind": "absence", "is_working": False, "counts_as_worked": False, "doc_type": CODE})
assert r.status_code == 200, r.text
shift_id = r.json()["id"]
r = api.put("/api/schedule/cell", json={
    "employee_id": EMP_ID, "date": TODAY, "shift_type_id": shift_id, "note": "смоук заявлений"})
assert r.status_code == 200, r.text

with sync_playwright() as p:
    browser = p.chromium.launch(args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"])
    page = browser.new_page(viewport={"width": 1440, "height": 960}, accept_downloads=True)
    page.goto(BASE, wait_until="networkidle")
    page.fill("#login-username", "admin")
    page.fill("#login-password", "demo1234")
    page.click("#login-form button[type=submit], #login-form .btn-primary")
    page.wait_for_selector("#app:not(.hidden)", timeout=10000)
    page.click('[data-view="schedule"]')
    page.wait_for_selector(f'.cellbtn[data-emp="{EMP_ID}"][data-date="{TODAY}"]', timeout=10000)
    page.click(f'.cellbtn[data-emp="{EMP_ID}"][data-date="{TODAY}"]')
    page.wait_for_selector("#doc-btns:not(.hidden)", timeout=8000)
    check("в ячейке с кастомным видом видны кнопки печати", True)

    with page.expect_download(timeout=15000) as dl:
        page.click("#doc-docx")
    d = dl.value
    body = d.path().read_bytes()
    check("DOCX скачался", body[:2] == b"PK", str(body[:8]))
    import io

    from docx import Document
    doctext = "\n".join(p_.text for p_ in Document(io.BytesIO(body)).paragraphs)
    check("в документе — текст своего вида", "материальную помощь" in doctext)
    check("плейсхолдеры подставлены", "{full_name_genitive}" not in doctext)

    # ── удалить вид через модалку (смена отвязывается) ──
    if page.query_selector("#modal [data-cancel]"):
        page.click("#modal [data-cancel]")        # модалка ячейки осталась открытой после скачивания
        page.wait_for_timeout(300)
    page.click('[data-view="settings"]')
    page.wait_for_selector("#s-add-kind", timeout=10000)
    page.click(f"tr:has-text('{CODE}') [data-kind]")
    page.wait_for_selector("#modal [data-del]", timeout=5000)
    page.click("#modal [data-del]")
    page.wait_for_selector("#modal [data-yes]", timeout=5000)
    page.click("#modal [data-yes]")
    page.wait_for_function(
        "() => !document.querySelector('#view-settings').innerText.includes('%s')" % CODE,
        timeout=8000)
    check("вид удалён через UI", True)
    browser.close()

# ── уборка ──
shifts = api.get("/api/shift-types", params={"include_archived": True}).json()
st = next(s for s in shifts if s["code"] == SHIFT_CODE)
check("у смены doc_type очищен после удаления вида", st["doc_type"] == "", st["doc_type"])
api.put("/api/schedule/cell", json={
    "employee_id": EMP_ID, "date": TODAY, "shift_type_id": None, "note": ""})
api.delete(f"/api/shift-types/{shift_id}")
leftover = {k["code"] for k in api.get("/api/docs/kinds").json()["kinds"]} - kinds_before
check("в справочнике не осталось смоук-видов", not leftover, str(leftover))
api.close()

# жёсткая уборка тестовой смены из архива (dev-база не должна зарастать мусором)
import sqlite3

con = sqlite3.connect("timetrack.db")
con.execute("DELETE FROM shift_revisions WHERE shift_type_id IN "
            "(SELECT id FROM shift_types WHERE code=?)", (SHIFT_CODE,))
con.execute("DELETE FROM shift_types WHERE code=?", (SHIFT_CODE,))
con.commit()
con.close()

print(f"\nитог: {OK} ok, {FAIL} fail")
sys.exit(1 if FAIL else 0)
