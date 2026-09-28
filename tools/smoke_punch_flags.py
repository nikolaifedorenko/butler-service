#!/usr/bin/env python3
"""Смоук батча 3: флаг «можно жать Пришёл/Ушёл» + override.

Сценарий: вид отсутствия с запретом → у сотрудника серая кнопка «сейчас статус: …» →
менеджер в модалке ячейки ставит override «разрешить» → кнопка оживает → отметка проходит.
Плюс проверка модалки смены (чекбоксы видны только у отсутствий).
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


# дата в TZ приложения (Europe/Moscow), а не в TZ песочницы
today = dt.datetime.now(ZoneInfo("Europe/Moscow")).date()
TODAY = today.isoformat()
EMP_ID = 2   # Соколова (Пятидневка)
CODE = "NOPUNCH_SMOKE"

api = httpx.Client(base_url=BASE, timeout=15)
api.post("/api/auth/login", json={"username": "admin", "password": "demo1234"})

# ── подготовка: вид отсутствия с запретом отметок + назначить Соколовой на сегодня ──
r = api.post("/api/shift-types", json={
    "code": CODE, "name": "Смоук: без отметок", "short_code": "СБ",
    "kind": "absence", "is_working": False, "counts_as_worked": False,
    "punch_in_allowed": False, "punch_out_allowed": False})
assert r.status_code == 200, r.text
shift_id = r.json()["id"]
r = api.put("/api/schedule/cell", json={
    "employee_id": EMP_ID, "date": TODAY, "shift_type_id": shift_id, "note": "смоук"})
assert r.status_code == 200, r.text

with sync_playwright() as p:
    browser = p.chromium.launch(args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"])

    # ═══ сотрудник: серая неактивная кнопка ═══
    ctx_emp = browser.new_context(viewport={"width": 430, "height": 900})
    pe = ctx_emp.new_page()
    pe.goto(BASE, wait_until="networkidle")
    pe.fill("#login-username", "sokolova")
    pe.fill("#login-password", "demo1234")
    pe.click("#login-form button[type=submit], #login-form .btn-primary")
    pe.wait_for_selector("#view-me .punch-btn", timeout=10000)
    btn = pe.query_selector("#punch-btn")
    check("кнопка неактивна (disabled)", btn.is_disabled())
    check("кнопка серая (класс idle)", "idle" in (btn.get_attribute("class") or ""))
    txt = pe.inner_text("#view-me").lower()
    check("подпись «сейчас статус: …»", "сейчас статус" in txt)
    check("в подписи — название отсутствия", "смоук: без отметок" in txt)
    pe.screenshot(path="tools/screens/batch3_disabled.png")

    # ═══ менеджер: модалка смены (чекбоксы) и модалка ячейки (override) ═══
    ctx_adm = browser.new_context(viewport={"width": 1440, "height": 960})
    pa = ctx_adm.new_page()
    pa.goto(BASE, wait_until="networkidle")
    pa.fill("#login-username", "admin")
    pa.fill("#login-password", "demo1234")
    pa.click("#login-form button[type=submit], #login-form .btn-primary")
    pa.wait_for_selector("#app:not(.hidden)", timeout=10000)

    # модалка смены: у рабочей чекбоксы скрыты, у отсутствия — видны и сняты
    pa.click('[data-view="settings"]')
    pa.wait_for_selector("#s-add-shift", timeout=10000)
    pa.click("#s-add-shift")
    pa.wait_for_selector("#sh-kind", timeout=5000)
    check("у рабочей смены блок отметок скрыт",
          pa.eval_on_selector("#sh-punch-wrap", "e => getComputedStyle(e).display") == "none")
    pa.select_option("#sh-kind", "absence")
    check("у отсутствия блок отметок виден",
          pa.eval_on_selector("#sh-punch-wrap", "e => getComputedStyle(e).display") != "none")
    pa.click("#modal [data-cancel]")

    # модалка ячейки: override «разрешить» приход
    pa.click('[data-view="schedule"]')
    pa.wait_for_selector(f'.cellbtn[data-emp="{EMP_ID}"][data-date="{TODAY}"]', timeout=10000)
    pa.click(f'.cellbtn[data-emp="{EMP_ID}"][data-date="{TODAY}"]')
    pa.wait_for_selector("#cell-punch-in", timeout=5000)
    check("override-блок в модалке ячейки виден",
          pa.eval_on_selector("#punch-override-block", "e => !e.classList.contains('hidden')"))
    pa.select_option("#cell-punch-in", "1")
    pa.screenshot(path="tools/screens/batch3_celloverride.png")
    pa.click("#modal [data-save]")
    pa.wait_for_selector("#modal .modal-head", state="detached", timeout=8000)
    pa.wait_for_timeout(600)

    # ═══ сотрудник: кнопка ожила, отметка проходит ═══
    pe.reload(wait_until="networkidle")
    pe.wait_for_selector("#view-me .punch-btn", timeout=10000)
    btn = pe.query_selector("#punch-btn")
    check("после override кнопка активна", not btn.is_disabled())
    pe.click("#punch-btn")
    pe.wait_for_selector(".toast", timeout=8000)
    toast = pe.inner_text(".toast").lower()
    check("отметка прошла (тост «отмечен приход»)", "отмечен приход" in toast, toast[:120])
    pe.screenshot(path="tools/screens/batch3_punched.png")

    ctx_emp.close()
    ctx_adm.close()
    browser.close()

# ── уборка ──
punches = api.get("/api/punches", params={"date": TODAY, "employee_id": EMP_ID}).json()
for p_ in punches:
    if p_["note"] == "" or "смоук" in (p_["note"] or ""):
        api.delete(f"/api/punches/{p_['id']}")
api.put("/api/schedule/cell", json={"employee_id": EMP_ID, "date": TODAY, "shift_type_id": None, "note": ""})
api.delete(f"/api/shift-types/{shift_id}")
api.close()

# жёсткая уборка тестовой смены из архива
import sqlite3

con = sqlite3.connect("timetrack.db")
con.execute("DELETE FROM shift_revisions WHERE shift_type_id=?", (shift_id,))
con.execute("DELETE FROM shift_types WHERE id=?", (shift_id,))
con.commit()
con.close()

print(f"\nитог: {OK} ok, {FAIL} fail")
sys.exit(1 if FAIL else 0)
