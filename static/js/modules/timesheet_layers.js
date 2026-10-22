'use strict';
/* ══ ГРАФИК: сетка «ФИО × дни», печать сетки, редакторы ячейки и периода ══
   Вынесено из app.js (15.10.2026) без изменения логики: границы разделов —
   файлами (сборки намеренно нет, ADR-0008), общие функции — через глобальную
   область (реестр tools/js_globals.json, ESLint no-undef ловит пропуски). */

async function loadSchedule() {
  $('#view-schedule').innerHTML = scheduleShell();
  bindScheduleToolbar();
  if (!state.shiftTypes.length) {
    // легенде сетки нужен словарь смен (без employees.view справочник не грузится — app.js)
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
    ${ro ? '' : `<button class="btn btn-sm" id="btn-range" title="Слой 1 · График: только «за счёт часов» — в Табеле остаётся явка, часы не меняются">Выходной за часы</button>
    <button class="btn btn-sm" id="btn-clear" title="Убрать ручные смены и согласованные отсутствия месяца, перегенерировать График из Табеля; Табель не меняется">Сбросить месяц</button>
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
    'Сбросить месяц в Графике?',
    `Ручные смены и согласованные отсутствия (отлучки-интервалы, «выходные за часы»)
     за ${MONTHS[state.month - 1]} ${state.year} будут удалены, График перегенерируется из Табеля —
     слой 1 вернётся к чистому плану из слоя 0. Табель НЕ трогается — он сбрасывается
     в «Слой 0 · Табель». Напечатанные заявления останутся в журнале аудита.
     Закрытые периоды не трогаются.`,
    async () => {
      const r = await api('/api/schedule/reset-month', { method: 'POST', body: { year: state.year, month: state.month } });
      toast(`Ручных смен удалено: ${r.cleared}, отсутствий: ${r.absences_cleared}`
        + (r.skipped_employees ? `, пропущено закрытых сотрудников: ${r.skipped_employees}` : ''), 'ok');
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
        title="${dateRu(d.date)}${d.double_scope ? ' · день двойной оплаты (' + esc(d.double_title || '') + '): переработки идут кодами ДЯ2/ДН2' : ''}">
        <span class="dow">${esc(d.weekday)}</span>${d.day}${d.double_scope ? '<span class="dbl-mark">×2</span>' : ''}</th>`).join('')}</tr>`;

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
      const color = cssColor(list[0]?.r.employee.group_color);
      /* заголовок блока: первая ячейка «липкая» — не уезжает при горизонтальной прокрутке,
         остальную строку заполняет ячейка-фон (исправление уезжавших заголовков) */
      const header = `<tr class="group-row"><td class="g-name">
        <span class="g-dot" style="background:${color}"></span>${esc(key || 'Без группы')}
        <span class="g-count">${list.length} ${plural(list.length, 'сотрудник', 'сотрудника', 'сотрудников')}</span></td>
        <td class="gfill" colspan="${g.days.length}"></td></tr>`;
      return header + list.map(({ r, b }) => empRow(r, g, b)).join('');
    }).join('');

    $('#grid-host').innerHTML = `<table class="sched"><thead>${head}</thead><tbody>${body}</tbody></table>`;
    if (!can('schedule.edit')) {             // UI-02: право, а не роль — как у тулбара
      $('#grid-host').classList.add('ro');   // только просмотр: клики по ячейкам отключены
    } else {
      $$('#grid-host .cellbtn:not([disabled])').forEach(btn => btn.onclick = () => openCellModal(+btn.dataset.emp, btn.dataset.date));
    }
    /* ФИО открывает карточку сотрудника (право employees.view — data-emp без него
       не рендерится, поэтому связка безопасна и для роли сотрудника) */
    $$('#grid-host td.name-cell[data-emp]').forEach(td => td.onclick = () => openEmployeeCard(+td.dataset.emp));
    if (state.scrollToToday) { state.scrollToToday = false; scrollGridToToday(); }
  }

  /* Легенда соответствует цвету ячеек: показываем, что реально использовано
     в месяце, — смены словаря (по времени окна), коды отсутствий, плашку
     «Выходной за часы». */
  const usedTypes = new Map();
  rows.forEach(r => Object.values(r.cells || {}).forEach(c => {
    if (c.employed === false) return;
    const off = cellWholeOff(c);
    if (off) {
      usedTypes.set(`off:${off.kind ? off.kind.code : 'off'}`,
        { label: (off.kind && off.kind.name) || 'Выходной за часы', color: cellColor(c) });
      return;
    }
    const sh = (c.shifts || [])[0];
    if (sh) {
      const wt = workTypeOfShift(sh);
      if (wt) usedTypes.set(`w:${wt.id}`,
        { label: `${wt.code} · ${wt.start_time}–${wt.end_time}`, color: cellColor(c) });
      else if (c.tabel) usedTypes.set(`c:${c.tabel.code}`,
        { label: c.tabel.code, color: cellColor(c) });
      return;
    }
    const tt = c.tabel;
    if (!tt) return;
    usedTypes.set(`a:${tt.code}`, { label: tt.code, color: cellColor(c) });
  }));
  $('#grid-legend').innerHTML = [...usedTypes.values()].map(x =>
    `<span class="chip"><span class="swatch" style="background:${x.color}"></span>${esc(x.label)}</span>`).join('') +
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

/* ── Содержимое и цвет ячейки: ЕДИНЫЕ правила для экрана и печати (16.10.2026) ──
   Содержимое: отсутствие на всё рабочее окно — плашка «Выходной за часы» (EX-29;
   whole_shift считает СЕРВЕР тем же правилом, что и для заявлений — второй копии
   правила на фронтенде нет); иначе — видимые отрезки смены по строкам (смена минус
   отсутствия, segments считает сервер); без смены — код Табеля. Код Табеля из ячейки
   убран: он живёт в слое 0 и в подсказке. Цвет — из словаря «Смены и отсутствия»:
   смена матчится по времени окна; день без смены — цвет кода Табеля из настроек
   (18.10.2026: связка «вид отсутствия → код Табеля» удалена). */
function cellWholeOff(c) {
  return (c.absences || []).find(a => a.whole_shift) || null;
}
function cellSegLines(c) {
  if ((c.segments || []).length) return c.segments.map(s => `${s[0]}–${s[1]}`);
  return (c.shifts || []).map(x => `${x.start_hm}–${x.end_hm}`);   // кеш без segments
}
function workTypeOfShift(sh) {
  return (state.shiftTypes || []).find(x => x.kind === 'work'
    && x.start_time === sh.start_hm && x.end_time === sh.end_hm);
}
function cellColor(c) {
  /* сервер разрешает цвет по словарю «Смены и отсутствия» (payload.color) — один
     источник для экрана, печати, PDF и Excel; ниже — подстраховка для кеша */
  if (c.color) return cssColor(c.color);
  const off = cellWholeOff(c);
  if (off) return cssColor(off.kind && off.kind.color, '#0e9aa7');
  const t = c.tabel;
  const sh = (c.shifts || [])[0];
  if (sh) {
    const wt = workTypeOfShift(sh);
    if (wt) return cssColor(wt.color);
  }
  /* день без смены (отсутствие кодом Табеля, выходной) — цвет кода из настроек */
  return V4_CODE_COLORS[t ? t.code : ''] || '#8a94a6';
}

function cellTd(r, d, c, cls) {
  const btn = (extra, inner, title, style) =>
    `<td class="${cls}"><button class="cellbtn ${extra}" data-emp="${r.employee.id}" data-date="${d.date}" title="${esc(title)}"${style ? ` style="${style}"` : ''}>${inner}</button></td>`;
  const t = c.tabel;
  const shifts = c.shifts || [];
  const absences = c.absences || [];
  const code = t ? t.code : '';
  const color = cellColor(c);
  const off = cellWholeOff(c);
  const lines = cellSegLines(c);
  const manual = shifts.some(x => x.source === 'manual');
  const title = `${r.employee.short_name}, ${dateRu(d.date)}: ` +
    (t ? `Табель «${t.value || t.code}»${t.source === 'cycle' ? ' (из циклов)' : ' (вручную)'}` : 'Табель не заполнен') +
    (shifts.length ? ` · смена ${shifts.map(x => `${x.start_hm}–${x.end_hm}${x.source === 'manual' ? ' (ручная)' : ''}`).join(', ')}` : ' · смены нет') +
    (absences.length ? ` · согласованное отсутствие ${absences.map(a => `${a.start_hm}–${a.end_hm}${a.whole_shift ? ' — вся смена (выходной за часы)' : ''}${a.kind ? ' (' + a.kind.name + ')' : ''}`).join(', ')} — на часы не влияет` : '') +
    (t && t.note ? ` · ${t.note}` : '');
  const marks = [manual ? '<span class="manual-mark" title="Ручная смена">Р</span>' : '',
    (absences.length && !off) ? '<span class="partial-mark" title="Согласованное отсутствие: смена показана разрезанной">✂</span>' : ''].join('');
  let inner;
  if (off) {
    inner = `${marks}<span class="dayoff" style="background:${withAlpha(color, .16)};border-color:${withAlpha(color, .6)}">Выходной<br>за часы</span>`;
  } else if (lines.length) {
    inner = `${marks}${lines.map(x => `<span class="t seg">${esc(x)}</span>`).join('')}`;
  } else {
    inner = `${marks}<span class="t t-full">${esc(t ? (t.value || t.code) : '—')}</span><span class="t t-short">${esc(t ? (t.value || t.code).replace(' ', '') : '—')}</span>`;
  }
  const style = (off || lines.length || code)
    ? `background:linear-gradient(165deg, ${withAlpha(color, .30)}, ${withAlpha(color, .16)});color:#2c3440` : '';
  return btn(code || off || lines.length ? '' : 'empty', inner, title, style);
}

function empRow(r, g, block) {
  const accent = cssColor(r.employee.group_color);
  /* ФИО строки — вход в карточку сотрудника (та же, что в разделе «Сотрудники»):
     правки доступны прямо из Графика. Без права employees.view (например, роль
     сотрудника) — обычный текст: ни класса, ни data-emp. */
  const canCard = can('employees.view');
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
    <td class="name-cell${canCard ? ' who-click' : ''}"${canCard ? ` data-emp="${r.employee.id}" title="Карточка сотрудника — открыть"` : ''} style="box-shadow: inset 4px 0 0 ${accent}">
      <div class="nm" title="${esc(r.employee.full_name)}">${esc(r.employee.short_name || r.employee.full_name)}</div>
      <div class="pos"><span class="dot-pos" style="background:${accent}"></span>${esc(r.employee.position || '')}</div>
      <div class="tot">${r.totals.work_days} ${plural(r.totals.work_days, 'смена', 'смены', 'смен')}</div>
    </td>${cells}
  </tr>`;
}


/* ── Печать: те же ячейки, что на экране (решение 16.10.2026) — та же геометрия
   (имя 232px, день 60px, итого 80px, строка 52px, те же шрифты), то же содержимое
   (отрезки смены по строкам, плашка «Выходной за часы», коды Табеля), блоки смен
   разделены заголовками. Физически 1:1 месяц на A4 не помещается (31 день × ~15 мм
   > 277 мм), поэтому дни режутся на страницы по ≤16 (колонка ФИО повторяется на
   каждой), а лист пропорционально масштабируется под ширину страницы — форма и
   пропорции ячеек остаются экранными (масштаб ≈0.9 вместо ≈0.5 при одной странице).
   Порядок строк задаёт сервер: блок → старшие → алфавит (16.10.2026). ── */
const P_NAME_W = 232, P_DAY_W = 60, P_PAGE_PX = 1062, P_CHUNK = 16;

function printGrid() {
  const g = state.grid;
  if (!g) return;
  const rows = filteredRows();
  /* блоки — как на экране; сотрудник без блока попадает в «Без группы» (не теряется) */
  const groups = {};
  rows.forEach(r => (r.blocks || []).forEach(b => { (groups[b.group] ||= []).push({ r, b }); }));
  rows.forEach(r => { if (!(r.blocks || []).length) (groups[''] ||= []).push({ r, b: null }); });
  const keys = Object.keys(groups).sort((a, b) =>
    groupOrder(a) - groupOrder(b) || a.localeCompare(b, 'ru'));
  const pages = Math.max(1, Math.ceil(g.days.length / P_CHUNK));
  const perPage = Math.ceil(g.days.length / pages);
  const zoom = Math.min(1, P_PAGE_PX / (P_NAME_W + perPage * P_DAY_W));
  let html = '';
  for (let pi = 0; pi < pages; pi++) {
    const chunk = g.days.slice(pi * perPage, (pi + 1) * perPage);
    if (!chunk.length) continue;
    const head = `<tr><th class="p-name">Сотрудник</th>${chunk.map(d =>
      `<th class="p-day${d.is_weekend ? ' we' : ''}${d.is_today ? ' today' : ''}">${String(d.day).padStart(2, '0')}<br><span class="dow">${esc(d.weekday)}</span>${d.double_scope ? '<span class="dbl">×2</span>' : ''}</th>`).join('')}</tr>`;
    const body = keys.map(key => {
      const trs = groups[key].map(({ r, b }) => {
        const rgs = (b && b.ranges) || (b ? [{ start: b.start, end: b.end }] : []);
        const tds = chunk.map(d => {
          const c = r.cells[d.date] || {};
          const out = rgs.length && !rgs.some(rg => d.date >= rg.start && (!rg.end || d.date <= rg.end));
          if (c.employed === false) return `<td class="p-cell dim" style="background:${g.colors.inactive || '#eceff4'}">—</td>`;
          if (out) return `<td class="p-cell dim" style="background:${g.colors.out_of_block}">—</td>`;
          const off = cellWholeOff(c);
          const lines = cellSegLines(c);
          const tt = c.tabel;
          const color = cellColor(c);
          const manual = (c.shifts || []).some(x => x.source === 'manual');
          const marks = `${manual ? '<sup>Р</sup>' : ''}${(c.absences || []).length && !off ? '<sup>✂</sup>' : ''}`;
          let txt;
          if (off) txt = 'Выходной\nза часы';
          else if (lines.length) txt = lines.join('\n');
          else txt = tt ? (tt.value || tt.code) : '';
          const bg = (off || lines.length || tt) ? ` style="background:${withAlpha(color, .22)}"` : '';
          return `<td class="p-cell${d.is_weekend ? ' we' : ''}"${bg}>${marks}${esc(txt)}</td>`;
        }).join('');
        return `<tr><td class="p-name">${esc(r.employee.full_name)} <span class="muted">${esc(r.employee.position || '')}</span></td>${tds}</tr>`;
      }).join('');
      return `<tr class="p-group"><td colspan="${chunk.length + 1}">${esc(key || 'Без группы')}</td></tr>${trs}`;
    }).join('');
    html += `<div class="p-page${pi ? ' pb' : ''}">
      <h1>График сменности, ${MONTHS[g.month - 1]} ${g.year} г. · дни ${chunk[0].day}–${chunk[chunk.length - 1].day}</h1>
      <p class="note">Ячейка — смена: отрезки времени по строкам. Плашка «Выходной за часы» —
        отсутствие на всю смену; ✂ — согласованное отсутствие (логический разрез, на часы не влияет);
        Р — ручная смена; ×2 — день двойной оплаты. «—» — вне блока/периода трудоустройства.
        Внутри блока: старшие, далее по алфавиту.</p>
      <table class="gridprint"><thead>${head}</thead><tbody>${body}</tbody></table></div>`;
  }
  printWindow(`График сменности ${MONTHS[g.month - 1]} ${g.year}`, html, `
    @page { size: A4 landscape; margin: 8mm; }
    body { zoom: ${zoom.toFixed(3)}; }
    .p-page.pb { page-break-before: always; }
    table.gridprint { border-collapse: collapse; table-layout: fixed; }
    .gridprint th, .gridprint td { border: 1px solid #b9c2d0; padding: 1px 2px; text-align: center;
      vertical-align: middle; font-size: 9px; }
    .gridprint th.p-name, .gridprint td.p-name { width: ${P_NAME_W}px; min-width: ${P_NAME_W}px;
      text-align: left; padding-left: 6px; font-size: 10.5px; }
    .gridprint td.p-name { height: 52px; }
    .gridprint th.p-day { width: ${P_DAY_W}px; min-width: ${P_DAY_W}px; height: 34px;
      font-size: 10.5px; background: #eef2f8; }
    .gridprint th.p-day .dow { color: #667; font-size: 9px; }
    .gridprint th.p-day.we { background: #f7efe7; color: #a04a3a; }
    .gridprint th.p-day.today { background: #141a25; color: #fff; }
    .gridprint th.p-day.today .dow { color: #e6c267; }
    .gridprint td.p-cell { width: ${P_DAY_W}px; min-width: ${P_DAY_W}px; height: 52px;
      font-size: 9px; font-weight: 700; white-space: pre-line; line-height: 1.3; }
    .gridprint td.p-cell.dim { color: #98a2b3; font-weight: 400; }
    .gridprint tr.p-group td { background: #ede5da; font-weight: 700; text-align: left;
      padding: 4px 8px; font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: #57493c; }
    .gridprint sup { font-size: 7px; }
    .gridprint .dbl { color: #8a6d1a; font-weight: 800; margin-left: 2px; }
    .muted { color: #8b98ad; }`);
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
  /* 18.10.2026: справочники независимы. «За счёт часов» — системный вид словаря
     смен; отсутствия периода (отпуск, больничный…) — коды Табеля без часов. */
  const kinds = state.shiftTypes.filter(x => x.kind === 'absence' && !x.is_default_off);
  openModal({
    title: fromSchedule ? 'Выходной за часы' : 'Назначить отсутствие (код Табеля)',
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
      ${fromSchedule
        ? `<div class="field"><span>Вид («за счёт часов») — в словаре один</span>
           <div style="font-weight:600">${kinds[0] ? esc(kinds[0].name) : '— нет вида в словаре смен —'}</div>
           <div class="hint" id="rg-mode-hint" style="margin-top:4px"></div></div>`
        : `<label class="field"><span>Код отсутствия (CFG-DAY-CODES)</span><select id="rg-code">
          <option value="">— загрузка… —</option>
        </select>
          <div class="hint" id="rg-mode-hint" style="margin-top:4px"></div></label>`}
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
        : 'Отсутствие оформляется кодом первичного документа: словарь смен не участвует.';
      const codeSel = m.querySelector('#rg-code');
      if (codeSel) (async () => {
        try {
          const di = await api('/api/shift-types/tabel-codes', { silent: true });
          const off = (di.codes || []).filter(c => !c.carries_hours && c.code !== 'В');
          codeSel.innerHTML = off.map(c => `<option value="${esc(c.code)}" ${c.code === 'ОТ' ? 'selected' : ''}>${esc(c.title || c.code)} · «${esc(c.code)}»</option>`).join('')
            || '<option value="">— нет кодов отсутствий в справочнике —</option>';
        } catch { codeSel.innerHTML = '<option value="">— справочник не загрузился —</option>'; }
      })();
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        const ids = $$('#rg-emps input:checked').map(i => +i.value);
        if (!ids.length) return toast('Отметьте сотрудников', 'warn');
        const kindId = fromSchedule ? (kinds[0] ? kinds[0].id : 0) : 0;
        const code = fromSchedule ? '' : ($('#rg-code') ? $('#rg-code').value : '');
        if (fromSchedule && !kindId) return toast('Нет вида «за счёт часов» в словаре', 'warn');
        if (!fromSchedule && !code) return toast('Выберите код отсутствия', 'warn');
        const from = $('#rg-from').value, to = $('#rg-to').value;
        if (!from || !to || from > to) return toast('Проверьте даты периода', 'warn');
        try {
          const res = await api('/api/schedule/range-absence', { method: 'POST', body: {
            employee_ids: ids, first: from, last: to,
            shift_type_id: kindId || null, code, note: $('#rg-note').value.trim(),
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
    && !x.archived);
  /* вид отсутствия из Графика — единственный «за счёт часов» (Q4): выбор убран,
     владельцу не зачем выбирать из одного (16.10.2026) */
  const absenceKind = absenceKinds[0] || null;
  const t = cell.tabel;
  const shifts = cell.shifts || [];
  const absences = cell.absences || [];
  const editable = cell.editable !== false;
  /* Отлучек в дне может быть несколько (решение владельца 16.10.2026): каждое
     печатается своим заявлением, а нижние кнопки собирают ОДНО заявление
     со списком интервалов («с 14:00 до 16:00 (2 ч) и с 18:00 до 20:00 (2 ч)»). */
  const printableIv = absences.filter(a => a.kind && a.kind.doc_type).length;
  const multiIv = printableIv > 1;

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
        <div class="tc-chips" id="cell-sh-chips">
          ${workShifts.map(x => `<button type="button" class="tc-chip" data-sh="${x.id}"
            style="background:${withAlpha(cssColor(x.color), .18)};border-color:${cssColor(x.color)}"
            title="${esc(x.name)}${x.overnight ? ' · заканчивается на следующие сутки' : ''}">${esc(x.display_code || x.name)}<small>${esc(x.start_time)}–${esc(x.end_time)}${x.overnight ? ' · +1 сутки' : ''}</small></button>`).join('')}
          <button type="button" class="tc-chip manual" data-sh="manual" title="Задать начало и конец вручную">⚙ Вручную</button>
        </div>
        <div id="cell-sh-manual" style="display:none">
          <div class="grid-2">
            <label class="field"><span>Начало</span><input type="time" id="cell-sh-from" value="09:00"></label>
            <label class="field"><span>Конец</span><input type="time" id="cell-sh-until" value="18:00"></label>
          </div>
          <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
            <input type="checkbox" id="cell-sh-next" style="width:17px;height:17px;accent-color:var(--primary)">
            Заканчивается на следующие сутки (смена через полночь)
          </label>
        </div>
        <div style="display:flex;gap:8px;margin:8px 0 6px;flex-wrap:wrap">
          <button class="btn btn-sm btn-primary" id="cell-sh-save">Сохранить ручную смену</button>
          ${shifts.some(x => x.source === 'manual') ? '<button class="btn btn-sm btn-danger" id="cell-sh-drop">Вернуть к генерации из Табеля</button>' : ''}
        </div>
        <p class="hint" style="margin:2px 0 6px">Смена выбирается плашкой из словаря (как значение дня
          в Табеле) либо «⚙ Вручную». День редактируем, если его код Табеля принимает коды УТ
          (accepts_ut = Да). Ручная смена может пересекать полночь; на часы влияет только Табель —
          правка Графика меняет флаги и доску, но не расчёт (RUL-SCHEDULE-ONLY-FLAGS).</p>
      </div>` : '<p class="hint">Ручную смену в этот день поставить нельзя: код Табеля не принимает коды УТ (день-якорь).</p>'}
      <div class="opt-group-title" style="margin-top:12px">Отпросился (выходной за часы) — согласованные отсутствия дня</div>
      ${absences.map(a => `<div class="status-line">
          <span class="k">✂ ${esc(a.start_hm)}–${esc(a.end_hm)}${a.kind ? ' · ' + esc(a.kind.name) : ''}${a.note ? ' · ' + esc(a.note) : ''}</span>
          <span class="v">${multiIv && a.kind && a.kind.doc_type ? `
            <button class="btn btn-sm btn-ghost" data-abs-print="${a.id}" title="Заявление только по этому интервалу">Печать</button>
            <button class="btn btn-sm btn-ghost" data-abs-pdf="${a.id}" title="PDF заявления только по этому интервалу">PDF</button>` : ''}
            <button class="btn btn-sm btn-ghost" data-abs-del="${a.id}">Удалить</button></span></div>`).join('') || ''}
      ${shifts.length ? `
      <div style="margin-top:8px;border:1px solid var(--line);border-radius:12px;padding:12px 14px 8px;background:#f8fbfd">
        <div class="opt-group-title" style="margin-top:0">Одна сущность — две точки ввода: интервал или вся смена</div>
        <div class="grid-2">
          <label class="field"><span>Отсутствовал с</span><input type="time" id="cell-abs-from" value="14:00"></label>
          <label class="field"><span>Отсутствовал до</span><input type="time" id="cell-abs-until" value="16:00"></label>
        </div>
        <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
          <input type="checkbox" id="cell-abs-next" style="width:17px;height:17px;accent-color:var(--primary)">
          До следующего дня (через полночь)
        </label>
        <label class="field"><span>Примечание</span><input type="text" id="cell-abs-note" placeholder="Например: заявление согласовано"></label>
        <label class="field"><span>Шаблон заявления</span><select id="cell-abs-doc">
          <option value="">— авто по точке ввода —</option></select>
          <div class="hint" style="margin-top:2px">Авто: интервал — «об отсутствии на рабочем
            месте», вся смена — «выходной за ранее отработанные часы». Выберите шаблон,
            чтобы печатать другой документ.</div></label>
        <p class="hint" id="cell-abs-split" style="margin:0 0 6px"></p>
        <div style="display:flex;gap:8px;margin:4px 0 6px;flex-wrap:wrap">
          <button class="btn btn-sm btn-primary" id="cell-abs-save" title="Отпросился на часть смены: интервал внутри окна">На интервал</button>
          <button class="btn btn-sm btn-primary" id="cell-abs-shift" title="Отсутствие на всё окно смены: «выходной за часы»">На всю смену</button>
          <span class="hint" id="cell-abs-hours" style="margin:0;align-self:center"></span>
        </div>
        <p class="hint" style="margin:2px 0 6px">Назначение <b>информационное</b> — «чтобы мы не ждали сотрудника» (Q8):
          отсутствие НЕ меняет план, часы и банк, оно режет смену для флагов (опоздание/ранний уход
          в ожидаемое время) и для доски «Отметки». Неотработанные часы стандартного окна уходят
          в недостачу дня, а при закрытии периода недостачу гасит банк 1:1 — то есть ранее
          накопленные переработки (EX-29). В Табеле остаётся явка.</p>
      </div>` : `<p class="hint" style="margin:8px 0 0">Смены с часами в этот день нет —
        согласованное отсутствие («выходной за часы») режет смену, поэтому назначать
        его не к чему. Поставьте смену плашками выше, а отсутствие на весь день без
        смены оформляется кодом Табеля в слое 0 («Изменить код Табеля…»).</p>`}
      ${printableIv ? `
      <div id="doc-btns" style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <button class="btn btn-sm" id="doc-print">Печать заявления${multiIv ? ' (все интервалы одним)' : ''}</button>
        <button class="btn btn-sm" id="doc-docx">${multiIv ? 'DOCX (все интервалы)' : 'Заявление DOCX'} (шаблон компании)</button>
        <button class="btn btn-sm" id="doc-pdf">${multiIv ? 'PDF (все интервалы)' : 'Заявление PDF'} (готов к печати)</button>
        <span class="hint" style="margin:0">${multiIv
          ? `В дне ${printableIv} интервала(-ов): нижние кнопки печатают ОДНО заявление со списком («…с 14:00 до 16:00 (2 ч) и с 18:00 до 20:00 (2 ч)…»), «Печать»/«PDF» у интервала — заявление по нему одному.`
          : 'Из Графика печатается «отпросился (выходной за часы)»: на всю смену — заявление на выходной за ранее отработанные часы, интервалом — об отсутствии на рабочем месте. Отпуск/ДО/ОВ — из Табеля.'}</span>
      </div>` : ''}`,
    footer: `<div style="flex:1"></div>
      <button class="btn btn-ghost" data-cancel>Закрыть</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      $('#cell-tabel').onclick = () => {
        closeModal();
        state.pendingTabelCell = { emp: empId, date: dateISO };
        navigate('timesheet');
      };
      /* Ручная смена — плашкой из словаря (как значение дня в Табеле) либо «⚙ Вручную»:
         плашка выбирается, время сохраняет «Сохранить ручную смену». */
      const shChips = $$('#cell-sh-chips .tc-chip', m);
      const manualBox = m.querySelector('#cell-sh-manual');
      const pick = chip => {
        shChips.forEach(b => b.classList.toggle('sel', b === chip));
        if (manualBox) manualBox.style.display = chip && chip.dataset.sh === 'manual' ? '' : 'none';
      };
      shChips.forEach(b => b.onclick = () => pick(b));
      const manualNow = shifts.find(x => x.source === 'manual');
      if (manualNow && shChips.length) {
        /* текущая ручная смена совпадает со словарём — предвыбираем её плашку,
           иначе — «Вручную» с её временем */
        const match = shChips.find(b => {
          const x = workShifts.find(s => String(s.id) === b.dataset.sh);
          return x && x.start_time === manualNow.start_hm && x.end_time === manualNow.end_hm;
        });
        if (match) pick(match);
        else {
          pick(shChips.find(b => b.dataset.sh === 'manual'));
          $('#cell-sh-from').value = manualNow.start_hm;
          $('#cell-sh-until').value = manualNow.end_hm;
          $('#cell-sh-next').checked = manualNow.end_hm <= manualNow.start_hm;
        }
      }
      const shSave = m.querySelector('#cell-sh-save');
      if (shSave) shSave.onclick = async () => {
        const sel = m.querySelector('#cell-sh-chips .tc-chip.sel');
        if (!sel) return toast('Выберите смену из словаря или «⚙ Вручную»', 'warn');
        const dict = workShifts.find(s => String(s.id) === sel.dataset.sh);
        if (sel.dataset.sh !== 'manual' && !dict) return toast('Смена не найдена в словаре', 'err');
        const one = sel.dataset.sh === 'manual'
          ? { start: $('#cell-sh-from').value, end: $('#cell-sh-until').value,
              end_next_day: $('#cell-sh-next').checked }
          : { start: dict.start_time, end: dict.end_time, end_next_day: !!dict.overnight };
        try {
          await api('/api/schedule/shift', { method: 'PUT', body: {
            employee_id: empId, date: dateISO, shifts: [one],
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
      /* После назначения модалка НЕ закрывается (решение владельца 16.10.2026):
         заявление можно напечатать сразу, а список интервалов обновляется на месте. */
      const refreshCellModal = async () => {
        await loadSchedule();
        openCellModal(empId, dateISO);
      };
      const addAbsence = async (from, until, nextDay) => {
        try {
          await api('/api/schedule/absence', { method: 'POST', body: {
            employee_id: empId, date: dateISO,
            from_time: from, until_time: until,
            next_day: nextDay,
            /* вид «за счёт часов» в словаре один (Q4) — выбор убран (16.10.2026) */
            kind_id: absenceKind ? absenceKind.id : null,
            note: $('#cell-abs-note').value.trim(),
            doc_type: $('#cell-abs-doc') ? $('#cell-abs-doc').value : '',
          } });
          toast('Согласованное отсутствие добавлено — заявление можно печатать сразу', 'ok');
          await refreshCellModal();
        } catch (e) { toast(e.message, 'err'); }
      };
      const absSave = m.querySelector('#cell-abs-save');
      if (absSave) absSave.onclick = () => addAbsence($('#cell-abs-from').value,
        $('#cell-abs-until').value, $('#cell-abs-next').checked);
      /* «На всю смену» — границы берутся из смены дня (График), а не вводятся руками:
         это типичный «выходной за часы» (EX-29). */
      const absShift = m.querySelector('#cell-abs-shift');
      if (absShift) absShift.onclick = () => {
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
      /* вид не выбирается: кнопки и часы «выходного за часы» доступны сразу,
         блок существует только при смене с часами (см. разметку выше) */
      /* шаблоны заявлений для диалога «Отпросился» (18.10.2026) */
      const docSel = m.querySelector('#cell-abs-doc');
      if (docSel) (async () => {
        try {
          const di = await api('/api/docs/kinds', { silent: true });
          docSel.innerHTML = '<option value="">— авто по точке ввода —</option>' +
            (di.kinds || []).filter(k => k.active !== false)
              .map(k => `<option value="${esc(k.code)}">${esc(k.name)}</option>`).join('');
        } catch { /* остаётся авто */ }
      })();
      /* рабочее время ДО и ПОСЛЕ интервала (пункт 4 задания 17.10.2026) */
      const splitHint = () => {
        const box = m.querySelector('#cell-abs-split');
        if (!box) return;
        const sh = (shifts || [])[0];
        const f = m.querySelector('#cell-abs-from')?.value;
        const u = m.querySelector('#cell-abs-until')?.value;
        if (!sh || !f || !u) { box.textContent = ''; return; }
        const min = v => { const [h, mm] = v.split(':').map(Number); return h * 60 + mm; };
        const s0 = min(sh.start_hm), e0 = min(sh.end_hm), a = min(f), b = min(u);
        if (!(a < b)) { box.textContent = ''; return; }
        const parts = [];
        if (a > s0) parts.push(`${sh.start_hm}–${f} (${hours((a - s0) / 60)} ч)`);
        if (e0 > b) parts.push(`${u}–${sh.end_hm} (${hours((e0 - b) / 60)} ч)`);
        box.textContent = parts.length
          ? `Рабочее время дня: ${parts.join(' и ')}`
          : 'Интервал накрывает всё окно — день станет плашкой «Выходной за часы»';
      };
      m.querySelector('#cell-abs-from')?.addEventListener('change', splitHint);
      m.querySelector('#cell-abs-until')?.addEventListener('change', splitHint);
      splitHint();
      if (m.querySelector('#cell-abs-shift')) showTimeoffHours();
      $$('[data-abs-del]', m).forEach(b => b.onclick = async () => {
        try {
          await api(`/api/schedule/absence/${b.dataset.absDel}`, { method: 'DELETE' });
          toast('Отсутствие удалено — отображение смены восстановлено', 'ok');
          await refreshCellModal();
        } catch (e) { toast(e.message, 'err'); }
      });
      /* печать заявления по ОДНОМУ интервалу, когда их в дне несколько */
      $$('[data-abs-print]', m).forEach(b => b.onclick = () =>
        printAbsenceRequest(empId, dateISO, 'schedule_absence', +b.dataset.absPrint));
      $$('[data-abs-pdf]', m).forEach(b => b.onclick = () =>
        downloadAbsenceDoc(empId, dateISO, 'pdf', 'schedule_absence', +b.dataset.absPdf));
      /* кнопки печати — только когда в дне есть печатаемые отсутствия: без них
         отсутствие-period отвечает ошибкой, и кнопки лишь сбивали с толку
         (замечание владельца 16.10.2026) */
      const docPrint = m.querySelector('#doc-print');
      if (docPrint) docPrint.onclick = () => printAbsenceRequest(empId, dateISO, 'schedule_absence');
      const docDocx = m.querySelector('#doc-docx');
      if (docDocx) docDocx.onclick = () => downloadAbsenceDoc(empId, dateISO, 'docx', 'schedule_absence');
      const docPdf = m.querySelector('#doc-pdf');
      if (docPdf) docPdf.onclick = () => downloadAbsenceDoc(empId, dateISO, 'pdf', 'schedule_absence');
    },
  });
}

