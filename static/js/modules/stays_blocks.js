/* ══════════════════════════════════════════════════════════════════════
   «ШАХМАТКА» — вкладка «Блоки» и карточка блока с сеткой «категория × ночь»
   (спецификация docs/superpowers/specs/2026-10-27-stays-ooo-blocks-design.md §3.2, §6, §7).
   Список — как «Брони»: фильтры, сортировка и срез страницы на сервере (GET /api/stays/blocks).
   Карточка: строки сетки — категории, столбцы — ночи блока (прокрутка внутри карточки), в клетке
   остаток; клетки выделяются (клик + shift-клик или протяжка) и получают число; помощник
   «заполнить»; «разложено / нехватка» по клеткам — из ответа сервера. Правки копятся в карточке,
   «Проверить» показывает, кто останется без объекта и где блоку не хватит, «Сохранить» отправляет
   сетку целиком. Видят все уровни доступа, пишет только stays.edit.
   Здесь же — общие для списков блоков и OOO помощники периода, выбора из списка и поиска.
   Модуль на lit-html (ADR-0013, раздел 7): списки и сетка — шаблоны.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

import { can } from '../app.js';
import { $, $$, api, closeModal, dateRu, loadGenerationFor, MONTHS, openModal, toast, WD_SHORT } from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { fieldRow } from '../ui/form.js';
import { formFootView, renderPreview, staysBindGatedFoot } from './stays_forms.js';
import { staysFilterOpen } from './stays_filters.js';
import { staysAddDays, staysFund, staysMonthNavView, staysMonthRange, staysToday } from './stays.js';

/* колонки: ключ сортировки сервера (null — без сортировки) — заголовок */
const STAYS_BLOCK_COLS = [['title', 'Название'], ['start', 'С'], ['end', 'По'], ['nights', 'Ночей'],
  [null, 'Остаток по категориям'], ['placed', 'Разложено'], ['short', 'Нехватка']];
const STAYS_BLOCK_PAGE = 200;
const STAYS_BLOCK_MAX_NIGHTS = 366;       // как MAX_NIGHTS сервера: поля дат это ограничивают

export function staysBlockEmpty() {
  return { mode: 'month', first: '', last: '', category_ids: [], short_only: false, q: '', sort: 'start', dir: 'asc' };
}
export const staysBlock = staysBlockEmpty();

/* ─────────────── Общие помощники списков блоков и OOO ─────────────── */
/* период: месяц разделов, свой диапазон или все даты; null — без ограничения */
export function staysPeriodRange(st) {
  if (st.mode === 'all') return null;
  return st.mode === 'custom' && st.first && st.last ? { first: st.first, last: st.last } : staysMonthRange();
}
export function staysPeriodBarView(st, body, rerender) {
  const range = staysPeriodRange(st) || staysMonthRange();
  return html`<select id="pd-mode" title="Период списка (пересечение с периодом)" @change=${e => {
      st.mode = e.target.value;
      if (st.mode === 'custom' && !(st.first && st.last)) ({ first: st.first, last: st.last } = staysMonthRange());
      rerender();
    }}>
      <option value="month" ?selected=${st.mode === 'month'}>Месяц разделов</option>
      <option value="custom" ?selected=${st.mode === 'custom'}>Свой период</option>
      <option value="all" ?selected=${st.mode === 'all'}>Все даты</option></select>
    ${st.mode === 'custom'
    ? html`<input type="date" id="pd-first" .value=${range.first} max=${range.last} title="Начало периода" @change=${e => {
        if (!e.target.value) return;
        st.first = e.target.value;
        if (st.last < st.first) st.last = st.first;
        rerender();
      }}>
      <input type="date" id="pd-last" .value=${range.last} min=${range.first} title="Конец периода" @change=${e => {
        if (!e.target.value) return;
        st.last = e.target.value;
        if (st.last < st.first) { toast('Конец периода раньше начала', 'warn'); st.last = st.first; }
        rerender();
      }}>`
    : st.mode === 'month' ? staysMonthNavView(body, rerender) : nothing}`;
}
/* поиск: запрос уходит после паузы; поле не пересоздаётся, поэтому фокус и курсор переживают перерисовку
   (value — атрибут, а не свойство: набранный текст перерисовка не затирает) */
export function staysSearchView(id, placeholder, st, rerender) {
  let timer = null;
  return html`<input type="search" id=${id} placeholder=${placeholder} value=${st.q} @input=${e => {
    clearTimeout(timer);
    const value = e.target.value;
    timer = setTimeout(() => { st.q = value; rerender(); }, 350);
  }}>`;
}
/* выпадающий список флажков категорий (как «Статусы» во вкладке «Брони»); раскрытие — staysFilterOpen */
function categoryPickView(items, chosen, onChange) {
  const picked = items.filter(([v]) => chosen.includes(v)).map(([, t]) => t);
  return html`<details class="sf-dd" data-pk-dd="cat" ?open=${staysFilterOpen.has('pk-cat')}
    @toggle=${e => { if (e.target.open) staysFilterOpen.add('pk-cat'); else staysFilterOpen.delete('pk-cat'); }}>
    <summary>Категории: <b>${picked.length ? picked.join(', ') : 'все'}</b></summary>
    <div class="sf-list" @change=${e => onChange([...e.currentTarget.querySelectorAll('input[type=checkbox]')]
      .filter(x => x.checked).map(x => Number(x.getAttribute('data-pk-cat'))))}>${items.length ? items.map(([v, t]) => html`<label class="chk">
      <input type="checkbox" data-pk-cat=${String(v)} .checked=${chosen.includes(v)}> ${t}</label>`)
      : html`<span class="muted">нет</span>`}</div></details>`;
}

/* ─────────────── Вкладка «Блоки» ─────────────── */
function staysBlockParams() {
  const b = staysBlock;
  const p = new URLSearchParams({ sort: b.sort, dir: b.dir });
  const range = staysPeriodRange(b);
  if (range) { p.set('first', range.first); p.set('last', range.last); }
  b.category_ids.forEach(v => p.append('category_ids', v));
  if (b.short_only) p.set('short_only', '1');
  if (b.q.trim()) p.set('q', b.q.trim());
  return p;
}

const staysBlockRow = (r, open) => html`<tr class="bk-row" data-bl-row=${r.id} tabindex="0" @click=${open}
    @keydown=${e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.currentTarget.click(); } }}>
    <td>${r.title}</td><td>${dateRu(r.start)}</td><td>${dateRu(r.end)}</td><td>${r.nights}</td>
    <td>${r.top.map(t => `${t.code} до ${t.max}`).join(', ') || '—'}</td><td>${r.placed}</td>
    <td>${r.short ? html`<span class="sp-warn" title="Нехватка: клеток «категория × ночь» без объекта">нехватка ${r.missing}</span>` : '—'}</td></tr>`;

export async function renderBlocksTab(body) {
  const fund = await staysFund();
  const fresh = loadGenerationFor(body);
  const b = staysBlock;
  let rows = [];
  let total = 0;
  let error = '';
  let loadingMore = false;
  const page = offset => {
    const p = staysBlockParams();
    p.set('offset', offset);
    p.set('limit', STAYS_BLOCK_PAGE);
    return api('/api/stays/blocks?' + p, { silent: true });
  };
  try {
    ({ rows, total } = await page(0));
  } catch (e) {
    error = e.message;
    toast(error, 'warn');
  }
  if (!fresh()) return;
  const rerender = () => renderBlocksTab(body);
  const draw = () => render(screen(), mount(body));
  const sortBy = key => {
    if (b.sort === key) b.dir = b.dir === 'asc' ? 'desc' : 'asc'; else { b.sort = key; b.dir = 'asc'; }
    rerender();
  };
  const more = async () => {
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
  const result = () => (error ? html`<div class="panel"><p class="muted">${error}</p></div>`
    : html`<div class="muted" id="bl-total">Найдено блоков: ${total}${rows.length < total ? ` · показано ${rows.length}` : ''}</div>
      <div class="sb-scroll"><table class="bk-table"><thead><tr>${STAYS_BLOCK_COLS.map(([k, t]) => (k
        ? html`<th data-bl-sort=${k} title="Сортировать" style="cursor:pointer" @click=${() => sortBy(k)}>${t}${arrow(k)}</th>` : html`<th>${t}</th>`))}</tr></thead>
      <tbody>${rows.length ? rows.map(r => staysBlockRow(r, () => openBlockCard(r.id, rerender).catch(err => toast(err.message, 'warn'))))
        : html`<tr><td colspan=${STAYS_BLOCK_COLS.length} class="empty">Блоков по фильтру нет</td></tr>`}</tbody></table></div>
      ${rows.length < total ? html`<button class="btn" id="bl-more" ?disabled=${loadingMore} @click=${more}>Показать ещё ${Math.min(STAYS_BLOCK_PAGE, total - rows.length)}</button>` : nothing}`);
  const screen = () => html`<div class="sb-toolbar">${staysPeriodBarView(b, body, rerender)}
    ${categoryPickView(fund.categories.map(c => [c.id, c.code]), b.category_ids, v => { b.category_ids = v; rerender(); })}
    <label class="chk"><input type="checkbox" id="bl-short" .checked=${b.short_only}
      @change=${e => { b.short_only = e.target.checked; rerender(); }}> с нехваткой</label>
    ${staysSearchView('bl-q', 'название блока', b, rerender)}
    ${can('stays.edit') ? html`<button class="btn btn-sm btn-primary" id="bl-new"
      @click=${() => openBlockCard(null, rerender).catch(err => toast(err.message, 'warn'))}>+ Блок</button>` : nothing}</div>
    <div id="bl-result">${result()}</div>`;
  draw();
}

/* ─────────────── Карточка блока ─────────────── */
/* ночи блока [start, end): не больше STAYS_BLOCK_MAX_NIGHTS; пустой список при неверных датах */
function staysBlockNights(start, end) {
  const out = [];
  if (!start || !end) return out;
  for (let d = start; d < end && out.length < STAYS_BLOCK_MAX_NIGHTS; d = staysAddDays(d, 1)) out.push(d);
  return out;
}
const staysGridCopy = g => Object.fromEntries(Object.entries(g || {}).map(([c, by]) => [c, { ...by }]));

/* клетка сетки: остаток; если блок сохранён и клетка не менялась — «разложено / нехватка» сервера;
   r и i — индексы клетки для выделения */
function staysBlockCell(c, n, qty, missing, dirty, r, i) {
  const short = missing > 0 && !dirty;
  const title = short ? `разложено ${qty - missing} из ${qty}, не хватает ${missing}` : qty ? `остаток ${qty}` : '';
  return html`<td class=${`bg-cell${short ? ' short' : ''}${dirty ? ' dirty' : ''}`} data-bg-c=${c} data-bg-n=${n} data-r=${r} data-i=${i}
    title=${title}>${qty ? html`${qty}${short ? html`<small>−${missing}</small>` : nothing}` : nothing}</td>`;
}

/* шапка: месяцы с colspan, под ними числа и дни недели */
function staysBlockHead(nights) {
  const months = [];
  nights.forEach(n => {
    const key = n.slice(0, 7);
    if (months.length && months[months.length - 1].key === key) months[months.length - 1].span++;
    else months.push({ key, span: 1, title: `${MONTHS[Number(n.slice(5, 7)) - 1]} ${n.slice(0, 4)}` });
  });
  return html`<tr><th class="bg-cat" rowspan="2">Категория</th>${months.map(m =>
    html`<th class="bg-month" colspan=${m.span}>${m.title}</th>`)}</tr>
    <tr>${nights.map(n => {
    const wd = new Date(n + 'T12:00:00Z').getUTCDay();
    return html`<th class=${`bg-day${wd === 0 || wd === 6 ? ' we' : ''}`} data-bg-h=${n}>${Number(n.slice(8))}<small>${WD_SHORT[(wd + 6) % 7]}</small></th>`;
  })}</tr>`;
}

export async function openBlockCard(id, onChanged) {
  const [fund, card] = await Promise.all([staysFund(), id ? api('/api/stays/blocks/' + id) : Promise.resolve(null)]);
  const edit = can('stays.edit');
  const st = { id: card ? card.id : null, version: card?.version, title: card?.title || '',
    start: card?.start || staysToday(), end: card?.end || staysAddDays(staysToday(), 3),
    grid: staysGridCopy(card?.grid), saved: staysGridCopy(card?.grid), short: card?.short || [],
    placed: card?.placed ?? 0, missing: card?.missing ?? 0,
    sel: null, anchor: null };
  /* строки: категории фонда + категории, оставшиеся в сетке (их уже нет в сегодняшнем фонде) */
  const rowsOf = () => {
    const rows = fund.categories.map(c => ({ id: String(c.id), code: c.code }));
    Object.keys(st.grid).forEach(cid => { if (!rows.some(r => r.id === cid)) rows.push({ id: cid, code: '#' + cid }); });
    return rows;
  };
  const codeOf = cid => rowsOf().find(r => r.id === String(cid))?.code || '#' + cid;
  /* нехватка сохранённого блока по клеткам: категория → ночь → не хватает */
  const missingMap = () => {
    const out = {};
    st.short.forEach(s => {
      for (let d = s.first; d <= s.last; d = staysAddDays(d, 1)) (out[s.category_id] ||= {})[d] = s.missing;
    });
    return out;
  };
  const title = () => (st.id ? `Блок · ${st.title}` : 'Новый блок');
  const gridView = () => {
    const nights = staysBlockNights(st.start, st.end);
    const rows = rowsOf();
    const miss = missingMap();
    const sums = nights.map(n => rows.reduce((a, r) => a + (st.grid[r.id]?.[n] || 0), 0));
    return html`<table class="bg-table" aria-label="Остатки блока по категориям и ночам">
      <thead>${staysBlockHead(nights)}</thead>
      <tbody>${rows.map((r, ri) => html`<tr><th class="bg-cat" scope="row">${r.code}</th>${nights.map((n, ni) => {
    const q = st.grid[r.id]?.[n] || 0;
    const dirty = q !== (st.saved[r.id]?.[n] || 0);
    return staysBlockCell(r.id, n, q, miss[r.id]?.[n] || 0, dirty, ri, ni);
  })}</tr>`)}
      <tr class="bg-sum"><th class="bg-cat" scope="row">Всего</th>${sums.map(s => html`<td>${s || ''}</td>`)}</tr></tbody></table>`;
  };
  const summaryView = () => {
    if (!st.id) return html`<span class="muted">Сохраните блок — сервер покажет, сколько разложено по объектам и где не хватает</span>`;
    return html`Разложено по объектам: <b>${st.placed}</b>${st.missing ? html` · <span class="sp-warn">нехватка: <b>${st.missing}</b></span>` : nothing}
      ${st.short.map(x => html`<div class="sp-warn" data-block-short>⚠ ${codeOf(x.category_id)}: не хватает ${x.missing} с ${dateRu(x.first)} по ${dateRu(x.last)}</div>`)}`;
  };
  const controls = () => html`
    <div class="bg-tools">
      <div class="bg-tool"><b>Выделение</b> <span id="bg-sel-info" class="muted">клик по клетке, shift-клик или протяжка — диапазон</span>
        <input type="number" id="bg-qty" min="0" max="500" .value=${'1'} title="Остаток для выделенных клеток">
        <button class="btn btn-sm" id="bg-set">Задать число</button>
        <button class="btn btn-sm btn-ghost" id="bg-clear" title="Убрать остаток у выделенных клеток">Очистить</button></div>
      <div class="bg-tool"><b>Заполнить</b>
        <select id="bg-fill-cat" title="Категория">${rowsOf().map(r => html`<option value=${r.id}>${r.code}</option>`)}</select>
        <input type="date" id="bg-fill-from" title="Первая ночь"><input type="date" id="bg-fill-to" title="Последняя ночь">
        <input type="number" id="bg-fill-qty" min="0" max="500" .value=${'1'} title="Остаток">
        <button class="btn btn-sm" id="bg-fill">Заполнить</button></div></div>`;
  const dateInput = (id, value) => html`<input id=${id} type="date" .value=${value} ?disabled=${!edit}>`;

  openModal({
    title: title(), wide: true,
    subtitle: edit ? 'Остаток по категориям на каждую ночь: блок держит объекты категории под группу. «Проверить» покажет, кто останется без объекта'
      : 'Остаток по категориям на каждую ночь',
    body: html`<div class="grid-2">
        ${fieldRow('Название', html`<input id="bg-title" type="text" maxlength="120" .value=${st.title} ?disabled=${!edit}>`)}
        <div class="grid-2">${fieldRow('С', dateInput('bg-start', st.start))}
          ${fieldRow('По (выезд)', dateInput('bg-end', st.end))}</div>
      </div>
      <div id="bg-summary" class="bg-summary"></div>
      ${edit ? controls() : nothing}
      <div class="bg-wrap" id="bg-wrap"></div>
      <div id="bg-note" class="muted"></div>
      <div id="rf-preview-out" class="sp-out"></div>`,
    footer: html`${edit && st.id ? html`<button class="btn btn-danger" id="bg-delete">Удалить…</button>` : nothing}
      ${edit ? formFootView() : html`<button class="btn btn-ghost" data-close>Закрыть</button>`}`,
    onMount(m) {
      m.classList.add('v4-xl');
      const wrap = $('#bg-wrap', m);
      const out = () => $('#rf-preview-out', m);
      let cells = [];
      let dragging = false;

      /* выделение — прямоугольник строк × ночей; индексы клетки лежат в data-r / data-i */
      const paintSel = () => {
        const s = st.sel;
        cells.forEach(td => {
          const r = Number(td.dataset.r), i = Number(td.dataset.i);
          td.classList.toggle('sel', !!s && r >= s.r0 && r <= s.r1 && i >= s.i0 && i <= s.i1);
        });
        const info = $('#bg-sel-info', m);
        if (info) {
          if (!s) { info.textContent = 'клик по клетке, shift-клик или протяжка — диапазон'; return; }
          const rows = rowsOf(), nights = staysBlockNights(st.start, st.end);
          info.textContent = `${rows[s.r0].code}${s.r1 > s.r0 ? '–' + rows[s.r1].code : ''} · ${dateRu(nights[s.i0])}${s.i1 > s.i0 ? '–' + dateRu(nights[s.i1]) : ''}`
            + ` · клеток: ${(s.r1 - s.r0 + 1) * (s.i1 - s.i0 + 1)}`;
        }
      };
      const paintGrid = () => {
        render(gridView(), wrap);
        cells = $$('.bg-table td[data-bg-c]', wrap);
        const outside = Object.values(st.grid).reduce((a, by) => a + Object.keys(by).filter(n => !(n >= st.start && n < st.end)).length, 0);
        $('#bg-note', m).textContent = outside ? `Ночей вне дат блока: ${outside} — при сохранении они удалятся` : '';
        render(summaryView(), $('#bg-summary', m));
        $('.modal-head h3', m).textContent = title();
        paintSel();
      };
      const rectTo = td => {
        const r = Number(td.dataset.r), i = Number(td.dataset.i);
        const a = st.anchor || { r, i };
        st.sel = { r0: Math.min(a.r, r), r1: Math.max(a.r, r), i0: Math.min(a.i, i), i1: Math.max(a.i, i) };
      };
      const touch = () => foot.reset();      // правка полей и сетки снимает запрет «не сохранится»
      /* число в выделенные клетки: 0 убирает остаток */
      const setCells = (cids, nights, qty) => {
        cids.forEach(cid => {
          nights.forEach(n => {
            if (qty > 0) (st.grid[cid] ||= {})[n] = qty;
            else if (st.grid[cid]) delete st.grid[cid][n];
          });
        });
        touch();
        paintGrid();
      };
      const readQty = id => {
        const q = Number($(id, m).value);
        if (!Number.isInteger(q) || q < 0 || q > 500) { toast('Остаток — целое число от 0 до 500', 'warn'); return null; }
        return q;
      };

      wrap.addEventListener('click', e => {
        const td = e.target.closest('td[data-bg-c]');
        if (!td) return;
        if (!e.shiftKey || !st.anchor) st.anchor = { r: Number(td.dataset.r), i: Number(td.dataset.i) };
        rectTo(td);
        paintSel();
      });
      wrap.addEventListener('mousedown', e => {
        const td = e.target.closest('td[data-bg-c]');
        if (!td || e.button !== 0) return;
        if (!e.shiftKey || !st.anchor) st.anchor = { r: Number(td.dataset.r), i: Number(td.dataset.i) };
        dragging = true;
        rectTo(td);
        paintSel();
      });
      wrap.addEventListener('mouseover', e => {
        const td = dragging && (e.buttons & 1) && e.target.closest('td[data-bg-c]');
        if (td) { rectTo(td); paintSel(); }
      });
      m.addEventListener('mouseup', () => { dragging = false; });

      const title$ = $('#bg-title', m);
      title$.oninput = () => { st.title = title$.value; };
      const dates = () => {
        st.start = $('#bg-start', m).value || st.start;
        st.end = $('#bg-end', m).value || st.end;
        st.sel = null; st.anchor = null;
        touch();
        paintGrid();
      };
      $('#bg-start', m).onchange = dates;
      $('#bg-end', m).onchange = dates;

      if (edit) {
        const syncFill = () => {
          const nights = staysBlockNights(st.start, st.end);
          $('#bg-fill-from', m).value = nights[0] || '';
          $('#bg-fill-to', m).value = nights[nights.length - 1] || '';
        };
        syncFill();
        $('#bg-start', m).addEventListener('change', syncFill);
        $('#bg-end', m).addEventListener('change', syncFill);
        $('#bg-set', m).onclick = () => {
          if (!st.sel) { toast('Выделите клетки сетки', 'warn'); return; }
          const q = readQty('#bg-qty');
          if (q === null) return;
          const rows = rowsOf(), nights = staysBlockNights(st.start, st.end);
          setCells(rows.slice(st.sel.r0, st.sel.r1 + 1).map(r => r.id), nights.slice(st.sel.i0, st.sel.i1 + 1), q);
        };
        $('#bg-clear', m).onclick = () => {
          if (!st.sel) { toast('Выделите клетки сетки', 'warn'); return; }
          const rows = rowsOf(), nights = staysBlockNights(st.start, st.end);
          setCells(rows.slice(st.sel.r0, st.sel.r1 + 1).map(r => r.id), nights.slice(st.sel.i0, st.sel.i1 + 1), 0);
        };
        $('#bg-fill', m).onclick = () => {
          const from = $('#bg-fill-from', m).value, to = $('#bg-fill-to', m).value;
          const q = readQty('#bg-fill-qty');
          if (q === null) return;
          if (!from || !to || to < from) { toast('Укажите ночи «с — по»: конец не раньше начала', 'warn'); return; }
          if (from < st.start || to >= st.end) {
            toast(`Ночи вне блока: можно с ${dateRu(st.start)} по ${dateRu(staysAddDays(st.end, -1))}`, 'warn');
            return;
          }
          setCells([$('#bg-fill-cat', m).value], staysBlockNights(from, staysAddDays(to, 1)), q);
        };
      }

      /* тело запроса: сетка целиком, только ночи внутри дат блока */
      const body = () => {
        const grid = {};
        Object.entries(st.grid).forEach(([cid, by]) => {
          const kept = Object.fromEntries(Object.entries(by).filter(([n, q]) => q > 0 && n >= st.start && n < st.end));
          if (Object.keys(kept).length) grid[cid] = kept;
        });
        return { title: st.title, start: st.start, end: st.end, grid, ...(st.id ? { version: st.version } : {}) };
      };
      const url = () => (st.id ? `/api/stays/blocks/${st.id}` : '/api/stays/blocks');
      const method = () => (st.id ? 'PUT' : 'POST');
      const editFlow = {
        async preview() {
          const r = await api(`${url()}?preview=1`, { method: method(), body: body() });
          const dropped = r.result?.dropped?.length;
          renderPreview(r.diff, out(), r.overbook_refused, dropped ? html`<div class="sp-warn">Уйдут ночи вне новых дат: ${dropped}</div>` : nothing);
          return r;
        },
        save: () => api(url(), { method: method(), body: body() }),
      };
      let mode = editFlow;
      /* после записи карточка остаётся открытой и показывает ответ сервера: разложено / нехватка */
      const reload = async result => {
        if (onChanged) onChanged();
        const fresh = await api('/api/stays/blocks/' + result.result.id);
        Object.assign(st, { id: fresh.id, version: fresh.version, title: fresh.title, start: fresh.start, end: fresh.end,
          grid: staysGridCopy(fresh.grid), saved: staysGridCopy(fresh.grid), short: fresh.short,
          placed: fresh.placed, missing: fresh.missing, sel: null, anchor: null });
        $('#bg-title', m).value = st.title; $('#bg-start', m).value = st.start; $('#bg-end', m).value = st.end;
        render(nothing, out());
        paintGrid();
        if (!$('#bg-delete', m)) {
          const btn = document.createElement('button');
          btn.className = 'btn btn-danger';
          btn.id = 'bg-delete';
          btn.textContent = 'Удалить…';
          m.querySelector('.modal-foot').prepend(btn);
        }
        bindDelete();
      };
      let foot = { reset() {} };
      if (edit) {
        foot = staysBindGatedFoot(m, { preview: () => mode.preview(), save: () => mode.save() }, {
          okText: 'Блок сохранён', out,
          done: r => (mode === editFlow ? reload(r).catch(err => toast(err.message, 'warn')) : (closeModal(), onChanged && onChanged())),
        });
      } else {
        $('[data-close]', m).onclick = closeModal;
      }
      const bindDelete = () => {
        const del = $('#bg-delete', m);
        if (!del) return;
        del.onclick = async () => {
          const path = `/api/stays/blocks/${st.id}?version=${st.version}`;
          mode = {
            async preview() {
              const r = await api(`${path}&preview=1`, { method: 'DELETE' });
              renderPreview(r.diff, out(), r.overbook_refused);
              return r;
            },
            save: () => api(path, { method: 'DELETE' }),
          };
          $('[data-save]', m).textContent = 'Удалить';
          try { await mode.preview(); } catch (e) { toast(e.message, 'err'); }
        };
      };
      bindDelete();
      paintGrid();
    },
  });
}

/* ── мост к общей области имён (генерируется tools/gen_js_globals.py; уйдёт вместе с переходом файла на import/export) ── */
Object.assign(globalThis, {
  staysBlockEmpty,
  staysBlock,
  staysPeriodRange,
  staysPeriodBarView,
  staysSearchView,
  renderBlocksTab,
  openBlockCard,
});
/* ── конец моста ── */
