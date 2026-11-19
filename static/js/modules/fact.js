'use strict';

/* ══════════════════════════════════════════════════════════════════
   ФАКТ — слой 2 модели «График = 4 слоя».
   Три представления одних и тех же отметок СКУД (порядок вкладок: Месяц — первая и по
   умолчанию, затем День и Сотрудник):
   · «Месяц» — гант фактических присутствий на непрерывной оси времени;
   · «День» (Q7) — один день глазами движка: сырые отметки и округление до шага,
     сопряжённые сессии, окно из кода Табеля, план / отработано / недостача /
     переработка по категориям и флаги из Графика. Все числа считает сервер
     (/api/fact/day, settle за период дня); шаг округления — из настроек, а не из
     интерфейса: источник истины — движок;
   · «Сотрудник» — исходная история «пришёл — ушёл» за диапазон, без округления
     (три индексных запроса на диапазон; бэкенд отдаёт только моменты, визуализация — здесь).
   Оперативная доска «кто на работе» — отдельный пункт меню «Отметки» (Q7).
   Модуль на lit-html (ADR-0013, раздел 7): разметка — шаблоны, вставки экранируются сами.
   ══════════════════════════════════════════════════════════════════ */
import { can, renderCategoryFooter } from '../app.js';
import {
  $, api, cssColor, dateRu, hours, loadGeneration, MONTHS, serverShiftMs, state, todayISO, withAlpha,
} from '../core.js';
import { html, mount, nothing, render, svg } from '../ui/html.js';
import { monthNav, V4_FLAG_CLASS, v4Hours } from './timesheet_common.js';

state.factEmp = state.factEmp || null;
state.factFrom = state.factFrom || null;

/* что показывает слой по вкладкам: загрузка, ошибка либо ответ сервера */
const tab = {
  month: { loading: true, error: '', meta: '' },
  day: { loading: true, error: '' },
  sessions: { loading: true, error: '', data: null, emps: [] },
};

export async function loadFact() {
  state.factMode = state.factMode || 'month';
  draw();
  if (state.factMode === 'sessions') await loadFactSessions();
  else if (state.factMode === 'month') await loadFactMonth();
  else await loadFactNumbers();
}

function draw() {
  const host = $('#view-fact');
  if (host) render(layerTemplate(), mount(host));
}

function setMode(mode) {
  if (state.factMode === mode) return;
  state.factMode = mode;
  loadFact();
}

function layerTemplate() {
  const mode = state.factMode;
  return html`
    <div class="page-head">
      <div><h2>Слой 2 · Факт</h2>
        <div class="sub">Слой 2 · отметки СКУД: «Месяц» — гант фактических
          присутствий на непрерывной оси времени (ночи темнее, окно Табеля
          штриховкой); «День» — день глазами движка (округление до шага, окно из
          Табеля, план / отработано / недостача / переработка, флаги из Графика);
          «Сотрудник» — исходная история «пришёл — ушёл» без округления</div></div>
      <div class="spacer"></div>
      <div class="seg" id="fc-mode">
        <button data-mode="month" class=${mode === 'month' ? 'active' : ''} @click=${() => setMode('month')}
          title="Гант месяца: округлённые сессии на непрерывной оси времени, ночи темнее, окно Табеля штриховкой">Месяц</button>
        <button data-mode="numbers" class=${mode === 'numbers' ? 'active' : ''} @click=${() => setMode('numbers')}
          title="Сетка дня: отметки, округлённые до шага, и расчёт дня">День</button>
        <button data-mode="sessions" class=${mode === 'sessions' ? 'active' : ''} @click=${() => setMode('sessions')}
          title="История сессий «пришёл — ушёл» одного сотрудника: точные моменты, без округления">Сотрудник</button>
      </div>
    </div>
    <div id="fc-pane">${mode === 'month' ? monthPane() : mode === 'sessions' ? sessionsPane() : dayPane()}</div>`;
}

const errorPanel = text => html`<div class="panel"><div class="empty">${text}</div></div>`;

/* ── вкладка «Месяц»: ГАНТ фактических присутствий ──
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
   зависит ни от порядка категорий в настройках, ни от их кодов. */
export function fgCategoryBands(categories) {
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
const fgCategoryLegend = categories => fgCategoryBands(categories).map(c => c.label).join(' · ');
function fgDarken(hex, k) {
  const n = parseInt(cssColor(hex).slice(1), 16);
  const f = v => Math.round(v * (1 - k));
  return `rgb(${f((n >> 16) & 255)},${f((n >> 8) & 255)},${f(n & 255)})`;
}
function fgHmX(di, hms) {
  const [h, m] = hms.split(':').map(Number);
  return di * FG_DAY_W + (h + m / 60) / 24 * FG_DAY_W;
}
const fgT2x = iso => fgHmX(+iso.slice(8, 10) - 1, iso.slice(11, 16));
function fgBar(x1, x2, y, fill, open, title) {
  const w = Math.max(2, x2 - x1);
  const color = cssColor(fill);
  return open
    ? svg`<rect x=${x1.toFixed(1)} y=${(y - FG_BAR_H / 2).toFixed(1)} width=${w.toFixed(1)} height=${FG_BAR_H} rx="3"
        fill=${withAlpha(color, .30)} stroke=${color} stroke-width="1.4" stroke-dasharray="4 3"><title>${title || ''}</title></rect>`
    : svg`<rect x=${x1.toFixed(1)} y=${(y - FG_BAR_H / 2).toFixed(1)} width=${w.toFixed(1)} height=${FG_BAR_H} rx="3"
        fill=${color}><title>${title || ''}</title></rect>`;
}
const fgWin = (x1, x2, y, col, pid) => svg`<rect x=${x1.toFixed(1)} y=${(y - FG_WIN_H / 2).toFixed(1)}
  width=${Math.max(2, x2 - x1).toFixed(1)} height=${FG_WIN_H} fill=${`url(#${pid})`}
  stroke=${withAlpha(cssColor(col), .55)} stroke-dasharray="3 2"><title>стандартное окно Табеля (ожидание)</title></rect>`;

async function loadFactMonth() {
  tab.month.loading = true; tab.month.error = '';
  draw();
  const fresh = loadGeneration('fact-month');
  let d;
  try { d = await api(`/api/fact/month?year=${state.year}&month=${state.month}`); }
  catch (e) { if (fresh()) { tab.month.loading = false; tab.month.error = String(e.message); draw(); } return; }
  if (!fresh()) return;          // пока ждали ответ, перелистнули месяц
  state.factMonth = d;
  tab.month.loading = false;
  if (d.rows.length) {
    tab.month.meta = `${fgCategoryLegend(d.categories)} · округление до шага ${d.step_minutes} мин · ось X — непрерывное время месяца · смена через полночь — одна полоса`;
    renderCategoryFooter(d.categories);
  }
  draw();
}

function monthPane() {
  const t = tab.month;
  let body;
  if (t.loading) body = html`<div class="empty">Загрузка…</div>`;
  else if (t.error) body = errorPanel(t.error);
  else if (!state.factMonth || !state.factMonth.rows.length) body = html`<div class="empty">Нет сотрудников в периоде</div>`;
  else body = gantt(state.factMonth);
  return html`
    <div class="toolbar">
      ${monthNav('fm', loadFactMonth)}
      <div class="spacer"></div>
      <span class="hint" id="fm-meta" style="margin:0">${t.loading || t.error ? '' : t.meta}</span>
    </div>
    <div id="fm-body">${body}</div>`;
}

function gantt(d) {
  const bands = fgCategoryBands(d.categories).filter(c => c.tone > 0);
  const W = d.days.length * FG_DAY_W, H = FG_HEAD_H + d.rows.length * FG_ROW_H;
  const hatchColors = [...new Set(d.rows.flatMap(r => Object.values(r.days)
    .filter(x => x.window && x.color).map(x => x.color)))];
  const hatchId = c => 'fgh' + hatchColors.indexOf(c);
  const S = [];
  d.days.forEach((day, i) => {
    const x = i * FG_DAY_W;
    if (day.is_weekend) S.push(svg`<rect x=${x} y=${FG_HEAD_H} width=${FG_DAY_W} height=${H - FG_HEAD_H} style="fill: var(--surface-1)"/>`);
    bands.forEach(c => c.spans.forEach(([h1, h2]) => S.push(
      svg`<rect class="fg-cat" data-cat=${c.code} x=${(x + h1 / 24 * FG_DAY_W).toFixed(1)} y=${FG_HEAD_H} width=${((h2 - h1) / 24 * FG_DAY_W).toFixed(1)} height=${H - FG_HEAD_H}
        style=${`fill: color-mix(in srgb, var(--text) ${(7 * c.tone).toFixed(1)}%, transparent)`}/>`)));
    S.push(svg`<line x1=${x} y1="0" x2=${x} y2=${H} style="stroke: var(--line-soft)"/>`);
    S.push(svg`<text x=${x + FG_DAY_W / 2} y="14" text-anchor="middle" font-size="11" font-weight="700"
      style=${`fill: ${day.is_weekend ? 'var(--danger-fg)' : 'var(--text)'}`}>${day.day}</text>`);
    S.push(svg`<text x=${x + FG_DAY_W / 2} y="26" text-anchor="middle" font-size="9" style="fill: var(--muted)">${day.weekday}</text>`);
  });
  S.push(svg`<line x1=${W - 1} y1="0" x2=${W - 1} y2=${H} style="stroke: var(--line-soft)"/>`);
  S.push(svg`<line x1="0" y1=${FG_HEAD_H} x2=${W} y2=${FG_HEAD_H} style="stroke: var(--line)"/>`);
  const todayIso = todayISO();
  if (d.days.some(x => x.date === todayIso)) {
    const nowHm = new Date(Date.now() + serverShiftMs).toISOString().slice(11, 16);
    const nx = fgHmX(+todayIso.slice(8, 10) - 1, nowHm);
    S.push(svg`<line x1=${nx.toFixed(1)} y1=${FG_HEAD_H} x2=${nx.toFixed(1)} y2=${H} style="stroke: var(--gold)" stroke-width="1.4"/>`);
  }
  d.rows.forEach((r, ri) => {
    const y = FG_HEAD_H + ri * FG_ROW_H + FG_ROW_H / 2;
    S.push(svg`<line x1="0" y1=${FG_HEAD_H + (ri + 1) * FG_ROW_H} x2=${W} y2=${FG_HEAD_H + (ri + 1) * FG_ROW_H} style="stroke: var(--line-soft)"/>`);
    d.days.forEach((day, di) => {
      const info = r.days[day.date] || {};
      const col = info.color || '#8a94a6';
      const x = di * FG_DAY_W;
      if (info.out_of_staff) return;
      if (!info.window && info.tabel) {
        S.push(svg`<rect x=${x + 2} y=${y - FG_WIN_H / 2} width=${FG_DAY_W - 4} height=${FG_WIN_H} rx="5" fill=${withAlpha(cssColor(col), .28)}><title>${dateRu(day.date)}: ${info.tabel} (смены нет)</title></rect>`);
        S.push(svg`<text x=${x + FG_DAY_W / 2} y=${y + 3.5} text-anchor="middle" font-size="9.5" font-weight="800" fill=${fgDarken(col, .45)}>${info.tabel}</text>`);
        return;
      }
      if (info.window) {
        const x1 = fgHmX(di, info.window[0]); const x2 = fgHmX(di, info.window[1]);
        if (x2 <= x1) { S.push(fgWin(x1, x + FG_DAY_W, y, col, hatchId(col))); S.push(fgWin(x, x2, y, col, hatchId(col))); }
        else S.push(fgWin(x1, x2, y, col, hatchId(col)));
      }
      (info.absences || []).forEach(([a, b]) => {
        const x1 = fgHmX(di, a), x2 = fgHmX(di, b);
        S.push(svg`<rect x=${x1.toFixed(1)} y=${(y - FG_BAR_H / 2 - 2).toFixed(1)} width=${Math.max(2, x2 - x1).toFixed(1)} height=${FG_BAR_H + 4}
          fill=${withAlpha('#0e9aa7', .25)} stroke="#0e9aa7" stroke-width="1"><title>согласованное отсутствие ${a}–${b}</title></rect>`);
        S.push(svg`<text x=${((x1 + x2) / 2).toFixed(1)} y=${(y - FG_BAR_H / 2 - 4).toFixed(1)} text-anchor="middle" font-size="8" fill="#0e9aa7">✂</text>`);
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
  return html`<div class="fg-wrap">
    <div class="fg-names" id="fm-names"><div class="fg-hd">Сотрудник · факт за ${MONTHS[d.month - 1]}</div>
      ${d.rows.map(r => html`<div class="fg-row"><b>${r.employee.short_name}</b><i>${r.employee.group || ''}${r.employee.position ? ' · ' + r.employee.position : ''}</i></div>`)}
    </div>
    <div class="fg-scroll"><svg width=${W} height=${H} viewBox=${`0 0 ${W} ${H}`} xmlns="http://www.w3.org/2000/svg"><defs>
      ${hatchColors.map(col => svg`<pattern id=${hatchId(col)} width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <rect width="5" height="5" fill=${withAlpha(cssColor(col), .07)}/>
        <line x1="0" y1="0" x2="0" y2="5" stroke=${withAlpha(cssColor(col), .6)} stroke-width="1.6"/></pattern>`)}
      </defs>${S}</svg></div></div>
    <div class="fg-legend">
      <span><span class="sw" style="background:#34a862"></span>факт (округлено до шага); цвет = смена словаря</span>
      <span><span class="sw" style=${`background:${fgDarken('#34a862', .42)}`}></span>ночные часы 22:00–06:00</span>
      <span><span class="sw" style="background:repeating-linear-gradient(45deg,rgba(52,168,98,.6) 0 2px,rgba(52,168,98,.07) 2px 5px)"></span>стандартное окно Табеля (штриховка)</span>
      <span><span class="sw" style="background:rgba(14,154,167,.25);border:1px solid #0e9aa7"></span>согласованное отсутствие (✂)</span>
      <span><span class="sw" style="background:rgba(52,168,98,.30);border:1.4px dashed #34a862"></span>идёт сейчас (уход не отмечен)</span>
      <span><span class="sw" style="background:rgba(240,165,0,.28)"></span>день без смены: код Табеля (В, ОТ, Б…)</span>
    </div>`;
}

/* ── вкладка «Сотрудник»: прежняя история сессий (16.4) ── */
async function loadFactSessions() {
  if (!state.factFrom) {
    const t = new Date();
    state.factFrom = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-01`;
  }
  tab.sessions.loading = true; tab.sessions.data = null; tab.sessions.error = '';
  draw();
  let emps = (state.employees || []).filter(e => e.active !== false);
  if (!emps.length && can('employees.view')) {
    try { emps = await api('/api/employees', { silent: true }); state.employees = emps; } catch { emps = []; }
  }
  if (!emps.length && state.user.employee_id) {
    emps = [{ id: state.user.employee_id, short_name: state.user.name || 'я' }];
  }
  if (!state.factEmp && emps.length) state.factEmp = emps[0].id;
  tab.sessions.emps = emps;
  draw();
  await fetchFact();
}

async function fetchFact() {
  const t = tab.sessions;
  if (!state.factEmp) { t.loading = false; t.data = null; t.error = 'Выберите сотрудника'; draw(); return; }
  const fresh = loadGeneration('fact-sessions');
  t.loading = true; t.error = '';
  draw();
  let d;
  try {
    d = await api(`/api/fact/sessions?employee_id=${state.factEmp}&first=${state.factFrom}&last=${state.factTo || todayISO()}`);
  } catch (e) { if (fresh()) { t.loading = false; t.error = String(e.message); draw(); } return; }
  if (!fresh()) return;          // пока ждали ответ, сменили сотрудника или даты
  t.loading = false; t.data = d;
  draw();
}

function sessionRows(d) {
  const byDay = {};
  d.sessions.forEach(s => {
    const key = s.start_local.slice(0, 10);
    (byDay[key] = byDay[key] || []).push(s);
  });
  const hm = iso => (iso ? iso.slice(11, 16) : '—');
  return Object.keys(byDay).sort().flatMap(day => byDay[day].map(s => html`<tr>
      <td data-label="День">${dateRu(day)}</td>
      <td data-label="Пришёл">${hm(s.start_local)}</td>
      <td data-label="Ушёл">${s.open ? '—' : hm(s.end_local)}</td>
      <td data-label="Длительность">${s.minutes != null ? `${hours(s.minutes / 60)} ч` : 'идёт сейчас'}</td>
      <td data-label="Примечания">${s.started_before_range ? html`<span class="badge muted" title="Сессия открыта отметкой до начала диапазона">начата до диапазона</span> ` : nothing}${
        s.closed_after_range ? html`<span class="badge muted" title="Уход — за правой границей диапазона">закрыта после диапазона</span> ` : nothing}${
        s.open ? html`<span class="badge warn" title="Сотрудник не отметил «Ушёл» — сессия открыта">открыта</span>` : nothing}</td></tr>`));
}

function sessionsBody() {
  const t = tab.sessions;
  if (t.loading) return html`<div class="empty">Загрузка…</div>`;
  if (t.error) return errorPanel(t.error);
  const d = t.data;
  if (!d) return nothing;
  const rows = sessionRows(d);
  return html`
    <div class="panel"><h3 class="panel-title">${d.employee.short_name || d.employee.full_name || ''} ·
      сессий: ${d.sessions.length}</h3>
      <div class="table-wrap"><table class="data responsive">
        <thead><tr><th>День</th><th>Пришёл</th><th>Ушёл</th><th>Длительность</th><th>Примечания</th></tr></thead>
        <tbody>${rows.length ? rows : html`<tr><td colspan="5" class="empty">Сессий в диапазоне нет</td></tr>`}</tbody>
      </table></div>
      <p class="hint">Моменты исходные (с секундами в источнике), без округления и дневной нарезки:
        сессия может пересекать полночь. Расчётные часы — во вкладке «Управленческий табель».</p></div>`;
}

function sessionsPane() {
  return html`
    <div class="toolbar">
      <select id="fc-emp" style="max-width:240px" @change=${e => { state.factEmp = +e.target.value; }}>
        ${tab.sessions.emps.map(e => html`<option value=${e.id} ?selected=${e.id === state.factEmp}>${e.short_name || e.full_name}</option>`)}</select>
      <label class="field" style="margin:0"><span>С</span><input type="date" id="fc-from" .value=${state.factFrom}></label>
      <label class="field" style="margin:0"><span>По</span><input type="date" id="fc-to" .value=${state.factTo || todayISO()}></label>
      <button class="btn btn-sm btn-primary" id="fc-go" @click=${() => {
        state.factFrom = $('#fc-from').value; state.factTo = $('#fc-to').value; fetchFact();
      }}>Показать</button>
    </div>
    <div id="fc-body">${sessionsBody()}</div>`;
}

/* ── вкладка «День»: сетка дня (Q7, T5) ── */
async function loadFactNumbers() {
  if (!state.factDay) state.factDay = todayISO();
  await fetchFactDay();
}

function shiftDay(delta) {
  const t = new Date(`${state.factDay}T00:00:00`);
  t.setDate(t.getDate() + delta);
  state.factDay = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;
  loadFactNumbers();
}

async function fetchFactDay() {
  tab.day.loading = true; tab.day.error = '';
  draw();
  const fresh = loadGeneration('fact-day');
  let d;
  try { d = await api(`/api/fact/day?date=${state.factDay}`); }
  catch (e) { if (fresh()) { tab.day.loading = false; tab.day.error = String(e.message); draw(); } return; }
  if (!fresh()) return;          // пока ждали ответ, сменили день
  state.factDayData = d;
  tab.day.loading = false;
  draw();
}

function marksCell(r) {
  if (!r.marks.length) return html`<span class="hint">отметок нет</span>`;
  const chips = r.marks.map(m => html`<span class="punch-chip${m.kind === 'out' ? ' out' : ''}"
      title=${`${m.kind === 'in' ? 'Пришёл' : 'Ушёл'}: исходно ${m.at}, округлено до шага — ${m.rounded}`}>${m.kind === 'in' ? 'Пришёл' : 'Ушёл'} ${m.at}${
      m.rounded !== m.at ? html`<span class="rnd"> → ${m.rounded}</span>` : nothing}</span>`);
  const segs = r.segments.map(sg => html`<span class="seg-chip${sg.open ? ' open' : ''}"
    title=${sg.open ? 'Сессия не закрыта отметкой «Ушёл»' : (sg.crosses_midnight ? 'Сессия пересекает полночь — показана часть дня' : 'Сопряжённая сессия после округления')}>${sg.start}–${sg.open ? '…' : sg.end}</span> `);
  return html`${chips}${segs.length ? html` <span class="hint">→</span> ${segs}` : nothing}`;
}

function overtimeCell(c) {
  if (!c) return nothing;
  const codes = Object.entries(c.codes || {}).map(([t, m]) =>
    html`<span class="v4-code ${t.startsWith('ДН') ? 'n' : 'd'}" style="display:inline-block;margin:1px 2px">${t} ${hours(m / 60)}</span>`);
  if (codes.length) return codes;
  if (c.overtime_minutes) {
    return html`<span class="badge muted" title="Переработка без дневных/ночных кодов">перераб. ${hours(c.overtime_minutes / 60)}${c.pays_overtime ? '' : ' · в банк'}</span>`;
  }
  return html`<span class="hint">—</span>`;
}

function dayRow(r) {
  const who = html`<td class="who" data-label="Сотрудник">${r.employee.short_name}<small>${r.employee.group}${r.employee.position ? ' · ' + r.employee.position : ''}</small></td>`;
  if (r.out_of_staff) {
    return html`<tr data-emp=${r.employee.id}>${who}<td colspan="7" data-label=""><span class="badge muted"
      title="День вне интервала трудоустройства (R35)">не в штате в этот день</span></td></tr>`;
  }
  const c = r.card;
  const marks = html`<td data-label="Отметки">${marksCell(r)}</td>`;
  if (!c) {
    return html`<tr data-emp=${r.employee.id}>${who}${marks}<td colspan="6" data-label="" style="color:var(--danger)">${r.error || 'Нет данных расчёта за период'}</td></tr>`;
  }
  const flags = (c.flags || []).map(f =>
    html`<span class="v4-flagtext ${V4_FLAG_CLASS[f.code] || ''}" title=${f.hint || ''}>● ${f.title}</span> `);
  return html`<tr data-emp=${r.employee.id}>
    ${who}
    ${marks}
    <td data-label="Окно" class="num" title="Стандартное окно кода Табеля (CFG-WINDOWS) — жёстко из кода (Q1)">${c.window ? `${c.window[0]}–${c.window[1]}` : '—'}<small class="hint" style="display:block">Табель: «${c.timesheet_value}»</small></td>
    <td data-label="План" class="num" title="Расчётный план = длина окна (R34); план строки Табеля — информационный">${v4Hours(c.plan_minutes / 60)}${c.timesheet_plan_minutes ? html`<small class="hint" style="display:block">строка ${hours(c.timesheet_plan_minutes / 60)}</small>` : nothing}</td>
    <td data-label="Отработано" class="num"><b>${v4Hours(c.work_minutes / 60)}</b><small class="hint" style="display:block">факт ${v4Hours(c.fact_minutes / 60)}</small></td>
    <td data-label="Недоработка" class="num">${c.debt_minutes ? html`<span class="v4-debt" title="Недостача дня (окно − отработано)">−${hours(c.debt_minutes / 60)}</span>` : '—'}${c.plan_equals_fact ? html` <span class="badge info" title="Применён «План=Факт»: день освобождён от недостачи">П=Ф</span>` : nothing}</td>
    <td data-label="Переработка" class="num">${overtimeCell(c)}</td>
    <td data-label="Флаги"><div style="display:flex;flex-direction:column;gap:2px">${flags.length ? flags : html`<span class="hint">нет</span>`}</div></td></tr>`;
}

function dayBody() {
  const t = tab.day;
  if (t.loading) return html`<div class="empty">Загрузка…</div>`;
  if (t.error) return errorPanel(t.error);
  const d = state.factDayData;
  if (!d) return nothing;
  return html`
    <div class="table-wrap"><table class="data responsive">
      <thead><tr><th class="who">Сотрудник</th><th>Отметки (СКУД → округление)</th>
        <th>Окно (из Табеля)</th><th>План</th><th>Отработано</th><th>Недоработка</th>
        <th>Переработка</th><th>Флаги (из Графика)</th></tr></thead>
      <tbody>${d.rows.length ? d.rows.map(dayRow)
        : html`<tr><td colspan="8" class="empty">${d.all_employees ? 'В этот день никто не трудоустроен' : 'Нет данных'}</td></tr>`}</tbody>
    </table></div>
    <p class="hint">${dateRu(d.date)} · период расчёта ${dateRu(d.period.start)}–${dateRu(d.period.end)}${d.granularity === 'half_month' ? ' (половина месяца)' : ''}.
      Часы, недостача, переработка и флаги — из движка (settle периода); отметки показаны
      сырыми и округлёнными до шага ${d.step_minutes} мин. Оперативная доска «кто на работе» —
      в разделе «Отметки» (Q7); исходные сессии без округления — во вкладке «Сотрудник».
      Подробная карточка сотрудника с трассой расчёта — в слое 3 (клик по строке).</p>`;
}

function dayPane() {
  const d = !tab.day.loading && !tab.day.error ? state.factDayData : null;
  return html`
    <div class="toolbar">
      <div class="month-nav">
        <button id="fd-prev" title="Предыдущий день" @click=${() => shiftDay(-1)}>‹</button>
        <div class="label" id="fd-label">${dateRu(state.factDay)}</div>
        <button id="fd-next" title="Следующий день" @click=${() => shiftDay(1)}>›</button>
      </div>
      <input type="date" id="fd-date" .value=${state.factDay} style="max-width:165px"
        @change=${e => { if (e.target.value) { state.factDay = e.target.value; loadFactNumbers(); } }}>
      <button class="btn btn-sm" id="fd-today" @click=${() => { state.factDay = todayISO(); loadFactNumbers(); }}>Сегодня</button>
      <div class="spacer"></div>
      <span class="hint" id="fd-meta" style="margin:0">${d ? html`Шаг округления: <b>${d.step_minutes} мин</b> (Настройки → Расчёт) ·
        период ${dateRu(d.period.start)}–${dateRu(d.period.end)}` : nothing}</span>
    </div>
    <div id="fd-body">${dayBody()}</div>`;
}
