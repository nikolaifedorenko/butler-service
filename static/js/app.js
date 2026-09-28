/* ══════════════════════════════════════════════════════════════════════
   TimeTrack — веб-интерфейс (SPA без сборки), светлая тема
   Разделы: График · Кто на работе · Посещения · Табель · Сотрудники · Мои отметки · Настройки
   Ядро (утилиты, api, состояние, модалки) вынесено в core.js — подключается раньше этого файла.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

/* ───────────────────────────── вкладки ───────────────────────────── */
const ICONS = {
  schedule: '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="16" rx="2" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M3 10h18M8 3v4M16 3v4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  attendance: '<svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.4" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M5 20c1.2-3.6 3.9-5.4 7-5.4s5.8 1.8 7 5.4" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/></svg>',
  onwork: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.8" fill="none"/><circle cx="12" cy="12" r="3.6" fill="currentColor"/><path d="M12 3v2.2M12 18.8V21M3 12h2.2M18.8 12H21" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  timesheet: '<svg viewBox="0 0 24 24"><path d="M5 3h14v18l-3-2-2 2-2-2-2 2-2-2-3 2z" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/><path d="M9 8h6M9 12h6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  employees: '<svg viewBox="0 0 24 24"><circle cx="9" cy="8" r="3.2" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M3 20c.9-3.3 3.2-5 6-5s5.1 1.7 6 5" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/><path d="M16 11h5M18.5 8.5v5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  me: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M12 7v5l3.5 2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" fill="none"/></svg>',
  night: '<svg viewBox="0 0 24 24"><path d="M20 13.5A8.5 8.5 0 0 1 10.5 4 8.5 8.5 0 1 0 20 13.5z" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/></svg>',
  cars: '<svg viewBox="0 0 24 24"><path d="M4 16v-3.2L6.2 8h11.6L20 12.8V16" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/><rect x="3" y="15" width="18" height="4.5" rx="1.6" stroke="currentColor" stroke-width="1.8" fill="none"/><circle cx="7.3" cy="17.2" r="1" fill="currentColor"/><circle cx="16.7" cy="17.2" r="1" fill="currentColor"/></svg>',
  settings: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M12 3v2.5M12 18.5V21M4.2 7.5l2.2 1.3M17.6 15.2l2.2 1.3M4.2 16.5l2.2-1.3M17.6 8.8l2.2-1.3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
};

function visibleTabs() {
  const manager = state.user?.role !== 'employee';
  const tabs = [];
  tabs.push({ id: 'schedule', title: 'График' });   // план видят все; батлеры — только просмотр
  tabs.push({ id: 'onwork', title: 'Кто на работе' });   // реально check-in сейчас — доступно всем
  if (manager) tabs.push({ id: 'attendance', title: 'Посещения' });
  if (manager) tabs.push({ id: 'timesheet', title: 'Табель' });
  if (manager) tabs.push({ id: 'employees', title: 'Сотрудники' });
  tabs.push({ id: 'me', title: 'Мои отметки' });
  tabs.push({ id: 'night', title: 'Ночной отчёт' });   // смена 20:00–08:00: доступен всем
  tabs.push({ id: 'cars', title: 'Электрокары' });     // парк каров: доступен всем
  if (manager) tabs.push({ id: 'settings', title: 'Настройки' });
  return tabs;
}

function renderNav() {
  const tabs = visibleTabs();
  $('#sidenav').querySelectorAll('.nav-item').forEach(el => el.remove());
  const foot = $('#sidenav-foot');
  tabs.forEach(t => {
    const b = document.createElement('button');
    b.className = 'nav-item' + (state.view === t.id ? ' active' : '');
    b.dataset.view = t.id;
    b.innerHTML = `${ICONS[t.id]}<span>${esc(t.title)}</span>`;
    b.onclick = () => navigate(t.id);
    $('#sidenav').insertBefore(b, foot);
  });
  $('#tabbar').innerHTML = tabs.slice(0, 5).map(t =>
    `<button data-view="${t.id}" class="${state.view === t.id ? 'active' : ''}">${ICONS[t.id]}<span>${esc(t.title)}</span></button>`
  ).join('');
  $$('#tabbar button').forEach(b => b.onclick = () => navigate(b.dataset.view));
  if (tabs.length > 5) {
    const more = document.createElement('button');
    more.className = 'nav-item' + (tabs.slice(5).some(t => t.id === state.view) ? ' active' : '');
    more.innerHTML = `${ICONS.settings}<span>Ещё</span>`;
    more.onclick = () => openModal({
      title: 'Разделы',
      body: tabs.slice(5).map(t => `<button class="btn btn-block" style="justify-content:flex-start;margin-bottom:8px" data-more="${t.id}">${ICONS[t.id] || ''} ${esc(t.title)}</button>`).join(''),
      onMount(m) { $$('[data-more]', m).forEach(b => b.onclick = () => { closeModal(); navigate(b.dataset.more); }); },
    });
    $('#sidenav').insertBefore(more, foot);
  }
  foot.innerHTML = `Учёт кратен часу<br>ДН 22:00–06:00 · ДЯ 06:00–22:00<br>Ночная смена относится к дате начала`;
}

function navigate(view) {
  state.view = view;
  $('#sidenav').classList.remove('open');
  $$('.view').forEach(v => v.classList.remove('active'));
  const el = $(`#view-${view}`);
  if (el) el.classList.add('active');
  renderNav();
  clearTimers();
  /* Загрузчики разделов ищем по имени в глобальной области, а не прямыми ссылками:
     если функция раздела не загрузилась (старый кэш, ошибка в файле раздела), интерфейс
     не падает целиком — показывается внятная заглушка вместо пустого экрана. */
  /* Загрузчики разделов — ленивые обёртки, а не строковые имена.
     Карта строится всегда (даже если функция раздела отсутствует), а ошибка
     всплывает в момент ВЫЗОВА и обрабатывается catch'ем ниже: вместо пустого
     экрана пользователь видит заглушку с причиной. Прямые ссылки нужны ещё и
     затем, чтобы линтер ловил отсутствующую функцию статически (no-undef):
     раньше здесь был `window[fnName]`, и потерянный loadNight не видел ни один
     инструмент — интерфейс просто молча пустел. */
  const LOADERS = {
    schedule: () => loadSchedule(), onwork: () => loadOnwork(),
    attendance: () => loadAttendance(), timesheet: () => loadTimesheet(),
    employees: () => loadEmployees(), me: () => loadMe(),
    night: () => loadNight(), cars: () => loadCars(),
    settings: () => loadSettings(),
  };
  const run = LOADERS[view] || (() => {
    if (!el) return;
    el.innerHTML = `<div class="panel"><h3 class="panel-title">Раздел не найден</h3>
      <p class="hint">Неизвестный раздел <code>${esc(view)}</code>. Обновите страницу
      с очисткой кэша (Cmd/Ctrl+Shift+R).</p></div>`;
  });
  Promise.resolve().then(run).catch(err => {
    console.error(err);
    if (el) el.innerHTML = `<div class="panel"><h3 class="panel-title">Раздел не загрузился</h3>
      <p style="color:var(--danger);font-weight:600">${esc(err?.message || err)}</p>
      <p class="hint">Что сделать: 1) обновите страницу с очисткой кеша (Cmd/Ctrl+Shift+R);
      2) перезапустите сервер (Ctrl+C и ./run.sh) — миграции применяются при старте;
      3) откройте http://127.0.0.1:8000/api/selfcheck — он покажет, не отстаёт ли схема БД;
      4) если ошибка повторяется, пришлите хвост server.log и текст из консоли браузера (F12 → Console).</p></div>`;
  });
}

window.addEventListener('unhandledrejection', e => {
  console.error('unhandled:', e.reason);
  toast('Ошибка интерфейса: ' + (e.reason?.message || e.reason || 'неизвестная') +
        ' — обновите страницу (Cmd/Ctrl+Shift+R)', 'err');
});
function clearTimers() {
  state.timers.forEach(t => clearInterval(t)); state.timers = [];
  pollers.length = 0;
}
/* Периодическое обновление раздела. Создавать ОДИН раз при открытии раздела (не в render/fetch —
   иначе каждый тик добавляет новый интервал и их число удваивается). В фоне не опрашиваем. */
const pollers = [];
function poll(view, fn, ms = 30000) {
  if (pollers.some(x => x.view === view)) return;   // повторный вызов loadX() не плодит интервалы
  const tick = () => { if (state.view === view && !document.hidden) fn(); };
  state.timers.push(setInterval(tick, ms));
  pollers.push({ view, fn });
}
document.addEventListener('visibilitychange', () => {
  if (document.hidden) return;
  // вернулись в приложение — сразу освежаем текущий раздел, не дожидаясь тика
  const p = pollers.filter(x => x.view === state.view).pop();
  if (p) p.fn();
});

/* ───────────────────────────── вход ───────────────────────────── */


function showLogin() {
  clearTimers();
  $('#app').classList.add('hidden');
  $('#login-screen').classList.remove('hidden');
}

async function enterApp() {
  $('#login-screen').classList.add('hidden');
  $('#app').classList.remove('hidden');
  renderUserChip();
  try {
    const chk = await api('/api/selfcheck', { silent: true, allow401: true });
    if (chk && chk.ok === false) {
      toast('Внимание: схема БД отстаёт от кода. ' + (chk.hint || ''), 'err', chk.missing.slice(0, 6));
    }
  } catch { /* самодиагностика недоступна — не критично */ }
  if (state.user.role !== 'employee') {
    try {
      await loadDirectory();
    } catch (e) {
      // справочник не загрузился — не блокируем интерфейс: разделы покажут свои ошибки
      toast('Справочники не загрузились: ' + (e.message || e) +
            ' — откройте Console/Network и пришлите ошибку', 'err');
    }
  }
  navigate(state.user.role !== 'employee' ? 'schedule' : 'me');
}

function renderUserChip() {
  const u = state.user;
  $('#user-name').textContent = u.name;
  $('#user-role').textContent = ROLE_TITLES[u.role] || u.role;
  $('#user-avatar').textContent = initials(u.name);
  $('#impersonation-bar').classList.toggle('hidden', !u.impersonated);
}

async function loadDirectory() {
  const [emps, types] = await Promise.all([api('/api/employees'), api('/api/shift-types')]);
  state.employees = emps;
  state.shiftTypes = types;
  try {
    const [deps, subs] = await Promise.all([api('/api/departments', { silent: true }),
                                            api('/api/subdivisions', { silent: true })]);
    state.departments = deps; state.subdivisions = subs;
  } catch { /* справочник недоступен — редактор сотрудника обойдётся кешем */ }
  try {
    const kd = await api('/api/docs/kinds', { silent: true });
    state.docKinds = kd.kinds || []; state.docPlaceholders = kd.placeholders || {};
  } catch { state.docKinds = state.docKinds || []; }
}

/* ══════════════════════════════════════════════════════════════════
   ГРАФИК: блоки смен, цвета должностей, произвольные циклы
   ══════════════════════════════════════════════════════════════════ */
async function loadSchedule() {
  $('#view-schedule').innerHTML = scheduleShell();
  bindScheduleToolbar();
  if (state.user?.role === 'employee' && !state.shiftTypes.length) {
    // легенде сетки нужен словарь смен (справочник сотрудников батлерам недоступен)
    try { state.shiftTypes = await api('/api/shift-types', { silent: true }); } catch { state.shiftTypes = []; }
  }
  const data = await api(`/api/schedule?year=${state.year}&month=${state.month}`);
  state.grid = data;
  state.scrollToToday = true;    // после загрузки месяца докрутить сетку к сегодняшнему числу
  renderGrid();
}

function scheduleShell() {
  const ro = state.user?.role === 'employee';   // батлеры: график только на просмотр
  return `
  <div class="page-head">
    <div>
      <h2>График смен</h2>
      <div class="sub">${ro
        ? 'План смен на месяц — так же, как его видит менеджер. Правки вносит менеджер'
        : `Смены 1/2 считаются базовым циклом объекта (Настройки); у «Пятидневки» и «Других смен»
        шаблон задаётся в карточке сотрудника. Вручную назначают только отсутствия и исключения`}</div>
    </div>
    <div class="spacer"></div>
    <div class="month-nav">
      <button id="m-prev" title="Предыдущий месяц">‹</button>
      <div class="label" id="m-label">—</div>
      <button id="m-next" title="Следующий месяц">›</button>
    </div>
    <button class="btn btn-sm" id="m-today">Сегодня</button>
  </div>
  ${ro ? `<div class="ro-banner">Режим «только просмотр»: виден план смен без отметок,
    переработок и часов. Назначать и менять смены может менеджер.</div>` : ''}

  <div class="grid-tools">
    <input id="f-text" type="text" placeholder="Поиск по ФИО…" style="max-width:210px">
    <div class="seg" id="color-mode" title="Чем красить рабочие ячейки">
      <button data-mode="shift">Цвет смен</button>
      <button data-mode="position">Цвет должностей</button>
    </div>
    ${ro ? '' : `<div class="seg" id="grid-mode" title="План — как по графику; Факт — реальное присутствие по отметкам">
      <button data-mode="plan">План</button>
      <button data-mode="fact">Факт</button>
    </div>`}
    <div class="spacer" style="flex:1"></div>
    ${ro ? '' : `<button class="btn btn-sm" id="btn-range">Назначить отсутствие</button>
    <button class="btn btn-sm" id="btn-clear">Обнулить месяц</button>
    <button class="btn btn-sm" id="btn-xlsx">Excel</button>`}
    <button class="btn btn-sm btn-ghost" id="btn-print">Печать</button>
    <button class="btn btn-sm btn-ghost" id="btn-pdf" title="Скачать PDF: файл собирает сервер">PDF</button>
  </div>

  <div class="grid-scroll" id="grid-host"><div class="empty">Загрузка…</div></div>
  <div class="legend" id="grid-legend"></div>`;
}

function bindScheduleToolbar() {
  const shiftMonth = delta => {
    let m = state.month + delta, y = state.year;
    if (m < 1) { m = 12; y--; } if (m > 12) { m = 1; y++; }
    state.month = m; state.year = y; loadSchedule();
  };
  $('#m-prev').onclick = () => shiftMonth(-1);
  $('#m-next').onclick = () => shiftMonth(1);
  $('#m-today').onclick = () => { const d = new Date(); state.year = d.getFullYear(); state.month = d.getMonth() + 1; loadSchedule(); };
  const ro = state.user?.role === 'employee';
  if (ro) state.gridMode = 'plan';   // «Факт» — данные менеджера, у батлера их нет в ответе
  $('#btn-print').onclick = printGrid;
  $('#btn-pdf').onclick = () => downloadBlob(`/api/schedule/pdf?year=${state.year}&month=${state.month}`, 'grafik.pdf');
  if ($('#btn-xlsx')) $('#btn-xlsx').onclick = () => downloadBlob(`/api/schedule/xlsx?year=${state.year}&month=${state.month}`, 'grafik.xlsx');
  if ($('#btn-range')) $('#btn-range').onclick = openRangeModal;
  if ($('#btn-clear')) $('#btn-clear').onclick = () => confirmDialog(
    'Обнулить месяц?',
    `Ручные правки за ${MONTHS[state.month - 1]} ${state.year} (отпуска, больничные, ночные, подмены) будут удалены,
     месяц вернётся к базовому циклу объекта. История табеля по отметкам сохранится.`,
    async () => {
      const r = await api('/api/schedule/clear-month', { method: 'POST', body: { year: state.year, month: state.month } });
      toast(`График обнулён: удалено ${r.deleted} ячеек`, 'ok');
      loadSchedule();
    });

  $('#f-text').value = state.filterText;
  $('#f-text').oninput = e => { state.filterText = e.target.value; renderGrid(); };

  $$('#color-mode button').forEach(b => {
    b.classList.toggle('active', b.dataset.mode === state.colorMode);
    b.onclick = () => {
      state.colorMode = b.dataset.mode;
      localStorage.setItem('tt_color_mode', state.colorMode);
      $$('#color-mode button').forEach(x => x.classList.toggle('active', x === b));
      renderGrid();
    };
  });

  $$('#grid-mode button').forEach(b => {
    b.classList.toggle('active', b.dataset.mode === state.gridMode);
    b.onclick = () => {
      state.gridMode = b.dataset.mode;
      localStorage.setItem('tt_grid_mode', state.gridMode);
      $$('#grid-mode button').forEach(x => x.classList.toggle('active', x === b));
      renderGrid();
    };
  });
}

const GROUP_ORDER_UI = ['Смена 1', 'Смена 2', 'Пятидневка', 'Другие смены'];
function groupOrder(name) {
  const n = name === 'Администрация' ? 'Пятидневка' : (name || '');   // старое название блока
  const i = GROUP_ORDER_UI.indexOf(n);
  if (i >= 0) return i;
  if (!name) return 999;
  return 100 + name.localeCompare(name, 'ru');
}

function filteredRows() {
  const q = state.filterText.trim().toLowerCase();
  return (state.grid?.rows || []).filter(r => {
    if (q && !r.employee.full_name.toLowerCase().includes(q) && !(r.employee.position || '').toLowerCase().includes(q)) return false;
    return true;
  });
}

function renderGrid() {
  const g = state.grid;
  if (!g) return;
  $('#m-label').textContent = `${MONTHS[g.month - 1]} ${g.year}`;
  const rows = filteredRows();
  if (!rows.length) {
    $('#grid-host').innerHTML = '<div class="empty">Сотрудники не найдены</div>';
  } else {
    const head = `<tr><th class="corner">ФИО</th>${g.days.map(d =>
      `<th class="${d.is_weekend ? 'weekend' : ''} ${d.is_today ? 'today' : ''}${d.double_scope ? ' double-day' : ''}"
        title="${dateRu(d.date)}${d.double_scope ? ' · день двойной оплаты (' + (d.double_title || '') + '): переработки идут кодами ДЯ2/ДН2' : ''}">
        <span class="dow">${esc(d.weekday)}</span>${d.day}${d.double_scope ? '<span class="dbl-mark">×2</span>' : ''}</th>`).join('')}<th>Итого</th></tr>`;

    /* блоки: Смена 1, Смена 2, Пятидневка, Другие смены; сотрудник виден в каждом своём блоке */
    const blocksOf = r => (r.blocks && r.blocks.length)
      ? r.blocks
      : (r.employee.schedule_group
        ? [{ group: r.employee.schedule_group, start: '0000-01-01', end: null }] : []);
    const groups = {};
    rows.forEach(r => blocksOf(r).forEach(b => { (groups[b.group] ||= []).push({ r, b }); }));
    rows.forEach(r => { if (!blocksOf(r).length) (groups[''] ||= []).push({ r, b: null }); });
    const keys = Object.keys(groups).sort((a, b) =>
      groupOrder(a) - groupOrder(b) || a.localeCompare(b, 'ru'));

    const body = keys.map(key => {
      const list = groups[key];
      const color = list[0]?.r.employee.group_color || '#8a94a6';
      /* заголовок блока: первая ячейка «липкая» — не уезжает при горизонтальной прокрутке,
         остальную строку заполняет ячейка-фон (исправление уезжавших заголовков) */
      const header = `<tr class="group-row"><td class="g-name">
        <span class="g-dot" style="background:${color}"></span>${esc(key || 'Без группы')}
        <span class="g-count">${list.length} ${plural(list.length, 'сотрудник', 'сотрудника', 'сотрудников')}</span></td>
        <td class="gfill" colspan="${g.days.length + 1}"></td></tr>`;
      return header + list.map(({ r, b }) => empRow(r, g, b)).join('');
    }).join('');

    $('#grid-host').innerHTML = `<table class="sched"><thead>${head}</thead><tbody>${body}</tbody></table>`;
    if (state.user?.role === 'employee') {
      $('#grid-host').classList.add('ro');   // только просмотр: клики по ячейкам отключены
    } else {
      $$('#grid-host .cellbtn:not([disabled])').forEach(btn => btn.onclick = () => openCellModal(+btn.dataset.emp, btn.dataset.date));
    }
    if (state.scrollToToday) { state.scrollToToday = false; scrollGridToToday(); }
  }

  const shGroups = { work: [], absence: [] };
  state.shiftTypes.forEach(sh => (shGroups[sh.kind] || shGroups.absence).push(sh));
  $('#grid-legend').innerHTML = [...shGroups.work, ...shGroups.absence].map(sh =>
    `<span class="chip" title="${esc(sh.name)}"><span class="swatch" style="background:${sh.color}"></span>
      <b>${esc(sh.kind === 'work' ? `${sh.start_time}–${sh.end_time}` : sh.name)}</b>
      ${sh.kind === 'work' ? `${hours(sh.planned_hours)} ч` : esc(sh.tzh_code)}</span>`).join('') +
    `<span class="chip" title="Сотрудник вышел в свой выходной — часы начислены как переработка">
      <span class="swatch" style="background:${state.grid?.colors?.worked_off || '#7c3aed'}"></span><b>работа в выходной</b></span>
     <span class="chip" title="Дни относятся к другому блоку (переход между сменами)">
      <span class="swatch" style="background:${state.grid?.colors?.out_of_block || '#d8d3e8'}"></span><b>дни другой смены</b></span>
     <span class="chip" title="Производственный календарь / ВИП-гости: переработки в эти дни оплачиваются вдвое (коды ДЯ2/ДН2). Календарь — в разделе «Настройки»">
      <span class="dbl-mark legend-x2">×2</span><b>день двойной оплаты</b></span>`;
}

/* Кнопка «Сегодня»: месяц открыт, а сетка докручивается до сегодняшней колонки и подсвечивает её */
function scrollGridToToday() {
  const host = $('#grid-host');
  if (!host) return;
  requestAnimationFrame(() => {
    const th = host.querySelector('thead th.today');
    if (!th) return;
    const left = Math.max(0, th.offsetLeft - host.clientWidth / 2 + th.clientWidth / 2);
    host.scrollTo({ left, behavior: 'smooth' });
    th.classList.add('flash-today');
    setTimeout(() => th.classList.remove('flash-today'), 1800);
  });
}

/* Вид «Факт»: интервалы реальной работы в ячейке («08–12 15–24»), отклонения, отсутствия */
function factCellTd(r, d, c, cls) {
  const f = c.fact || {};
  const btn = (extra, inner, title) =>
    `<td class="${cls}"><button class="cellbtn ${extra}" data-emp="${r.employee.id}" data-date="${d.date}" title="${esc(title)}">${inner}</button></td>`;
  const ivs = f.intervals || [];
  const t = x => x === '24:00' ? '24' : (x.endsWith(':00') ? x.slice(0, 2) : x.slice(0, 5));
  if (ivs.length) {
    const iv = ivs.map(([a, b]) => `${t(a)}–${t(b)}`).join(' ');
    const mk = [];
    if (f.late_hours > 0) mk.push(`<span class="late" title="Опоздание ${hours(f.late_hours)} ч">Л${hours(f.late_hours)}</span>`);
    if (f.early_hours > 0) mk.push(`<span class="early" title="Ранний уход ${hours(f.early_hours)} ч">РУ${hours(f.early_hours)}</span>`);
    if (f.gap_hours > 0) mk.push(`<span class="gapm" title="Несогласованный перерыв внутри смены ${hours(f.gap_hours)} ч">ПР${hours(f.gap_hours)}</span>`);
    if (f.ot_hours > 0) mk.push(`<span class="ot" title="Переработка ${hours(f.ot_hours)} ч">+${hours(f.ot_hours)}</span>`);
    if (f.open_now) mk.push('<span title="Сотрудник ещё на работе — смена не закрыта">●сейчас</span>');
    if (f.auto_closed) mk.push('<span class="gapm" title="Смена закрыта автоматически">авто</span>');
    const klass = f.attention ? 'fact-att' : 'fact-ok';
    const title = `${r.employee.short_name}, ${dateRu(d.date)}: работал ${iv} · учтено ${hours(f.counted_hours)} ч`
      + (f.attention ? ` · требует внимания: ${statusTitle(f.status)}` : '')
      + (f.from_prev ? ' · хвост вчерашней ночной смены' : '') + (f.to_next ? ' · продолжается в следующих сутках' : '')
      + (c.partial ? ` · отпросился ${c.partial.from_time}–${c.partial.until_time}` : '');
    return btn(`${klass}${f.open_now ? ' fact-open' : ''}`,
      `<span class="iv">${esc(iv)}</span>${mk.length ? `<span class="mk">${mk.join('')}</span>` : ''}`
      + (c.partial ? '<span class="partial-mark">отпр</span>' : ''), title);
  }
  const sh = c.shift;
  if (f.absence_code) {
    return btn('fact-abs', `<span class="t t-short">${esc(f.absence_code)}</span>`,
      `${dateRu(d.date)}: ${statusTitle(f.status) || 'отсутствие'} · ${esc(sh ? sh.name : f.absence_code)}`);
  }
  if (sh && sh.kind === 'work') {
    if (d.date > (state.grid?.today || '')) {
      return btn('empty', `<span class="t t-short">${esc(sh.display_code || '')}</span>`,
        'Смена впереди — факт появится после отметок');
    }
    return btn('fact-att', '<span class="t t-short">НН?</span>',
      'По графику рабочая смена, но отметок нет. Откройте ячейку, чтобы зафиксировать неявку (НН) или причину');
  }
  if (!f.has_row) {
    return btn('empty', '—', 'Нет данных');
  }
  return btn('fact-abs', '—', `${dateRu(d.date)}: ${statusTitle(f.status) || 'нет работы'}`);
}

function empRow(r, g, block) {
  const accent = r.employee.group_color || '#8a94a6';
  const ranges = block?.ranges || (block ? [{ start: block.start, end: block.end }] : []);
  const inBlock = iso => !ranges.length || ranges.some(rg =>
    iso >= rg.start && (!rg.end || iso <= rg.end));
  const cells = g.days.map(d => {
    const c = r.cells[d.date] || {};
    const sh = c.shift;
    const cls = ['cell', d.is_weekend ? 'weekend' : '', d.is_today ? 'today' : ''].join(' ');
    const outOfBlock = ranges.length && !inBlock(d.date);
    if (outOfBlock) {
      return `<td class="${cls}"><button class="cellbtn" disabled
        title="Неактивно: в этот день сотрудник относится к другому блоку"
        style="background:${g.colors.out_of_block};color:#5d5670;cursor:default">—</button></td>`;
    }
    if (c.employed === false) {
      return `<td class="${cls}"><button class="cellbtn inactive" disabled
        title="Неактивно: сотрудник не работал в эту дату (до приёма, после увольнения или между периодами работы)">—</button></td>`;
    }
    if (state.gridMode === 'fact') return factCellTd(r, d, c, cls);
    if (!sh) {
      return `<td class="${cls}"><button class="cellbtn empty" data-emp="${r.employee.id}" data-date="${d.date}" title="Не заполнено">—</button></td>`;
    }
    if (c.worked_off) {
      return `<td class="${cls}"><button class="cellbtn" data-emp="${r.employee.id}" data-date="${d.date}"
        title="Работа в выходной: ${hours(c.fact_hours)} ч начислено"
        style="background:linear-gradient(165deg, ${withAlpha(g.colors.worked_off, .95)}, ${withAlpha(g.colors.worked_off, .75)});color:#fff">
        <span class="t t-full">РАБ ${hours(c.fact_hours)}</span><span class="t t-short">Р${hours(c.fact_hours)}</span></button></td>`;
    }
    const baseColor = (state.colorMode === 'position' && sh.kind === 'work') ? accent : sh.color;
    const mainFull = sh.kind === 'work' ? `${sh.start.slice(0, 5)}–${sh.end.slice(0, 5)}` : (sh.display_code || sh.name);
    const mainShort = sh.kind === 'work' ? (sh.display_code || `${sh.start.slice(0, 2)}–${sh.end.slice(0, 2)}`) : (sh.display_code || sh.name);
    const sub = sh.kind === 'work' ? (sh.overnight ? 'ночная' : `${hours(sh.planned_hours)} ч`) : '';
    const style = `background:linear-gradient(165deg, ${withAlpha(baseColor, .96)}, ${withAlpha(baseColor, .78)});color:${textOn(baseColor)}`;
    const pt = c.partial;
    const ptTitle = pt ? ` · отпросился с ${pt.from_time} до ${pt.until_time} (${hours(pt.hours)} ч${pt.reason ? ', ' + pt.reason.name : ''})` : '';
    const ptMark = pt ? `<span class="partial-mark" title="Согласованное отсутствие части смены">${pt.from_time.slice(0, 2)}–${pt.until_time.slice(0, 2)}</span>` : '';
    return `<td class="${cls}">
      <button class="cellbtn" style="${style}" data-emp="${r.employee.id}" data-date="${d.date}"
              title="${esc(sh.name)}${c.auto ? ' · по базовому циклу' : ''}${ptTitle}${c.note ? ' · ' + esc(c.note) : ''}">
        ${c.note ? '<span class="dot-note"></span>' : ''}${ptMark}
        <span class="t t-full">${esc(mainFull)}</span><span class="t t-short">${esc(mainShort)}</span>${sub ? `<span class="s">${esc(sub)}</span>` : ''}
      </button></td>`;
  }).join('');
  return `<tr class="emp-row">
    <td class="name-cell" style="box-shadow: inset 4px 0 0 ${accent}">
      <div class="nm" title="${esc(r.employee.full_name)}">${esc(r.employee.short_name || r.employee.full_name)}</div>
      <div class="pos"><span class="dot-pos" style="background:${accent}"></span>${esc(r.employee.position || '')}</div>
      <div class="tot">${hours(r.totals.planned_hours)} ч · ${r.totals.work_days} ${plural(r.totals.work_days, 'смена', 'смены', 'смен')}</div>
    </td>${cells}
    <td class="num" style="padding:8px 10px;font-weight:700">${hours(r.totals.planned_hours)}<small style="color:var(--muted);font-weight:400"> ч</small></td>
  </tr>`;
}

/* ── печать отдельных документов (чистое окно: весь месяц, без служебных элементов) ── */
function printWindow(title, bodyHtml) {
  const w = window.open('', '_blank', 'width=1200,height=800');
  if (!w) { toast('Браузер заблокировал окно печати — разрешите всплывающие окна', 'warn'); return; }
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${esc(title)}</title>
    <style>
      @page { size: A4 landscape; margin: 10mm; }
      body { font-family: -apple-system, 'Segoe UI', Roboto, Arial, sans-serif; color: #1a2438; font-size: 11px; }
      h1 { font-size: 16px; margin: 0 0 2mm; }
      table { border-collapse: collapse; width: 100%; }
      th, td { border: 1px solid #b9c2d0; padding: 1.2mm 1mm; text-align: center; font-size: 9px; }
      th.name, td.name { text-align: left; padding-left: 2mm; width: 52mm; font-size: 10px; }
      tr.group td { background: #eef2f8; font-weight: 700; text-align: left; padding-left: 2mm; font-size: 10px; }
      .muted { color: #8b98ad; }
    </style></head><body>${bodyHtml}<script>window.onload = () => { window.print(); };<\/script></body></html>`);
  w.document.close();
}

function printGrid() {
  const g = state.grid;
  if (!g) return;
  const rows = filteredRows();
  const groups = {};
  rows.forEach(r => (r.blocks || []).forEach(b => { (groups[b.group] ||= []).push({ r, b }); }));
  const keys = Object.keys(groups).sort((a, b) => groupOrder(a) - groupOrder(b));
  const body = keys.map(key => {
    const trs = groups[key].map(({ r, b }) => {
      const rgs = (b && b.ranges) || (b ? [{ start: b.start, end: b.end }] : []);
      const tds = g.days.map(d => {
        const c = r.cells[d.date] || {};
        const out = rgs.length && !rgs.some(rg => d.date >= rg.start && (!rg.end || d.date <= rg.end));
        if (c.employed === false) return `<td style="background:${g.colors.inactive || '#eceff4'};color:#98a2b3">—</td>`;
        if (out) return `<td style="background:${g.colors.out_of_block}">—</td>`;
        if (c.worked_off) return `<td style="background:${g.colors.worked_off};color:#fff">РАБ ${hours(c.fact_hours)}</td>`;
        if (!c.shift) return `<td class="muted"></td>`;
        let txt = c.shift.kind === 'work' ? `${c.shift.start}–${c.shift.end}` : (c.shift.display_code || c.shift.name);
        if (c.partial) txt += '*';
        return `<td style="background:${withAlpha(c.shift.color, .25)}">${esc(txt)}</td>`;
      }).join('');
      return `<tr><td class="name">${esc(r.employee.full_name)}<br><span class="muted">${esc(r.employee.position || '')}</span></td>${tds}
        <td><b>${hours(r.totals.planned_hours)}</b></td></tr>`;
    }).join('');
    return `<tr class="group"><td colspan="${g.days.length + 2}">${esc(key.toUpperCase())}</td></tr>${trs}`;
  }).join('');
  const head = `<tr><th class="name">Сотрудник</th>${g.days.map(d =>
    `<th>${d.day}<br><span class="muted">${esc(d.weekday)}</span></th>`).join('')}<th>Часов</th></tr>`;
  printWindow(`График сменности ${MONTHS[g.month - 1]} ${g.year}`,
    `<h1>График сменности, ${MONTHS[g.month - 1]} ${g.year} г. (весь месяц)</h1>
     <table><thead>${head}</thead><tbody>${body}</tbody></table>`);
}

function printTimesheet() {
  const d = state.timesheet;
  if (!d) return;
  const rowsHtml = d.rows.map(r => `<tr>
    <td class="name">${esc(r.employee.full_name)}<br><span class="muted">${esc(r.employee.position || '')}</span></td>
    <td>${hours(r.totals.planned)}</td><td><b>${hours(r.totals.fact)}</b></td>
    <td>${hours(r.totals.day)}</td><td>${hours(r.totals.night)}</td>
    <td>${hours(r.totals.ot)}</td><td>${hours(r.totals.deficit)}</td><td>${hours(r.totals.timeoff)}</td>
    <td><b>${r.totals.balance >= 0 ? '+' : ''}${hours(r.totals.balance)}</b></td></tr>`).join('');
  printWindow(`Табель ${MONTHS[d.month - 1]} ${d.year}`,
    `<h1>Табель учёта рабочего времени, ${MONTHS[d.month - 1]} ${d.year} г.</h1>
     <table><thead><tr><th class="name">Сотрудник</th><th>План</th><th>Факт</th><th>ДЯ</th><th>ДН</th>
     <th>Перераб.</th><th>Недораб.</th><th>Отгулы</th><th>Банк</th></tr></thead><tbody>${rowsHtml}</tbody></table>
     <p class="muted">Учёт кратен часу. ДН — ночные часы 22:00–06:00. Детализация по дням — в разделе «Табель» или в выгрузке Excel.</p>`);
}

/* ── заявление на отпуск: печать по редактируемому шаблону, период подхватывается целиком ── */
async function getDocTemplates() {
  if (!state.doc) {
    const s = await api('/api/settings', { silent: true });
    state.doc = s.doc;
  }
  try {
    const kd = await api('/api/docs/kinds', { silent: true });
    state.docKinds = kd.kinds || []; state.docPlaceholders = kd.placeholders || {};
  } catch { /* печать продолжим с кешем */ }
  return state.doc;
}

function fillTemplate(tpl, values) {
  return (tpl || '').replace(/\{(\w+)\}/g, (m, k) => (values[k] ?? m));
}

/* Документы по отсутствию: период берётся с сервера ЦЕЛИКОМ — даже когда отпуск
   начинается в одном месяце, а заканчивается в следующем (исправление бага печати). */
async function absencePeriodInfo(empId, dateISO) {
  return await api(`/api/schedule/absence-period?employee_id=${empId}&date=${dateISO}`);
}

function triggerDownload(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

/* DOCX/PDF из корпоративного шаблона (Настройки → Шаблоны документов компании).
   PDF собирается на сервере (LibreOffice или встроенный рендер) и открывается в новой
   вкладке — из неё сразу можно печатать. */
async function downloadAbsenceDoc(empId, dateISO, fmt) {
  let p;
  try { p = await absencePeriodInfo(empId, dateISO); }
  catch (e) {
    return toast(e.message.includes('нет назначенного')
      ? 'Сначала сохраните отсутствие в ячейке — тогда станет доступна печать заявления'
      : e.message, 'err');
  }
  const type = p.shift?.doc_type;
  if (!type) return toast('К этому виду отсутствия не привязан шаблон заявления (Настройки → Словарь смен)', 'warn');
  loading(true);
  try {
    const res = await fetch('/api/docs/render', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type, employee_id: empId, date_from: p.start, date_to: p.end, format: fmt,
        from_time: p.partial?.from_time || '', until_time: p.partial?.until_time || '',
        hours: p.partial ? p.partial.hours : null,
        reason: p.partial?.reason?.name || p.shift?.name || '',
        note: (p.notes || []).join('; '),
      }),
    });
    if (!res.ok) {
      let msg = `Ошибка ${res.status}`;
      try { msg = (await res.json()).detail || msg; } catch {}
      throw new Error(msg);
    }
    const blob = await res.blob();
    const name = (res.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/)?.[1]
      || `document_${empId}.${fmt}`;
    if (fmt === 'pdf') {
      const url = URL.createObjectURL(blob);
      const w = window.open(url, '_blank');
      if (!w) {
        toast('Браузер заблокировал новое окно — PDF скачан файлом; разрешите всплывающие окна для печати', 'warn');
        triggerDownload(blob, name);
      } else {
        setTimeout(() => URL.revokeObjectURL(url), 120000);
        toast('PDF готов — открыт в новой вкладке, можно печатать', 'ok');
      }
    } else {
      triggerDownload(blob, name);
      toast('Документ DOCX скачан — откройте его в Word и печатайте', 'ok');
    }
  } catch (e) { toast(e.message, 'err'); }
  finally { loading(false); }
}

/* Быстрая печать заявления окном браузера (по редактируемому шаблону из Настроек) */
async function printAbsenceRequest(empId, dateISO) {
  let p;
  try { p = await absencePeriodInfo(empId, dateISO); }
  catch (e) {
    return toast(e.message.includes('нет назначенного')
      ? 'Сначала сохраните отсутствие в ячейке — тогда станет доступна печать заявления'
      : e.message, 'err');
  }
  try {
    const doc = await getDocTemplates();
    const kind = (state.docKinds || []).find(k => k.code === p.shift?.doc_type);
    const tplKey = { vacation_paid: 'vacation', vacation_unpaid: 'vacation_unpaid',
                     day_off_hours: 'day_off_hours', time_off_request: 'time_off_request' }[p.shift?.doc_type]
      || 'vacation';
    const tplText = (kind?.text || '').trim() || doc[tplKey] || doc.vacation;
    const e = p.employee || {};
    const vals = {
      company: doc.company, director: doc.director,
      full_name: e.full_name || '', short_name: e.short_name || '',
      full_name_genitive: e.full_name_genitive || e.full_name || '',
      position: e.position || '—', tab_number: e.tab_number || '—',
      nationality: e.nationality || '', subdivision: e.subdivision || '', department: e.department || '',
      group: e.subdivision || '',
      date_from: dateRu(p.start), date_to: dateRu(p.end), days: p.days,
      from_time: p.partial?.from_time || '', until_time: p.partial?.until_time || '',
      hours: p.partial ? hours(p.partial.hours) : '',
      period: p.end === p.start ? dateRu(p.start) : `с ${dateRu(p.start)} по ${dateRu(p.end)}`,
      reason: p.partial?.reason?.name || p.shift?.name || '',
      note: (p.notes || []).join('; '),
      today: dateRu(todayISO()),
    };
    printWindow('Заявление',
      `<div style="white-space:pre-wrap;font-size:13px;line-height:1.7;width:170mm;margin:0 auto">${esc(fillTemplate(tplText, vals))}</div>`);
  } catch (e) { toast(e.message, 'err'); }
}

/* ── назначение периода разом (отпуск на месяц и т.п.) ── */
function openRangeModal() {
  const g = state.grid;
  const first = g.days[0].date;      // конец периода берётся из формы модалки
  const absences = state.shiftTypes.filter(x => x.kind === 'absence' && !x.is_default_off);
  openModal({
    title: 'Назначить отсутствие',
    subtitle: 'Отпуск, больничный, отгул и т.п. на период сразу — в том числе через границы месяцев',
    wide: true,
    body: `
      <div class="opt-group-title">Сотрудники</div>
      <div class="check-list" id="rg-emps">
        ${g.rows.map(r => `<label><input type="checkbox" value="${r.employee.id}">
          ${esc(r.employee.full_name)} <small style="color:var(--muted)">· ${esc(r.employee.position || '')}</small></label>`).join('')}
      </div>
      <div class="grid-2" style="margin-top:14px">
        <label class="field"><span>С</span><input type="date" id="rg-from" value="${first}"></label>
        <label class="field"><span>По (включительно)</span><input type="date" id="rg-to" value="${first}"></label>
      </div>
      <label class="field"><span>Вид отсутствия</span><select id="rg-shift">
        ${absences.map(x => `<option value="${x.id}" ${x.code === 'VACATION' ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}
      </select></label>
      <label class="field"><span>Примечание</span>
        <input type="text" id="rg-note" placeholder="Например: приказ №47 от 01.09.2026"></label>
      <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
        <input type="checkbox" id="rg-work-only" style="width:17px;height:17px;accent-color:var(--primary)">
        Только на рабочие дни по графику (для «выходного за часы»: на плановые выходные не ставится)
      </label>
      <div class="grid-2" style="margin-top:10px">
        <label class="field"><span>Отметки «Пришёл» на период</span><select id="rg-punch-in">
          <option value="">как в словаре вида отсутствия</option>
          <option value="1">разрешить</option>
          <option value="0">запретить</option>
        </select></label>
        <label class="field"><span>Отметки «Ушёл» на период</span><select id="rg-punch-out">
          <option value="">как в словаре вида отсутствия</option>
          <option value="1">разрешить</option>
          <option value="0">запретить</option>
        </select></label>
      </div>
      <p class="hint" style="margin-top:2px">Явный override флага вида отсутствия — сразу на все ячейки периода
        (например, в командировке отмечаться можно, хотя по словарю вида — нельзя).</p>
      <p class="hint">Период может выходить за пределы открытого месяца — например с 28 сентября по 5 октября.
        График заполнится до конца периода, а экран переключится на его первый месяц.
        Дни, когда сотрудник не работал (до приёма / после увольнения) или относился к другому блоку,
        пропускаются автоматически. Рабочие смены назначать не нужно: их считает базовый цикл.</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Назначить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        const ids = $$('#rg-emps input:checked').map(i => +i.value);
        if (!ids.length) return toast('Отметьте сотрудников', 'warn');
        const from = $('#rg-from').value, to = $('#rg-to').value;
        if (!from || !to || from > to) return toast('Проверьте даты периода', 'warn');
        try {
          const ov = sel => { const v = $(sel).value; return v === '' ? null : v === '1'; };
          const res = await api('/api/schedule/range-absence', { method: 'POST', body: {
            employee_ids: ids, start: from, end: to,
            shift_type_id: +$('#rg-shift').value, note: $('#rg-note').value.trim(),
            only_work_days: $('#rg-work-only').checked,
            punch_in_override: ov('#rg-punch-in'), punch_out_override: ov('#rg-punch-out'),
          } });
          closeModal();
          const skipped = (res.skipped_inactive || 0) + (res.skipped_off || 0);
          toast(`Отсутствие назначено: ${res.updated} ${plural(res.updated, 'ячейка', 'ячейки', 'ячеек')}`
            + (res.months?.length > 1 ? ` в ${res.months.length} месяцах` : '')
            + (skipped ? `, пропущено ${skipped} (неактивные дни / выходные)` : ''), 'ok');
          /* период начался в другом месяце — переключаем экран туда, чтобы результат было видно */
          const d0 = new Date(from + 'T12:00:00');
          if (d0.getFullYear() !== state.year || d0.getMonth() + 1 !== state.month) {
            state.year = d0.getFullYear();
            state.month = d0.getMonth() + 1;
          }
          loadSchedule();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ── редактор ячейки графика ── */
function openCellModal(empId, dateISO) {
  const row = state.grid.rows.find(r => r.employee.id === empId);
  const cell = row?.cells?.[dateISO] || {};
  const cur = cell.shift || null;
  let selected = cur && !cur.archived ? cur.id : null;

  const d = new Date(dateISO + 'T00:00:00');
  const title = `${WD[d.getDay()]}, ${d.getDate()} ${MONTHS_GEN[d.getMonth()]} ${d.getFullYear()}`;
  const groups = { work: [], absence: [] };
  state.shiftTypes.forEach(s => (groups[s.kind] || groups.absence).push(s));
  const nnShift = state.shiftTypes.find(x => x.code === 'ABSENT_UNKNOWN');

  const opt = s => `
    <button type="button" class="shift-opt ${selected === s.id ? 'sel' : ''}" data-id="${s.id}">
      <span class="swatch" style="background:${s.color}"></span>
      <span><span class="nm">${esc(s.kind === 'work' ? `${s.start_time}–${s.end_time}` : s.name)}</span>
      <span class="hh">${s.kind === 'work' ? `${hours(s.planned_hours)} ч${s.overnight ? ' · ночная' : ''}` : `код ${esc(s.tzh_code)}${s.deduct_from_bank ? ' · часы из банка' : ''}`}</span></span>
    </button>`;

  openModal({
    title: row?.employee.full_name || 'Сотрудник',
    subtitle: `${title} · ${row?.employee.position || ''}`,
    body: `
      <div class="opt-group-title">Рабочие смены (часы можно добавить в словаре: Настройки)</div>
      <div class="shift-options">${groups.work.map(opt).join('')}</div>
      <div class="opt-group-title">Отсутствие / выходные</div>
      <div class="shift-options">${groups.absence.map(opt).join('')}</div>
      ${cur && cur.archived ? `<p class="hint" style="color:var(--warn)">В ячейке смена из архива (${esc(cur.name)}) —
        она считалась в прошлом, но для новых назначений недоступна.</p>` : ''}
      <div id="partial-block" class="hidden" style="margin-top:12px;border:1px solid var(--line);border-radius:12px;padding:12px 14px 8px;background:#f8fbfd">
        <div class="opt-group-title" style="margin-top:0">Отпросился — отсутствие части смены</div>
        <div class="grid-2">
          <label class="field"><span>Отсутствовал с</span><input type="time" id="cell-from" value="${esc(cell.partial?.from_time || '')}"></label>
          <label class="field"><span>Отсутствовал до</span><input type="time" id="cell-until" value="${esc(cell.partial?.until_time || '')}"></label>
        </div>
        <label class="field"><span>Причина отсутствия</span><select id="cell-partial-reason">
          <option value="">— не указана —</option>
          ${groups.absence.map(x => `<option value="${x.id}"
            ${(cell.partial ? cell.partial.reason?.id === x.id : x.code === 'AWAY_HOURS') ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}
        </select></label>
        <p class="hint" style="margin:2px 0 6px">Отметки в согласованном окне не считаются опозданием или ранним уходом;
          часы отсутствия списываются из банка часов. Чтобы убрать «отпросился» — очистите время.</p>
      </div>
      <div id="punch-override-block" class="hidden" style="margin-top:12px;border:1px solid var(--line);border-radius:12px;padding:12px 14px 8px;background:#f8fbfd">
        <div class="opt-group-title" style="margin-top:0">Отметки «Пришёл / Ушёл» во время этого отсутствия</div>
        <div class="grid-2">
          <label class="field"><span>«Пришёл на работу»</span><select id="cell-punch-in">
            <option value="">как в словаре</option>
            <option value="1">разрешить</option>
            <option value="0">запретить</option>
          </select></label>
          <label class="field"><span>«Ушёл с работы»</span><select id="cell-punch-out">
            <option value="">как в словаре</option>
            <option value="1">разрешить</option>
            <option value="0">запретить</option>
          </select></label>
        </div>
        <p class="hint" style="margin:2px 0 6px">Переопределяет настройку вида отсутствия только для этой ячейки.</p>
      </div>
      <label class="field" style="margin-top:10px"><span>Примечание</span>
        <textarea id="cell-note" placeholder="Например: замена Иванова, приказ №12">${esc(cell.note || '')}</textarea>
      </label>
      <div class="status-line"><span class="k">Текущее значение</span>
        <span class="v">${cur ? esc(cur.name) : 'не заполнено'}${cur && cur.kind === 'work' ? ` · ${hours(cur.planned_hours)} ч` : ''}${cell.auto ? ' · по базовому циклу' : ''}${cell.partial ? ` · отпросился ${cell.partial.from_time}–${cell.partial.until_time}` : ''}</span></div>
      <div id="doc-btns" class="hidden" style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn btn-sm" id="doc-print">Печать заявления</button>
        <button class="btn btn-sm" id="doc-docx">Заявление DOCX (шаблон компании)</button>
        <button class="btn btn-sm" id="doc-pdf">Заявление PDF (готов к печати)</button>
      </div>
      ${nnShift ? `<button class="btn btn-sm hidden" id="cell-nn" style="margin-top:8px">Отметить неявку (НН)</button>` : ''}`,
    footer: `
      <button class="btn btn-danger" data-clear>Очистить</button>
      <div style="flex:1"></div>
      <button class="btn btn-ghost" data-cancel>Отмена</button>
      <button class="btn btn-primary" data-save>Сохранить</button>`,
    onMount(m) {
      const readPartial = () => ({
        partial_shift_id: +(m.querySelector('#cell-partial-reason')?.value || 0) || null,
        from_time: m.querySelector('#cell-from')?.value || '',
        until_time: m.querySelector('#cell-until')?.value || '',
      });
      const effectiveShift = () => state.shiftTypes.find(x => x.id === selected) || cur;
      const syncUI = () => {
        const eff = effectiveShift();
        const isWork = !!(eff && eff.kind === 'work');
        const isAbsence = !!(eff && eff.kind === 'absence');
        m.querySelector('#partial-block').classList.toggle('hidden', !isWork);
        m.querySelector('#punch-override-block').classList.toggle('hidden', !isAbsence);
        const reason = state.shiftTypes.find(x => x.id === +(m.querySelector('#cell-partial-reason')?.value || 0));
        const hasDoc = !!((eff && eff.doc_type) || (isWork && reason && reason.doc_type));
        m.querySelector('#doc-btns').classList.toggle('hidden', !hasDoc);
        const nn = m.querySelector('#cell-nn');
        if (nn) nn.classList.toggle('hidden', dateISO > todayISO());
      };
      $$('.shift-opt', m).forEach(b => b.onclick = () => {
        selected = +b.dataset.id;
        $$('.shift-opt', m).forEach(x => x.classList.toggle('sel', +x.dataset.id === selected));
        syncUI();
      });
      ['#cell-from', '#cell-until', '#cell-partial-reason'].forEach(sel => {
        const el = m.querySelector(sel);
        if (el) { el.onchange = syncUI; el.oninput = syncUI; }
      });
      const setOv = (sel, v) => { m.querySelector(sel).value = v === true ? '1' : (v === false ? '0' : ''); };
      setOv('#cell-punch-in', cell.punch_in_override ?? null);
      setOv('#cell-punch-out', cell.punch_out_override ?? null);
      syncUI();
      m.querySelector('#doc-print').onclick = () => printAbsenceRequest(empId, dateISO);
      m.querySelector('#doc-docx').onclick = () => downloadAbsenceDoc(empId, dateISO, 'docx');
      m.querySelector('#doc-pdf').onclick = () => downloadAbsenceDoc(empId, dateISO, 'pdf');
      const nnBtn = m.querySelector('#cell-nn');
      if (nnBtn) nnBtn.onclick = () => {
        saveCell(empId, dateISO, nnShift.id,
          m.querySelector('#cell-note').value.trim() || 'Неявка по невыясненной причине', false);
      };
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-clear]').onclick = () => saveCell(empId, dateISO, null, '', true);
      const readOverrides = () => {
        const v = sel => { const x = m.querySelector(sel).value; return x === '' ? null : x === '1'; };
        return { in: v('#cell-punch-in'), out: v('#cell-punch-out') };
      };
      m.querySelector('[data-save]').onclick = () =>
        saveCell(empId, dateISO, selected, m.querySelector('#cell-note').value.trim(), false, readPartial(), readOverrides());
    },
  });
}

async function saveCell(empId, dateISO, shiftId, note, clearing, partial, overrides) {
  try {
    const res = await api('/api/schedule/cell', {
      method: 'PUT', body: {
        employee_id: empId, date: dateISO, shift_type_id: shiftId, note,
        partial_shift_id: partial?.partial_shift_id ?? null,
        from_time: partial?.from_time || '',
        until_time: partial?.until_time || '',
        punch_in_override: overrides ? overrides.in : null,
        punch_out_override: overrides ? overrides.out : null,
      },
    });
    closeModal();
    const c = res.cell;
    const row = state.grid.rows.find(r => r.employee.id === empId);
    if (row) {
      row.cells[dateISO] = { ...(row.cells[dateISO] || {}), shift: c.shift, note: c.note,
        partial: c.partial, planned_hours: c.planned_hours,
        punch_in_override: c.punch_in_override, punch_out_override: c.punch_out_override,
        is_today: dateISO === state.grid.today, is_future: dateISO > state.grid.today };
      const tot = Object.values(row.cells).reduce((a, x) => a + (x.planned_hours || 0), 0);
      const wd = Object.values(row.cells).filter(x => x.shift && x.shift.kind === 'work').length;
      row.totals = { ...(row.totals || {}), planned_hours: Math.round(tot * 100) / 100, work_days: wd };
    }
    renderGrid();
    const pt = c.partial ? `, отпросился ${c.partial.from_time}–${c.partial.until_time}` : '';
    toast(clearing ? 'Ячейка очищена' : `Сохранено: ${c.shift ? c.shift.name : '—'} на ${dateRu(dateISO)}${pt}`, 'ok');
  } catch (e) { toast(e.message, 'err'); }
}

/* ══════════════════════════════════════════════════════════════════
   ПОСЕЩЕНИЯ
   ══════════════════════════════════════════════════════════════════ */
async function loadAttendance() {
  $('#view-attendance').innerHTML = `
    <div class="page-head">
      <div><h2>Посещения</h2><div class="sub">Точное время прихода и ухода + кто сейчас на смене</div></div>
      <div class="spacer"></div>
      <div class="month-nav">
        <button id="a-prev">‹</button><div class="label" id="a-label">—</div><button id="a-next">›</button>
      </div>
      <input type="date" id="a-date" value="${state.attDate}" style="max-width:170px">
      <button class="btn btn-sm" id="a-today">Сегодня</button>
    </div>
    <div id="a-body"><div class="empty">Загрузка…</div></div>`;

  const shiftDay = (iso, delta) => {
    const x = new Date(iso + 'T12:00:00');
    x.setDate(x.getDate() + delta);
    return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`;
  };
  $('#a-prev').onclick = () => { state.attDate = shiftDay(state.attDate, -1); $('#a-date').value = state.attDate; fetchAttendance(); };
  $('#a-next').onclick = () => { state.attDate = shiftDay(state.attDate, 1); $('#a-date').value = state.attDate; fetchAttendance(); };
  $('#a-today').onclick = () => { state.attDate = todayISO(); $('#a-date').value = state.attDate; fetchAttendance(); };
  $('#a-date').onchange = e => { state.attDate = e.target.value; fetchAttendance(); };
  await fetchAttendance();
  poll('attendance', () => { if (state.attDate === todayISO()) fetchAttendance(true); });
}

async function fetchAttendance(silent) {
  const data = await api(`/api/punches/attendance?date=${state.attDate}`, { silent: !!silent });
  /* отметки дня с id — для менеджерской кнопки «✕ отменить отметку» */
  let dayPunches = [];
  try { dayPunches = await api(`/api/punches?date=${state.attDate}`, { silent: true }); } catch {}
  const punchIdFor = (empId, isoTs) => {
    if (!isoTs) return null;
    const p = dayPunches.find(x => x.employee_id === empId && x.ts.slice(0, 16) === isoTs.slice(0, 16));
    return p ? p.id : null;
  };
  const delBtn = (empId, isoTs) => {
    const id = punchIdFor(empId, isoTs);
    return id ? ` <button class="icon-btn" data-pdel="${id}" style="color:var(--danger);font-size:12px;padding:2px 4px" title="Отменить отметку (пересчёт табеля + аудит)">✕</button>` : '';
  };
  const d = new Date(state.attDate + 'T00:00:00');
  $('#a-label').textContent = `${d.getDate()} ${MONTHS_GEN[d.getMonth()]}, ${WD[d.getDay()]}`;

  const live = data.on_shift || [];
  const rows = data.items.map(i => {
    const st = STATUS_META[i.status] || { t: i.status, c: 'muted' };
    const inCls = i.is_late ? 'time-late' : 'time-exact';
    return `<tr>
      <td class="who" data-label="Сотрудник">${esc(i.employee.short_name)}<small>${esc(i.employee.position || '')}</small></td>
      <td data-label="По графику">${i.shift && i.shift.kind === 'work'
        ? `<span class="shift-pill" style="background:${withAlpha(i.shift.color, .9)};color:${textOn(i.shift.color)}">${esc(i.shift.start)}–${esc(i.shift.end)}</span>`
        : (i.shift ? `<span class="badge muted">${esc(i.shift.name)}</span>` : '<span class="badge muted">не задан</span>')}</td>
      <td data-label="Пришёл" class="num ${inCls}">${i.fact_in ? hhmm(i.fact_in) : '—'}${delBtn(i.employee.id, i.fact_in)}</td>
      <td data-label="Ушёл" class="num ${i.status === 'early' || i.status === 'late_early' ? 'time-early' : ''}">${i.on_shift_now ? '<span class="pulse"></span>на смене' : (i.fact_out ? hhmm(i.fact_out) : '—')}${delBtn(i.employee.id, i.fact_out)}</td>
      <td data-label="Часов" class="num">${i.fact_hours ? hours(i.fact_hours) : '—'}</td>
      <td data-label="Перераб." class="num">${i.ot_hours ? `<b style="color:var(--warn)">${hours(i.ot_hours)}</b>` : '—'}</td>
      <td data-label="Статус">${i.on_shift_now
        ? `<span class="badge ok"><span class="pulse" style="margin:0"></span>на смене ${i.elapsed_hours != null ? hours(i.elapsed_hours) + ' ч' : ''}</span>`
        : `<span class="badge ${st.c}">${esc(st.t)}</span>`}</td>
      <td data-label="Примечание" style="max-width:220px;color:var(--muted);font-size:12.5px">${esc(i.note || '')}</td>
    </tr>`;
  }).join('');

  $('#a-body').innerHTML = `
    <div class="stat-grid">
      <div class="stat accent"><div class="k">Сейчас на смене</div><div class="v">${live.length}</div></div>
      <div class="stat"><div class="k">По графику сегодня</div><div class="v">${data.items.filter(i => i.shift && i.shift.kind === 'work').length}</div></div>
      <div class="stat warn"><div class="k">Опоздания</div><div class="v">${data.items.filter(i => i.is_late).length}</div></div>
      <div class="stat danger"><div class="k">Требуют внимания</div><div class="v">${data.items.filter(i => ['no_punch', 'unclosed', 'work_no_plan', 'work_off'].includes(i.status)).length}</div></div>
    </div>

    ${live.length ? `<div class="panel"><h3 class="panel-title">На смене прямо сейчас · ${esc(hhmm(data.now))}</h3>
      <div class="presence-grid">${live.map(i => `
        <div class="presence-card ${i.is_late ? 'late' : ''}">
          <div class="nm"><span class="pulse"></span>${esc(i.employee.short_name)}</div>
          <div class="pos">${esc(i.employee.position || '')} · ${esc(i.shift?.name || '')}</div>
          <div class="row"><span style="color:var(--muted)">Пришёл</span><b>${hhmm(i.fact_in)}</b></div>
          <div class="row"><span style="color:var(--muted)">Уже на смене</span><b>${i.elapsed_hours != null ? hours(i.elapsed_hours) + ' ч' : '—'}</b></div>
          <div class="row"><span style="color:var(--muted)">План до</span><b>${i.planned_end ? hhmm(i.planned_end) : '—'}</b></div>
        </div>`).join('')}</div></div>` : ''}

    <div class="table-wrap">
      <table class="data responsive">
        <thead><tr><th>Сотрудник</th><th>По графику</th><th>Пришёл</th><th>Ушёл</th><th>Часов</th><th>Перераб.</th><th>Статус</th><th>Примечание</th></tr></thead>
        <tbody>${rows || `<tr><td colspan="8" class="empty">Нет данных</td></tr>`}</tbody>
      </table>
    </div>
    <p class="hint">Система показывает точное время отметок, а в табель часы попадают кратно часу (округление к ближайшему).</p>`;

  $$('#a-body [data-pdel]').forEach(b => b.onclick = () =>
    confirmDialog('Отменить отметку?',
      'Отметка будет удалена, день табеля пересчитан. Действие попадёт в журнал аудита.',
      async () => {
        try {
          await api(`/api/punches/${b.dataset.pdel}`, { method: 'DELETE' });
          toast('Отметка отменена, табель пересчитан', 'ok');
          fetchAttendance();
        } catch (e) { toast(e.message, 'err'); }
      }, 'Отменить отметку'));

}

/* ══════════════════════════════════════════════════════════════════
   КТО НА РАБОТЕ: реальный check-in прямо сейчас (видно всем ролям)
   ══════════════════════════════════════════════════════════════════ */
async function loadOnwork() {
  $('#view-onwork').innerHTML = `
    <div class="page-head">
      <div><h2>Кто на работе</h2>
        <div class="sub">Сотрудники, которые нажали «Пришёл на работу» и ещё не отметили уход.
          Обновляется автоматически каждые 30 секунд</div></div>
      <div class="spacer"></div>
      <span class="badge ok" id="ow-now" style="font-size:13px;padding:7px 12px">—</span>
      <button class="btn btn-sm" id="ow-refresh">Обновить</button>
    </div>
    <div id="ow-body"><div class="empty">Загрузка…</div></div>`;
  $('#ow-refresh').onclick = () => fetchOnwork();
  await fetchOnwork();
  poll('onwork', () => fetchOnwork(true));
}

async function fetchOnwork(silent) {
  let d;
  try {
    d = await api('/api/punches/onwork', { silent: !!silent });
  } catch (e) {
    const body0 = $('#ow-body');
    if (body0) body0.innerHTML = `<div class="panel"><div class="empty">${esc(e.message || e)}</div></div>`;
    return;
  }
  const nowEl = $('#ow-now');
  if (nowEl) nowEl.textContent = `Сейчас ${d.now.slice(11, 16)} · на работе ${d.count}`;
  const body = $('#ow-body');
  if (!body) return;
  const cards = d.items.map(i => {
    const tel = String(i.phone || '').trim();
    const tg = String(i.telegram || '').trim().replace(/^@+/, '');
    const telHref = tel.replace(/[^0-9+]/g, '');
    const tgHref = tg.replace(/[^A-Za-z0-9_]/g, '');
    return `
    <div class="presence-card ${i.is_late ? 'late' : ''}">
      <div class="nm"><span class="pulse"></span>${esc(i.short_name)}</div>
      <div class="pos">${esc(i.position || '—')}${i.schedule_group ? ' · ' + esc(i.schedule_group) : ''}</div>
      ${tel || tg ? `<div class="contacts">${tel ? `<a href="tel:${esc(telHref)}" title="Позвонить">📞 ${esc(tel)}</a>` : ''}${tg ? `<a href="https://t.me/${esc(tgHref)}" target="_blank" rel="noopener" title="Написать в Telegram">✈️ @${esc(tg)}</a>` : ''}</div>` : ''}
      <div class="row"><span style="color:var(--muted)">На смене с</span><b>${esc(i.session_start.slice(11, 16))}</b></div>
      <div class="row"><span style="color:var(--muted)">Уже работает</span><b>${i.elapsed_hours != null ? hours(i.elapsed_hours) + ' ч' : '—'}</b></div>
      <div class="row"><span style="color:var(--muted)">По графику</span><b>${i.shift && i.shift.kind === 'work'
        ? esc(`${i.shift.start}–${i.shift.end}`) : (i.shift ? esc(i.shift.name) : '—')}</b></div>
      <div class="row"><span style="color:var(--muted)">План до</span><b>${i.planned_end ? esc(i.planned_end.slice(11, 16)) : '—'}</b></div>
      ${i.is_late ? '<div class="row"><span style="color:var(--muted)">Статус</span><b style="color:var(--warn)">пришёл позже начала смены</b></div>' : ''}
    </div>`;
  }).join('');
  body.innerHTML = `
    <div class="stat-grid">
      <div class="stat accent"><div class="k">Сейчас на работе</div><div class="v">${d.count}</div></div>
      <div class="stat"><div class="k">По графику сегодня</div><div class="v">${d.planned_today}</div></div>
    </div>
    ${d.count
      ? `<div class="panel"><h3 class="panel-title">На смене прямо сейчас</h3><div class="presence-grid">${cards}</div></div>`
      : `<div class="panel"><div class="empty">Сейчас никто не отмечен на работе.
         Сотрудники нажимают кнопку «Пришёл на работу» в разделе «Мои отметки».</div></div>`}`;
}

/* ══════════════════════════════════════════════════════════════════
   ТАБЕЛЬ
   ══════════════════════════════════════════════════════════════════ */
async function loadTimesheet() {
  $('#view-timesheet').innerHTML = `
    <div class="page-head">
      <div><h2>Табель учёта рабочего времени</h2>
        <div class="sub">План / факт, дневные (ДЯ) и ночные (ДН) часы, переработки и банк часов</div></div>
      <div class="spacer"></div>
      <div class="month-nav">
        <button id="t-prev">‹</button><div class="label" id="t-label">—</div><button id="t-next">›</button>
      </div>
      <button class="btn btn-sm" id="t-recalc">Пересчитать</button>
      <button class="btn btn-sm btn-ghost" id="t-print">Печать</button>
      <button class="btn btn-sm btn-ghost" id="t-pdf" title="Скачать PDF: файл собирает сервер">PDF</button>
      <button class="btn btn-sm" id="t-csv">CSV (внутр.)</button>
      <button class="btn btn-sm" id="t-csv-pay">CSV (в учёт з/п)</button>
      <button class="btn btn-sm btn-primary" id="t-xlsx">Скачать Excel</button>
    </div>
    <div id="t-body"><div class="empty">Загрузка…</div></div>`;

  const shiftMonth = delta => {
    let m = state.month + delta, y = state.year;
    if (m < 1) { m = 12; y--; } if (m > 12) { m = 1; y++; }
    state.month = m; state.year = y; loadTimesheet();
  };
  $('#t-prev').onclick = () => shiftMonth(-1);
  $('#t-next').onclick = () => shiftMonth(1);
  $('#t-print').onclick = printTimesheet;
  $('#t-pdf').onclick = () => downloadBlob(`/api/timesheet/pdf?year=${state.year}&month=${state.month}`, 'tabel.pdf');
  $('#t-csv').onclick = () => downloadBlob(`/api/timesheet/csv?year=${state.year}&month=${state.month}`, 'tabel.csv');
  $('#t-csv-pay').onclick = () => downloadBlob(`/api/timesheet/csv?year=${state.year}&month=${state.month}&mode=payroll`, 'vyplata.csv');
  $('#t-xlsx').onclick = () => downloadBlob(`/api/timesheet/xlsx?year=${state.year}&month=${state.month}`, 'tabel.xlsx');
  $('#t-recalc').onclick = async () => {
    try {
      const r = await api('/api/timesheet/recalc', { method: 'POST', body: { year: state.year, month: state.month } });
      toast(`Пересчитано ${r.recalculated_days} ${plural(r.recalculated_days, 'день', 'дня', 'дней')}`, 'ok');
      loadTimesheet();
    } catch (e) { toast(e.message, 'err'); }
  };

  const [data, ot] = await Promise.all([
    api(`/api/timesheet?year=${state.year}&month=${state.month}`),
    api(`/api/timesheet/overtime?year=${state.year}&month=${state.month}`),
  ]);
  state.timesheet = data;
  state.overtime = ot;
  renderTimesheet();
}

function renderTimesheet() {
  const d = state.timesheet;
  $('#t-label').textContent = `${MONTHS[d.month - 1]} ${d.year}`;
  const g = d.grand;

  const problems = [];
  d.rows.forEach(r => r.days.forEach(day => {
    if (day.is_future || day.status === 'planned') return;
    if (['late', 'early', 'late_early', 'no_punch', 'unclosed', 'work_no_plan', 'work_off'].includes(day.status)) {
      problems.push({ emp: r.employee, day });
    }
  }));

  const rows = d.rows.map(r => {
    const t = r.totals;
    const open = state.expanded.has(r.employee.id);
    const accent = r.employee.group_color || '#8a94a6';
    return `
    <tr class="ts-row" data-emp="${r.employee.id}">
      <td class="who" data-label="Сотрудник" style="box-shadow: inset 3px 0 0 ${accent}">${esc(r.employee.short_name)}
        <small>${esc(r.employee.position || '')}${r.employee.schedule_group ? ' · ' + esc(r.employee.schedule_group) : ''}</small></td>
      <td class="num" data-label="План">${hours(t.planned)}</td>
      <td class="num" data-label="Факт"><b>${hours(t.fact)}</b></td>
      <td class="num" data-label="ДЯ">${hours(t.day)}</td>
      <td class="num" data-label="ДН" style="color:#3d55c8">${t.night ? hours(t.night) : '—'}</td>
      <td class="num" data-label="Перераб.">${t.ot ? `<b style="color:var(--warn)">${hours(t.ot)}</b>` : '—'}</td>
      <td class="num" data-label="Недораб.">${t.deficit ? `<span style="color:#c0392b">${hours(t.deficit)}</span>` : '—'}</td>
      <td class="num" data-label="Отгулы">${t.timeoff ? hours(t.timeoff) : '—'}</td>
      <td class="num" data-label="Банк часов"><span class="${t.balance >= 0 ? 'balance-pos' : 'balance-neg'}">${t.balance >= 0 ? '+' : ''}${hours(t.balance)}</span></td>
      <td class="num" data-label="Проблемы">${t.issues ? `<span class="badge danger">${t.issues}</span>` : '<span class="badge ok">нет</span>'}</td>
    </tr>
    ${open ? `<tr class="ts-detail"><td colspan="10"><div class="ts-detail-inner">
      <div class="day-chips">${r.days.map(day => dayChip(day)).join('')}</div>
    </div></td></tr>` : ''}`;
  }).join('');

  $('#t-body').innerHTML = `
    <div class="stat-grid">
      <div class="stat"><div class="k">План, часов</div><div class="v">${hours(g.planned)}</div></div>
      <div class="stat accent"><div class="k">Факт, часов</div><div class="v">${hours(g.fact)}</div></div>
      <div class="stat info"><div class="k">Ночные (ДН)</div><div class="v">${hours(g.night)}</div></div>
      <div class="stat warn"><div class="k">Переработка</div><div class="v">${hours(g.ot)}</div></div>
      <div class="stat danger"><div class="k">Дней с отклонениями</div><div class="v">${problems.length}</div></div>
    </div>

    <div class="table-wrap">
      <table class="data responsive">
        <thead><tr><th>Сотрудник</th><th>План</th><th>Факт</th><th>ДЯ</th><th>ДН</th><th>Перераб.</th><th>Недораб.</th><th>Отгулы</th><th>Банк часов</th><th>Проблемы</th></tr></thead>
        <tbody>${rows || `<tr><td class="empty" colspan="10">Нет данных</td></tr>`}</tbody>
      </table>
    </div>
    <p class="hint">Нажмите на строку сотрудника, чтобы увидеть расшифровку по дням. Банк часов = стартовый баланс + переработка − отгулы − недоработка. Выгрузка Excel содержит сетку «ФИО × дни» с ячейками «ДЯ n ДН m».</p>

    ${state.overtime ? `
    <div class="panel" style="margin-top:18px">
      <h3 class="panel-title">Переработки к выплате за месяц</h3>
      <p class="hint" style="margin:-6px 0 10px">Начислено: ранние приходы, поздние уходы, работа в выходной (ДЯ/ДН).
      В дни двойной оплаты (производственный календарь, ВИП-гости) переработки идут кодами <b class="dbl">ДЯ2/ДН2</b> — двойной тариф.
      Списано: опоздания, ранние уходы, выходные за часы — вычитаются сначала из дневных часов ранних дней, затем из ночных;
      из двойных часов списание снимается вполовину (8 часов оплаты = 4 часа ДЯ2).
      «Всего» — в одинарных часах: час ДЯ2/ДН2 считается как два. Итог — это то, что вносится в систему учёта зарплаты:
      кнопка «CSV (в учёт з/п)» или лист «В учёт зарплаты» в Excel; журнал зачёта — кнопка «зачёт».</p>
      <div class="table-wrap" style="max-height:none">
        <table class="data responsive"><thead><tr>
          <th>Сотрудник</th><th>Начислено</th><th>Списано</th>
          <th>К выплате</th><th title="ДЯ2/ДН2 учтены по двойному тарифу">Всего</th><th></th>
        </tr></thead><tbody>
        ${state.overtime.rows.filter(r => r.totals.credit_dya || r.totals.credit_dn || r.totals.credit_dya2 || r.totals.credit_dn2 || r.totals.debit).map(r => `<tr>
          <td class="who" data-label="Сотрудник">${esc(r.employee.short_name)}</td>
          <td class="num" data-label="Начислено">${payCodes(r.totals, 'credit_')}</td>
          <td class="num" data-label="Списано" style="color:#c0392b">${r.totals.debit ? '−' + hours(r.totals.debit) : '—'}</td>
          <td class="num" data-label="К выплате">${payCodes(r.totals, 'pay_')}</td>
          <td class="num" data-label="Всего"><b>${hours(r.totals.pay_total)}</b>${(r.totals.pay_dya2 || r.totals.pay_dn2) ? `<div class="dbl-hint">в т.ч. ×2: ${hours((r.totals.pay_dya2 || 0) + (r.totals.pay_dn2 || 0))} ч</div>` : ''}</td>
          <td class="num"><button class="btn btn-sm btn-ghost" data-ot="${r.employee.id}">зачёт</button></td>
        </tr>`).join('') || '<tr><td colspan="6" class="empty">За месяц не было переработок и списаний</td></tr>'}
        </tbody></table>
      </div>
    </div>` : ''}

    ${problems.length ? `
    <div class="panel" style="margin-top:18px">
      <h3 class="panel-title">Требует внимания · ${problems.length}</h3>
      <div class="table-wrap" style="max-height:280px">
        <table class="data responsive"><thead><tr><th>Дата</th><th>Сотрудник</th><th>Смена</th><th>Отметки</th><th>Часы</th><th>Что случилось</th></tr></thead>
        <tbody>${problems.map(p => `<tr>
          <td data-label="Дата">${dateRu(p.day.date)}</td>
          <td class="who" data-label="Сотрудник">${esc(p.emp.short_name)}</td>
          <td data-label="Смена">${esc(p.day.shift_name || '—')}</td>
          <td class="num" data-label="Отметки">${p.day.fact_in ? hhmm(p.day.fact_in) : '—'} → ${p.day.fact_out ? hhmm(p.day.fact_out) : '—'}</td>
          <td class="num" data-label="Часы">${hours(p.day.fact_hours)} / ${hours(p.day.planned_hours)}</td>
          <td data-label="Статус">${statusBadge(p.day.status)}${p.day.warnings?.length ? `<div style="color:var(--muted);font-size:12px;margin-top:4px">${p.day.warnings.map(esc).join('<br>')}</div>` : ''}</td>
        </tr>`).join('')}</tbody></table>
      </div>
    </div>` : ''}`;

  $$('.ts-row').forEach(tr => tr.onclick = () => {
    const id = +tr.dataset.emp;
    state.expanded.has(id) ? state.expanded.delete(id) : state.expanded.add(id);
    renderTimesheet();
  });
  $$('[data-ot]').forEach(b => b.onclick = e => {
    e.stopPropagation();
    const r = state.overtime.rows.find(x => x.employee.id === +b.dataset.ot);
    openModal({
      title: 'Зачёт переработок: ' + r.employee.full_name,
      subtitle: `${MONTHS[state.overtime.month - 1]} ${state.overtime.year}`,
      wide: true,
      body: `
        <div class="opt-group-title">Начислено (брутто)</div>
        ${r.credits.map(c => `<div style="font-size:13px;padding:2px 0">${dateRu(c.date)}${(c.dya2 || c.dn2) ? ' <span class="badge warn" title="День двойной оплаты: переработки по двойному тарифу">×2</span>' : ''}: ${creditLine(c)}</div>`).join('') || '<div class="hint">нет</div>'}
        <div class="opt-group-title">Списано</div>
        ${r.debits.map(dd => `<div style="font-size:13px;padding:2px 0">${dateRu(dd.date)}: ${esc(dd.kind)} −${hours(dd.hours)} ч</div>`).join('') || '<div class="hint">нет</div>'}
        <div class="opt-group-title">Как зачлось (сначала дневные часы ранних дней; из двойных ДЯ2/ДН2 — вполовину)</div>
        ${r.log.map(l => `<div style="font-size:13px;padding:2px 0">${esc(l.kind)} ${String(l.debit_date || '').includes('-') ? dateRu(l.debit_date) : esc(l.debit_date || '—')}
          → ${l.credit_date ? dateRu(l.credit_date) + ' (' + l.from + ')' : 'не покрыто переработками'}:
          ${l.credit_date && String(l.from || '').endsWith('2')
            ? `−${hours(l.credit_hours)} ч ${esc(l.from)} <span class="dbl-hint">(= ${hours(l.hours)} ч оплаты)</span>`
            : hours(l.hours) + ' ч'}</div>`).join('') || '<div class="hint">списаний не было</div>'}
        <div class="opt-group-title">К выплате</div>
        ${r.remain.map(c => `<div style="font-size:13px;padding:2px 0">${dateRu(c.date)}${(c.dya2 || c.dn2) ? ' <span class="badge warn">×2</span>' : ''}: ${creditLine(c)}</div>`).join('') || '<div class="hint">всё покрыто списаниями</div>'}
        <div class="status-line" style="margin-top:10px"><span class="k">Итого к подаче</span>
          <span class="v">${settleTotalLine(r.totals)}</span></div>`,
      footer: `<button class="btn btn-primary" data-close>Закрыть</button>`,
      onMount(m) { m.querySelector('[data-close]').onclick = closeModal; },
    });
  });
}

/* Коды часов к выплате: ДЯ/ДН — одинарный тариф, ДЯ2/ДН2 — двойной
   (производственный календарь / ВИП-гости). prefix: 'credit_' | 'pay_' */
function payCodes(t, p) {
  const out = [];
  if (t[p + 'dya']) out.push(`<b>ДЯ ${hours(t[p + 'dya'])}</b>`);
  if (t[p + 'dn']) out.push(`<b style="color:#3d55c8">ДН ${hours(t[p + 'dn'])}</b>`);
  if (t[p + 'dya2']) out.push(`<b class="dbl">ДЯ2 ${hours(t[p + 'dya2'])}</b>`);
  if (t[p + 'dn2']) out.push(`<b class="dbl">ДН2 ${hours(t[p + 'dn2'])}</b>`);
  return out.join(' · ') || '—';
}
function creditLine(c) {
  const bits = [];
  if (c.dya) bits.push(`<b>ДЯ ${hours(c.dya)}</b>`);
  if (c.dn) bits.push(`<b style="color:#3d55c8">ДН ${hours(c.dn)}</b>`);
  if (c.dya2) bits.push(`<b class="dbl">ДЯ2 ${hours(c.dya2)}</b>`);
  if (c.dn2) bits.push(`<b class="dbl">ДН2 ${hours(c.dn2)}</b>`);
  return bits.join(', ') || '—';
}
function settleTotalLine(t) {
  const bits = [];
  if (t.pay_dya) bits.push(`ДЯ ${hours(t.pay_dya)}`);
  if (t.pay_dn) bits.push(`ДН ${hours(t.pay_dn)}`);
  if (t.pay_dya2) bits.push(`ДЯ2 ${hours(t.pay_dya2)}`);
  if (t.pay_dn2) bits.push(`ДН2 ${hours(t.pay_dn2)}`);
  const dbl = (t.pay_dya2 || 0) + (t.pay_dn2 || 0);
  return `${bits.join(' + ') || '0'} = ${hours(t.pay_total)} ч к оплате`
    + (dbl ? ' · ДЯ2/ДН2 учтены по двойному тарифу' : '');
}

function dayChip(day) {
  const issue = ['late', 'early', 'late_early'].includes(day.status) && !day.is_future;
  const bad = ['no_punch', 'unclosed', 'work_no_plan'].includes(day.status);
  const off = day.kind !== 'work' || day.is_future;
  const cls = ['day-chip', bad ? 'bad' : '', issue ? 'issue' : '', off ? 'off' : '',
    day.status === 'work_off' ? 'issue' : '', day.is_double ? 'double' : ''].filter(Boolean).join(' ');
  const parts = [];
  if (day.fact_in || day.fact_out) parts.push(`${hhmm(day.fact_in) || '?'} → ${hhmm(day.fact_out) || '?'}`);
  if (day.planned_hours || day.fact_hours) parts.push(`${hours(day.fact_hours)} / ${hours(day.planned_hours)} ч`);
  if (day.day_hours) parts.push(`ДЯ ${hours(day.day_hours)}`);
  if (day.night_hours) parts.push(`ДН ${hours(day.night_hours)}`);
  if (day.ot_hours) parts.push(`перераб. ${hours(day.ot_hours)}`);
  if (day.deficit_hours) parts.push(`недораб. ${hours(day.deficit_hours)}`);
  if (day.timeoff_hours) parts.push(`списано ${hours(day.timeoff_hours)} ч`);
  if (day.is_double) parts.push(`×2 ${day.double_reason === 'vip' ? 'ВИП-гость' : 'двойная оплата'}`);
  return `<div class="${cls}" title="${esc(day.shift_name || '')}">
    <div class="d"><span>${day.day} ${esc(day.weekday)}</span>
      <span class="dot" style="background:${day.color}"></span></div>
    <div class="h">${esc(day.shift_name || 'не заполнено')}</div>
    <div class="h">${parts.map(esc).join(' · ') || statusTitle(day.status)}</div>
    ${day.ot_note ? `<div class="otn">★ ${esc(day.ot_note)}</div>` : ''}
    ${day.warnings?.length ? `<div class="w">${day.warnings.map(esc).join('<br>')}</div>` : ''}
    ${day.note ? `<div class="w" style="color:var(--muted)">${esc(day.note)}</div>` : ''}
  </div>`;
}
function statusTitle(st) { return (STATUS_META[st] || { t: st || '—' }).t; }

/* ══════════════════════════════════════════════════════════════════
   МОИ ОТМЕТКИ
   ══════════════════════════════════════════════════════════════════ */
async function loadMe() {
  $('#view-me').innerHTML = '<div class="me-wrap"><div class="empty">Загрузка…</div></div>';
  try {
    const [status, me] = await Promise.all([api('/api/punches/status'), api('/api/auth/me')]);
    state.status = status;
    syncServerClock(status.now);
    renderMe(status, me);
    poll('me', loadMeSilently);
  } catch (e) {
    $('#view-me').innerHTML = `<div class="me-wrap"><div class="panel"><h3 class="panel-title">Мои отметки</h3>
      <p style="color:var(--muted);font-size:14px">К вашей учётной записи не привязан сотрудник — отметки недоступны.<br><br>${esc(e.message)}</p></div></div>`;
  }
}

function renderMe(s, me) {
  const d = new Date(s.today + 'T00:00:00');
  const shift = s.shift;
  const isWork = shift && shift.kind === 'work';
  const color = shift?.color || '#8a94a6';
  const nowD = new Date(s.now);

  const inOk = s.punch_in_allowed !== false;
  const outOk = s.punch_out_allowed !== false;
  let mainBtn, punchBlocked = null;
  if (s.on_shift && outOk) {
    mainBtn = `<button class="punch-btn out" id="punch-btn">Ушёл с работы
      <small>нажать в ${s.planned_end ? hhmm(s.planned_end) : '—'} · сейчас ${nowD.toTimeString().slice(0, 5)}</small></button>`;
  } else if (s.on_shift) {
    punchBlocked = 'out';
    mainBtn = `<button class="punch-btn idle" id="punch-btn" disabled>Ушёл с работы
      <small>сейчас статус: ${esc(shift?.name || 'absence')} — отмечать уход запрещено</small></button>`;
  } else if (!inOk) {
    punchBlocked = 'in';
    mainBtn = `<button class="punch-btn idle" id="punch-btn" disabled>Пришёл на работу
      <small>сейчас статус: ${esc(shift?.name || 'absence')} — отмечать приход запрещено</small></button>`;
  } else if (isWork) {
    mainBtn = `<button class="punch-btn in" id="punch-btn">Пришёл на работу
      <small>смена ${shift.start}–${shift.end} · сейчас ${nowD.toTimeString().slice(0, 5)}</small></button>`;
  } else {
    mainBtn = `<button class="punch-btn in" id="punch-btn">Пришёл на работу
      <small>по графику ${esc(shift ? shift.name.toLowerCase() : 'смена не задана')} — часы будут учтены как работа в выходной</small></button>`;
  }

  $('#view-me').innerHTML = `
  <div class="me-wrap">
    <div class="me-date">${WD[d.getDay()]}, ${d.getDate()} ${MONTHS_GEN[d.getMonth()]} ${d.getFullYear()} · ${nowD.toTimeString().slice(0, 5)}</div>

    <div class="me-shift" style="--accent:${color}">
      <div class="code">${esc(shift?.tzh_code || '—')} · ${esc(shift ? (shift.kind === 'work' ? 'рабочая смена' : 'отсутствие') : 'нет данных')}</div>
      <div class="title" style="color:${color}">${esc(isWork ? `${shift.start}–${shift.end}` : (shift?.name || '—'))}</div>
      <div class="sub">${isWork
        ? `${hours(shift.planned_hours)} ч к зачёту${shift.overnight ? ' · ночная смена: часы попадут в дату начала' : ''}`
        : 'часы в табель не начисляются'}</div>
      ${s.note ? `<div class="note">${esc(s.note)}</div>` : ''}
    </div>

    <div class="punch-zone">${mainBtn}</div>

    ${punchBlocked ? `<div class="status-line" style="border-color:#f0d9a8;background:#fffdf6">
      <span class="k">Сейчас статус: ${esc(shift?.name || 'absence')}</span>
      <span class="v" style="color:#8a5300">Отмечаться нельзя${punchBlocked === 'in' ? ' (приход)' : ' (уход)'}. Если это ошибка — обратитесь к менеджеру.</span>
    </div>` : ''}

    ${s.on_shift ? `
    <div class="status-line"><span class="k"><span class="pulse"></span>Вы на смене с ${hhmm(s.session_start)}</span>
      <span class="v">${s.elapsed_hours != null ? hours(s.elapsed_hours) + ' ч' : '—'}</span></div>` : ''}

    <div class="me-stats">
      <div class="me-stat"><div class="k">Отработано сегодня${s.on_shift ? ' (предв.)' : ''}</div><div class="v">${hours(s.today_fact.fact_hours)} ч</div></div>
      <div class="me-stat"><div class="k">Ночные сегодня (ДН)</div><div class="v">${hours(s.today_fact.night_hours)} ч</div></div>
      <div class="me-stat"><div class="k">Переработка сегодня</div><div class="v" style="color:var(--warn)">${hours(s.today_fact.ot_hours)} ч</div></div>
      <div class="me-stat"><div class="k">Банк часов</div>
        <div class="v ${s.balance_hours >= 0 ? 'balance-pos' : 'balance-neg'}">${s.balance_hours >= 0 ? '+' : ''}${hours(s.balance_hours)}</div></div>
    </div>

    <div class="history">
      <h3 class="panel-title">Мои отметки</h3>
      <div id="me-history"><div class="empty">Загрузка…</div></div>
    </div>

    ${carStripHtml()}

    ${state.user.impersonated ? `<div class="panel" style="margin-top:16px;border-color:#f0d9a8;background:#fffdf6">
      <p style="margin:0;font-size:13.5px;color:#8a5300">Демо-режим: вы смотрите интерфейс сотрудника
      <b>${esc(state.user.name)}</b>. Отметки, нажатые здесь, попадут в его табель.</p></div>` : ''}
  </div>`;

  const btn = $('#punch-btn');
  if (btn && !btn.disabled) btn.onclick = doPunch;
  loadMyHistory();
  bindCarStrip();
}

/* ── полоска «Мой электрокар» в «Моих отметках»: держу / закреплён / взять свободный ── */
function carStripHtml() {
  return `<div class="panel" id="car-strip"><h3 class="panel-title">Электрокар</h3>
    <div class="empty" style="padding:12px">Загрузка…</div></div>`;
}

async function bindCarStrip() {
  const host = $('#car-strip');
  if (!host) return;
  try {
    const data = await api('/api/cars', { silent: true });
    const cars = data.cars || [];
    const me = data.me || {};
    const held = cars.find(c => c.id === me.held);
    const assigned = cars.find(c => c.id === me.assigned);
    const freeRec = cars.find(c => c.id === me.free_recommended);
    let inner;
    if (held) {
      inner = `<div class="rule-row"><div>
          <div class="lbl">Вы держите кар №${esc(held.number)} <span class="badge ${CAR_BADGE[held.status] || 'muted'}">${esc(held.status_title)}</span></div>
          <div class="desc">место: ${esc(held.location || '—')} · заряд: ${esc(held.charge_title)}${held.has_key ? ' · ключ у вас' : ''}</div>
        </div><div class="rule-input" style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn btn-sm" id="cs-return">Вернул</button>
          <button class="btn btn-sm btn-ghost" id="cs-handover">Передать</button>
        </div></div>`;
    } else if (freeRec) {
      inner = `<div class="rule-row"><div>
          <div class="lbl">Свободный кар: №${esc(freeRec.number)} · ${esc(freeRec.location || 'место не указано')}</div>
          <div class="desc">${assigned ? `Закреплён за вами: №${esc(assigned.number)}. ` : ''}Взять кар можно, даже если он на зарядке.</div>
        </div><div class="rule-input"><button class="btn btn-sm btn-accent" id="cs-take">Взял кар №${esc(freeRec.number)}</button></div></div>`;
    } else {
      inner = `<div class="hint" style="margin:0">Свободных каров нет — вы ничего не держите. Актуальный парк: раздел «Электрокары».</div>`;
    }
    if (assigned && assigned.id !== me.held) {
      inner += `<div class="hint">Закреплённый за вами кар №${esc(assigned.number)} сейчас ${assigned.status === 'busy' ? `у ${esc(assigned.holder_name || 'другого')}` : assigned.status_title.toLowerCase()}</div>`;
    }
    host.innerHTML = `<h3 class="panel-title">Электрокар</h3>${inner}`;
    const take = $('#cs-take'), ret = $('#cs-return'), ho = $('#cs-handover');
    if (take) take.onclick = async () => {
      try {
        await api(`/api/cars/${freeRec.id}/take`, { method: 'POST', body: { ack_assigned: false } });
        toast(`Кар №${freeRec.number} взят — ключ по умолчанию у вас`, 'ok');
        loadMe();
      } catch (e) {
        if (e.payload?.interception) {
          confirmDialog('Кар закреплён за другим', e.payload.message, async () => {
            try {
              await api(`/api/cars/${freeRec.id}/take`, { method: 'POST', body: { ack_assigned: true } });
              toast(`Кар №${freeRec.number} взят, факт записан в историю`, 'ok');
              loadMe();
            } catch (e2) { toast(e2.message, 'err'); }
          }, 'Всё равно взять', false);
        } else toast(e.message, 'err');
      }
    };
    if (ret) ret.onclick = () => carReturnModal(held, () => loadMe());
    if (ho) ho.onclick = () => carHandoverModal(held, () => loadMe());
  } catch {
    host.innerHTML = `<h3 class="panel-title">Электрокар</h3><div class="hint" style="margin:0">Раздел недоступен</div>`;
  }
}

async function loadMeSilently() {
  try {
    if (punchInFlight) return;   // не перерисовываем кнопку, пока отметка отправляется
    const [s, me] = await Promise.all([api('/api/punches/status', { silent: true }),
                                       api('/api/auth/me', { silent: true })]);
    state.status = s;
    syncServerClock(s.now);
    if (state.view === 'me' && !punchInFlight) renderMe(s, me);
  } catch { /* тихо */ }
}

let punchInFlight = false;
async function doPunch() {
  if (punchInFlight) return;               // двойной тап
  punchInFlight = true;
  const btn = $('#punch-btn');
  if (btn) btn.disabled = true;
  // направление — по тому, что видит пользователь на кнопке, а не «auto» на сервере:
  // иначе второй тап превращается в «Ушёл» через секунду после «Пришёл»
  const kind = state.status?.on_shift ? 'out' : 'in';
  try {
    const res = await api('/api/punches', { method: 'POST', body: { kind } });
    let msg = res.message;
    if (res.day && res.day.fact_hours) {
      msg += ` · зачтено ${hours(res.day.fact_hours)} ч из ${hours(res.day.planned_hours)}`;
      if (res.day.ot_hours) msg += `, переработка ${hours(res.day.ot_hours)} ч`;
    }
    toast(msg, 'ok', res.warnings || []);
    state.status = res.status;
    const me = await api('/api/auth/me', { silent: true });
    punchInFlight = false;
    renderMe(res.status, me);
    if (res.punch?.kind === 'OUT' && res.day?.ot_hours > 0) {
      openOtNoteModal(res.punch.id, '', res.day.ot_hours);
    }
  } catch (e) {
    toast(e.message, 'err');
    if (btn) btn.disabled = false;
  } finally {
    punchInFlight = false;
  }
}

function openOtNoteModal(punchId, current, otHours) {
  openModal({
    title: 'Описание переработки',
    subtitle: otHours ? `Переработка ${hours(otHours)} ч — опишите, с кем работали и что делали` : 'Описание попадёт в табель и в выгрузку Excel',
    body: `<label class="field"><span>Текст</span>
      <textarea id="ot-note" rows="4" placeholder="Например: оставался с Ивановым, готовили зал к банкету; принимал доставку белья">${esc(current || '')}</textarea></label>`,
    footer: `<button class="btn btn-ghost" data-skip>Позже</button>
             <button class="btn btn-primary" data-save>Сохранить</button>`,
    onMount(m) {
      m.querySelector('[data-skip]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        const note = m.querySelector('#ot-note').value.trim();
        try {
          await api(`/api/punches/${punchId}/note`, { method: 'PUT', body: { note } });
          closeModal();
          toast('Описание переработки сохранено', 'ok');
          if (state.view === 'me') loadMe();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

async function loadMyHistory() {
  const host = $('#me-history');
  if (!host) return;
  const d = new Date();
  const mine = state.user.employee_id ? `&employee_id=${state.user.employee_id}` : '';
  const items = await api(`/api/punches?year=${d.getFullYear()}&month=${d.getMonth() + 1}${mine}`);
  if (!items.length) { host.innerHTML = '<div class="empty">Отметок пока нет</div>'; return; }
  host.innerHTML = items.slice(0, 30).map(p => {
    const dt = new Date(p.ts);
    return `<div class="history-item">
      <div class="ic ${p.kind === 'IN' ? 'in' : 'out'}">${p.kind === 'IN' ? '→' : '←'}</div>
      <div class="meta">${p.kind === 'IN' ? 'Пришёл на работу' : 'Ушёл с работы'}
        <small>${dt.getDate()} ${MONTHS_GEN[dt.getMonth()]} · ${esc(p.source === 'manual' ? 'добавлено менеджером' : 'самостоятельно')}${p.note ? ' · ★ ' + esc(p.note) : ''}</small></div>
      ${p.kind === 'OUT' ? `<button class="btn btn-sm btn-ghost note-btn" data-note="${p.id}" data-cur="${esc(p.note || '')}">★ описание</button>` : ''}
      <div class="t">${dt.toTimeString().slice(0, 5)}</div>
    </div>`;
  }).join('');
  $$('[data-note]', host).forEach(b => b.onclick = () => openOtNoteModal(+b.dataset.note, b.dataset.cur, 0));
}

/* ══════════════════════════════════════════════════════════════════
   СОТРУДНИКИ: список → карточка → редактор
   ══════════════════════════════════════════════════════════════════ */
async function loadEmployees() {
  const host = $('#view-employees');
  await loadDirectory();
  host.innerHTML = `
    <div class="page-head">
      <div><h2>Сотрудники</h2><div class="sub">Нажмите на строку, чтобы открыть карточку со всеми подробностями</div></div>
      <div class="spacer"></div>
      <button class="btn btn-primary btn-sm" id="e-add">+ Добавить сотрудника</button>
    </div>
    <div class="table-wrap">
      <table class="data responsive"><thead><tr>
        <th>Сотрудник</th><th>Должность</th><th>Блок графика</th><th>Статус</th><th></th>
      </tr></thead><tbody>
      ${state.employees.map(e => `<tr data-card="${e.id}" style="cursor:pointer">
        <td class="who" data-label="Сотрудник">
          <span class="dot-pos" style="display:inline-block;width:9px;height:9px;border-radius:3px;background:${e.group_color};margin-right:7px"></span>${esc(e.full_name)}
          <small>${esc(e.position || '')}${e.telegram ? ' · tg: ' + esc(e.telegram) : ''}</small></td>
        <td data-label="Должность">${esc(e.position || '—')}</td>
        <td data-label="Блок">${esc(e.schedule_group || '—')}</td>
        <td data-label="Статус">${e.deleted ? '<span class="badge muted">удалён (в истории)</span>'
          : e.dismissed_at ? `<span class="badge muted">уволен ${dateRu(e.dismissed_at)}</span>`
          : e.active ? '<span class="badge ok">работает</span>' : '<span class="badge muted">неактивен</span>'}</td>
        <td class="num"><span class="badge muted">карточка →</span></td>
      </tr>`).join('')}
      </tbody></table>
    </div>
    <p class="hint">Удаление скрывает сотрудника из списков и графика, но вся история (табель, отметки, аудит) сохраняется.</p>`;
  $('#e-add').onclick = () => employeeModal(null);
  $$('[data-card]', host).forEach(tr => tr.onclick = () =>
    employeeCard(state.employees.find(x => x.id === +tr.dataset.card)));
}

async function employeeCard(emp) {
  const history = await api(`/api/employees/${emp.id}/history`);
  const contacts = emp.contacts?.length ? emp.contacts
    : (emp.emergency_name ? [{ name: emp.emergency_name, phone: emp.emergency_phone, relation: '' }] : []);
  const canBank = ['admin', 'manager'].includes(state.user?.role);
  const bankNow = history.bank_now ?? emp.balance_hours;
  openModal({
    title: emp.full_name,
    subtitle: `${emp.position || 'должность не указана'} · ${emp.schedule_group || 'без блока'}`,
    wide: true,
    body: `
      <div class="grid-2">
        <div class="field"><span>Табельный номер</span><div style="font-weight:600">${esc(emp.tab_number || '—')}</div></div>
        <div class="field"><span>Дата приёма</span><div style="font-weight:600">${emp.hired_at ? dateRu(emp.hired_at) : '—'}</div></div>
        <div class="field"><span>Гражданство</span><div style="font-weight:600">${esc(emp.nationality || '—')}</div></div>
        <div class="field"><span>Подразделение / служба (для документов)</span><div style="font-weight:600">${esc(emp.subdivision || '—')}</div></div>
        <div class="field"><span>Департамент</span><div style="font-weight:600">${esc(emp.department || '—')}</div></div>
        <div class="field" style="grid-column:1/-1"><span>ФИО в родительном падеже (для документов)</span>
          <div style="font-weight:600">${esc(emp.full_name_genitive || emp.full_name_genitive_hint || '—')}${!emp.full_name_genitive && emp.full_name_genitive_hint ? ' <small class="muted">(подставляется автоматически)</small>' : ''}</div></div>
        <div class="field"><span>Телефон</span><div style="font-weight:600">${esc(emp.phone || '—')}</div></div>
        <div class="field"><span>Рабочая почта</span><div style="font-weight:600">${esc(emp.email || '—')}</div></div>
        <div class="field"><span>Telegram</span><div style="font-weight:600">${esc(emp.telegram || '—')}</div></div>
        <div class="field"><span>Логин / роль</span><div style="font-weight:600"><code>${esc(emp.username || '—')}</code> · ${esc(ROLE_TITLES[emp.role] || '—')}</div></div>
        <div class="field"><span>Банк часов (сейчас)</span><div class="${bankNow >= 0 ? 'balance-pos' : 'balance-neg'}" style="font-size:18px">${bankNow >= 0 ? '+' : ''}${hours(bankNow)} ч</div>
          <div class="hint" style="margin-top:2px">старт ${emp.balance_hours >= 0 ? '+' : ''}${hours(emp.balance_hours)} ч + переработки − отгулы/недоработки ± корректировки</div></div>
        <div class="field"><span>Статус</span><div style="font-weight:600">${emp.deleted ? 'удалён (хранится в истории)'
          : emp.dismissed_at ? `уволен (последний рабочий день ${dateRu(emp.dismissed_at)})` : emp.active ? 'работает' : 'неактивен'}</div></div>
      </div>
      <div class="opt-group-title">Периоды работы (приём → увольнение → повторный приём)</div>
      ${(history.employment || []).map(h => `<div style="font-size:13.5px;padding:3px 0">
        ${dateRu(h.start)} — ${h.end ? dateRu(h.end) : 'настоящее время'}${h.current ? ' <span class="badge ok">работает</span>' : ''}${h.note ? ` <small class="muted">· ${esc(h.note)}</small>` : ''}</div>`).join('') || '<div class="hint">нет записей</div>'}
      <div class="opt-group-title">Контакты близких (экстренно)</div>
      ${contacts.length ? contacts.map(c => `<div style="font-size:13.5px;padding:3px 0">
        <b>${esc(c.name)}</b> · ${esc(c.phone || '—')}${c.relation ? ` · ${esc(c.relation)}` : ''}</div>`).join('')
        : '<div class="hint">не указаны</div>'}
      <div class="opt-group-title">История должностей</div>
      ${history.positions.map(h => `<div style="font-size:13.5px;padding:3px 0">
        ${esc(h.position)} — с ${dateRu(h.start)}${h.end ? ` по ${dateRu(h.end)}` : ' — по настоящее время'}</div>`).join('') || '<div class="hint">нет записей</div>'}
      <div class="opt-group-title">Блоки графика (переходы между сменами)</div>
      ${history.blocks.map(h => `<div style="font-size:13.5px;padding:3px 0">
        «${esc(h.group)}» — с ${dateRu(h.start)}${h.end ? ` по ${dateRu(h.end)}` : ' — по настоящее время'}${h.pattern_label ? ` <small class="muted">· ${esc(h.pattern_label)}</small>` : ''}</div>`).join('') || '<div class="hint">нет записей</div>'}
      <div class="opt-group-title">Ручные корректировки банка часов</div>
      ${(history.bank_adjustments || []).map(a => `<div style="font-size:13.5px;padding:3px 0">
        <b class="${a.hours >= 0 ? 'balance-pos' : 'balance-neg'}">${a.hours >= 0 ? '+' : ''}${hours(a.hours)} ч</b>
        с ${dateRu(a.date)} — ${esc(a.note)} <small class="muted">(${esc(a.author)})</small></div>`).join('') || '<div class="hint">корректировок не было</div>'}`,
    footer: `
      <button class="btn btn-danger" data-delete>Удалить</button>
      ${emp.dismissed_at || (!emp.active && !emp.deleted)
        ? '<button class="btn" data-rehire>Принять обратно</button>'
        : '<button class="btn btn-ghost" data-dismiss>Уволить</button>'}
      <div style="flex:1"></div>
      ${canBank ? '<button class="btn btn-ghost" data-bank>Корректировка банка</button>' : ''}
      <button class="btn btn-ghost" data-block>Перевод в блок</button>
      <button class="btn btn-ghost" data-pos>Перевод на должность</button>
      <button class="btn btn-ghost" data-imp>Войти как сотрудник</button>
      <button class="btn btn-primary" data-edit>Изменить</button>`,
    onMount(m) {
      m.querySelector('[data-edit]').onclick = () => { closeModal(); employeeModal(emp); };
      m.querySelector('[data-imp]').onclick = async () => {
        await api('/api/auth/impersonate', { method: 'POST', body: { employee_id: emp.id } });
        const me = await api('/api/auth/me');
        state.user = me.user; renderUserChip(); closeModal(); navigate('me');
        toast('Вы смотрите интерфейс глазами сотрудника', 'warn');
      };
      m.querySelector('[data-pos]').onclick = () => { closeModal(); datedActionModal(emp, 'position'); };
      m.querySelector('[data-block]').onclick = () => { closeModal(); datedActionModal(emp, 'block'); };
      const dis = m.querySelector('[data-dismiss]');
      if (dis) dis.onclick = () => { closeModal(); datedActionModal(emp, 'dismiss'); };
      const reh = m.querySelector('[data-rehire]');
      if (reh) reh.onclick = () => { closeModal(); rehireModal(emp); };
      const bank = m.querySelector('[data-bank]');
      if (bank) bank.onclick = () => { closeModal(); bankAdjustModal(emp, history); };
      m.querySelector('[data-delete]').onclick = () => {
        closeModal();
        confirmDialog('Удалить сотрудника?',
          `${emp.full_name} исчезнет из списков и графика. Табель, отметки и аудит сохранятся в истории.`,
          async () => {
            await api(`/api/employees/${emp.id}/delete`, { method: 'POST' });
            toast('Сотрудник удалён из активных списков; история сохранена', 'ok');
            await loadDirectory(); loadEmployees();
          }, 'Удалить');
      };
    },
  });
}

/* ── шаблоны блоков: пятидневка (свои выходные) или индивидуальный цикл (3/3, 1/3, custom:РРВВ) ── */
function patternFieldsHtml(prefix, kind, workShifts, today) {
  if (kind === 'week5') return `
    <div class="opt-group-title" style="margin-top:8px">Выходные дни этого сотрудника (пятидневка)</div>
    <div class="wd-picker" id="${prefix}-wd">
      ${WD_SHORT.map((w, i) => `<label><input type="checkbox" value="${i}" ${(i === 5 || i === 6) ? 'checked' : ''}>${w}</label>`).join('')}
    </div>
    <label class="field" style="margin-top:8px"><span>Рабочая смена</span><select id="${prefix}-shift">
      ${workShifts.map(x => `<option value="${x.code}" ${x.code === 'DAY9' ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}
    </select></label>
    <p class="hint" style="margin:2px 0 0">У каждого сотрудника пятидневки СВОИ выходные: например у начальника вс/пн —
      отметьте «вс» и «пн» (снимите «сб»).</p>`;
  if (kind === 'cycle') return `
    <div class="grid-2" style="margin-top:8px">
      <label class="field"><span>Цикл</span><input type="text" id="${prefix}-cycle" value="3/3" placeholder="3/3, 1/3, 4/2 или custom:РРВВРВ"></label>
      <label class="field"><span>Опорная дата (начало цикла)</span><input type="date" id="${prefix}-anchor" value="${today}"></label>
    </div>
    <label class="field"><span>Рабочая смена</span><select id="${prefix}-shift">
      ${workShifts.map(x => `<option value="${x.code}">${esc(x.name)}</option>`).join('')}
    </select></label>
    <p class="hint" style="margin:2px 0 0">«Другие смены»: 3/3, 1/3, сутки через трое (смена 08:00–08:00) или
      произвольный цикл «custom:РРВВРВ» (Р — рабочий, В — выходной).</p>`;
  if (kind === 'manual') return '<p class="hint">График этого сотрудника заполняется вручную по ячейкам — автоматического шаблона нет.</p>';
  return '<p class="hint">Блок считается базовым циклом объекта (Настройки → Базовый цикл).</p>';
}

function collectPatternFields(prefix, kind, date) {
  const body = { kind };
  if (kind === 'week5') {
    body.off_weekdays = $$(`#${prefix}-wd input:checked`).map(i => +i.value);
    body.shift_code = $(`#${prefix}-shift`)?.value || '';
  } else if (kind === 'cycle') {
    body.cycle = $(`#${prefix}-cycle`)?.value.trim() || '3/3';
    body.anchor = $(`#${prefix}-anchor`)?.value || date;
    body.shift_code = $(`#${prefix}-shift`)?.value || '';
  }
  return body;
}

async function datedActionModal(emp, kind) {
  const titles = {
    position: 'Перевод на должность',
    block: 'Перевод между блоками графика',
    dismiss: 'Увольнение (деактивация)',
  };
  const today = todayISO();
  let groups = [];
  if (kind === 'block') {
    try { groups = await api('/api/group-choices'); } catch { groups = []; }
    if (!groups.length) groups = ['Смена 1', 'Смена 2', 'Пятидневка', 'Другие смены'].map(name => ({ name, kind: 'base', title: name, hint: '' }));
  }
  const workShifts = state.shiftTypes.filter(x => x.kind === 'work');
  openModal({
    title: titles[kind],
    subtitle: emp.full_name,
    wide: kind === 'block',
    body: kind === 'position' ? `
      <label class="field"><span>Новая должность</span><input type="text" id="da-position" value="${esc(emp.position || '')}"></label>
      <label class="field"><span>Дата перевода</span><input type="date" id="da-date" value="${today}"></label>
      <p class="hint">В истории должностей текущая запись закроется этой датой, новая откроется.</p>`
    : kind === 'block' ? `
      <label class="field"><span>Новый блок графика</span><select id="da-group">
        ${groups.map(g => `<option value="${esc(g.name)}" ${emp.schedule_group === g.name ? 'selected' : ''}>${esc(g.title || g.name)}</option>`).join('')}
      </select></label>
      <p class="hint" id="da-group-hint" style="margin-top:-4px"></p>
      <div id="da-pattern"></div>
      <label class="field" style="margin-top:8px"><span>Дата перевода</span><input type="date" id="da-date" value="${today}"></label>
      <p class="hint">В графике сотрудник будет виден в обоих блоках: дни до даты — неактивные в новом блоке,
      дни после — неактивные в старом. «Пятидневка» — у каждого свои выходные;
      «Другие смены» — индивидуальный график (3/3, 1/3, сутки через трое, «РРВВ» или вручную).</p>`
    : `
      <label class="field"><span>Дата увольнения (последний рабочий день)</span><input type="date" id="da-date" value="${today}"></label>
      <p class="hint">Сотрудник станет неактивным и не сможет войти; вся история (табель, отметки, документы) сохранится.
      В графике дни после этой даты станут неактивными. Принять обратно можно из карточки — «Принять обратно».</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Провести</button>`,
    onMount(m) {
      let blockKind = 'base';
      if (kind === 'block') {
        const sel = m.querySelector('#da-group');
        const hint = m.querySelector('#da-group-hint');
        const host = m.querySelector('#da-pattern');
        const renderPattern = () => {
          const g = groups.find(x => x.name === sel.value) || {};
          blockKind = g.kind || 'base';
          hint.textContent = g.hint || '';
          host.innerHTML = patternFieldsHtml('da', blockKind, workShifts, today);
        };
        sel.onchange = renderPattern;
        renderPattern();
      }
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        const date = $('#da-date').value || today;
        try {
          if (kind === 'position') {
            await api(`/api/employees/${emp.id}/position-change`, { method: 'POST',
              body: { position: $('#da-position').value.trim(), date } });
          } else if (kind === 'block') {
            const body = { group: $('#da-group').value, date, ...collectPatternFields('da', blockKind, date) };
            await api(`/api/employees/${emp.id}/block-change`, { method: 'POST', body });
          } else {
            await api(`/api/employees/${emp.id}/dismiss`, { method: 'POST', body: { date } });
          }
          closeModal();
          toast('Проведено: ' + titles[kind].toLowerCase() + ' с ' + dateRu(date), 'ok');
          await loadDirectory();
          if (state.view === 'employees') loadEmployees(); else navigate(state.view);
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ── повторный приём уволенного сотрудника с произвольной даты ── */
async function rehireModal(emp) {
  const today = todayISO();
  let groups = [];
  try { groups = await api('/api/group-choices'); } catch { groups = []; }
  const workShifts = state.shiftTypes.filter(x => x.kind === 'work');
  openModal({
    title: 'Принять обратно',
    subtitle: `${emp.full_name}${emp.dismissed_at ? ' · уволен(а), последний рабочий день ' + dateRu(emp.dismissed_at) : ''}`,
    wide: true,
    body: `
      <label class="field"><span>Дата приёма (первый рабочий день)</span><input type="date" id="rh-date" value="${today}"></label>
      <label class="field"><span>Должность (пусто — оставить прежнюю)</span>
        <input type="text" id="rh-position" value="" placeholder="${esc(emp.position || '')}"></label>
      ${groups.length ? `
      <label class="field"><span>Блок графика (пусто — оставить прежний «${esc(emp.schedule_group || '—')}»)</span>
        <select id="rh-group">
          <option value="">— оставить прежний —</option>
          ${groups.map(g => `<option value="${esc(g.name)}">${esc(g.title || g.name)}</option>`).join('')}
        </select></label>
      <div id="rh-pattern"></div>` : ''}
      <p class="hint">В графике будут видны смены до увольнения, неактивные дни между периодами
      и активные дни после нового приёма. Вся прошлая история (табель, отметки, документы) сохраняется,
      банк часов продолжается с прежнего значения.</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Принять на работу</button>`,
    onMount(m) {
      const sel = m.querySelector('#rh-group');
      const host = m.querySelector('#rh-pattern');
      let kind = '';
      if (sel) sel.onchange = () => {
        const g = groups.find(x => x.name === sel.value) || {};
        kind = sel.value ? (g.kind || 'base') : '';
        host.innerHTML = sel.value ? patternFieldsHtml('rh', kind, workShifts, today) : '';
      };
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        const date = $('#rh-date').value || today;
        const body = { date, position: $('#rh-position').value.trim() };
        if (sel && sel.value) {
          body.group = sel.value;
          Object.assign(body, collectPatternFields('rh', kind || 'base', date));
        }
        try {
          await api(`/api/employees/${emp.id}/rehire`, { method: 'POST', body });
          closeModal();
          toast(`Сотрудник принят обратно с ${dateRu(date)}`, 'ok');
          await loadDirectory();
          if (state.view === 'employees') loadEmployees(); else navigate(state.view);
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ── ручная корректировка банка часов (+/−) с причиной и историей ── */
async function bankAdjustModal(emp, history) {
  const today = todayISO();
  const bankNow = history?.bank_now ?? emp.balance_hours;
  openModal({
    title: 'Корректировка банка часов',
    subtitle: `${emp.full_name} · сейчас ${bankNow >= 0 ? '+' : ''}${hours(bankNow)} ч`,
    wide: true,
    body: `
      <div class="grid-2">
        <label class="field"><span>Часы (+ добавить / − списать)</span>
          <input type="number" step="0.5" id="ba-hours" placeholder="например 4 или -8"></label>
        <label class="field"><span>Действует с даты</span><input type="date" id="ba-date" value="${today}"></label>
      </div>
      <label class="field"><span>Причина (обязательно — попадёт в историю)</span>
        <input type="text" id="ba-note" placeholder="Например: исправление потерянных отметок 12.09 по служебной записке №3"></label>
      <div class="opt-group-title">История корректировок</div>
      <div id="ba-list">${(history?.bank_adjustments || []).map(a => `<div style="font-size:13.5px;padding:3px 0;display:flex;gap:8px;align-items:center">
        <b class="${a.hours >= 0 ? 'balance-pos' : 'balance-neg'}">${a.hours >= 0 ? '+' : ''}${hours(a.hours)} ч</b>
        <span>с ${dateRu(a.date)} — ${esc(a.note)} <small class="muted">(${esc(a.author)})</small></span>
        <button class="btn btn-sm btn-ghost" data-del-adj="${a.id}" title="Удалить корректировку">✕</button></div>`).join('') || '<div class="hint">пока не было</div>'}</div>
      <p class="hint">Корректировку может сделать только администратор или менеджер; автор, причина и время
      сохраняются в журнале аудита. Банк = стартовый баланс + переработки − отгулы/недоработки ± корректировки.</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Закрыть</button>
             <button class="btn btn-primary" data-ok>Применить корректировку</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      const reopen = async () => {
        const h = await api(`/api/employees/${emp.id}/history`);
        closeModal(); bankAdjustModal({ ...emp, balance_hours: emp.balance_hours }, h);
      };
      $$('[data-del-adj]', m).forEach(b => b.onclick = async () => {
        if (!confirm('Удалить эту корректировку банка?')) return;
        try { await api(`/api/employees/${emp.id}/bank-adjustments/${b.dataset.delAdj}`, { method: 'DELETE' });
          toast('Корректировка удалена', 'ok'); reopen();
        } catch (e) { toast(e.message, 'err'); }
      });
      m.querySelector('[data-ok]').onclick = async () => {
        const h = parseFloat($('#ba-hours').value);
        if (!h) return toast('Укажите часы — ненулевые, со знаком + или −', 'warn');
        const note = $('#ba-note').value.trim();
        if (!note) return toast('Укажите причину корректировки', 'warn');
        try {
          const r = await api(`/api/employees/${emp.id}/bank-adjust`, { method: 'POST',
            body: { hours: h, date: $('#ba-date').value || today, note } });
          toast(`Применено ${h >= 0 ? '+' : ''}${hours(h)} ч · банк теперь ${hours(r.bank_now)} ч`, 'ok');
          reopen();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

async function employeeModal(emp) {
  let groups = [];
  try { groups = await api('/api/group-choices'); } catch { groups = []; }
  const groupList = (groups.length ? groups : ['Смена 1', 'Смена 2', 'Пятидневка', 'Другие смены'].map(name => ({ name })))
    .map(g => typeof g === 'string' ? { name: g, title: g } : g);
  let departments = [];
  try { departments = await api('/api/departments'); } catch { departments = []; }
  try { state.subdivisions = await api('/api/subdivisions', { silent: true }); }
  catch { state.subdivisions = state.subdivisions || []; }
  const isNew = !emp;
  const contacts = emp?.contacts?.length ? emp.contacts
    : (emp?.emergency_name ? [{ name: emp.emergency_name, phone: emp.emergency_phone, relation: '' }] : []);
  openModal({
    title: isNew ? 'Новый сотрудник' : 'Изменить: ' + emp.full_name, wide: true,
    subtitle: isNew ? 'Логин создастся автоматически из ФИО' : 'Редактор карточки',
    body: `
      <div class="grid-2">
        <label class="field"><span>ФИО *</span><input type="text" id="e-full" value="${esc(emp?.full_name || '')}" placeholder="Иванов Иван Иванович"></label>
        <label class="field"><span>Кратко (для сетки)</span><input type="text" id="e-short" value="${esc(emp?.short_name || '')}" placeholder="Иванов И.И."></label>
        <div class="field" style="grid-column:1/-1"><span>ФИО в родительном падеже — для документов («от …»)</span>
          <div style="display:flex;gap:8px;align-items:center">
            <input type="text" id="e-full-gen" value="${esc(emp?.full_name_genitive || '')}"
              placeholder="${esc(emp?.full_name_genitive_hint || 'Федоренко Николая Сергеевича')}" style="flex:1">
            <button class="btn btn-sm" id="e-gen-suggest" type="button"
              title="Предложить вариант по ФИО (проверьте окончание фамилии)">Подсказать</button>
          </div>
          <div class="hint" style="margin-top:2px">Если поле пустое, система подставит сюда автоматический вариант (показан как подсказка в поле).</div>
        </div>
        <label class="field"><span>Должность</span><input type="text" id="e-pos" value="${esc(emp?.position || '')}" placeholder="Батлер"></label>
        <label class="field"><span>Табельный номер</span><input type="text" id="e-tab" value="${esc(emp?.tab_number || '')}" placeholder="017"></label>
        <label class="field"><span>Гражданство</span><input type="text" id="e-nat" value="${esc(emp?.nationality || '')}" placeholder="Российская Федерация"></label>
        <label class="field"><span>Подразделение / служба (для документов)</span><select id="e-subdiv">
          <option value="">— не указано —</option>
          ${(state.subdivisions || []).map(s => `<option value="${esc(s.name)}" ${emp?.subdivision === s.name ? 'selected' : ''}>${esc(s.name)}</option>`).join('')}
          ${emp?.subdivision && !(state.subdivisions || []).some(s => s.name === emp.subdivision)
            ? `<option value="${esc(emp.subdivision)}" selected>${esc(emp.subdivision)}</option>` : ''}
        </select><div class="hint" style="margin-top:2px">Справочник — в «Настройки → Департаменты и службы».</div></label>
        <label class="field"><span>Департамент</span><select id="e-dep">
          <option value="">— не выбран —</option>
          ${departments.map(d => `<option value="${d.id}" ${emp?.department_id === d.id ? 'selected' : ''}>${esc(d.name)}</option>`).join('')}
        </select></label>
        <label class="field"><span>Дата приёма на работу</span><input type="date" id="e-hired" value="${esc(emp?.hired_at || '')}"></label>
        <label class="field"><span>Телефон</span><input type="text" id="e-phone" value="${esc(emp?.phone || '')}"></label>
        <label class="field"><span>Рабочая почта</span><input type="email" id="e-email" value="${esc(emp?.email || '')}" placeholder="i.ivanov@butler.service"></label>
        <label class="field"><span>Логин Telegram</span><input type="text" id="e-tg" value="${esc(emp?.telegram || '')}" placeholder="@ivanov"></label>
        <label class="field"><span>Блок графика (в сетке)</span><select id="e-group">
          <option value="">— не задано —</option>
          ${groupList.map(g => `<option value="${esc(g.name)}" ${emp?.schedule_group === g.name ? 'selected' : ''}>${esc(g.title || g.name)}</option>`).join('')}
        </select></label>
        <label class="field"><span>Роль в системе</span><select id="e-role">
          ${['employee', 'supervisor', 'manager', 'admin'].map(r => `<option value="${r}" ${emp?.role === r ? 'selected' : ''}>${ROLE_TITLES[r]}</option>`).join('')}
        </select></label>
        <label class="field"><span>Стартовый банк часов</span><input type="number" step="0.5" id="e-balance" value="${emp?.balance_hours ?? 0}"></label>
        <label class="field"><span>Логин</span><input type="text" id="e-login" value="${esc(emp?.username || '')}" placeholder="создастся автоматически"></label>
      </div>
      <div class="opt-group-title">Контакты близких (экстренно) — можно несколько</div>
      <div id="e-contacts">
        ${contacts.map((c, i) => contactRow(c, i)).join('')}
      </div>
      <button class="btn btn-sm" id="e-add-contact" type="button">+ Добавить контакт</button>
      <div class="field" style="margin-top:14px"><span>Цвет должности (для сетки и строк табеля)</span>
        <div class="color-swatches" id="e-colors">
          ${POSITION_COLORS.map(pc => `
            <label title="${esc(pc.t)}" style="background:${pc.c}">
              <input type="radio" name="e-color" value="${pc.c}" ${(emp?.group_color || '#8a94a6') === pc.c ? 'checked' : ''}>
            </label>`).join('')}
        </div>
      </div>
      <div class="grid-2">
        <label class="field"><span>${isNew ? 'Пароль (по умолчанию demo1234)' : 'Новый пароль (оставьте пустым, чтобы не менять)'}</span>
          <input type="text" id="e-pass" placeholder="••••••••"></label>
        <label class="field"><span>Подтверждение пароля</span>
          <input type="text" id="e-pass2" placeholder="••••••••"></label>
      </div>`,
    footer: `
      <div style="flex:1"></div>
      <button class="btn btn-ghost" data-cancel>Отмена</button>
      <button class="btn btn-primary" data-save>${isNew ? 'Создать' : 'Сохранить'}</button>`,
    onMount(m) {
      let ci = contacts.length;
      const host = m.querySelector('#e-contacts');
      m.querySelector('#e-add-contact').onclick = () => {
        host.insertAdjacentHTML('beforeend', contactRow(null, ci++));
        bindContactRemove(host);
      };
      bindContactRemove(host);
      m.querySelector('#e-gen-suggest').onclick = async () => {
        const fio = $('#e-full').value.trim();
        if (!fio) return toast('Сначала заполните ФИО', 'warn');
        try {
          const r = await api('/api/employees/suggest-genitive', { method: 'POST', body: { full_name: fio } });
          $('#e-full-gen').value = r.genitive || '';
          toast('Проверьте окончание фамилии: автоподстановка может ошибаться', 'ok');
        } catch (e) { toast(e.message, 'err'); }
      };
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        const pass = m.querySelector('#e-pass').value;
        const pass2 = m.querySelector('#e-pass2').value;
        if (pass && pass !== pass2) return toast('Пароли не совпадают', 'warn');
        const color = m.querySelector('#e-colors input:checked')?.value || '#8a94a6';
        const contactList = $$('#e-contacts .contact-row', m).map(row => ({
          name: row.querySelector('.c-name').value.trim(),
          phone: row.querySelector('.c-phone').value.trim(),
          relation: row.querySelector('.c-rel').value.trim(),
        })).filter(c => c.name);
        const body = {
          full_name: $('#e-full').value.trim(), short_name: $('#e-short').value.trim(),
          full_name_genitive: $('#e-full-gen').value.trim(),
          position: $('#e-pos').value.trim(), phone: $('#e-phone').value.trim(),
          tab_number: $('#e-tab').value.trim(), hired_at: $('#e-hired').value || null,
          nationality: $('#e-nat').value.trim(), subdivision: $('#e-subdiv').value.trim(),
          department_id: $('#e-dep').value ? +$('#e-dep').value : null,
          email: $('#e-email').value.trim(), telegram: $('#e-tg').value.trim(),
          emergency_name: contactList[0]?.name || '', emergency_phone: contactList[0]?.phone || '',
          contacts: contactList,
          schedule_group: $('#e-group').value, group_color: color,
          balance_hours: +$('#e-balance').value || 0,
          username: $('#e-login').value.trim() || null, password: pass || null,
          role: $('#e-role').value,
        };
        if (!body.full_name) return toast('Укажите ФИО', 'warn');
        try {
          const res = isNew
            ? await api('/api/employees', { method: 'POST', body })
            : await api(`/api/employees/${emp.id}`, { method: 'PUT', body });
          closeModal();
          await loadDirectory();
          toast(isNew ? `Создан: ${res.full_name}, логин ${res.username}, пароль ${res.initial_password}` : 'Изменения сохранены', 'ok');
          loadEmployees();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

function contactRow(c, i) {
  return `<div class="grid-2 contact-row" style="grid-template-columns:1fr 1fr 1fr auto;gap:8px;margin-bottom:6px">
    <input class="c-name" type="text" placeholder="Имя, например Иванова М. И." value="${esc(c?.name || '')}">
    <input class="c-phone" type="text" placeholder="+7 900 000-00-00" value="${esc(c?.phone || '')}">
    <input class="c-rel" type="text" placeholder="кем приходится (жена, мать…)" value="${esc(c?.relation || '')}">
    <button class="btn btn-sm btn-danger c-del" type="button" title="Убрать контакт">✕</button>
  </div>`;
}
function bindContactRemove(host) {
  host.querySelectorAll('.c-del').forEach(b => b.onclick = () => b.closest('.contact-row').remove());
}

/* ══════════════════════════════════════════════════════════════════
   НАСТРОЙКИ: правила + словарь смен (произвольные часы)
   ══════════════════════════════════════════════════════════════════ */
/* ── справочники «Департаменты и службы» (панель настроек) ── */
async function renderDicts() {
  const host = $('#dicts-body');
  if (!host) return;
  let deps = [], subs = [];
  try { deps = await api('/api/departments', { silent: true }); } catch {}
  try { subs = await api('/api/subdivisions', { silent: true }); } catch {}
  state.departments = deps; state.subdivisions = subs;
  const dictCol = (items, kind, title, ph) => `
    <div>
      <div class="opt-group-title">${title}</div>
      <table class="data"><tbody>
        ${items.length ? items.map(d => `<tr>
          <td>${esc(d.name)}</td>
          <td class="num" style="white-space:nowrap">
            <button class="btn btn-sm btn-ghost" data-${kind}-ren="${d.id}">Переименовать</button>
            <button class="btn btn-sm btn-ghost" data-${kind}-del="${d.id}">Удалить</button>
          </td></tr>`).join('') : '<tr><td class="empty">Пока не созданы</td></tr>'}
      </tbody></table>
      <div style="display:flex;gap:8px;margin-top:8px">
        <input type="text" id="${kind}-new" placeholder="${ph}" style="flex:1">
        <button class="btn btn-sm" id="${kind}-add">+ Добавить</button>
      </div>
    </div>`;
  host.innerHTML = dictCol(deps, 'dep', 'Департаменты', 'Новый департамент')
                 + dictCol(subs, 'sub', 'Службы / подразделения', 'Новая служба');

  const wire = (kind, url) => {
    const items = () => (kind === 'dep' ? state.departments : state.subdivisions);
    const add = async () => {
      const inp = $(`#${kind}-new`);
      const name = inp.value.trim();
      if (!name) return toast('Введите название', 'warn');
      try { await api(url, { method: 'POST', body: { name } }); toast('Добавлено', 'ok'); renderDicts(); }
      catch (e) { toast(e.message, 'err'); }
    };
    $(`#${kind}-add`).onclick = add;
    $(`#${kind}-new`).onkeydown = ev => { if (ev.key === 'Enter') add(); };
    $$(`[data-${kind}-ren]`, host).forEach(b => b.onclick = () =>
      renameDictModal(url, items().find(x => x.id === +b.dataset[`${kind}Ren`])));
    $$(`[data-${kind}-del]`, host).forEach(b => b.onclick = () => {
      const item = items().find(x => x.id === +b.dataset[`${kind}Del`]);
      if (!item) return;
      confirmDialog(`Удалить «${item.name}»?`,
        'У сотрудников, где это значение выбрано, поле будет очищено. История документов не меняется.',
        async () => {
          try { await api(`${url}/${item.id}`, { method: 'DELETE' }); toast('Удалено', 'ok'); renderDicts(); }
          catch (e) { toast(e.message, 'err'); }
        }, 'Удалить');
    });
  };
  wire('dep', '/api/departments');
  wire('sub', '/api/subdivisions');
}

function renameDictModal(url, item) {
  if (!item) return;
  openModal({
    title: 'Переименовать',
    body: `<label class="field"><span>Название</span><input type="text" id="dict-name" value="${esc(item.name)}"></label>
           <p class="hint">Новое название автоматически обновится в карточках сотрудников.</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Сохранить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        const name = $('#dict-name').value.trim();
        if (!name) return toast('Введите название', 'warn');
        try {
          await api(`${url}/${item.id}`, { method: 'PUT', body: { name } });
          closeModal(); toast('Переименовано', 'ok'); renderDicts();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ── вид заявления: название, текст с плейсхолдерами, фирменный бланк .docx ── */
function openKindModal(kind) {
  const isNew = !kind;
  openModal({
    title: isNew ? 'Новый вид заявления' : kind.name,
    subtitle: isNew ? 'Код — строчная латиница: по нему хранится фирменный бланк .docx'
                    : `Код: ${kind.code}${kind.builtin ? ' · встроенный вид' : ''}`,
    wide: true,
    body: `
      <div class="grid-2">
        <label class="field"><span>Код (латиницей${isNew ? '' : ', неизменяемый'})</span>
          <input type="text" id="k-code" value="${esc(kind?.code || '')}" placeholder="mat_aid" ${isNew ? '' : 'disabled'}></label>
        <label class="field"><span>Название (как в списках)</span>
          <input type="text" id="k-name" value="${esc(kind?.name || '')}" placeholder="Заявление на материальную помощь"></label>
      </div>
      <label class="field"><span>Текст заявления (плейсхолдеры в фигурных скобках)</span>
        <textarea id="k-text" rows="12" style="font-family:ui-monospace,monospace;font-size:12px"
          placeholder="{director} / {company} / от {full_name_genitive} … ЗАЯВЛЕНИЕ … Прошу … {today} / {short_name}">${esc(kind?.text || '')}</textarea></label>
      <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
        <input type="checkbox" id="k-active" ${kind?.active !== false ? 'checked' : ''} style="width:17px;height:17px;accent-color:var(--primary)">
        Показывать вид в списках выбора (снимите, чтобы скрыть устаревший, но оставить в истории)
      </label>
      ${kind ? `<div class="rule-row" style="margin-top:10px;align-items:flex-start">
        <div><div class="lbl">Фирменный бланк компании (.docx)</div>
          <div class="desc">${kind.template?.uploaded
            ? `загружен: ${esc(kind.template.filename || '')} · найдено плейсхолдеров: ${(kind.template?.placeholders || []).length}`
            : 'не загружен — документ печатается текстом выше; бланк перекрывает текст и сохраняет шрифты, логотип и колонтитулы Word'}</div></div>
        <div class="rule-input" style="gap:6px;display:flex">
          <button class="btn btn-sm" id="k-sample" type="button">Пример .docx</button>
          <label class="btn btn-sm" style="cursor:pointer">Загрузить .docx
            <input type="file" accept=".docx" id="k-file" style="display:none"></label>
          ${kind.template?.uploaded ? '<button class="btn btn-sm btn-danger" id="k-tpl-del" type="button">Удалить бланк</button>' : ''}
        </div></div>`
        : '<p class="hint">После создания вида можно загрузить фирменный бланк .docx — он перекроет текст, сохранив оформление Word.</p>'}
      <details style="margin-top:8px"><summary class="hint" style="cursor:pointer">Доступные плейсхолдеры</summary>
        <table class="data" style="margin-top:8px">${Object.entries(state.docPlaceholders || {}).map(([k, v]) =>
          `<tr><td><code>{${esc(k)}}</code></td><td>${esc(v)}</td></tr>`).join('')}</table></details>`,
    footer: `${isNew ? '' : '<button class="btn btn-danger" data-del>Удалить вид</button>'}
             <div style="flex:1"></div>
             <button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-save>${isNew ? 'Создать' : 'Сохранить'}</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      const sampleBtn = m.querySelector('#k-sample');
      if (sampleBtn) sampleBtn.onclick = () =>
        downloadBlob(`/api/docs/sample?type=${encodeURIComponent(kind.code)}`, `sample_${kind.code}.docx`);
      const fileInp = m.querySelector('#k-file');
      if (fileInp) fileInp.onchange = async () => {
        const f = fileInp.files[0];
        if (!f) return;
        const fd = new FormData();
        fd.append('file', f);
        loading(true);
        try {
          const res = await fetch(`/api/docs/templates?type=${encodeURIComponent(kind.code)}`,
            { method: 'POST', credentials: 'same-origin', body: fd });
          const d = await res.json().catch(() => ({}));
          if (!res.ok) throw new Error(d.detail || `Ошибка ${res.status}`);
          toast(`Бланк загружен · найдено плейсхолдеров: ${d.placeholders.length}`, 'ok');
          closeModal(); loadSettings();
        } catch (e) { toast(e.message, 'err'); }
        finally { loading(false); }
      };
      const tplDel = m.querySelector('#k-tpl-del');
      if (tplDel) tplDel.onclick = async () => {
        if (!confirm('Удалить загруженный бланк? Документ будет печататься текстом из карточки вида.')) return;
        try {
          await api(`/api/docs/templates?type=${encodeURIComponent(kind.code)}`, { method: 'DELETE' });
          toast('Бланк удалён', 'ok');
          closeModal(); loadSettings();
        } catch (e) { toast(e.message, 'err'); }
      };
      const delBtn = m.querySelector('[data-del]');
      if (delBtn) delBtn.onclick = () => confirmDialog(`Удалить вид «${kind.name}»?`,
        'У смен словаря, привязанных к этому виду, печать заявления отключится. Загруженный бланк будет удалён.',
        async () => {
          try {
            const r = await api(`/api/docs/kinds/${kind.id}`, { method: 'DELETE' });
            closeModal();
            toast(`Вид удалён${r.shifts_cleared ? ` · отвязано смен: ${r.shifts_cleared}` : ''}`, 'ok');
            loadSettings();
          } catch (e) { toast(e.message, 'err'); }
        }, 'Удалить');
      m.querySelector('[data-save]').onclick = async () => {
        const body = { name: $('#k-name').value.trim(), text: $('#k-text').value,
                       active: $('#k-active').checked, sort_order: kind?.sort_order ?? 100 };
        if (!body.name) return toast('Введите название', 'warn');
        try {
          if (isNew) {
            await api('/api/docs/kinds', { method: 'POST',
              body: { ...body, code: $('#k-code').value.trim() } });
          } else {
            await api(`/api/docs/kinds/${kind.id}`, { method: 'PUT', body });
          }
          closeModal();
          toast(isNew ? 'Вид заявления создан' : 'Вид заявления сохранён', 'ok');
          loadSettings();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

async function loadSettings() {
  const host = $('#view-settings');
  host.innerHTML = '<div class="empty">Загрузка…</div>';
  const [data, audit] = await Promise.all([api('/api/settings'), api('/api/timesheet/audit?limit=40')]);
  let docsInfo = null;
  try {
    docsInfo = await api('/api/docs/kinds', { silent: true });
    state.docKinds = docsInfo.kinds || []; state.docPlaceholders = docsInfo.placeholders || {};
  } catch {}
  let shiftList = state.shiftTypes;
  if (state.showArchived) {
    try { shiftList = await api('/api/shift-types?include_archived=true', { silent: true }); } catch {}
  }

  const input = item => {
    if (item.type === 'bool') {
      return `<label class="switch"><input type="checkbox" data-k="${item.key}" ${item.value ? 'checked' : ''}><span class="sl"></span></label>`;
    }
    const type = item.type === 'int' ? 'number' : 'text';
    return `<input type="${type}" class="rule-v" data-k="${item.key}" value="${esc(item.value)}" style="max-width:180px">`;
  };

  host.innerHTML = `
    <div class="page-head">
      <div><h2>Настройки</h2><div class="sub">Правила расчёта, словарь смен (любые часы), журнал изменений</div></div>
      <div class="spacer"></div>
      <button class="btn btn-primary btn-sm" id="s-save">Сохранить правила</button>
    </div>

    <div class="panel">
      <h3 class="panel-title">Смены и варианты графика (словарь)</h3>
      <div class="table-wrap" style="max-height:none">
        <table class="data responsive"><thead><tr>
          <th>Код</th><th>Название</th><th>Время</th><th>Часов</th><th>Код табеля</th><th>Тип</th><th></th>
        </tr></thead><tbody>
        ${shiftList.map(s => `<tr${s.archived ? ' style="opacity:.62"' : ''}>
          <td data-label="Код"><span class="shift-pill" style="background:${s.color};color:${textOn(s.color)}">${esc(s.code)}</span></td>
          <td data-label="Название">${esc(s.name)}</td>
          <td class="num" data-label="Время">${s.kind === 'work' ? `${esc(s.start_time)}–${esc(s.end_time)}${s.overnight ? ' (ночь)' : ''}` : '—'}</td>
          <td class="num" data-label="Часов">${s.kind === 'work' ? hours(s.planned_hours) : '—'}</td>
          <td data-label="Код табеля">${esc(s.tzh_code)}</td>
          <td data-label="Тип">${s.kind === 'work' ? '<span class="badge ok">смена</span>' : '<span class="badge muted">отсутствие</span>'}
            ${s.doc_type ? '<span class="badge info" title="Из ячейки графика печатается заявление">заявление</span>' : ''}
            ${s.kind !== 'work' && (s.punch_in_allowed === false || s.punch_out_allowed === false) ? '<span class="badge warn" title="Отмечаться во время этого отсутствия нельзя (настройка вида)">без отметок</span>' : ''}
            ${s.deduct_from_bank ? '<span class="badge warn" title="Часы отсутствия списываются из банка часов">часы из банка</span>' : ''}
            ${s.archived ? `<span class="badge muted" title="В архиве${s.archived_at ? ' с ' + dateRu(s.archived_at) : ''}: прошлые графики считаются, в новых ячейках недоступна">архив</span>` : ''}
            ${s.revisions ? `<span class="badge" title="Есть история значений: прошлые даты считаются по прежним часам">${s.revisions} изм.</span>` : ''}</td>
          <td class="num" style="white-space:nowrap">
            <button class="btn btn-sm btn-ghost" data-shift="${s.id}">Изменить</button>
            ${s.archived
              ? `<button class="btn btn-sm" data-restore="${s.id}">Вернуть</button>`
              : `<button class="btn btn-sm btn-ghost" data-archive="${s.id}" title="Убрать из словаря: прошлые графики и табели продолжат считаться по этой смене">В архив</button>`}
          </td>
        </tr>`).join('')}
        </tbody></table>
      </div>
      <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">
        <button class="btn btn-sm" id="s-add-shift">+ Новая смена / часы (например 08:00–17:00)</button>
        <button class="btn btn-sm btn-ghost" id="s-toggle-archived">${state.showArchived ? 'Скрыть архив' : 'Показать архив'}</button>
      </div>
      <p class="hint">«Удаление» смены = архив: она исчезает из новых назначений, но прошлые графики и табели
        продолжают считаться по ней. Изменение времени создаёт новую версию словаря: отработанные дни остаются
        посчитанными по ПРЕЖНИМ часам, дата вступления изменения указывается в редакторе смены.</p>
    </div>

    <div class="panel">
      <h3 class="panel-title">Департаменты и службы (справочники)</h3>
      <p class="hint" style="margin:-6px 0 12px">Значения справочников попадают в карточку сотрудника
        и подставляются в документы. Переименование обновляет карточки, удаление — очищает
        поле у сотрудников, где значение было выбрано.</p>
      <div class="grid-2" id="dicts-body"><div class="empty">Загрузка…</div></div>
    </div>

    <div class="panel">
      <h3 class="panel-title">Базовый цикл объекта (Смена 1 / Смена 2)</h3>
      <p class="hint" style="margin:-6px 0 12px">Задаётся один раз и действует на все месяцы вперёд и назад.
        Ручные ячейки графика — исключения (отпуск, больничный, подмена) и перекрывают базовый цикл.</p>
      <div class="grid-2">
        <label class="field"><span>Цикл смен 1/2</span><select id="b-cycle">
          ${['2/2', '3/3', '4/2', '4/3', '1/3'].map(c => `<option ${data.base?.cycle === c ? 'selected' : ''}>${c}</option>`).join('')}
          <option value="custom" ${String(data.base?.cycle || '').startsWith('custom') ? 'selected' : ''}>произвольный…</option>
        </select></label>
        <label class="field"><span>Опорная дата (день, когда Смена 1 рабочая)</span>
          <input type="date" id="b-anchor" value="${esc(data.base?.anchor || '2024-01-01')}"></label>
        <label class="field hidden" id="b-cycle-wrap"><span>Произвольный цикл (Р/В)</span>
          <input type="text" id="b-cycle-custom" value="${esc(String(data.base?.cycle || '').startsWith('custom') ? String(data.base.cycle).slice(7) : '')}" placeholder="РРВВВВРР"></label>
        <label class="field"><span>Смена блока «Смена 1»</span><select id="b-shift1">
          ${state.shiftTypes.filter(x => x.kind === 'work').map(x => `<option value="${x.code}" ${data.base?.groups?.['Смена 1']?.shift_code === x.code ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}
        </select></label>
        <label class="field"><span>Смена блока «Смена 2»</span><select id="b-shift2">
          ${state.shiftTypes.filter(x => x.kind === 'work').map(x => `<option value="${x.code}" ${data.base?.groups?.['Смена 2']?.shift_code === x.code ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}
        </select></label>
      </div>
      <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
        <input type="checkbox" id="b-invert2" ${data.base?.groups?.['Смена 2']?.invert !== false ? 'checked' : ''}
          style="width:17px;height:17px;accent-color:var(--primary)">
        Смена 2 работает в противофазе со Сменой 1 (когда одни работают — другие отдыхают)
      </label>
      <div class="opt-group-title">Пятидневка и «Другие смены»</div>
      <p class="hint" style="margin-top:0">Здесь не настраиваются. У «Пятидневки» выходные задаются
        для КАЖДОГО сотрудника индивидуально (Сотрудники → карточка → «Перевод в блок»: например у начальника вс/пн,
        у бэк-специалиста сб/вс). «Другие смены» — контейнер индивидуальных графиков: 3/3, 1/3, сутки через трое,
        произвольный цикл «custom:РРВВ» или ручное заполнение ячеек.</p>
      <button class="btn btn-primary btn-sm" id="s-base-save" style="margin-top:4px">Сохранить базовый цикл</button>
    </div>

    <div class="panel">
      <h3 class="panel-title">Дни двойной оплаты (производственный календарь) и ВИП-гости</h3>
      <p class="hint" style="margin:-6px 0 10px">В отмеченные дни переработки оплачиваются по двойному тарифу
        и попадают в реестр «Переработки к выплате» кодами <b class="dbl">ДЯ2</b>/<b class="dbl">ДН2</b>.
        Стоимость часов внутри смены не меняется — двойные только переработки; списания, ложащиеся на двойные
        часы, снимаются вполовину (8 часов оплаты = 4 часа ДЯ2). Календарь заполняется из производственного
        календаря / писем C&B — хоть на год вперёд; любая правка сразу пересчитывает затронутые дни табеля.</p>
      <div id="dp-body"><div class="empty">Загрузка…</div></div>
    </div>

    <div class="panel">
      <h3 class="panel-title">Виды заявлений и шаблоны</h3>
      <p class="hint" style="margin:-6px 0 12px">Виды заявлений — расширяемый справочник: у каждого свой текст
        с плейсхолдерами и (по желанию) фирменный бланк .docx. Вид привязывается к отсутствию в словаре смен —
        документ печатается из ячейки графика («Печать заявления», DOCX, PDF).
        ${docsInfo?.pdf_available ? '' : '<br>PDF-конвертация станет доступна после установки LibreOffice на сервер (<code>soffice</code>); DOCX работает всегда.'}</p>
      <div class="grid-2">
        <label class="field"><span>Организация</span><input type="text" id="d-company" value="${esc(data.doc?.company || '')}"></label>
        <label class="field"><span>Кому (шапка)</span><input type="text" id="d-director" value="${esc(data.doc?.director || '')}"></label>
      </div>
      <button class="btn btn-primary btn-sm" id="s-doc-save">Сохранить реквизиты</button>
      <table class="data" style="margin-top:14px"><thead><tr>
        <th>Вид заявления</th><th>Код</th><th>Фирменный бланк</th><th></th></tr></thead>
      <tbody>${(docsInfo?.kinds || []).map(k => `<tr>
        <td>${esc(k.name)}${k.builtin ? ' <span class="badge">встроенный</span>' : ''}${k.active ? '' : ' <span class="badge muted">скрыт</span>'}</td>
        <td><code>${esc(k.code)}</code></td>
        <td>${k.template?.uploaded ? `<span class="badge ok" title="${esc(k.template.filename || '')}">загружен</span>` : '<span class="badge muted">печать текстом</span>'}</td>
        <td class="num" style="white-space:nowrap"><button class="btn btn-sm btn-ghost" data-kind="${k.id}">Изменить</button></td>
      </tr>`).join('') || '<tr><td colspan="4" class="empty">Виды заявлений не найдены</td></tr>'}</tbody></table>
      <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
        <button class="btn btn-sm" id="s-add-kind">+ Новый вид заявления</button>
        <button class="btn btn-sm btn-ghost" id="s-kind-help">Справка по плейсхолдерам</button>
      </div>
    </div>

    <div class="panel">
      <h3 class="panel-title">Правила расчёта</h3>
      ${data.items.map(i => `<div class="rule-row">
        <div><div class="lbl">${esc(i.description || i.key)}</div><div class="desc"><code>${esc(i.key)}</code> · по умолчанию: ${esc(i.default)}</div></div>
        <div class="rule-input">${input(i)}${String(i.value) !== String(i.default) ? `<span class="badge warn" title="по умолчанию ${esc(i.default)}">изменено</span>` : ''}</div>
      </div>`).join('')}
      <p class="hint">После изменения правил нажмите «Пересчитать» в табеле. Перерывы и денежные расчёты в системе не ведутся — только часы.</p>
    </div>

    <div class="panel">
      <h3 class="panel-title">Данные системы</h3>
      <div class="stat-grid">
        <div class="stat"><div class="k">Сотрудников</div><div class="v">${data.counts.employees}</div></div>
        <div class="stat"><div class="k">Учётных записей</div><div class="v">${data.counts.users}</div></div>
        <div class="stat"><div class="k">Ячеек графика</div><div class="v">${data.counts.schedule_entries}</div></div>
        <div class="stat"><div class="k">Отметок</div><div class="v">${data.counts.punches}</div></div>
        <div class="stat"><div class="k">Строк табеля</div><div class="v">${data.counts.timesheet_rows}</div></div>
      </div>
      <button class="btn btn-sm" id="s-recalc">Пересчитать весь текущий месяц</button>
    </div>

    <div class="panel">
      <h3 class="panel-title">Журнал изменений (аудит)</h3>
      ${audit.map(a => `<div class="audit-item">
        <span class="ts">${esc(a.ts.replace('T', ' '))}</span>
        <span class="ac">${esc(a.action)}</span>
        <span style="color:var(--muted)">${esc(a.actor)} · ${esc(a.target)}</span></div>`).join('') || '<div class="empty">Пусто</div>'}
    </div>`;

  $('#s-doc-save').onclick = async () => {
    try {
      await api('/api/settings/doc', { method: 'PUT', body: {
        company: $('#d-company').value, director: $('#d-director').value } });
      state.doc = null;
      toast('Реквизиты сохранены', 'ok');
      loadSettings();
    } catch (e) { toast(e.message, 'err'); }
  };
  $('#s-add-kind').onclick = () => openKindModal(null);
  $$('[data-kind]', host).forEach(b => b.onclick = () =>
    openKindModal((docsInfo?.kinds || []).find(k => k.id === +b.dataset.kind)));
  $('#s-kind-help').onclick = () => openModal({
    title: 'Плейсхолдеры документов', wide: true,
    body: `<table class="data">${Object.entries(docsInfo?.placeholders || {}).map(([k, v]) =>
      `<tr><td><code>{${esc(k)}}</code></td><td>${esc(v)}</td></tr>`).join('')}</table>`,
    footer: '<button class="btn btn-primary" data-ok>Понятно</button>',
    onMount(m) { m.querySelector('[data-ok]').onclick = closeModal; },
  });
  const syncCycle = () => $('#b-cycle-wrap').classList.toggle('hidden', $('#b-cycle').value !== 'custom');
  $('#b-cycle').onchange = syncCycle; syncCycle();
  $('#s-base-save').onclick = async () => {
    const cycle = $('#b-cycle').value === 'custom'
      ? 'custom:' + $('#b-cycle-custom').value.trim()
      : $('#b-cycle').value;
    const body = {
      cycle, anchor: $('#b-anchor').value,
      groups: {
        'Смена 1': { shift_code: $('#b-shift1').value, invert: false },
        'Смена 2': { shift_code: $('#b-shift2').value, invert: $('#b-invert2').checked },
        /* пятидневка: шаблон по умолчанию сохраняем, выходные каждого сотрудника — в его карточке */
        'Пятидневка': data.base?.groups?.['Пятидневка'] || { shift_code: 'DAY9', off_weekdays: [5, 6] },
      },
    };
    try {
      await api('/api/settings/base', { method: 'PUT', body });
      toast('Базовый цикл сохранён и действует на все месяцы', 'ok');
      loadSettings();
    } catch (e) { toast(e.message, 'err'); }
  };
  $('#s-save').onclick = async () => {
    const payload = [];
    // только поля правил (у них есть data-k): класс .rule-row используется и в
    // панели шаблонов документов, где лежат файловые инпуты — они ломали сохранение (422)
    $$('.rule-row input[data-k]').forEach(i => {
      const v = i.type === 'checkbox' ? (i.checked ? '1' : '0') : i.value;
      payload.push({ key: i.dataset.k, value: String(v) });
    });
    try {
      await api('/api/settings', { method: 'PUT', body: payload });
      toast('Правила сохранены. Не забудьте пересчитать табель.', 'ok');
      loadSettings();
    } catch (e) { toast(e.message, 'err'); }
  };
  $('#s-recalc').onclick = async () => {
    /* Тяжёлый пересчёт запускаем в фоне и опрашиваем статус: иначе на большом штате
       запрос висит секундами и упирается в таймаут прокси. */
    const btn = $('#s-recalc');
    try {
      const r = await api('/api/settings/recalc-all?background=1', { method: 'POST' });
      if (!r.started) { toast(r.detail || 'Пересчёт уже запущен', 'warn'); return; }
      btn.disabled = true;
      const label = btn.textContent;
      btn.textContent = 'Пересчёт…';
      toast('Пересчёт табеля запущен в фоне', 'ok');
      const tick = setInterval(async () => {
        try {
          const st = await api('/api/settings/recalc-status', { silent: true });
          if (st.running) { btn.textContent = 'Пересчёт…'; return; }
          clearInterval(tick);
          btn.disabled = false; btn.textContent = label;
          const job = st.current || (st.jobs || [])[0];
          if (job?.status === 'done') {
            toast(`Пересчитано ${job.days} ${plural(job.days, 'день', 'дня', 'дней')}`, 'ok');
            if (state.view === 'timesheet') loadTimesheet();
          } else if (job?.status === 'error') {
            toast('Пересчёт завершился ошибкой: ' + (job.error || 'неизвестно'), 'err');
          }
        } catch { clearInterval(tick); btn.disabled = false; btn.textContent = label; }
      }, 1500);
    } catch (e) { toast(e.message, 'err'); }
  };
  $('#s-add-shift').onclick = () => shiftModal(null);
  renderDicts();
  $('#s-toggle-archived').onclick = () => { state.showArchived = !state.showArchived; loadSettings(); };
  $$('[data-shift]', host).forEach(b => b.onclick = () =>
    shiftModal(shiftList.find(x => x.id === +b.dataset.shift)));
  $$('[data-archive]', host).forEach(b => b.onclick = () => {
    const sh = shiftList.find(x => x.id === +b.dataset.archive);
    confirmDialog('Архивировать смену?',
      `«${sh?.name || ''}» исчезнет из словаря для НОВЫХ назначений, но все прошлые графики и табели
       продолжат считаться по этой смене — история не сломается. Смену можно вернуть из архива.`,
      async () => {
        try {
          await api(`/api/shift-types/${sh.id}`, { method: 'DELETE' });
          toast('Смена перенесена в архив', 'ok');
          await loadDirectory(); loadSettings();
        } catch (e) { toast(e.message, 'err'); }
      }, 'В архив');
  });
  $$('[data-restore]', host).forEach(b => b.onclick = async () => {
    try {
      await api(`/api/shift-types/${b.dataset.restore}/restore`, { method: 'POST' });
      toast('Смена возвращена в словарь', 'ok');
      await loadDirectory(); loadSettings();
    } catch (e) { toast(e.message, 'err'); }
  });
  refreshDoublePay();
}

/* ══════════════════════════════════════════════════════════════════
   ДНИ ДВОЙНОЙ ОПЛАТЫ: производственный календарь + ВИП-гости
   ══════════════════════════════════════════════════════════════════ */
const DP_MONTHS = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
                   'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'];
const DP_WD = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];

async function refreshDoublePay() {
  const body = document.querySelector('#dp-body');
  if (!body) return;
  const year = state.dpYear || (state.dpYear = new Date().getFullYear());
  let data;
  try {
    data = await api(`/api/doublepay?year=${year}`, { silent: true });
  } catch (e) {
    body.innerHTML = `<div class="empty">Не загрузилось: ${esc(e.message || e)}</div>`;
    return;
  }
  const canWrite = ['admin', 'manager'].includes(state.user?.role);
  const scopeShort = { shift: 'сменщики', week5: 'пятидневка', all: 'все' };
  const byMonth = {};
  data.days.forEach(d => { (byMonth[d.month] ||= []).push(d); });

  body.innerHTML = `
    <div class="dp-head">
      <div class="month-nav">
        <button id="dp-prev">‹</button><div class="label">${year}</div><button id="dp-next">›</button>
      </div>
      <span class="badge">${data.days.length} ${plural(data.days.length, 'день', 'дня', 'дней')} в календаре</span>
      ${!canWrite ? '<span class="hint" style="margin:0">Править может администратор или менеджер (данные из C&B)</span>' : ''}
    </div>

    ${canWrite ? `
    <div class="dp-form">
      <label class="field"><span>Для кого</span><select id="dp-scope">
        ${data.scopes.map(s => `<option value="${s.id}" ${s.id === 'all' ? 'selected' : ''}>${esc(s.title)}</option>`).join('')}
      </select></label>
      <label class="field"><span>Список дат (через запятую или пробел)</span>
        <input type="text" id="dp-dates" placeholder="01.01.${year}, 07.01.${year}, 23.02.${year}"></label>
      <div class="dp-or">или период</div>
      <label class="field"><span>С</span><input type="date" id="dp-start"></label>
      <label class="field"><span>По</span><input type="date" id="dp-end"></label>
      <div class="field"><span>Дни недели периода (пусто = все)</span>
        <div class="dp-wd">${DP_WD.map((w, i) => `<label><input type="checkbox" value="${i}">${w}</label>`).join('')}</div></div>
      <label class="field"><span>Примечание</span>
        <input type="text" id="dp-note" placeholder="Новогодние праздники · письмо C&B от …"></label>
      <button class="btn btn-primary btn-sm" id="dp-add">Добавить дни</button>
    </div>` : ''}

    ${Object.keys(byMonth).sort((a, b) => a - b).map(m => `
      <div class="opt-group-title">${DP_MONTHS[m - 1]}</div>
      <div class="dp-days">${byMonth[m].map(d => `
        <span class="dp-chip${d.is_weekend ? ' we' : ''}" title="${esc(d.scope_title)}${d.note ? ' · ' + esc(d.note) : ''}">
          <b>${esc(d.weekday)} ${String(d.day).padStart(2, '0')}.${String(d.month).padStart(2, '0')}</b>
          <i>${esc(scopeShort[d.scope] || d.scope)}</i>${d.note ? `<span>${esc(d.note)}</span>` : ''}
          ${canWrite ? `<button class="dp-del" data-day-del="${d.id}" title="Удалить день">×</button>` : ''}
        </span>`).join('')}</div>`).join('')
      || `<div class="empty" style="padding:10px 0">За ${year} год дней пока нет — добавьте из производственного календаря</div>`}

    <div class="opt-group-title" style="margin-top:14px">ВИП-гости: периоды двойных переработок</div>
    <p class="hint" style="margin-top:0">Сотрудник работает с ВИП-гостем — назначьте период, и его переработки в эти дни
      станут двойными (ДЯ2/ДН2), даже если по производственному календарю день обычный.
      Совпадение с календарём тариф не увеличивает — всегда ×2, не ×4.</p>
    ${canWrite ? `
    <div class="dp-form">
      <label class="field"><span>Сотрудник</span><select id="vip-emp">
        ${(state.employees || []).map(e => `<option value="${e.id}">${esc(e.full_name)}</option>`).join('')}
      </select></label>
      <label class="field"><span>С</span><input type="date" id="vip-start"></label>
      <label class="field"><span>По</span><input type="date" id="vip-end"></label>
      <label class="field"><span>Примечание</span><input type="text" id="vip-note" placeholder="ВИП-гость: фамилия / вилла"></label>
      <button class="btn btn-primary btn-sm" id="vip-add">Назначить ×2</button>
    </div>` : ''}
    ${data.vip.length ? data.vip.map(v => `
      <div class="rule-row">
        <div><div class="lbl">${esc(v.employee_full_name || v.employee_name)} ·
          ${dateRu(v.start_date)} – ${dateRu(v.end_date)}
          <span class="badge warn">${v.days} ${plural(v.days, 'день', 'дня', 'дней')}</span></div>
          <div class="desc">${esc(v.note || 'без примечания')}${v.author ? ' · добавил(а): ' + esc(v.author) : ''}</div></div>
        ${canWrite ? `<div class="rule-input"><button class="btn btn-sm btn-danger" data-vip-del="${v.id}">Удалить</button></div>` : ''}
      </div>`).join('') : '<div class="empty" style="padding:10px 0">Периодов нет</div>'}`;

  document.querySelector('#dp-prev').onclick = () => { state.dpYear = year - 1; refreshDoublePay(); };
  document.querySelector('#dp-next').onclick = () => { state.dpYear = year + 1; refreshDoublePay(); };
  if (canWrite) {
    document.querySelector('#dp-add').onclick = async () => {
      const weekdays = [...body.querySelectorAll('.dp-wd input:checked')].map(i => +i.value);
      const payload = {
        dates: document.querySelector('#dp-dates').value.trim(),
        start: document.querySelector('#dp-start').value || null,
        end: document.querySelector('#dp-end').value || null,
        weekdays: weekdays.length ? weekdays : null,
        scope: document.querySelector('#dp-scope').value,
        note: document.querySelector('#dp-note').value.trim(),
      };
      if (!payload.dates && !(payload.start && payload.end))
        return toast('Введите список дат или период', 'warn');
      try {
        const r = await api('/api/doublepay/days', { method: 'POST', body: payload });
        toast(`Добавлено: ${r.added}, обновлено: ${r.updated}. Пересчитано строк табеля: ${r.recalculated}`, 'ok');
        refreshDoublePay();
      } catch (e) { toast(e.message, 'err'); }
    };
    const vipBtn = document.querySelector('#vip-add');
    if (vipBtn) vipBtn.onclick = async () => {
      const payload = {
        employee_id: +document.querySelector('#vip-emp').value,
        start_date: document.querySelector('#vip-start').value,
        end_date: document.querySelector('#vip-end').value,
        note: document.querySelector('#vip-note').value.trim(),
      };
      if (!payload.employee_id || !payload.start_date || !payload.end_date)
        return toast('Выберите сотрудника и укажите даты периода', 'warn');
      try {
        const r = await api('/api/doublepay/vip', { method: 'POST', body: payload });
        toast(`Назначены двойные переработки: ${r.item.days} ${plural(r.item.days, 'день', 'дня', 'дней')}. Пересчитано строк: ${r.recalculated}`, 'ok');
        refreshDoublePay();
      } catch (e) { toast(e.message, 'err'); }
    };
  }
  body.querySelectorAll('[data-day-del]').forEach(b => b.onclick = () => {
    confirmDialog('Удалить день двойной оплаты?',
      'Переработки этого дня снова будут считаться одинарными (ДЯ/ДН). Табель пересчитается автоматически.',
      async () => {
        try {
          const r = await api(`/api/doublepay/days/${b.dataset.dayDel}`, { method: 'DELETE' });
          toast(`День удалён. Пересчитано строк табеля: ${r.recalculated}`, 'ok');
          refreshDoublePay();
        } catch (e) { toast(e.message, 'err'); }
      }, 'Удалить');
  });
  body.querySelectorAll('[data-vip-del]').forEach(b => b.onclick = () => {
    confirmDialog('Удалить ВИП-период?',
      'Переработки сотрудника в эти дни вернутся к обычному тарифу (если день не остался в календаре двойной оплаты).',
      async () => {
        try {
          const r = await api(`/api/doublepay/vip/${b.dataset.vipDel}`, { method: 'DELETE' });
          toast(`Период удалён. Пересчитано строк табеля: ${r.recalculated}`, 'ok');
          refreshDoublePay();
        } catch (e) { toast(e.message, 'err'); }
      }, 'Удалить');
  });
}

/* ── словарь смен: произвольные часы работы ── */
function shiftModal(st) {
  const isNew = !st;
  openModal({
    title: isNew ? 'Новая смена' : st.name,
    subtitle: 'Любые часы работы: 08:00–17:00, 09:00–18:00, ночные и т.д.',
    body: `
      <div class="grid-2">
        <label class="field"><span>Код (латиницей)</span><input type="text" id="sh-code" value="${esc(st?.code || '')}" placeholder="DAY9_17"></label>
        <label class="field"><span>Название</span><input type="text" id="sh-name" value="${esc(st?.name || '')}" placeholder="08:00–17:00 (9 ч)"></label>
        <label class="field"><span>Начало</span><input type="time" id="sh-start" value="${esc(st?.start_time || '08:00')}"></label>
        <label class="field"><span>Конец</span><input type="time" id="sh-end" value="${esc(st?.end_time || '17:00')}"></label>
        <label class="field"><span>Код в сетке и табеле (единый)</span><input type="text" id="sh-short" value="${esc(st?.display_code || st?.tzh_code || '')}" placeholder="08–17 / В / ОТ…"></label>
        <label class="field"><span>Тип</span><select id="sh-kind">
          <option value="work" ${st?.kind === 'work' ? 'selected' : ''}>рабочая смена</option>
          <option value="absence" ${st?.kind === 'absence' ? 'selected' : ''}>отсутствие / выходной</option>
        </select></label>
        <label class="field"><span>Заявление (печать из ячейки графика)</span><select id="sh-doc">
          <option value="">— не печатать —</option>
          ${(state.docKinds || []).filter(k => k.active !== false).map(k =>
            `<option value="${esc(k.code)}">${esc(k.name)}</option>`).join('')}
          ${st?.doc_type && !(state.docKinds || []).some(k => k.code === st.doc_type)
            ? `<option value="${esc(st.doc_type)}" selected>${esc(st.doc_type)} (вид удалён — выберите другой)</option>` : ''}
        </select></label>
        <label class="field"><span>Цвет</span><input type="color" id="sh-color" value="${esc(st?.color || '#34a862')}" style="height:44px;padding:4px"></label>
      </div>
      <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
        <input type="checkbox" id="sh-overnight" ${st?.overnight ? 'checked' : ''} style="width:17px;height:17px;accent-color:var(--primary)">
        Смена через полночь (ночная): конец принадлежит следующим суткам, часы — дате начала
      </label>
      <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
        <input type="checkbox" id="sh-deduct" ${st?.deduct_from_bank ? 'checked' : ''} style="width:17px;height:17px;accent-color:var(--primary)">
        Списывать часы этого отсутствия из банка часов («выходной за часы», «отпросился»)
      </label>
      <div id="sh-punch-wrap">
        <div class="opt-group-title" style="margin:12px 0 6px">Отметки во время этого отсутствия</div>
        <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
          <input type="checkbox" id="sh-punch-in" ${st?.punch_in_allowed !== false ? 'checked' : ''} style="width:17px;height:17px;accent-color:var(--primary)">
          Сотрудник может нажать «Пришёл на работу»
        </label>
        <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
          <input type="checkbox" id="sh-punch-out" ${st?.punch_out_allowed !== false ? 'checked' : ''} style="width:17px;height:17px;accent-color:var(--primary)">
          Сотрудник может нажать «Ушёл с работы»
        </label>
        <div class="hint" style="margin-top:4px">Если снять, кнопка в «Моих отметках» станет неактивной с подписью
          «сейчас статус: …». При назначении отсутствия на период или ячейку можно переопределить индивидуально.</div>
      </div>
      ${isNew ? '' : `<label class="field"><span>Изменения вступают в силу с даты</span>
        <input type="date" id="sh-eff" value="${todayISO()}">
        <div class="hint" style="margin-top:2px">Прошлые графики и табели останутся считаться по ПРЕЖНИМ значениям —
        история не ломается. Дату можно задать и в прошлом (тогда период пересчитается по-новому).</div></label>`}
      <p class="hint" id="sh-hours"></p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-save>${isNew ? 'Создать' : 'Сохранить'}</button>`,
    onMount(m) {
      $('#sh-doc').value = st?.doc_type || '';
      const kindToggle = () => {
        $('#sh-punch-wrap').style.display = $('#sh-kind').value === 'work' ? 'none' : '';
      };
      $('#sh-kind').onchange = kindToggle; kindToggle();
      const recalc = () => {
        const s = $('#sh-start').value, e = $('#sh-end').value;
        if (!s || !e) return;
        const [h1, m1] = s.split(':').map(Number), [h2, m2] = e.split(':').map(Number);
        let mins = (h2 * 60 + m2) - (h1 * 60 + m1);
        const over = mins <= 0;
        if (over) mins += 24 * 60;
        $('#sh-hours').textContent = `Длительность: ${Math.floor(mins / 60)} ч ${mins % 60 ? (mins % 60) + ' мин' : ''}${over ? ' · через полночь' : ''}`;
        if (over) $('#sh-overnight').checked = true;
      };
      $('#sh-start').onchange = recalc; $('#sh-end').onchange = recalc; recalc();
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        const kindSel = $('#sh-kind').value;
        const body = {
          code: $('#sh-code').value.trim().toUpperCase(), name: $('#sh-name').value.trim(),
          short_code: $('#sh-short').value.trim(),
          kind: kindSel === 'work' ? 'work' : 'absence',
          start_time: $('#sh-start').value, end_time: $('#sh-end').value,
          overnight: $('#sh-overnight').checked, color: $('#sh-color').value,
          sort_order: st?.sort_order ?? 100,
          is_working: kindSel === 'work',
          counts_as_worked: kindSel === 'work',
          punch_in_allowed: kindSel === 'work' ? true : $('#sh-punch-in').checked,
          punch_out_allowed: kindSel === 'work' ? true : $('#sh-punch-out').checked,
          is_default_off: st?.is_default_off ?? false,
          doc_type: $('#sh-doc').value,
          deduct_from_bank: $('#sh-deduct').checked,
          effective_from: isNew ? null : ($('#sh-eff')?.value || todayISO()),
        };
        if (!body.code || !body.name) return toast('Заполните код и название', 'warn');
        try {
          isNew ? await api('/api/shift-types', { method: 'POST', body })
                : await api(`/api/shift-types/${st.id}`, { method: 'PUT', body });
          closeModal();
          await loadDirectory();
          toast('Словарь смен обновлён', 'ok');
          loadSettings();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ══════════════════════════════════════════════════════════════════
   СТАРТ
   ══════════════════════════════════════════════════════════════════ */
$('#login-form').addEventListener('submit', async e => {
  e.preventDefault();
  $('#login-error').classList.add('hidden');
  try {
    const res = await api('/api/auth/login', { method: 'POST', allow401: true,
      body: { username: $('#login-username').value.trim(), password: $('#login-password').value } });
    state.user = res.user;
    await enterApp();
  } catch (err) {
    const box = $('#login-error');
    box.textContent = err.message || 'Не удалось войти';
    box.classList.remove('hidden');
  }
});

$('#logout-btn').onclick = async () => {
  try { await api('/api/auth/logout', { method: 'POST', silent: true }); } catch { /* не важно */ }
  state.user = null;
  showLogin();
};
$('#nav-toggle').onclick = () => $('#sidenav').classList.toggle('open');
$('#change-pass-btn').onclick = () => openModal({
  title: 'Смена пароля',
  subtitle: 'Потребуется старый пароль для подтверждения',
  body: `
    <label class="field"><span>Старый пароль</span><input type="password" id="cp-old" autocomplete="current-password"></label>
    <label class="field"><span>Новый пароль</span><input type="password" id="cp-new" autocomplete="new-password"></label>
    <label class="field"><span>Подтверждение нового пароля</span><input type="password" id="cp-new2" autocomplete="new-password"></label>`,
  footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
           <button class="btn btn-primary" data-save>Сменить пароль</button>`,
  onMount(m) {
    m.querySelector('[data-cancel]').onclick = closeModal;
    m.querySelector('[data-save]').onclick = async () => {
      const nw = $('#cp-new').value, nw2 = $('#cp-new2').value;
      if (!$('#cp-old').value) return toast('Введите старый пароль', 'warn');
      if (nw.length < 8) return toast('Новый пароль слишком короткий (минимум 8 символов)', 'warn');
      if (nw !== nw2) return toast('Новый пароль и подтверждение не совпадают', 'warn');
      try {
        await api('/api/auth/change-password', { method: 'POST',
          body: { old_password: $('#cp-old').value, new_password: nw } });
        closeModal();
        toast('Пароль изменён', 'ok');
      } catch (e) { toast(e.message, 'err'); }
    };
  },
});
$('#stop-impersonation').onclick = async () => {
  const r = await api('/api/auth/impersonate/stop', { method: 'POST' });
  state.user = r.user; renderUserChip(); navigate(state.user.role === 'employee' ? 'me' : 'schedule');
  toast('Вы вернулись в свой интерфейс', 'ok');
};


if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost'
    || location.hostname === '127.0.0.1')) {
  navigator.serviceWorker.register('/sw.js').then(reg => {
    reg.addEventListener('updatefound', () => {
      const nw = reg.installing;
      nw?.addEventListener('statechange', () => {
        if (nw.state === 'installed' && navigator.serviceWorker.controller) {
          toast('Доступна новая версия приложения — обновите страницу', 'ok');
        }
      });
    });
  }).catch(e => console.warn('SW:', e));
}

(async function boot() {
  api('/api/health', { silent: true, allow401: true })
    .then(h => syncServerClock(h?.server_time_local)).catch(() => {});
  try {
    const me = await api('/api/auth/me', { silent: true, allow401: true });
    if (me?.user) { state.user = me.user; await enterApp(); return; }
  } catch { /* не авторизован */ }
  showLogin();
})();
