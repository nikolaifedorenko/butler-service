'use strict';
/* ══ ГРАФИК: сетка «ФИО × дни», печать сетки, редакторы ячейки и периода ══
   Вынесено из app.js (15.10.2026) без изменения логики: границы разделов —
   файлами (сборки намеренно нет, ADR-0008), общие функции — через глобальную
   область (реестр tools/js_globals.json, ESLint no-undef ловит пропуски). */

async function loadSchedule() {
  $('#view-schedule').innerHTML = scheduleShell();
  bindScheduleToolbar();
  if (state.user?.role === 'employee' && !state.shiftTypes.length) {
    // легенде сетки нужен словарь смен (справочник сотрудников батлерам недоступен)
    try { state.shiftTypes = await api('/api/shift-types', { silent: true }); } catch { state.shiftTypes = []; }
  }
  const data = await api(`/api/schedule?year=${state.year}&month=${state.month}`);
  state.grid = data;
  state.scrollToToday = true;    // после загрузки месяца докрутить сетку к сегодняшнему числу
  renderGrid();
}

function scheduleShell() {
  const ro = !can('schedule.edit');   // без права «Редактирование графика» — только просмотр
  return `
  <div class="page-head">
    <div>
      <h2>Слой 1 · План / График</h2>
      <div class="sub">${ro
        ? 'План смен на месяц — так же, как его видит менеджер. Правки вносит менеджер'
        : 'График генерируется из Табеля по окнам CFG-WINDOWS; ручная смена заменяет генерацию дня. «Пропуск/отлучка» — согласованное отсутствие: смена показывается разрезанной, на часы не влияет'}</div>
    </div>
    <div class="spacer"></div>
    <div class="month-nav">
      <button id="m-prev" title="Предыдущий месяц">‹</button>
      <div class="label" id="m-label">—</div>
      <button id="m-next" title="Следующий месяц">›</button>
    </div>
    <button class="btn btn-sm" id="m-today">Сегодня</button>
  </div>
  ${ro ? `<div class="ro-banner">Режим «только просмотр»: виден план смен без отметок,
    переработок и часов. Назначать и менять смены может менеджер.</div>` : ''}

  <div class="grid-tools">
    <input id="f-text" type="text" placeholder="Поиск по ФИО…" style="max-width:210px">
    <div class="spacer" style="flex:1"></div>
    ${ro ? '' : `<button class="btn btn-sm" id="btn-range" title="Слой 1 · График: только «за счёт часов» — в Табеле остаётся явка, часы не меняются">Отпросить (выходной за часы)</button>
    <button class="btn btn-sm" id="btn-clear">Обнулить месяц</button>
    <button class="btn btn-sm" id="btn-xlsx">Excel</button>`}
    <button class="btn btn-sm btn-ghost" id="btn-print">Печать</button>
    <button class="btn btn-sm btn-ghost" id="btn-pdf" title="Скачать PDF: файл собирает сервер">PDF</button>
  </div>

  <div class="grid-scroll" id="grid-host"><div class="empty">Загрузка…</div></div>
  <div class="legend" id="grid-legend"></div>`;
}

function bindScheduleToolbar() {
  const shiftMonth = delta => {
    let m = state.month + delta, y = state.year;
    if (m < 1) { m = 12; y--; } if (m > 12) { m = 1; y++; }
    state.month = m; state.year = y; loadSchedule();
  };
  $('#m-prev').onclick = () => shiftMonth(-1);
  $('#m-next').onclick = () => shiftMonth(1);
  $('#m-today').onclick = () => { const d = new Date(); state.year = d.getFullYear(); state.month = d.getMonth() + 1; loadSchedule(); };
  $('#btn-print').onclick = printGrid;
  $('#btn-pdf').onclick = () => downloadBlob(`/api/schedule/pdf?year=${state.year}&month=${state.month}`, 'grafik.pdf');
  if ($('#btn-xlsx')) $('#btn-xlsx').onclick = () => downloadBlob(`/api/schedule/xlsx?year=${state.year}&month=${state.month}`, 'grafik.xlsx');
  if ($('#btn-range')) $('#btn-range').onclick = () => openRangeModal('schedule');
  if ($('#btn-clear')) $('#btn-clear').onclick = () => confirmDialog(
    'Обнулить месяц?',
    `Строки Табеля и сгенерированный График за ${MONTHS[state.month - 1]} ${state.year} будут удалены
     (месяц вернётся к пустому Табелю; заполните его из циклов во вкладке «Табель»).
     Закрытые периоды не трогаются.`,
    async () => {
      const r = await api('/api/schedule/clear-month', { method: 'POST', body: { year: state.year, month: state.month } });
      toast(`Очищено строк Табеля: ${r.cleared}`, 'ok');
      loadSchedule();
    });

  $('#f-text').value = state.filterText;
  $('#f-text').oninput = e => { state.filterText = e.target.value; renderGrid(); };
}

const GROUP_ORDER_UI = ['Смена 1', 'Смена 2', 'Пятидневка', 'Другие смены'];
function groupOrder(name) {
  const n = name === 'Администрация' ? 'Пятидневка' : (name || '');   // старое название блока
  const i = GROUP_ORDER_UI.indexOf(n);
  if (i >= 0) return i;
  if (!name) return 999;
  return 100 + name.localeCompare(name, 'ru');
}

function filteredRows() {
  const q = state.filterText.trim().toLowerCase();
  return (state.grid?.rows || []).filter(r => {
    if (q && !r.employee.full_name.toLowerCase().includes(q) && !(r.employee.position || '').toLowerCase().includes(q)) return false;
    return true;
  });
}

function renderGrid() {
  const g = state.grid;
  if (!g) return;
  $('#m-label').textContent = `${MONTHS[g.month - 1]} ${g.year}`;
  const rows = filteredRows();
  if (!rows.length) {
    $('#grid-host').innerHTML = '<div class="empty">Сотрудники не найдены</div>';
  } else {
    const head = `<tr><th class="corner">ФИО</th>${g.days.map(d =>
      `<th class="${d.is_weekend ? 'weekend' : ''} ${d.is_today ? 'today' : ''}${d.double_scope ? ' double-day' : ''}"
        title="${dateRu(d.date)}${d.double_scope ? ' · день двойной оплаты (' + (d.double_title || '') + '): переработки идут кодами ДЯ2/ДН2' : ''}">
        <span class="dow">${esc(d.weekday)}</span>${d.day}${d.double_scope ? '<span class="dbl-mark">×2</span>' : ''}</th>`).join('')}<th>Итого</th></tr>`;

    /* блоки: Смена 1, Смена 2, Пятидневка, Другие смены; сотрудник виден в каждом своём блоке */
    const blocksOf = r => (r.blocks && r.blocks.length)
      ? r.blocks
      : (r.employee.schedule_group
        ? [{ group: r.employee.schedule_group, start: '0000-01-01', end: null }] : []);
    const groups = {};
    rows.forEach(r => blocksOf(r).forEach(b => { (groups[b.group] ||= []).push({ r, b }); }));
    rows.forEach(r => { if (!blocksOf(r).length) (groups[''] ||= []).push({ r, b: null }); });
    const keys = Object.keys(groups).sort((a, b) =>
      groupOrder(a) - groupOrder(b) || a.localeCompare(b, 'ru'));

    const body = keys.map(key => {
      const list = groups[key];
      const color = list[0]?.r.employee.group_color || '#8a94a6';
      /* заголовок блока: первая ячейка «липкая» — не уезжает при горизонтальной прокрутке,
         остальную строку заполняет ячейка-фон (исправление уезжавших заголовков) */
      const header = `<tr class="group-row"><td class="g-name">
        <span class="g-dot" style="background:${color}"></span>${esc(key || 'Без группы')}
        <span class="g-count">${list.length} ${plural(list.length, 'сотрудник', 'сотрудника', 'сотрудников')}</span></td>
        <td class="gfill" colspan="${g.days.length + 1}"></td></tr>`;
      return header + list.map(({ r, b }) => empRow(r, g, b)).join('');
    }).join('');

    $('#grid-host').innerHTML = `<table class="sched"><thead>${head}</thead><tbody>${body}</tbody></table>`;
    if (state.user?.role === 'employee') {
      $('#grid-host').classList.add('ro');   // только просмотр: клики по ячейкам отключены
    } else {
      $$('#grid-host .cellbtn:not([disabled])').forEach(btn => btn.onclick = () => openCellModal(+btn.dataset.emp, btn.dataset.date));
    }
    if (state.scrollToToday) { state.scrollToToday = false; scrollGridToToday(); }
  }

  const usedCodes = {};
  rows.forEach(r => Object.values(r.cells || {}).forEach(c => {
    if (c.tabel && c.tabel.code) usedCodes[c.tabel.code] = c.tabel.value || c.tabel.code;
  }));
  $('#grid-legend').innerHTML = Object.keys(usedCodes).map(code =>
    `<span class="chip"><span class="swatch" style="background:${V4_CODE_COLORS[code] || '#8a94a6'}"></span>
      <b>${esc(code)}</b>${usedCodes[code] !== code ? ' ' + esc(usedCodes[code]) : ''}</span>`).join('') +
    `<span class="chip" title="Согласованное отсутствие (логический разрез смены): на часы не влияет, видно во флагах и на доске">
      <span class="swatch" style="background:#0e9aa7"></span><b>✂</b> пропуск/отлучка</span>
     <span class="chip" title="Ручная смена заменяет сгенерированную из Табеля">
      <span class="swatch" style="background:#5b6bd6"></span><b>Р</b> ручная смена</span>
     <span class="chip" title="Производственный календарь / ВИП-гости: переработки в эти дни оплачиваются вдвое (коды ДЯ2/ДН2)">
      <span class="dbl-mark legend-x2">×2</span><b>день двойной оплаты</b></span>`;
}

/* Кнопка «Сегодня»: месяц открыт, а сетка докручивается до сегодняшней колонки и подсвечивает её */
function scrollGridToToday() {
  const host = $('#grid-host');
  if (!host) return;
  requestAnimationFrame(() => {
    const th = host.querySelector('thead th.today');
    if (!th) return;
    const left = Math.max(0, th.offsetLeft - host.clientWidth / 2 + th.clientWidth / 2);
    host.scrollTo({ left, behavior: 'smooth' });
    th.classList.add('flash-today');
    setTimeout(() => th.classList.remove('flash-today'), 1800);
  });
}

function cellTd(r, d, c, cls) {
  const btn = (extra, inner, title, style) =>
    `<td class="${cls}"><button class="cellbtn ${extra}" data-emp="${r.employee.id}" data-date="${d.date}" title="${esc(title)}"${style ? ` style="${style}"` : ''}>${inner}</button></td>`;
  const t = c.tabel;
  const shifts = c.shifts || [];
  const absences = c.absences || [];
  const code = t ? t.code : '';
  const color = V4_CODE_COLORS[code] || '#8a94a6';
  const parts = [];
  if (t) parts.push(t.value || t.code);
  if (shifts.length) parts.push(shifts.map(x => `${x.start_hm}–${x.end_hm}`).join(' '));
  const manual = shifts.some(x => x.source === 'manual');
  const title = `${r.employee.short_name}, ${dateRu(d.date)}: ` +
    (t ? `Табель «${t.value || t.code}»${t.source === 'cycle' ? ' (из циклов)' : ' (вручную)'}` : 'Табель не заполнен') +
    (shifts.length ? ` · смена ${shifts.map(x => `${x.start_hm}–${x.end_hm}${x.source === 'manual' ? ' (ручная)' : ''}`).join(', ')}` : ' · смены нет') +
    (absences.length ? ` · согласованное отсутствие ${absences.map(a => `${a.start_hm}–${a.end_hm}${a.kind ? ' (' + a.kind.name + ')' : ''}`).join(', ')} — на часы не влияет` : '') +
    (t && t.note ? ` · ${t.note}` : '');
  const marks = [manual ? '<span class="manual-mark" title="Ручная смена">Р</span>' : '',
    absences.length ? '<span class="partial-mark" title="Согласованное отсутствие: смена показана разрезанной">✂</span>' : ''].join('');
  const inner = `${marks}<span class="t t-full">${esc(parts.join(' ') || '—')}</span><span class="t t-short">${esc(t ? (t.value || t.code).replace(' ', '') : '—')}</span>`;
  const style = code ? `background:linear-gradient(165deg, ${withAlpha(color, .30)}, ${withAlpha(color, .16)});color:#2c3440` : '';
  return btn(code ? '' : 'empty', inner, title, style);
}

function empRow(r, g, block) {
  const accent = r.employee.group_color || '#8a94a6';
  const ranges = block?.ranges || (block ? [{ start: block.start, end: block.end }] : []);
  const inBlock = iso => !ranges.length || ranges.some(rg =>
    iso >= rg.start && (!rg.end || iso <= rg.end));
  const cells = g.days.map(d => {
    const c = r.cells[d.date] || {};
    const cls = ['cell', d.is_weekend ? 'weekend' : '', d.is_today ? 'today' : ''].join(' ');
    const outOfBlock = ranges.length && !inBlock(d.date);
    if (outOfBlock) {
      return `<td class="${cls}"><button class="cellbtn" disabled
        title="Неактивно: в этот день сотрудник относится к другому блоку"
        style="background:${g.colors.out_of_block};color:#5d5670;cursor:default">—</button></td>`;
    }
    if (c.employed === false) {
      return `<td class="${cls}"><button class="cellbtn inactive" disabled
        title="Не в штате: сотрудник не работал в эту дату (до приёма или после увольнения)">—</button></td>`;
    }
    return cellTd(r, d, c, cls);
  }).join('');
  return `<tr class="emp-row">
    <td class="name-cell" style="box-shadow: inset 4px 0 0 ${accent}">
      <div class="nm" title="${esc(r.employee.full_name)}">${esc(r.employee.short_name || r.employee.full_name)}</div>
      <div class="pos"><span class="dot-pos" style="background:${accent}"></span>${esc(r.employee.position || '')}</div>
      <div class="tot">${hours(r.totals.planned_hours)} ч · ${r.totals.work_days} ${plural(r.totals.work_days, 'смена', 'смены', 'смен')}</div>
    </td>${cells}
    <td class="num" style="padding:8px 10px;font-weight:700">${hours(r.totals.planned_hours)}<small style="color:var(--muted);font-weight:400"> ч</small></td>
  </tr>`;
}


function printGrid() {
  const g = state.grid;
  if (!g) return;
  const rows = filteredRows();
  const groups = {};
  rows.forEach(r => (r.blocks || []).forEach(b => { (groups[b.group] ||= []).push({ r, b }); }));
  const keys = Object.keys(groups).sort((a, b) => groupOrder(a) - groupOrder(b));
  const body = keys.map(key => {
    const trs = groups[key].map(({ r, b }) => {
      const rgs = (b && b.ranges) || (b ? [{ start: b.start, end: b.end }] : []);
      const tds = g.days.map(d => {
        const c = r.cells[d.date] || {};
        const out = rgs.length && !rgs.some(rg => d.date >= rg.start && (!rg.end || d.date <= rg.end));
        if (c.employed === false) return `<td style="background:${g.colors.inactive || '#eceff4'};color:#98a2b3">—</td>`;
        if (out) return `<td style="background:${g.colors.out_of_block}">—</td>`;
        const t = c.tabel;
        const shifts = c.shifts || [];
        let txt = t ? (t.value || t.code) : '';
        if (shifts.length) txt += (txt ? '\n' : '') + shifts.map(x => `${x.start_hm}–${x.end_hm}`).join(' ');
        if ((c.absences || []).length) txt += '*';
        const color = t ? (V4_CODE_COLORS[t.code] || '#8a94a6') : null;
        return `<td${color ? ` style="background:${withAlpha(color, .22)}"` : ' class="muted"'}>${esc(txt)}</td>`;
      }).join('');
      return `<tr><td class="name">${esc(r.employee.full_name)}<br><span class="muted">${esc(r.employee.position || '')}</span></td>${tds}
        <td><b>${hours(r.totals.planned_hours)}</b></td></tr>`;
    }).join('');
    return `<tr class="group"><td colspan="${g.days.length + 2}">${esc(key.toUpperCase())}</td></tr>${trs}`;
  }).join('');
  const head = `<tr><th class="name">Сотрудник</th>${g.days.map(d =>
    `<th>${d.day}<br><span class="muted">${esc(d.weekday)}</span></th>`).join('')}<th>Часов</th></tr>`;
  printWindow(`График сменности ${MONTHS[g.month - 1]} ${g.year}`,
    `<h1>График сменности, ${MONTHS[g.month - 1]} ${g.year} г. (весь месяц)</h1>
     <p style="font-size:12px;color:#667">Значение Табеля и интервалы смен; * — согласованное отсутствие (логический разрез смены).</p>
     <table><thead>${head}</thead><tbody>${body}</tbody></table>`);
}


/* ── назначение отсутствия на период: два входа по слоям (Q4, норматив 12.10.2026) ──
   mode='schedule' — из «Графика»: только «за счёт часов» (отпросился / выходной за часы),
   Табель остаётся явкой, недостачу гасит банк (EX-29);
   mode='tabel' — из «Табеля»: виды с кодом Табеля (ОТ, ДО, Б, ОВ, НН…) — отсутствие
   это код первичного документа, там же печатаются заявления. */
function openRangeModal(mode = 'tabel') {
  const fromSchedule = mode === 'schedule';
  const first = `${state.year}-${String(state.month).padStart(2, '0')}-01`;
  const rows = (state.grid?.rows || state.tabel?.rows || []);
  const people = rows.length ? rows.map(r => r.employee)
    : (state.employees || []).map(e => ({ id: e.id, full_name: e.full_name, position: e.position }));
  const kinds = state.shiftTypes.filter(x => x.kind === 'absence' && !x.is_default_off
    && (fromSchedule ? !x.tzh_code : !!x.tzh_code));
  openModal({
    title: fromSchedule ? 'Отпросить (выходной за часы)' : 'Назначить отсутствие (код Табеля)',
    subtitle: fromSchedule
      ? 'Слой 1 · График: в Табеле остаётся явка, часы и план не меняются'
      : 'Слой 0 · Табель: отпуск, больничный, за свой счёт, оплачиваемый выходной — на период сразу',
    wide: true,
    body: `
      <div class="opt-group-title">Сотрудники</div>
      <div class="check-list" id="rg-emps">
        ${people.map(r => `<label><input type="checkbox" value="${r.id}">
          ${esc(r.full_name)} <small style="color:var(--muted)">· ${esc(r.position || '')}</small></label>`).join('')}
      </div>
      <div class="grid-2" style="margin-top:14px">
        <label class="field"><span>С</span><input type="date" id="rg-from" value="${first}"></label>
        <label class="field"><span>По (включительно)</span><input type="date" id="rg-to" value="${first}"></label>
      </div>
      <label class="field"><span>${fromSchedule ? 'Вид (из Графика — только «за счёт часов»)' : 'Вид отсутствия (код Табеля)'}</span><select id="rg-shift">
        ${kinds.map((x, i) => `<option value="${x.id}" ${!fromSchedule && (x.code === 'VACATION' || i === 0) ? 'selected' : ''}>${esc(x.name)} · код Табеля ${x.tzh_code ? `«${esc(x.tzh_code)}»` : 'не задан'}</option>`).join('')
          || '<option value="">— нет подходящих видов в словаре смен —</option>'}
      </select>
        <div class="hint" id="rg-mode-hint" style="margin-top:4px"></div></label>
      <label class="field"><span>Примечание</span>
        <input type="text" id="rg-note" placeholder="${fromSchedule ? 'Например: заявление согласовано 12.10' : 'Например: приказ №47 от 01.09.2026'}"></label>
      <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
        <input type="checkbox" id="rg-work-only" style="width:17px;height:17px;accent-color:var(--primary)">
        Только на рабочие дни по Табелю${fromSchedule ? ' (на плановые выходные «выходной за часы» не ставится)' : ''}
      </label>
      <p class="hint">${fromSchedule
        ? 'Отсутствие пишется в График на всё стандартное окно дня: сотрудник не ожидается, флагов нет, а неотработанные часы окна уходят в недостачу — её гасит банк часов при закрытии периода (Q8: назначение информационное, расчёт не меняется). Заявление печатается из ячейки дня в «Графике».'
        : 'В эти дни в Табель будет записан код отсутствия: смены в эти дни нет, сотрудник не ожидается, флагов нет. Часы и банк не меняются. Заявление печатается из ячейки дня в «Табеле» или из «Документов».'}
        Период может выходить за границы открытого месяца; дни до приёма и после увольнения
        пропускаются автоматически. Закрытые периоды не трогаются.</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Назначить</button>`,
    onMount(m) {
      const hint = $('#rg-mode-hint');
      if (hint) hint.textContent = fromSchedule
        ? 'Единая сущность «отпросился (выходной за часы)»: на весь день — из Графика, интервалом — в ячейке дня.'
        : 'Вид с кодом Табеля: отсутствие оформляется кодом первичного документа.';
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        const ids = $$('#rg-emps input:checked').map(i => +i.value);
        if (!ids.length) return toast('Отметьте сотрудников', 'warn');
        const kindId = +$('#rg-shift').value;
        if (!kindId) return toast('Выберите вид отсутствия', 'warn');
        const from = $('#rg-from').value, to = $('#rg-to').value;
        if (!from || !to || from > to) return toast('Проверьте даты периода', 'warn');
        try {
          const res = await api('/api/schedule/range-absence', { method: 'POST', body: {
            employee_ids: ids, first: from, last: to,
            shift_type_id: kindId, note: $('#rg-note').value.trim(),
            workdays_only: $('#rg-work-only').checked,
          } });
          closeModal();
          const what = res.mode === 'schedule_absence' ? 'дней в Графике' : 'ячеек Табеля';
          toast(`Отсутствие назначено: ${res.written} ${plural(res.written, 'ячейка', 'ячейки', 'ячеек')} (${what})`
            + (res.skipped ? `, пропущено ${res.skipped}` : ''), (res.errors || []).length ? 'warn' : 'ok',
            (res.errors || []).map(e => `${e.date}: ${e.error}`).slice(0, 6));
          const d0 = new Date(from + 'T12:00:00');
          if (d0.getFullYear() !== state.year || d0.getMonth() + 1 !== state.month) {
            state.year = d0.getFullYear();
            state.month = d0.getMonth() + 1;
          }
          if (fromSchedule) loadSchedule(); else loadTabel();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ── редактор ячейки Графика (16.3): ручная смена, согласованное отсутствие,
      переход в Табель за кодом дня ── */
function openCellModal(empId, dateISO) {
  const row = state.grid.rows.find(r => r.employee.id === empId);
  const cell = row?.cells?.[dateISO] || {};
  const d = new Date(dateISO + 'T00:00:00');
  const title = `${WD[d.getDay()]}, ${d.getDate()} ${MONTHS_GEN[d.getMonth()]} ${d.getFullYear()}`;
  const workShifts = state.shiftTypes.filter(x => x.kind === 'work' && !x.archived_at);
  /* Из Графика назначается ТОЛЬКО «за счёт часов» (Q4): виды без кода Табеля. Отпуск,
     больничный, за свой счёт и оплачиваемый выходной — коды первичного документа, они
     ставятся в Табеле (слой 0), там же печатаются заявления. */
  const absenceKinds = state.shiftTypes.filter(x => x.kind === 'absence' && !x.is_default_off
    && !x.tzh_code && !x.archived);
  const t = cell.tabel;
  const shifts = cell.shifts || [];
  const absences = cell.absences || [];
  const editable = cell.editable !== false;

  openModal({
    title: row?.employee.full_name || 'Сотрудник',
    subtitle: `${title} · ${row?.employee.position || ''}`,
    body: `
      <div class="status-line"><span class="k">Табель (первичный документ)</span>
        <span class="v">${t ? esc(t.value || t.code) + (t.source === 'cycle' ? ' · из циклов' : ' · вручную') : 'не заполнен'}</span></div>
      <div style="display:flex;gap:8px;margin:8px 0 4px">
        <button class="btn btn-sm" id="cell-tabel">Изменить код Табеля…</button>
      </div>
      <div class="opt-group-title">Смены дня (График генерируется из Табеля по окнам)</div>
      ${shifts.length ? shifts.map(x => `<div class="status-line">
          <span class="k">${esc(x.start_hm)}–${esc(x.end_hm)} ${x.source === 'manual' ? '· ручная' : '· из Табеля'}${x.note ? ' · ' + esc(x.note) : ''}</span>
          <span class="v"></span></div>`).join('')
        : '<p class="hint" style="margin:4px 0">Смен нет: значение Табеля без часов (выходной/отсутствие) либо Табель не заполнен.</p>'}
      ${editable ? `
      <div id="manual-block" style="margin-top:10px;border:1px solid var(--line);border-radius:12px;padding:12px 14px 8px;background:#f8fbfd">
        <div class="opt-group-title" style="margin-top:0">Ручная смена (заменяет генерацию дня целиком)</div>
        <label class="field"><span>Пресет из словаря</span><select id="cell-preset">
          <option value="">— задать время вручную —</option>
          ${workShifts.map(x => `<option value="${x.start_time}|${x.end_time}|${x.overnight ? 1 : 0}">${esc(x.name)}</option>`).join('')}
        </select></label>
        <div class="grid-2">
          <label class="field"><span>Начало</span><input type="time" id="cell-sh-from" value="09:00"></label>
          <label class="field"><span>Конец</span><input type="time" id="cell-sh-until" value="18:00"></label>
        </div>
        <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
          <input type="checkbox" id="cell-sh-next" style="width:17px;height:17px;accent-color:var(--primary)">
          Заканчивается на следующие сутки (смена через полночь)
        </label>
        <div style="display:flex;gap:8px;margin:8px 0 6px;flex-wrap:wrap">
          <button class="btn btn-sm btn-primary" id="cell-sh-save">Сохранить ручную смену</button>
          ${shifts.some(x => x.source === 'manual') ? '<button class="btn btn-sm btn-danger" id="cell-sh-drop">Вернуть к генерации из Табеля</button>' : ''}
        </div>
        <p class="hint" style="margin:2px 0 6px">День редактируем, если его код Табеля принимает коды УТ
          (accepts_ut = Да). Ручная смена может пересекать полночь; на часы влияет только Табель —
          правка Графика меняет флаги и доску, но не расчёт (RUL-SCHEDULE-ONLY-FLAGS).</p>
      </div>` : '<p class="hint">Ручную смену в этот день поставить нельзя: код Табеля не принимает коды УТ (день-якорь).</p>'}
      <div class="opt-group-title" style="margin-top:12px">Отпросился (выходной за часы) — согласованные отсутствия дня</div>
      ${absences.map(a => `<div class="status-line">
          <span class="k">✂ ${esc(a.start_hm)}–${esc(a.end_hm)}${a.kind ? ' · ' + esc(a.kind.name) : ''}${a.note ? ' · ' + esc(a.note) : ''}</span>
          <span class="v"><button class="btn btn-sm btn-ghost" data-abs-del="${a.id}">Удалить</button></span></div>`).join('') || ''}
      <div style="margin-top:8px;border:1px solid var(--line);border-radius:12px;padding:12px 14px 8px;background:#f8fbfd">
        <div class="opt-group-title" style="margin-top:0">Одна сущность — две точки ввода: интервал или вся смена</div>
        <label class="field"><span>Вид отсутствия</span><select id="cell-abs-kind">
          <option value="">— без вида —</option>
          ${absenceKinds.map(x => `<option value="${x.id}" data-code="${esc(x.code)}">${esc(x.name)}</option>`).join('')}
        </select>
          <div class="hint" style="margin-top:2px">Из Графика — только «за счёт часов». Отпуск, больничный,
            за свой счёт и оплачиваемый выходной ставятся кодом Табеля («Изменить код Табеля…» выше).</div></label>
        <div class="grid-2">
          <label class="field"><span>Отсутствовал с</span><input type="time" id="cell-abs-from" value="14:00"></label>
          <label class="field"><span>Отсутствовал до</span><input type="time" id="cell-abs-until" value="16:00"></label>
        </div>
        <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
          <input type="checkbox" id="cell-abs-next" style="width:17px;height:17px;accent-color:var(--primary)">
          До следующего дня (через полночь)
        </label>
        <label class="field"><span>Примечание</span><input type="text" id="cell-abs-note" placeholder="Например: заявление согласовано"></label>
        <div style="display:flex;gap:8px;margin:4px 0 6px;flex-wrap:wrap">
          <button class="btn btn-sm" id="cell-abs-save" title="Отпросился на часть смены: интервал внутри окна">Отпросить на интервал</button>
          <button class="btn btn-sm" id="cell-abs-shift" title="Отсутствие на всё окно смены: «выходной за часы»">На всю смену</button>
          <span class="hint" id="cell-abs-hours" style="margin:0;align-self:center"></span>
        </div>
        <p class="hint" style="margin:2px 0 6px">Назначение <b>информационное</b> — «чтобы мы не ждали сотрудника» (Q8):
          отсутствие НЕ меняет план, часы и банк, оно режет смену для флагов (опоздание/ранний уход
          в ожидаемое время) и для доски «Отметки». Неотработанные часы стандартного окна уходят
          в недостачу дня, а при закрытии периода недостачу гасит банк 1:1 — то есть ранее
          накопленные переработки (EX-29). В Табеле остаётся явка.</p>
      </div>
      <div id="doc-btns" style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <button class="btn btn-sm" id="doc-print">Печать заявления</button>
        <button class="btn btn-sm" id="doc-docx">Заявление DOCX (шаблон компании)</button>
        <button class="btn btn-sm" id="doc-pdf">Заявление PDF (готов к печати)</button>
        <span class="hint" style="margin:0">Из Графика печатается «отпросился (выходной за часы)»:
          на всю смену — заявление на выходной за ранее отработанные часы, интервалом —
          об отсутствии на рабочем месте. Отпуск/ДО/ОВ — из Табеля.</span>
      </div>`,
    footer: `<div style="flex:1"></div>
      <button class="btn btn-ghost" data-cancel>Закрыть</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      $('#cell-tabel').onclick = () => {
        closeModal();
        state.pendingTabelCell = { emp: empId, date: dateISO };
        navigate('timesheet');
      };
      const preset = m.querySelector('#cell-preset');
      if (preset) preset.onchange = () => {
        if (!preset.value) return;
        const [a, b, next] = preset.value.split('|');
        $('#cell-sh-from').value = a; $('#cell-sh-until').value = b; $('#cell-sh-next').checked = next === '1';
      };
      const shSave = m.querySelector('#cell-sh-save');
      if (shSave) shSave.onclick = async () => {
        try {
          await api('/api/schedule/shift', { method: 'PUT', body: {
            employee_id: empId, date: dateISO,
            shifts: [{ start: $('#cell-sh-from').value, end: $('#cell-sh-until').value,
                       end_next_day: $('#cell-sh-next').checked }],
          } });
          closeModal(); toast('Ручная смена сохранена', 'ok'); loadSchedule();
        } catch (e) { toast(e.message, 'err'); }
      };
      const shDrop = m.querySelector('#cell-sh-drop');
      if (shDrop) shDrop.onclick = async () => {
        try {
          await api(`/api/schedule/shift?employee_id=${empId}&date=${dateISO}`, { method: 'DELETE' });
          closeModal(); toast('День возвращён к генерации из Табеля', 'ok'); loadSchedule();
        } catch (e) { toast(e.message, 'err'); }
      };
      const addAbsence = async (from, until, nextDay) => {
        try {
          await api('/api/schedule/absence', { method: 'POST', body: {
            employee_id: empId, date: dateISO,
            from_time: from, until_time: until,
            next_day: nextDay,
            kind_id: +$('#cell-abs-kind').value || null,
            note: $('#cell-abs-note').value.trim(),
          } });
          closeModal(); toast('Согласованное отсутствие добавлено', 'ok'); loadSchedule();
        } catch (e) { toast(e.message, 'err'); }
      };
      $('#cell-abs-save').onclick = () => addAbsence($('#cell-abs-from').value,
        $('#cell-abs-until').value, $('#cell-abs-next').checked);
      /* «На всю смену» — границы берутся из смены дня (График), а не вводятся руками:
         это типичный «выходной за часы» (EX-29). */
      $('#cell-abs-shift').onclick = () => {
        const sh = shifts[0];
        if (!sh) return toast('В этот день нет смены — задайте время вручную', 'warn');
        const untilNext = sh.end_hm <= sh.start_hm;
        $('#cell-abs-from').value = sh.start_hm;
        $('#cell-abs-until').value = sh.end_hm;
        $('#cell-abs-next').checked = untilNext;
        addAbsence(sh.start_hm, sh.end_hm, untilNext);
      };
      /* Часы «выходного за часы» — стандартное окно смен сотрудника (сервер выводит). */
      const showTimeoffHours = async () => {
        const hint = $('#cell-abs-hours');
        if (!hint) return;
        try {
          const r = await api(`/api/schedule/timeoff-hours?employee_id=${empId}&date=${dateISO}`,
                              { silent: true });
          const src = { window_of_day: 'окно его смены', timesheet_mode: 'обычная смена за 90 дней',
                        default: 'настройка объекта' }[r.hours_source] || r.hours_source;
          hint.textContent = `«Выходной за часы»: ${hours(r.hours)} ч (${src})`;
          hint.title = 'Сколько часов попадёт в заявление; в Табеле остаётся явка, день гасится банком';
        } catch { hint.textContent = ''; }
      };
      /* Обе точки ввода принадлежат одной сущности (Q3), поэтому доступны для любого
         вида «за счёт часов»; «без вида» — отсутствие без заявления. */
      const absKind = $('#cell-abs-kind');
      const syncAbsKind = () => {
        const sel = absKind.selectedOptions[0];
        $('#cell-abs-shift').style.display = sel ? '' : 'none';
        if (sel) showTimeoffHours(); else $('#cell-abs-hours').textContent = '';
      };
      absKind.onchange = syncAbsKind;
      if (absenceKinds.length) absKind.value = String(absenceKinds[0].id);
      syncAbsKind();
      $$('[data-abs-del]', m).forEach(b => b.onclick = async () => {
        try {
          await api(`/api/schedule/absence/${b.dataset.absDel}`, { method: 'DELETE' });
          closeModal(); toast('Отсутствие удалено — отображение смены восстановлено', 'ok'); loadSchedule();
        } catch (e) { toast(e.message, 'err'); }
      });
      $('#doc-print').onclick = () => printAbsenceRequest(empId, dateISO, 'schedule_absence');
      $('#doc-docx').onclick = () => downloadAbsenceDoc(empId, dateISO, 'docx', 'schedule_absence');
      $('#doc-pdf').onclick = () => downloadAbsenceDoc(empId, dateISO, 'pdf', 'schedule_absence');
    },
  });
}

