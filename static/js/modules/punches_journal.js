'use strict';

/* ══════════════════════════════════════════════════════════════════
   ЖУРНАЛ ОТМЕТОК — инструмент менеджера в разделе «Отметки» (ревью 22.10.2026):
   все отметки за месяц, отметка за сотрудника (в т.ч. задним числом — забытый
   уход) и отмена ошибочной. Бэкенд был готов давно (POST /api/punches с
   employee_id/ts, DELETE /api/punches/{id}), кнопок не было — правили SQL-ом.
   Права: просмотр — punches.view_all, отметка за другого — punches.punch_for_others,
   задним числом — punches.backfill, отмена — punches.manage. Проверяет их сервер;
   здесь права только прячут недоступные кнопки.
   ══════════════════════════════════════════════════════════════════ */

const PUNCH_SOURCES = { web: 'сам', manual: 'вручную' };
const punchJournal = { month: '', employeeId: '' };

/* Контейнер #mk-journal рисует loadMarks; опрос доски (30 с) его не трогает. */
async function loadPunchJournal() {
  const host = $('#mk-journal');
  if (!host || !can('punches.view_all')) return;
  if (!punchJournal.month) {                 // местный месяц, а не UTC (toISOString)
    const d = new Date();
    punchJournal.month = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  }
  const emps = (state.employees || []).filter(e => e.active !== false);
  host.innerHTML = `<div class="panel">
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px">
      <h3 class="panel-title" style="margin:0">Журнал отметок</h3>
      <div class="spacer"></div>
      <input type="month" id="pj-month" value="${esc(punchJournal.month)}" aria-label="Месяц">
      <select id="pj-emp" aria-label="Сотрудник"><option value="">Все сотрудники</option>
        ${emps.map(e => `<option value="${e.id}" ${String(e.id) === punchJournal.employeeId ? 'selected' : ''}>${esc(e.full_name)}</option>`).join('')}
      </select>
      ${can('punches.punch_for_others') && emps.length
        ? '<button class="btn btn-sm btn-primary" id="pj-add">+ Отметка за сотрудника</button>' : ''}
    </div>
    <div id="pj-body"><div class="empty">Загрузка…</div></div></div>`;
  $('#pj-month').onchange = e => { punchJournal.month = e.target.value; fetchPunchJournal(); };
  $('#pj-emp').onchange = e => { punchJournal.employeeId = e.target.value; fetchPunchJournal(); };
  const add = $('#pj-add');
  if (add) add.onclick = () => punchForOtherModal(emps);
  await fetchPunchJournal();
}

async function fetchPunchJournal() {
  const body = $('#pj-body');
  if (!body) return;
  const [y, m] = (punchJournal.month || '').split('-').map(Number);
  if (!y || !m) { body.innerHTML = '<div class="empty">Выберите месяц</div>'; return; }
  const emp = punchJournal.employeeId ? `&employee_id=${punchJournal.employeeId}` : '';
  let items;
  try { items = await api(`/api/punches?year=${y}&month=${m}${emp}`, { silent: true }); } catch (e) {
    body.innerHTML = `<div class="empty">${esc(e.message || e)}</div>`;
    return;
  }
  if (!items.length) { body.innerHTML = '<div class="empty">Отметок за месяц нет</div>'; return; }
  const canCancel = can('punches.manage');
  body.innerHTML = `<div class="table-wrap"><table class="data"><thead><tr>
      <th>Дата</th><th>Время</th><th>Сотрудник</th><th>Отметка</th><th>Кто поставил</th><th>Комментарий</th>
      ${canCancel ? '<th></th>' : ''}</tr></thead><tbody>
    ${items.map(p => `<tr>
      <td>${esc(dateRu(p.ts.slice(0, 10)))}</td><td><b>${esc(p.ts.slice(11, 16))}</b></td>
      <td>${esc(p.employee)}</td>
      <td style="white-space:nowrap">${p.kind === 'IN' ? '→ пришёл' : '← ушёл'}</td>
      <td>${esc(PUNCH_SOURCES[p.source] || p.source || '')}</td>
      <td>${esc(p.note || '')}</td>
      ${canCancel ? `<td><button class="btn btn-sm btn-ghost" data-pj-del="${p.id}">Отменить</button></td>` : ''}
    </tr>`).join('')}</tbody></table></div>`;
  $$('[data-pj-del]', body).forEach(b => b.onclick = () => {
    const p = items.find(x => String(x.id) === b.dataset.pjDel);
    confirmDialog('Отменить отметку?',
      `${p.employee}: ${p.kind === 'IN' ? 'приход' : 'уход'} ${dateRu(p.ts.slice(0, 10))} в ${p.ts.slice(11, 16)}. `
      + 'Отмена записывается в журнал аудита.', async () => {
        await api(`/api/punches/${p.id}`, { method: 'DELETE' });
        toast('Отметка отменена', 'ok');
        await fetchPunchJournal();
        fetchMarks(true);
      }, 'Отменить отметку');
  });
}

function punchForOtherModal(emps) {
  const backfill = can('punches.backfill');
  openModal({
    title: 'Отметка за сотрудника',
    subtitle: backfill ? 'Время пустое — отметка «сейчас»; заполненное — задним числом (до 2 месяцев)' : '',
    body: `<label class="field"><span>Сотрудник</span><select id="pf-emp">
        ${emps.map(e => `<option value="${e.id}" ${String(e.id) === punchJournal.employeeId ? 'selected' : ''}>${esc(e.full_name)}</option>`).join('')}
      </select></label>
      <label class="field"><span>Отметка</span><select id="pf-kind">
        <option value="in">Пришёл</option><option value="out">Ушёл</option></select></label>
      ${backfill ? `<label class="field"><span>Время (локальное)</span>
        <input type="datetime-local" id="pf-ts" max="${new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16)}"></label>` : ''}
      <label class="field"><span>Комментарий</span><input type="text" id="pf-note" maxlength="255"
        placeholder="например: забыл отметить уход"></label>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
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
