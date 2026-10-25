/* ══════════════════════════════════════════════════════════════════════
   РАЗДЕЛ «НАСТРОЙКИ» — область с под-разделами.

   Реализация целевой информационной архитектуры (ред. 19.10.2026 —
   docs/PROPOSAL-SETTINGS-IA-2026-10-19.md, развитие SETTINGS-UI-PROPOSAL-2026-10-12):
   единый центр конфигурации объекта. Под-навигация по группам («Расчёт»,
   «Персонал и смены», «Объект», «Доставка», «Администрирование»), hash-адрес
   каждого экрана (#/settings/pay), поиск (⌘K), экран «Обзор» со здоровьем
   конфигурации, формы вместо JSON и черновик версии справочников с diff.
   В группу «Объект» переехали справочники из операционных разделов: ночной
   обход (зоны/объекты/чек-листы/службы — право night.edit) и электрокары
   (парк/места стоянки — право cars.manage); «Права доступа» и «Журнал аудита»
   убраны из верхнего меню и открываются из группы «Администрирование».

   Порядок экранов — по частоте обращений и цене ошибки, а не по порядку таблиц БД.
   Правила оплаты (то, что определяет деньги) — первый класс: карточки модификаторов,
   переопределения, мастер «что → кому → когда» и «Проверитель», который объясняет
   значение для (сотрудник, день) тем же доменным приоритетом 1–7, что и расчёт.

   Зависит от core.js ($, api, state, esc, openModal, toast, …), app.js (can,
   renderDicts, refreshDoublePay, shiftModal, openKindModal, loadDirectory,
   DEFAULT_TITLES, fmtGdValue) и modules/engine_settings.js (renderEngineSettings — режим эксперта).

   Экраны — по файлу на экран: modules/settings_<экран>.js (шаг 6.5 аудита, 22.10.2026);
   здесь — оболочка, реестр, состояние, черновик и публикация версии, здоровье, поиск.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

/* ─────────────────────────── реестр под-разделов ─────────────────────────── */
const SETTINGS_ICONS = {
  home: '<path d="M4 11l8-7 8 7v9a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/>',
  calc: '<rect x="5" y="3" width="14" height="18" rx="2" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="M8 7h8M8 11h3M13 11h3M8 15h3M13 15h3" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
  money: '<circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="M12 7v10M9.5 9.5h4a1.6 1.6 0 0 1 0 3.2h-3a1.6 1.6 0 0 0 0 3.2h4" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round"/>',
  codes: '<rect x="3" y="5" width="18" height="15" rx="2" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="M3 10h18M8 5v15" stroke="currentColor" stroke-width="1.7"/><path d="M12 14h6" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
  people: '<circle cx="9" cy="8" r="3.1" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="M3.5 20c.8-3.3 3-5 5.5-5s4.7 1.7 5.5 5" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linecap="round"/><path d="M16 11h5M18.5 8.5v5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
  cal: '<rect x="3" y="5" width="18" height="16" rx="2" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="M3 10h18M8 3v4M16 3v4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><circle cx="12" cy="15" r="1.4" fill="currentColor"/>',
  shift: '<circle cx="12" cy="12" r="8.6" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="M12 7.2V12l3.2 2" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
  doc: '<path d="M6 3h8l4 4v14H6z" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/><path d="M9 12h7M9 16h7M9 8h3" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
  gear: '<circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="M12 3v2.5M12 18.5V21M4.2 7.5l2.2 1.3M17.6 15.2l2.2 1.3M4.2 16.5l2.2-1.3M17.6 8.8l2.2-1.3" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
  code: '<path d="M9 6l-5 6 5 6M15 6l5 6-5 6" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
  shield: '<path d="M12 3l7 3v5c0 4.5-3 8.2-7 10-4-1.8-7-5.5-7-10V6z" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/><path d="M9.4 12.2l1.9 1.9 3.4-3.6" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
  list: '<path d="M6 3h9l4 4v14H6z" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/><path d="M9 11h7M9 15h7M9 7h4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
  mail: '<rect x="3" y="5.5" width="18" height="13" rx="2" stroke="currentColor" stroke-width="1.7" fill="none"/><path d="M3.8 7l8.2 6 8.2-6" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/>',
  moon: '<path d="M20 13.5A8.5 8.5 0 0 1 10.5 4 8.5 8.5 0 1 0 20 13.5z" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/>',
  car: '<path d="M4 16v-3.2L6.2 8h11.6L20 12.8V16" stroke="currentColor" stroke-width="1.7" fill="none" stroke-linejoin="round"/><rect x="3" y="15" width="18" height="4.5" rx="1.6" stroke="currentColor" stroke-width="1.7" fill="none"/><circle cx="7.3" cy="17.2" r="1" fill="currentColor"/><circle cx="16.7" cy="17.2" r="1" fill="currentColor"/>',
};

/* Состав раздела (ред. 19.10.2026 — единый центр конфигурации,
   docs/PROPOSAL-SETTINGS-IA-2026-10-19.md): группы «Расчёт», «Персонал и смены»,
   «Объект» (ночной обход, электрокары, документы), «Доставка», «Администрирование».
   Подписи, группы, порядок и право ВИДИМОСТИ экранов объявляют манифесты модулей (Screen,
   шаг 5.4) — список приходит в /api/auth/me уже по правам; рендер и иконку регистрирует
   файл, где живёт экран (registerModule): справочники «Объекта» — modules/night.js и
   modules/cars.js, рядом со своим доменом. `external` — переход в самостоятельный view:
   «Права доступа» и «Журнал аудита» убраны из верхнего меню (19.10.2026) и открываются
   отсюда. Право правки экраны проверяют сами (night.edit, cars.manage, settings.edit). */
registerModule({ views: { settings: loadSettings } });   // экраны регистрируют свои файлы settings_*.js

/* Экраны в порядке манифестов, с записями групп ({ group }) перед первым экраном группы. */
function settingsScreens() {
  const out = [];
  let group = null;
  (state.settingsScreens || []).forEach(({ group: g, ...s }) => {
    if (g && g !== group) out.push({ group: g });
    group = g;
    out.push({ ...s, ...MODULE_SCREENS[s.id] });   // без group: запись с group — заголовок
  });
  return out;
}
function settingsTitle(id) { return settingsScreens().find(s => s.id === id)?.title; }

/* Открыть конкретный экран Настроек из другого раздела (deep-link 19.10.2026):
   «Справочник» в «Ночном отчёте» и «+ Кар»/«Места» в «Электрокарах» больше не
   открывают свои модалки — единственное место правки справочника здесь.
   Hash читает loadSettings при входе в раздел. */
function settingsOpen(screenId) {
  location.hash = `#/settings/${screenId}`;
  navigate('settings');
}

/* Карточки модификаторов CFG-MODIFIERS: что делает правило, пример и ссылка на норму.
   Тексты — из спецификации v7.1 (5.2, CFG-MODIFIERS, CFG-WEIGHTS), не из кода. */
const SETTINGS_MODS = [
  { name: 'pays_overtime', title: 'Оплачиваются ли переработки', type: 'bool', def: 'Да',
    what: 'Переработка дня идёт в УТ («Да») или в банк часов по весу кода («Нет»).',
    ex: '12 ч ДЯ2 при «Нет» → 24 ч банка, в УТ дня кодов нет (INV-NO-CODES-WHEN-EXCLUDED).',
    spec: '5.2 · pays_overtime(D) = counts_in_ut(D) ∧ модификатор(D) · RUL-UNPAID-TO-BANK' },
  { name: 'double_overtime', title: 'Двойные переработки', type: 'bool', def: 'Нет',
    what: 'Вес часа переработки = 2: коды ДЯ2/ДН2 вместо ДЯ/ДН.',
    ex: 'Источники-слои: производственный календарь и ВИП-периоды подмешиваются автоматически.',
    spec: 'CFG-MODIFIERS · CFG-WEIGHTS (ДЯ2 = 2) · каскад гасит долг двойными последними' },
  { name: 'plan_equals_fact', title: 'План=Факт', type: 'tri', def: 'Нет',
    what: 'День без отметок и без факта считается отработанным как запланировано.',
    ex: 'Применяется, если: код несёт часы ∧ значение «Да» ∧ нет исходной отметки ∧ факт = 0.',
    spec: 'R30 (единый предикат) · «Авто» разрешается в «Да» только колонкой кода (R19, стартово у «К»)' },
  { name: 'counts_in_ut', title: 'Учитываются ли часы в УТ', type: 'bool', def: 'по коду дня',
    what: 'Переопределяет колонку «Учитывается в УТ» из справочника кодов Табеля.',
    ex: 'Уровень 7 для этого правила — колонка кода, а не глобальная строка (CHK-DEFAULTS).',
    spec: 'CFG-DAY-CODES.counts_in_ut · участвует в pays_overtime' },
];
const SETTINGS_LEVEL_FORMS = { 1: 'сотрудник + день', 2: 'сотрудник + период', 3: 'группа + день',
  4: 'группа + период', 5: 'все + день', 6: 'все + период', 7: 'глобальный дефолт' };

/* ─────────────────────────── состояние раздела ─────────────────────────── */
/* Отдельный объект, а не поля глобального `state`: здесь живут черновик версии
   справочников и кеши запросов экрана, которые не нужны остальным разделам. */
const settingsUI = {
  screen: null,
  data: null,          // /api/settings
  health: null,        // /api/engine-settings/health
  engine: null,        // /api/engine-settings
  draft: null,         // черновик payload (копия active.payload)
  calYear: 0, calMonth: 0,
  shiftTab: 'work',
  payFilter: '',
  searchBound: false,
};

function settingsInvalidate() {
  settingsUI.engine = null; settingsUI.health = null; settingsUI.draft = null;
}
async function settingsEngine() {
  if (!settingsUI.engine) settingsUI.engine = await api('/api/engine-settings');
  return settingsUI.engine;
}
async function settingsHealth() {
  if (!settingsUI.health) settingsUI.health = await api('/api/engine-settings/health', { silent: true });
  return settingsUI.health;
}
function settingsPayload() { return settingsUI.engine?.active?.payload || null; }
function settingsDraft() {
  const p = settingsPayload();
  if (!p) return null;
  if (!settingsUI.draft) settingsUI.draft = JSON.parse(JSON.stringify(p));
  return settingsUI.draft;
}
function settingsDirty() {
  const p = settingsPayload();
  return !!(p && settingsUI.draft && JSON.stringify(p) !== JSON.stringify(settingsUI.draft));
}
async function settingsRefresh() {
  settingsInvalidate();
  await loadSettings();
}

/* ─────────────────────────── мелкие помощники ─────────────────────────── */
function settingsHm(min) {
  const m = ((Number(min) || 0) % 1440 + 1440) % 1440;
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}
function settingsMin(hhmm) {
  const [h, m] = String(hhmm || '').split(':').map(Number);
  if (Number.isNaN(h) || Number.isNaN(m)) return null;
  return h * 60 + m;
}
function settingsSnap(min, step) {
  const s = Number(step) || 15;
  return Math.round((Number(min) || 0) / s) * s;
}
function settingsHoursText(min) {
  const m = Number(min) || 0;
  return `${hours(m / 60)} ч`;
}
function settingsLevelBadge(level) {
  return `<span class="level-badge${level === 7 ? ' l7' : ''}" title="Уровень приоритета ${level}: ${esc(SETTINGS_LEVEL_FORMS[level] || '')}">${level}</span>`;
}
function settingsChainHtml(chain) {
  if (!chain || !chain.length) return '';
  return `<div class="chain">${chain.map((c, i) => `${i ? '<span class="arrow">→</span>' : ''}
    <span class="step${c.hit ? ' hit' : ''}">${settingsLevelBadge(c.level)} ${esc(c.form)}${c.hit ? ' ✓' : ''}</span>`).join('')}</div>`;
}
function settingsCodeColor(code, policy) {
  const from = policy?.[code]?.color;
  return cssColor(from, v4CodeColor(code, null));
}
function settingsCodePill(code, policy) {
  const c = settingsCodeColor(code, policy);
  return `<span class="code-pill" style="background:${withAlpha(c, .16)};color:${c}">${esc(code)}</span>`;
}
function settingsPanel(title, body, extra = '') {
  return `<div class="panel">${title ? `<h3 class="panel-title">${title}</h3>` : ''}${extra}${body}</div>`;
}
function settingsHead(title, sub, right = '') {
  return `<div class="page-head"><div><h2>${esc(title)}</h2><div class="sub">${sub}</div></div>
    <div class="spacer"></div>${right}</div>`;
}
/* Привязка клика к элементу, которого может не быть: кнопки правки не отрисовываются
   без права settings.edit, и обращение к null роняло весь экран (найдено снимком
   интерфейса под супервайзером). */
function settingsOn(sel, host, fn) {
  const el = $(sel, host);
  if (el) el.onclick = fn;
  return el;
}
function settingsFail(host, e) {
  host.innerHTML = `<div class="panel"><h3 class="panel-title">Не загрузилось</h3>
    <p style="color:var(--danger);font-weight:600">${esc(e?.message || e)}</p>
    <p class="hint">Проверьте соединение и повторите. Если ошибка повторяется — откройте
    «Система → Диагностика» и пришлите текст ошибки.</p>
    <button class="btn btn-sm" id="st-retry">Повторить</button></div>`;
  const b = $('#st-retry', host);
  if (b) b.onclick = () => settingsRefresh();
}

/* ─────────────────────────── оболочка раздела ─────────────────────────── */
function settingsScreenAllowed(id) {
  /* id обязателен: у записей групп ({ group: … }) его нет, и find по undefined
     матчил бы группу — экран «undefined» вместо «Обзора» (найдено сценарием) */
  if (!id) return false;
  const item = settingsScreens().find(s => s.id === id);
  return !!item && !item.external && (!item.perm || can(item.perm));
}

async function loadSettings() {
  const host = $('#view-settings');
  if (!host) return;
  host.innerHTML = '<div class="empty">Загрузка…</div>';
  try {
    settingsUI.data = await api('/api/settings', { silent: true });
  } catch (e) {
    /* Данные раздела недоступны (например, пункту «Настройки» хватит права
       access.manage/audit.view — а /api/settings требует settings.view): оболочку
       всё равно рисуем, external-экраны работают без данных, остальные покажут
       свою ошибку в теле (19.10.2026). */
    settingsUI.data = null;
  }

  const fromHash = (location.hash.match(/^#\/settings\/([a-z-]+)/) || [])[1];
  const screen = settingsScreenAllowed(fromHash) ? fromHash
    : (settingsScreenAllowed(settingsUI.screen) ? settingsUI.screen : 'overview');
  settingsUI.screen = screen;
  if (!settingsUI.calYear) { settingsUI.calYear = state.year; settingsUI.calMonth = state.month; }
  settingsBindSearch();

  let health = null;
  try { health = await settingsHealth(); } catch { health = null; }   // «Обзор» покажет причину

  const errors = (health?.checks || []).filter(c => c.level === 'error').length;
  host.innerHTML = `
    <div class="page-head">
      <div><h2>Настройки</h2>
        <div class="sub">Правила расчёта и деньги · справочники Табеля · словарь смен · документы.
          Каждый экран имеет собственный адрес — на него можно дать ссылку</div></div>
      <div class="spacer"></div>
      <button class="settings-search" id="st-search" title="Поиск по настройкам">
        <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><circle cx="11" cy="11" r="6.5" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M16 16l4.5 4.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
        <span>Поиск по настройкам…</span><kbd>⌘K</kbd></button>
    </div>
    <div class="settings-layout">
      <nav class="settings-nav" id="st-nav" aria-label="Под-разделы настроек"></nav>
      <div class="settings-body" id="st-body"><div class="empty">Загрузка…</div></div>
    </div>`;
  settingsOn('#st-search', host, () => settingsSearchPalette());
  settingsRenderNav(health, errors);
  await settingsRenderScreen();
}

function settingsRenderNav(health, errors) {
  const nav = $('#st-nav');
  if (!nav) return;
  const s = health?.stats || {};
  const counters = {
    overview: errors ? { n: (health?.checks || []).length, bad: true } : null,
    pay: s.rules_active ? { n: s.rules_active } : null,
    codes: s.codes ? { n: s.codes } : null,
    shifts: { n: (state.shiftTypes || []).filter(x => !x.archived).length },
    calendar: s.rules_upcoming ? { n: s.rules_upcoming } : null,
  };
  nav.innerHTML = settingsScreens().filter(x => !x.perm || can(x.perm)).map(item => {
    if (item.group) return `<div class="nav-group">${esc(item.group)}</div>`;
    const active = item.id === settingsUI.screen ? ' active' : '';
    const c = counters[item.id];
    const arrow = item.external ? ' ↗' : '';
    return `<button class="nav-item${active}" data-st="${item.id}" title="${esc(item.title)}">
      <svg viewBox="0 0 24 24" aria-hidden="true">${SETTINGS_ICONS[item.icon] || ''}</svg>
      <span>${esc(item.title)}${arrow}</span>
      ${c ? `<span class="cnt${c.bad ? ' bad' : ''}">${c.n}</span>` : ''}</button>`;
  }).join('') + `<div class="nav-foot">Движок v7.1${health?.version?.id
    ? ` · версия справочников #${health.version.id}<br>действует с ${dateRu(health.version.valid_from)}`
    : ' · справочники по умолчанию'}<br>${errors
    ? `<b style="color:var(--danger)">ошибок конфигурации: ${errors}</b>`
    : 'конфигурация здорова'}</div>`;
  $$('#st-nav [data-st]').forEach(b => b.onclick = () => settingsGo(b.dataset.st));
}

function settingsGo(id) {
  const item = settingsScreens().find(s => s.id === id);
  if (!item) return;
  if (item.external) { navigate(item.external); return; }
  if (item.perm && !can(item.perm)) { toast(`Нет права на экран «${item.title}»`, 'warn'); return; }
  if (settingsDirty() && id !== settingsUI.screen) {
    confirmDialog('Черновик не опубликован',
      'В справочниках есть несохранённые изменения. Перейти на другой экран и потерять черновик?',
      () => { settingsUI.draft = null; settingsUI.screen = id; settingsRenderScreen(); },
      'Потерять и перейти');
    return;
  }
  settingsUI.screen = id;
  settingsRenderScreen();
}

/* Поколение рендера экрана настроек (ревью 20.10.2026, P1-fe-6): при быстром
   переключении экранов медленный render прежнего экрана возвращался ПОСЛЕ
   нового и перезаписывал #st-body чужим содержимым (nav подсвечивал один
   экран, показывался другой). */
/* Последний закрытый период — по сотрудникам (решение владельца 25.10.2026): закрытие
   «всё или ничего», но период мог остаться закрытым частично (прежние правила, сбой);
   тогда — сколько закрыто и у кого нет, чтобы докрыть «Закрыть месяц». */
function closedPeriodText(lc, { recalcNote = true } = {}) {
  if (!lc) return 'закрытых периодов нет';
  const head = `начинается ${dateRu(lc.start)}`;
  if (lc.complete) {
    return `${head} — закрыт у всех (${lc.total})`
      + (recalcNote && lc.recalc_available ? ' · доступен пересчёт' : '');
  }
  const names = (lc.not_closed || []).slice(0, 5).join(', ');
  const more = (lc.not_closed || []).length > 5 ? ` и ещё ${lc.not_closed.length - 5}` : '';
  return `${head} — закрыт у ${lc.closed_count} из ${lc.total} · не закрыт: ${names}${more}`;
}

let settingsRenderGen = 0;

async function settingsRenderScreen() {
  const gen = ++settingsRenderGen;
  const old = $('#st-body');
  if (!old) return;
  /* Рендерим в СВЕЖИЙ узел: запоздалый render предыдущего экрана пишет в уже
     отсоединённый старый узел и невидим; id/class сохраняются (cloneNode),
     поэтому $('#st-body') везде указывает на актуальный узел. */
  const body = old.cloneNode(false);
  old.replaceWith(body);
  /* fallback — «Обзор», а не settingsScreens()[1]: после перегруппировки (19.10.2026)
     под этим индексом может оказаться запись группы без render */
  const item = settingsScreens().find(s => s.id && s.id === settingsUI.screen)
    || settingsScreens().find(s => s.id === 'overview');
  settingsUI.screen = item.id;
  if (history.replaceState) history.replaceState(null, '', `#/settings/${item.id}`);
  $$('#st-nav [data-st]').forEach(b => b.classList.toggle('active', b.dataset.st === item.id));
  body.innerHTML = '<div class="empty">Загрузка…</div>';
  body.scrollTop = 0;
  try {
    await item.render(body);
  } catch (e) {
    if (gen === settingsRenderGen) {
      console.error('экран настроек', item.id, e);
      settingsFail(body, e);
    }
  }
  if (gen !== settingsRenderGen) return;   // пока ждали, открыли другой экран — не мешаем
  settingsUpdateDraftBars();
}

/* Черновик версии справочников: одна плавающая панель на всех экранах, где он есть. */
function settingsUpdateDraftBars() {
  $$('[data-draft-bar]').forEach(bar => {
    const dirty = settingsDirty();
    const n = dirty ? settingsDiff(settingsPayload(), settingsUI.draft).length : 0;
    bar.classList.toggle('idle', !dirty);
    const t = $('.t', bar);
    if (t) t.textContent = dirty
      ? `Черновик: ${n} ${plural(n, 'изменение', 'изменения', 'изменений')} · не опубликовано`
      : 'Черновика нет: показана действующая версия справочников';
    $$('[data-draft-act]', bar).forEach(b => { b.disabled = !dirty; });
  });
}
function settingsDraftBarHtml() {
  if (!can('settings.edit')) return '';
  return `<div class="draft-bar idle" data-draft-bar>
    <span class="t">Черновика нет: показана действующая версия справочников</span>
    <span class="spacer"></span>
    <button class="btn btn-sm" data-draft-diff data-draft-act disabled>Что изменилось</button>
    <button class="btn btn-sm" data-draft-reset data-draft-act disabled>Сбросить</button>
    <button class="btn btn-sm btn-primary" data-draft-publish data-draft-act disabled>Опубликовать версию…</button>
  </div>`;
}
function settingsBindDraftBar(host) {
  const bar = $('[data-draft-bar]', host);
  if (!bar) return;
  $('[data-draft-diff]', bar).onclick = () =>
    settingsDiffModal(settingsPayload(), settingsUI.draft, 'Черновик против действующей версии');
  $('[data-draft-reset]', bar).onclick = () => confirmDialog('Сбросить черновик?',
    'Несохранённые изменения справочников будут потеряны.',
    () => { settingsUI.draft = null; settingsRenderScreen(); }, 'Сбросить', false);
  $('[data-draft-publish]', bar).onclick = () => settingsPublishModal();
}

/* ─────────────────────────── diff и публикация версии ─────────────────────────── */
function settingsGranularityText(g) { return g === 'half_month' ? 'полмесяца (1–15 / 16–конец)' : 'месяц'; }

function settingsDiff(base, draft) {
  const out = [];
  if (!base || !draft) return out;
  const push = (block, text) => out.push({ block, text });
  const scalar = (key, label, fmt) => {
    const a = base[key], b = draft[key];
    if (String(a) !== String(b)) push('Каркас', `${label}: ${fmt ? fmt(a) : a} → ${fmt ? fmt(b) : b}`);
  };
  scalar('tz', 'Часовой пояс');
  scalar('period_granularity', 'Период расчёта', settingsGranularityText);
  scalar('step_minutes', 'Шаг расчёта', v => `${v} мин`);
  scalar('late_limit_minutes', 'Лимит опоздания', v => `${v} мин`);
  scalar('day_limit_minutes', 'Лимит часов в дне', v => `${v} мин`);

  const cat = (p, code) => (p.categories || []).find(c => c.code === code) || null;
  const day = cat(base, 'ДЯ'), dayNew = cat(draft, 'ДЯ');
  if (day && dayNew && (day.start_minute !== dayNew.start_minute || day.end_minute !== dayNew.end_minute)) {
    push('Категории времени', `Дневные часы (ДЯ): ${settingsHm(day.start_minute)}–${settingsHm(day.end_minute)} → `
      + `${settingsHm(dayNew.start_minute)}–${settingsHm(dayNew.end_minute)} (ночные ДН — дополнение суток)`);
  }
  Object.keys({ ...(base.weights || {}), ...(draft.weights || {}) }).forEach(k => {
    const a = base.weights?.[k], b = draft.weights?.[k];
    if (String(a) !== String(b)) push('Веса кодов УТ', `${k}: ${a ?? '—'} → ${b ?? '—'}`);
  });
  ['cascade_order', 'placement_order'].forEach(key => {
    const a = (base[key] || []).join(' → '), b = (draft[key] || []).join(' → ');
    if (a !== b) push(key === 'cascade_order' ? 'Порядок каскада' : 'Порядок размещения', `${a || '—'} → ${b || '—'}`);
  });
  const gA = base.groups || [], gB = draft.groups || [];
  gB.filter(g => !gA.includes(g)).forEach(g => push('Группы', `добавлена «${g}»`));
  gA.filter(g => !gB.includes(g)).forEach(g => push('Группы', `исключена «${g}»`));

  const codesA = base.day_code_policy || {}, codesB = draft.day_code_policy || {};
  Object.keys(codesB).filter(c => !codesA[c]).forEach(c =>
    push('Коды Табеля', `добавлен «${c}»${codesB[c].title ? ` — ${codesB[c].title}` : ''}`));
  Object.keys(codesA).filter(c => !codesB[c]).forEach(c => push('Коды Табеля', `исключён «${c}»`));
  Object.keys(codesA).filter(c => codesB[c]).forEach(c => {
    const a = codesA[c], b = codesB[c];
    ['carries_hours', 'accepts_ut', 'counts_in_ut', 'plan_equals_fact_auto'].forEach(f => {
      if (!!a[f] !== !!b[f]) {
        const labels = { carries_hours: 'несёт часы', accepts_ut: 'принимает коды УТ',
          counts_in_ut: 'учитывается в УТ', plan_equals_fact_auto: '«План=Факт» = Авто' };
        push('Коды Табеля', `«${c}» · ${labels[f]}: ${a[f] ? 'Да' : 'Нет'} → ${b[f] ? 'Да' : 'Нет'}`);
      }
    });
    if ((a.title || '') !== (b.title || '')) push('Коды Табеля', `«${c}» · название: ${a.title || '—'} → ${b.title || '—'}`);
    if ((a.color || '') !== (b.color || '')) push('Коды Табеля', `«${c}» · цвет: ${a.color || '—'} → ${b.color || '—'}`);
  });
  const wA = base.windows || {}, wB = draft.windows || {};
  Object.keys(wB).filter(k => !wA[k]).forEach(k =>
    push('Окна и значения', `добавлено «${k}»: ${settingsHm(wB[k].start_minute)}–${settingsHm(wB[k].end_minute)}`));
  Object.keys(wA).filter(k => !wB[k]).forEach(k => push('Окна и значения', `удалено «${k}»`));
  Object.keys(wA).filter(k => wB[k]).forEach(k => {
    if (wA[k].start_minute !== wB[k].start_minute || wA[k].end_minute !== wB[k].end_minute) {
      push('Окна и значения', `«${k}»: ${settingsHm(wA[k].start_minute)}–${settingsHm(wA[k].end_minute)} → `
        + `${settingsHm(wB[k].start_minute)}–${settingsHm(wB[k].end_minute)}`);
    }
  });
  const gdA = base.global_defaults || {}, gdB = draft.global_defaults || {};
  SETTINGS_MODS.filter(m => m.name in gdB || m.name in gdA).forEach(m => {
    const a = gdA[m.name], b = gdB[m.name];
    if (String(a) !== String(b)) {
      push('Правила оплаты', `${m.title} (глобально): ${fmtGdValue(m.name, a)} → ${fmtGdValue(m.name, b)}`);
    }
  });
  return out;
}

function settingsDiffModal(base, draft, title) {
  const lines = settingsDiff(base, draft);
  openModal({
    title: title || 'Что изменилось', wide: true,
    subtitle: lines.length ? `${lines.length} ${plural(lines.length, 'правка', 'правки', 'правок')} в черновике` : 'изменений нет',
    body: lines.length
      ? `<div class="settings-list">${[...new Set(lines.map(l => l.block))].map(block => `
          <div class="panel" style="margin:0;box-shadow:none">
            <h3 class="panel-title">${esc(block)}</h3>
            ${lines.filter(l => l.block === block).map(l =>
              `<div class="kv"><span class="v" style="text-align:left;font-weight:600">${esc(l.text)}</span></div>`).join('')}
          </div>`).join('')}</div>`
      : '<p class="hint">Черновик совпадает с действующей версией справочников.</p>',
    footer: '<button class="btn btn-primary" data-ok>Закрыть</button>',
    onMount(m) { m.querySelector('[data-ok]').onclick = closeModal; },
  });
}

/* Фактическая дата применения: версия выбирается по дате НАЧАЛА периода
   (base_version(period.start)), поэтому любая дата внутри периода означает
   «с начала следующего» — показываем честно, до публикации (дефект D25). */
function settingsAppliesFrom(validFrom, granularity) {
  const d = new Date(`${validFrom}T12:00:00`);
  if (Number.isNaN(d.getTime())) return null;
  if (granularity === 'half_month') {
    if (d.getDate() <= 15) return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`;
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-16`;
  }
  if (d.getDate() === 1) return validFrom;
  const n = new Date(d.getFullYear(), d.getMonth() + 1, 1);
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}-01`;
}

function settingsPublishModal() {
  const draft = settingsDraft();
  if (!draft) return;
  const lines = settingsDiff(settingsPayload(), draft);
  if (!lines.length) return toast('Черновик не отличается от действующей версии', 'warn');
  const today = todayISO();
  const first = settingsAppliesFrom(today, draft.period_granularity) || today;
  const gran = draft.period_granularity || 'month';
  openModal({
    title: 'Опубликовать версию справочников', wide: true,
    subtitle: `${lines.length} ${plural(lines.length, 'правка', 'правки', 'правок')} · проверка CHK-* выполняется при сохранении`,
    body: `
      <div class="wizard-steps">
        <div class="ws on"><b>1 · Что меняем</b>черновик справочников</div>
        <div class="ws on"><b>2 · С какой даты</b>любая дата</div>
        <div class="ws"><b>3 · Проверка</b>сервер вернёт все нарушения разом</div>
      </div>
      <div class="settings-list" style="max-height:34vh;overflow:auto">
        ${[...new Set(lines.map(l => l.block))].map(block => `<div>
          <div class="opt-group-title">${esc(block)}</div>
          ${lines.filter(l => l.block === block).map(l =>
            `<div class="kv"><span class="v" style="text-align:left;font-weight:600">${esc(l.text)}</span></div>`).join('')}
        </div>`).join('')}
      </div>
      <div class="grid-2" style="margin-top:14px">
        <label class="field"><span>Действует с</span><input type="date" id="pb-from" value="${esc(first)}">
          <div class="hint">Дата больше не ограничена 1-м или 16-м числом: версия применяется к периодам,
            <b>начинающимся</b> с этой даты или позже</div></label>
        <label class="field"><span>Комментарий (обязателен)</span><input type="text" id="pb-note"
          placeholder="что и почему меняем — текст попадёт в историю версий"></label>
      </div>
      <div class="preview" id="pb-preview"></div>
      <p class="hint">Закрытые периоды не пересчитываются (RUL-CLOSED-PERIOD-IMMUTABLE): чтобы исправить
        последний закрытый период, опубликуйте версию датой не позже его начала и выполните
        «Пересчитать» в «Управленческом табеле».</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-save>Опубликовать</button>`,
    onMount(m) {
      const from = m.querySelector('#pb-from');
      const note = m.querySelector('#pb-note');
      const preview = m.querySelector('#pb-preview');
      const health = settingsUI.health;
      const lastClosed = health?.periods?.last_closed_start || null;
      const cur = health?.periods?.current || null;
      const render = () => {
        const v = from.value || today;
        const applies = settingsAppliesFrom(v, gran);
        const rows = [
          ['Указана дата', dateRu(v)],
          ['Фактически применится', `к периодам, начинающимся с <b>${dateRu(applies)}</b>`],
        ];
        if (cur && applies > cur.end) {
          rows.push([`Текущий период (${dateRu(cur.start)}–${dateRu(cur.end)})`,
            'считается по прежней версии — дата лежит внутри него']);
        } else if (cur && applies <= cur.start) {
          rows.push([`Текущий период (${dateRu(cur.start)}–${dateRu(cur.end)})`,
            '<b style="color:var(--warn)">будет пересчитан по новой версии</b>']);
        }
        if (lastClosed) {
          const lc = health?.periods?.last_closed;
          const who = lc && !lc.complete ? ` (закрыт у ${lc.closed_count} из ${lc.total})` : '';
          rows.push(['Последний закрытый период', applies <= lastClosed
            ? `<b style="color:var(--warn)">начинается ${dateRu(lastClosed)}${esc(who)} — нужен явный пересчёт в «Управленческом табеле»</b>`
            : `начинается ${dateRu(lastClosed)}${esc(who)} — не затрагивается`]);
        }
        preview.innerHTML = rows.map(([k, val]) =>
          `<div class="row"><span class="k">${esc(k)}</span><span>${val}</span></div>`).join('');
      };
      from.onchange = render; render();
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        if (!note.value.trim()) return toast('Напишите комментарий: зачем меняется конфигурация', 'warn');
        if (!from.value) return toast('Укажите дату вступления', 'warn');
        try {
          const r = await api('/api/engine-settings', { method: 'PUT', body: {
            valid_from: from.value, payload: settingsUI.draft, note: note.value.trim(),
            base_version_id: settingsUI.engine?.latest_id ?? null } });
          closeModal();
          toast(`Версия #${r.id} опубликована · применится с ${dateRu(r.applies_from)}`
            + (r.period?.closed ? ' (период закрыт — нужен пересчёт)' : ''), 'ok');
          await settingsRefresh();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ─────────────────────────── здоровье конфигурации ─────────────────────────── */
function settingsHealthBanner(health) {
  const checks = health?.checks || [];
  if (!checks.length) {
    return `<div class="health ok"><b>Конфигурация здорова</b>
      <ul><li>Проверки CHK-* и сверки справочников не нашли замечаний на ${esc(dateRu(health?.on))}</li></ul></div>`;
  }
  const errors = checks.filter(c => c.level === 'error');
  const warns = checks.filter(c => c.level !== 'error');
  const cls = errors.length ? 'bad' : '';
  return `<div class="health ${cls}">
    <b>${errors.length
      ? `${errors.length} ${plural(errors.length, 'ошибка', 'ошибки', 'ошибок')} конфигурации — расчёт остановится`
      : `${warns.length} ${plural(warns.length, 'предупреждение', 'предупреждения', 'предупреждений')}`}</b>
    <ul>${checks.slice(0, 12).map(c => `<li>
      <span>${c.level === 'error' ? '⛔' : '⚠'} ${esc(c.text)}
        <span class="spec-ref">[${esc(c.code)}]</span></span>
      <button data-go="${esc(c.screen)}">${esc(settingsTitle(c.screen) || c.screen)} →</button></li>`).join('')}
      ${checks.length > 12 ? `<li><span>… и ещё ${checks.length - 12}</span></li>` : ''}</ul></div>`;
}
function settingsBindHealth(host) {
  $$('[data-go]', host).forEach(b => b.onclick = () => settingsGo(b.dataset.go));
}

/* ══════════════════════════════════════════════════════════════════════
   ПОИСК ПО НАСТРОЙКАМ (⌘K / Ctrl+K) — любая настройка находится за 2 нажатия
   ══════════════════════════════════════════════════════════════════════ */
function settingsSearchIndex() {
  const out = [];
  settingsScreens().filter(s => s.id).forEach(s => out.push({
    title: s.title, hint: s.external ? 'отдельная вкладка приложения' : 'под-раздел настроек',
    screen: s.id, external: s.external || null }));
  const p = settingsPayload();
  if (p) {
    Object.keys(p.day_code_policy || {}).forEach(c => out.push({
      title: `Код Табеля «${c}»${p.day_code_policy[c].title ? ' — ' + p.day_code_policy[c].title : ''}`,
      hint: 'справочник кодов', screen: 'codes' }));
    Object.keys(p.windows || {}).forEach(k => out.push({
      title: `Значение и окно «${k}»`,
      hint: `${settingsHm(p.windows[k].start_minute)}–${settingsHm(p.windows[k].end_minute)}`, screen: 'codes' }));
    Object.keys(p.weights || {}).forEach(k => out.push({
      title: `Вес кода УТ «${k}» = ${p.weights[k]}`, hint: 'CFG-WEIGHTS', screen: 'calc' }));
    (p.groups || []).forEach(g => out.push({ title: `Группа «${g}»`, hint: 'CFG-GROUPS', screen: 'groups' }));
    out.push({ title: 'Лимит опоздания', hint: `${p.late_limit_minutes} мин`, screen: 'calc' });
    out.push({ title: 'Шаг расчёта', hint: `${p.step_minutes} мин`, screen: 'calc' });
    out.push({ title: 'Период расчёта', hint: settingsGranularityText(p.period_granularity), screen: 'calc' });
    out.push({ title: 'Часовой пояс', hint: String(p.tz || ''), screen: 'calc' });
    out.push({ title: 'Категории ДЯ/ДН', hint: 'дневные и ночные часы', screen: 'calc' });
    out.push({ title: 'Порядок каскада и размещения', hint: 'CFG-CASCADE, CFG-PLACEMENT', screen: 'calc' });
  }
  SETTINGS_MODS.forEach(m => out.push({ title: m.title, hint: m.what, screen: 'pay' }));
  /* Справочники группы «Объект» (19.10.2026) — статические записи: содержимое
     экраны подгружают сами, а найти их поиском можно уже отсюда. */
  if (can('night.view')) {
    out.push({ title: 'Зоны ночного обхода', hint: 'справочник обхода: зоны, объекты', screen: 'night' });
    out.push({ title: 'Чек-листы зон', hint: 'шаблон зоны и индивидуальные пункты объекта', screen: 'night' });
    out.push({ title: 'Ответственные службы', hint: 'получатели недостатков: чат и почта', screen: 'night' });
  }
  if (can('cars.view')) {
    out.push({ title: 'Парк электрокаров', hint: 'кары: карточка, архив', screen: 'cars' });
    out.push({ title: 'Места стоянки', hint: 'справочник мест электрокаров', screen: 'cars' });
  }
  (settingsUI.data?.items || []).forEach(i => out.push({
    title: i.description || i.key, hint: `прочие правила объекта · ${i.key}`, screen: 'docs' }));
  (state.shiftTypes || []).forEach(s => out.push({
    title: `${s.kind === 'work' ? 'Смена' : 'Отсутствие'} «${s.name}»`, hint: `${s.code}`, screen: 'shifts' }));
  (state.docKinds || []).forEach(k => out.push({
    title: `Вид заявления «${k.name}»`, hint: k.code, screen: 'docs' }));
  return out;
}

function settingsSearchPalette() {
  const index = settingsSearchIndex();
  openModal({
    title: 'Поиск по настройкам', wide: true,
    subtitle: `${index.length} ${plural(index.length, 'пункт', 'пункта', 'пунктов')} · экраны, справочники, правила, смены`,
    body: `<div class="search-palette">
      <input type="text" id="sp-q" placeholder="например: переработки, окно, лимит, Смена 1…" autocomplete="off">
      <div class="res" id="sp-res"></div></div>`,
    onMount(m) {
      const q = m.querySelector('#sp-q'), res = m.querySelector('#sp-res');
      const draw = list => {
        res.innerHTML = list.slice(0, 40).map((x, i) => `<button data-i="${i}" class="${i === 0 ? 'sel' : ''}">
          <span><b>${esc(x.title)}</b><br><small style="color:var(--muted-2)">${esc(x.hint || '')}</small></span>
          <small>${esc(settingsTitle(x.screen) || '')}${x.external ? ' ↗' : ''}</small></button>`).join('')
          || '<p class="hint" style="padding:10px">Ничего не найдено</p>';
        $$('[data-i]', res).forEach(b => b.onclick = () => pick(list[+b.dataset.i]));
      };
      const pick = x => {
        if (!x) return;
        closeModal();
        if (x.external) { navigate(x.external); return; }
        if (x.screen !== settingsUI.screen) settingsGo(x.screen);
        else settingsRenderScreen();
      };
      const filter = () => {
        const s = q.value.trim().toLowerCase();
        draw(!s ? index : index.filter(x =>
          `${x.title} ${x.hint || ''} ${settingsTitle(x.screen) || ''}`.toLowerCase().includes(s)));
      };
      q.oninput = filter;
      q.onkeydown = e => {
        const items = $$('[data-i]', res);
        const cur = items.findIndex(b => b.classList.contains('sel'));
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault();
          const next = Math.min(items.length - 1, Math.max(0, cur + (e.key === 'ArrowDown' ? 1 : -1)));
          items.forEach((b, i) => b.classList.toggle('sel', i === next));
          items[next]?.scrollIntoView({ block: 'nearest' });
        } else if (e.key === 'Enter') { e.preventDefault(); pick(items[cur >= 0 ? cur : 0] && index[+items[cur >= 0 ? cur : 0].dataset.i]); }
      };
      filter(); q.focus();
    },
  });
}

function settingsBindSearch() {
  if (settingsUI.searchBound) return;
  settingsUI.searchBound = true;
  document.addEventListener('keydown', e => {
    if (!(e.key === 'k' || e.key === 'K' || e.key === 'л' || e.key === 'Л')) return;
    if (!(e.metaKey || e.ctrlKey)) return;
    if (state.view !== 'settings') return;
    const t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT')) return;
    if (!$('#modal-backdrop')?.classList.contains('hidden')) return;
    e.preventDefault();
    settingsSearchPalette();
  });
}
