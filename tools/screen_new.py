"""Скриншоты новых возможностей (Playwright): вид План/Факт, «Кто на работе»,
карточка сотрудника, «отпросился», период через месяцы, архив смен."""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).parent / "screens"
OUT.mkdir(exist_ok=True)
errors: list[str] = []


def login(page, username, password="demo1234"):
    page.goto(BASE, wait_until="networkidle")
    page.fill("#login-username", username)
    page.fill("#login-password", password)
    page.click("#login-form button[type=submit]")
    page.wait_for_timeout(1600)


def shot(page, name):
    page.screenshot(path=str(OUT / f"{name}.png"))
    print("saved", name)


def watch(page, label):
    page.on("console", lambda m: errors.append(f"[{label}] console.{m.type}: {m.text}")
            if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"[{label}] pageerror: {e}"))


with sync_playwright() as pw:
    b = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    ctx = b.new_context(viewport={"width": 1560, "height": 950}, locale="ru-RU")
    page = ctx.new_page()
    watch(page, "desktop")

    login(page, "gromova")

    # график: план (липкие заголовки блоков)
    page.wait_for_selector("#grid-host table.sched", timeout=15000)
    page.wait_for_timeout(800)
    shot(page, "80-schedule-plan")

    # график: факт
    page.click('#grid-mode button[data-mode="fact"]')
    page.wait_for_timeout(800)
    shot(page, "81-schedule-fact")
    page.click('#grid-mode button[data-mode="plan"]')
    page.wait_for_timeout(400)

    # «Кто на работе»
    page.click('.nav-item[data-view="onwork"]')
    page.wait_for_selector("#ow-body .stat-grid", timeout=12000)
    page.wait_for_timeout(500)
    shot(page, "82-onwork")

    # карточка сотрудника (гражданство, служба, периоды работы, банк)
    page.click('.nav-item[data-view="employees"]')
    page.wait_for_selector("#view-employees tr[data-card]", timeout=12000)
    page.click("#view-employees tr[data-card]")
    page.wait_for_selector("#modal [data-edit]", timeout=10000)
    page.wait_for_timeout(400)
    shot(page, "83-employee-card")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # редактор ячейки с «отпросился» — открываем рабочую ячейку Иванова сегодня/вчера
    page.click('.nav-item[data-view="schedule"]')
    page.wait_for_selector("#grid-host table.sched", timeout=12000)
    opened = False
    for sel in ['#grid-host td.today .cellbtn:not([disabled])',
                '#grid-host .cellbtn:not([disabled]):not(.empty)']:
        try:
            page.click(sel, timeout=3000)
            page.wait_for_selector(".modal .shift-opt", timeout=5000)
            # выбрать рабочую смену, чтобы появился блок «отпросился»
            page.locator(".modal .shift-opt").first.click()
            page.wait_for_timeout(300)
            if page.locator("#partial-block").is_visible():
                opened = True
                break
            page.keyboard.press("Escape")
            page.wait_for_timeout(250)
        except Exception:
            continue
    if opened:
        shot(page, "84-cell-partial")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # модалка «Назначить отсутствие» (период через границы месяцев)
    page.click("#btn-range")
    page.wait_for_selector("#rg-from", timeout=8000)
    page.fill("#rg-from", "2026-09-28")
    page.fill("#rg-to", "2026-10-05")
    page.wait_for_timeout(300)
    shot(page, "85-range-modal")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # настройки: базовый цикл (без администрации)
    page.click('.nav-item[data-view="settings"]')
    page.wait_for_selector("#s-base-save", timeout=12000)
    page.eval_on_selector("#s-base-save", "el => el.scrollIntoView({block: 'center'})")
    page.wait_for_timeout(400)
    shot(page, "86-settings-base")

    # словарь смен с архивом
    page.click("#s-toggle-archived")
    page.wait_for_timeout(900)
    page.eval_on_selector("#s-add-shift", "el => el.scrollIntoView({block: 'center'})")
    page.wait_for_timeout(300)
    shot(page, "87-settings-shifts-archive")
    page.click("#s-toggle-archived")
    page.wait_for_timeout(500)

    ctx.close()

    # «Кто на работе» глазами сотрудника
    ctx2 = b.new_context(viewport={"width": 1560, "height": 950}, locale="ru-RU")
    page2 = ctx2.new_page()
    watch(page2, "employee")
    login(page2, "ivanov")
    page2.click('.nav-item[data-view="onwork"]')
    page2.wait_for_selector("#ow-body .stat-grid", timeout=12000)
    page2.wait_for_timeout(500)
    shot(page2, "88-onwork-employee")
    ctx2.close()

    # телефон: кто на работе
    ctx3 = b.new_context(viewport={"width": 390, "height": 844}, locale="ru-RU",
                         is_mobile=True, has_touch=True)
    page3 = ctx3.new_page()
    watch(page3, "mobile")
    login(page3, "ivanov")
    page3.click('#tabbar button[data-view="onwork"]')   # на телефоне — нижний таббар
    page3.wait_for_selector("#ow-body .stat-grid", timeout=12000)
    page3.wait_for_timeout(500)
    shot(page3, "89-onwork-mobile")
    ctx3.close()

    b.close()

print("JS errors:", errors if errors else "none")
