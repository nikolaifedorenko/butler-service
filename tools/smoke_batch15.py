#!/usr/bin/env python3
"""Смоук батча 1+5: «оплачиваемое отсутствие» убрано из модалки смены;
в «Кто на работе» нет плитки опозданий, есть кликабельные tel:/t.me.

Запуск: сервер должен слушать 127.0.0.1:8000.
  ./.venv/bin/python tools/smoke_batch15.py
"""
import sys

import httpx

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


def api_part():
    print("== API ==")
    c = httpx.Client(base_url=BASE, timeout=15)
    r = c.post("/api/auth/login", json={"username": "admin", "password": "demo1234"})
    check("login admin", r.status_code == 200, r.text[:120])

    # отметка «Пришёл» за Иванова (id 4, в сиде есть телефон и @ivanov_butler)
    r = c.post("/api/punches", json={"kind": "IN", "employee_id": 4})
    check("punch IN за сотрудника", r.status_code == 200, r.text[:200])
    punch_id = r.json().get("punch", {}).get("id")

    r = c.get("/api/punches/onwork")
    check("onwork 200", r.status_code == 200)
    d = r.json()
    item = next((i for i in d["items"] if i["employee_id"] == 4), None)
    check("Иванов в «кто на работе»", item is not None)
    if item:
        check("onwork отдаёт phone", bool(item.get("phone")), item.get("phone"))
        check("onwork отдаёт telegram", "ivanov" in (item.get("telegram") or ""), item.get("telegram"))

    # cleanup: удаляем тестовую отметку (заодно проверяем, что DELETE работает)
    if punch_id:
        r = c.delete(f"/api/punches/{punch_id}")
        check("DELETE тестовой отметки", r.status_code == 200, r.text[:120])
    c.close()


def ui_part():
    print("== UI (Playwright) ==")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(BASE, wait_until="networkidle")
        page.fill("#login-username", "admin")
        page.fill("#login-password", "demo1234")
        page.click("#login-form button[type=submit], #login-form .btn-primary")
        page.wait_for_selector("#app:not(.hidden)", timeout=10000)

        # ── «Кто на работе» ──
        # отметка нужна, чтобы карточка точно отрисовалась
        c = httpx.Client(base_url=BASE, timeout=15)
        c.post("/api/auth/login", json={"username": "admin", "password": "demo1234"})
        r = c.post("/api/punches", json={"kind": "IN", "employee_id": 4})
        punch_id = r.json().get("punch", {}).get("id")

        page.click('[data-view="onwork"]')
        page.wait_for_selector("#ow-body .presence-card", timeout=10000)
        body = page.inner_text("#view-onwork")
        check("плитка «Пришли с опозданием» убрана", "пришли с опозданием" not in body.lower())
        tel = page.query_selector_all('#ow-body .contacts a[href^="tel:"]')
        tg = page.query_selector_all('#ow-body .contacts a[href*="t.me"]')
        check("ссылка tel: в карточке", len(tel) >= 1)
        check("ссылка t.me в карточке", len(tg) >= 1)
        if tg:
            href = tg[0].get_attribute("href")
            check("t.me href без @", href == "https://t.me/ivanov_butler", href)
        page.screenshot(path="tools/screens/batch15_onwork.png", full_page=False)

        if punch_id:
            c.delete(f"/api/punches/{punch_id}")
        c.close()

        # ── Настройки → модалка смены ──
        page.click('[data-view="settings"]')
        page.wait_for_selector("#s-add-shift", timeout=10000)
        page.click("#s-add-shift")
        page.wait_for_selector("#sh-kind", timeout=5000)
        opts = page.eval_on_selector_all("#sh-kind option", "els => els.map(e => e.value)")
        check("в типе смены 2 опции (work/absence)", opts == ["work", "absence"], str(opts))
        txt = page.inner_text("#modal").lower()
        check("нет слов «оплачиваемое отсутствие»", "оплачиваемое отсутствие" not in txt)
        page.screenshot(path="tools/screens/batch15_shiftmodal.png")
        page.click('[data-cancel]')

        # бейдж в списке смен — только «смена»/«отсутствие»
        rows = page.inner_text("#view-settings").lower()
        check("в списке смен нет «оплачиваемое отсутствие»", "оплачиваемое отсутствие" not in rows)

        browser.close()


if __name__ == "__main__":
    api_part()
    ui_part()
    print(f"\nитог: {OK} ok, {FAIL} fail")
    sys.exit(1 if FAIL else 0)
