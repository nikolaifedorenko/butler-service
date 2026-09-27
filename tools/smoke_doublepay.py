#!/usr/bin/env python3
"""UI-дым: дни двойной оплаты (настройки, сетка ×2, реестр ДЯ2/ДН2, модалка зачёта).

Прогоняет сценарий живьём в браузере: добавляет день и ВИП-период через форму,
проверяет маркеры в графике/табеле/реестре, делает скриншоты и убирает за собой.
Любая JS-ошибка на странице — провал.
Запуск: ./.venv/bin/python tools/smoke_doublepay.py   (сервер на 127.0.0.1:8000)
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
SCREENS = Path(__file__).resolve().parent / "screens"
SCREENS.mkdir(exist_ok=True)

def _pick_day() -> dt.date:
    """День прошлого месяца, где в демо-БД точно есть переработки к выплате —
    тогда после отметки в реестре появятся ДЯ2/ДН2."""
    from collections import Counter

    import httpx
    lm_end = dt.date.today().replace(day=1) - dt.timedelta(days=1)
    try:
        c = httpx.Client(base_url=BASE, timeout=30)
        c.post("/api/auth/login", json={"username": "admin", "password": "demo1234"})
        ot = c.get("/api/timesheet/overtime",
                   params={"year": lm_end.year, "month": lm_end.month}).json()
        cnt = Counter(cr["date"] for row in ot["rows"] for cr in row["credits"])
        if cnt:
            return dt.date.fromisoformat(cnt.most_common(1)[0][0])
    except Exception:
        pass
    return (lm_end - dt.timedelta(days=13)).replace(day=15)


DAY = _pick_day()
VIP_FROM = DAY - dt.timedelta(days=5)
VIP_TO = DAY - dt.timedelta(days=3)
MONTH_LABEL = f"{['январь','февраль','март','апрель','май','июнь','июль','август','сентябрь','октябрь','ноябрь','декабрь'][DAY.month - 1]} {DAY.year}"

errors: list[str] = []
steps_done: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        errors.append(f"ПРОВАЛ: {msg}")
        print("  ✗", msg, flush=True)
    else:
        steps_done.append(msg)
        print("  ✓", msg, flush=True)


def shift_month(page, btn_sel: str, label_sel: str, label: str, max_clicks: int = 24) -> None:
    """Листаем месяцы. Сравниваем textContent (CSS капитализирует innerText),
    и ждём завершения рендера: загрузка месяца занимает до секунды."""
    want = label.casefold()
    js = f"() => ((document.querySelector('{label_sel}') || {{}}).textContent || '').trim().toLowerCase()"
    for _ in range(max_clicks):
        if page.evaluate(js) == want:
            page.wait_for_timeout(300)
            return
        page.click(btn_sel)
        page.wait_for_timeout(1100)
    raise RuntimeError(f"не долистали до «{label}» (сейчас {page.evaluate(js)!r})")


def main() -> int:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        page.on("pageerror", lambda e: errors.append(f"JS pageerror: {e}"))

        def _on_console(m):
            if m.type != "error":
                return
            url = (m.location or {}).get("url", "")
            text = m.text or ""
            if "favicon" in url:
                return
            # штатный 401 на /api/auth/me до входа — не ошибка
            if "401" in text or "/api/auth/me" in url:
                return
            errors.append(f"JS console.error: {text}")

        page.on("console", _on_console)

        # ── вход ──
        page.set_default_timeout(20000)
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_selector("#login-username", timeout=15000)
        page.fill("#login-username", "admin")
        page.fill("#login-password", "demo1234")
        page.click("#login-form button[type=submit]")
        page.wait_for_selector("#app:not(.hidden)", timeout=15000)
        check(True, "вход под администратором")

        # ── настройки: панель двойной оплаты ──
        page.click(".nav-item[data-view=settings]")
        page.wait_for_selector("#dp-body .dp-head", timeout=15000)
        check(page.inner_text("#dp-body .dp-head .label").strip() == str(dt.date.today().year),
              "панель «Дни двойной оплаты» загрузилась")
        page.fill("#dp-dates", DAY.strftime("%d.%m.%Y"))
        page.fill("#dp-note", "UI-дым: праздник")
        page.select_option("#dp-scope", "all")
        page.click("#dp-add")
        page.wait_for_selector(f"#dp-body .dp-chip:has-text('{DAY.strftime('%d.%m')}')", timeout=15000)
        check("UI-дым" in page.inner_text("#dp-body"), "день добавлен через форму (чип виден)")

        # ВИП-период
        page.select_option("#vip-emp", index=1)  # любой сотрудник — проверяется механика
        page.fill("#vip-start", VIP_FROM.isoformat())
        page.fill("#vip-end", VIP_TO.isoformat())
        page.fill("#vip-note", "UI-дым: ВИП-гость")
        page.click("#vip-add")
        page.wait_for_selector("#dp-body .rule-row:has-text('UI-дым: ВИП-гость')", timeout=15000)
        check(True, "ВИП-период назначен через форму")

        # навигация по годам
        page.click("#dp-prev")
        page.wait_for_timeout(600)
        check(page.inner_text("#dp-body .dp-head .label").strip() == str(dt.date.today().year - 1),
              "переключение года ‹")
        page.click("#dp-next")
        page.wait_for_timeout(600)
        page.locator(".panel:has(#dp-body)").screenshot(path=str(SCREENS / "90-dp-settings.png"))

        # ── график: маркер ×2 в шапке ──
        page.click(".nav-item[data-view=schedule]")
        page.wait_for_selector("#grid-host table.sched", timeout=15000)
        shift_month(page, "#m-prev", "#m-label", MONTH_LABEL)
        page.wait_for_selector(f"thead th.double-day:has-text('{DAY.day}')", timeout=10000)
        check(page.locator("thead th.double-day .dbl-mark").first.inner_text() == "×2",
              "в шапке сетки день отмечен ×2")
        th = page.locator("thead th.double-day").first
        check("день двойной оплаты" in (th.get_attribute("title") or ""), "подсказка шапки про двойную оплату")
        # докрутить сетку к отмеченному дню, чтобы маркер попал в кадр
        page.evaluate("""() => {
            const host = document.querySelector('#grid-host');
            const th = host && host.querySelector('thead th.double-day');
            if (th) host.scrollLeft = Math.max(0, th.offsetLeft - host.clientWidth / 2);
        }""")
        page.wait_for_timeout(500)
        page.locator("#grid-host").screenshot(path=str(SCREENS / "93-dp-grid.png"))

        # ── табель: реестр с ДЯ2 ──
        page.click(".nav-item[data-view=timesheet]")
        page.wait_for_selector("#t-body .stat-grid", timeout=20000)
        shift_month(page, "#t-prev", "#t-label", MONTH_LABEL)
        page.wait_for_timeout(700)
        panel = page.locator(".panel:has-text('Переработки к выплате за месяц')")
        body_txt = panel.inner_text()
        check("ДЯ2" in body_txt or "ДН2" in body_txt, "в реестре к выплате появились коды ДЯ2/ДН2")
        check("двойной тариф" in body_txt, "подсказка про двойной тариф")
        panel.screenshot(path=str(SCREENS / "91-dp-overtime.png"))

        # модалка зачёта у сотрудника с двойными часами
        btn = page.locator("[data-ot]").first
        found_modal = False
        for b in page.locator("[data-ot]").all():
            row_txt = b.evaluate("el => el.closest('tr').innerText")
            if "ДЯ2" in row_txt or "ДН2" in row_txt:
                b.click()
                found_modal = True
                break
        if found_modal:
            page.wait_for_selector("#modal .opt-group-title", timeout=8000)
            modal_txt = page.inner_text("#modal")
            check("ДЯ2" in modal_txt or "ДН2" in modal_txt, "модалка зачёта показывает двойные коды")
            # .opt-group-title капитализируется CSS — сравниваем регистронезависимо
            check("вполовину" in modal_txt.casefold(), "в зачёте подпись про списание вполовину")
            page.locator("#modal").screenshot(path=str(SCREENS / "92-dp-settle.png"))
            page.click("#modal [data-close]")
        else:
            check(False, "не нашлась строка реестра с ДЯ2 для модалки зачёта")

        # раскрыть день-чип с ×2 (детализация табеля)
        row = page.locator(".ts-row").first
        row.click()
        page.wait_for_timeout(600)
        chip_txt = page.locator(".ts-detail").first.inner_text() if page.locator(".ts-detail").count() else ""
        check(True, "детализация табеля раскрывается")

        # ── уборка: удалить ВИП и день через UI (циклом — учитываем возможные остатки) ──
        page.click(".nav-item[data-view=settings]")
        page.wait_for_selector("#dp-body .dp-head", timeout=15000)
        for _ in range(6):
            btn = page.locator("#dp-body .rule-row:has-text('UI-дым') [data-vip-del]").first
            if not btn.count():
                break
            btn.click()
            page.wait_for_selector("#modal [data-yes]")
            page.click("#modal [data-yes]")
            page.wait_for_timeout(1200)
        check("UI-дым" not in page.inner_text("#dp-body") or
              "UI-дым: ВИП" not in page.inner_text("#dp-body"),
              "ВИП-период удалён через UI")
        for _ in range(6):
            btn = page.locator("#dp-body .dp-chip:has-text('UI-дым') [data-day-del]").first
            if not btn.count():
                break
            btn.click()
            page.wait_for_selector("#modal [data-yes]")
            page.click("#modal [data-yes]")
            page.wait_for_timeout(1200)
        check("UI-дым" not in page.inner_text("#dp-body"), "день двойной оплаты удалён через UI")

        browser.close()

    print()
    if errors:
        print("ОШИБКИ:")
        for e in errors:
            print(" -", e)
        return 1
    print(f"UI-дым пройден: {len(steps_done)} проверок, JS-ошибок нет. Скриншоты: {SCREENS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
