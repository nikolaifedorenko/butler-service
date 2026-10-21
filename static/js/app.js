/* ══════════════════════════════════════════════════════════════════════
   TimeTrack — веб-интерфейс (SPA без сборки), светлая тема
   Разделы (7): График · Отметки · Сотрудники · Мои отметки · Ночной отчёт ·
   Электрокары · Настройки. Права доступа и Журнал аудита — экраны Настроек
   (группа «Администрирование»), navigate('access'/'audit') продолжает работать.
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
  /* 7 пунктов (19.10.2026, docs/PROPOSAL-SETTINGS-IA-2026-10-19.md): «Права доступа»
     и «Журнал аудита» убраны из верхнего меню — они живут в «Настройках»
     (группа «Администрирование»); navigate('access'/'audit') по-прежнему работает.
     «Настройки» видны, если есть право хотя бы на один их экран. */
  const all = [
    { id: 'grafik', title: 'График', anyPerm: GRAFIK_LAYERS.map(l => l.perm) },
    { id: 'marks', title: 'Отметки', perm: 'presence.view' },
    { id: 'employees', title: 'Сотрудники', perm: 'employees.view' },
    { id: 'me', title: 'Мои отметки', perm: 'me.punch' },
    { id: 'night', title: 'Ночной отчёт', perm: 'night.view' },
    { id: 'cars', title: 'Электрокары', perm: 'cars.view' },
    { id: 'settings', title: 'Настройки', anyPerm: ['settings.view', 'access.manage', 'audit.view'] },
  ];
  return all.filter(t => t.anyPerm ? t.anyPerm.some(can) : can(t.perm));
}

function renderNav() {
  const tabs = visibleTabs();
  /* «Права доступа» и «Журнал аудита» открываются из Настроек (external-экраны):
     их содержимое — отдельные view, но в меню подсвечиваем «Настройки», откуда пришли. */
  const activeView = (state.view === 'access' || state.view === 'audit') ? 'settings' : state.view;
  $('#sidenav').querySelectorAll('.nav-item').forEach(el => el.remove());
  const foot = $('#sidenav-foot');
  tabs.forEach(t => {
    const b = document.createElement('button');
    b.className = 'nav-item' + (activeView === t.id ? ' active' : '');
    b.dataset.view = t.id;
    b.innerHTML = `${ICONS[t.id]}<span>${esc(t.title)}</span>`;
    b.onclick = () => navigate(t.id);
    $('#sidenav').insertBefore(b, foot);
  });
  $('#tabbar').innerHTML = tabs.slice(0, 5).map(t =>
    `<button data-view="${t.id}" class="${activeView === t.id ? 'active' : ''}">${ICONS[t.id]}<span>${esc(t.title)}</span></button>`
  ).join('');
  $$('#tabbar button').forEach(b => b.onclick = () => navigate(b.dataset.view));
  if (tabs.length > 5) {
    const more = document.createElement('button');
    more.className = 'nav-item' + (tabs.slice(5).some(t => t.id === activeView) ? ' active' : '');
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
  $('#login-password').value = '';   // после выхода форма логина пустая (16.10.2026)
}

async function loadPerms() {
  try {
    const me = await api('/api/auth/me', { silent: true });
    state.perms = me.permissions || [];
  } catch { state.perms = []; }
}

function startView() {
  const tabs = visibleTabs().map(t => t.id);
  /* Телефон — основной инструмент батлера (решение владельца 19.10.2026): смену
     начинают с «Моих отметок» (пришёл/ушёл — самое частое действие), а не с «Графика».
     У менеджмента стартовый раздел прежний. */
  const order = state.user?.role === 'employee'
    ? ['me', 'marks', 'grafik']
    : ['grafik', 'marks', 'me'];
  return order.find(v => tabs.includes(v)) || tabs[0] || 'me';
}

/* Сброс состояния при смене пользователя (вход, вход/выход из режима
   «посмотреть глазами сотрудника»): выход не перезагружает страницу, поэтому
   кэши и DOM разделов не должны доставаться следующему пользователю (16.10.2026).
   Полнота сброса — ревью 20.10.2026, P1-fe-1: раньше чистились только
   fact-поля, employees, grafikLayer и вкладки «Графика», а кэши справочников,
   сетки, фильтры, позиция UI и состояния модулей (carsState/nightState/
   settingsUI) переживали смену пользователя. loadDirectory и загрузчики
   разделов наполнят всё заново при входе. */
function resetUserViewState() {
  state.factMode = null; state.factMonth = null; state.factDay = null;
  state.factEmp = null; state.factFrom = null; state.factTo = null;
  state.employees = [];
  /* Кэши справочников: у сотрудника loadDirectory не вызывается — в памяти не
     должно оставаться данных предыдущего менеджера. */
  state.shiftTypes = []; state.departments = []; state.subdivisions = [];
  state.docKinds = []; state.docPlaceholders = {}; state.tabelCodes = [];
  state.grid = null; state.timesheet = null; state.status = null;
  state.filterDept = 'all'; state.filterText = ''; state.expanded = new Set();
  /* Позиция UI — на «сегодня» по часам объекта (serverShiftMs из core). */
  const nowObj = new Date(Date.now() + serverShiftMs);
  state.year = nowObj.getFullYear(); state.month = nowObj.getMonth() + 1;
  state.attDate = todayISO(); state.dpYear = nowObj.getFullYear();
  state.grafikLayer = null;
  /* Состояния модулей (ADR-0008: межфайловые вызовы через глобальную область).
     settingsUI.searchBound НЕ сбрасываем: флаг стережёт одноразовую привязку
     document-листнера ⌘K, которая не снимается — сброс удвоил бы обработчик. */
  Object.assign(carsState, { data: null, meta: null, locations: [], filter: 'all', q: '' });
  Object.assign(nightState, { reportId: null, today: null, areas: null, zoneId: null,
    areaId: null, q: '', filter: 'all', dictTab: 'zones', dictZone: null,
    dictArea: null, defectsSelected: new Set(), defectsShowSent: false });
  Object.assign(settingsUI, { screen: null, data: null, health: null, engine: null,
    draft: null, calYear: 0, calMonth: 0, shiftTab: 'work', payFilter: '' });
  /* DOM разделов — в начальное пустое состояние: в index.html все .view пустые,
     их рисуют загрузчики при открытии; каркас #view-grafik восстановит
     grafikSkeleton() (loadGrafik проверяет #grafik-tabs). Прежняя очистка одного
     #grafik-tabs оставляла чужую разметку остальных разделов до первого открытия. */
  $$('.view').forEach(v => { v.innerHTML = ''; });
}

async function enterApp() {
  resetUserViewState();
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
/* Разделы «Отметки» (доска), «Факт» (история сессий), «Табель», «Управленческий табель»,
   «Права доступа» и «Журнал аудита» — в modules/timesheet_v4.js (движок v7.1). */



/* ══════════════════════════════════════════════════════════════════
   СТАРТ
   ══════════════════════════════════════════════════════════════════ */
/* Форма логина отправляется НАТИВНО (action=/api/auth/login-form, 303-редирект):
   связку «submit формы с паролем → редирект» менеджеры паролей распознают без
   эвристик и предлагают сохранить пароль сразу после входа. Ошибки возвращаются
   кодом в ?login_error=… и показываются здесь при старте. */
const LOGIN_ERRORS = {
  auth: 'Неверный логин или пароль',
  rate: 'Слишком много неудачных попыток входа. Подождите несколько минут.',
  disabled: 'Учётная запись отключена',
};

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
  state.user = r.user; renderUserChip(); await loadPerms();
  resetUserViewState(); navigate(startView());
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

async function bootApp() {
  api('/api/health', { silent: true, allow401: true })
    .then(h => syncServerClock(h?.server_time_local)).catch(() => {});
  const loginErr = new URLSearchParams(location.search).get('login_error');
  if (loginErr) history.replaceState(null, '', location.pathname + location.hash);
  try {
    const me = await api('/api/auth/me', { silent: true, allow401: true });
    if (me?.user) {
      state.user = me.user;
      await loadMediaLimits();     // лимиты фото/видео для подсказок загрузки
      await enterApp();
      return;
    }
  } catch { /* не авторизован */ }
  showLogin();
  if (loginErr) {
    const box = $('#login-error');
    box.textContent = LOGIN_ERRORS[loginErr] || 'Не удалось войти';
    box.classList.remove('hidden');
  }
}
bootApp();
