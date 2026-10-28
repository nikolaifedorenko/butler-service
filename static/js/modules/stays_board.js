/* ══════════════════════════════════════════════════════════════════════
   «ШАХМАТКА» — шахматка батлеров (§6.2) и табло дня (§6.3).
   Фон дня батлера — смена по Графику; красное — перегруз, «вне смены», подмена.
   Табло — заезды / выезды / проживают / требуют внимания и «не заехали»;
   на телефоне — одной колонкой. Предупреждения сервер считает при каждом чтении.
   Использует хелперы app.js: $ $$ esc api openModal closeModal toast can dateRu.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

const STAYS_DUTY = { shift: 'на смене', off: 'выходной', absent: 'отсутствие' };
const STAYS_WARN = { off_shift: 'вне смены', overload: 'перегруз', need_replacement: 'нужна подмена',
  hole: 'гости без батлера', double_cover: 'два батлера у гостя' };
const boardState = { first: null, days: 7, day: null, tab: 'arrivals', esc: false, vip: false, q: '' };

/* ─────────────── Шахматка батлеров ─────────────── */
async function renderButlersBoard(body) {
  if (!boardState.first) boardState.first = staysToday();
  const last = staysAddDays(boardState.first, boardState.days - 1);
  const fresh = loadGenerationFor(body);    // запоздавший ответ не перерисовывает (stays.js)
  const data = await api(`/api/stays/board/butlers?first=${boardState.first}&last=${last}`, { silent: true });
  if (!fresh()) return;
  body.innerHTML = `
    <div class="sb-toolbar">
      <input type="date" id="bb-first" value="${esc(boardState.first)}">
      <select id="bb-days">${[7, 14].map(n => `<option value="${n}"${n === boardState.days ? ' selected' : ''}>${n} дн.</option>`).join('')}</select>
      <span class="muted">лимит нагрузки — ${esc(String(data.limit))}</span>
    </div>
    <div class="sb-grid bb-grid" style="--days:${data.days.length}">
      <div class="bb-row sb-head"><div class="sb-unit">Батлер</div>${data.days.map(d => `<div>${esc(dateRu(d).slice(0, 5))}</div>`).join('')}</div>
      ${data.rows.map(r => `<div class="bb-row"><div class="sb-unit"><b>${esc(r.name)}</b>${r.escort ? '' : '<small>не в списке</small>'}</div>
        ${r.cells.map(c => `<div class="bb-cell duty-${c.duty}${c.warnings.length ? ' warn' : ''}" data-bb-emp="${r.employee_id}"
          data-day="${esc(c.day)}" data-warn="${esc(c.warnings.join(' '))}" title="${esc(STAYS_DUTY[c.duty] + (c.code ? ' · ' + c.code : ''))}">
          <div>${esc(c.units.map(u => u.label).join(', ') || (c.duty === 'shift' ? '—' : STAYS_DUTY[c.duty]))}</div>
          ${c.load ? `<small>${esc(String(c.load))}/${esc(String(data.limit))}</small>` : ''}
          ${c.warnings.length ? `<small class="bb-w">${esc(c.warnings.map(w => STAYS_WARN[w] || w).join(', '))}</small>` : ''}
        </div>`).join('')}</div>`).join('') || '<div class="empty">Список «Сопровождают гостей» пуст — Настройки → Сопровождение</div>'}
    </div>`;
  const rerender = () => renderButlersBoard(body);
  $('#bb-first', body).onchange = e => { boardState.first = e.target.value || staysToday(); rerender(); };
  $('#bb-days', body).onchange = e => { boardState.days = Number(e.target.value); rerender(); };
  $$('[data-bb-emp]', body).forEach(cell => {
    const row = data.rows.find(r => r.employee_id === Number(cell.dataset.bbEmp));
    cell.onclick = () => openButlerDay(row, row.cells.find(c => c.day === cell.dataset.day), rerender);
  });
}

async function openButlerDay(row, cell, onChanged) {
  const assign = can('stays.assign');
  const offShift = cell.warnings.includes('off_shift') && assign;
  const kinds = offShift ? (await api('/api/shift-types', { silent: true })).filter(t => t.kind === 'work' && t.active) : [];
  openModal({
    title: `${row.name} · ${dateRu(cell.day)}`, subtitle: `${STAYS_DUTY[cell.duty]}${cell.code ? ' · ' + cell.code : ''} · нагрузка ${cell.load}`,
    body: `${cell.units.map(u => `<div class="sb-line"><b>${esc(u.label)}</b>
        <button class="btn btn-sm btn-ghost" data-open-res="${u.reservation_id}">Бронь…</button>
        ${assign && cell.warnings.includes('need_replacement') ? `<button class="btn btn-sm" data-replace-res="${u.reservation_id}">Заменить</button>` : ''}</div>`).join('') || '<p class="muted">Гостей не ведёт</p>'}
      ${cell.guests.length ? `<p>${esc(cell.guests.join(', '))}</p>` : ''}
      ${cell.warnings.length ? `<div class="dict-banner gold"><span>⚠</span><span>${esc(cell.warnings.map(w => STAYS_WARN[w] || w).join(', '))}</span></div>` : ''}
      ${offShift ? `${sfRow('Смена Графика', `<select id="bb-shift-type">${kinds.map(k =>
        `<option value="${k.id}">${esc(k.name)} ${esc(k.start_time)}–${esc(k.end_time)}</option>`).join('')}</select>`)}
        <p class="hint">Добавится ручная смена в График (нужно право на правку Графика); Табель не меняется.</p>` : ''}
      <div id="bb-assign-box"></div>`,
    footer: `<button class="btn btn-ghost" data-close>Закрыть</button>
      ${assign && row.escort ? '<button class="btn" id="bb-assign">Назначить на этот день</button>' : ''}
      ${offShift && kinds.length ? '<button class="btn btn-primary" id="bb-add-shift">Добавить смену в График</button>' : ''}`,
    onMount(m) {
      $('[data-close]', m).onclick = closeModal;
      $$('[data-open-res]', m).forEach(b => { b.onclick = () => openReservationCard(Number(b.dataset.openRes), onChanged); });
      $$('[data-replace-res]', m).forEach(btn => { btn.onclick = () => openReplace(Number(btn.dataset.replaceRes), cell.day, onChanged); });
      const assignBtn = $('#bb-assign', m);
      if (assignBtn) assignBtn.onclick = async () => {
        /* брони дня, где гостей ещё никто не ведёт, — табло дня уже знает их статус */
        const day = await api('/api/stays/day?date=' + cell.day, { silent: true });
        const open = day.in_house.filter(x => x.cover_status === 'uncovered' || x.cover_status === 'replacement');
        $('#bb-assign-box', m).innerHTML = open.length ? `${sfRow('Бронь без батлера', `<select id="bb-res">${open.map(x =>
          `<option value="${x.reservation_id}">${esc(x.unit)} · ${esc(x.guests.map(g => g.name).join(', '))}</option>`).join('')}</select>`)}
          <button class="btn btn-primary" id="bb-assign-save">Назначить ${esc(row.name)}</button>` : '<p class="muted">Все гости дня уже с батлерами</p>';
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
    body: got.map(c => `<div class="sb-line"><b>${esc(c.name)}</b>
      <span class="muted">${c.knows_guest ? 'знает гостя · ' : ''}нагрузка ${esc(String(c.load_after))}${c.note ? ' · ' + esc(c.note) : ''}</span>
      <button class="btn btn-sm btn-primary" data-pick="${c.employee_id}">Назначить</button></div>`).join('')
      || '<p class="muted">Свободных на смене в пределах лимита нет</p>',
    footer: '<button class="btn btn-ghost" data-close>Закрыть</button>',
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
const DAY_TABS = [['arrivals', 'Заезды'], ['departures', 'Выезды'], ['in_house', 'Проживают'], ['attention', 'Требуют внимания']];

function dayStatusHtml(r) {
  switch (r.cover_status) {
    case 'covered': return `<span class="badge ok">${esc(r.covered.map(c => c.name + (c.guests.length ? ' — ' + c.guests.join(', ') : '')).join('; '))}</span>`;
    case 'uncovered': return `<span class="badge danger">⚠ не назначено</span>${r.candidates?.length ? ` <span class="muted">кандидаты: ${esc(r.candidates.map(c => c.name).join(', '))}</span>` : ''}`;
    case 'replacement': return `<span class="badge warn">↔ нужна подмена</span>${r.candidates?.length ? ` <span class="muted">кандидаты: ${esc(r.candidates.map(c => c.name).join(', '))}</span>` : ''}`;
    case 'declined': return '<span class="badge muted">гость отказался</span>';
    default: return '<span class="badge muted">не требуется</span>';
  }
}

function dayRowHtml(r, names) {
  const guests = names ? r.guests.map(g => `${g.level !== 'regular' ? esc(STAYS_LEVEL_MARK[g.level]) : ''}${esc(g.name)}`).join(', ')
    : `${r.guests_count} гост.`;
  const det = r.details ? [...r.details.logistics.map(l => `${l.time} ${l.description}`), ...r.details.companions.map(c => c.description),
    ...r.details.allergies.map(a => 'аллергия: ' + a), r.details.purpose].filter(Boolean).join(' · ') : '';
  return `<div class="db-row" data-db-row="${r.reservation_id}">
    <div class="db-time">${esc(r.time)}</div><div class="db-unit"><b>${esc(r.unit)}</b></div>
    <div class="db-guests">${guests}</div><div class="db-status">${names ? dayStatusHtml(r) : esc(STAYS_STATUS[r.status] || r.status)}</div>
    <div class="db-det muted">${esc(det)}</div></div>`;
}

async function renderDayBoard(body) {
  if (!boardState.day) boardState.day = staysToday();
  const q = new URLSearchParams({ date: boardState.day });
  if (boardState.esc) q.set('escorted_only', '1');
  if (boardState.vip) q.set('vip', '1');
  if (boardState.q.trim()) q.set('q', boardState.q.trim());
  const fresh = loadGenerationFor(body);
  const data = await api('/api/stays/day?' + q, { silent: true });
  if (!fresh()) return;
  const names = data.visibility !== 'occupancy';
  const t = data.totals;
  const tabs = DAY_TABS.filter(([id]) => names || id !== 'attention');
  const list = data[boardState.tab] || data.arrivals;
  body.innerHTML = `
    <div class="sb-toolbar">
      <button class="btn btn-sm" id="db-prev">◀</button><input type="date" id="db-date" value="${esc(boardState.day)}">
      <button class="btn btn-sm" id="db-next">▶</button><button class="btn btn-sm btn-ghost" id="db-today">Сегодня</button>
      ${names ? `<label class="chk"><input type="checkbox" id="db-esc"${boardState.esc ? ' checked' : ''}> только с сопровождением</label>
        <label class="chk"><input type="checkbox" id="db-vip"${boardState.vip ? ' checked' : ''}> VIP/VVIP</label>
        <input type="search" id="db-q" placeholder="фамилия, № брони, объект" value="${esc(boardState.q)}">` : ''}
    </div>
    <div class="db-sum">
      <div>▲ Заезды <b>${t.arrivals}</b></div><div>▼ Выезды <b>${t.departures}</b></div><div>🏠 Проживают <b>${t.in_house}</b></div>
      ${names ? `<div>🤵 Ведёт батлер <b>${t.covered}</b></div><div class="danger">⚠ Нужно, не назначено <b>${t.uncovered}</b></div>
        <div class="warn">↔ Нужна подмена <b>${t.need_replacement}</b></div><div>— Не требуется <b>${t.not_required}</b></div>
        <div>★ VIP ${t.vip} · VVIP ${t.vvip}</div>` : ''}
      <div>Не заехали <b>${t.no_show}</b></div>
    </div>
    <div class="layer-tabs">${tabs.map(([id, title]) => `<button class="btn btn-sm${boardState.tab === id ? ' btn-primary' : ''}" data-dtab="${id}">${esc(title)}
      ${(data[id] || []).length}</button>`).join('')}</div>
    <div class="db-list">${list.map(r => dayRowHtml(r, names)).join('') || '<div class="empty">Нет броней</div>'}</div>
    ${boardState.tab === 'arrivals' && data.no_show.length ? `<h4>Не заехали</h4>${data.no_show.map(r =>
      `<div class="db-row" data-db-row="${r.reservation_id}"><div class="db-unit">${esc(names ? r.number || '#' + r.reservation_id : 'бронь')}</div></div>`).join('')}` : ''}`;
  const rerender = () => renderDayBoard(body);
  const go = d => { boardState.day = d; rerender(); };
  $('#db-prev', body).onclick = () => go(staysAddDays(boardState.day, -1));
  $('#db-next', body).onclick = () => go(staysAddDays(boardState.day, 1));
  $('#db-today', body).onclick = () => go(staysToday());
  $('#db-date', body).onchange = e => go(e.target.value || staysToday());
  $$('[data-dtab]', body).forEach(b => { b.onclick = () => { boardState.tab = b.dataset.dtab; rerender(); }; });
  if (names) {
    $('#db-esc', body).onchange = e => { boardState.esc = e.target.checked; rerender(); };
    $('#db-vip', body).onchange = e => { boardState.vip = e.target.checked; rerender(); };
    let timer = null;
    $('#db-q', body).oninput = e => { clearTimeout(timer); timer = setTimeout(() => { boardState.q = e.target.value; rerender(); }, 350); };
    $$('[data-db-row]', body).forEach(el => { el.onclick = () => openReservationCard(Number(el.dataset.dbRow), rerender); });
  }
}

/* ─────────────── Сводная загрузка (§6.1) ─────────────── */
/* узлы дерева × дни, сверху «Итого по выбранному»; полная вкладка (8 строк узла, «% / штуки»,
   месяц) — задача 4.2 */
async function renderOccupancyGrid(body) {
  const fund = await staysFund();
  if (!boardState.first) boardState.first = staysToday();
  const last = staysAddDays(boardState.first, 13);
  const q = new URLSearchParams({ first: boardState.first, last });
  if (boardState.group_id) q.append('group_ids', boardState.group_id);
  const fresh = loadGenerationFor(body);
  const data = await api('/api/stays/occupancy?' + q, { silent: true });
  if (!fresh()) return;
  const roots = fund.groups.filter(g => g.parent_id == null);
  const heat = pct => pct == null ? '' : pct >= 1 ? 'heat3' : pct >= 0.8 ? 'heat2' : pct >= 0.5 ? 'heat1' : '';
  const row = (n, total) => `<div class="bb-row"><div class="sb-unit"><b>${esc(n.path[n.path.length - 1] || '')}</b>
      <small>${esc(n.path.slice(0, -1).join(' / '))}</small></div>
    ${n.days.map((x, i) => `<div class="oc-cell ${heat(x.pct)}"${!total && n.group_id != null ? ` data-oc-node="${n.group_id}"` : ''} data-day="${esc(data.days[i])}">
      <b>${x.living}/${x.total}</b><small>${x.arrivals ? '▲' + x.arrivals : ''} ${x.departures ? '▼' + x.departures : ''}${x.pct != null ? ' · ' + Math.round(x.pct * 100) + '%' : ''}</small>
    </div>`).join('')}</div>`;
  body.innerHTML = `
    <div class="sb-toolbar">
      <input type="date" id="oc-first" value="${esc(boardState.first)}">
      <select id="oc-group"><option value="">Весь фонд</option>${roots.map(g =>
        `<option value="${g.id}"${String(g.id) === String(boardState.group_id) ? ' selected' : ''}>${esc(g.title)}</option>`).join('')}</select>
      <span class="muted">проживают / всего · ▲ заезды · ▼ выезды · загрузка</span>
    </div>
    <div class="sb-grid bb-grid" style="--days:${data.days.length}">
      <div class="bb-row sb-head"><div class="sb-unit">Узел</div>${data.days.map(d => `<div>${esc(dateRu(d).slice(0, 5))}</div>`).join('')}</div>
      ${data.nodes.length ? row(data.total, true) + data.nodes.map(n => row(n, false)).join('') : '<div class="empty">Фонд пуст</div>'}
    </div>`;
  const rerender = () => renderOccupancyGrid(body);
  $('#oc-first', body).onchange = e => { boardState.first = e.target.value || staysToday(); rerender(); };
  $('#oc-group', body).onchange = e => { boardState.group_id = e.target.value; rerender(); };
  /* клик по ячейке узла — шахматка объектов этого узла с этого дня (§6.1) */
  $$('[data-oc-node]', body).forEach(el => {
    el.onclick = () => {
      staysState.filters.group_id = el.dataset.ocNode;
      staysState.first = el.dataset.day;
      staysState.tab = 'units';
      loadStays();
    };
  });
}

/* ─────────────── «Мои гости» (§6.6): батлер с телефона ─────────────── */
async function renderMine() {
  const host = $('#view-mystays');
  host.innerHTML = '<div class="page-head"><div><h2>Мои гости</h2><div class="sub">Сегодня и неделя вперёд, вчерашние — чтобы дописать</div></div></div><div id="mine-body" class="empty">Загрузка…</div>';
  let data;
  try { data = await api('/api/stays/mine', { silent: true }); } catch (e) {
    $('#mine-body', host).innerHTML = `<p class="muted">${esc(e.message)}</p>`;
    return;
  }
  const level = l => (l !== 'regular' ? esc(STAYS_LEVEL_MARK[l]) : '');
  $('#mine-body', host).className = '';
  $('#mine-body', host).innerHTML = data.reservations.map(r => `
    <div class="panel mine-card">
      <h3 class="panel-title">${esc(r.units.join(' → ') || 'без объекта')} · ${esc(dateRu(r.check_in))}–${esc(dateRu(r.check_out))}</h3>
      <div class="muted">веду: ${esc(r.days.map(d => dateRu(d).slice(0, 5)).join(', '))}</div>
      ${r.guests.map(g => `<div class="mine-guest"><b>${level(g.level)}${esc(g.name)}</b> <span class="muted">${esc(STAYS_ROLE[g.role])}${g.phone ? ' · ' + esc(g.phone) : ''}</span>
        ${Object.entries(g.preferences).filter(([, v]) => v).map(([k, v]) => `<div class="muted">${esc(k)}: ${esc(v)}</div>`).join('')}
        ${g.special_dates.map(s => `<div class="muted">🎉 ${esc(dateRu(s.date))} — ${esc(s.what)}</div>`).join('')}
        <button class="btn btn-sm btn-ghost" data-mine-guest="${g.guest_id}">Сведения о госте</button></div>`).join('')}
      ${r.logistics.map(l => `<div>🚗 ${esc(l.date ? dateRu(l.date).slice(0, 5) : '')} ${esc(l.time)} ${esc(l.description)}</div>`).join('')}
      ${r.note ? `<p>${esc(r.note)}</p>` : ''}
      <button class="btn btn-sm" data-mine-res="${r.reservation_id}">Дополнить бронь</button>
    </div>`).join('') || '<div class="empty">На сегодня и ближайшую неделю гостей нет</div>';
  $$('[data-mine-res]', host).forEach(b => { b.onclick = () => openReservationForm(Number(b.dataset.mineRes), { mine: true, onSaved: renderMine }); });
  $$('[data-mine-guest]', host).forEach(b => { b.onclick = () => openGuestForm(Number(b.dataset.mineGuest), renderMine, { mine: true }); });
}
