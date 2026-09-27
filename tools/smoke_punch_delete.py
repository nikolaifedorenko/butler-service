#!/usr/bin/env python3
"""Смоук: менеджер отменяет ошибочную отметку в «Посещениях» (✕ → подтверждение → пересчёт)."""
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

api = httpx.Client(base_url=BASE, timeout=15)
api.post("/api/auth/login", json={"username": "admin", "password": "demo1234"})

# убираем хвосты прежних запусков: сегодняшние ручные (созданные менеджером) отметки
for x in api.get("/api/punches", params={"date": TODAY}).json():
    if x.get("source") == "manual":
        api.delete(f"/api/punches/{x['id']}")

# нужен сотрудник, у которого отметка попадёт в СЕГОДНЯШНЮЮ строку табеля
# (дневная смена, сейчас внутри окна приёма отметок) — проверяем по fact_in
att = api.get("/api/punches/attendance", params={"date": TODAY}).json()
workers = [i["employee"]["id"] for i in att["items"]
           if i.get("shift") and i["shift"]["kind"] == "work" and not i["shift"].get("overnight")]
assert workers, "нет сотрудников с рабочей дневной сменой сегодня — смоук неприменим"
EMP_ID, punch_id = None, None
for cand in workers:
    r = api.post("/api/punches", json={"kind": "IN", "employee_id": cand})
    assert r.status_code == 200, r.text
    att = api.get("/api/punches/attendance", params={"date": TODAY}).json()
    item = next(i for i in att["items"] if i["employee"]["id"] == cand)
    if item["fact_in"]:
        EMP_ID, punch_id = cand, r.json()["punch"]["id"]
        break
    api.delete(f"/api/punches/{r.json()['punch']['id']}")   # отметка ушла в другой день — пробуем следующего
assert punch_id, "ни у кого отметка не легла в сегодняшний табель (окно приёма?)"

with sync_playwright() as p:
    browser = p.chromium.launch(args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"])
    page = browser.new_page(viewport={"width": 1440, "height": 960})
    page.goto(BASE, wait_until="networkidle")
    page.fill("#login-username", "admin")
    page.fill("#login-password", "demo1234")
    page.click("#login-form button[type=submit], #login-form .btn-primary")
    page.wait_for_selector("#app:not(.hidden)", timeout=10000)
    page.click('[data-view="attendance"]')
    page.wait_for_selector(f'#a-body [data-pdel="{punch_id}"]', timeout=10000)
    check("✕ видна у отметки в «Посещениях»", True)
    page.screenshot(path="tools/screens/punch_delete.png")
    page.click(f'#a-body [data-pdel="{punch_id}"]')
    page.wait_for_selector("#modal [data-yes]", timeout=5000)
    page.click("#modal [data-yes]")
    page.wait_for_selector(".toast", timeout=8000)
    check("подтверждение и тост", "отменена" in page.inner_text(".toast").lower())
    page.wait_for_timeout(700)
    gone = page.query_selector(f'#a-body [data-pdel="{punch_id}"]') is None
    check("после отмены ✕ исчезла", gone)
    browser.close()

left = api.get("/api/punches", params={"date": TODAY, "employee_id": EMP_ID}).json()
check("отметки нет в журнале", all(x["id"] != punch_id for x in left))
api.close()

print(f"\nитог: {OK} ok, {FAIL} fail")
sys.exit(1 if FAIL else 0)
