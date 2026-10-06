/* ══════════════════════════════════════════════════════════════════════
   Движок v4: «Кто на работе» / «Посещения», Табель, Управленческий табель,
   Права доступа, Журнал аудита, справочники движка (в Настройках).
   Зависит от core.js (api, state, $, esc, openModal, toast …) и app.js (can, poll).
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

const V4_CODE_COLORS = {
  'Я': '#34a862', 'Н': '#5b6bd6', 'К': '#2b8fb6', 'В': '#c3cdd9', 'ДО': '#d9822b', 'ОТ': '#f0a500',
  'ОВ': '#9b59b6', 'Б': '#e05d4b', 'НБ': '#c0504d', 'НН': '#b03a48',
};
const V4_FLAG_CLASS = { danger: 'danger', warn: 'warn', info: 'info', muted: 'muted' };

function v4MonthNav(prefix, onShift) {
  return `<div class="month-nav"><button id="${prefix}-prev">‹</button>
    <div class="label" id="${prefix}-label">${MONTHS[state.month - 1]} ${state.year}</div>
    <button id="${prefix}-next">›</button></div>`;
}
function v4BindMonthNav(prefix, reload) {
  const shift = delta => {
    let m = state.month + delta, y = state.year;
    if (m < 1) { m = 12; y--; } if (m > 12) { m = 1; y++; }
    state.month = m; state.year = y; reload();
  };
  $(`#${prefix}-prev`).onclick = () => shift(-1);
  $(`#${prefix}-next`).onclick = () => shift(1);
}
function v4DayHead(iso) {
  const d = new Date(iso + 'T12:00:00');
  const wd = WD_SHORT[(d.getDay() + 6) % 7];
  const weekend = d.getDay() === 0 || d.getDay() === 6;
  return `<th class="v4-day${weekend ? ' we' : ''}${iso === todayISO() ? ' today' : ''}">${d.getDate()}<small>${wd}</small></th>`;
}
function v4Hours(v) { return v ? hours(v) : ''; }

/* ══════════════════════════════════════════════════════════════════
   КТО НА РАБОТЕ / ПОСЕЩЕНИЯ — одинаковое содержание (по требованию):
   счётчики «Сейчас на работе» и «По графику сегодня» + три списка
   ══════════════════════════════════════════════════════════════════ */
async function loadPresence(view) {
  const host = $(`#view-${view}`);
  const title = view === 'onwork' ? 'Кто на работе' : 'Посещения';
  host.innerHTML = `
    <div class="page-head">
      <div><h2>${title}</h2>
        <div class="sub">Присутствие по реальным отметкам и ожидания по Графику на сегодня. Обновляется каждые 30 секунд</div></div>
      <div class="spacer"></div>
      <span class="badge ok" id="${view}-now" style="font-size:13px;padding:7px 12px">—</span>
      <button class="btn btn-sm" id="${view}-refresh">Обновить</button>
    </div>
    <div id="${view}-body"><div class="empty">Загрузка…</div></div>`;
  $(`#${view}-refresh`).onclick = () => fetchPresence(view);
  await fetchPresence(view);
  poll(view, () => fetchPresence(view, true));
}

function v4Contacts(e) {
  const tel = String(e.phone || '').trim();
  const tg = String(e.telegram || '').trim().replace(/^@+/, '');
  if (!tel && !tg) return '';
  return `<div class="contacts">${tel ? `<a href="tel:${esc(tel.replace(/[^0-9+]/g, ''))}">📞 ${esc(tel)}</a>` : ''}${
    tg ? `<a href="https://t.me/${esc(tg.replace(/[^A-Za-z0-9_]/g, ''))}" target="_blank" rel="noopener">✈️ @${esc(tg)}</a>` : ''}</div>`;
}

function v4PresenceCard(i, kind) {
  const e = i.employee;
  const row = (k, v, style = '') => `<div class="row"><span style="color:var(--muted)">${k}</span><b style="${style}">${v}</b></div>`;
  const plan = i.plan.length ? i.plan.join(', ') : '—';
  let rows = '';
  if (kind === 'present') {
    rows = row('На работе с', esc(i.since || '—')) + row('Уже работает', i.elapsed_hours != null ? hours(i.elapsed_hours) + ' ч' : '—')
      + row('По графику сегодня', esc(plan));
  } else if (kind === 'stepped_out') {
    rows = row('Ушёл в', esc(i.left_at || '—')) + row('Ожидается', esc(i.expected_at || '—'), i.overdue ? 'color:var(--danger)' : '')
      + row('По графику', esc(plan));
  } else {
    rows = row('Ожидается к', esc(i.expected_at || '—'), i.overdue ? 'color:var(--danger)' : '')
      + row('До', esc(i.expected_until || '—')) + row('По графику', esc(plan));
  }
  const late = i.overdue ? `<div class="row"><span></span><b style="color:var(--danger)">${kind === 'expected' ? 'опаздывает' : 'не вернулся вовремя'}</b></div>` : '';
  return `<div class="presence-card ${i.overdue ? 'late' : ''}">
    <div class="nm">${kind === 'present' ? '<span class="pulse"></span>' : ''}${esc(e.short_name)}</div>
    <div class="pos">${esc(e.position || '—')}${e.group ? ' · ' + esc(e.group) : ''}</div>
    ${v4Contacts(e)}${rows}${late}</div>`;
}

async function fetchPresence(view, silent) {
  let d;
  try { d = await api('/api/presence/board', { silent: !!silent }); } catch (e) {
    const b = $(`#${view}-body`); if (b) b.innerHTML = `<div class="panel"><div class="empty">${esc(e.message || e)}</div></div>`;
    return;
  }
  const body = $(`#${view}-body`);
  if (!body) return;
  $(`#${view}-now`).textContent = `Сейчас ${d.now.slice(11, 16)}`;
  const section = (title, list, kind, empty) => `<div class="panel"><h3 class="panel-title">${title} · ${list.length}</h3>
    ${list.length ? `<div class="presence-grid">${list.map(i => v4PresenceCard(i, kind)).join('')}</div>`
                  : `<div class="empty">${empty}</div>`}</div>`;
  body.innerHTML = `
    <div class="stat-grid">
      <div class="stat accent"><div class="k">Сейчас на работе</div><div class="v">${d.counts.present}</div></div>
      <div class="stat"><div class="k">По графику сегодня</div><div class="v">${d.counts.planned_today}</div></div>
    </div>
    ${section('Кто на работе прямо сейчас', d.present, 'present', 'Сейчас никто не отмечен на работе')}
    ${section('Отлучились, но ожидаются', d.stepped_out, 'stepped_out', 'Никто не отлучался')}
    ${section('Ожидаются к приходу сегодня', d.expected, 'expected', 'Больше никого сегодня не ждём')}`;
}

/* ══════════════════════════════════════════════════════════════════
   ТАБЕЛЬ — первичный документ: код дня + плановые часы (просмотр и правка)
   ══════════════════════════════════════════════════════════════════ */
async function loadTabel() {
  const host = $('#view-timesheet');
  host.innerHTML = `
    <div class="page-head">
      <div><h2>Табель</h2><div class="sub">Код дня и плановые часы — основа расчёта. Независим от Графика:
        правка Графика меняет только флаги, правка Табеля — часы и УТ</div></div>
      <div class="spacer"></div>
      ${v4MonthNav('tb')}
      <button class="btn btn-sm" id="tb-fill">Заполнить из Графика</button>
    </div>
    <div id="tb-body"><div class="empty">Загрузка…</div></div>`;
  v4BindMonthNav('tb', loadTabel);
  let data;
  try { data = await api(`/api/tabel?year=${state.year}&month=${state.month}`); } catch (e) {
    $('#tb-body').innerHTML = `<div class="panel"><div class="empty">${esc(e.message)}</div></div>`; return;
  }
  state.tabel = data;
  $('#tb-fill').style.display = data.can_edit ? '' : 'none';
  $('#tb-fill').onclick = () => tabelFillModal(data);
  renderTabel();
}

function v4CellLabel(c) {
  if (!c) return '';
  return c.value.replace(' ', '');
}

function renderTabel() {
  const d = state.tabel;
  const lockBadge = l => l === 'locked' ? '<span class="badge muted" title="Период закрыт, следующий тоже закрыт — правка запрещена">закрыт</span>'
    : (l === 'last_closed' ? '<span class="badge warn" title="Последний закрытый период: правка разрешена, затем — пересчёт в УТ">закрыт · можно править</span>' : '');
  const empty = d.rows.reduce((n, r) => n + d.days.filter(x => !r.cells[x]).length, 0);
  const rows = d.rows.map(r => `<tr>
    <td class="who">${esc(r.employee.short_name)}<small>${esc(r.employee.group)} ${lockBadge(r.lock)}</small></td>
    ${d.days.map(day => {
      const c = r.cells[day];
      const color = c ? (V4_CODE_COLORS[c.code] || '#8a94a6') : 'transparent';
      const edit = d.can_edit && r.lock !== 'locked';
      return `<td class="v4-cell${edit ? ' edit' : ''}${c ? '' : ' empty'}" ${edit ? `data-e="${r.employee.id}" data-d="${day}"` : ''}
        title="${c ? esc(c.value + (c.source === 'schedule' ? ' · из Графика' : ' · вручную') + (c.note ? ' · ' + c.note : '')) : 'не заполнено (считается «' + d.empty_code + '»)'}"
        style="${c ? `background:${withAlpha(color, .22)};border-left:3px solid ${color}` : ''}">${esc(v4CellLabel(c))}</td>`;
    }).join('')}
    <td class="num"><b>${hours(r.plan_hours)}</b></td></tr>`).join('');
  $('#tb-body').innerHTML = `
    ${empty ? `<div class="panel" style="border-color:#ecd9ae;background:#fffaf0"><b>${empty}</b> ${plural(empty, 'ячейка', 'ячейки', 'ячеек')} Табеля не заполнены —
      такие дни считаются «${esc(d.empty_code)}» (без плана, любая работа — переработка). Заполните их или нажмите «Заполнить из Графика».</div>` : ''}
    <div class="table-wrap v4-grid-wrap"><table class="data v4-grid">
      <thead><tr><th class="who">Сотрудник</th>${d.days.map(v4DayHead).join('')}<th>План, ч</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="${d.days.length + 2}" class="empty">Нет сотрудников</td></tr>`}</tbody>
    </table></div>
    <p class="hint">Коды: ${d.codes.map(c => `<span class="badge" style="background:${withAlpha(V4_CODE_COLORS[c.code] || '#8a94a6', .22)}" title="${esc(c.title)}">${esc(c.code)}</span> ${esc(c.title)}`).join(' · ')}.
      Значения с часами: ${d.values.map(esc).join(', ')}.</p>`;
  $$('#tb-body td.v4-cell.edit').forEach(td => td.onclick = () => tabelCellModal(+td.dataset.e, td.dataset.d));
}

function tabelCellModal(empId, day) {
  const d = state.tabel;
  const row = d.rows.find(r => r.employee.id === empId);
  const cur = row.cells[day] || null;
  const lastDay = d.days[d.days.length - 1].slice(8);
  openModal({
    title: `Табель · ${row.employee.short_name}`,
    subtitle: `${dateRu(day)}${row.lock === 'last_closed' ? ' · период закрыт: после правки нужен пересчёт в УТ' : ''}`,
    body: `
      <label class="field"><span>Код дня (Т1)</span><select id="tc-code">
        <option value="">— очистить ячейку —</option>
        ${d.codes.map(c => `<option value="${esc(c.code)}" data-h="${c.carries_hours ? 1 : 0}" ${cur && cur.code === c.code ? 'selected' : ''}>${esc(c.code)} — ${esc(c.title)}</option>`).join('')}
      </select></label>
      <label class="field" id="tc-hours-f"><span>Плановые часы</span>
        <input id="tc-hours" type="number" step="0.5" min="0" max="24" value="${cur ? cur.hours : 12}" list="tc-hours-list">
        <datalist id="tc-hours-list"></datalist></label>
      <label class="field"><span>Применить по число месяца (включительно)</span>
        <input id="tc-until" type="number" min="${+day.slice(8)}" max="${+lastDay}" value="${+day.slice(8)}"></label>
      <label class="field"><span>Примечание</span><input type="text" id="tc-note" value="${esc(cur?.note || '')}"></label>
      <p class="hint">Для кода с часами нужна строка окна в Т2 (${d.values.map(esc).join(', ')}).</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button><button class="btn btn-primary" data-save>Сохранить</button>`,
    onMount(m) {
      const sync = () => {
        const opt = $('#tc-code').selectedOptions[0];
        const withHours = opt && opt.dataset.h === '1';
        $('#tc-hours-f').style.display = withHours ? '' : 'none';
        $('#tc-hours-list').innerHTML = d.values.filter(v => v.startsWith(opt.value + ' ')).map(v => `<option value="${v.split(' ')[1]}">`).join('');
      };
      $('#tc-code').onchange = sync; sync();
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        const code = $('#tc-code').value, h = Number($('#tc-hours').value) || 0;
        const until = Math.max(+day.slice(8), Math.min(+lastDay, Number($('#tc-until').value) || +day.slice(8)));
        try {
          let res;
          if (until > +day.slice(8)) {
            const dates = d.days.filter(x => +x.slice(8) >= +day.slice(8) && +x.slice(8) <= until);
            res = await api('/api/tabel/bulk', { method: 'POST', body: { employee_ids: [empId], dates, code, hours: h } });
            (res.warnings || []).forEach(w => toast(w, 'warn'));
          } else {
            res = await api('/api/tabel/cell', { method: 'PUT', body: { employee_id: empId, date: day, code, hours: h, note: $('#tc-note').value } });
            if (res.warning) toast(res.warning, 'warn');
          }
          closeModal(); toast('Табель сохранён', 'ok'); loadTabel();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

function tabelFillModal(d) {
  openModal({
    title: 'Заполнить Табель из Графика',
    subtitle: `${MONTHS[d.month - 1]} ${d.year}`,
    body: `
      <p>Плановые смены Графика раскладываются по календарным дням и подбираются по окнам Т2
        («Я 12» = 08–20, «Н 4» = 20–24, «Н 8» = 00–08, «Н 12» = 00–08 + 20–24). Дни без работы получают код отсутствия.</p>
      <label class="field"><span>Что перезаписывать</span><select id="tf-mode">
        <option value="empty">Только пустые ячейки</option>
        <option value="schedule">Пустые и ранее заполненные из Графика (ручные правки сохраняются)</option>
        <option value="all">Все ячейки, включая ручные правки</option>
      </select></label>
      <p class="hint">Закрытые периоды (кроме последнего закрытого) не меняются.</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button><button class="btn btn-primary" data-save>Заполнить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        try {
          const r = await api('/api/tabel/fill-from-schedule', { method: 'POST',
            body: { year: d.year, month: d.month, overwrite: $('#tf-mode').value } });
          closeModal();
          toast(`Заполнено ячеек: ${r.written}, пропущено: ${r.skipped}`, r.warnings.length ? 'warn' : 'ok', r.warnings.slice(0, 8));
          loadTabel();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ══════════════════════════════════════════════════════════════════
   УПРАВЛЕНЧЕСКИЙ ТАБЕЛЬ — режимы view (без изъятий) и close (каскад, сохранение)
   ══════════════════════════════════════════════════════════════════ */
state.mgmtMode = state.mgmtMode || 'view';

async function loadMgmt() {
  const host = $('#view-mgmt');
  host.innerHTML = `
    <div class="page-head">
      <div><h2>Управленческий табель</h2><div class="sub">Коды УТ (ДЯ, ДН, ДЯ 2, ДН 2) по дням после размещения;
        в режиме «Закрытие» — после погашения недостачи банком и каскадом</div></div>
      <div class="spacer"></div>
      ${v4MonthNav('ut')}
      <div class="seg" id="ut-mode">
        <button data-m="view" class="${state.mgmtMode === 'view' ? 'active' : ''}">Просмотр (view)</button>
        <button data-m="close" class="${state.mgmtMode === 'close' ? 'active' : ''}">Закрытие (close)</button>
      </div>
      <button class="btn btn-sm btn-primary" id="ut-close">Закрыть период</button>
      <button class="btn btn-sm" id="ut-recalc">Пересчитать</button>
      <button class="btn btn-sm btn-ghost" id="ut-xlsx">Excel</button>
    </div>
    <div id="ut-body"><div class="empty">Загрузка…</div></div>`;
  v4BindMonthNav('ut', loadMgmt);
  $$('#ut-mode button').forEach(b => b.onclick = () => { state.mgmtMode = b.dataset.m; loadMgmt(); });
  $('#ut-xlsx').onclick = () => downloadBlob(`/api/mgmt/xlsx?year=${state.year}&month=${state.month}&mode=${state.mgmtMode}`, 'upr_tabel.xlsx');
  let data;
  try { data = await api(`/api/mgmt?year=${state.year}&month=${state.month}&mode=${state.mgmtMode}`); } catch (e) {
    $('#ut-body').innerHTML = `<div class="panel"><div class="empty">${esc(e.message)}</div></div>`; return;
  }
  state.mgmt = data;
  const anyOpen = data.rows.some(r => !r.closed && !r.error);
  const anyClosed = data.rows.some(r => r.closed && !r.next_closed);
  $('#ut-close').style.display = data.can_close && data.complete && anyOpen ? '' : 'none';
  $('#ut-recalc').style.display = data.can_recalculate && anyClosed ? '' : 'none';
  $('#ut-close').onclick = () => mgmtAction('close', null);
  $('#ut-recalc').onclick = () => mgmtAction('recalculate', null);
  renderMgmt();
}

function mgmtCell(codes) {
  const items = Object.entries(codes || {});
  if (!items.length) return '';
  return items.map(([t, h]) => `<span class="v4-code ${t.includes('2') ? 'x2' : ''} ${t.startsWith('ДН') ? 'n' : 'd'}">${esc(t.replace(' ', ''))}&nbsp;${hours(h)}</span>`).join('');
}

function renderMgmt() {
  const d = state.mgmt;
  const modeNote = d.mode === 'view'
    ? 'Просмотр: недостача показана, коды не изымаются, банк — предварительный (входящий + корректировки + зачисленное). Ничего не сохраняется.'
    : (d.complete ? 'Закрытие: недостача гасится банком, затем кодами по очереди Т6 целыми гранулами. Для незакрытых сотрудников показан предпросмотр — сохранится после «Закрыть период».'
                  : `Период ещё не завершён — закрыть можно с 00:00 дня после ${dateRu(d.period.end)}. Закрытие пока недоступно.`);
  const state_ = r => r.error ? `<span class="badge danger" title="${esc(r.error)}">ошибка</span>`
    : (r.closed ? `<span class="badge ok" title="Закрыл ${esc(r.closed_by || '')}">закрыт${r.revision > 1 ? ' · пересчёт ' + (r.revision - 1) : ''}</span>`
      : (r.source === 'preview' ? '<span class="badge warn">предпросмотр</span>' : '<span class="badge muted">view</span>'));
  const rows = d.rows.map(r => {
    if (r.error) {
      return `<tr><td class="who">${esc(r.employee.short_name)}<small>${esc(r.employee.group)}</small></td>
        <td colspan="${d.days.length + d.tariffs.length + 3}" style="color:var(--danger)">${esc(r.error)}</td><td>${state_(r)}</td></tr>`;
    }
    const flagsByDay = {};
    (r.flags || []).forEach(f => { (flagsByDay[f.day] = flagsByDay[f.day] || []).push(f); });
    return `<tr data-emp="${r.employee.id}" class="v4-click">
      <td class="who">${esc(r.employee.short_name)}<small>${esc(r.employee.group)}</small></td>
      ${d.days.map(day => {
        const card = r.cards.find(c => c.day === day);
        const fl = flagsByDay[day] || [];
        const debt = card && card.debt ? `<span class="v4-debt" title="Недостача дня">−${hours(card.debt)}</span>` : '';
        const flag = fl.length ? `<span class="v4-flag ${V4_FLAG_CLASS[fl[0].severity] || ''}" title="${esc(fl.map(f => f.text).join('\n'))}">●</span>` : '';
        const future = day > todayISO() ? ' future' : '';
        return `<td class="v4-ut${future}" title="${card ? esc(card.value) + (future ? ' · прогноз: недостача = план, если сотрудник не придёт' : '') : ''}">${mgmtCell(r.ut[day])}${debt}${flag}</td>`;
      }).join('')}
      ${d.tariffs.map(t => `<td class="num">${v4Hours(r.totals[t])}</td>`).join('')}
      <td class="num" title="Общий долг / остаток после погашения">${hours(r.debt.total)}${d.mode === 'close' ? ` / ${hours(r.debt.residual)}` : ''}</td>
      <td class="num"><b style="color:${r.bank.closed < 0 ? 'var(--danger)' : 'inherit'}">${r.bank.closed >= 0 ? '+' : ''}${hours(r.bank.closed)}</b></td>
      <td class="num">${r.deferred.length ? `<span class="badge warn" title="Отложено на следующий период">${r.deferred.length}</span>` : ''}</td>
      <td>${state_(r)}</td></tr>`;
  }).join('');
  $('#ut-body').innerHTML = `
    <div class="panel" style="padding:12px 16px"><span class="hint" style="margin:0">${esc(modeNote)}</span></div>
    <div class="table-wrap v4-grid-wrap"><table class="data v4-grid">
      <thead><tr><th class="who">Сотрудник</th>${d.days.map(v4DayHead).join('')}
        ${d.tariffs.map(t => `<th>${esc(t)}</th>`).join('')}<th>Недостача</th><th>Банк</th><th title="Отложенные блоки">→</th><th>Статус</th></tr></thead>
      <tbody>${rows || `<tr><td class="empty" colspan="99">Нет сотрудников</td></tr>`}</tbody>
    </table></div>
    <p class="hint">Шаг расчёта ${d.step_minutes} мин · версии настроек: ${d.settings_versions.map(esc).join(', ')}.
      Клик по строке — карточки дней, флаги, изъятия и трасса расчёта.</p>`;
  $$('#ut-body tr[data-emp]').forEach(tr => tr.onclick = () => mgmtDetail(+tr.dataset.emp));
}

async function mgmtAction(kind, empId) {
  const d = state.mgmt;
  const title = kind === 'close' ? 'Закрыть период?' : 'Пересчитать закрытый период?';
  const text = kind === 'close'
    ? `${MONTHS[d.month - 1]} ${d.year}: недостача будет погашена банком и кодами, результат, банк и отложенные блоки сохранятся. ` +
      'Повторно закрыть нельзя; исправить можно только пересчётом последнего закрытого периода.'
    : 'Расчёт повторится с исходных входящих остатков периода; результат, банк и переносы в следующий период будут заменены. ' +
      'Доступно только для последнего закрытого периода.';
  confirmDialog(title, text, async () => {
    try {
      const body = { year: d.year, month: d.month };
      if (empId) body.employee_ids = [empId];
      const r = await api(`/api/mgmt/${kind}`, { method: 'POST', body });
      closeModal();
      const msg = kind === 'close' ? `Закрыто: ${r.done.length}` : `Пересчитано: ${r.done.length}`;
      toast(msg + (r.errors.length ? `, ошибок: ${r.errors.length}` : ''), r.errors.length ? 'warn' : 'ok',
            r.errors.map(e => `${e.name}: ${e.error}`).slice(0, 8));
      loadMgmt();
    } catch (e) { toast(e.message, 'err'); }
  }, kind === 'close' ? 'Закрыть' : 'Пересчитать', false);
}

async function mgmtDetail(empId) {
  const d = state.mgmt;
  let r;
  try { r = await api(`/api/mgmt/employee/${empId}?year=${d.year}&month=${d.month}&mode=${d.mode}`); } catch (e) { toast(e.message, 'err'); return; }
  if (r.error) { toast(r.error, 'err'); return; }
  const flags = {};
  r.flags.forEach(f => { (flags[f.day] = flags[f.day] || []).push(f); });
  const cards = r.cards.map(c => `<tr>
    <td>${dateRu(c.day).slice(0, 5)}</td><td>${esc(c.value)}${c.plan_equals_fact ? ' <span class="badge info">План=Факт</span>' : ''}</td>
    <td class="num">${v4Hours(c.plan)}</td><td class="num">${v4Hours(c.fact)}</td><td class="num">${v4Hours(c.work)}</td>
    <td class="num">${v4Hours(c.ot)}</td><td class="num" style="color:var(--danger)">${c.debt ? hours(c.debt) : ''}</td>
    <td>${mgmtCell(c.codes)}${!c.pays_overtime && c.ot ? ' <span class="badge muted">в банк</span>' : ''}</td>
    <td>${mgmtCell(r.ut[c.day])}</td>
    <td>${(flags[c.day] || []).map(f => `<div class="v4-flagtext ${V4_FLAG_CLASS[f.severity] || ''}">● ${esc(f.text)}</div>`).join('')}</td></tr>`).join('');
  const b = r.bank;
  const canRecalc = d.can_recalculate && r.closed && !r.next_closed;
  const canClose = d.can_close && d.complete && !r.closed;
  openModal({
    title: `${r.employee.full_name}`,
    subtitle: `${MONTHS[d.month - 1]} ${d.year} · ${r.closed ? 'период закрыт' : (d.mode === 'close' ? 'предпросмотр закрытия' : 'просмотр (view)')}`,
    wide: true,
    body: `
      <div class="stat-grid">
        <div class="stat"><div class="k">План / факт</div><div class="v">${hours(r.plan_total)} / ${hours(r.fact_total)}</div></div>
        <div class="stat warn"><div class="k">Недостача (всего)</div><div class="v">${hours(r.debt.total)}</div></div>
        <div class="stat"><div class="k">Погашено банком / кодами</div><div class="v">${hours(b.paid)} / ${hours(r.debt.cut)}</div></div>
        <div class="stat accent"><div class="k">Банк на закрытие</div><div class="v">${b.closed >= 0 ? '+' : ''}${hours(b.closed)}</div></div>
      </div>
      <p class="hint" style="margin-top:-6px">Банк: входящий ${hours(b.open)}${b.open_normalized !== b.open ? ` (нормализован ${hours(b.open_normalized)})` : ''}
        + корректировки ${hours(b.adjustments)} + зачислено неоплачиваемых ${hours(b.credited)}.
        ${r.open_session_since ? ' <b style="color:var(--danger)">Смена не закрыта (нет «Ушёл»).</b>' : ''}</p>
      <div class="table-wrap" style="max-height:46vh"><table class="data">
        <thead><tr><th>День</th><th>Табель</th><th>План</th><th>Факт</th><th>Рабочее</th><th>Перераб.</th><th>Недост.</th>
          <th>Коды дня</th><th>Итог УТ</th><th>Флаги</th></tr></thead><tbody>${cards}</tbody></table></div>
      ${r.deferred.length ? `<div class="panel" style="margin-top:12px"><h3 class="panel-title">Отложено на следующий период</h3>
        ${r.deferred.map(x => `<span class="badge warn">${esc(x.tariff)} ${hours(x.hours)} ч из ${dateRu(x.source_day)}</span>`).join(' ')}</div>` : ''}
      ${r.cuts && r.cuts.length ? `<div class="panel" style="margin-top:12px"><h3 class="panel-title">Изъятия каскадом</h3>
        ${r.cuts.map(c => `<div>${esc(c.tariff)} ${hours(c.taken_hours)} ч (${dateRu(c.source_day)}${c.placed_day ? ' → ' + dateRu(c.placed_day) : ''}) — погашено ${hours(c.paid_hours)} ч</div>`).join('')}</div>` : ''}
      ${r.exceptions.length ? `<div class="panel" style="margin-top:12px"><h3 class="panel-title">Исключения</h3>${r.exceptions.map(x => `<div>${esc(x)}</div>`).join('')}</div>` : ''}
      <details style="margin-top:12px"><summary>Трасса расчёта (${r.trace.length})</summary>
        ${r.trace.map(t => `<div class="audit-item"><span class="ac">${esc(t.code)}</span> ${esc(t.text)}</div>`).join('') || '<div class="empty">Пусто</div>'}</details>`,
    footer: `${canClose ? '<button class="btn btn-primary" data-close>Закрыть период сотрудника</button>' : ''}
      ${canRecalc ? '<button class="btn" data-recalc>Пересчитать</button>' : ''}
      <button class="btn btn-ghost" data-cancel>Закрыть окно</button>`,
    onMount(m) {
      m.classList.add('v4-xl');
      m.querySelector('[data-cancel]').onclick = closeModal;
      const c = m.querySelector('[data-close]'); if (c) c.onclick = () => mgmtAction('close', empId);
      const rc = m.querySelector('[data-recalc]'); if (rc) rc.onclick = () => mgmtAction('recalculate', empId);
    },
  });
}

/* ══════════════════════════════════════════════════════════════════
   ПРАВА ДОСТУПА — роли (базовые группы), группы доступа, индивидуальные права
   ══════════════════════════════════════════════════════════════════ */
state.accessTab = state.accessTab || 'roles';

async function loadAccess() {
  const host = $('#view-access');
  host.innerHTML = `
    <div class="page-head">
      <div><h2>Права доступа</h2><div class="sub">Итоговое право = права роли → группы (запрет сильнее разрешения) →
        индивидуальные права пользователя (решают окончательно)</div></div>
      <div class="spacer"></div>
      <div class="seg" id="ac-tabs">
        <button data-t="roles">Роли</button><button data-t="groups">Группы</button><button data-t="users">Пользователи</button>
      </div>
    </div>
    <div id="ac-body"><div class="empty">Загрузка…</div></div>`;
  $$('#ac-tabs button').forEach(b => {
    b.classList.toggle('active', b.dataset.t === state.accessTab);
    b.onclick = () => { state.accessTab = b.dataset.t; loadAccess(); };
  });
  try { state.access = await api('/api/access'); } catch (e) {
    $('#ac-body').innerHTML = `<div class="panel"><div class="empty">${esc(e.message)}</div></div>`; return;
  }
  ({ roles: renderAccessRoles, groups: renderAccessGroups, users: renderAccessUsers })[state.accessTab]();
}

function accessMatrix(grants, baseline, idPrefix) {
  /* grants — {perm: allow|deny}; baseline — множество прав «по умолчанию» (для подсказки) */
  const sections = {};
  state.access.permissions.forEach(p => { (sections[p.section] = sections[p.section] || []).push(p); });
  return Object.entries(sections).map(([sec, perms]) => `
    <div class="v4-perm-sec"><div class="lbl">${esc(sec)}</div>
      ${perms.map(p => {
        const v = grants[p.key] || 'default';
        const base = baseline ? (baseline.has(p.key) ? '✓' : '✗') : '—';
        return `<div class="v4-perm-row"><span>${esc(p.title)} <code>${esc(p.key)}</code></span>
          <select data-perm="${p.key}" id="${idPrefix}-${p.key.replace('.', '_')}">
            <option value="default" ${v === 'default' ? 'selected' : ''}>по умолчанию (${base})</option>
            <option value="allow" ${v === 'allow' ? 'selected' : ''}>разрешить</option>
            <option value="deny" ${v === 'deny' ? 'selected' : ''}>запретить</option>
          </select></div>`;
      }).join('')}</div>`).join('');
}
function collectMatrix(root) {
  const out = {};
  $$('select[data-perm]', root).forEach(s => { if (s.value !== 'default') out[s.dataset.perm] = s.value; });
  return out;
}

function renderAccessRoles() {
  const a = state.access;
  $('#ac-body').innerHTML = a.roles.map(r => `
    <div class="panel"><h3 class="panel-title">${esc(r.title)} · ${r.effective.length} из ${a.permissions.length}</h3>
      <div class="v4-chips">${a.permissions.map(p => `<span class="badge ${r.effective.includes(p.key) ? 'ok' : 'muted'}">${esc(p.title)}</span>`).join(' ')}</div>
      <button class="btn btn-sm" data-role="${r.role}" style="margin-top:10px">Изменить права роли</button></div>`).join('')
    + '<p class="hint">Права роли — базовые для всех пользователей с этой ролью. Изменения применяются сразу.</p>';
  $$('#ac-body [data-role]').forEach(b => b.onclick = () => {
    const r = a.roles.find(x => x.role === b.dataset.role);
    openModal({
      title: `Права роли «${r.title}»`, wide: true,
      body: accessMatrix(r.overrides, new Set(r.defaults), 'ar'),
      footer: `<button class="btn btn-ghost" data-cancel>Отмена</button><button class="btn btn-primary" data-save>Сохранить</button>`,
      onMount(m) {
        m.querySelector('[data-cancel]').onclick = closeModal;
        m.querySelector('[data-save]').onclick = async () => {
          try { await api(`/api/access/roles/${r.role}`, { method: 'PUT', body: { grants: collectMatrix(m) } });
            closeModal(); toast('Права роли сохранены', 'ok'); loadAccess(); } catch (e) { toast(e.message, 'err'); }
        };
      },
    });
  });
}

function renderAccessGroups() {
  const a = state.access;
  const userName = id => (a.users.find(u => u.id === id) || {}).name || id;
  $('#ac-body').innerHTML = `
    <div class="panel"><div style="display:flex;gap:8px;flex-wrap:wrap;align-items:end">
      <label class="field" style="margin:0;flex:1;min-width:200px"><span>Новая группа</span><input type="text" id="ag-name" placeholder="Например: Табельщики"></label>
      <label class="field" style="margin:0;flex:2;min-width:200px"><span>Описание</span><input type="text" id="ag-desc"></label>
      <button class="btn btn-primary" id="ag-add">Создать</button></div></div>
    ${a.groups.map(g => `<div class="panel">
      <h3 class="panel-title">${esc(g.name)} · участников ${g.members.length}</h3>
      ${g.description ? `<p class="hint" style="margin-top:-6px">${esc(g.description)}</p>` : ''}
      <div class="v4-chips">${Object.entries(g.grants).map(([k, v]) => `<span class="badge ${v === 'allow' ? 'ok' : 'danger'}">${v === 'allow' ? '+' : '−'} ${esc((a.permissions.find(p => p.key === k) || {}).title || k)}</span>`).join(' ') || '<span class="hint">прав не задано</span>'}</div>
      <div class="v4-chips" style="margin-top:6px">${g.members.map(id => `<span class="badge muted">${esc(userName(id))}</span>`).join(' ')}</div>
      <div style="display:flex;gap:8px;margin-top:10px">
        <button class="btn btn-sm" data-g-grants="${g.id}">Права группы</button>
        <button class="btn btn-sm" data-g-members="${g.id}">Состав</button>
        <button class="btn btn-sm btn-ghost" data-g-del="${g.id}" style="color:var(--danger)">Удалить</button></div></div>`).join('')
      || '<div class="panel"><div class="empty">Групп пока нет. Группа добавляет (или запрещает) права всем своим участникам.</div></div>'}`;
  $('#ag-add').onclick = async () => {
    try { await api('/api/access/groups', { method: 'POST', body: { name: $('#ag-name').value, description: $('#ag-desc').value } });
      toast('Группа создана', 'ok'); loadAccess(); } catch (e) { toast(e.message, 'err'); }
  };
  $$('[data-g-grants]').forEach(b => b.onclick = () => {
    const g = a.groups.find(x => x.id === +b.dataset.gGrants);
    openModal({ title: `Права группы «${g.name}»`, wide: true, body: accessMatrix(g.grants, null, 'ag'),
      footer: `<button class="btn btn-ghost" data-cancel>Отмена</button><button class="btn btn-primary" data-save>Сохранить</button>`,
      onMount(m) {
        m.querySelector('[data-cancel]').onclick = closeModal;
        m.querySelector('[data-save]').onclick = async () => {
          try { await api(`/api/access/groups/${g.id}/grants`, { method: 'PUT', body: { grants: collectMatrix(m) } });
            closeModal(); toast('Права группы сохранены', 'ok'); loadAccess(); } catch (e) { toast(e.message, 'err'); }
        };
      } });
  });
  $$('[data-g-members]').forEach(b => b.onclick = () => {
    const g = a.groups.find(x => x.id === +b.dataset.gMembers);
    openModal({ title: `Состав группы «${g.name}»`,
      body: `<input type="text" id="agm-q" placeholder="Поиск" style="width:100%;margin-bottom:8px">
        <div style="max-height:50vh;overflow:auto">${a.users.map(u => `<label class="v4-user-check" data-n="${esc((u.name + ' ' + u.username).toLowerCase())}">
          <input type="checkbox" value="${u.id}" ${g.members.includes(u.id) ? 'checked' : ''}> ${esc(u.name)} <small>${esc(u.username)} · ${esc(ROLE_TITLES[u.role] || u.role)}</small></label>`).join('')}</div>`,
      footer: `<button class="btn btn-ghost" data-cancel>Отмена</button><button class="btn btn-primary" data-save>Сохранить</button>`,
      onMount(m) {
        $('#agm-q').oninput = e => $$('.v4-user-check', m).forEach(l => { l.style.display = l.dataset.n.includes(e.target.value.toLowerCase()) ? '' : 'none'; });
        m.querySelector('[data-cancel]').onclick = closeModal;
        m.querySelector('[data-save]').onclick = async () => {
          const ids = $$('.v4-user-check input:checked', m).map(i => +i.value);
          try { await api(`/api/access/groups/${g.id}/members`, { method: 'PUT', body: { user_ids: ids } });
            closeModal(); toast('Состав сохранён', 'ok'); loadAccess(); } catch (e) { toast(e.message, 'err'); }
        };
      } });
  });
  $$('[data-g-del]').forEach(b => b.onclick = () => confirmDialog('Удалить группу?', 'Права группы перестанут действовать для её участников.',
    async () => { try { await api(`/api/access/groups/${b.dataset.gDel}`, { method: 'DELETE' }); closeModal(); loadAccess(); } catch (e) { toast(e.message, 'err'); } }, 'Удалить'));
}

function renderAccessUsers() {
  const a = state.access;
  const gname = id => (a.groups.find(g => g.id === id) || {}).name || id;
  $('#ac-body').innerHTML = `<div class="panel"><input type="text" id="au-q" placeholder="Поиск по имени или логину" style="width:100%;max-width:360px"></div>
    <div class="table-wrap"><table class="data responsive"><thead><tr><th>Пользователь</th><th>Роль</th><th>Группы</th>
      <th>Индивидуально</th><th>Итого прав</th><th></th></tr></thead><tbody>
    ${a.users.map(u => `<tr data-n="${esc((u.name + ' ' + u.username).toLowerCase())}">
      <td class="who" data-label="Пользователь">${esc(u.name)}<small>${esc(u.username)}${u.active ? '' : ' · отключён'}</small></td>
      <td data-label="Роль">${esc(ROLE_TITLES[u.role] || u.role)}</td>
      <td data-label="Группы">${u.groups.map(g => `<span class="badge muted">${esc(gname(g))}</span>`).join(' ')}</td>
      <td data-label="Индивидуально">${Object.entries(u.grants).map(([k, v]) => `<span class="badge ${v === 'allow' ? 'ok' : 'danger'}">${v === 'allow' ? '+' : '−'} ${esc(k)}</span>`).join(' ')}</td>
      <td class="num" data-label="Итого">${u.effective.length}</td>
      <td><button class="btn btn-sm" data-u="${u.id}">Права</button></td></tr>`).join('')}</tbody></table></div>`;
  $('#au-q').oninput = e => $$('#ac-body tr[data-n]').forEach(tr => { tr.style.display = tr.dataset.n.includes(e.target.value.toLowerCase()) ? '' : 'none'; });
  $$('[data-u]').forEach(b => b.onclick = () => {
    const u = a.users.find(x => x.id === +b.dataset.u);
    openModal({ title: `Индивидуальные права · ${u.name}`, subtitle: `Сейчас действует: ${u.effective.length} прав`, wide: true,
      body: accessMatrix(u.grants, new Set(u.effective), 'au') + '<p class="hint">«По умолчанию» — как получается из роли и групп (в скобках — текущее итоговое значение).</p>',
      footer: `<button class="btn btn-ghost" data-cancel>Отмена</button><button class="btn btn-primary" data-save>Сохранить</button>`,
      onMount(m) {
        m.querySelector('[data-cancel]').onclick = closeModal;
        m.querySelector('[data-save]').onclick = async () => {
          try { await api(`/api/access/users/${u.id}/grants`, { method: 'PUT', body: { grants: collectMatrix(m) } });
            closeModal(); toast('Права пользователя сохранены', 'ok'); loadAccess(); } catch (e) { toast(e.message, 'err'); }
        };
      } });
  });
}

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

/* ══════════════════════════════════════════════════════════════════
   СПРАВОЧНИКИ ДВИЖКА (в разделе «Настройки»): Т1–Т7, Т9, Т-Группы + модификаторы Т4
   ══════════════════════════════════════════════════════════════════ */
async function renderEngineSettings(host) {
  if (!host) return;
  let data, mods;
  try {
    [data, mods] = await Promise.all([api('/api/engine-settings'),
      api(`/api/engine-settings/modifiers?year=${state.year}&month=${state.month}`)]);
  } catch (e) { host.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  const p = data.active.payload;
  const edit = can('settings.edit');
  const first = `${state.year}-${String(state.month).padStart(2, '0')}-01`;
  const empName = id => (state.employees.find(e => e.id === id) || {}).short_name || `#${id}`;
  host.innerHTML = `
    <h3 class="panel-title">Справочники движка (Т1–Т7, Т9, Т-Группы)</h3>
    <div class="stat-grid">
      <div class="stat"><div class="k">Шаг расчёта</div><div class="v">${p.step_minutes} мин</div></div>
      <div class="stat"><div class="k">Лимит опоздания</div><div class="v">${p.late_limit_minutes} мин</div></div>
      <div class="stat"><div class="k">Лимит дня</div><div class="v">${p.day_limit_minutes / 60} ч</div></div>
      <div class="stat"><div class="k">Действует с</div><div class="v" style="font-size:16px">${data.active.valid_from ? dateRu(data.active.valid_from) : 'по умолчанию'}</div></div>
    </div>
    <p class="hint" style="margin-top:-6px">Каскад (Т6): банк → ${p.cascade_order.map(esc).join(' → ')}. Порядок размещения (Т9): ${p.placement_order.map(esc).join(' → ')}.
      Окна Т2: ${p.windows.map(w => `${esc(w.code)} ${w.hours} = ${w.segments.map(s => s.join('–')).join(' + ')}`).join('; ')}.</p>
    <details><summary>Редактировать справочники (JSON)</summary>
      <textarea id="es-json" style="width:100%;min-height:320px;font-family:monospace;font-size:12px" ${edit ? '' : 'readonly'}>${esc(JSON.stringify(p, null, 2))}</textarea>
      ${edit ? `<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:end;margin-top:8px">
        <label class="field" style="margin:0"><span>Действует с (1-е число)</span><input type="date" id="es-from" value="${first}"></label>
        <label class="field" style="margin:0;flex:1"><span>Комментарий</span><input type="text" id="es-note" placeholder="что и почему меняем"></label>
        <button class="btn btn-primary" id="es-save">Сохранить новую версию</button></div>
        <p class="hint">Перед сохранением конфигурация проверяется правилами В1–В11, В-Гр; все нарушения выводятся разом.
          Шаг меняется только с начала периода. Закрытые периоды не пересчитываются автоматически.</p>` : ''}
    </details>
    <details style="margin-top:8px"><summary>История версий (${data.versions.length})</summary>
      ${data.versions.map(v => `<div class="audit-item"><span class="ts">${dateRu(v.valid_from)}</span><span class="ac">#${v.id}</span>
        <span style="color:var(--muted)">${esc(v.created_by)} · ${esc(v.note)}</span></div>`).join('')}</details>
    <h3 class="panel-title" style="margin-top:16px">Модификаторы дня (Т4) · ${MONTHS[state.month - 1]} ${state.year}</h3>
    <p class="hint" style="margin-top:-6px">Дни двойной оплаты и ВИП-гости из блока ниже тоже действуют как «Двойные переработки».
      Приоритет: сотрудник+день → сотрудник+период → группа+день → группа+период → все+день → все+период.</p>
    <div class="table-wrap"><table class="data"><thead><tr><th>Модификатор</th><th>Значение</th><th>Кому</th><th>Когда</th><th>Комментарий</th><th></th></tr></thead><tbody>
      ${mods.map(m => `<tr><td>${esc(m.title)}</td><td>${m.value === '1' ? 'Да' : (m.value === '0' ? 'Нет' : 'Авто')}</td>
        <td>${m.employee_id ? esc(empName(m.employee_id)) : (m.group ? 'группа «' + esc(m.group) + '»' : 'все')}</td>
        <td>${m.date ? dateRu(m.date) : 'весь месяц'}</td><td>${esc(m.note)}</td>
        <td>${edit ? `<button class="btn btn-sm btn-ghost" data-mod-del="${m.id}">✕</button>` : ''}</td></tr>`).join('') || '<tr><td colspan="6" class="empty">Нет модификаторов в этом месяце</td></tr>'}
    </tbody></table></div>
    ${edit ? `<div class="v4-filters" style="margin-top:8px">
      <label class="field"><span>Модификатор</span><select id="md-name">${data.modifier_names.map(n => `<option value="${n.name}">${esc(n.title)}</option>`).join('')}</select></label>
      <label class="field"><span>Значение</span><select id="md-value"><option value="1">Да</option><option value="0">Нет</option><option value="auto">Авто (План=Факт)</option></select></label>
      <label class="field"><span>Кому</span><select id="md-scope"><option value="all">все</option>
        ${(p.groups || []).map(g => `<option value="g:${esc(g.name)}">группа «${esc(g.name)}»</option>`).join('')}
        ${state.employees.map(e => `<option value="e:${e.id}">${esc(e.short_name)}</option>`).join('')}</select></label>
      <label class="field"><span>День (пусто — весь месяц)</span><input type="date" id="md-date"></label>
      <label class="field"><span>Комментарий</span><input type="text" id="md-note"></label>
      <button class="btn" id="md-add">Добавить</button></div>` : ''}`;
  if (edit) {
    $('#es-save').onclick = async () => {
      let payload;
      try { payload = JSON.parse($('#es-json').value); } catch (e) { toast('JSON с ошибкой: ' + e.message, 'err'); return; }
      try { await api('/api/engine-settings', { method: 'PUT', body: { valid_from: $('#es-from').value, payload, note: $('#es-note').value } });
        toast('Новая версия справочников сохранена', 'ok'); renderEngineSettings(host); } catch (e) { toast(e.message, 'err'); }
    };
    $('#md-add').onclick = async () => {
      const scope = $('#md-scope').value, day = $('#md-date').value;
      const body = { name: $('#md-name').value, value: $('#md-value').value, note: $('#md-note').value,
        date: day || null, period_start: day ? null : first,
        employee_id: scope.startsWith('e:') ? +scope.slice(2) : null, group: scope.startsWith('g:') ? scope.slice(2) : '' };
      try { await api('/api/engine-settings/modifiers', { method: 'POST', body }); toast('Модификатор добавлен', 'ok'); renderEngineSettings(host); }
      catch (e) { toast(e.message, 'err'); }
    };
    $$('[data-mod-del]', host).forEach(b => b.onclick = async () => {
      try { await api(`/api/engine-settings/modifiers/${b.dataset.modDel}`, { method: 'DELETE' }); renderEngineSettings(host); }
      catch (e) { toast(e.message, 'err'); }
    });
  }
}
