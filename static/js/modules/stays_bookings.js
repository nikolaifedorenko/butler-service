/* ══════════════════════════════════════════════════════════════════════
   «ШАХМАТКА» — вкладка «Брони»: плоский список бронирований за период
   (спецификация docs/superpowers/specs/2026-10-26-stays-fund-versions-design.md §8).
   Фильтры, сортировка и срез страницы — на сервере (GET /api/stays/bookings); клиент держит
   накопленные страницы («Показать ещё» — +200). Период — общий месяц разделов или свой диапазон
   (не больше 366 дней: поля дат это ограничивают, сообщение сервера 422 показывается тостом).
   Модуль на lit-html (ADR-0013, раздел 7): разметка — шаблоны, вставки экранируются сами.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

import { can } from '../app.js';
import { api, dateRu, downloadBlob, loadGenerationFor, toast } from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import {
  staysCodeTagView, staysFilterView, staysGuestMarkView, staysMonthNavView, openReservationCard, staysAddDays, staysColor, staysFund, staysFundParams,
  staysMonthRange, staysPeopleParams, staysState,
} from './stays.js';
import { staysFilterOpen } from './stays_filters.js';

const STAYS_BOOK_MODES = [['stay', 'проживает в период'], ['check_in', 'заезд в период'],
  ['check_out', 'выезд в период'], ['created', 'создана в период']];
const STAYS_BOOK_STATUSES = [['tentative', 'предварительная'], ['confirmed', 'подтверждена'], ['in_house', 'заселён'],
  ['checked_out', 'выехал'], ['cancelled', 'отменена'], ['no_show', 'не заехал']];
/* колонки: ключ сортировки сервера — заголовок */
const STAYS_BOOK_COLS = [['number', '№ брони'], ['guest', 'Гость'], ['check_in', 'Заезд'], ['check_out', 'Выезд'],
  ['nights', 'Ночей'], ['category', 'Категория'], ['unit', 'Объект'], ['status', 'Статус'], ['created_at', 'Создана']];
const STAYS_BOOK_MAX_DAYS = 366;
const STAYS_BOOK_PAGE = 200;

export function staysBookEmpty() {
  return { custom: false, first: '', last: '', mode: 'stay', statuses: [], label_ids: [],
    unassigned: false, with_warnings: false, sort: 'check_in', dir: 'asc' };
}
export const staysBook = staysBookEmpty();

/* период запроса: свой диапазон или общий месяц */
function staysBookRange() {
  return staysBook.custom && staysBook.first && staysBook.last
    ? { first: staysBook.first, last: staysBook.last } : staysMonthRange();
}
function staysBookParams() {
  const f = staysState.filters;
  const { first, last } = staysBookRange();
  const p = staysFundParams(new URLSearchParams({ first, last, mode: staysBook.mode,
    sort: staysBook.sort, dir: staysBook.dir }));
  staysBook.statuses.forEach(v => p.append('statuses', v));
  staysBook.label_ids.forEach(v => p.append('label_ids', v));
  if (staysBook.unassigned) p.set('unassigned', '1');
  if (staysBook.with_warnings) p.set('with_warnings', '1');
  if (f.escorted) p.set('escorted', '1');
  staysPeopleParams(p, f);
  return p;
}

/* выпадающий список флажков: имя data-атрибута у каждого списка своё */
const CHECKBOX = {
  status: (v, on) => html`<input type="checkbox" data-bk-status=${v} .checked=${on}>`,
  label: (v, on) => html`<input type="checkbox" data-bk-label=${v} .checked=${on}>`,
};

export async function renderBookings(body) {
  const fund = await staysFund();
  const fresh = loadGenerationFor(body);
  const b = staysBook;
  let rows = [];
  let total = 0;
  let error = '';
  let loadingMore = false;
  const page = async offset => {
    const p = staysBookParams();
    p.set('offset', offset);
    p.set('limit', STAYS_BOOK_PAGE);
    return api('/api/stays/bookings?' + p, { silent: true });
  };
  try {
    ({ rows, total } = await page(0));
  } catch (e) {
    error = e.message;
    toast(error, 'warn');
  }
  if (!fresh()) return;
  const rerender = () => renderBookings(body);
  const draw = () => render(screen(), mount(body));

  const pick = (key, title, items, chosen, field, cast) => {
    const picked = items.filter(([v]) => chosen.includes(v)).map(([, t]) => t);
    return html`<details class="sf-dd" data-bk-dd=${key} ?open=${staysFilterOpen.has('bk-' + key)}
      @toggle=${e => { if (e.target.open) staysFilterOpen.add('bk-' + key); else staysFilterOpen.delete('bk-' + key); }}>
      <summary>${title}: <b>${picked.length ? picked.join(', ') : 'все'}</b></summary>
      <div class="sf-list" @change=${e => {
        b[field] = [...e.currentTarget.querySelectorAll('input[type=checkbox]')].filter(x => x.checked)
          .map(x => cast(x.getAttribute(`data-bk-${key}`)));
        rerender();
      }}>${items.length ? items.map(([v, t]) => html`<label class="chk">${CHECKBOX[key](String(v), chosen.includes(v))} ${t}</label>`)
        : html`<span class="muted">нет</span>`}</div></details>`;
  };

  const toolbar = () => {
    const { first, last } = staysBookRange();
    return html`<div class="sb-toolbar">
      <select id="bk-period" title="Период списка" @change=${e => {
        b.custom = e.target.value === 'custom';
        if (b.custom && !(b.first && b.last)) ({ first: b.first, last: b.last } = staysMonthRange());
        rerender();
      }}><option value="month" ?selected=${!b.custom}>Месяц разделов</option>
        <option value="custom" ?selected=${b.custom}>Свой период</option></select>
      ${b.custom
        ? html`<input type="date" id="bk-first" .value=${first} max=${last} title="Начало периода" @change=${e => {
            if (!e.target.value) return;
            b.first = e.target.value;
            const cap = staysAddDays(b.first, STAYS_BOOK_MAX_DAYS - 1);
            if (b.last < b.first) b.last = b.first;
            if (b.last > cap) b.last = cap;
            rerender();
          }}>
          <input type="date" id="bk-last" .value=${last} min=${first} max=${staysAddDays(first, STAYS_BOOK_MAX_DAYS - 1)}
            title=${`Конец периода (не позже ${STAYS_BOOK_MAX_DAYS} дней от начала)`} @change=${e => {
            if (!e.target.value) return;
            b.last = e.target.value;
            if (b.last < b.first) { toast('Конец периода раньше начала', 'warn'); b.last = b.first; }
            rerender();
          }}>
          <span class="muted">не больше ${STAYS_BOOK_MAX_DAYS} дней</span>`
        : staysMonthNavView(body, rerender)}
      <select id="bk-mode" title="Какие брони попадают в период" @change=${e => { b.mode = e.target.value; rerender(); }}>${STAYS_BOOK_MODES.map(([v, t]) =>
        html`<option value=${v} ?selected=${v === b.mode}>${t}</option>`)}</select>
      ${pick('status', 'Статусы', STAYS_BOOK_STATUSES, b.statuses, 'statuses', String)}
      ${pick('label', 'Метки', (fund.labels || []).map(l => [l.id, l.title]), b.label_ids, 'label_ids', Number)}
      <label class="chk"><input type="checkbox" id="bk-unassigned" .checked=${b.unassigned}
        @change=${e => { b.unassigned = e.target.checked; rerender(); }}> без объекта</label>
      <label class="chk"><input type="checkbox" id="bk-warn" .checked=${b.with_warnings}
        @change=${e => { b.with_warnings = e.target.checked; rerender(); }}> с предупреждениями</label>
      ${can('stays.export') ? html`<button class="btn btn-sm btn-ghost" id="bk-xlsx" title="Выгрузить список по текущим фильтрам" @click=${() => {
        downloadBlob('/api/stays/bookings/export?' + staysBookParams(), `bookings_${first}_${last}.xlsx`)
          .catch(err => toast(err.message, 'warn'));
      }}>Выгрузить</button>` : nothing}
    </div>`;
  };

  const rowView = r => html`<tr class="bk-row" data-bk-row=${r.id} tabindex="0"
      @click=${() => openReservationCard(r.id, rerender).catch(err => toast(err.message, 'warn'))}
      @keydown=${e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.currentTarget.click(); } }}>
    <td>${r.label ? html`<span class="sb-star" style=${`color:${staysColor(r.label.color)}`} title=${r.label.title}>●</span> ` : nothing}${r.number || '#' + r.id}</td>
    <td>${staysGuestMarkView(r.special)}${r.main_guest}${staysCodeTagView(r.vip_code)}</td>
    <td>${dateRu(r.check_in)}${r.early ? html` <span class="muted" title="Ранний заезд">РЗ</span>` : nothing}</td>
    <td>${dateRu(r.check_out)}${r.late ? html` <span class="muted" title="Поздний выезд">ПВ</span>` : nothing}</td>
    <td>${r.nights}</td><td>${r.category}${r.upgrade ? html` <span class="badge muted" title=${r.upgrade}>${r.upgrade}</span>` : nothing}</td><td>${r.unit || '—'}</td>
    <td>${r.status_title}</td><td>${r.created_at.slice(0, 16).replace('T', ' ')}</td></tr>`;

  const sortBy = key => {
    /* сортировка: клик — по возрастанию, повторный — направление */
    if (b.sort === key) b.dir = b.dir === 'asc' ? 'desc' : 'asc'; else { b.sort = key; b.dir = 'asc'; }
    rerender();
  };
  const loadMore = async () => {
    loadingMore = true; draw();
    try {
      const next = await page(rows.length);
      if (!fresh()) return;
      rows = rows.concat(next.rows);
      total = next.total;
    } catch (e) { toast(e.message, 'warn'); }
    loadingMore = false;
    draw();
  };
  const arrow = key => (b.sort === key ? (b.dir === 'asc' ? ' ↑' : ' ↓') : '');
  const result = () => (error
    ? html`<div class="panel"><p class="muted">${error}</p></div>`
    : html`<div class="muted" id="bk-total">Найдено броней: ${total}${rows.length < total ? ` · показано ${rows.length}` : ''}</div>
      <div class="sb-scroll"><table class="bk-table"><thead><tr>${STAYS_BOOK_COLS.map(([k, t]) =>
        html`<th data-bk-sort=${k} title="Сортировать" style="cursor:pointer" @click=${() => sortBy(k)}>${t}${arrow(k)}</th>`)}</tr></thead>
      <tbody>${rows.length ? rows.map(rowView) : html`<tr><td colspan=${STAYS_BOOK_COLS.length} class="empty">Броней по фильтру нет</td></tr>`}</tbody></table></div>
      ${rows.length < total ? html`<button class="btn" id="bk-more" ?disabled=${loadingMore} @click=${loadMore}>Показать ещё ${Math.min(STAYS_BOOK_PAGE, total - rows.length)}</button>` : nothing}`);
  const screen = () => html`${toolbar()}${staysFilterView(fund, rerender, { people: true })}<div id="bk-result">${result()}</div>`;
  draw();
}
