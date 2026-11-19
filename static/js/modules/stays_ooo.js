/* ══════════════════════════════════════════════════════════════════════
   «ШАХМАТКА» — вкладка «OOO»: объекты не в продаже по половинкам суток
   (спецификация docs/superpowers/specs/2026-10-27-stays-ooo-blocks-design.md §3.1, §6, §7).
   Список видят все уровни доступа (имён гостей в OOO нет); запись — только stays.edit, всегда с
   предпросмотром «кто переедет». Фильтры и сортировка — на сервере (GET /api/stays/ooo), как
   во вкладке «Брони»; период и поиск — общие помощники из stays_blocks.js.
   Модуль на lit-html (ADR-0013, раздел 7).
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

import { can } from '../app.js';
import { $, api, dateRu, loadGenerationFor, openModal, toast } from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { checkField, fieldRow, selectField, textInput } from '../ui/form.js';
import { formFootView, previewThenSave, renderPreview, staysBindGatedFoot } from './stays_forms.js';
import { staysPeriodBarView, staysPeriodRange, staysSearchView } from './stays_blocks.js';
import { staysFilterView, staysFund, staysFundParams, staysToday } from './stays.js';

/* колонки: ключ сортировки сервера — заголовок */
const STAYS_OOO_COLS = [['unit', 'Объект'], ['category', 'Категория'], ['start', 'С'], ['end', 'По'],
  ['reason', 'Причина'], ['author', 'Поставил'], ['created_at', 'Создано']];
const STAYS_OOO_PAGE = 200;

export function staysOooEmpty() { return { mode: 'month', first: '', last: '', q: '', sort: 'start', dir: 'asc' }; }
export const staysOoo = staysOooEmpty();

function staysOooParams() {
  const o = staysOoo;
  const p = staysFundParams(new URLSearchParams({ sort: o.sort, dir: o.dir }));
  const range = staysPeriodRange(o);
  if (range) { p.set('first', range.first); p.set('last', range.last); }
  if (o.q.trim()) p.set('q', o.q.trim());
  return p;
}

/* «с вечера» / «с утра» и «до утра» / «до вечера»: половинки суток, как в форме */
const staysOooStart = r => `${dateRu(r.start)} ${r.start_half === 'AM' ? 'с утра' : 'с вечера'}`;
const staysOooEnd = r => `${dateRu(r.end)} ${r.end_half === 'PM' ? 'до вечера' : 'до утра'}`;

export async function renderOooTab(body) {
  const fund = await staysFund();
  const fresh = loadGenerationFor(body);
  const o = staysOoo;
  let rows = [];
  let total = 0;
  let error = '';
  let loadingMore = false;
  const page = offset => {
    const p = staysOooParams();
    p.set('offset', offset);
    p.set('limit', STAYS_OOO_PAGE);
    return api('/api/stays/ooo?' + p, { silent: true });
  };
  try {
    ({ rows, total } = await page(0));
  } catch (e) {
    error = e.message;
    toast(error, 'warn');
  }
  if (!fresh()) return;
  const rerender = () => renderOooTab(body);
  const draw = () => render(screen(), mount(body));
  const editable = can('stays.edit');
  const sortBy = key => {
    if (o.sort === key) o.dir = o.dir === 'asc' ? 'desc' : 'asc'; else { o.sort = key; o.dir = 'asc'; }
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
  const arrow = key => (o.sort === key ? (o.dir === 'asc' ? ' ↑' : ' ↓') : '');
  const open = r => { if (editable) openOooForm(r, rerender).catch(err => toast(err.message, 'warn')); };
  const rowView = r => html`<tr class=${editable ? 'bk-row' : ''} data-oo-row=${r.id} tabindex=${editable ? '0' : nothing}
      @click=${() => open(r)} @keydown=${e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.currentTarget.click(); } }}>
    <td title=${r.group}>${r.unit}${r.group ? html` <span class="muted">${r.group}</span>` : nothing}</td>
    <td>${r.category || '—'}</td><td>${staysOooStart(r)}</td><td>${staysOooEnd(r)}</td>
    <td>${r.reason || '—'}</td><td>${r.author || '—'}</td>
    <td>${r.created_at.slice(0, 16).replace('T', ' ')}</td></tr>`;
  const result = () => (error ? html`<div class="panel"><p class="muted">${error}</p></div>`
    : html`<div class="muted" id="oo-total">Найдено OOO: ${total}${rows.length < total ? ` · показано ${rows.length}` : ''}</div>
      <div class="sb-scroll"><table class="bk-table"><thead><tr>${STAYS_OOO_COLS.map(([k, t]) =>
        html`<th data-oo-sort=${k} title="Сортировать" style="cursor:pointer" @click=${() => sortBy(k)}>${t}${arrow(k)}</th>`)}</tr></thead>
      <tbody>${rows.length ? rows.map(rowView) : html`<tr><td colspan=${STAYS_OOO_COLS.length} class="empty">OOO по фильтру нет</td></tr>`}</tbody></table></div>
      ${rows.length < total ? html`<button class="btn" id="oo-more" ?disabled=${loadingMore} @click=${more}>Показать ещё ${Math.min(STAYS_OOO_PAGE, total - rows.length)}</button>` : nothing}`);
  const screen = () => html`<div class="sb-toolbar">${staysPeriodBarView(o, body, rerender)}
      ${staysSearchView('oo-q', 'причина или объект', o, rerender)}
      ${editable ? html`<button class="btn btn-sm btn-primary" id="oo-new"
        @click=${() => openOooForm(null, rerender).catch(err => toast(err.message, 'warn'))}>+ OOO</button>` : nothing}</div>
    ${staysFilterView(fund, rerender, { people: false })}<div id="oo-result">${result()}</div>`;
  draw();
}

/* ─────────────── Форма OOO: создание, правка, удаление — с предпросмотром ─────────────── */
/* src — id, null (новое), либо уже загруженная запись (строка списка, полоса шахматки, табло дня:
   там причина лежит в title); onChanged — обновить вид после записи */
export async function openOooForm(src, onChanged) {
  const fund = await staysFund();
  let hold = src || {};
  if (typeof src === 'number') {
    hold = (await api('/api/stays/ooo?limit=200', { silent: true })).rows.find(r => r.id === src);
    if (!hold) throw new Error('OOO не найден — обновите список');
  }
  const reason = hold.reason ?? hold.title ?? '';
  const isNew = !hold.id;
  const first = hold.start || staysToday();
  /* «с утра» (start_half = AM) и «до вечера» (end_half = PM) — сутки целиком; новое OOO — целые сутки */
  const wholeStart = isNew || hold.start_half === 'AM';
  const wholeEnd = isNew || hold.end_half === 'PM';
  const units = fund.units.filter(u => u.active).map(u => [u.id, u.label]);
  if (hold.unit_id && !units.some(([id]) => id === hold.unit_id)) units.push([hold.unit_id, hold.unit || '№' + hold.unit_id]);
  openModal({
    title: isNew ? 'OOO — не в продаже' : `OOO · ${dateRu(hold.start)}–${dateRu(hold.end)}`,
    subtitle: 'Объект не в продаже: по умолчанию с вечера «с» до утра «по»; галочки — сутки целиком. Брони на эти дни перераспределятся. Блоки по категориям — на вкладке «Блоки»',
    body: html`<div class="grid-2">
        ${fieldRow('Объект', selectField('hf-unit', units, hold.unit_id))}
        <div></div>
        ${fieldRow('С', textInput('hf-start', first, 'date'))}
        ${fieldRow('По', textInput('hf-end', hold.end || first, 'date'))}
        ${checkField('hf-start-am', 'С утра', wholeStart)}
        ${checkField('hf-end-pm', 'До вечера', wholeEnd)}
      </div>
      ${fieldRow('Причина', html`<input id="hf-title" type="text" maxlength="120" .value=${reason}>`)}
      <div class="muted" data-hf-hint>без имён гостей — видно всем</div>
      <div id="rf-preview-out" class="sp-out"></div>`,
    footer: html`${isNew ? nothing : html`<button class="btn btn-danger" id="hf-delete">Удалить…</button>`}${formFootView()}`,
    onMount(m) {
      const out = () => $('#rf-preview-out', m);
      const body = () => ({ unit_id: Number($('#hf-unit', m).value),
        start: $('#hf-start', m).value, end: $('#hf-end', m).value,
        start_half: $('#hf-start-am', m).checked ? 'AM' : 'PM', end_half: $('#hf-end-pm', m).checked ? 'PM' : 'AM',
        reason: $('#hf-title', m).value, ...(isNew ? {} : { version: hold.version }) });
      const edit = previewThenSave({ url: isNew ? '/api/stays/ooo' : `/api/stays/ooo/${hold.id}`,
        method: isNew ? 'POST' : 'PUT', body, out });
      const del = `/api/stays/ooo/${hold.id}?version=${hold.version}`;
      const remove = {
        async preview() {
          const r = await api(`${del}&preview=1`, { method: 'DELETE' });
          renderPreview(r.diff, out(), r.overbook_refused);
          return r;
        },
        save: () => api(del, { method: 'DELETE' }),
      };
      let mode = edit;
      staysBindGatedFoot(m, { preview: () => mode.preview(), save: () => mode.save() },
        { onSaved: onChanged, okText: 'Готово', out });
      const delBtn = $('#hf-delete', m);
      if (delBtn) delBtn.onclick = async () => {
        mode = remove;
        $('[data-save]', m).textContent = 'Удалить';
        try {
          const r = await remove.preview();
          if (r.overbook_refused) $('[data-save]', m).disabled = true;
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}
