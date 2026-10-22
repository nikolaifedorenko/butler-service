'use strict';

/* ══════════════════════════════════════════════════════════════════
   ЖУРНАЛ АУДИТА — отдельная вкладка с фильтрами и выгрузкой
   ══════════════════════════════════════════════════════════════════ */
state.auditQ = state.auditQ || { q: '', action: '', actor: '', date_from: '', date_to: '', offset: 0 };
const AUDIT_PAGE = 100;

async function loadAudit() {
  const f = state.auditQ;
  $('#view-audit').innerHTML = `
    <div class="page-head">
      <div><h2>Журнал аудита</h2><div class="sub">Кто, когда и что менял: отметки, График, Табель, закрытия периодов, права, настройки</div></div>
      <div class="spacer"></div>
      <button class="btn btn-sm btn-ghost" id="au-csv">CSV</button>
    </div>
    <div class="panel"><div class="v4-filters">
      <label class="field"><span>Поиск</span><input type="text" id="af-q" value="${esc(f.q)}" placeholder="объект, данные, автор"></label>
      <label class="field"><span>Действие</span><select id="af-action"><option value="">все</option></select></label>
      <label class="field"><span>Кто</span><input type="text" id="af-actor" value="${esc(f.actor)}"></label>
      <label class="field"><span>С</span><input type="date" id="af-from" value="${esc(f.date_from)}"></label>
      <label class="field"><span>По</span><input type="date" id="af-to" value="${esc(f.date_to)}"></label>
      <button class="btn btn-primary" id="af-go">Показать</button></div></div>
    <div id="au-body"><div class="empty">Загрузка…</div></div>`;
  const qs = () => new URLSearchParams({ q: f.q, action: f.action, actor: f.actor, date_from: f.date_from, date_to: f.date_to }).toString()
    .replace(/(date_from|date_to)=(&|$)/g, '');
  $('#af-go').onclick = () => {
    Object.assign(f, { q: $('#af-q').value.trim(), action: $('#af-action').value, actor: $('#af-actor').value.trim(),
      date_from: $('#af-from').value, date_to: $('#af-to').value, offset: 0 });
    loadAudit();
  };
  $('#au-csv').onclick = () => downloadBlob(`/api/audit/csv?${qs()}`, 'audit.csv');
  let data;
  try { data = await api(`/api/audit?${qs()}&limit=${AUDIT_PAGE}&offset=${f.offset}`); } catch (e) {
    $('#au-body').innerHTML = `<div class="panel"><div class="empty">${esc(e.message)}</div></div>`; return;
  }
  $('#af-action').innerHTML = '<option value="">все</option>' + data.actions.map(a =>
    `<option value="${esc(a.action)}" ${a.action === f.action ? 'selected' : ''}>${esc(a.title)}</option>`).join('');
  const pretty = p => { try { const o = JSON.parse(p); return Object.keys(o).length ? JSON.stringify(o, null, 0) : ''; } catch { return p; } };
  $('#au-body').innerHTML = `
    <div class="table-wrap"><table class="data responsive"><thead><tr><th>Время</th><th>Кто</th><th>Действие</th><th>Объект</th><th>Данные</th></tr></thead>
      <tbody>${data.items.map(i => `<tr>
        <td data-label="Время" style="white-space:nowrap">${esc(i.ts.replace('T', ' '))}</td>
        <td data-label="Кто">${esc(i.actor)}</td>
        <td data-label="Действие"><span class="badge">${esc(i.action_title)}</span></td>
        <td data-label="Объект">${esc(i.target)}</td>
        <td data-label="Данные" class="v4-payload">${esc(pretty(i.payload))}</td></tr>`).join('') || '<tr><td colspan="5" class="empty">Записей нет</td></tr>'}</tbody>
    </table></div>
    <div style="display:flex;gap:8px;align-items:center;margin-top:10px">
      <button class="btn btn-sm" id="au-prev" ${f.offset ? '' : 'disabled'}>‹ Новее</button>
      <span class="hint" style="margin:0">${data.total ? `${f.offset + 1}–${Math.min(f.offset + AUDIT_PAGE, data.total)} из ${data.total}` : ''}</span>
      <button class="btn btn-sm" id="au-next" ${f.offset + AUDIT_PAGE < data.total ? '' : 'disabled'}>Старее ›</button></div>`;
  $('#au-prev').onclick = () => { f.offset = Math.max(0, f.offset - AUDIT_PAGE); loadAudit(); };
  $('#au-next').onclick = () => { f.offset += AUDIT_PAGE; loadAudit(); };
}
