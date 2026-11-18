/* ══════════════════════════════════════════════════════════════════════
   «ШАХМАТКА» — шахматка батлеров (§6.2) и табло дня (§6.3).
   Фон дня батлера — смена по Графику; красное — перегруз, «вне смены», подмена.
   Табло — заезды / выезды / проживают / требуют внимания и «не заехали»;
   на телефоне — одной колонкой. Предупреждения сервер считает при каждом чтении.
   Модуль на lit-html (ADR-0013, раздел 7): разметка — шаблоны, вставки экранируются сами.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

import { can } from '../app.js';
import { $, $$, api, closeModal, dateRu, loadGenerationFor, openModal, toast } from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { relativesView, STAYS_STATUS } from './stays_forms.js';
import { openOooForm } from './stays_ooo.js';
import {
  staysCodeTagView, staysDayHeadView, staysFilterView, staysGuestMarkView, loadStays, staysMonthNavView, openReservationCard, staysAddDays, staysFocusDay, staysFund,
  staysFundParams, staysMonthRange, staysPeopleParams, staysState, staysToday, staysWeight,
} from './stays.js';

const STAYS_DUTY = { shift: 'на смене', off: 'выходной', absent: 'отсутствие' };
const STAYS_WARN = { off_shift: 'вне смены', overload: 'перегруз', need_replacement: 'нужна подмена',
  hole: 'гости без батлера', double_cover: 'два батлера у гостя' };
export const boardState = { day: null, tab: 'arrivals' };   // месяц — общий state; фильтры — staysState.filters

/* подпись поля в окнах: подпись над элементом управления */
const fieldRow = (label, control) => html`<label class="field"><span>${label}</span>${control}</label>`;

/* ─────────────── Шахматка батлеров ─────────────── */
export async function renderButlersBoard(body) {
  const { first, last } = staysMonthRange();
  const fresh = loadGenerationFor(body);    // запоздавший ответ не перерисовывает (stays.js)
  const data = await api(`/api/stays/board/butlers?first=${first}&last=${last}`, { silent: true });
  if (!fresh()) return;
  const today = staysToday();
  const rerender = () => renderButlersBoard(body);
  render(html`
    <div class="sb-toolbar">
      ${staysMonthNavView(body, rerender)}
      <span class="muted">лимит нагрузки — ${staysWeight(data.limit)}</span>
    </div>
    <div class="sb-grid bb-grid" style=${`--days:${data.days.length}`}>
      <div class="bb-row sb-head"><div class="sb-unit">Батлер</div>${data.days.map(d => staysDayHeadView(d, today))}</div>
      ${data.rows.length ? data.rows.map(r => html`<div class="bb-row"><div class="sb-unit"><b>${r.name}</b>${r.escort ? nothing : html`<small>не в списке</small>`}</div>
        ${r.cells.map(c => html`<div class="bb-cell duty-${c.duty}${c.warnings.length ? ' warn' : ''}" data-bb-emp=${r.employee_id}
          data-day=${c.day} data-warn=${c.warnings.join(' ')} title=${STAYS_DUTY[c.duty] + (c.code ? ' · ' + c.code : '')}
          @click=${() => openButlerDay(r, c, rerender)}>
          <div>${c.units.map(u => u.label).join(', ') || (c.duty === 'shift' ? '—' : STAYS_DUTY[c.duty])}</div>
          ${c.load ? html`<small>${staysWeight(c.load)}/${staysWeight(data.limit)}</small>` : nothing}
          ${c.warnings.length ? html`<small class="bb-w">${c.warnings.map(w => STAYS_WARN[w] || w).join(', ')}</small>` : nothing}
        </div>`)}</div>`)
        : html`<div class="empty">Список «Сопровождают гостей» пуст — Настройки → Сопровождение</div>`}
    </div>`, mount(body));
  staysFocusDay(body);
}

async function openButlerDay(row, cell, onChanged) {
  const assign = can('stays.assign');
  const offShift = cell.warnings.includes('off_shift') && assign;
  const kinds = offShift ? (await api('/api/shift-types', { silent: true })).filter(t => t.kind === 'work' && t.active) : [];
  openModal({
    title: `${row.name} · ${dateRu(cell.day)}`, subtitle: `${STAYS_DUTY[cell.duty]}${cell.code ? ' · ' + cell.code : ''} · нагрузка ${staysWeight(cell.load)}`,
    body: html`${cell.units.length ? cell.units.map(u => html`<div class="sb-line"><b>${u.label}</b>
        <button class="btn btn-sm btn-ghost" data-open-res=${u.reservation_id}>Бронь…</button>
        ${assign && cell.warnings.includes('need_replacement') ? html`<button class="btn btn-sm" data-replace-res=${u.reservation_id}>Заменить</button>` : nothing}</div>`)
        : html`<p class="muted">Гостей не ведёт</p>`}
      ${cell.guests.length ? html`<p>${cell.guests.join(', ')}</p>` : nothing}
      ${cell.warnings.length ? html`<div class="dict-banner gold"><span>⚠</span><span>${cell.warnings.map(w => STAYS_WARN[w] || w).join(', ')}</span></div>` : nothing}
      ${offShift ? html`${fieldRow('Смена Графика', html`<select id="bb-shift-type">${kinds.map(k =>
        html`<option value=${k.id}>${k.name} ${k.start_time}–${k.end_time}</option>`)}</select>`)}
        <p class="hint">Добавится ручная смена в График (нужно право на правку Графика); Табель не меняется.</p>` : nothing}
      <div id="bb-assign-box"></div>`,
    footer: html`<button class="btn btn-ghost" data-close>Закрыть</button>
      ${assign && row.escort ? html`<button class="btn" id="bb-assign">Назначить на этот день</button>` : nothing}
      ${offShift && kinds.length ? html`<button class="btn btn-primary" id="bb-add-shift">Добавить смену в График</button>` : nothing}`,
    onMount(m) {
      $('[data-close]', m).onclick = closeModal;
      $$('[data-open-res]', m).forEach(b => { b.onclick = () => openReservationCard(Number(b.dataset.openRes), onChanged); });
      $$('[data-replace-res]', m).forEach(btn => { btn.onclick = () => openReplace(Number(btn.dataset.replaceRes), cell.day, onChanged); });
      const assignBtn = $('#bb-assign', m);
      if (assignBtn) assignBtn.onclick = async () => {
        /* брони дня, где гостей ещё никто не ведёт, — табло дня уже знает их статус */
        const day = await api('/api/stays/day?date=' + cell.day, { silent: true });
        const open = day.in_house.filter(x => x.cover_status === 'uncovered' || x.cover_status === 'replacement');
        render(open.length ? html`${fieldRow('Бронь без батлера', html`<select id="bb-res">${open.map(x =>
          html`<option value=${x.reservation_id}>${x.unit} · ${x.guests.map(g => g.name).join(', ')}</option>`)}</select>`)}
          <button class="btn btn-primary" id="bb-assign-save">Назначить ${row.name}</button>` : html`<p class="muted">Все гости дня уже с батлерами</p>`,
        $('#bb-assign-box', m));
        const save = $('#bb-assign-save', m);
        if (save) save.onclick = async () => {
          try {
            await api('/api/stays/coverage/day', { method: 'PUT', body: { day: cell.day,
              reservation_id: Number($('#bb-res', m).value), employee_id: row.employee_id } });
            closeModal(); toast('Назначено'); onChanged();
          } catch (e) { toast(e.message, 'err'); }
        };
      };
      const add = $('#bb-add-shift', m);
      if (add) add.onclick = async () => {
        try {
          await api('/api/stays/coverage/add-shift', { method: 'POST',
            body: { employee_id: row.employee_id, day: cell.day, shift_type_id: Number($('#bb-shift-type', m).value) } });
          closeModal(); toast('Смена добавлена в График'); onChanged();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* замена батлера на один день: кандидаты на смене, «знает гостя» первым (§4.5) */
async function openReplace(rid, day, onChanged) {
  const got = await api(`/api/stays/coverage/candidates?day=${day}&reservation_id=${rid}`);
  openModal({
    title: `Замена на ${dateRu(day)}`,
    body: got.length ? got.map(c => html`<div class="sb-line"><b>${c.name}</b>
      <span class="muted">${c.knows_guest ? 'знает гостя · ' : ''}нагрузка ${staysWeight(c.load_after)}${c.note ? ' · ' + c.note : ''}</span>
      <button class="btn btn-sm btn-primary" data-pick=${c.employee_id}>Назначить</button></div>`)
      : html`<p class="muted">Свободных на смене в пределах лимита нет</p>`,
    footer: html`<button class="btn btn-ghost" data-close>Закрыть</button>`,
    onMount(m) {
      $('[data-close]', m).onclick = closeModal;
      $$('[data-pick]', m).forEach(b => {
        b.onclick = async () => {
          try {
            await api('/api/stays/coverage/day', { method: 'PUT', body: { day, reservation_id: rid, employee_id: Number(b.dataset.pick) } });
            closeModal(); toast('Батлер заменён'); onChanged();
          } catch (e) { toast(e.message, 'err'); }
        };
      });
    },
  });
}

/* ─────────────── Табло дня ─────────────── */
/* «Требуют внимания» — всем уровням: OOO дня и овербукинг (на уровне «занятость» — без гостей) */
const DAY_TABS = [['arrivals', 'Заезды'], ['departures', 'Выезды'], ['in_house', 'Проживают'], ['attention', 'Требуют внимания']];

function dayStatus(r) {
  const candidates = r.candidates?.length ? html` <span class="muted">кандидаты: ${r.candidates.map(c => c.name).join(', ')}</span>` : nothing;
  switch (r.cover_status) {
    case 'covered': return html`<span class="badge ok">${r.covered.map(c => c.name + (c.guests.length ? ' — ' + c.guests.join(', ') : '')).join('; ')}</span>`;
    case 'uncovered': return html`<span class="badge danger">⚠ не назначено</span>${candidates}`;
    case 'replacement': return html`<span class="badge warn">↔ нужна подмена</span>${candidates}`;
    case 'declined': return html`<span class="badge muted">сопровождение: отказался</span>`;
    default: return html`<span class="badge muted">не требуется</span>`;
  }
}

/* почему сопровождение нужно / не нужно (§4.1): категория, узел, код, ◆, вручную */
const dayReasons = r => (r.escort_reasons?.length ? html`<div class="muted" data-db-reasons>${r.escort_reasons.join(' · ')}</div>` : nothing);

/* OOO в «Требуют внимания»: начинается и/или заканчивается в этот день */
function dayOoo(r, onClick) {
  const ev = r.events.map(e => (e === 'starts' ? 'начинается' : 'заканчивается')).join(' и ');
  return html`<div class="db-row db-ooo" data-db-ooo=${r.id} @click=${onClick}>
    <div class="db-time"><span class="badge danger">OOO</span></div><div class="db-unit"><b>${r.unit}</b></div>
    <div class="db-guests">${r.title || 'без причины'}</div>
    <div class="db-status">${ev} · ${dateRu(r.start)} ${r.start_half === 'AM' ? 'с утра' : 'с вечера'} – ${dateRu(r.end)} ${r.end_half === 'PM' ? 'до вечера' : 'до утра'}</div>
    <div class="db-det muted"></div></div>`;
}

function dayRow(r, names, rerender) {
  if (r.kind === 'ooo') return dayOoo(r, can('stays.edit') && names ? () => openOooForm(r, rerender) : nothing);
  const guests = names
    ? html`${r.guests.map((g, i) => html`${i ? ', ' : ''}${staysGuestMarkView(g.special)}${g.name}${g.role === 'main' ? staysCodeTagView(r.vip_code) : nothing}`)}${
      r.guests.filter(g => g.relatives?.length).map(g => relativesView(g.relatives.map(x => ({ ...x, title: `${g.name}: ${x.title}` }))))}`
    : `${r.guests_count} гост.`;
  const det = r.details ? [...r.details.logistics.map(l => `${l.time} ${l.description}`), ...r.details.companions.map(c => c.description),
    ...r.details.allergies.map(a => 'аллергия: ' + a)].filter(Boolean).join(' · ') : '';
  return html`<div class="db-row" data-db-row=${r.reservation_id} @click=${names ? () => openReservationCard(r.reservation_id, rerender) : nothing}>
    <div class="db-time">${r.time}</div><div class="db-unit"><b>${r.unit}</b>${r.overbooked ? html` <span class="badge danger">овербукинг</span>` : nothing}</div>
    <div class="db-guests">${guests}</div><div class="db-status">${names ? html`${dayStatus(r)}${dayReasons(r)}` : STAYS_STATUS[r.status] || r.status}</div>
    <div class="db-det muted">${det}</div></div>`;
}

export async function renderDayBoard(body) {
  const fund = await staysFund();
  if (!boardState.day) boardState.day = staysToday();
  const f = staysState.filters;
  const q = staysFundParams(new URLSearchParams({ date: boardState.day }));
  if (f.escorted) q.set('escorted_only', '1');
  staysPeopleParams(q, f);
  const fresh = loadGenerationFor(body);
  const data = await api('/api/stays/day?' + q, { silent: true });
  if (!fresh()) return;
  const names = data.visibility !== 'occupancy';
  const t = data.totals;
  const list = data[boardState.tab] || data.arrivals;
  const rerender = () => renderDayBoard(body);
  const go = d => { boardState.day = d; rerender(); };
  render(html`
    <div class="sb-toolbar">
      <button class="btn btn-sm" id="db-prev" @click=${() => go(staysAddDays(boardState.day, -1))}>◀</button>
      <input type="date" id="db-date" .value=${boardState.day} @change=${e => go(e.target.value || staysToday())}>
      <button class="btn btn-sm" id="db-next" @click=${() => go(staysAddDays(boardState.day, 1))}>▶</button>
      <button class="btn btn-sm btn-ghost" id="db-today" @click=${() => go(staysToday())}>Сегодня</button>
    </div>
    ${staysFilterView(fund, rerender, { people: names })}
    <div class="db-sum">
      <div>▲ Заезды <b>${t.arrivals}</b></div><div>▼ Выезды <b>${t.departures}</b></div><div>🏠 Проживают <b>${t.in_house}</b></div>
      ${names ? html`<div>🤵 Ведёт батлер <b>${t.covered}</b></div><div class="danger">⚠ Нужно, не назначено <b>${t.uncovered}</b></div>
        <div class="warn">↔ Нужна подмена <b>${t.need_replacement}</b></div><div>— Не требуется <b>${t.not_required}</b></div>
        <div data-db-special>◆ Особых гостей <b>${t.special}</b></div>` : nothing}
      <div>Не заехали <b>${t.no_show}</b></div>
      ${t.overbooked ? html`<div class="danger">Овербукинг <b>${t.overbooked}</b></div>` : nothing}
    </div>
    <div class="layer-tabs">${DAY_TABS.map(([id, title]) => html`<button class="btn btn-sm${boardState.tab === id ? ' btn-primary' : ''}" data-dtab=${id}
      @click=${() => { boardState.tab = id; rerender(); }}>${title}
      ${(data[id] || []).length}</button>`)}</div>
    <div class="db-list">${list.length ? list.map(r => dayRow(r, names, rerender)) : html`<div class="empty">Нет броней</div>`}</div>
    ${boardState.tab === 'arrivals' && data.no_show.length ? html`<h4>Не заехали</h4>${data.no_show.map(r =>
      html`<div class="db-row" data-db-row=${r.reservation_id} @click=${names ? () => openReservationCard(r.reservation_id, rerender) : nothing}>
        <div class="db-unit">${names ? r.number || '#' + r.reservation_id : 'бронь'}</div></div>`)}` : nothing}`, mount(body));
}

/* ─────────────── Сводная загрузка (§6.1) ─────────────── */
/* Весь месяц; строки — узлы дерева (по фильтру «Где»), сверху «Итого по выбранному».
   Свёрнутый узел — одна строка загрузки («% / штуки»), развёрнутый — восемь строк §6.1.
   Клик по названию — свернуть / развернуть; по клетке «Проживают» — шахматка узла с этого дня. */
const OC_ROWS = [['total', 'Всего объектов'], ['living', 'Проживают'], ['guests', 'Гостей'], ['arrivals', '▲ Заезды'],
  ['departures', '▼ Выезды'], ['free', 'Свободно'], ['ooo', 'OOO'], ['blocks', 'Блоки']];
/* «OOO» и «Блоки» — по половинкам: ночь занята, если занята половинка PM дня (часть 2 §6); «Свободно»
   без нижней границы 0 — отрицательное значение это овербукинг */

const ocHeat = pct => (pct == null ? '' : pct >= 1 ? 'heat3' : pct >= 0.8 ? 'heat2' : pct >= 0.5 ? 'heat1' : '');
const ocIsOpen = key => staysState.ocOpen[key] ?? key === 'total';

export async function renderOccupancyGrid(body) {
  const fund = await staysFund();
  const { first, last } = staysMonthRange();
  const q = staysFundParams(new URLSearchParams({ first, last }));
  if (staysState.filters.escorted) q.set('escorted', '1');
  const fresh = loadGenerationFor(body);
  const data = await api('/api/stays/occupancy?' + q, { silent: true });
  if (!fresh()) return;
  const rerender = () => renderOccupancyGrid(body);
  const draw = () => render(html`
    <div class="sb-toolbar">
      ${staysMonthNavView(body, rerender)}
      <span class="oc-modes">${[['pct', '%'], ['count', 'штуки']].map(([m, t]) =>
        html`<button class="btn btn-sm${staysState.ocMode === m ? ' btn-primary' : ''}" data-oc-mode=${m}
          @click=${() => { staysState.ocMode = m; draw(); }}>${t}</button>`)}</span>
      <span class="muted">цвет: от 50 % · от 80 % · 100 % и больше</span>
    </div>
    <!-- поиск и VIP к загрузке не применяются: в ней нет данных гостей (§6.1) -->
    ${staysFilterView(fund, rerender, { people: false })}
    <div class="sb-grid bb-grid oc-grid" style=${`--days:${data.days.length}`} @click=${gridClick}>${ocGrid(data)}</div>`, mount(body));
  const gridClick = e => {
    const tog = e.target.closest('[data-oc-toggle]');
    if (tog) {
      const key = tog.dataset.ocToggle;
      staysState.ocOpen[key] = !ocIsOpen(key);
      draw();
      return;
    }
    const cell = e.target.closest('[data-oc-living]');
    if (cell) staysOpenNodeDay(cell.dataset.ocNode, cell.dataset.day);
  };
  draw();
  staysFocusDay(body);
}

function ocGrid(data) {
  const today = staysToday();
  const count = staysState.ocMode === 'count';
  const nodeView = (n, key) => {
    const name = n.path[n.path.length - 1] || '';
    const sub = n.path.slice(0, -1).join(' / ');
    const isOpen = ocIsOpen(key);
    const label = extra => html`<div class="sb-unit"><button class="oc-name" data-oc-toggle=${key} title="Свернуть / развернуть">
      ${isOpen ? '▾' : '▸'} ${name}</button>${sub ? html`<small>${sub}</small>` : nothing}${extra ? html`<small>${extra}</small>` : nothing}</div>`;
    /* «Проживают» узла ведёт в шахматку объектов; «Без группы» фильтром «Где» не выбрать */
    const node = key === 'total' ? '' : n.group_id == null ? null : String(n.group_id);
    if (!isOpen) {
      return html`<div class="oc-node" data-oc-group=${key}><div class="bb-row oc-line">${label('загрузка')}
        ${n.days.map(x => html`<div class="oc-cell ${ocHeat(x.pct)}" title="занято (проживают + блоки) / доступно (всего − OOO)">${count
          ? `${x.living + x.blocks}/${x.total - x.ooo}` : (x.pct == null ? '—' : Math.round(x.pct * 100) + '%')}</div>`)}</div></div>`;
    }
    return html`<div class="oc-node" data-oc-group=${key}>${OC_ROWS.map(([field, title], i) => html`<div class="bb-row oc-line">
      ${i === 0 ? label(title) : html`<div class="sb-unit oc-sub">${title}</div>`}
      ${n.days.map((x, d) => (field === 'living'
        ? html`<div class="oc-cell ${ocHeat(x.pct)}" data-oc-living=${node != null ? '' : nothing} data-oc-node=${node != null ? node : nothing}
            data-day=${node != null ? data.days[d] : nothing}
            title=${x.pct == null ? 'загрузка —' : 'загрузка ' + Math.round(x.pct * 100) + '%'}>${x.living}</div>`
        : field === 'free' && x.free < 0
          ? html`<div class="oc-cell oc-neg" title="овербукинг: броней и блоков больше, чем свободных объектов">${x.free}</div>`
          : html`<div class="oc-cell">${x[field]}</div>`))}</div>`)}</div>`;
  };
  return html`<div class="bb-row sb-head oc-head"><div class="sb-unit">Узел</div>${data.days.map(d => staysDayHeadView(d, today))}</div>
    ${data.nodes.length ? html`${nodeView(data.total, 'total')}${data.nodes.map(n => nodeView(n, n.group_id == null ? 'none' : String(n.group_id)))}`
      : html`<div class="empty">Фонд пуст</div>`}`;
}

/* клик по «Проживают» (§6.1): шахматка объектов узла, раздел узла развёрнут, докрутка к дню */
function staysOpenNodeDay(node, day) {
  if (node) {
    const gid = Number(node);
    staysState.filters = { ...staysState.filters, group_ids: [gid] };
    (staysState.fund?.groups || []).forEach(g => {
      if (g.path.includes(gid) || (staysState.fund.groups.find(x => x.id === gid)?.path || []).includes(g.id)) {
        staysState.collapsed[String(g.id)] = false;
      }
    });
    staysState.collapsed[node] = false;
  }
  staysState.focusDay = day;
  staysState.tab = 'units';
  loadStays();
}
