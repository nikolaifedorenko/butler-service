"""UI-смоук: пройтись по всем разделам и убедиться, что каждый отрисовал данные и нет JS-ошибок.

Проверяет в т.ч. новые возможности: «Кто на работе» (для менеджера и сотрудника),
переключатель План/Факт, липкие заголовки блоков, модалку периода через границы месяцев,
«отпросился» в редакторе ячейки, архив смен в настройках."""
import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
errors = []

CHECKS = [
    ("schedule", "#grid-host table.sched", "сетка графика"),
    ("onwork", "#ow-body .stat-grid", "кто на работе"),
    ("attendance", "#a-body table.data", "таблица посещений"),
    ("timesheet", "#t-body table.data", "таблица табеля"),
    ("employees", "#view-employees table.data", "периоды/карточки сотрудников"),
    ("me", "#view-me .me-shift", "карточка смены сотрудника"),
    ("settings", "#view-settings .rule-row", "правила расчёта"),
]

ok = True


def fail(msg: str):
    global ok
    ok = False
    print("  ✗", msg)


with sync_playwright() as pw:
    b = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    ctx = b.new_context(viewport={"width": 1500, "height": 900}, locale="ru-RU")
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(f"PAGEERROR: {e}"))
    page.on("console", lambda m: errors.append(f"console.error: {m.text[:160]}",)
            if m.type == "error" and "401" not in m.text else None)
    page.goto(BASE, wait_until="networkidle")
    page.fill("#login-username", "gromova")
    page.fill("#login-password", "demo1234")
    page.click("#login-form button[type=submit]")
    page.wait_for_timeout(1500)

    for view, selector, title in CHECKS:
        page.click(f'.nav-item[data-view="{view}"]')
        try:
            page.wait_for_selector(selector, timeout=12000)
            print(f"  ✓ {view:<10} {title}")
        except Exception:
            fail(f"{view:<10} {title} — НЕ ОТРИСОВАЛОСЬ")
            txt = page.eval_on_selector(f"#view-{view}", "el => el.innerText.slice(0, 200)")
            print("     содержимое:", txt.replace("\n", " | ")[:200])

    # ── график: липкий заголовок блока, План/Факт, скролл к сегодня ──
    page.click('.nav-item[data-view="schedule"]')
    page.wait_for_selector("#grid-host table.sched", timeout=10000)
    if page.locator("#grid-host tr.group-row td.g-name").count() > 0:
        print("  ✓ заголовки блоков — отдельные липкие ячейки (td.g-name)")
    else:
        fail("заголовки блоков не переведены на липкие ячейки")
    page.eval_on_selector("#grid-host", "el => el.scrollLeft = 800")
    page.wait_for_timeout(300)
    sticky_left = page.eval_on_selector("#grid-host tr.group-row td.g-name",
                                        "el => el.getBoundingClientRect().left")
    host_left = page.eval_on_selector("#grid-host", "el => el.getBoundingClientRect().left")
    if abs(sticky_left - host_left) < 30:
        print("  ✓ при прокрутке заголовок блока остаётся слева (sticky)")
    else:
        fail(f"заголовок блока уезжает: left={sticky_left:.0f} vs host={host_left:.0f}")

    page.click('#grid-mode button[data-mode="fact"]')
    page.wait_for_timeout(600)
    if page.locator("#grid-host .cellbtn.fact-ok, #grid-host .cellbtn.fact-abs, "
                    "#grid-host .cellbtn.fact-att, #grid-host .cellbtn.empty").count() > 0:
        print("  ✓ вид «Факт» переключается и рисует ячейки")
    else:
        fail("вид «Факт» не отрисовал ячейки")
    page.click('#grid-mode button[data-mode="plan"]')
    page.wait_for_timeout(400)

    # кнопка «Сегодня»: месяц открыт и сегодняшняя колонка существует
    page.click("#m-today")
    page.wait_for_timeout(900)
    if page.locator("#grid-host thead th.today").count() == 1:
        print("  ✓ «Сегодня» открывает текущий месяц с сегодняшней колонкой")
    else:
        fail("«Сегодня» не навело на текущий месяц")

    # ── модалка «Назначить отсутствие»: даты не ограничены месяцем ──
    page.click("#btn-range")
    page.wait_for_selector("#rg-from", timeout=8000)
    has_max = page.eval_on_selector("#rg-to", "el => el.getAttribute('max')")
    if has_max is None:
        print("  ✓ период отсутствия можно задать за границами месяца (без max)")
    else:
        fail(f"поле «по» ограничено месяцем: max={has_max}")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # ── редактор ячейки: рабочие смены показывают блок «отпросился» ──
    page.wait_for_selector("#grid-host .cellbtn:not([disabled])", timeout=10000)
    opened = False
    for btn in page.locator("#grid-host .cellbtn:not([disabled])").all()[:40]:
        try:
            btn.click(timeout=2000)
            page.wait_for_selector(".modal .shift-opt", timeout=4000)
        except Exception:
            continue
        work_opt = page.locator(".modal .shift-opt")
        # выбираем первую рабочую смену
        work_opt.first.click()
        page.wait_for_timeout(200)
        if page.locator("#partial-block").is_visible():
            print("  ✓ редактор ячейки: блок «отпросился» для рабочей смены виден")
            opened = True
        page.keyboard.press("Escape")
        page.wait_for_timeout(250)
        break
    if not opened:
        fail("блок «отпросился» не появился в редакторе ячейки")

    # ── карточка сотрудника: новые поля и периоды работы ──
    page.click('.nav-item[data-view="employees"]')
    page.wait_for_selector("#view-employees tr[data-card]", timeout=10000)
    page.click("#view-employees tr[data-card]")
    page.wait_for_selector("#modal [data-edit]", timeout=8000)
    body_txt = page.eval_on_selector("#modal", "el => el.innerText").upper()
    for needle in ("Гражданство", "Подразделение / служба", "Периоды работы",
                   "Ручные корректировки банка"):
        if needle.upper() in body_txt:
            print(f"  ✓ карточка: есть «{needle}»")
        else:
            fail(f"в карточке нет блока «{needle}»")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # ── настройки: базовый цикл без «Администрации», архив смен ──
    page.click('.nav-item[data-view="settings"]')
    page.wait_for_selector("#s-base-save", timeout=10000)
    if page.locator("#b-shift3").count() == 0:
        print("  ✓ базовый цикл: «Администрация/Пятидневка» убрана из общих настроек")
    else:
        fail("в настройках базового цикла осталась «Администрация»")
    page.click("#s-toggle-archived")
    page.wait_for_timeout(900)
    if page.locator("#s-toggle-archived").count() and "Скрыть архив" in page.inner_text("#s-toggle-archived"):
        print("  ✓ словарь смен: архив показывается/скрывается")
    page.click("#s-toggle-archived")
    page.wait_for_timeout(500)

    # ── вход сотрудником: «Кто на работе» доступен ──
    page.click("#logout-btn")
    page.wait_for_selector("#login-form", timeout=8000)
    page.fill("#login-username", "ivanov")
    page.fill("#login-password", "demo1234")
    page.click("#login-form button[type=submit]")
    page.wait_for_timeout(1500)
    if page.locator('.nav-item[data-view="onwork"]').count() > 0:
        page.click('.nav-item[data-view="onwork"]')
        try:
            page.wait_for_selector("#ow-body .stat-grid", timeout=10000)
            print("  ✓ сотрудник видит раздел «Кто на работе»")
        except Exception:
            fail("у сотрудника раздел «Кто на работе» не отрисовался")
    else:
        fail("у сотрудника нет пункта «Кто на работе»")

    print("\nJS-ошибки:", errors if errors else "нет")
    ctx.close()
    b.close()
    sys.exit(0 if ok and not any("PAGEERROR" in e for e in errors) else 1)
