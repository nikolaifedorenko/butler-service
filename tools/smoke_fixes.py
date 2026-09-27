#!/usr/bin/env python3
"""UI-дым для трёх правок: сохранение правил (баг 422), кнопки PDF в «Графике»/«Табеле»,
график «только просмотр» для батлера. Любая JS-ошибка на странице — провал.
Запуск: ./.venv/bin/python tools/smoke_fixes.py   (сервер на 127.0.0.1:8000)
"""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
SCREENS = Path(__file__).resolve().parent / "screens"
SCREENS.mkdir(exist_ok=True)

errors: list[str] = []
steps: list[str] = []


def check(cond: bool, msg: str) -> None:
    if cond:
        steps.append(msg)
        print("  ✓", msg, flush=True)
    else:
        errors.append(f"ПРОВАЛ: {msg}")
        print("  ✗", msg, flush=True)


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
            if "favicon" in url or "401" in text or "/api/auth/me" in url:
                return
            errors.append(f"JS console.error: {text}")

        page.on("console", _on_console)
        page.set_default_timeout(20000)

        # ── вход администратором ──
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_selector("#login-username", timeout=15000)
        page.fill("#login-username", "admin")
        page.fill("#login-password", "demo1234")
        page.click("#login-form button[type=submit]")
        page.wait_for_selector("#app:not(.hidden)", timeout=15000)
        check(True, "вход администратором")

        # ── 1. БАГ: «Сохранить правила» больше не падает с 422 ──
        page.click(".nav-item[data-view=settings]")
        page.wait_for_selector("#s-save", timeout=15000)
        puts: dict = {}

        def _on_resp(resp):
            if resp.request.method == "PUT" and resp.url.rstrip("/").endswith("/api/settings"):
                puts["status"] = resp.status
                puts["body"] = resp.request.post_data

        page.on("response", _on_resp)
        page.click("#s-save")
        page.wait_for_selector(".toast:has-text('Правила сохранены')", timeout=15000)
        page.wait_for_timeout(400)
        check(puts.get("status") == 200, f"PUT /api/settings → 200 (было 422), факт: {puts.get('status')}")
        payload = json.loads(puts.get("body") or "[]")
        check(len(payload) > 0 and all("key" in i and isinstance(i["key"], str) for i in payload),
              f"в payload только поля с key ({len(payload)} шт., мусора нет)")
        page.screenshot(path=str(SCREENS / "94-settings-save-ok.png"))

        # ── 2. PDF в графике и табеле ──
        page.click(".nav-item[data-view=schedule]")
        page.wait_for_selector("#grid-host table.sched", timeout=15000)
        check(page.is_visible("#btn-pdf"), "в «Графике» есть кнопка PDF рядом с «Печать»")
        with page.expect_download(timeout=60000) as dl:
            page.click("#btn-pdf")
        name = dl.value.suggested_filename
        check(name.startswith("grafik_") and name.endswith(".pdf"), f"скачался {name}")
        page.locator(".grid-tools").screenshot(path=str(SCREENS / "95-schedule-pdf-btn.png"))

        page.click(".nav-item[data-view=timesheet]")
        page.wait_for_selector("#t-body table", timeout=20000)
        check(page.is_visible("#t-pdf"), "в «Табеле» есть кнопка PDF рядом с «Печать»")
        with page.expect_download(timeout=60000) as dl2:
            page.click("#t-pdf")
        name2 = dl2.value.suggested_filename
        check(name2.startswith("tabel_") and name2.endswith(".pdf"), f"скачался {name2}")

        # ── 3. батлер: график только на просмотр ──
        page.click("#logout-btn")
        page.wait_for_selector("#login-username", timeout=15000)
        page.fill("#login-username", "sokolova")
        page.fill("#login-password", "demo1234")
        page.click("#login-form button[type=submit]")
        page.wait_for_selector("#app:not(.hidden)", timeout=15000)
        role = page.evaluate("() => window.state ? state.user.role : (document.querySelector('#user-role')||{}).textContent")
        check(any(w in str(role).lower() for w in ("employee", "батлер", "сотрудник")),
              f"вошли батлером ({role})")

        check(page.is_visible(".nav-item[data-view=schedule]"), "у батлера есть вкладка «График»")
        page.click(".nav-item[data-view=schedule]")
        page.wait_for_selector("#grid-host table.sched", timeout=20000)
        check(page.is_visible(".ro-banner"), "плашка «только просмотр» видна")
        check(not page.locator("#btn-range").count() and not page.locator("#btn-xlsx").count()
              and not page.locator("#grid-mode").count(),
              "нет менеджерских кнопок (назначить отсутствие, обнулить, Excel, вид «Факт»)")
        check(page.is_visible("#btn-print") and page.is_visible("#btn-pdf"),
              "печать и PDF батлеру доступны")

        # клик по ячейке не открывает модалку
        cell = page.locator("#grid-host .cellbtn:not([disabled])").first
        cell.evaluate("el => el.click()")   # синтетически: pointer-events:none не пускает мышь
        page.wait_for_timeout(700)
        check(page.locator("#modal-backdrop").evaluate("el => el.classList.contains('hidden')"),
              "клик по ячейке не открывает редактор (только просмотр)")

        ro = page.evaluate("""async () => {
            const r = await fetch('/api/schedule?year=' + state.year + '&month=' + state.month,
                                 { credentials: 'same-origin' });
            const d = await r.json();
            const cells = Object.values(d.rows[0].cells);
            return { status: r.status, readonly: d.readonly,
                     hasFact: cells.some(c => c.fact), hasNote: cells.some(c => c.note),
                     hasBalance: 'balance_hours' in d.rows[0].employee,
                     hasShift: cells.some(c => c.shift) };
        }""")
        check(ro["status"] == 200 and ro["readonly"] is True and not ro["hasFact"]
              and not ro["hasNote"] and not ro["hasBalance"] and ro["hasShift"],
              f"API батлеру: план без факта/заметок/банка ({ro})")

        with page.expect_download(timeout=60000) as dl3:
            page.click("#btn-pdf")
        name3 = dl3.value.suggested_filename
        check(name3.startswith("grafik_") and name3.endswith(".pdf"),
              f"батлер скачивает PDF своего плана ({name3})")
        page.locator("#view-schedule").screenshot(path=str(SCREENS / "96-ro-schedule.png"))

        browser.close()

    print()
    if errors:
        print("ПРОВАЛЕНО проверок:", len(errors))
        for e in errors:
            print(" -", e)
        return 1
    print(f"ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ: {len(steps)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
