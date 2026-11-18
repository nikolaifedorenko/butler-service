'use strict';

/* ══════════════════════════════════════════════════════════════════
   ЖУРНАЛ АУДИТА — отдельная вкладка с фильтрами и выгрузкой
   Модуль на lit-html (ADR-0013, раздел 7).
   ══════════════════════════════════════════════════════════════════ */
import { registerModule } from '../app.js';
import { $, api, downloadBlob, state } from '../core.js';
import { html, mount, render } from '../ui/html.js';

state.auditQ = state.auditQ || { q: '', action: '', actor: '', date_from: '', date_to: '', offset: 0 };
const AUDIT_PAGE = 100;

registerModule({ views: { audit: loadAudit }, screens: { audit: { icon: 'list' } } });

async function loadAudit() {
  const f = state.auditQ;
  const host = $('#view-audit');
  const qs = () => new URLSearchParams({ q: f.q, action: f.action, actor: f.actor, date_from: f.date_from, date_to: f.date_to }).toString()
    .replace(/(date_from|date_to)=(&|$)/g, '');
  let data = null;
  let error = '';
  try { data = await api(`/api/audit?${qs()}&limit=${AUDIT_PAGE}&offset=${f.offset}`); } catch (e) { error = e.message; }
  const pretty = p => { try { const o = JSON.parse(p); return Object.keys(o).length ? JSON.stringify(o, null, 0) : ''; } catch { return p; } };
  const go = () => {
    Object.assign(f, { q: $('#af-q', host).value.trim(), action: $('#af-action', host).value, actor: $('#af-actor', host).value.trim(),
      date_from: $('#af-from', host).value, date_to: $('#af-to', host).value, offset: 0 });
    loadAudit();
  };
  render(html`
    <div class="page-head">
      <div><h2>Журнал аудита</h2><div class="sub">Кто, когда и что менял: отметки, График, Табель, закрытия периодов, права, настройки</div></div>
      <div class="spacer"></div>
      <button class="btn btn-sm btn-ghost" id="au-csv" @click=${() => downloadBlob(`/api/audit/csv?${qs()}`, 'audit.csv')}>CSV</button>
    </div>
    <div class="panel"><div class="v4-filters">
      <label class="field"><span>Поиск</span><input type="text" id="af-q" .value=${f.q} placeholder="объект, данные, автор"></label>
      <label class="field"><span>Действие</span><select id="af-action"><option value="">все</option>${(data?.actions || []).map(a =>
        html`<option value=${a.action} ?selected=${a.action === f.action}>${a.title}</option>`)}</select></label>
      <label class="field"><span>Кто</span><input type="text" id="af-actor" .value=${f.actor}></label>
      <label class="field"><span>С</span><input type="date" id="af-from" .value=${f.date_from}></label>
      <label class="field"><span>По</span><input type="date" id="af-to" .value=${f.date_to}></label>
      <button class="btn btn-primary" id="af-go" @click=${go}>Показать</button></div></div>
    <div id="au-body">${error ? html`<div class="panel"><div class="empty">${error}</div></div>` : html`
    <div class="table-wrap"><table class="data responsive"><thead><tr><th>Время</th><th>Кто</th><th>Действие</th><th>Объект</th><th>Данные</th></tr></thead>
      <tbody>${data.items.length ? data.items.map(i => html`<tr>
        <td data-label="Время" style="white-space:nowrap">${i.ts.replace('T', ' ')}</td>
        <td data-label="Кто">${i.actor}</td>
        <td data-label="Действие"><span class="badge">${i.action_title}</span></td>
        <td data-label="Объект">${i.target}</td>
        <td data-label="Данные" class="v4-payload">${pretty(i.payload)}</td></tr>`)
        : html`<tr><td colspan="5" class="empty">Записей нет</td></tr>`}</tbody>
    </table></div>
    <div style="display:flex;gap:8px;align-items:center;margin-top:10px">
      <button class="btn btn-sm" id="au-prev" ?disabled=${!f.offset} @click=${() => { f.offset = Math.max(0, f.offset - AUDIT_PAGE); loadAudit(); }}>‹ Новее</button>
      <span class="hint" style="margin:0">${data.total ? `${f.offset + 1}–${Math.min(f.offset + AUDIT_PAGE, data.total)} из ${data.total}` : ''}</span>
      <button class="btn btn-sm" id="au-next" ?disabled=${!(f.offset + AUDIT_PAGE < data.total)} @click=${() => { f.offset += AUDIT_PAGE; loadAudit(); }}>Старее ›</button></div>`}</div>`, mount(host));
}
