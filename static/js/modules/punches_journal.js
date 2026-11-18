'use strict';

/* ══════════════════════════════════════════════════════════════════
   ЖУРНАЛ ОТМЕТОК — инструмент менеджера в разделе «Отметки» (ревью 22.10.2026):
   все отметки за месяц, отметка за сотрудника (в т.ч. задним числом — забытый
   уход) и отмена ошибочной. Бэкенд был готов давно (POST /api/punches с
   employee_id/ts, DELETE /api/punches/{id}), кнопок не было — правили SQL-ом.
   Права: просмотр — punches.view_all, отметка за другого — punches.punch_for_others,
   задним числом — punches.backfill, отмена — punches.manage. Проверяет их сервер;
   здесь права только прячут недоступные кнопки.
   Модуль на lit-html (ADR-0013, раздел 7).
   ══════════════════════════════════════════════════════════════════ */
import { can } from '../app.js';
import { $, api, closeModal, confirmDialog, dateRu, openModal, state, toast } from '../core.js';
import { html, nothing, render } from '../ui/html.js';
import { fetchMarks } from './marks.js';

const PUNCH_SOURCES = { web: 'сам', manual: 'вручную' };
const punchJournal = { month: '', employeeId: '' };
/* что показывает таблица: загрузка, текст ошибки либо отметки месяца */
const table = { loading: true, error: '', items: null };

/* Контейнер #mk-journal — пустой, его рисует эта функция; опрос доски (30 с) его не трогает. */
export async function loadPunchJournal() {
  const host = $('#mk-journal');
  if (!host || !can('punches.view_all')) return;
  if (!punchJournal.month) {                 // местный месяц, а не UTC (toISOString)
    const d = new Date();
    punchJournal.month = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  }
  table.loading = true;
  drawJournal();
  await fetchPunchJournal();
}

const activeEmployees = () => (state.employees || []).filter(e => e.active !== false);

function employeeOptions() {
  return activeEmployees().map(e => html`<option value=${e.id} ?selected=${String(e.id) === punchJournal.employeeId}>${e.full_name}</option>`);
}

function drawJournal() {
  const host = $('#mk-journal');
  if (!host) return;
  const emps = activeEmployees();
  render(html`<div class="panel">
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px">
      <h3 class="panel-title" style="margin:0">Журнал отметок</h3>
      <div class="spacer"></div>
      <input type="month" id="pj-month" .value=${punchJournal.month} aria-label="Месяц"
        @change=${e => { punchJournal.month = e.target.value; fetchPunchJournal(); }}>
      <select id="pj-emp" aria-label="Сотрудник" @change=${e => { punchJournal.employeeId = e.target.value; fetchPunchJournal(); }}>
        <option value="">Все сотрудники</option>${employeeOptions()}</select>
      ${can('punches.punch_for_others') && emps.length
        ? html`<button class="btn btn-sm btn-primary" id="pj-add" @click=${() => punchForOtherModal(emps)}>+ Отметка за сотрудника</button>`
        : nothing}
    </div>
    <div id="pj-body">${bodyTemplate()}</div></div>`, host);
}

function bodyTemplate() {
  if (table.loading) return html`<div class="empty">Загрузка…</div>`;
  if (table.error) return html`<div class="empty">${table.error}</div>`;
  const items = table.items;
  if (!items) return html`<div class="empty">Выберите месяц</div>`;
  if (!items.length) return html`<div class="empty">Отметок за месяц нет</div>`;
  const canCancel = can('punches.manage');
  return html`<div class="table-wrap"><table class="data"><thead><tr>
      <th>Дата</th><th>Время</th><th>Сотрудник</th><th>Отметка</th><th>Кто поставил</th><th>Комментарий</th>
      ${canCancel ? html`<th></th>` : nothing}</tr></thead><tbody>
    ${items.map(p => html`<tr>
      <td>${dateRu(p.ts.slice(0, 10))}</td><td><b>${p.ts.slice(11, 16)}</b></td>
      <td>${p.employee}</td>
      <td style="white-space:nowrap">${p.kind === 'IN' ? '→ пришёл' : '← ушёл'}</td>
      <td>${PUNCH_SOURCES[p.source] || p.source || ''}</td>
      <td>${p.note || ''}</td>
      ${canCancel ? html`<td><button class="btn btn-sm btn-ghost" data-pj-del=${p.id} @click=${() => cancelPunch(p)}>Отменить</button></td>` : nothing}
    </tr>`)}</tbody></table></div>`;
}

export async function fetchPunchJournal() {
  const [y, m] = (punchJournal.month || '').split('-').map(Number);
  if (!y || !m) { table.loading = false; table.error = ''; table.items = null; drawJournal(); return; }
  const emp = punchJournal.employeeId ? `&employee_id=${punchJournal.employeeId}` : '';
  try {
    table.items = await api(`/api/punches?year=${y}&month=${m}${emp}`, { silent: true });
    table.error = '';
  } catch (e) {
    table.error = String(e.message || e);
    table.items = null;
  }
  table.loading = false;
  drawJournal();
}

function cancelPunch(p) {
  confirmDialog('Отменить отметку?',
    `${p.employee}: ${p.kind === 'IN' ? 'приход' : 'уход'} ${dateRu(p.ts.slice(0, 10))} в ${p.ts.slice(11, 16)}. `
    + 'Отмена записывается в журнал аудита.', async () => {
      const r = await api(`/api/punches/${p.id}`, { method: 'DELETE' });
      toast('Отметка отменена', 'ok', r && r.warning ? [r.warning] : []);
      await fetchPunchJournal();
      fetchMarks(true);
    }, 'Отменить отметку');
}

function punchForOtherModal(emps) {
  const backfill = can('punches.backfill');
  const maxTs = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  openModal({
    title: 'Отметка за сотрудника',
    subtitle: backfill ? 'Время пустое — отметка «сейчас»; заполненное — задним числом (до 2 месяцев)' : '',
    body: html`<label class="field"><span>Сотрудник</span><select id="pf-emp">
        ${emps.map(e => html`<option value=${e.id} ?selected=${String(e.id) === punchJournal.employeeId}>${e.full_name}</option>`)}
      </select></label>
      <label class="field"><span>Отметка</span><select id="pf-kind">
        <option value="in">Пришёл</option><option value="out">Ушёл</option></select></label>
      ${backfill ? html`<label class="field"><span>Время (локальное)</span>
        <input type="datetime-local" id="pf-ts" max=${maxTs}></label>` : nothing}
      <label class="field"><span>Комментарий</span><input type="text" id="pf-note" maxlength="255"
        placeholder="например: забыл отметить уход"></label>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-save>Поставить отметку</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        const body = { employee_id: Number($('#pf-emp', m).value), kind: $('#pf-kind', m).value,
                       note: $('#pf-note', m).value.trim() };
        const ts = $('#pf-ts', m)?.value;
        if (ts) body.ts = ts;
        const r = await api('/api/punches', { method: 'POST', body });
        closeModal();
        toast(r.message || 'Отметка поставлена', 'ok', r.warnings || []);
        await fetchPunchJournal();
        fetchMarks(true);
      };
    },
  });
}
