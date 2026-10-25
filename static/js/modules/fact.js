'use strict';

/* ══════════════════════════════════════════════════════════════════
   ФАКТ — история сессий (16.4): сырые сессии без округления; визуализация — здесь,
   бэкенд отдаёт только моменты. Три индексных запроса на диапазон.
   ══════════════════════════════════════════════════════════════════ */
state.factEmp = state.factEmp || null;
state.factFrom = state.factFrom || null;

/* ══════════════════════════════════════════════════════════════════
   ФАКТ — слой 2 модели «График = 4 слоя» (T5, норматив 12.10.2026).
   Два представления одних и тех же отметок СКУД:
   · «Номера» (Q7) — один день глазами движка: сырые отметки и округление до шага,
     сопряжённые сессии, окно из кода Табеля, план / отработано / недостача /
     переработка по категориям и флаги из Графика. Все числа считает сервер
     (/api/fact/day, settle за период дня); шаг округления — из настроек, а не из
     интерфейса: источник истины — движок.
   · «Сессии» — исходная история «пришёл — ушёл» за диапазон, без округления.
   Оперативная доска «кто на работе» — отдельный пункт меню «Отметки» (Q7).
   ══════════════════════════════════════════════════════════════════ */
async function loadFact() {
  const host = $('#view-fact');
  /* порядок вкладок и вкладка по умолчанию — решения владельца 16.10.2026:
     Месяц (гант) первым и по умолчанию, затем День и Сотрудник */
  state.factMode = state.factMode || 'month';
  host.innerHTML = `
    <div class="page-head">
      <div><h2>Слой 2 · Факт</h2>
        <div class="sub">Слой 2 · отметки СКУД: «Месяц» — гант фактических
          присутствий на непрерывной оси времени (ночи темнее, окно Табеля
          штриховкой); «День» — день глазами движка (округление до шага, окно из
          Табеля, план / отработано / недостача / переработка, флаги из Графика);
          «Сотрудник» — исходная история «пришёл — ушёл» без округления</div></div>
      <div class="spacer"></div>
      <div class="seg" id="fc-mode">
        <button data-mode="month" class="${state.factMode === 'month' ? 'active' : ''}"
          title="Гант месяца: округлённые сессии на непрерывной оси времени, ночи темнее, окно Табеля штриховкой">Месяц</button>
        <button data-mode="numbers" class="${state.factMode === 'numbers' ? 'active' : ''}"
          title="Сетка дня: отметки, округлённые до шага, и расчёт дня">День</button>
        <button data-mode="sessions" class="${state.factMode === 'sessions' ? 'active' : ''}"
          title="История сессий «пришёл — ушёл» одного сотрудника: точные моменты, без округления">Сотрудник</button>
      </div>
    </div>
    <div id="fc-pane"></div>`;
  $$('#fc-mode button').forEach(b => b.onclick = () => {
    if (state.factMode === b.dataset.mode) return;
    state.factMode = b.dataset.mode;
    loadFact();
  });
  if (state.factMode === 'sessions') await loadFactSessions();
  else if (state.factMode === 'month') await loadFactMonth();
  else await loadFactNumbers();
}

/* ── вкладка «Месяц»: ГАНТ фактических присутствий (16.10.2026) ──
   Ось X — непрерывное время месяца (не колонки дней), поэтому смена через
   полночь — ОДНА полоса. Данные — GET /api/fact/month: сессии из ОКРУГЛЁННЫХ
   отметок (to_calc_mark + pair_marks, то же ядро, что у вкладки «День»), целиком,
   без нарезки полуночью; на день — стандартное окно Табеля (штриховка), цвет
   полосы из словаря «Смены и отсутствия» (тот же, что в ячейках Графика),
   согласованные отсутствия (✂). Категории времени периода (CFG-CATEGORIES, из ответа
   /api/fact/month) — тоном: самая длинная (обычно день) — цветом полосы, короче —
   темнее; видно, кто работал в ночь. Рендерер — из прототипа
   docs/prototype-fact-month-gantt.html. */
const FG_DAY_W = 52, FG_ROW_H = 34, FG_HEAD_H = 34, FG_BAR_H = 12, FG_WIN_H = 22;
/* запасной вариант, если категории не пришли: значения по умолчанию CFG-CATEGORIES */
const FG_FALLBACK_CATEGORIES = [{ code: 'ДЯ', start: '06:00', end: '22:00' },
                                { code: 'ДН', start: '22:00', end: '06:00' }];
const fgHours = hms => { const [h, m] = hms.split(':').map(Number); return h + m / 60; };
/* Полосы категорий суток в часах: [{code, label, spans: [[h1, h2], …], tone}] в порядке
   настроек. tone 0 — самая длинная категория, 1 — самая короткая (темнее): правило не
   зависит ни от порядка категорий в настройках, ни от их кодов (25.10.2026). */
function fgCategoryBands(categories) {
  const list = (categories && categories.length ? categories : FG_FALLBACK_CATEGORIES).map((c, i) => {
    const a = fgHours(c.start), b = fgHours(c.end);
    const spans = b > a ? [[a, b]] : [[a, 24], [0, b]].filter(([x, y]) => y > x);
    return { code: c.code, label: `${c.code} ${c.start}–${c.end}`, spans, i,
             len: spans.reduce((s, [x, y]) => s + y - x, 0) };
  });
  const byLen = [...list].sort((p, q) => q.len - p.len || p.i - q.i);
  byLen.forEach((c, r) => { c.tone = byLen.length > 1 ? r / (byLen.length - 1) : 0; });
  return list;
}
function fgCategoryLegend(categories) {
  return fgCategoryBands(categories).map(c => c.label).join(' · ');
}
function fgDarken(hex, k) {
  const n = parseInt(cssColor(hex).slice(1), 16);
  const f = v => Math.round(v * (1 - k));
  return `rgb(${f((n >> 16) & 255)},${f((n >> 8) & 255)},${f(n & 255)})`;
}
function fgHmX(di, hms) {
  const [h, m] = hms.split(':').map(Number);
  return di * FG_DAY_W + (h + m / 60) / 24 * FG_DAY_W;
}
function fgT2x(iso) { return fgHmX(+iso.slice(8, 10) - 1, iso.slice(11, 16)); }
function fgBar(x1, x2, y, fill, open, title) {
  const w = Math.max(2, x2 - x1);
  return `<rect x="${x1.toFixed(1)}" y="${(y - FG_BAR_H / 2).toFixed(1)}" width="${w.toFixed(1)}" height="${FG_BAR_H}" rx="3" `
    + (open ? `fill="${withAlpha(cssColor(fill), .30)}" stroke="${cssColor(fill)}" stroke-width="1.4" stroke-dasharray="4 3"`
            : `fill="${cssColor(fill)}"`)
    + `><title>${esc(title || '')}</title></rect>`;
}
function fgWin(x1, x2, y, col, pid) {
  return `<rect x="${x1.toFixed(1)}" y="${(y - FG_WIN_H / 2).toFixed(1)}" width="${Math.max(2, x2 - x1).toFixed(1)}" height="${FG_WIN_H}" fill="url(#${pid})" stroke="${withAlpha(cssColor(col), .55)}" stroke-dasharray="3 2"><title>стандартное окно Табеля (ожидание)</title></rect>`;
}

async function loadFactMonth() {
  const pane = $('#fc-pane');
  pane.innerHTML = `
    <div class="toolbar">
      ${v4MonthNav('fm')}
      <div class="spacer"></div>
      <span class="hint" id="fm-meta" style="margin:0"></span>
    </div>
    <div id="fm-body"><div class="empty">Загрузка…</div></div>`;
  v4BindMonthNav('fm', loadFactMonth);
  let d;
  try { d = await api(`/api/fact/month?year=${state.year}&month=${state.month}`); }
  catch (e) { $('#fm-body').innerHTML = `<div class="panel"><div class="empty">${esc(e.message)}</div></div>`; return; }
  state.factMonth = d;
  renderFactMonth();
}

function renderFactMonth() {
  const d = state.factMonth;
  const host = $('#fm-body');
  if (!d || !d.rows.length) { host.innerHTML = '<div class="empty">Нет сотрудников в периоде</div>'; return; }
  const bands = fgCategoryBands(d.categories).filter(c => c.tone > 0);
  $('#fm-meta').textContent = `${fgCategoryLegend(d.categories)} · округление до шага ${d.step_minutes} мин · ось X — непрерывное время месяца · смена через полночь — одна полоса`;
  renderCategoryFooter(d.categories);
  const W = d.days.length * FG_DAY_W, H = FG_HEAD_H + d.rows.length * FG_ROW_H;
  const hatchColors = [...new Set(d.rows.flatMap(r => Object.values(r.days)
    .filter(x => x.window && x.color).map(x => x.color)))];
  const hatchId = c => 'fgh' + hatchColors.indexOf(c);
  const S = [`<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg"><defs>`];
  hatchColors.forEach(col => S.push(
    `<pattern id="${hatchId(col)}" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
       <rect width="5" height="5" fill="${withAlpha(cssColor(col), .07)}"/>
       <line x1="0" y1="0" x2="0" y2="5" stroke="${withAlpha(cssColor(col), .6)}" stroke-width="1.6"/>
     </pattern>`));
  S.push('</defs>');
  d.days.forEach((day, i) => {
    const x = i * FG_DAY_W;
    if (day.is_weekend) S.push(`<rect x="${x}" y="${FG_HEAD_H}" width="${FG_DAY_W}" height="${H - FG_HEAD_H}" fill="#faf7f3"/>`);
    bands.forEach(c => c.spans.forEach(([h1, h2]) => S.push(
      `<rect class="fg-cat" data-cat="${esc(c.code)}" x="${(x + h1 / 24 * FG_DAY_W).toFixed(1)}" y="${FG_HEAD_H}" width="${((h2 - h1) / 24 * FG_DAY_W).toFixed(1)}" height="${H - FG_HEAD_H}" fill="rgba(23,32,54,${(.07 * c.tone).toFixed(3)})"/>`)));
    S.push(`<line x1="${x}" y1="0" x2="${x}" y2="${H}" stroke="#e6e9ee"/>`);
    S.push(`<text x="${x + FG_DAY_W / 2}" y="14" text-anchor="middle" font-size="11" font-weight="700" fill="${day.is_weekend ? '#a04a3a' : '#141a25'}">${day.day}</text>`);
    S.push(`<text x="${x + FG_DAY_W / 2}" y="26" text-anchor="middle" font-size="9" fill="#67707e">${esc(day.weekday)}</text>`);
  });
  S.push(`<line x1="${W - 1}" y1="0" x2="${W - 1}" y2="${H}" stroke="#e6e9ee"/>`);
  S.push(`<line x1="0" y1="${FG_HEAD_H}" x2="${W}" y2="${FG_HEAD_H}" stroke="#dfe3ea"/>`);
  const todayIso = todayISO();
  if (d.days.some(x => x.date === todayIso)) {
    const nowHm = new Date(Date.now() + serverShiftMs).toISOString().slice(11, 16);
    const nx = fgHmX(+todayIso.slice(8, 10) - 1, nowHm);
    S.push(`<line x1="${nx.toFixed(1)}" y1="${FG_HEAD_H}" x2="${nx.toFixed(1)}" y2="${H}" stroke="#cbb05b" stroke-width="1.4"/>`);
  }
  d.rows.forEach((r, ri) => {
    const y = FG_HEAD_H + ri * FG_ROW_H + FG_ROW_H / 2;
    S.push(`<line x1="0" y1="${FG_HEAD_H + (ri + 1) * FG_ROW_H}" x2="${W}" y2="${FG_HEAD_H + (ri + 1) * FG_ROW_H}" stroke="#eef0f4"/>`);
    d.days.forEach((day, di) => {
      const info = r.days[day.date] || {};
      const col = info.color || '#8a94a6';
      const x = di * FG_DAY_W;
      if (info.out_of_staff) return;
      if (!info.window && info.tabel) {
        S.push(`<rect x="${x + 2}" y="${y - FG_WIN_H / 2}" width="${FG_DAY_W - 4}" height="${FG_WIN_H}" rx="5" fill="${withAlpha(cssColor(col), .28)}"><title>${dateRu(day.date)}: ${esc(info.tabel)} (смены нет)</title></rect>`);
        S.push(`<text x="${x + FG_DAY_W / 2}" y="${y + 3.5}" text-anchor="middle" font-size="9.5" font-weight="800" fill="${fgDarken(col, .45)}">${esc(info.tabel)}</text>`);
        return;
      }
      if (info.window) {
        const x1 = fgHmX(di, info.window[0]); let x2 = fgHmX(di, info.window[1]);
        if (x2 <= x1) { S.push(fgWin(x1, x + FG_DAY_W, y, col, hatchId(col))); S.push(fgWin(x, x2, y, col, hatchId(col))); }
        else S.push(fgWin(x1, x2, y, col, hatchId(col)));
      }
      (info.absences || []).forEach(([a, b]) => {
        const x1 = fgHmX(di, a), x2 = fgHmX(di, b);
        S.push(`<rect x="${x1.toFixed(1)}" y="${(y - FG_BAR_H / 2 - 2).toFixed(1)}" width="${Math.max(2, x2 - x1).toFixed(1)}" height="${FG_BAR_H + 4}" fill="${withAlpha('#0e9aa7', .25)}" stroke="#0e9aa7" stroke-width="1"><title>согласованное отсутствие ${esc(a)}–${esc(b)}</title></rect>`);
        S.push(`<text x="${((x1 + x2) / 2).toFixed(1)}" y="${(y - FG_BAR_H / 2 - 4).toFixed(1)}" text-anchor="middle" font-size="8" fill="#0e9aa7">✂</text>`);
      });
    });
    r.sessions.forEach(s => {
      const x1 = fgT2x(s.start), x2 = s.end ? fgT2x(s.end) : W - 2;
      const dayInfo = r.days[s.start.slice(0, 10)] || {};
      const col = dayInfo.color || '#8a94a6';
      const title = `${r.employee.short_name} · ${dateRu(s.start.slice(0, 10))} · ${s.start.slice(11, 16)}–${s.end ? s.end.slice(11, 16) : '… (идёт сейчас)'}${dayInfo.tabel ? ` · Табель «${dayInfo.tabel}»` : ''}${dayInfo.window ? ` · окно ${dayInfo.window[0]}–${dayInfo.window[1]}` : ''}`;
      const dark = [];
      for (let di = Math.floor(x1 / FG_DAY_W); di <= Math.floor((x2 - .01) / FG_DAY_W); di++) {
        bands.forEach(c => c.spans.forEach(([h1, h2]) => {
          const a = Math.max(x1, di * FG_DAY_W + h1 / 24 * FG_DAY_W);
          const b = Math.min(x2, di * FG_DAY_W + h2 / 24 * FG_DAY_W);
          if (b > a) dark.push([a, b, c]);
        }));
      }
      dark.sort((p, q) => p[0] - q[0]);
      let cur = x1;
      dark.forEach(([a, b, c]) => {
        if (a > cur) S.push(fgBar(cur, a, y, col, false, title));
        S.push(fgBar(a, b, y, fgDarken(col, .42 * c.tone), false, `${title} · ${c.label}`));
        cur = b;
      });
      if (cur < x2) S.push(fgBar(cur, x2, y, col, !s.end, title));
    });
  });
  S.push('</svg>');
  host.innerHTML = `<div class="fg-wrap">
    <div class="fg-names" id="fm-names"><div class="fg-hd">Сотрудник · факт за ${MONTHS[d.month - 1]}</div>
      ${d.rows.map(r => `<div class="fg-row"><b>${esc(r.employee.short_name)}</b><i>${esc(r.employee.group || '')}${r.employee.position ? ' · ' + esc(r.employee.position) : ''}</i></div>`).join('')}
    </div>
    <div class="fg-scroll">${S.join('')}</div></div>
    <div class="fg-legend">
      <span><span class="sw" style="background:#34a862"></span>факт (округлено до шага); цвет = смена словаря</span>
      <span><span class="sw" style="background:${fgDarken('#34a862', .42)}"></span>ночные часы 22:00–06:00</span>
      <span><span class="sw" style="background:repeating-linear-gradient(45deg,rgba(52,168,98,.6) 0 2px,rgba(52,168,98,.07) 2px 5px)"></span>стандартное окно Табеля (штриховка)</span>
      <span><span class="sw" style="background:rgba(14,154,167,.25);border:1px solid #0e9aa7"></span>согласованное отсутствие (✂)</span>
      <span><span class="sw" style="background:rgba(52,168,98,.30);border:1.4px dashed #34a862"></span>идёт сейчас (уход не отмечен)</span>
      <span><span class="sw" style="background:rgba(240,165,0,.28)"></span>день без смены: код Табеля (В, ОТ, Б…)</span>
    </div>`;
}

/* ── режим «Сессии»: прежняя история сессий (16.4) ── */
async function loadFactSessions() {
  const pane = $('#fc-pane');
  if (!state.factFrom) {
    const t = new Date();
    state.factFrom = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-01`;
  }
  pane.innerHTML = `
    <div class="toolbar">
      <select id="fc-emp" style="max-width:240px"></select>
      <label class="field" style="margin:0"><span>С</span><input type="date" id="fc-from" value="${esc(state.factFrom)}"></label>
      <label class="field" style="margin:0"><span>По</span><input type="date" id="fc-to" value="${esc(state.factTo || todayISO())}"></label>
      <button class="btn btn-sm btn-primary" id="fc-go">Показать</button>
    </div>
    <div id="fc-body"><div class="empty">Загрузка…</div></div>`;
  let emps = (state.employees || []).filter(e => e.active !== false);
  if (!emps.length && can('employees.view')) {
    try { emps = await api('/api/employees', { silent: true }); state.employees = emps; } catch { emps = []; }
  }
  if (!emps.length && state.user.employee_id) {
    emps = [{ id: state.user.employee_id, short_name: state.user.name || 'я' }];
  }
  if (!state.factEmp && emps.length) state.factEmp = emps[0].id;
  $('#fc-emp').innerHTML = emps.map(e =>
    `<option value="${e.id}" ${e.id === state.factEmp ? 'selected' : ''}>${esc(e.short_name || e.full_name)}</option>`).join('');
  $('#fc-emp').onchange = () => { state.factEmp = +$('#fc-emp').value; };
  $('#fc-go').onclick = () => { state.factFrom = $('#fc-from').value; state.factTo = $('#fc-to').value; fetchFact(); };
  await fetchFact();
}

/* ── режим «Номера»: сетка дня (Q7, T5) ── */
async function loadFactNumbers() {
  const pane = $('#fc-pane');
  if (!state.factDay) state.factDay = todayISO();
  pane.innerHTML = `
    <div class="toolbar">
      <div class="month-nav">
        <button id="fd-prev" title="Предыдущий день">‹</button>
        <div class="label" id="fd-label">—</div>
        <button id="fd-next" title="Следующий день">›</button>
      </div>
      <input type="date" id="fd-date" value="${esc(state.factDay)}" style="max-width:165px">
      <button class="btn btn-sm" id="fd-today">Сегодня</button>
      <div class="spacer"></div>
      <span class="hint" id="fd-meta" style="margin:0"></span>
    </div>
    <div id="fd-body"><div class="empty">Загрузка…</div></div>`;
  const shiftDay = delta => {
    const t = new Date(`${state.factDay}T00:00:00`);
    t.setDate(t.getDate() + delta);
    state.factDay = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;
    loadFactNumbers();
  };
  $('#fd-prev').onclick = () => shiftDay(-1);
  $('#fd-next').onclick = () => shiftDay(1);
  $('#fd-today').onclick = () => { state.factDay = todayISO(); loadFactNumbers(); };
  $('#fd-date').onchange = e => { if (e.target.value) { state.factDay = e.target.value; loadFactNumbers(); } };
  await fetchFactDay();
}

async function fetchFactDay() {
  const body = $('#fd-body');
  $('#fd-label').textContent = dateRu(state.factDay);
  let d;
  try { d = await api(`/api/fact/day?date=${state.factDay}`); }
  catch (e) { body.innerHTML = `<div class="panel"><div class="empty">${esc(e.message)}</div></div>`; return; }
  state.factDayData = d;
  $('#fd-meta').innerHTML = `Шаг округления: <b>${d.step_minutes} мин</b> (Настройки → Расчёт) ·
    период ${dateRu(d.period.start)}–${dateRu(d.period.end)}`;
  renderFactNumbers();
}

function factMarksCell(r) {
  if (!r.marks.length) return '<span class="hint">отметок нет</span>';
  const chips = r.marks.map(m => {
    const rounded = m.rounded !== m.at ? `<span class="rnd"> → ${esc(m.rounded)}</span>` : '';
    return `<span class="punch-chip${m.kind === 'out' ? ' out' : ''}"
      title="${m.kind === 'in' ? 'Пришёл' : 'Ушёл'}: исходно ${esc(m.at)}, округлено до шага — ${esc(m.rounded)}">${m.kind === 'in' ? 'Пришёл' : 'Ушёл'} ${esc(m.at)}${rounded}</span>`;
  }).join('');
  const segs = r.segments.map(sg => `<span class="seg-chip${sg.open ? ' open' : ''}"
    title="${sg.open ? 'Сессия не закрыта отметкой «Ушёл»' : (sg.crosses_midnight ? 'Сессия пересекает полночь — показана часть дня' : 'Сопряжённая сессия после округления')}">${esc(sg.start)}–${sg.open ? '…' : esc(sg.end)}</span>`).join('');
  return `${chips}${segs ? ` <span class="hint">→</span> ${segs}` : ''}`;
}

function factOtCell(c) {
  if (!c) return '';
  const codes = Object.entries(c.codes || {}).map(([t, m]) =>
    `<span class="v4-code ${t.startsWith('ДН') ? 'n' : 'd'}" style="display:inline-block;margin:1px 2px">${esc(t)} ${hours(m / 60)}</span>`).join('');
  if (codes) return codes;
  if (c.overtime_minutes) {
    return `<span class="badge muted" title="Переработка без дневных/ночных кодов">перераб. ${hours(c.overtime_minutes / 60)}${c.pays_overtime ? '' : ' · в банк'}</span>`;
  }
  return '<span class="hint">—</span>';
}

function renderFactNumbers() {
  const d = state.factDayData;
  const body = $('#fd-body');
  if (!d) return;
  const rows = d.rows.map(r => {
    const who = `<td class="who" data-label="Сотрудник">${esc(r.employee.short_name)}<small>${esc(r.employee.group)}${r.employee.position ? ' · ' + esc(r.employee.position) : ''}</small></td>`;
    if (r.out_of_staff) {
      return `<tr data-emp="${r.employee.id}">${who}<td colspan="7" data-label=""><span class="badge muted"
        title="День вне интервала трудоустройства (R35)">не в штате в этот день</span></td></tr>`;
    }
    const c = r.card;
    const marks = `<td data-label="Отметки">${factMarksCell(r)}</td>`;
    if (!c) {
      return `<tr data-emp="${r.employee.id}">${who}${marks}<td colspan="6" data-label="" style="color:var(--danger)">${esc(r.error || 'Нет данных расчёта за период')}</td></tr>`;
    }
    const flags = (c.flags || []).map(f =>
      `<span class="v4-flagtext ${V4_FLAG_CLASS[f.code] || ''}" title="${esc(f.hint || '')}">● ${esc(f.title)}</span>`).join(' ')
      || '<span class="hint">нет</span>';
    return `<tr data-emp="${r.employee.id}">
      ${who}
      ${marks}
      <td data-label="Окно" class="num" title="Стандартное окно кода Табеля (CFG-WINDOWS) — жёстко из кода (Q1)">${c.window ? `${esc(c.window[0])}–${esc(c.window[1])}` : '—'}<small class="hint" style="display:block">Табель: «${esc(c.timesheet_value)}»</small></td>
      <td data-label="План" class="num" title="Расчётный план = длина окна (R34); план строки Табеля — информационный">${v4Hours(c.plan_minutes / 60)}${c.timesheet_plan_minutes ? `<small class="hint" style="display:block">строка ${hours(c.timesheet_plan_minutes / 60)}</small>` : ''}</td>
      <td data-label="Отработано" class="num"><b>${v4Hours(c.work_minutes / 60)}</b><small class="hint" style="display:block">факт ${v4Hours(c.fact_minutes / 60)}</small></td>
      <td data-label="Недоработка" class="num">${c.debt_minutes ? `<span class="v4-debt" title="Недостача дня (окно − отработано)">−${hours(c.debt_minutes / 60)}</span>` : '—'}${c.plan_equals_fact ? ' <span class="badge info" title="Применён «План=Факт»: день освобождён от недостачи">П=Ф</span>' : ''}</td>
      <td data-label="Переработка" class="num">${factOtCell(c)}</td>
      <td data-label="Флаги"><div style="display:flex;flex-direction:column;gap:2px">${flags}</div></td></tr>`;
  }).join('');
  body.innerHTML = `
    <div class="table-wrap"><table class="data responsive">
      <thead><tr><th class="who">Сотрудник</th><th>Отметки (СКУД → округление)</th>
        <th>Окно (из Табеля)</th><th>План</th><th>Отработано</th><th>Недоработка</th>
        <th>Переработка</th><th>Флаги (из Графика)</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="8" class="empty">${d.all_employees ? 'В этот день никто не трудоустроен' : 'Нет данных'}</td></tr>`}</tbody>
    </table></div>
    <p class="hint">${dateRu(d.date)} · период расчёта ${dateRu(d.period.start)}–${dateRu(d.period.end)}${d.granularity === 'half_month' ? ' (половина месяца)' : ''}.
      Часы, недостача, переработка и флаги — из движка (settle периода); отметки показаны
      сырыми и округлёнными до шага ${d.step_minutes} мин. Оперативная доска «кто на работе» —
      в разделе «Отметки» (Q7); исходные сессии без округления — во вкладке «Сотрудник».
      Подробная карточка сотрудника с трассой расчёта — в слое 3 (клик по строке).</p>`;
}

async function fetchFact() {
  const body = $('#fc-body');
  if (!state.factEmp) { body.innerHTML = '<div class="panel"><div class="empty">Выберите сотрудника</div></div>'; return; }
  let d;
  try {
    d = await api(`/api/fact/sessions?employee_id=${state.factEmp}&first=${state.factFrom}&last=${state.factTo || todayISO()}`);
  } catch (e) { body.innerHTML = `<div class="panel"><div class="empty">${esc(e.message)}</div></div>`; return; }
  const byDay = {};
  d.sessions.forEach(s => {
    const key = s.start_local.slice(0, 10);
    (byDay[key] = byDay[key] || []).push(s);
  });
  const hm = iso => iso ? iso.slice(11, 16) : '—';
  const rows = Object.keys(byDay).sort().map(day => byDay[day].map(s => {
    const dur = s.minutes != null ? `${hours(s.minutes / 60)} ч` : 'идёт сейчас';
    const badges = [
      s.started_before_range ? '<span class="badge muted" title="Сессия открыта отметкой до начала диапазона">начата до диапазона</span>' : '',
      s.closed_after_range ? '<span class="badge muted" title="Уход — за правой границей диапазона">закрыта после диапазона</span>' : '',
      s.open ? '<span class="badge warn" title="Сотрудник не отметил «Ушёл» — сессия открыта">открыта</span>' : '',
    ].join(' ');
    return `<tr>
      <td data-label="День">${dateRu(day)}</td>
      <td data-label="Пришёл">${hm(s.start_local)}</td>
      <td data-label="Ушёл">${s.open ? '—' : hm(s.end_local)}</td>
      <td data-label="Длительность">${dur}</td>
      <td data-label="Примечания">${badges}</td></tr>`;
  }).join('')).join('');
  body.innerHTML = `
    <div class="panel"><h3 class="panel-title">${esc(d.employee.short_name || d.employee.full_name || '')} ·
      сессий: ${d.sessions.length}</h3>
      <div class="table-wrap"><table class="data responsive">
        <thead><tr><th>День</th><th>Пришёл</th><th>Ушёл</th><th>Длительность</th><th>Примечания</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="5" class="empty">Сессий в диапазоне нет</td></tr>'}</tbody>
      </table></div>
      <p class="hint">Моменты исходные (с секундами в источнике), без округления и дневной нарезки:
        сессия может пересекать полночь. Расчётные часы — во вкладке «Управленческий табель».</p></div>`;
}
