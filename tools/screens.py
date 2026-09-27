"""Скриншоты интерфейса + сбор ошибок консоли (Playwright, headless Chromium)."""
from __future__ import annotations

import sys
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


def shot(page, name, full=False):
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=full)
    print("saved", path.name)


def watch(page, label):
    page.on("console", lambda m: errors.append(f"[{label}] console.{m.type}: {m.text}")
            if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: errors.append(f"[{label}] pageerror: {e}"))


def run_desktop(browser):
    ctx = browser.new_context(viewport={"width": 1560, "height": 950}, device_scale_factor=1,
                              locale="ru-RU")
    page = ctx.new_page()
    watch(page, "desktop")

    login(page, "gromova")
    shot(page, "01-login-skip")

    # график
    page.wait_for_selector("#grid-host table.sched", timeout=15000)
    page.wait_for_timeout(700)
    shot(page, "10-schedule-desktop")

    # модалка редактирования ячейки
    page.click("#grid-host .cellbtn >> nth=8")
    page.wait_for_selector(".modal .shift-opt", timeout=8000)
    page.wait_for_timeout(400)
    shot(page, "11-cell-editor")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # модалка заполнения графиком
    page.click("#btn-pattern")
    page.wait_for_selector("#p-pattern", timeout=8000)
    page.wait_for_timeout(400)
    shot(page, "12-fill-pattern")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # посещения
    page.click('.nav-item[data-view="attendance"]')
    page.wait_for_selector("#a-body table.data", timeout=15000)
    page.wait_for_timeout(900)
    shot(page, "20-attendance-desktop")

    # табель
    page.click('.nav-item[data-view="timesheet"]')
    page.wait_for_selector("#t-body table.data", timeout=15000)
    page.wait_for_timeout(900)
    shot(page, "30-timesheet-desktop")
    page.click(".ts-row >> nth=1")
    page.wait_for_selector(".day-chips", timeout=8000)
    page.wait_for_timeout(600)
    shot(page, "31-timesheet-days")

    # сотрудники
    page.click('.nav-item[data-view="employees"]')
    page.wait_for_selector("#view-employees table.data", timeout=15000)
    page.wait_for_timeout(700)
    shot(page, "40-employees-desktop")

    # настройки
    page.click('.nav-item[data-view="settings"]')
    page.wait_for_selector("#view-settings .rule-row", timeout=15000)
    page.wait_for_timeout(700)
    shot(page, "50-settings-desktop")

    # мои отметки (от имени менеджера, привязанного к сотруднику)
    page.click('.nav-item[data-view="me"]')
    page.wait_for_timeout(1500)
    shot(page, "60-me-desktop")

    ctx.close()


def run_mobile(browser):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                              is_mobile=True, has_touch=True, locale="ru-RU")
    page = ctx.new_page()
    watch(page, "mobile")

    page.goto(BASE, wait_until="networkidle")
    shot(page, "00-login-mobile")
    login(page, "gromova")
    page.wait_for_selector("#grid-host table.sched", timeout=20000)
    page.wait_for_timeout(900)
    shot(page, "10-schedule-mobile")

    page.click("#grid-host .cellbtn >> nth=5")
    page.wait_for_selector(".modal .shift-opt", timeout=8000)
    page.wait_for_timeout(500)
    shot(page, "11-cell-editor-mobile")
    page.keyboard.press("Escape")

    page.click('#tabbar button[data-view="attendance"]')
    page.wait_for_selector("#a-body table.data", timeout=15000)
    page.wait_for_timeout(900)
    shot(page, "20-attendance-mobile", full=True)

    page.click('#tabbar button[data-view="timesheet"]')
    page.wait_for_selector("#t-body table.data", timeout=15000)
    page.wait_for_timeout(900)
    shot(page, "30-timesheet-mobile", full=True)

    page.click('#tabbar button[data-view="me"]')
    page.wait_for_timeout(1800)
    shot(page, "60-me-mobile", full=True)
    ctx.close()


def run_mobile_landscape(browser):
    ctx = browser.new_context(viewport={"width": 844, "height": 390}, device_scale_factor=2,
                              is_mobile=True, has_touch=True, locale="ru-RU")
    page = ctx.new_page()
    watch(page, "landscape")
    login(page, "ivanov")
    page.wait_for_timeout(2000)
    shot(page, "70-me-landscape", full=True)
    ctx.close()


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        run_desktop(browser)
        run_mobile(browser)
        run_mobile_landscape(browser)
        browser.close()
    print("\n=== console problems ===")
    for e in errors[:60]:
        print(" -", e[:260])
    print("total:", len(errors))
    return 1 if any("pageerror" in e for e in errors) else 0


if __name__ == "__main__":
    sys.exit(main())
