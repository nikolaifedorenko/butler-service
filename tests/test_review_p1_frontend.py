"""Стражи находок P1 внешнего ревью от 20.10.2026 — батч «фронтенд» (батч 4 плана).

Фронтенд — скрипты без сборки (ADR-0008): юнит-тестов на JS в проекте нет,
поэтому стражи здесь двух видов (прецедент — source-сканы test_review_p0.py):

* **source-сканы** — закрепляют структуру фикса в исходниках (находка не
  вернётся молча: удаление защиты роняет тест);
* **поведенческий прогон ``httpError``** через node (чистая функция, DOM не
  нужен): 422-массив pydantic → «поле: причина», структурный 409 сохраняет
  контракт payload/status.

Находки:

* **P1-fe-1** — ``resetUserViewState`` сбрасывает ВСЁ пользовательское
  состояние: кэши справочников, сетки, фильтры, позицию UI, состояния модулей
  (carsState/nightState/settingsUI) и DOM разделов; ``searchBound`` не
  сбрасывается (стережёт одноразовую привязку document-листнера ⌘K);
* **P1-fe-2** — селектор «Значение рабочего дня» в ``rehireModal`` строится из
  ``/api/tabel-values`` (как в модалке перевода блока), а не из словаря типов
  смен (``workShifts`` давали пустые option «undefined · undefined»);
* **P1-fe-3** — ``double_title`` в title ячейки Графика экранируется (``esc``);
* **P1-fe-4** — ошибка HTTP-ответа собирается ``httpError``: 422-массив
  pydantic не попадает в тост сырым JSON;
* **P1-fe-5** — ``loadMyHistory()`` вызывается с ``.catch`` (сбой истории —
  локальная плашка, а не unhandledrejection с общим тостом);
* **P1-fe-6** — ``settingsRenderScreen`` под стражей поколения рендера
  (``settingsRenderGen``) и рендерит в свежий узел (``cloneNode`` +
  ``replaceWith``): запоздалый рендер прежнего экрана не перезаписывает новый.

Поведение в сборке дополнительно стерегут смоуки (run_ui_check на трёх ролях,
сценарии settings/layers/norms/night_zones/night_cars) и ESLint no-undef.
"""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

import pytest

BASE = pathlib.Path(__file__).resolve().parent.parent
JS = BASE / "static" / "js"


def _src(rel: str) -> str:
    return (JS / rel).read_text(encoding="utf-8")


def _body(src: str, fn_name: str) -> str:
    """Тело функции/блока от `fn_name` до первой закрывающей `}` в колонке 0."""
    start = src.index(fn_name)
    end = re.search(r"^}", src[start:], re.M)
    return src[start:start + end.end()] if end else src[start:]


# ── P1-fe-1: resetUserViewState — полный сброс ────────────────────────────────

def test_fe1_reset_clears_caches_modules_and_dom():
    body = _body(_src("app.js"), "function resetUserViewState()")
    # кэши справочников и данных
    for needle in ("state.employees = []", "state.shiftTypes = []",
                   "state.departments = []", "state.subdivisions = []",
                   "state.docKinds = []", "state.docPlaceholders = {}",
                   "state.tabelCodes = []", "state.grid = null",
                   "state.timesheet = null", "state.status = null"):
        assert needle in body, f"resetUserViewState не сбрасывает {needle!r}"
    # фильтры и позиция UI — на «сегодня» по часам объекта
    for needle in ("state.filterDept = 'all'", "state.filterText = ''",
                   "state.expanded = new Set()", "state.attDate = todayISO()",
                   "serverShiftMs"):
        assert needle in body, f"resetUserViewState не сбрасывает {needle!r}"
    # состояния модулей (ADR-0008 — глобалы разделов)
    for needle in ("carsState", "nightState", "settingsUI"):
        assert needle in body, f"resetUserViewState не сбрасывает {needle}"
    # DOM разделов — в начальное пустое состояние
    assert "$$('.view')" in body


def test_fe1_reset_keeps_search_bound_flag():
    """searchBound — флаг ОДНОРАЗОВОЙ привязки document-листнера ⌘K (не снимается):
    сброс флага удвоил бы обработчик при следующем входе в настройки."""
    body = _body(_src("app.js"), "function resetUserViewState()")
    assert not re.search(r"searchBound\s*[:=]", body)


# ── P1-fe-2: rehireModal — значение рабочего дня из /api/tabel-values ─────────

def test_fe2_rehire_pattern_uses_tabel_values():
    src = _src("modules/employees.js")
    body = _body(src, "async function rehireModal(")
    assert "/api/tabel-values" in body, "rehireModal не грузит значения Табеля"
    assert "patternFieldsHtml('rh', kind, values, today)" in body
    # словарь типов смен больше не подменяет значения Табеля (упоминание в
    # комментарии допустимо — проверяем отсутствие объявления и обращения)
    assert "state.shiftTypes" not in body
    assert not re.search(r"^\s*(?:const|let|var)\s+workShifts\b", body, re.M)


# ── P1-fe-3: double_title экранирован ─────────────────────────────────────────

def test_fe3_double_title_escaped():
    offenders = []
    for path in sorted(JS.rglob("*.js")):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"double_title", text):
            line = text[text.rfind("\n", 0, m.start()) + 1:text.find("\n", m.end())]
            if "esc(" not in line:
                offenders.append(f"{path.name}: {line.strip()[:100]}")
    assert offenders == []


# ── P1-fe-4: httpError — 422 не сырым JSON ────────────────────────────────────

def test_fe4_api_uses_http_error():
    core = _src("core.js")
    assert "function httpError(msg, status)" in core
    assert "Array.isArray(msg)" in _body(core, "function httpError(")
    # оба транспорта бросают через общий разбор
    assert core.count("throw httpError(msg, res.status)") == 2, \
        "api() и multipartApi() обязаны использовать httpError"


@pytest.mark.skipif(shutil.which("node") is None, reason="node недоступен")
def test_fe4_http_error_behaviour():
    """Прогон чистой функции в node: 422-массив → «поле: причина»; структурный
    409 сохраняет контракт (message/payload/status); строковый detail — как был."""
    core = _src("core.js")
    fn = re.search(r"function httpError\(msg, status\) \{[\s\S]*?\n\}", core).group(0)
    script = fn + """
const e1 = httpError([{ loc: ['body', 'year'], msg: 'Input should be a valid integer',
                        type: 'int_parsing' }], 422);
if (e1.message !== 'year: Input should be a valid integer') { console.error('422:', e1.message); process.exit(1); }
if (e1.status !== 422 || !Array.isArray(e1.payload)) process.exit(2);
const e2 = httpError({ message: 'Перехват области', area: 7 }, 409);
if (e2.message !== 'Перехват области' || e2.payload.area !== 7 || e2.status !== 409) process.exit(3);
const e3 = httpError('Период закрыт', 409);
if (e3.message !== 'Период закрыт' || e3.status !== undefined) process.exit(4);
const e4 = httpError([], 422);
if (e4.message !== 'Ошибка 422') process.exit(5);
process.exit(0);
"""
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr or proc.stdout


# ── P1-fe-5: loadMyHistory — вызов с catch ────────────────────────────────────

def test_fe5_load_my_history_has_catch():
    src = _src("modules/me.js")
    calls = [m for m in re.finditer(r"loadMyHistory\(\)", src)
             if not src[max(0, m.start() - 9):m.start()].endswith("function ")]
    assert calls, "loadMyHistory() не вызывается — раздел «Я» без истории?"
    for m in calls:
        tail = src[m.end():m.end() + 20]
        assert tail.startswith(".catch("), \
            f"вызов loadMyHistory() без .catch: …{src[m.start():m.end() + 20]}"


# ── P1-fe-6: гонка settingsRenderScreen ───────────────────────────────────────

def test_fe6_settings_render_guarded_by_generation():
    src = _src("modules/settings.js")
    assert re.search(r"^let settingsRenderGen = 0;", src, re.M), \
        "нет счётчика поколений рендера"
    body = _body(src, "async function settingsRenderScreen()")
    # свежий узел: запоздалый рендер пишет в отсоединённый старый узел
    assert "old.cloneNode(false)" in body and "old.replaceWith(body)" in body
    # поколение: инкремент на входе, страж в обработке сбоя и страж перед
    # обновлением черновых панелей
    assert "++settingsRenderGen" in body
    assert "gen === settingsRenderGen" in body
    assert "gen !== settingsRenderGen" in body
