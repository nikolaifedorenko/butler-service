/* ══════════════════════════════════════════════════════════════════════
   TimeTrack — веб-интерфейс (SPA без сборки), светлая тема
   Разделы: График · Кто на работе · Посещения · Табель · Сотрудники · Мои отметки · Настройки
   Ядро (утилиты, api, состояние, модалки) вынесено в core.js — подключается раньше этого файла.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

/* ───────────────────────────── вкладки ───────────────────────────── */
const ICONS = {
  grafik: '<svg viewBox="0 0 24 24"><path d="M12 3l8 4.4-8 4.4-8-4.4z" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/><path d="M4.6 12L12 16l7.4-4" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/><path d="M4.6 16.4L12 20.4l7.4-4" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/></svg>',
  schedule: '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="16" rx="2" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M3 10h18M8 3v4M16 3v4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  attendance: '<svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.4" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M5 20c1.2-3.6 3.9-5.4 7-5.4s5.8 1.8 7 5.4" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/></svg>',
  marks: '<svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.4" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M5 20c1.2-3.6 3.9-5.4 7-5.4s5.8 1.8 7 5.4" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/><circle cx="19" cy="6" r="2.4" fill="currentColor"/></svg>',
  fact: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M12 7v5l3.5 2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" fill="none"/><path d="M3.5 9.5h3M17.5 14.5h3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  onwork: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.8" fill="none"/><circle cx="12" cy="12" r="3.6" fill="currentColor"/><path d="M12 3v2.2M12 18.8V21M3 12h2.2M18.8 12H21" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  timesheet: '<svg viewBox="0 0 24 24"><path d="M5 3h14v18l-3-2-2 2-2-2-2 2-2-2-3 2z" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/><path d="M9 8h6M9 12h6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  employees: '<svg viewBox="0 0 24 24"><circle cx="9" cy="8" r="3.2" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M3 20c.9-3.3 3.2-5 6-5s5.1 1.7 6 5" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/><path d="M16 11h5M18.5 8.5v5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  me: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M12 7v5l3.5 2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" fill="none"/></svg>',
  night: '<svg viewBox="0 0 24 24"><path d="M20 13.5A8.5 8.5 0 0 1 10.5 4 8.5 8.5 0 1 0 20 13.5z" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/></svg>',
  cars: '<svg viewBox="0 0 24 24"><path d="M4 16v-3.2L6.2 8h11.6L20 12.8V16" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/><rect x="3" y="15" width="18" height="4.5" rx="1.6" stroke="currentColor" stroke-width="1.8" fill="none"/><circle cx="7.3" cy="17.2" r="1" fill="currentColor"/><circle cx="16.7" cy="17.2" r="1" fill="currentColor"/></svg>',
  mgmt: '<svg viewBox="0 0 24 24"><rect x="4" y="3" width="16" height="18" rx="2" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M8 8h8M8 12h8M8 16h5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M15.5 16.5l1.5 1.5 3-3" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  access: '<svg viewBox="0 0 24 24"><path d="M12 3l7 3v5c0 4.5-3 8.2-7 10-4-1.8-7-5.5-7-10V6z" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/><circle cx="12" cy="11" r="2.2" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M12 13.2V16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  audit: '<svg viewBox="0 0 24 24"><path d="M6 3h9l4 4v14H6z" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/><path d="M9 11h7M9 15h7M9 7h4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  settings: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M12 3v2.5M12 18.5V21M4.2 7.5l2.2 1.3M17.6 15.2l2.2 1.3M4.2 16.5l2.2-1.3M17.6 8.8l2.2-1.3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
};

/* Права приходят с сервера (/api/auth/me → permissions): роль + группы + индивидуальные. */
function can(perm) { return (state.perms || []).includes(perm); }

/* T5 (норматив 12.10.2026): «График» — ОДИН пункт меню с четырьмя слоями внутри
   (Q2): 0 Табель · 1 План/График · 2 Факт · 3 Управленческий Табель. Пункт виден,
   если есть право хотя бы на один слой; сами слои фильтруются по правам в
   grafikLayers(). Доска «Отметки» — отдельный пункт меню (Q7). */
const GRAFIK_LAYERS = [
  { view: 'timesheet', num: '0', title: 'Табель', sub: 'первоисточник · бухгалтерия', perm: 'tabel.view' },
  { view: 'schedule', num: '1', title: 'План / График', sub: 'операционный план · флаги', perm: 'schedule.view' },
  { view: 'fact', num: '2', title: 'Факт', sub: 'отметки · округление до шага', perm: 'presence.view' },
  { view: 'mgmt', num: '3', title: 'Управленческий Табель', sub: 'результат · банк · закрытие', perm: 'mgmt.view' },
];
/* старые имена разделов — алиасы слоёв: navigate('timesheet') и др. продолжают
   работать (переходы из модалок, сценарии, смоук harness) */
const GRAFIK_ALIAS = { timesheet: 'grafik', schedule: 'grafik', fact: 'grafik', mgmt: 'grafik' };

function visibleTabs() {
  const all = [
    { id: 'grafik', title: 'График', anyPerm: GRAFIK_LAYERS.map(l => l.perm) },
    { id: 'marks', title: 'Отметки', perm: 'presence.view' },
    { id: 'employees', title: 'Сотрудники', perm: 'employees.view' },
    { id: 'me', title: 'Мои отметки', perm: 'me.punch' },
    { id: 'night', title: 'Ночной отчёт', perm: 'night.view' },
    { id: 'cars', title: 'Электрокары', perm: 'cars.view' },
    { id: 'access', title: 'Права доступа', perm: 'access.manage' },
    { id: 'audit', title: 'Журнал аудита', perm: 'audit.view' },
    { id: 'settings', title: 'Настройки', perm: 'settings.view' },
  ];
  return all.filter(t => t.anyPerm ? t.anyPerm.some(can) : can(t.perm));
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
  foot.innerHTML = `Учёт кратен шагу (по умолчанию 1 ч)<br>ДН 22:00–06:00 · ДЯ 06:00–22:00<br>Часы — по календарным дням`;
}

function navigate(view) {
  if (GRAFIK_ALIAS[view]) { state.grafikLayer = view; view = GRAFIK_ALIAS[view]; }
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
    grafik: () => loadGrafik(), marks: () => loadMarks(),
    access: () => loadAccess(), audit: () => loadAudit(),
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

/* ───────────── «График» = 4 слоя: обёртка и панель слоёв (T5) ───────────── */
function grafikLayers() { return GRAFIK_LAYERS.filter(l => can(l.perm)); }

const LAYER_LOADERS = {
  timesheet: () => loadTabel(), schedule: () => loadSchedule(),
  fact: () => loadFact(), mgmt: () => loadMgmt(),
};

/* Каркас обёртки живёт в index.html; восстанавливаем его, если предыдущая
   загрузка раздела упала и заглушка ошибки перезаписала #view-grafik целиком. */
function grafikSkeleton() {
  $('#view-grafik').innerHTML = `
    <div class="layer-tabs" id="grafik-tabs"></div>
    <section id="view-timesheet" class="layer-pane"></section>
    <section id="view-schedule" class="layer-pane"></section>
    <section id="view-fact" class="layer-pane"></section>
    <section id="view-mgmt" class="layer-pane"></section>`;
}

async function loadGrafik() {
  if (!document.getElementById('grafik-tabs')) grafikSkeleton();
  const layers = grafikLayers();
  if (!layers.some(l => l.view === state.grafikLayer)) {
    /* слой по умолчанию — План/График (как раньше открывался раздел «График»);
       без права на него — первый доступный слой цепочки */
    state.grafikLayer = (layers.find(l => l.view === 'schedule') || layers[0] || {}).view || null;
  }
  renderGrafikTabs();
  $$('#view-grafik .layer-pane').forEach(p =>
    p.classList.toggle('on', !!state.grafikLayer && p.id === `view-${state.grafikLayer}`));
  if (!state.grafikLayer) {
    const wrap = $('#view-grafik');
    if (!wrap.querySelector('.layer-noperm')) {
      wrap.insertAdjacentHTML('beforeend',
        '<div class="panel layer-noperm"><div class="empty">Нет прав ни на один слой «Графика»</div></div>');
    }
    return;
  }
  await LAYER_LOADERS[state.grafikLayer]();
}

function renderGrafikTabs() {
  const host = $('#grafik-tabs');
  if (!host) return;
  host.innerHTML = grafikLayers().map(l => `
    <button class="layer-tab${l.view === state.grafikLayer ? ' active' : ''}" data-layer="${l.view}"
      title="Слой ${l.num} · ${esc(l.title)}: ${esc(l.sub)}">
      <span class="lnum">${l.num}</span>
      <span class="ltt">${esc(l.title)}<small>${esc(l.sub)}</small></span>
    </button>`).join('');
  $$('#grafik-tabs .layer-tab').forEach(b => b.onclick = () => navigate(b.dataset.layer));
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

async function loadPerms() {
  try {
    const me = await api('/api/auth/me', { silent: true });
    state.perms = me.permissions || [];
  } catch { state.perms = []; }
}

function startView() {
  const tabs = visibleTabs().map(t => t.id);
  return ['grafik', 'marks', 'me'].find(v => tabs.includes(v)) || tabs[0] || 'me';
}

async function enterApp() {
  $('#login-screen').classList.add('hidden');
  $('#app').classList.remove('hidden');
  await loadPerms();
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
  navigate(startView());
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
  /* Коды Табеля нужны редактору смены: «код в табеле» — выбор из справочника,
     а не свободный текст (T1). Недоступен — редактор покажет текущее значение. */
  try {
    const tc = await api('/api/shift-types/tabel-codes', { silent: true });
    state.tabelCodes = tc.codes || [];
  } catch { state.tabelCodes = state.tabelCodes || []; }
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
  const ro = !can('schedule.edit');   // без права «Редактирование графика» — только просмотр
  return `
  <div class="page-head">
    <div>
      <h2>Слой 1 · План / График</h2>
      <div class="sub">${ro
        ? 'План смен на месяц — так же, как его видит менеджер. Правки вносит менеджер'
        : 'График генерируется из Табеля по окнам CFG-WINDOWS; ручная смена заменяет генерацию дня. «Пропуск/отлучка» — согласованное отсутствие: смена показывается разрезанной, на часы не влияет'}</div>
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
    <div class="spacer" style="flex:1"></div>
    ${ro ? '' : `<button class="btn btn-sm" id="btn-range" title="Слой 1 · График: только «за счёт часов» — в Табеле остаётся явка, часы не меняются">Отпросить (выходной за часы)</button>
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
  $('#btn-print').onclick = printGrid;
  $('#btn-pdf').onclick = () => downloadBlob(`/api/schedule/pdf?year=${state.year}&month=${state.month}`, 'grafik.pdf');
  if ($('#btn-xlsx')) $('#btn-xlsx').onclick = () => downloadBlob(`/api/schedule/xlsx?year=${state.year}&month=${state.month}`, 'grafik.xlsx');
  if ($('#btn-range')) $('#btn-range').onclick = () => openRangeModal('schedule');
  if ($('#btn-clear')) $('#btn-clear').onclick = () => confirmDialog(
    'Обнулить месяц?',
    `Строки Табеля и сгенерированный График за ${MONTHS[state.month - 1]} ${state.year} будут удалены
     (месяц вернётся к пустому Табелю; заполните его из циклов во вкладке «Табель»).
     Закрытые периоды не трогаются.`,
    async () => {
      const r = await api('/api/schedule/clear-month', { method: 'POST', body: { year: state.year, month: state.month } });
      toast(`Очищено строк Табеля: ${r.cleared}`, 'ok');
      loadSchedule();
    });

  $('#f-text').value = state.filterText;
  $('#f-text').oninput = e => { state.filterText = e.target.value; renderGrid(); };
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

  const usedCodes = {};
  rows.forEach(r => Object.values(r.cells || {}).forEach(c => {
    if (c.tabel && c.tabel.code) usedCodes[c.tabel.code] = c.tabel.value || c.tabel.code;
  }));
  $('#grid-legend').innerHTML = Object.keys(usedCodes).map(code =>
    `<span class="chip"><span class="swatch" style="background:${V4_CODE_COLORS[code] || '#8a94a6'}"></span>
      <b>${esc(code)}</b>${usedCodes[code] !== code ? ' ' + esc(usedCodes[code]) : ''}</span>`).join('') +
    `<span class="chip" title="Согласованное отсутствие (логический разрез смены): на часы не влияет, видно во флагах и на доске">
      <span class="swatch" style="background:#0e9aa7"></span><b>✂</b> пропуск/отлучка</span>
     <span class="chip" title="Ручная смена заменяет сгенерированную из Табеля">
      <span class="swatch" style="background:#5b6bd6"></span><b>Р</b> ручная смена</span>
     <span class="chip" title="Производственный календарь / ВИП-гости: переработки в эти дни оплачиваются вдвое (коды ДЯ2/ДН2)">
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

function cellTd(r, d, c, cls) {
  const btn = (extra, inner, title, style) =>
    `<td class="${cls}"><button class="cellbtn ${extra}" data-emp="${r.employee.id}" data-date="${d.date}" title="${esc(title)}"${style ? ` style="${style}"` : ''}>${inner}</button></td>`;
  const t = c.tabel;
  const shifts = c.shifts || [];
  const absences = c.absences || [];
  const code = t ? t.code : '';
  const color = V4_CODE_COLORS[code] || '#8a94a6';
  const parts = [];
  if (t) parts.push(t.value || t.code);
  if (shifts.length) parts.push(shifts.map(x => `${x.start_hm}–${x.end_hm}`).join(' '));
  const manual = shifts.some(x => x.source === 'manual');
  const title = `${r.employee.short_name}, ${dateRu(d.date)}: ` +
    (t ? `Табель «${t.value || t.code}»${t.source === 'cycle' ? ' (из циклов)' : ' (вручную)'}` : 'Табель не заполнен') +
    (shifts.length ? ` · смена ${shifts.map(x => `${x.start_hm}–${x.end_hm}${x.source === 'manual' ? ' (ручная)' : ''}`).join(', ')}` : ' · смены нет') +
    (absences.length ? ` · согласованное отсутствие ${absences.map(a => `${a.start_hm}–${a.end_hm}${a.kind ? ' (' + a.kind.name + ')' : ''}`).join(', ')} — на часы не влияет` : '') +
    (t && t.note ? ` · ${t.note}` : '');
  const marks = [manual ? '<span class="manual-mark" title="Ручная смена">Р</span>' : '',
    absences.length ? '<span class="partial-mark" title="Согласованное отсутствие: смена показана разрезанной">✂</span>' : ''].join('');
  const inner = `${marks}<span class="t t-full">${esc(parts.join(' ') || '—')}</span><span class="t t-short">${esc(t ? (t.value || t.code).replace(' ', '') : '—')}</span>`;
  const style = code ? `background:linear-gradient(165deg, ${withAlpha(color, .30)}, ${withAlpha(color, .16)});color:#2c3440` : '';
  return btn(code ? '' : 'empty', inner, title, style);
}

function empRow(r, g, block) {
  const accent = r.employee.group_color || '#8a94a6';
  const ranges = block?.ranges || (block ? [{ start: block.start, end: block.end }] : []);
  const inBlock = iso => !ranges.length || ranges.some(rg =>
    iso >= rg.start && (!rg.end || iso <= rg.end));
  const cells = g.days.map(d => {
    const c = r.cells[d.date] || {};
    const cls = ['cell', d.is_weekend ? 'weekend' : '', d.is_today ? 'today' : ''].join(' ');
    const outOfBlock = ranges.length && !inBlock(d.date);
    if (outOfBlock) {
      return `<td class="${cls}"><button class="cellbtn" disabled
        title="Неактивно: в этот день сотрудник относится к другому блоку"
        style="background:${g.colors.out_of_block};color:#5d5670;cursor:default">—</button></td>`;
    }
    if (c.employed === false) {
      return `<td class="${cls}"><button class="cellbtn inactive" disabled
        title="Не в штате: сотрудник не работал в эту дату (до приёма или после увольнения)">—</button></td>`;
    }
    return cellTd(r, d, c, cls);
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
        const t = c.tabel;
        const shifts = c.shifts || [];
        let txt = t ? (t.value || t.code) : '';
        if (shifts.length) txt += (txt ? '\n' : '') + shifts.map(x => `${x.start_hm}–${x.end_hm}`).join(' ');
        if ((c.absences || []).length) txt += '*';
        const color = t ? (V4_CODE_COLORS[t.code] || '#8a94a6') : null;
        return `<td${color ? ` style="background:${withAlpha(color, .22)}"` : ' class="muted"'}>${esc(txt)}</td>`;
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
     <p style="font-size:12px;color:#667">Значение Табеля и интервалы смен; * — согласованное отсутствие (логический разрез смены).</p>
     <table><thead>${head}</thead><tbody>${body}</tbody></table>`);
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

/* Заявление печатается из своего слоя (Q4, норматив 12.10.2026): отпуск, больничный,
   за свой счёт и оплачиваемый выходной — коды Табеля (первичный документ, слой 0),
   а «отпросился (выходной за часы)» — данные Графика (слой 1). Сервер сообщает источник
   в `source`; кнопка не того слоя объясняет, куда идти, а не печатает чужой документ. */
function statementLayerOk(p, layer) {
  if (!layer || !p.source || p.source === layer) return true;
  toast(p.source === 'tabel_code'
    ? 'Это отсутствие — код Табеля (отпуск, больничный, отгул): заявление печатается из раздела «Табель», из ячейки дня'
    : '«Отпросился (выходной за часы)» — данные Графика: заявление печатается из ячейки дня в разделе «График»',
    'warn');
  return false;
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
async function downloadAbsenceDoc(empId, dateISO, fmt, layer = '') {
  let p;
  try { p = await absencePeriodInfo(empId, dateISO); }
  catch (e) {
    return toast(e.message.includes('нет назначенного')
      ? 'Сначала сохраните отсутствие в ячейке — тогда станет доступна печать заявления'
      : e.message, 'err');
  }
  if (!statementLayerOk(p, layer)) return;
  /* Вид заявления определяет сервер: у единого «отпросился (выходной за часы)» он
     зависит от точки ввода — вся смена или интервал (Q3). */
  const type = p.doc_type || p.shift?.doc_type;
  if (!type) return toast('К этому виду отсутствия не привязан шаблон заявления (Настройки → Словарь смен)', 'warn');
  loading(true);
  try {
    const res = await fetch('/api/docs/render', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type, employee_id: empId, date_from: p.start, date_to: p.end, format: fmt,
        from_time: p.partial?.from_time || '', until_time: p.partial?.until_time || '',
        hours: p.hours != null ? p.hours : null,
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
async function printAbsenceRequest(empId, dateISO, layer = '') {
  let p;
  try { p = await absencePeriodInfo(empId, dateISO); }
  catch (e) {
    return toast(e.message.includes('нет назначенного')
      ? 'Сначала сохраните отсутствие в ячейке — тогда станет доступна печать заявления'
      : e.message, 'err');
  }
  if (!statementLayerOk(p, layer)) return;
  try {
    const docType = p.doc_type || p.shift?.doc_type;
    const doc = await getDocTemplates();
    const kind = (state.docKinds || []).find(k => k.code === docType);
    const tplKey = { vacation_paid: 'vacation', vacation_unpaid: 'vacation_unpaid',
                     day_off_hours: 'day_off_hours', time_off_request: 'time_off_request' }[docType]
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
      /* Часы отсутствия: сервер считает их по стандартному окну смен сотрудника
         (для «выходного за часы» — не длина записи, а норма его смены). */
      hours: p.hours != null ? hours(p.hours) : '',
      period: p.end === p.start ? dateRu(p.start) : `с ${dateRu(p.start)} по ${dateRu(p.end)}`,
      reason: p.partial?.reason?.name || p.shift?.name || '',
      note: (p.notes || []).join('; '),
      today: dateRu(todayISO()),
    };
    printWindow('Заявление',
      `<div style="white-space:pre-wrap;font-size:13px;line-height:1.7;width:170mm;margin:0 auto">${esc(fillTemplate(tplText, vals))}</div>`);
  } catch (e) { toast(e.message, 'err'); }
}

/* ── назначение отсутствия на период: два входа по слоям (Q4, норматив 12.10.2026) ──
   mode='schedule' — из «Графика»: только «за счёт часов» (отпросился / выходной за часы),
   Табель остаётся явкой, недостачу гасит банк (EX-29);
   mode='tabel' — из «Табеля»: виды с кодом Табеля (ОТ, ДО, Б, ОВ, НН…) — отсутствие
   это код первичного документа, там же печатаются заявления. */
function openRangeModal(mode = 'tabel') {
  const fromSchedule = mode === 'schedule';
  const first = `${state.year}-${String(state.month).padStart(2, '0')}-01`;
  const rows = (state.grid?.rows || state.tabel?.rows || []);
  const people = rows.length ? rows.map(r => r.employee)
    : (state.employees || []).map(e => ({ id: e.id, full_name: e.full_name, position: e.position }));
  const kinds = state.shiftTypes.filter(x => x.kind === 'absence' && !x.is_default_off
    && (fromSchedule ? !x.tzh_code : !!x.tzh_code));
  openModal({
    title: fromSchedule ? 'Отпросить (выходной за часы)' : 'Назначить отсутствие (код Табеля)',
    subtitle: fromSchedule
      ? 'Слой 1 · График: в Табеле остаётся явка, часы и план не меняются'
      : 'Слой 0 · Табель: отпуск, больничный, за свой счёт, оплачиваемый выходной — на период сразу',
    wide: true,
    body: `
      <div class="opt-group-title">Сотрудники</div>
      <div class="check-list" id="rg-emps">
        ${people.map(r => `<label><input type="checkbox" value="${r.id}">
          ${esc(r.full_name)} <small style="color:var(--muted)">· ${esc(r.position || '')}</small></label>`).join('')}
      </div>
      <div class="grid-2" style="margin-top:14px">
        <label class="field"><span>С</span><input type="date" id="rg-from" value="${first}"></label>
        <label class="field"><span>По (включительно)</span><input type="date" id="rg-to" value="${first}"></label>
      </div>
      <label class="field"><span>${fromSchedule ? 'Вид (из Графика — только «за счёт часов»)' : 'Вид отсутствия (код Табеля)'}</span><select id="rg-shift">
        ${kinds.map((x, i) => `<option value="${x.id}" ${!fromSchedule && (x.code === 'VACATION' || i === 0) ? 'selected' : ''}>${esc(x.name)} · код Табеля ${x.tzh_code ? `«${esc(x.tzh_code)}»` : 'не задан'}</option>`).join('')
          || '<option value="">— нет подходящих видов в словаре смен —</option>'}
      </select>
        <div class="hint" id="rg-mode-hint" style="margin-top:4px"></div></label>
      <label class="field"><span>Примечание</span>
        <input type="text" id="rg-note" placeholder="${fromSchedule ? 'Например: заявление согласовано 12.10' : 'Например: приказ №47 от 01.09.2026'}"></label>
      <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
        <input type="checkbox" id="rg-work-only" style="width:17px;height:17px;accent-color:var(--primary)">
        Только на рабочие дни по Табелю${fromSchedule ? ' (на плановые выходные «выходной за часы» не ставится)' : ''}
      </label>
      <p class="hint">${fromSchedule
        ? 'Отсутствие пишется в График на всё стандартное окно дня: сотрудник не ожидается, флагов нет, а неотработанные часы окна уходят в недостачу — её гасит банк часов при закрытии периода (Q8: назначение информационное, расчёт не меняется). Заявление печатается из ячейки дня в «Графике».'
        : 'В эти дни в Табель будет записан код отсутствия: смены в эти дни нет, сотрудник не ожидается, флагов нет. Часы и банк не меняются. Заявление печатается из ячейки дня в «Табеле» или из «Документов».'}
        Период может выходить за границы открытого месяца; дни до приёма и после увольнения
        пропускаются автоматически. Закрытые периоды не трогаются.</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Назначить</button>`,
    onMount(m) {
      const hint = $('#rg-mode-hint');
      if (hint) hint.textContent = fromSchedule
        ? 'Единая сущность «отпросился (выходной за часы)»: на весь день — из Графика, интервалом — в ячейке дня.'
        : 'Вид с кодом Табеля: отсутствие оформляется кодом первичного документа.';
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        const ids = $$('#rg-emps input:checked').map(i => +i.value);
        if (!ids.length) return toast('Отметьте сотрудников', 'warn');
        const kindId = +$('#rg-shift').value;
        if (!kindId) return toast('Выберите вид отсутствия', 'warn');
        const from = $('#rg-from').value, to = $('#rg-to').value;
        if (!from || !to || from > to) return toast('Проверьте даты периода', 'warn');
        try {
          const res = await api('/api/schedule/range-absence', { method: 'POST', body: {
            employee_ids: ids, first: from, last: to,
            shift_type_id: kindId, note: $('#rg-note').value.trim(),
            workdays_only: $('#rg-work-only').checked,
          } });
          closeModal();
          const what = res.mode === 'schedule_absence' ? 'дней в Графике' : 'ячеек Табеля';
          toast(`Отсутствие назначено: ${res.written} ${plural(res.written, 'ячейка', 'ячейки', 'ячеек')} (${what})`
            + (res.skipped ? `, пропущено ${res.skipped}` : ''), (res.errors || []).length ? 'warn' : 'ok',
            (res.errors || []).map(e => `${e.date}: ${e.error}`).slice(0, 6));
          const d0 = new Date(from + 'T12:00:00');
          if (d0.getFullYear() !== state.year || d0.getMonth() + 1 !== state.month) {
            state.year = d0.getFullYear();
            state.month = d0.getMonth() + 1;
          }
          if (fromSchedule) loadSchedule(); else loadTabel();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ── редактор ячейки Графика (16.3): ручная смена, согласованное отсутствие,
      переход в Табель за кодом дня ── */
function openCellModal(empId, dateISO) {
  const row = state.grid.rows.find(r => r.employee.id === empId);
  const cell = row?.cells?.[dateISO] || {};
  const d = new Date(dateISO + 'T00:00:00');
  const title = `${WD[d.getDay()]}, ${d.getDate()} ${MONTHS_GEN[d.getMonth()]} ${d.getFullYear()}`;
  const workShifts = state.shiftTypes.filter(x => x.kind === 'work' && !x.archived_at);
  /* Из Графика назначается ТОЛЬКО «за счёт часов» (Q4): виды без кода Табеля. Отпуск,
     больничный, за свой счёт и оплачиваемый выходной — коды первичного документа, они
     ставятся в Табеле (слой 0), там же печатаются заявления. */
  const absenceKinds = state.shiftTypes.filter(x => x.kind === 'absence' && !x.is_default_off
    && !x.tzh_code && !x.archived);
  const t = cell.tabel;
  const shifts = cell.shifts || [];
  const absences = cell.absences || [];
  const editable = cell.editable !== false;

  openModal({
    title: row?.employee.full_name || 'Сотрудник',
    subtitle: `${title} · ${row?.employee.position || ''}`,
    body: `
      <div class="status-line"><span class="k">Табель (первичный документ)</span>
        <span class="v">${t ? esc(t.value || t.code) + (t.source === 'cycle' ? ' · из циклов' : ' · вручную') : 'не заполнен'}</span></div>
      <div style="display:flex;gap:8px;margin:8px 0 4px">
        <button class="btn btn-sm" id="cell-tabel">Изменить код Табеля…</button>
      </div>
      <div class="opt-group-title">Смены дня (График генерируется из Табеля по окнам)</div>
      ${shifts.length ? shifts.map(x => `<div class="status-line">
          <span class="k">${esc(x.start_hm)}–${esc(x.end_hm)} ${x.source === 'manual' ? '· ручная' : '· из Табеля'}${x.note ? ' · ' + esc(x.note) : ''}</span>
          <span class="v"></span></div>`).join('')
        : '<p class="hint" style="margin:4px 0">Смен нет: значение Табеля без часов (выходной/отсутствие) либо Табель не заполнен.</p>'}
      ${editable ? `
      <div id="manual-block" style="margin-top:10px;border:1px solid var(--line);border-radius:12px;padding:12px 14px 8px;background:#f8fbfd">
        <div class="opt-group-title" style="margin-top:0">Ручная смена (заменяет генерацию дня целиком)</div>
        <label class="field"><span>Пресет из словаря</span><select id="cell-preset">
          <option value="">— задать время вручную —</option>
          ${workShifts.map(x => `<option value="${x.start_time}|${x.end_time}|${x.overnight ? 1 : 0}">${esc(x.name)}</option>`).join('')}
        </select></label>
        <div class="grid-2">
          <label class="field"><span>Начало</span><input type="time" id="cell-sh-from" value="09:00"></label>
          <label class="field"><span>Конец</span><input type="time" id="cell-sh-until" value="18:00"></label>
        </div>
        <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
          <input type="checkbox" id="cell-sh-next" style="width:17px;height:17px;accent-color:var(--primary)">
          Заканчивается на следующие сутки (смена через полночь)
        </label>
        <div style="display:flex;gap:8px;margin:8px 0 6px;flex-wrap:wrap">
          <button class="btn btn-sm btn-primary" id="cell-sh-save">Сохранить ручную смену</button>
          ${shifts.some(x => x.source === 'manual') ? '<button class="btn btn-sm btn-danger" id="cell-sh-drop">Вернуть к генерации из Табеля</button>' : ''}
        </div>
        <p class="hint" style="margin:2px 0 6px">День редактируем, если его код Табеля принимает коды УТ
          (accepts_ut = Да). Ручная смена может пересекать полночь; на часы влияет только Табель —
          правка Графика меняет флаги и доску, но не расчёт (RUL-SCHEDULE-ONLY-FLAGS).</p>
      </div>` : '<p class="hint">Ручную смену в этот день поставить нельзя: код Табеля не принимает коды УТ (день-якорь).</p>'}
      <div class="opt-group-title" style="margin-top:12px">Отпросился (выходной за часы) — согласованные отсутствия дня</div>
      ${absences.map(a => `<div class="status-line">
          <span class="k">✂ ${esc(a.start_hm)}–${esc(a.end_hm)}${a.kind ? ' · ' + esc(a.kind.name) : ''}${a.note ? ' · ' + esc(a.note) : ''}</span>
          <span class="v"><button class="btn btn-sm btn-ghost" data-abs-del="${a.id}">Удалить</button></span></div>`).join('') || ''}
      <div style="margin-top:8px;border:1px solid var(--line);border-radius:12px;padding:12px 14px 8px;background:#f8fbfd">
        <div class="opt-group-title" style="margin-top:0">Одна сущность — две точки ввода: интервал или вся смена</div>
        <label class="field"><span>Вид отсутствия</span><select id="cell-abs-kind">
          <option value="">— без вида —</option>
          ${absenceKinds.map(x => `<option value="${x.id}" data-code="${esc(x.code)}">${esc(x.name)}</option>`).join('')}
        </select>
          <div class="hint" style="margin-top:2px">Из Графика — только «за счёт часов». Отпуск, больничный,
            за свой счёт и оплачиваемый выходной ставятся кодом Табеля («Изменить код Табеля…» выше).</div></label>
        <div class="grid-2">
          <label class="field"><span>Отсутствовал с</span><input type="time" id="cell-abs-from" value="14:00"></label>
          <label class="field"><span>Отсутствовал до</span><input type="time" id="cell-abs-until" value="16:00"></label>
        </div>
        <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
          <input type="checkbox" id="cell-abs-next" style="width:17px;height:17px;accent-color:var(--primary)">
          До следующего дня (через полночь)
        </label>
        <label class="field"><span>Примечание</span><input type="text" id="cell-abs-note" placeholder="Например: заявление согласовано"></label>
        <div style="display:flex;gap:8px;margin:4px 0 6px;flex-wrap:wrap">
          <button class="btn btn-sm" id="cell-abs-save" title="Отпросился на часть смены: интервал внутри окна">Отпросить на интервал</button>
          <button class="btn btn-sm" id="cell-abs-shift" title="Отсутствие на всё окно смены: «выходной за часы»">На всю смену</button>
          <span class="hint" id="cell-abs-hours" style="margin:0;align-self:center"></span>
        </div>
        <p class="hint" style="margin:2px 0 6px">Назначение <b>информационное</b> — «чтобы мы не ждали сотрудника» (Q8):
          отсутствие НЕ меняет план, часы и банк, оно режет смену для флагов (опоздание/ранний уход
          в ожидаемое время) и для доски «Отметки». Неотработанные часы стандартного окна уходят
          в недостачу дня, а при закрытии периода недостачу гасит банк 1:1 — то есть ранее
          накопленные переработки (EX-29). В Табеле остаётся явка.</p>
      </div>
      <div id="doc-btns" style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <button class="btn btn-sm" id="doc-print">Печать заявления</button>
        <button class="btn btn-sm" id="doc-docx">Заявление DOCX (шаблон компании)</button>
        <button class="btn btn-sm" id="doc-pdf">Заявление PDF (готов к печати)</button>
        <span class="hint" style="margin:0">Из Графика печатается «отпросился (выходной за часы)»:
          на всю смену — заявление на выходной за ранее отработанные часы, интервалом —
          об отсутствии на рабочем месте. Отпуск/ДО/ОВ — из Табеля.</span>
      </div>`,
    footer: `<div style="flex:1"></div>
      <button class="btn btn-ghost" data-cancel>Закрыть</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      $('#cell-tabel').onclick = () => {
        closeModal();
        state.pendingTabelCell = { emp: empId, date: dateISO };
        navigate('timesheet');
      };
      const preset = m.querySelector('#cell-preset');
      if (preset) preset.onchange = () => {
        if (!preset.value) return;
        const [a, b, next] = preset.value.split('|');
        $('#cell-sh-from').value = a; $('#cell-sh-until').value = b; $('#cell-sh-next').checked = next === '1';
      };
      const shSave = m.querySelector('#cell-sh-save');
      if (shSave) shSave.onclick = async () => {
        try {
          await api('/api/schedule/shift', { method: 'PUT', body: {
            employee_id: empId, date: dateISO,
            shifts: [{ start: $('#cell-sh-from').value, end: $('#cell-sh-until').value,
                       end_next_day: $('#cell-sh-next').checked }],
          } });
          closeModal(); toast('Ручная смена сохранена', 'ok'); loadSchedule();
        } catch (e) { toast(e.message, 'err'); }
      };
      const shDrop = m.querySelector('#cell-sh-drop');
      if (shDrop) shDrop.onclick = async () => {
        try {
          await api(`/api/schedule/shift?employee_id=${empId}&date=${dateISO}`, { method: 'DELETE' });
          closeModal(); toast('День возвращён к генерации из Табеля', 'ok'); loadSchedule();
        } catch (e) { toast(e.message, 'err'); }
      };
      const addAbsence = async (from, until, nextDay) => {
        try {
          await api('/api/schedule/absence', { method: 'POST', body: {
            employee_id: empId, date: dateISO,
            from_time: from, until_time: until,
            next_day: nextDay,
            kind_id: +$('#cell-abs-kind').value || null,
            note: $('#cell-abs-note').value.trim(),
          } });
          closeModal(); toast('Согласованное отсутствие добавлено', 'ok'); loadSchedule();
        } catch (e) { toast(e.message, 'err'); }
      };
      $('#cell-abs-save').onclick = () => addAbsence($('#cell-abs-from').value,
        $('#cell-abs-until').value, $('#cell-abs-next').checked);
      /* «На всю смену» — границы берутся из смены дня (График), а не вводятся руками:
         это типичный «выходной за часы» (EX-29). */
      $('#cell-abs-shift').onclick = () => {
        const sh = shifts[0];
        if (!sh) return toast('В этот день нет смены — задайте время вручную', 'warn');
        const untilNext = sh.end_hm <= sh.start_hm;
        $('#cell-abs-from').value = sh.start_hm;
        $('#cell-abs-until').value = sh.end_hm;
        $('#cell-abs-next').checked = untilNext;
        addAbsence(sh.start_hm, sh.end_hm, untilNext);
      };
      /* Часы «выходного за часы» — стандартное окно смен сотрудника (сервер выводит). */
      const showTimeoffHours = async () => {
        const hint = $('#cell-abs-hours');
        if (!hint) return;
        try {
          const r = await api(`/api/schedule/timeoff-hours?employee_id=${empId}&date=${dateISO}`,
                              { silent: true });
          const src = { window_of_day: 'окно его смены', timesheet_mode: 'обычная смена за 90 дней',
                        default: 'настройка объекта' }[r.hours_source] || r.hours_source;
          hint.textContent = `«Выходной за часы»: ${hours(r.hours)} ч (${src})`;
          hint.title = 'Сколько часов попадёт в заявление; в Табеле остаётся явка, день гасится банком';
        } catch { hint.textContent = ''; }
      };
      /* Обе точки ввода принадлежат одной сущности (Q3), поэтому доступны для любого
         вида «за счёт часов»; «без вида» — отсутствие без заявления. */
      const absKind = $('#cell-abs-kind');
      const syncAbsKind = () => {
        const sel = absKind.selectedOptions[0];
        $('#cell-abs-shift').style.display = sel ? '' : 'none';
        if (sel) showTimeoffHours(); else $('#cell-abs-hours').textContent = '';
      };
      absKind.onchange = syncAbsKind;
      if (absenceKinds.length) absKind.value = String(absenceKinds[0].id);
      syncAbsKind();
      $$('[data-abs-del]', m).forEach(b => b.onclick = async () => {
        try {
          await api(`/api/schedule/absence/${b.dataset.absDel}`, { method: 'DELETE' });
          closeModal(); toast('Отсутствие удалено — отображение смены восстановлено', 'ok'); loadSchedule();
        } catch (e) { toast(e.message, 'err'); }
      });
      $('#doc-print').onclick = () => printAbsenceRequest(empId, dateISO, 'schedule_absence');
      $('#doc-docx').onclick = () => downloadAbsenceDoc(empId, dateISO, 'docx', 'schedule_absence');
      $('#doc-pdf').onclick = () => downloadAbsenceDoc(empId, dateISO, 'pdf', 'schedule_absence');
    },
  });
}

/* Разделы «Отметки» (доска), «Факт» (история сессий), «Табель», «Управленческий табель»,
   «Права доступа» и «Журнал аудита» — в section_v4.js (движок v7.1). */

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
  const nowD = new Date(s.now);
  const inOk = s.punch_in_allowed !== false;
  const outOk = s.punch_out_allowed !== false;
  const hint = s.punch_status_hint || 'согласованное отсутствие';

  let mainBtn;
  if (s.on_shift && outOk) {
    mainBtn = `<button class="punch-btn out" id="punch-btn">Ушёл с работы
      <small>нажать в ${s.planned_end ? hhmm(s.planned_end) : '—'} · сейчас ${nowD.toTimeString().slice(0, 5)}</small></button>`;
  } else if (s.on_shift) {
    mainBtn = `<button class="punch-btn idle" id="punch-btn" disabled>Ушёл с работы
      <small>${esc(hint)} — отмечать уход запрещено</small></button>`;
  } else if (!inOk) {
    mainBtn = `<button class="punch-btn idle" id="punch-btn" disabled>Пришёл на работу
      <small>${esc(hint)} — отмечать приход запрещено</small></button>`;
  } else if (shift) {
    mainBtn = `<button class="punch-btn in" id="punch-btn">Пришёл на работу
      <small>смена ${esc(shift.start_hm)}–${esc(shift.end_hm)} · сейчас ${nowD.toTimeString().slice(0, 5)}</small></button>`;
  } else {
    mainBtn = `<button class="punch-btn in" id="punch-btn">Пришёл на работу
      <small>по Графику смены нет — часы будут учтены как переработка (коды ДЯ/ДН)</small></button>`;
  }

  $('#view-me').innerHTML = `
  <div class="me-wrap">
    <div class="me-date">${WD[d.getDay()]}, ${d.getDate()} ${MONTHS_GEN[d.getMonth()]} ${d.getFullYear()} · ${nowD.toTimeString().slice(0, 5)}</div>

    <div class="me-shift" style="--accent:#34a862">
      <div class="code">${shift ? (shift.source === 'manual' ? 'ручная смена' : 'смена из Табеля') : 'График'}</div>
      <div class="title">${shift ? `${esc(shift.start_hm)}–${esc(shift.end_hm)}` : 'смены нет'}</div>
      <div class="sub">${(s.expected || []).length
        ? 'ожидается: ' + s.expected.map(x => `${esc(x[0])}–${esc(x[1])}`).join(', ')
        : (shift ? 'ожидается вся смена' : 'сегодня не ожидались')}</div>
    </div>

    <div class="punch-zone">${mainBtn}</div>

    ${s.on_shift ? `
    <div class="status-line"><span class="k"><span class="pulse"></span>Вы на смене с ${hhmm(s.session_start)}</span>
      <span class="v">${s.elapsed_hours != null ? hours(s.elapsed_hours) + ' ч' : '—'}</span></div>` : ''}

    <div class="me-stats">
      <div class="me-stat"><div class="k">Часы сегодня (по отметкам)</div><div class="v">${hours(s.today_hours || 0)} ч</div></div>
      <div class="me-stat"><div class="k">Банк часов</div>
        <div class="v ${s.balance_hours >= 0 ? 'balance-pos' : 'balance-neg'}">${s.balance_hours >= 0 ? '+' : ''}${hours(s.balance_hours)}</div></div>
    </div>
    <p class="hint" style="margin-top:-4px">${esc(s.balance_note || '')}. Точные рабочее время,
      переработки и недостача — во вкладке «Управленческий табель» у менеджера.</p>

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
    toast(res.message, 'ok', res.warnings || []);
    state.status = res.status;
    const me = await api('/api/auth/me', { silent: true });
    punchInFlight = false;
    renderMe(res.status, me);
    if (res.punch?.kind === 'OUT') {
      openOtNoteModal(res.punch.id, '', 0);
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
          ${e.telegram ? `<small>tg: ${esc(e.telegram)}</small>` : ''}</td>
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
  const canBank = can('employees.edit');   // право, а не роль: гранты и группы учитываются
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
        state.user = me.user; state.perms = me.permissions || []; renderUserChip(); closeModal(); navigate('me');
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
  // Роли, которые текущий пользователь вправе назначать (защита от эскалации прав):
  // admin — все; manager — без admin; supervisor и ниже — только employee.
  const roleOptions = state.user?.role === 'admin' ? ['employee', 'supervisor', 'manager', 'admin']
    : state.user?.role === 'manager' ? ['employee', 'supervisor', 'manager']
    : ['employee'];
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
          ${roleOptions.map(r => `<option value="${r}" ${emp?.role === r ? 'selected' : ''}>${ROLE_TITLES[r]}</option>`).join('')}
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
        <label class="field"><span>${isNew ? 'Пароль (пусто — сгенерируется случайный)' : 'Новый пароль (оставьте пустым, чтобы не менять)'}</span>
          <input type="password" id="e-pass" placeholder="••••••••" autocomplete="new-password"></label>
        <label class="field"><span>Подтверждение пароля</span>
          <input type="password" id="e-pass2" placeholder="••••••••" autocomplete="new-password"></label>
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

const DEFAULT_TITLES = { pays_overtime: 'Оплачиваются ли переработки',
                         double_overtime: 'Двойные переработки', plan_equals_fact: 'План=Факт' };
function fmtGdValue(name, v) {
  if (name === 'plan_equals_fact') return { yes: 'Да', no: 'Нет', auto: 'Авто' }[v] || String(v);
  return (v === true || v === 'true' || v === 1) ? 'Да' : 'Нет';
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
  const canWrite = can('settings.edit');   // право, а не роль: гранты и группы учитываются
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
async function shiftModal(st) {
  /* «Код в табеле» — выбор из справочника CFG-DAY-CODES (T1); если словарь ещё не
     загружен, добираем его, иначе редактор предложит только «не задан». */
  if (!(state.tabelCodes || []).length) {
    try {
      state.tabelCodes = (await api('/api/shift-types/tabel-codes', { silent: true })).codes || [];
    } catch { state.tabelCodes = state.tabelCodes || []; }
  }
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
        <label class="field"><span>Код в сетке (подпись ячейки)</span><input type="text" id="sh-short" value="${esc(st?.display_code || '')}" placeholder="08–17 / В / ОТ…">
          <div class="hint" style="margin-top:2px">Только отображение в сетке Графика — на расчёт не влияет.</div></label>
        <label class="field"><span>Код в табеле (CFG-DAY-CODES)</span>
          <select id="sh-tzh">
            <option value="">— не задан —</option>
            ${(state.tabelCodes || []).map(c => `<option value="${esc(c.code)}" ${st?.tzh_code === c.code ? 'selected' : ''}>${esc(c.code)}${c.title ? ' — ' + esc(c.title) : ''}${c.carries_hours ? ' (с часами)' : ''}</option>`).join('')}
            ${st?.tzh_code && !(state.tabelCodes || []).some(c => c.code === st.tzh_code)
              ? `<option value="" selected>⚠ «${esc(st.tzh_code)}» — нет в справочнике (будет очищено)</option>` : ''}
          </select>
          <div class="hint" style="margin-top:2px" id="sh-tzh-hint">По этому коду день заполняется из циклов
            и получает стандартное окно (Я 8 → 09:00–18:00, Я 10,75 → 08:00–20:00). Пусто — смена
            не участвует в автозаполнении Табеля (например, «отпросился»: в Табеле остаётся явка).</div></label>
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
      /* T1: код Табеля определяет стандартное окно, поэтому подсказываем, совпадают ли
         часы смены с окном этого кода (не совпадают — не ошибка, но владелец это видит). */
      const tzhHint = () => {
        const code = $('#sh-tzh').value;
        const box = $('#sh-tzh-hint');
        if (!box) return;
        const meta = (state.tabelCodes || []).find(c => c.code === code);
        const known = (state.tabelCodes || []).map(c => c.code);
        if (!code) {
          box.textContent = (st?.tzh_code && !known.includes(st.tzh_code))
            ? `Прежнее значение «${st.tzh_code}» отсутствует в справочнике кодов Табеля — сохранение очистит поле. Выберите код из списка, чтобы дни этой смены заполнялись из циклов.`
            : 'Код не задан: смена не участвует в автозаполнении Табеля (например, «отпросился»).';
          box.style.color = (st?.tzh_code && !known.includes(st.tzh_code)) ? 'var(--danger)' : '';
          return;
        }
        box.style.color = '';
        box.textContent = `Код «${code}»${meta?.title ? ' — ' + meta.title : ''}: `
          + (meta?.carries_hours
            ? 'несёт часы — день получит стандартное окно из CFG-WINDOWS.'
            : 'часы не несёт — день считается отсутствием.');
      };
      $('#sh-tzh').onchange = tzhHint; tzhHint();
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        const kindSel = $('#sh-kind').value;
        const body = {
          code: $('#sh-code').value.trim().toUpperCase(), name: $('#sh-name').value.trim(),
          short_code: $('#sh-short').value.trim(),
          tzh_code: $('#sh-tzh').value,
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
  state.user = r.user; renderUserChip(); await loadPerms(); navigate(startView());
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
