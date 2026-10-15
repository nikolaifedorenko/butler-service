/* ══════════════════════════════════════════════════════════════════════
   Движок v7.1: вкладки «Отметки» (доска 16.2), «Факт» (история сессий 16.4),
   «Табель» (16.5), «Управленческий табель» (16.6), «Права доступа»,
   «Журнал аудита», справочники движка (в Настройках).
   Зависит от core.js (api, state, $, esc, openModal, toast …) и app.js (can, poll).
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

/* Цвета кодов Табеля — только подстраховка: основной источник — блок presentation
   версии справочников (payload.day_code_policy[code].color), если он заполнен.
   Кодов «С» и «НВ» здесь нет: из справочника Табеля они исключены (норматив
   12.10.2026) — суточная смена это явка «Я 10,75» в дне-якоре, выходной за часы —
   отсутствие в Графике. */
const V4_CODE_COLORS = {
  'Я': '#34a862', 'К': '#2b8fb6', 'В': '#c3cdd9', 'ДО': '#d9822b',
  'ОТ': '#f0a500', 'ОВ': '#9b59b6', 'Б': '#e05d4b', 'НБ': '#c0504d',
  'НН': '#b03a48',
};
function v4CodeColor(code, fromPayload) {
  /* cssColor на выходе закрывает все стоки (пилюли, таймлайн, ячейки): цвета из
     payload настроек приходят из БД и не должны вырываться из style="…". */
  return cssColor((fromPayload && fromPayload[code]) || V4_CODE_COLORS[code]);
}
const V4_FLAG_CLASS = { LATE: 'warn', EARLY_DEPARTURE: 'warn', OFF_SHIFT_ATTENDANCE: 'info' };

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
function v4Contacts(e) {
  const tel = String(e.phone || '').trim();
  const tg = String(e.telegram || '').trim().replace(/^@+/, '');
  if (!tel && !tg) return '';
  return `<div class="contacts">${tel ? `<a href="tel:${esc(tel.replace(/[^0-9+]/g, ''))}">📞 ${esc(tel)}</a>` : ''}${
    tg ? `<a href="https://t.me/${esc(tg.replace(/[^A-Za-z0-9_]/g, ''))}" target="_blank" rel="noopener">✈️ @${esc(tg)}</a>` : ''}</div>`;
}

/* ══════════════════════════════════════════════════════════════════
   ОТМЕТКИ — доска «прямо сейчас» (16.2):
   (a) сколько на работе, (b) сколько ожидается по Графику,
   (c) карточки открытых сессий, (d) кто ещё должен прийти (ближайший подинтервал)
   ══════════════════════════════════════════════════════════════════ */
async function loadMarks() {
  const host = $('#view-marks');
  host.innerHTML = `
    <div class="page-head">
      <div><h2>Отметки</h2>
        <div class="sub">Кто сейчас на работе и кого ждём по Графику — по реальным отметкам.
          Обновляется каждые 30 секунд. Забытый уход виден как есть: счётчик растёт</div></div>
      <div class="spacer"></div>
      <span class="badge ok" id="mk-now" style="font-size:13px;padding:7px 12px">—</span>
      <button class="btn btn-sm" id="mk-refresh">Обновить</button>
    </div>
    <div id="mk-body"><div class="empty">Загрузка…</div></div>`;
  $('#mk-refresh').onclick = () => fetchMarks();
  await fetchMarks();
  poll('marks', () => fetchMarks(true));
}

async function fetchMarks(silent) {
  let d;
  try { d = await api('/api/presence/board', { silent: !!silent }); } catch (e) {
    const b = $('#mk-body');
    if (b) b.innerHTML = `<div class="panel"><div class="empty">${esc(e.message || e)}</div></div>`;
    return;
  }
  const body = $('#mk-body');
  if (!body) return;
  const nowEl = $('#mk-now');
  if (nowEl) nowEl.textContent = `Сейчас ${d.now.slice(11, 16)}`;
  const card = c => {
    const e = c.employee || {};
    const shiftToday = (c.shift_today || []).map(([a, b]) =>
      `${a.slice(11, 16)}–${b.slice(11, 16)}`).join(', ');
    return `<div class="presence-card">
      <div class="nm"><span class="pulse"></span>${esc(e.short_name || c.employee_id)}</div>
      <div class="pos">${esc(e.position || '—')}${e.group ? ' · ' + esc(e.group) : ''}</div>
      ${v4Contacts(e)}
      <div class="row"><span style="color:var(--muted)">На работе с</span><b>${esc(c.open_since_hm)}</b></div>
      <div class="row"><span style="color:var(--muted)">Уже работает</span><b>${esc(durationRu(c.minutes_open))}</b></div>
      <div class="row"><span style="color:var(--muted)">По графику сегодня</span>
        <b>${c.expected_today ? esc(shiftToday || 'ожидается') : 'не ожидался'}</b></div>
    </div>`;
  };
  const arrival = a => {
    const e = a.employee || {};
    return `<div class="presence-card ${a.already_started ? 'late' : ''}">
      <div class="nm">${esc(e.short_name || a.employee_id)}</div>
      <div class="pos">${esc(e.position || '—')}${e.group ? ' · ' + esc(e.group) : ''}</div>
      ${v4Contacts(e)}
      <div class="row"><span style="color:var(--muted)">Ожидается к</span>
        <b style="${a.already_started ? 'color:var(--danger)' : ''}">${esc(a.expected_at_hm)}</b></div>
      ${a.already_started ? '<div class="row"><span></span><b style="color:var(--danger)">не пришёл вовремя</b></div>' : ''}
    </div>`;
  };
  body.innerHTML = `
    <div class="stat-grid">
      <div class="stat accent"><div class="k">Сейчас на работе</div><div class="v">${d.at_work_now}</div></div>
      <div class="stat"><div class="k">По графику в этот момент</div><div class="v">${d.expected_now}</div></div>
      <div class="stat"><div class="k">Ещё должны прийти</div><div class="v">${d.yet_to_come.length}</div></div>
    </div>
    <div class="panel"><h3 class="panel-title">На работе прямо сейчас · ${d.open_session_cards.length}</h3>
      ${d.open_session_cards.length
        ? `<div class="presence-grid">${d.open_session_cards.map(card).join('')}</div>`
        : '<div class="empty">Сейчас никто не отмечен на работе</div>'}</div>
    <div class="panel"><h3 class="panel-title">Кто ещё должен прийти · ${d.yet_to_come.length}</h3>
      ${d.yet_to_come.length
        ? `<div class="presence-grid">${d.yet_to_come.map(arrival).join('')}</div>`
        : '<div class="empty">Больше никого сегодня не ждём</div>'}</div>
    <p class="hint">(a) и (b) — независимые счётчики: «на работе» может превышать «по графику»
      (внеграфиковая работа) и наоборот (не пришли). Расхождение — не ошибка: Табель всегда прав.</p>`;
}

/* ══════════════════════════════════════════════════════════════════
   ФАКТ — история сессий (16.4): сырые сессии без округления; визуализация — здесь,
   бэкенд отдаёт только моменты. Три индексных запроса на диапазон.
   ══════════════════════════════════════════════════════════════════ */
state.factEmp = state.factEmp || null;
state.factFrom = state.factFrom || null;

/* ══════════════════════════════════════════════════════════════════
   ФАКТ — слой 2 модели «График = 4 слоя» (T5, норматив 12.10.2026).
   Два представления одних и тех же отметок СКУД:
   · «Номера» (Q7) — один день глазами движка: сырые отметки и округление до шага,
     сопряжённые сессии, окно из кода Табеля, план / отработано / недостача /
     переработка по категориям и флаги из Графика. Все числа считает сервер
     (/api/fact/day, settle за период дня); шаг округления — из настроек, а не из
     интерфейса: источник истины — движок.
   · «Сессии» — исходная история «пришёл — ушёл» за диапазон, без округления.
   Оперативная доска «кто на работе» — отдельный пункт меню «Отметки» (Q7).
   ══════════════════════════════════════════════════════════════════ */
async function loadFact() {
  const host = $('#view-fact');
  state.factMode = state.factMode || 'numbers';
  host.innerHTML = `
    <div class="page-head">
      <div><h2>Слой 2 · Факт</h2>
        <div class="sub">Слой 2 · отметки СКУД: «Номера» — день глазами движка
          (округление до шага, окно из Табеля, план / отработано / недостача /
          переработка, флаги из Графика); «Сессии» — исходная история
          «пришёл — ушёл» без округления</div></div>
      <div class="spacer"></div>
      <div class="seg" id="fc-mode">
        <button data-mode="numbers" class="${state.factMode === 'numbers' ? 'active' : ''}"
          title="Сетка «Номера»: отметки дня, округлённые до шага, и расчёт дня">Номера</button>
        <button data-mode="sessions" class="${state.factMode === 'sessions' ? 'active' : ''}"
          title="История сессий «пришёл — ушёл»: точные моменты, без округления">Сессии</button>
      </div>
    </div>
    <div id="fc-pane"></div>`;
  $$('#fc-mode button').forEach(b => b.onclick = () => {
    if (state.factMode === b.dataset.mode) return;
    state.factMode = b.dataset.mode;
    loadFact();
  });
  if (state.factMode === 'sessions') await loadFactSessions();
  else await loadFactNumbers();
}

/* ── режим «Сессии»: прежняя история сессий (16.4) ── */
async function loadFactSessions() {
  const pane = $('#fc-pane');
  if (!state.factFrom) {
    const t = new Date();
    state.factFrom = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-01`;
  }
  pane.innerHTML = `
    <div class="toolbar">
      <select id="fc-emp" style="max-width:240px"></select>
      <label class="field" style="margin:0"><span>С</span><input type="date" id="fc-from" value="${esc(state.factFrom)}"></label>
      <label class="field" style="margin:0"><span>По</span><input type="date" id="fc-to" value="${esc(state.factTo || todayISO())}"></label>
      <button class="btn btn-sm btn-primary" id="fc-go">Показать</button>
    </div>
    <div id="fc-body"><div class="empty">Загрузка…</div></div>`;
  let emps = (state.employees || []).filter(e => e.active !== false);
  if (!emps.length && can('employees.view')) {
    try { emps = await api('/api/employees', { silent: true }); state.employees = emps; } catch { emps = []; }
  }
  if (!emps.length && state.user.employee_id) {
    emps = [{ id: state.user.employee_id, short_name: state.user.name || 'я' }];
  }
  if (!state.factEmp && emps.length) state.factEmp = emps[0].id;
  $('#fc-emp').innerHTML = emps.map(e =>
    `<option value="${e.id}" ${e.id === state.factEmp ? 'selected' : ''}>${esc(e.short_name || e.full_name)}</option>`).join('');
  $('#fc-emp').onchange = () => { state.factEmp = +$('#fc-emp').value; };
  $('#fc-go').onclick = () => { state.factFrom = $('#fc-from').value; state.factTo = $('#fc-to').value; fetchFact(); };
  await fetchFact();
}

/* ── режим «Номера»: сетка дня (Q7, T5) ── */
async function loadFactNumbers() {
  const pane = $('#fc-pane');
  if (!state.factDay) state.factDay = todayISO();
  pane.innerHTML = `
    <div class="toolbar">
      <div class="month-nav">
        <button id="fd-prev" title="Предыдущий день">‹</button>
        <div class="label" id="fd-label">—</div>
        <button id="fd-next" title="Следующий день">›</button>
      </div>
      <input type="date" id="fd-date" value="${esc(state.factDay)}" style="max-width:165px">
      <button class="btn btn-sm" id="fd-today">Сегодня</button>
      <div class="spacer"></div>
      <span class="hint" id="fd-meta" style="margin:0"></span>
    </div>
    <div id="fd-body"><div class="empty">Загрузка…</div></div>`;
  const shiftDay = delta => {
    const t = new Date(`${state.factDay}T00:00:00`);
    t.setDate(t.getDate() + delta);
    state.factDay = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;
    loadFactNumbers();
  };
  $('#fd-prev').onclick = () => shiftDay(-1);
  $('#fd-next').onclick = () => shiftDay(1);
  $('#fd-today').onclick = () => { state.factDay = todayISO(); loadFactNumbers(); };
  $('#fd-date').onchange = e => { if (e.target.value) { state.factDay = e.target.value; loadFactNumbers(); } };
  await fetchFactDay();
}

async function fetchFactDay() {
  const body = $('#fd-body');
  $('#fd-label').textContent = dateRu(state.factDay);
  let d;
  try { d = await api(`/api/fact/day?date=${state.factDay}`); }
  catch (e) { body.innerHTML = `<div class="panel"><div class="empty">${esc(e.message)}</div></div>`; return; }
  state.factDayData = d;
  $('#fd-meta').innerHTML = `Шаг округления: <b>${d.step_minutes} мин</b> (Настройки → Расчёт) ·
    период ${dateRu(d.period.start)}–${dateRu(d.period.end)}`;
  renderFactNumbers();
}

function factMarksCell(r) {
  if (!r.marks.length) return '<span class="hint">отметок нет</span>';
  const chips = r.marks.map(m => {
    const rounded = m.rounded !== m.at ? `<span class="rnd"> → ${esc(m.rounded)}</span>` : '';
    return `<span class="punch-chip${m.kind === 'out' ? ' out' : ''}"
      title="${m.kind === 'in' ? 'Пришёл' : 'Ушёл'}: исходно ${esc(m.at)}, округлено до шага — ${esc(m.rounded)}">${m.kind === 'in' ? 'Пришёл' : 'Ушёл'} ${esc(m.at)}${rounded}</span>`;
  }).join('');
  const segs = r.segments.map(sg => `<span class="seg-chip${sg.open ? ' open' : ''}"
    title="${sg.open ? 'Сессия не закрыта отметкой «Ушёл»' : (sg.crosses_midnight ? 'Сессия пересекает полночь — показана часть дня' : 'Сопряжённая сессия после округления')}">${esc(sg.start)}–${sg.open ? '…' : esc(sg.end)}</span>`).join('');
  return `${chips}${segs ? ` <span class="hint">→</span> ${segs}` : ''}`;
}

function factOtCell(c) {
  if (!c) return '';
  const codes = Object.entries(c.codes || {}).map(([t, m]) =>
    `<span class="v4-code ${t.startsWith('ДН') ? 'n' : 'd'}" style="display:inline-block;margin:1px 2px">${esc(t)} ${hours(m / 60)}</span>`).join('');
  if (codes) return codes;
  if (c.overtime_minutes) {
    return `<span class="badge muted" title="Переработка без дневных/ночных кодов">перераб. ${hours(c.overtime_minutes / 60)}${c.pays_overtime ? '' : ' · в банк'}</span>`;
  }
  return '<span class="hint">—</span>';
}

function renderFactNumbers() {
  const d = state.factDayData;
  const body = $('#fd-body');
  if (!d) return;
  const rows = d.rows.map(r => {
    const who = `<td class="who" data-label="Сотрудник">${esc(r.employee.short_name)}<small>${esc(r.employee.group)}${r.employee.position ? ' · ' + esc(r.employee.position) : ''}</small></td>`;
    if (r.out_of_staff) {
      return `<tr data-emp="${r.employee.id}">${who}<td colspan="7" data-label=""><span class="badge muted"
        title="День вне интервала трудоустройства (R35)">не в штате в этот день</span></td></tr>`;
    }
    const c = r.card;
    const marks = `<td data-label="Отметки">${factMarksCell(r)}</td>`;
    if (!c) {
      return `<tr data-emp="${r.employee.id}">${who}${marks}<td colspan="6" data-label="" style="color:var(--danger)">${esc(r.error || 'Нет данных расчёта за период')}</td></tr>`;
    }
    const flags = (c.flags || []).map(f =>
      `<span class="v4-flagtext ${V4_FLAG_CLASS[f.code] || ''}" title="${esc(f.hint || '')}">● ${esc(f.title)}</span>`).join(' ')
      || '<span class="hint">нет</span>';
    return `<tr data-emp="${r.employee.id}">
      ${who}
      ${marks}
      <td data-label="Окно" class="num" title="Стандартное окно кода Табеля (CFG-WINDOWS) — жёстко из кода (Q1)">${c.window ? `${esc(c.window[0])}–${esc(c.window[1])}` : '—'}<small class="hint" style="display:block">Табель: «${esc(c.timesheet_value)}»</small></td>
      <td data-label="План" class="num" title="Расчётный план = длина окна (R34); план строки Табеля — информационный">${v4Hours(c.plan_minutes / 60)}${c.timesheet_plan_minutes ? `<small class="hint" style="display:block">строка ${hours(c.timesheet_plan_minutes / 60)}</small>` : ''}</td>
      <td data-label="Отработано" class="num"><b>${v4Hours(c.work_minutes / 60)}</b><small class="hint" style="display:block">факт ${v4Hours(c.fact_minutes / 60)}</small></td>
      <td data-label="Недоработка" class="num">${c.debt_minutes ? `<span class="v4-debt" title="Недостача дня (окно − отработано)">−${hours(c.debt_minutes / 60)}</span>` : '—'}${c.plan_equals_fact ? ' <span class="badge info" title="Применён «План=Факт»: день освобождён от недостачи">П=Ф</span>' : ''}</td>
      <td data-label="Переработка" class="num">${factOtCell(c)}</td>
      <td data-label="Флаги"><div style="display:flex;flex-direction:column;gap:2px">${flags}</div></td></tr>`;
  }).join('');
  body.innerHTML = `
    <div class="table-wrap"><table class="data responsive">
      <thead><tr><th class="who">Сотрудник</th><th>Отметки (СКУД → округление)</th>
        <th>Окно (из Табеля)</th><th>План</th><th>Отработано</th><th>Недоработка</th>
        <th>Переработка</th><th>Флаги (из Графика)</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="8" class="empty">${d.all_employees ? 'В этот день никто не трудоустроен' : 'Нет данных'}</td></tr>`}</tbody>
    </table></div>
    <p class="hint">${dateRu(d.date)} · период расчёта ${dateRu(d.period.start)}–${dateRu(d.period.end)}${d.granularity === 'half_month' ? ' (половина месяца)' : ''}.
      Часы, недостача, переработка и флаги — из движка (settle периода); отметки показаны
      сырыми и округлёнными до шага ${d.step_minutes} мин. Оперативная доска «кто на работе» —
      в разделе «Отметки» (Q7); исходные сессии без округления — в режиме «Сессии».
      Подробная карточка сотрудника с трассой расчёта — в слое 3 (клик по строке).</p>`;
}

async function fetchFact() {
  const body = $('#fc-body');
  if (!state.factEmp) { body.innerHTML = '<div class="panel"><div class="empty">Выберите сотрудника</div></div>'; return; }
  let d;
  try {
    d = await api(`/api/fact/sessions?employee_id=${state.factEmp}&first=${state.factFrom}&last=${state.factTo || todayISO()}`);
  } catch (e) { body.innerHTML = `<div class="panel"><div class="empty">${esc(e.message)}</div></div>`; return; }
  const byDay = {};
  d.sessions.forEach(s => {
    const key = s.start_local.slice(0, 10);
    (byDay[key] = byDay[key] || []).push(s);
  });
  const hm = iso => iso ? iso.slice(11, 16) : '—';
  const rows = Object.keys(byDay).sort().map(day => byDay[day].map(s => {
    const dur = s.minutes != null ? `${hours(s.minutes / 60)} ч` : 'идёт сейчас';
    const badges = [
      s.started_before_range ? '<span class="badge muted" title="Сессия открыта отметкой до начала диапазона">начата до диапазона</span>' : '',
      s.closed_after_range ? '<span class="badge muted" title="Уход — за правой границей диапазона">закрыта после диапазона</span>' : '',
      s.open ? '<span class="badge warn" title="Сотрудник не отметил «Ушёл» — сессия открыта">открыта</span>' : '',
    ].join(' ');
    return `<tr>
      <td data-label="День">${dateRu(day)}</td>
      <td data-label="Пришёл">${hm(s.start_local)}</td>
      <td data-label="Ушёл">${s.open ? '—' : hm(s.end_local)}</td>
      <td data-label="Длительность">${dur}</td>
      <td data-label="Примечания">${badges}</td></tr>`;
  }).join('')).join('');
  body.innerHTML = `
    <div class="panel"><h3 class="panel-title">${esc(d.employee.short_name || d.employee.full_name || '')} ·
      сессий: ${d.sessions.length}</h3>
      <div class="table-wrap"><table class="data responsive">
        <thead><tr><th>День</th><th>Пришёл</th><th>Ушёл</th><th>Длительность</th><th>Примечания</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="5" class="empty">Сессий в диапазоне нет</td></tr>'}</tbody>
      </table></div>
      <p class="hint">Моменты исходные (с секундами в источнике), без округления и дневной нарезки:
        сессия может пересекать полночь. Расчётные часы — во вкладке «Управленческий табель».</p></div>`;
}

/* ══════════════════════════════════════════════════════════════════
   ТАБЕЛЬ (16.5) — первичный документ: код дня + информационный план строки.
   Циклы графика — инструмент заполнения Табеля (решение владельца).
   ══════════════════════════════════════════════════════════════════ */
async function loadTabel() {
  const host = $('#view-timesheet');
  host.innerHTML = `
    <div class="page-head">
      <div><h2>Слой 0 · Табель</h2><div class="sub">Первичный документ: код дня и плановые часы.
        Окно рабочего времени, недостача и план карточки считаются от значения Табеля
        (CFG-WINDOWS); График генерируется из Табеля</div></div>
      <div class="spacer"></div>
      ${v4MonthNav('tb')}
      <button class="btn btn-sm" id="tb-absence" title="Слой 0 · Табель: отпуск, больничный, за свой счёт, оплачиваемый выходной — коды первичного документа">Назначить отсутствие</button>
      <button class="btn btn-sm" id="tb-fill">Заполнить из циклов</button>
      <button class="btn btn-sm" id="tb-reset" title="Убрать ручные коды периода и вернуть автозаполнение из циклов">Сбросить</button>
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
  /* T3 (Q5, 12.10.2026): «Сбросить» — убрать ручные коды и вернуть автозаполнение. */
  $('#tb-reset').style.display = data.can_edit ? '' : 'none';
  $('#tb-reset').onclick = () => tabelResetModal(data);
  /* Q4: отпуск/ДО/Б/ОВ назначаются кодом Табеля — из Табеля, а не из Графика. */
  $('#tb-absence').style.display = data.can_edit ? '' : 'none';
  $('#tb-absence').onclick = () => openRangeModal('tabel');
  renderTabel();
  if (state.pendingTabelCell) {
    const { emp, date } = state.pendingTabelCell;
    state.pendingTabelCell = null;
    const row = data.rows.find(r => r.employee.id === emp);
    if (row && data.days.includes(date)) tabelCellModal(emp, date);
  }
}

function v4CellLabel(c) { return c ? c.value.replace(' ', '') : ''; }

function renderTabel() {
  const d = state.tabel;
  const lockBadge = l => l === 'locked'
    ? '<span class="badge muted" title="Период закрыт, следующий тоже закрыт — правка запрещена">закрыт</span>'
    : (l === 'last_closed'
      ? '<span class="badge warn" title="Последний закрытый период: правка разрешена, затем — пересчёт в УТ">закрыт · можно править</span>' : '');
  const missing = d.rows.reduce((n, r) => n + (r.missing_days || []).length, 0);
  const rows = d.rows.map(r => `<tr>
    <td class="who">${esc(r.employee.short_name)}<small>${esc(r.employee.group)} ${lockBadge(r.lock)}</small></td>
    ${d.days.map(day => {
      const c = r.cells[day];
      const color = c ? v4CodeColor(c.code, d.colors) : 'transparent';
      const edit = d.can_edit && r.lock !== 'locked';
      const src = c ? (c.source === 'cycle' ? ' · из циклов' : ' · вручную') : '';
      return `<td class="v4-cell${edit ? ' edit' : ''}${c ? '' : ' empty'}" ${edit ? `data-e="${r.employee.id}" data-d="${day}"` : ''}
        title="${c ? esc(c.value + src + (c.note ? ' · ' + c.note : '')) : 'не заполнено — расчёт не запустится, пока Табель не покрывает период'}"
        style="${c ? `background:${withAlpha(color, .22)};border-left:3px solid ${color}` : ''}">${esc(v4CellLabel(c))}</td>`;
    }).join('')}
    <td class="num"><b>${hours(r.plan_hours)}</b></td></tr>`).join('');
  $('#tb-body').innerHTML = `
    ${missing ? `<div class="panel" style="border-color:#ecd9ae;background:#fffaf0"><b>${missing}</b> ${plural(missing, 'ячейка', 'ячейки', 'ячеек')} не заполнены.
      Табель обязан покрывать период: ровно одна строка на каждый день трудоустройства
      (RUL-TIMESHEET-COVERS-PERIOD) — иначе расчёт УТ не запустится. Заполните вручную или «Заполнить из циклов».</div>` : ''}
    <div class="table-wrap v4-grid-wrap"><table class="data v4-grid">
      <thead><tr><th class="who">Сотрудник</th>${d.days.map(v4DayHead).join('')}<th>План, ч</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="${d.days.length + 2}" class="empty">Нет сотрудников</td></tr>`}</tbody>
    </table></div>
    <p class="hint">Коды: ${d.codes.map(c => `<span class="badge" style="background:${withAlpha(v4CodeColor(c.code, d.colors), .22)}" title="${esc(c.title)}">${esc(c.code)}</span> ${esc(c.title)}`).join(' · ')}.
      Значения с окнами (CFG-WINDOWS): ${d.values.map(esc).join(', ')}. План строки — информационный
      (зарплатный) атрибут; план карточки УТ = длина окна.</p>`;
  $$('#tb-body td.v4-cell.edit').forEach(td => td.onclick = () => tabelCellModal(+td.dataset.e, td.dataset.d));
}

function tabelCellModal(empId, day) {
  const d = state.tabel;
  const row = d.rows.find(r => r.employee.id === empId);
  const cur = row.cells[day] || null;
  const lastDay = d.days[d.days.length - 1].slice(8);
  /* Q4 (норматив 12.10.2026): отпуск, больничный, за свой счёт и оплачиваемый выходной —
     коды Табеля, и заявления по ним печатаются ОТСЮДА (из слоя 0). «Отпросился
     (выходной за часы)» — данные Графика, его заявление печатается из ячейки Графика. */
  const kindOfCode = code => (state.shiftTypes || []).find(x => x.tzh_code === code
    && x.kind === 'absence' && x.doc_type && !x.archived);
  const statementName = k => (state.docKinds || []).find(x => x.code === k.doc_type)?.name
    || k.doc_type;
  openModal({
    title: `Табель · ${row.employee.short_name}`,
    subtitle: `${dateRu(day)}${row.lock === 'last_closed' ? ' · период закрыт: после правки нужен пересчёт в УТ' : ''}`,
    body: `
      <label class="field"><span>Код дня (CFG-DAY-CODES)</span><select id="tc-code">
        <option value="">— очистить ячейку —</option>
        ${d.codes.map(c => `<option value="${esc(c.code)}" data-h="${c.carries_hours ? 1 : 0}" ${cur && cur.code === c.code ? 'selected' : ''}>${esc(c.code)} — ${esc(c.title)}</option>`).join('')}
      </select></label>
      <label class="field" id="tc-hours-f"><span>Плановые часы (информационный план строки)</span>
        <input id="tc-hours" type="number" step="0.25" min="0" max="24" value="${cur ? cur.hours : 12}" list="tc-hours-list">
        <datalist id="tc-hours-list"></datalist></label>
      <label class="field"><span>Применить по число месяца (включительно)</span>
        <input id="tc-until" type="number" min="${+day.slice(8)}" max="${+lastDay}" value="${+day.slice(8)}"></label>
      <label class="field"><span>Примечание</span><input type="text" id="tc-note" value="${esc(cur?.note || '')}"></label>
      <p class="hint">План кратен 15 минутам; для значения с часами нужна строка окна
        (${d.values.map(esc).join(', ')}). Информационный план может быть меньше длины окна
        (например, обед в зарплатной норме) — расчёт идёт от окна.</p>
      <div id="tc-doc-wrap" style="display:none;margin-top:10px;border-top:1px solid var(--line);padding-top:10px">
        <div class="opt-group-title" style="margin-top:0">Заявление по коду Табеля</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          <button class="btn btn-sm" id="tc-print">Печать заявления</button>
          <button class="btn btn-sm" id="tc-docx">DOCX (шаблон компании)</button>
          <button class="btn btn-sm" id="tc-pdf">PDF (готов к печати)</button>
          <span class="hint" style="margin:0" id="tc-doc-name"></span>
        </div>
        <p class="hint" style="margin:6px 0 0">Печатается по СОХРАНЁННОМУ коду дня и находит весь
          период отсутствия, даже если он переходит границы месяца. Период берётся из Табеля.</p>
      </div>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button><button class="btn btn-primary" data-save>Сохранить</button>`,
    onMount(m) {
      const sync = () => {
        const opt = $('#tc-code').selectedOptions[0];
        const withHours = opt && opt.dataset.h === '1';
        $('#tc-hours-f').style.display = withHours ? '' : 'none';
        $('#tc-hours-list').innerHTML = d.values.filter(v => v.startsWith(opt.value + ' '))
          .map(v => `<option value="${v.split(' ')[1]}">`).join('');
        /* у кода с часами план обязан быть положительным (CHK-PLAN-CONSISTENT): если
           поле пустое/нулевое (прежнее значение кода без часов), предлагаем первое
           окно кода из CFG-WINDOWS — иначе сохранение упадёт в 422 без подсказки */
        if (withHours && !(Number($('#tc-hours').value) > 0)) {
          const first = d.values.find(v => v.startsWith(opt.value + ' '));
          if (first) $('#tc-hours').value = first.split(' ')[1];
        }
        const kind = kindOfCode(opt ? opt.value : '');
        $('#tc-doc-wrap').style.display = kind ? '' : 'none';
        if (kind) $('#tc-doc-name').textContent = statementName(kind);
      };
      $('#tc-code').onchange = sync; sync();
      /* печать имеет смысл только по сохранённому дню: сервер читает код из Табеля */
      const ifSaved = fn => () => {
        if (!cur) return toast('Сначала сохраните код дня — тогда станет доступна печать', 'warn');
        fn();
      };
      $('#tc-print').onclick = ifSaved(() => printAbsenceRequest(empId, day, 'tabel_code'));
      $('#tc-docx').onclick = ifSaved(() => downloadAbsenceDoc(empId, day, 'docx', 'tabel_code'));
      $('#tc-pdf').onclick = ifSaved(() => downloadAbsenceDoc(empId, day, 'pdf', 'tabel_code'));
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        const code = $('#tc-code').value;
        /* план отправляем только для кода, несущего часы: поле часов для прочих
           скрыто, и его прежнее значение не должно попадать в запрос (иначе
           CHK-PLAN-CONSISTENT честно вернёт 422 — «код не несёт часы») */
        const codeOpt = $('#tc-code').selectedOptions[0];
        const h = codeOpt && codeOpt.dataset.h === '1' ? (Number($('#tc-hours').value) || 0) : 0;
        const until = Math.max(+day.slice(8), Math.min(+lastDay, Number($('#tc-until').value) || +day.slice(8)));
        try {
          let res;
          if (until > +day.slice(8)) {
            const dates = d.days.filter(x => +x.slice(8) >= +day.slice(8) && +x.slice(8) <= until);
            res = await api('/api/tabel/bulk', { method: 'POST', body: { employee_ids: [empId], dates, code, hours: h } });
            (res.warnings || []).forEach(w => toast(w, 'warn'));
            (res.errors || []).slice(0, 5).forEach(e => toast(`${e.date}: ${e.detail}`, 'err'));
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
    title: 'Заполнить Табель из циклов',
    subtitle: `${MONTHS[d.month - 1]} ${d.year}`,
    body: `
      <p>Циклы блоков (2/2, 3/3, пятидневка, произвольный цикл) раскладываются по дням и
        подбирают значение Табеля по окнам CFG-WINDOWS («Я 12» = 08:00–20:00). Смена через
        полночь оформляется <b>одной строкой в дне начала</b>: суточные 08:00–08:00 дают явку
        с окном 08:00–20:00, а присутствие после полуночи попадает в карточку следующего
        дня — рабочее время считается по окну своего дня, часы вне окна идут в переработку.
        Дни без работы получают код отсутствия из словаря. График будет перегенерирован
        из Табеля.</p>
      <label class="field"><span>Что перезаписывать</span><select id="tf-mode">
        <option value="keep">Только пустые и заполненные из циклов (ручные правки сохраняются)</option>
        <option value="all">Все ячейки, включая ручные правки</option>
      </select></label>
      <p class="hint">Закрытые периоды (кроме последнего закрытого) не меняются.</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button><button class="btn btn-primary" data-save>Заполнить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        try {
          const r = await api('/api/tabel/fill-from-cycles', { method: 'POST',
            body: { year: d.year, month: d.month, overwrite: $('#tf-mode').value === 'all' } });
          closeModal();
          toast(`Заполнено ячеек: ${r.written}, пропущено: ${r.skipped}`,
            r.warnings.length ? 'warn' : 'ok', (r.warnings || []).slice(0, 8));
          loadTabel();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* «Сбросить» (T3, решение владельца Q5 от 12.10.2026): убирает введённые вручную коды
   периода и возвращает автозаполнение из циклов; закрытых периодов не касается. */
function tabelResetModal(d) {
  const rows = d.rows || [];
  const manual = rows.reduce((n, r) => n + Object.values(r.cells)
    .filter(c => c.source === 'manual').length, 0);
  openModal({
    title: 'Сбросить Табель',
    subtitle: `${MONTHS[d.month - 1]} ${d.year}${d.half ? ` · половина ${d.half}` : ''}`,
    body: `
      <p>Табель — первичный документ: он заполняется из настроек сотрудника (циклов блоков),
        а ручная правка ячейки запоминается и автозаполнением больше не перезаписывается.
        Сброс убирает <b>введённые вручную</b> коды периода и заново заполняет Табель из
        циклов; График перегенерируется из Табеля.</p>
      <div class="panel" style="border-color:#ecd9ae;background:#fffaf0;margin:10px 0">
        Сейчас вручную заполнено ячеек: <b>${manual}</b>. Закрытые периоды не трогаются
        (RUL-CLOSED-PERIOD-IMMUTABLE); дни вне трудоустройства не заполняются.</div>
      <label class="field"><span>Кому</span><select id="tr-emp">
        <option value="">Всем сотрудникам периода</option>
        ${rows.map(r => `<option value="${r.employee.id}">${esc(r.employee.short_name)} · ${esc(r.employee.group)}${r.lock === 'locked' ? ' · закрыт' : ''}</option>`).join('')}
      </select></label>
      <p class="hint">Если для дня цикл не даёт значения (нет строки CFG-WINDOWS либо отрезки
        дня одним значением непредставимы), ячейка останется пустой — список вернёт сервер,
        такие дни нужно заполнить вручную, иначе расчёт не запустится. Пересчёт часов не
        запускается: итоги обновятся при чтении «Управленческого Табеля».</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-danger" data-ok>Сбросить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = () => {
        const empId = $('#tr-emp').value;      // значение читаем ДО подтверждающей модалки
        confirmDialog('Сбросить ручные коды Табеля?',
          'Ручные правки периода будут удалены, Табель снова заполнится из циклов, График перегенерируется. Вернуть удалённые коды можно только повторным вводом вручную.',
          async () => {
            try {
              const r = await api('/api/tabel/reset', { method: 'POST', body: {
                year: d.year, month: d.month, half: d.half || null,
                employee_ids: empId ? [+empId] : null } });
              const bits = [`очищено ручных ячеек: ${r.cleared}`,
                            `заполнено из циклов: ${r.written}`];
              if ((r.locked_skipped || []).length) bits.push(`пропущено закрытых: ${r.locked_skipped.length}`);
              if (r.uncovered_total) bits.push(`остались пустыми: ${r.uncovered_total} дн.`);
              toast(bits.join(', '),
                (r.uncovered_total || (r.warnings || []).length) ? 'warn' : 'ok',
                [...(r.warnings || []),
                 ...(r.uncovered || []).map(u => `${u.employee} ${dateRu(u.date)}: не заполнено`)].slice(0, 8));
              loadTabel();
            } catch (e) { toast(e.message, 'err'); }
          }, 'Сбросить');
      };
    },
  });
}

/* ══════════════════════════════════════════════════════════════════
   УПРАВЛЕНЧЕСКИЙ ТАБЕЛЬ (16.6) — единственная вкладка тяжёлого конвейера.
   Период: месяц либо половина месяца (настройка period_granularity, v7.1/R36).
   Открытие: незакрытый → живой расчёт (view, ничего не сохраняется); закрытый →
   сохранённые результат и снимок флагов без пересчёта. «Закрыть период» /
   «Пересчитать» — атомарные операции.
   ══════════════════════════════════════════════════════════════════ */
state.mgmtHalf = state.mgmtHalf || null;

function v4PeriodNav(prefix) {
  return `<div class="month-nav"><button id="${prefix}-prev">‹</button>
    <div class="label" id="${prefix}-label">—</div>
    <button id="${prefix}-next">›</button></div>`;
}

async function loadMgmt() {
  const host = $('#view-mgmt');
  host.innerHTML = `
    <div class="page-head">
      <div><h2>Слой 3 · Управленческий Табель</h2><div class="sub">Коды УТ (ДЯ, ДН, ДЯ2, ДН2) по дням после
        размещения; недостача гасится банком и каскадом при закрытии периода</div></div>
      <div class="spacer"></div>
      ${v4PeriodNav('ut')}
      <button class="btn btn-sm btn-primary" id="ut-close">Закрыть период</button>
      <button class="btn btn-sm" id="ut-recalc">Пересчитать</button>
      <button class="btn btn-sm btn-ghost" id="ut-xlsx">Excel</button>
    </div>
    <div id="ut-body"><div class="empty">Загрузка…</div></div>`;
  const qs = () => `year=${state.year}&month=${state.month}` +
    (state.mgmtHalf ? `&half=${state.mgmtHalf}` : '');
  const reload = () => loadMgmt();
  const shiftPeriod = delta => {
    if (state.mgmtHalf) {
      if (delta > 0 && state.mgmtHalf === 1) { state.mgmtHalf = 2; return reload(); }
      if (delta < 0 && state.mgmtHalf === 2) { state.mgmtHalf = 1; return reload(); }
    }
    let m = state.month + delta, y = state.year;
    if (m < 1) { m = 12; y--; } if (m > 12) { m = 1; y++; }
    state.month = m; state.year = y;
    if (state.mgmtHalf) state.mgmtHalf = delta > 0 ? 1 : 2;
    reload();
  };
  $('#ut-prev').onclick = () => shiftPeriod(-1);
  $('#ut-next').onclick = () => shiftPeriod(1);
  let d;
  try { d = await api(`/api/mgmt?${qs()}`); } catch (e) {
    $('#ut-body').innerHTML = `<div class="panel"><div class="empty">${esc(e.message)}</div></div>`; return;
  }
  state.mgmt = d;
  if (d.granularity === 'half_month' && !state.mgmtHalf) state.mgmtHalf = d.half || 1;
  $('#ut-label').textContent = d.granularity === 'half_month'
    ? `${MONTHS[d.month - 1]} ${d.year} · ${d.period.start.slice(8)}–${d.period.end.slice(8)}`
    : `${MONTHS[d.month - 1]} ${d.year}`;
  $('#ut-close').style.display = d.can_close ? '' : 'none';
  $('#ut-recalc').style.display = d.can_recalculate ? '' : 'none';
  $('#ut-close').onclick = () => mgmtAction('close', null);
  $('#ut-recalc').onclick = () => mgmtAction('recalculate', null);
  $('#ut-xlsx').onclick = () => downloadBlob(`/api/mgmt/xlsx?${qs()}`, 'upr_tabel.xlsx');
  renderMgmt();
}

function mgmtCell(ut) {
  return Object.entries(ut || {}).map(([t, m]) =>
    `<span class="v4-code ${m >= 120 ? 'x2' : ''} ${t.startsWith('ДН') ? 'n' : 'd'}">${esc(t)}&nbsp;${hours(m / 60)}</span>`).join('');
}

function renderMgmt() {
  const d = state.mgmt;
  const modeNote = 'Просмотр: недостача показана, коды не изымаются, банк — предварительный ' +
    '(входящий + корректировки + зачисленное). Ничего не сохраняется. Закрытие выполняет ' +
    'погашение банком и каскадом и сохраняет результат, снимок флагов и переносы.';
  const stateBadge = r => r.error ? `<span class="badge danger" title="${esc(r.error)}">ошибка</span>`
    : (r.state?.closed ? '<span class="badge ok">закрыт</span>' : '<span class="badge muted">view</span>');
  const rows = d.rows.map(r => {
    if (r.error) {
      return `<tr><td class="who">${esc(r.employee.short_name)}<small>${esc(r.employee.group)}</small></td>
        <td colspan="${d.days.length + d.tariffs.length + 3}" style="color:var(--danger)">${esc(r.error)}</td>
        <td>${stateBadge(r)}</td></tr>`;
    }
    const flagsByDay = {};
    (r.days || []).forEach(dv => (dv.flags || []).forEach(f => {
      (flagsByDay[dv.day] = flagsByDay[dv.day] || []).push(f);
    }));
    const cardByDay = {};
    (r.days || []).forEach(dv => { cardByDay[dv.day] = dv; });
    const outDays = new Set(r.out_of_staff_days || []);
    return `<tr data-emp="${r.employee.id}" class="v4-click">
      <td class="who">${esc(r.employee.short_name)}<small>${esc(r.employee.group)}</small></td>
      ${d.days.map(day => {
        if (outDays.has(day)) {
          return `<td class="v4-ut" title="День вне интервала трудоустройства"><span class="badge muted">не в штате</span></td>`;
        }
        const dv = cardByDay[day];
        const fl = flagsByDay[day] || [];
        const debt = dv && dv.debt_minutes ? `<span class="v4-debt" title="Недостача дня (от окна)">−${hours(dv.debt_minutes / 60)}</span>` : '';
        const flag = fl.length ? `<span class="v4-flag ${V4_FLAG_CLASS[fl[0].code] || ''}" title="${esc(fl.map(f => f.title).join('\n'))}">●</span>` : '';
        const future = day > todayISO() ? ' future' : '';
        const pef = dv && dv.plan_equals_fact ? ' <span class="badge info" title="Применён «План=Факт»: день освобождён от недостачи">П=Ф</span>' : '';
        return `<td class="v4-ut${future}" title="${dv ? esc(dv.timesheet_value) + (future ? ' · прогноз: недостача = окно, если сотрудник не придёт' : '') : ''}">${mgmtCell(r.ut[day])}${debt}${flag}${pef}</td>`;
      }).join('')}
      ${d.tariffs.map(t => `<td class="num">${v4Hours((r.totals[t] || 0) / 60)}</td>`).join('')}
      <td class="num" title="Общий долг / остаток после погашения">${hours(r.debt.total_h)}${r.state?.closed ? ` / ${hours(r.debt.residual_h)}` : ''}</td>
      <td class="num"><b style="color:${r.bank.closed < 0 ? 'var(--danger)' : 'inherit'}">${r.bank.closed >= 0 ? '+' : ''}${hours(r.bank.closed_h)}</b></td>
      <td class="num">${r.deferred.length ? `<span class="badge warn" title="Отложено на следующий период">${r.deferred.length}</span>` : ''}</td>
      <td>${stateBadge(r)}</td></tr>`;
  }).join('');
  $('#ut-body').innerHTML = `
    <div class="panel" style="padding:12px 16px"><span class="hint" style="margin:0">${esc(modeNote)}</span></div>
    <div class="table-wrap v4-grid-wrap"><table class="data v4-grid">
      <thead><tr><th class="who">Сотрудник</th>${d.days.map(v4DayHead).join('')}
        ${d.tariffs.map(t => `<th>${esc(t)}</th>`).join('')}<th>Недостача</th><th>Банк</th><th title="Отложенные блоки">→</th><th>Статус</th></tr></thead>
      <tbody>${rows || '<tr><td class="empty" colspan="99">Нет сотрудников, трудоустроенных в периоде</td></tr>'}</tbody>
    </table></div>
    <p class="hint">Период ${dateRu(d.period.start)} – ${dateRu(d.period.end)} · шаг расчёта
      ${d.step_minutes} мин · версии настроек: ${d.settings_versions.map(esc).join(', ')}.
      Клик по строке — карточки дней (расчётный и информационный планы), флаги, изъятия и трасса расчёта.</p>`;
  $$('#ut-body tr[data-emp]').forEach(tr => tr.onclick = () => mgmtDetail(+tr.dataset.emp));
}

async function mgmtAction(kind, empId) {
  const d = state.mgmt;
  const title = kind === 'close' ? 'Закрыть период?' : 'Пересчитать закрытый период?';
  const text = kind === 'close'
    ? `${dateRu(d.period.start)} – ${dateRu(d.period.end)}: недостача будет погашена банком и кодами, ` +
      'результат, снимок флагов, банк и отложенные блоки сохранятся одной атомарной операцией. ' +
      'Повторно закрыть нельзя; исправить можно только пересчётом последнего закрытого периода.'
    : 'Отметки, Табель и корректировки будут перечитаны свежими; расчёт повторится с исходных ' +
      'входящих остатков периода (ClosingInputs заморожены). Результат, банк, переносы и снимок ' +
      'флагов будут ЗАМЕНЕНЫ. Доступно только для последнего закрытого периода.';
  confirmDialog(title, text, async () => {
    try {
      const body = { year: d.year, month: d.month, half: d.half };
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
  try {
    r = await api(`/api/mgmt?year=${d.year}&month=${d.month}${d.half ? `&half=${d.half}` : ''}&employee_id=${empId}&detail=true`);
    r = (r.rows || [])[0];
  } catch (e) { toast(e.message, 'err'); return; }
  if (!r || r.error) { toast(r ? r.error : 'Нет данных', 'err'); return; }
  const b = r.bank;
  const cardRows = (r.days || []).map(dv => {
    const flags = (dv.flags || []).map(f =>
      `<div class="v4-flagtext ${V4_FLAG_CLASS[f.code] || ''}">● ${esc(f.title)}${f.hint ? ` <small>${esc(f.hint)}</small>` : ''}</div>`).join('');
    return `<tr>
      <td>${dateRu(dv.day).slice(0, 6)}</td>
      <td>${esc(dv.timesheet_value)}${dv.plan_equals_fact ? ' <span class="badge info">План=Факт</span>' : ''}</td>
      <td class="num" title="Расчётный план = длина окна (R34)">${v4Hours(dv.plan_hours)}</td>
      <td class="num" title="Информационный (зарплатный) план строки Табеля">${v4Hours(dv.timesheet_plan_hours)}</td>
      <td class="num">${v4Hours(dv.fact_minutes / 60)}</td>
      <td class="num">${v4Hours(dv.work_minutes / 60)}</td>
      <td class="num">${v4Hours(dv.overtime_minutes / 60)}</td>
      <td class="num" style="color:var(--danger)">${dv.debt_minutes ? hours(dv.debt_minutes / 60) : ''}</td>
      <td>${mgmtCell(dv.codes)}${!dv.pays_overtime && dv.overtime_minutes ? ' <span class="badge muted">в банк</span>' : ''}</td>
      <td>${mgmtCell(r.ut[dv.day])}</td>
      <td>${flags}</td></tr>`;
  }).join('');
  const canRecalc = d.can_recalculate && r.state?.can_recalculate;
  const canClose = d.can_close && r.state?.can_close;
  const outDays = (r.out_of_staff_days || []);
  openModal({
    title: r.employee.full_name,
    subtitle: `${dateRu(d.period.start)} – ${dateRu(d.period.end)} · ${r.state?.closed ? 'период закрыт (сохранённые данные)' : 'просмотр (живой расчёт)'}`,
    wide: true,
    body: `
      <div class="stat-grid">
        <div class="stat"><div class="k">Недостача всего</div><div class="v">${hours(r.debt.total_h)}</div></div>
        <div class="stat"><div class="k">Погашено банком</div><div class="v">${hours(b.paid / 60)}</div></div>
        <div class="stat warn"><div class="k">Остаток долга</div><div class="v">${hours(r.debt.residual_h)}</div></div>
        <div class="stat accent"><div class="k">Банк на закрытие</div><div class="v">${b.closed >= 0 ? '+' : ''}${hours(b.closed_h)}</div></div>
      </div>
      <p class="hint" style="margin-top:-6px">Банк: входящий ${hours(b.open_h)}${b.open_normalized !== b.open ? ` (нормализован к шагу: ${hours(b.open_normalized / 60)})` : ''}
        + корректировки ${hours(b.adjustments_h)} + зачислено неоплачиваемых переработок ${hours(b.credited_h)}.
        Остаток недостачи всегда переносится минусом банка.</p>
      ${outDays.length ? `<p class="hint">Дни вне трудоустройства («не в штате»): ${outDays.map(x => dateRu(x).slice(0, 6)).join(', ')}</p>` : ''}
      <div class="table-wrap" style="max-height:46vh"><table class="data">
        <thead><tr><th>День</th><th>Табель</th><th>План (окно)</th><th>План строки</th><th>Факт</th>
          <th>Рабочее</th><th>Перераб.</th><th>Недост.</th><th>Коды дня</th><th>Итог УТ</th><th>Флаги</th></tr></thead>
        <tbody>${cardRows}</tbody></table></div>
      ${r.deferred.length ? `<div class="panel" style="margin-top:12px"><h3 class="panel-title">Отложено на следующий период</h3>
        ${r.deferred.map(x => `<span class="badge warn">${esc(x.tariff)} ${hours(x.hours)} ч из ${dateRu(x.source_day)}</span>`).join(' ')}</div>` : ''}
      ${r.cuts && r.cuts.length ? `<div class="panel" style="margin-top:12px"><h3 class="panel-title">Изъятия каскадом</h3>
        ${r.cuts.map(c => `<div>${esc(c.tariff)} ${hours(c.taken_minutes / 60)} ч (${dateRu(c.source_day)}${c.placed_day ? ' → ' + dateRu(c.placed_day) : ''}) — погашено ${hours(c.paid_minutes / 60)} ч</div>`).join('')}</div>` : ''}
      ${r.exceptions.length ? `<div class="panel" style="margin-top:12px"><h3 class="panel-title">Исключения</h3>${r.exceptions.map(x => `<div>${esc(x.text)}</div>`).join('')}</div>` : ''}
      <details style="margin-top:12px"><summary>Трасса расчёта (${(r.trace || []).length})</summary>
        ${(r.trace || []).map(t => `<div class="audit-item"><span class="ac">${esc(t.step)} · ${esc(t.code)}</span> ${esc(t.text)}</div>`).join('') || '<div class="empty">Пусто</div>'}</details>`,
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
   СПРАВОЧНИКИ ДВИЖКА v7.1 (в разделе «Настройки»): CFG-DAY-CODES, CFG-WINDOWS,
   CFG-CATEGORIES, CFG-WEIGHTS, CFG-CASCADE, CFG-PLACEMENT, CFG-GROUPS,
   CFG-LIMITS, гранулярность периода + модификаторы CFG-MODIFIERS
   ══════════════════════════════════════════════════════════════════ */
const V4_MOD_TITLES = {
  double_overtime: 'Двойные переработки', pays_overtime: 'Оплачиваются ли переработки',
  plan_equals_fact: 'План=Факт', counts_in_ut: 'Учитываются ли часы в УТ',
};

async function renderEngineSettings(host) {
  if (!host) return;
  let data, mods;
  try {
    [data, mods] = await Promise.all([api('/api/engine-settings'),
      api(`/api/engine-settings/modifiers?year=${state.year}&month=${state.month}`)]);
  } catch (e) { host.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  const p = data.active.payload;
  state.enginePayload = p;      // панель «Правила оплаты переработок» сохраняет новую версию отсюда

  const edit = can('settings.edit');
  const first = `${state.year}-${String(state.month).padStart(2, '0')}-01`;
  const empName = id => (state.employees.find(e => e.id === id) || {}).short_name || `#${id}`;
  const hm = m => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
  const winList = Object.entries(p.windows || {})
    .map(([k, w]) => `${esc(k)} = ${hm(w.start_minute)}–${hm(w.end_minute)}`).join('; ');
  const groups = Array.isArray(p.groups) ? p.groups : Object.keys(p.groups || {});
  host.innerHTML = `
    <h3 class="panel-title">Справочники движка v7.1 (CFG-*)</h3>
    <div class="stat-grid">
      <div class="stat"><div class="k">Шаг расчёта</div><div class="v">${p.step_minutes} мин</div></div>
      <div class="stat"><div class="k">Лимит опоздания</div><div class="v">${p.late_limit_minutes} мин</div></div>
      <div class="stat"><div class="k">Период</div><div class="v" style="font-size:16px">${p.period_granularity === 'half_month' ? 'полмесяца' : 'месяц'}</div></div>
      <div class="stat"><div class="k">Действует с</div><div class="v" style="font-size:16px">${data.active.valid_from ? dateRu(data.active.valid_from) : 'по умолчанию'}</div></div>
    </div>
    <p class="hint" style="margin-top:-6px">Каскад (CFG-CASCADE): банк → ${p.cascade_order.map(esc).join(' → ')}.
      Порядок размещения (CFG-PLACEMENT): ${p.placement_order.map(esc).join(' → ')}.
      Веса (CFG-WEIGHTS): ${Object.entries(p.weights).map(([k, w]) => `${esc(k)}=${w}`).join(', ')}.
      Группы (CFG-GROUPS): ${groups.map(esc).join(', ')}.</p>
    <p class="hint">Окна (CFG-WINDOWS): ${winList}. План карточки = длина окна; недостача и
      ёмкость переносов — от окна. Информационный план строки Табеля может быть меньше
      длины окна (зарплатная норма, например обед).</p>
    <details><summary>Редактировать справочники (JSON)</summary>
      <textarea id="es-json" style="width:100%;min-height:320px;font-family:monospace;font-size:12px" ${edit ? '' : 'readonly'}>${esc(JSON.stringify(p, null, 2))}</textarea>
      ${edit ? `<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:end;margin-top:8px">
        <label class="field" style="margin:0"><span>Действует с (1 или 16 число)</span><input type="date" id="es-from" value="${first}"></label>
        <!-- версия выбирается по дате НАЧАЛА периода: дата внутри месяца фактически
             означает «с первого числа следующего» (base_version(period.start)) -->
        <label class="field" style="margin:0;flex:1"><span>Комментарий</span><input type="text" id="es-note" placeholder="что и почему меняем"></label>
        <button class="btn btn-primary" id="es-save">Сохранить новую версию</button></div>
        <p class="hint">Перед сохранением конфигурация проверяется правилами CHK-* уровня 1;
          все нарушения выводятся разом. Шаг и гранулярность меняются только с границы периода.
          Закрытые периоды не пересчитываются автоматически.</p>` : ''}
    </details>
    <details style="margin-top:8px"><summary>История версий (${data.versions.length})</summary>
      ${data.versions.map(v => `<div class="audit-item"><span class="ts">${dateRu(v.valid_from)}</span><span class="ac">#${v.id}</span>
        <span style="color:var(--muted)">${esc(v.created_by)} · ${esc(v.note)}</span></div>`).join('')}</details>
    <h3 class="panel-title" style="margin-top:16px">Модификаторы дня (CFG-MODIFIERS) · ${MONTHS[state.month - 1]} ${state.year}</h3>
    <p class="hint" style="margin-top:-6px">Дни двойной оплаты и ВИП-гости тоже действуют как «Двойные переработки».
      Приоритет: сотрудник+день → сотрудник+период → группа+день → группа+период → все+день → все+период → глобальный дефолт.
      «План=Факт = Авто» разрешается в «Да» только колонкой кода (стартово — у «К»).
      Две записи одного уровня на один день — конфликт конфигурации.</p>
    <div class="table-wrap"><table class="data"><thead><tr><th>Модификатор</th><th>Значение</th><th>Кому</th><th>Когда</th><th>Комментарий</th><th></th></tr></thead><tbody>
      ${mods.map(m => `<tr><td>${esc(V4_MOD_TITLES[m.name] || m.name)}</td><td>${m.value === '1' ? 'Да' : (m.value === '0' ? 'Нет' : 'Авто')}</td>
        <td>${m.employee_id ? esc(empName(m.employee_id)) : (m.group ? 'группа «' + esc(m.group) + '»' : 'все')}</td>
        <td>${m.date ? dateRu(m.date) : 'весь период'}</td><td>${esc(m.note)}</td>
        <td>${edit ? `<button class="btn btn-sm btn-ghost" data-mod-del="${m.id}">✕</button>` : ''}</td></tr>`).join('') || '<tr><td colspan="6" class="empty">Нет модификаторов в этом месяце</td></tr>'}
    </tbody></table></div>
    ${edit ? `<div class="v4-filters" style="margin-top:8px">
      <label class="field"><span>Модификатор</span><select id="md-name">${data.modifier_names.map(n => `<option value="${n.name}">${esc(n.title)}</option>`).join('')}</select></label>
      <label class="field"><span>Значение</span><select id="md-value"><option value="1">Да</option><option value="0">Нет</option><option value="auto">Авто (План=Факт)</option></select></label>
      <label class="field"><span>Кому</span><select id="md-scope"><option value="all">все</option>
        ${groups.map(g => `<option value="g:${esc(typeof g === 'string' ? g : g.name)}">группа «${esc(typeof g === 'string' ? g : g.name)}»</option>`).join('')}
        ${state.employees.map(e => `<option value="e:${e.id}">${esc(e.short_name)}</option>`).join('')}</select></label>
      <label class="field"><span>День (пусто — весь период)</span><input type="date" id="md-date"></label>
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
