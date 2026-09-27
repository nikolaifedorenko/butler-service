#!/usr/bin/env python3
"""Патч app.js: (1) баг сохранения правил — селектор захватывал файловые инпуты
шаблонов документов; (2) кнопки PDF в «Графике» и «Табеле»; (3) график
только-для-просмотра для батлеров. Запуск: ./.venv/bin/python tools/patch_readonly_pdf_js.py"""
from pathlib import Path

P = Path(__file__).resolve().parent.parent / "static" / "js" / "app.js"
s = P.read_text(encoding="utf-8")
n0 = len(s)


def rep(old: str, new: str, count: int = 1) -> None:
    global s
    found = s.count(old)
    assert found == count, f"ожидал {count} вхождений, нашёл {found}: {old[:80]!r}"
    s = s.replace(old, new)


# ── 1. БАГ: «Сохранить правила» → 422. Селектор '.rule-row input' захватывал
#     четыре <input type="file"> из панели шаблонов документов (.docx) — без
#     data-k, поэтому в payload улетали {"value":""} без key.
rep("""    $$('.rule-row input').forEach(i => {""",
    """    // только поля правил (у них есть data-k): класс .rule-row используется и в
    // панели шаблонов документов, где лежат файловые инпуты — они ломали сохранение (422)
    $$('.rule-row input[data-k]').forEach(i => {""")

# ── 2a. downloadBlob: показывать человечную подсказку сервера (detail) ──
rep("""    const res = await fetch(path, { credentials: 'same-origin' });
    if (!res.ok) throw new Error(`Ошибка ${res.status}`);""",
    """    const res = await fetch(path, { credentials: 'same-origin' });
    if (!res.ok) {
      // в detail сервер отдаёт понятный текст (например, подсказку про PDF-движок)
      let msg = `Ошибка ${res.status}`;
      try { const j = JSON.parse(await res.text()); if (typeof j?.detail === 'string') msg = j.detail; } catch { /* не JSON */ }
      throw new Error(msg);
    }""")

# ── 3a. Вкладка «График» видна всем (батлеры — только просмотр плана) ──
rep("""  if (manager) tabs.push({ id: 'schedule', title: 'График' });""",
    """  tabs.push({ id: 'schedule', title: 'График' });   // план видят все; батлеры — только просмотр""")

# ── 3b. scheduleShell: режим «только просмотр» (баннер, без менеджерских кнопок)
#        + кнопка PDF рядом с «Печать» ──
rep("""function scheduleShell() {
  return `
  <div class="page-head">
    <div>
      <h2>График смен</h2>
      <div class="sub">Смены 1/2 считаются базовым циклом объекта (Настройки); у «Пятидневки» и «Других смен»
        шаблон задаётся в карточке сотрудника. Вручную назначают только отсутствия и исключения</div>
    </div>""",
    """function scheduleShell() {
  const ro = state.user?.role === 'employee';   // батлеры: график только на просмотр
  return `
  <div class="page-head">
    <div>
      <h2>График смен</h2>
      <div class="sub">${ro
        ? 'План смен на месяц — так же, как его видит менеджер. Правки вносит менеджер'
        : `Смены 1/2 считаются базовым циклом объекта (Настройки); у «Пятидневки» и «Других смен»
        шаблон задаётся в карточке сотрудника. Вручную назначают только отсутствия и исключения`}</div>
    </div>""")

rep("""    <button class="btn btn-sm" id="m-today">Сегодня</button>
  </div>

  <div class="grid-tools">""",
    """    <button class="btn btn-sm" id="m-today">Сегодня</button>
  </div>
  ${ro ? `<div class="ro-banner">Режим «только просмотр»: виден план смен без отметок,
    переработок и часов. Назначать и менять смены может менеджер.</div>` : ''}

  <div class="grid-tools">""")

rep("""    <div class="seg" id="grid-mode" title="План — как по графику; Факт — реальное присутствие по отметкам">
      <button data-mode="plan">План</button>
      <button data-mode="fact">Факт</button>
    </div>
    <div class="spacer" style="flex:1"></div>
    <button class="btn btn-sm" id="btn-range">Назначить отсутствие</button>
    <button class="btn btn-sm" id="btn-clear">Обнулить месяц</button>
    <button class="btn btn-sm" id="btn-xlsx">Excel</button>
    <button class="btn btn-sm btn-ghost" id="btn-print">Печать</button>
  </div>""",
    """    ${ro ? '' : `<div class="seg" id="grid-mode" title="План — как по графику; Факт — реальное присутствие по отметкам">
      <button data-mode="plan">План</button>
      <button data-mode="fact">Факт</button>
    </div>`}
    <div class="spacer" style="flex:1"></div>
    ${ro ? '' : `<button class="btn btn-sm" id="btn-range">Назначить отсутствие</button>
    <button class="btn btn-sm" id="btn-clear">Обнулить месяц</button>
    <button class="btn btn-sm" id="btn-xlsx">Excel</button>`}
    <button class="btn btn-sm btn-ghost" id="btn-print">Печать</button>
    <button class="btn btn-sm btn-ghost" id="btn-pdf" title="Скачать PDF: файл собирает сервер">PDF</button>
  </div>""")

# ── 3c. bindScheduleToolbar: PDF-кнопка; менеджерские кнопки — только если есть ──
rep("""  $('#btn-print').onclick = printGrid;
  $('#btn-xlsx').onclick = () => downloadBlob(`/api/schedule/xlsx?year=${state.year}&month=${state.month}`, 'grafik.xlsx');
  $('#btn-range').onclick = openRangeModal;
  $('#btn-clear').onclick = () => confirmDialog(""",
    """  const ro = state.user?.role === 'employee';
  if (ro) state.gridMode = 'plan';   // «Факт» — данные менеджера, у батлера их нет в ответе
  $('#btn-print').onclick = printGrid;
  $('#btn-pdf').onclick = () => downloadBlob(`/api/schedule/pdf?year=${state.year}&month=${state.month}`, 'grafik.pdf');
  if ($('#btn-xlsx')) $('#btn-xlsx').onclick = () => downloadBlob(`/api/schedule/xlsx?year=${state.year}&month=${state.month}`, 'grafik.xlsx');
  if ($('#btn-range')) $('#btn-range').onclick = openRangeModal;
  if ($('#btn-clear')) $('#btn-clear').onclick = () => confirmDialog(""")

# ── 3d. loadSchedule: батлеру подгрузить словарь смен для легенды ──
rep("""async function loadSchedule() {
  $('#view-schedule').innerHTML = scheduleShell();
  bindScheduleToolbar();
  const data = await api(`/api/schedule?year=${state.year}&month=${state.month}`);""",
    """async function loadSchedule() {
  $('#view-schedule').innerHTML = scheduleShell();
  bindScheduleToolbar();
  if (state.user?.role === 'employee' && !state.shiftTypes.length) {
    // легенде сетки нужен словарь смен (справочник сотрудников батлерам недоступен)
    try { state.shiftTypes = await api('/api/shift-types', { silent: true }); } catch { state.shiftTypes = []; }
  }
  const data = await api(`/api/schedule?year=${state.year}&month=${state.month}`);""")

# ── 3e. renderGrid: в режиме просмотра ячейки не кликаются ──
rep("""    $('#grid-host').innerHTML = `<table class="sched"><thead>${head}</thead><tbody>${body}</tbody></table>`;
    $$('#grid-host .cellbtn:not([disabled])').forEach(btn => btn.onclick = () => openCellModal(+btn.dataset.emp, btn.dataset.date));""",
    """    $('#grid-host').innerHTML = `<table class="sched"><thead>${head}</thead><tbody>${body}</tbody></table>`;
    if (state.user?.role === 'employee') {
      $('#grid-host').classList.add('ro');   // только просмотр: клики по ячейкам отключены
    } else {
      $$('#grid-host .cellbtn:not([disabled])').forEach(btn => btn.onclick = () => openCellModal(+btn.dataset.emp, btn.dataset.date));
    }""")

# ── 2b. Табель: кнопка PDF рядом с «Печать» ──
rep("""      <button class="btn btn-sm btn-ghost" id="t-print">Печать</button>""",
    """      <button class="btn btn-sm btn-ghost" id="t-print">Печать</button>
      <button class="btn btn-sm btn-ghost" id="t-pdf" title="Скачать PDF: файл собирает сервер">PDF</button>""")

rep("""  $('#t-print').onclick = printTimesheet;""",
    """  $('#t-print').onclick = printTimesheet;
  $('#t-pdf').onclick = () => downloadBlob(`/api/timesheet/pdf?year=${state.year}&month=${state.month}`, 'tabel.pdf');""")

P.write_text(s, encoding="utf-8")
print(f"OK: app.js пропатчен ({n0} → {len(s)} байт)")
