#!/usr/bin/env python3
"""Смоук батча 4: панель «Департаменты и службы» в настройках + select службы в карточке."""
import sys

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


with sync_playwright() as p:
    browser = p.chromium.launch(args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"])
    page = browser.new_page(viewport={"width": 1440, "height": 960})
    page.goto(BASE, wait_until="networkidle")
    page.fill("#login-username", "admin")
    page.fill("#login-password", "demo1234")
    page.click("#login-form button[type=submit], #login-form .btn-primary")
    page.wait_for_selector("#app:not(.hidden)", timeout=10000)

    # ── Настройки → панель справочников ──
    page.click('[data-view="settings"]')
    page.wait_for_selector("#dicts-body", timeout=10000)
    page.wait_for_selector("#dep-add", timeout=10000)
    check("панель «Департаменты и службы» видна",
          "департаменты и службы" in page.inner_text("#view-settings").lower())
    dicts_txt = page.inner_text("#dicts-body")
    check("бэкфилл: служба из карточек попала в справочник",
          "Служба управления виллами" in dicts_txt, dicts_txt[:200])
    check("существующие департаменты на месте",
          "Служба батлеров" in dicts_txt and "Управление" in dicts_txt)

    # добавить департамент
    page.fill("#dep-new", "Смоук-департамент")
    page.click("#dep-add")
    page.wait_for_function(
        "() => document.querySelector('#dicts-body').innerText.includes('Смоук-департамент')",
        timeout=8000)
    check("департамент добавился", True)

    # переименовать
    page.click("#dicts-body tr:has-text('Смоук-департамент') [data-dep-ren]")
    page.wait_for_selector("#dict-name", timeout=5000)
    page.fill("#dict-name", "Смоук-департамент 2")
    page.click("#modal [data-ok]")
    page.wait_for_function(
        "() => document.querySelector('#dicts-body').innerText.includes('Смоук-департамент 2')",
        timeout=8000)
    check("департамент переименован", True)

    # добавить службу
    page.fill("#sub-new", "Смоук-служба")
    page.click("#sub-add")
    page.wait_for_function(
        "() => document.querySelector('#dicts-body').innerText.includes('Смоук-служба')",
        timeout=8000)
    check("служба добавилась", True)
    page.screenshot(path="tools/screens/batch4_dicts.png")

    # ── Карточка сотрудника: служба стала select-ом ──
    page.click('[data-view="employees"]')
    page.wait_for_selector("tr[data-card]", timeout=10000)
    page.click("tr[data-card]")
    page.wait_for_selector("[data-edit]", timeout=5000)
    page.click("[data-edit]")
    page.wait_for_selector("#e-subdiv", timeout=5000)
    tag = page.evaluate("() => document.querySelector('#e-subdiv').tagName")
    check("поле службы — select", tag == "SELECT", tag)
    opts = page.eval_on_selector_all("#e-subdiv option", "els => els.map(e => e.textContent)")
    check("в select есть «Смоук-служба» и «— не указано —»",
          any("Смоук-служба" in o for o in opts) and any("не указано" in o for o in opts), str(opts))
    page.screenshot(path="tools/screens/batch4_empmodal.png")
    page.click("#modal [data-cancel]")

    # ── удаление службы через confirm ──
    page.click('[data-view="settings"]')
    page.wait_for_selector("#dicts-body [data-sub-del]", timeout=8000)
    page.click("#dicts-body tr:has-text('Смоук-служба') [data-sub-del]")
    page.wait_for_selector("#modal [data-yes]", timeout=5000)
    page.click("#modal [data-yes]")
    page.wait_for_function(
        "() => !document.querySelector('#dicts-body').innerText.includes('Смоук-служба')",
        timeout=8000)
    check("служба удалена через подтверждение", True)

    # ── удаление департамента ──
    page.click("#dicts-body tr:has-text('Смоук-департамент 2') [data-dep-del]")
    page.wait_for_selector("#modal [data-yes]", timeout=5000)
    page.click("#modal [data-yes]")
    page.wait_for_function(
        "() => !document.querySelector('#dicts-body').innerText.includes('Смоук-департамент')",
        timeout=8000)
    check("департамент удалён", True)

    browser.close()

print(f"\nитог: {OK} ok, {FAIL} fail")
sys.exit(1 if FAIL else 0)
