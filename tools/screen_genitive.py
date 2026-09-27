"""UI-проверка поля «ФИО в родительном падеже» и кнопки «Подсказать» + панель шаблонов.

Логинится админом, открывает редактор нового сотрудника, вводит ФИО, жмёт «Подсказать»
и проверяет автоподстановку. Делает скриншоты редактора и панели шаблонов документов.
"""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).parent / "screens"
OUT.mkdir(exist_ok=True)

errors = []

with sync_playwright() as pw:
    b = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, locale="ru-RU")
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(f"PAGEERROR: {e}"))
    page.on("console", lambda m: errors.append(f"console.error: {m.text[:160]}")
            if m.type == "error" and "401" not in m.text else None)

    page.goto(BASE, wait_until="networkidle")
    page.fill("#login-username", "admin")
    page.fill("#login-password", "demo1234")
    page.click("#login-form button[type=submit]")
    page.wait_for_timeout(1200)

    # ── редактор нового сотрудника ──
    page.click('.nav-item[data-view="employees"]')
    page.wait_for_selector("#e-add", timeout=8000)
    page.click("#e-add")
    page.wait_for_selector("#e-full", timeout=8000)

    page.fill("#e-full", "Федоренко Николай Сергеевич")
    page.click("#e-gen-suggest")
    page.wait_for_timeout(700)
    gen = page.input_value("#e-full-gen")
    print("Подсказать →", repr(gen))
    assert gen == "Федоренко Николая Сергеевича", f"ожидался род. падеж, получено: {gen!r}"

    # проверим и женский вариант
    page.fill("#e-full", "Смирнова Анна Петровна")
    page.click("#e-gen-suggest")
    page.wait_for_timeout(500)
    gen2 = page.input_value("#e-full-gen")
    print("Подсказать (жен.) →", repr(gen2))
    assert gen2 == "Смирновой Анны Петровны", f"получено: {gen2!r}"

    # вернём мужской для скриншота
    page.fill("#e-full", "Федоренко Николай Сергеевич")
    page.click("#e-gen-suggest")
    page.wait_for_timeout(400)
    page.screenshot(path=str(OUT / "genitive_editor.png"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # ── панель шаблонов документов в настройках ──
    page.click('.nav-item[data-view="settings"]')
    page.wait_for_selector("[data-tpl-sample]", timeout=10000)
    el = page.query_selector("[data-tpl-sample]")
    el.scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    # раскроем список всех плейсхолдеров, чтобы {full_name_genitive} попал в кадр
    page.eval_on_selector_all("#view-settings details", "ds => ds.forEach(d => d.open = true)")
    page.wait_for_timeout(200)
    panel = page.query_selector("[data-tpl-sample]").evaluate_handle("b => b.closest('.panel')")
    panel.as_element().screenshot(path=str(OUT / "genitive_settings.png"))
    print("sample button present:", bool(el))

    b.close()

print("errors:", errors or "нет")
