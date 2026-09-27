"""Диагностика кликов: «Обнулить месяц» и «Удалить сотрудника» — что происходит в DOM/консоли."""
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
logs = []

with sync_playwright() as pw:
    b = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    ctx = b.new_context(viewport={"width": 1500, "height": 900}, locale="ru-RU")
    page = ctx.new_page()
    page.on("console", lambda m: logs.append(f"console.{m.type}: {m.text[:200]}"))
    page.on("pageerror", lambda e: logs.append(f"PAGEERROR: {str(e)[:300]}"))
    page.goto(BASE, wait_until="networkidle")
    page.fill("#login-username", "gromova")
    page.fill("#login-password", "demo1234")
    page.click("#login-form button[type=submit]")
    page.wait_for_selector("#grid-host table.sched", timeout=15000)

    print("== клик «Обнулить месяц» ==")
    page.click("#btn-clear")
    page.wait_for_timeout(700)
    print("модалка видна:", page.eval_on_selector("#modal-backdrop", "el => !el.classList.contains('hidden')"))
    print("текст модалки:", page.eval_on_selector("#modal", "el => el.innerText.slice(0,120)").replace("\n", " | "))
    if page.eval_on_selector("#modal-backdrop", "el => !el.classList.contains('hidden')"):
        page.click("#modal [data-yes]")
        page.wait_for_timeout(1200)
        print("после подтверждения: ячеек в сетке:",
              page.eval_on_selector_all("#grid-host .cellbtn:not(.empty)", "els => els.length"))

    print("== сотрудник: удалить ==")
    page.click('.nav-item[data-view="employees"]')
    page.wait_for_selector("#view-employees table.data", timeout=15000)
    page.click("#view-employees [data-edit]")
    page.wait_for_timeout(600)
    has_del = page.eval_on_selector_all("#modal [data-delete]", "els => els.length")
    print("кнопка удалить есть:", has_del)
    if has_del:
        page.click("#modal [data-delete]")
        page.wait_for_timeout(700)
        print("модалка подтверждения видна:",
              page.eval_on_selector("#modal-backdrop", "el => !el.classList.contains('hidden')"))
        print("текст:", page.eval_on_selector("#modal", "el => el.innerText.slice(0,120)").replace("\n", " | "))
    print("== console/page errors ==")
    for l in logs:
        print(" ", l)
    ctx.close()
    b.close()
