/* ══════════════════════════════════════════════════════════════════════
   РАЗДЕЛ «НАСТРОЙКИ» — область с под-разделами.

   Реализация целевой информационной архитектуры из
   docs/SETTINGS-UI-PROPOSAL-2026-10-12.md (ред. 5): вместо одной длинной страницы
   из 8 панелей — под-навигация по группам («Расчёт», «Справочники объекта»,
   «Служебное»), hash-адрес каждого экрана (#/settings/pay), поиск (⌘K), экран
   «Обзор» со здоровьем конфигурации, формы вместо JSON и черновик версии
   справочников с diff и честным показом даты применения.

   Порядок экранов — по частоте обращений и цене ошибки, а не по порядку таблиц БД.
   Правила оплаты (то, что определяет деньги) — первый класс: карточки модификаторов,
   переопределения, мастер «что → кому → когда» и «Проверитель», который объясняет
   значение для (сотрудник, день) тем же доменным приоритетом 1–7, что и расчёт.

   Зависит от core.js ($, api, state, esc, openModal, toast, …), app.js (can,
   renderDicts, refreshDoublePay, shiftModal, openKindModal, loadDirectory,
   DEFAULT_TITLES, fmtGdValue) и section_v4.js (renderEngineSettings — режим эксперта).
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
};

/* Состав раздела. `external` — переход в самостоятельную вкладку приложения
   (права и аудит не дублируются: у них свои разделы и свои права). */
const SETTINGS_SCREENS = [
  { group: 'Расчёт' },
  { id: 'overview', title: 'Обзор', icon: 'home', render: settingsScreenOverview },
  { id: 'calc', title: 'Расчёт', icon: 'calc', render: settingsScreenCalc, edit: true },
  { id: 'pay', title: 'Правила оплаты', icon: 'money', render: settingsScreenPay },
  { id: 'codes', title: 'Коды Табеля', icon: 'codes', render: settingsScreenCodes, edit: true },
  { id: 'groups', title: 'Группы и графики', icon: 'people', render: settingsScreenGroups, edit: true },
  { id: 'calendar', title: 'Календарь правил', icon: 'cal', render: settingsScreenCalendar },
  { group: 'Справочники объекта' },
  { id: 'shifts', title: 'Смены и отсутствия', icon: 'shift', render: settingsScreenShifts, edit: true },
  { id: 'docs', title: 'Документы и справочники', icon: 'doc', render: settingsScreenDocs, edit: true },
  { group: 'Служебное' },
  { id: 'system', title: 'Система', icon: 'gear', render: settingsScreenSystem },
  { id: 'expert', title: 'Режим эксперта (JSON)', icon: 'code', render: settingsScreenExpert, edit: true },
  { id: 'access', title: 'Права доступа', icon: 'shield', external: 'access', perm: 'access.manage' },
  { id: 'audit', title: 'Журнал аудита', icon: 'list', external: 'audit', perm: 'audit.view' },
];
const SETTINGS_IDS = SETTINGS_SCREENS.filter(s => s.id && !s.external).map(s => s.id);
const SETTINGS_TITLES = Object.fromEntries(SETTINGS_SCREENS.filter(s => s.id).map(s => [s.id, s.title]));

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
async function loadSettings() {
  const host = $('#view-settings');
  if (!host) return;
  host.innerHTML = '<div class="empty">Загрузка…</div>';
  try {
    settingsUI.data = await api('/api/settings');
  } catch (e) { settingsFail(host, e); return; }

  const fromHash = (location.hash.match(/^#\/settings\/([a-z-]+)/) || [])[1];
  const screen = SETTINGS_IDS.includes(fromHash) ? fromHash
    : (SETTINGS_IDS.includes(settingsUI.screen) ? settingsUI.screen : 'overview');
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
  nav.innerHTML = SETTINGS_SCREENS.filter(x => !x.perm || can(x.perm)).map(item => {
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
  const item = SETTINGS_SCREENS.find(s => s.id === id);
  if (!item) return;
  if (item.external) { navigate(item.external); return; }
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

async function settingsRenderScreen() {
  const body = $('#st-body');
  if (!body) return;
  const item = SETTINGS_SCREENS.find(s => s.id === settingsUI.screen) || SETTINGS_SCREENS[1];
  settingsUI.screen = item.id;
  if (history.replaceState) history.replaceState(null, '', `#/settings/${item.id}`);
  $$('#st-nav [data-st]').forEach(b => b.classList.toggle('active', b.dataset.st === item.id));
  body.innerHTML = '<div class="empty">Загрузка…</div>';
  body.scrollTop = 0;
  try {
    await item.render(body);
  } catch (e) {
    console.error('экран настроек', item.id, e);
    settingsFail(body, e);
  }
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
          rows.push(['Последний закрытый период', applies <= lastClosed
            ? `<b style="color:var(--warn)">начинается ${dateRu(lastClosed)} — нужен явный пересчёт в «Управленческом табеле»</b>`
            : `начинается ${dateRu(lastClosed)} — не затрагивается`]);
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
            valid_from: from.value, payload: settingsUI.draft, note: note.value.trim() } });
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
      <button data-go="${esc(c.screen)}">${esc(SETTINGS_TITLES[c.screen] || c.screen)} →</button></li>`).join('')}
      ${checks.length > 12 ? `<li><span>… и ещё ${checks.length - 12}</span></li>` : ''}</ul></div>`;
}
function settingsBindHealth(host) {
  $$('[data-go]', host).forEach(b => b.onclick = () => settingsGo(b.dataset.go));
}

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «ОБЗОР» — паспорт объекта: что действует, здорово ли, что вступит в силу
   ══════════════════════════════════════════════════════════════════════ */
async function settingsScreenOverview(host) {
  const [health, engine] = await Promise.all([settingsHealth(), settingsEngine()]);
  const v = health?.version || {};
  const s = health?.stats || {};
  const p = engine?.active?.payload || {};
  const upcoming = health?.upcoming || [];
  const recent = health?.recent || [];

  host.innerHTML = `
    ${settingsHead('Обзор', 'Что действует сейчас, здорова ли конфигурация и что вступит в силу — одним экраном.',
      `<button class="btn btn-sm" id="ov-versions">История версий</button>
       <button class="btn btn-sm" id="ov-compare">Сравнить с предыдущей</button>
       <button class="btn btn-sm btn-primary" id="ov-expert">Режим эксперта</button>`)}
    ${settingsPanel('', `
      <div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap">
        <div style="flex:1;min-width:260px">
          <div class="panel-title" style="margin-bottom:6px">Действующая версия справочников</div>
          <div style="font-family:var(--font-display);font-size:21px">
            ${v.id ? `#${v.id} · действует с ${esc(dateRu(v.valid_from))}` : 'справочники по умолчанию (версий нет)'}</div>
          <div class="hint" style="margin-top:4px">${esc(v.created_by || '—')}${v.created_at
            ? ` · ${esc(v.created_at.replace('T', ' ').slice(0, 16))}` : ''}${v.note ? ` · «${esc(v.note)}»` : ''}</div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn btn-sm" id="ov-calc">Каркас расчёта</button>
          <button class="btn btn-sm" id="ov-system">Версии и откат</button>
        </div>
      </div>`)}
    ${settingsHealthBanner(health)}
    <div class="stat-grid">
      <div class="stat"><div class="k">Шаг расчёта</div><div class="v">${s.step_minutes ?? '—'} <small>мин</small></div></div>
      <div class="stat info"><div class="k">Период</div><div class="v" style="font-size:19px">${esc(s.period_granularity === 'half_month' ? 'полмесяца' : 'месяц')}</div></div>
      <div class="stat"><div class="k">Лимит опоздания</div><div class="v">${s.late_limit_minutes ?? '—'} <small>мин</small></div></div>
      <div class="stat"><div class="k">Кодов Табеля</div><div class="v">${s.codes ?? 0}</div></div>
      <div class="stat"><div class="k">Окон (значений)</div><div class="v">${s.windows ?? 0}</div></div>
      <div class="stat ${s.rules_active ? 'warn' : ''}"><div class="k">Переопределений в месяце</div><div class="v">${s.rules_active ?? 0}</div></div>
    </div>
    <div class="grid-2">
      ${settingsPanel('Вступит в силу', upcoming.length
        ? upcoming.map(u => `<div class="kv"><span class="k">${esc(dateRu(u.date))} · ${esc(u.kind === 'version' ? 'версия' : 'правило')}</span>
            <span class="v" style="text-align:left;font-weight:600">${esc(u.text)}
              <button class="btn btn-sm btn-ghost" data-go="${esc(u.screen)}">открыть</button></span></div>`).join('')
        : '<p class="hint" style="margin:0">Правил и версий на будущее нет. Здесь видно всё, что вступит после сегодняшнего дня — «я не помню, что уже задал» больше не проблема.</p>')}
      ${settingsPanel('Изменения за 30 дней', recent.length
        ? recent.map(r => `<div class="kv"><span class="k">${esc((r.ts || '').replace('T', ' ').slice(0, 16))} · ${esc(r.actor || '—')}</span>
            <span class="v" style="text-align:left;font-weight:600">${esc(r.action)} · ${esc(r.target)}</span></div>`).join('')
          + '<div style="margin-top:10px"><button class="btn btn-sm btn-ghost" data-go="audit">Весь журнал аудита →</button></div>'
        : '<p class="hint" style="margin:0">За последние 30 дней настройки не менялись.</p>')}
    </div>
    ${settingsPanel('Что включено сейчас', `
      <div class="grid-2">
        <div>${SETTINGS_MODS.filter(m => m.name !== 'counts_in_ut').map(m => `
          <div class="kv"><span class="k">${esc(m.title)}</span>
            <span class="v">${esc(fmtGdValue(m.name, (s.global_defaults || {})[m.name]))}
              <span class="badge muted">глобально</span></span></div>`).join('')}
          <div class="kv"><span class="k">Учитываются ли часы в УТ</span>
            <span class="v">по коду дня <button class="btn btn-sm btn-ghost" data-go="codes">коды →</button></span></div>
        </div>
        <div>
          <div class="kv"><span class="k">Часовой пояс</span><span class="v">${esc(s.tz || p.tz || '—')}</span></div>
          <div class="kv"><span class="k">Каскад гашения</span><span class="v" style="font-weight:600">банк → ${esc((p.cascade_order || []).join(' → '))}</span></div>
          <div class="kv"><span class="k">Порядок размещения</span><span class="v" style="font-weight:600">${esc((p.placement_order || []).join(' → '))}</span></div>
          <div class="kv"><span class="k">Группы</span><span class="v" style="font-weight:600">${esc((p.groups || []).join(', '))}</span></div>
        </div>
      </div>`)}
    ${settingsPanel('Быстрые действия', `
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        ${can('settings.edit') ? '<button class="btn btn-sm" id="ov-wizard">+ Переопределение правила</button>' : ''}
        <button class="btn btn-sm" id="ov-resolve">Проверить значение для дня</button>
        ${can('settings.edit') ? '<button class="btn btn-sm" id="ov-code">+ Код Табеля</button>' : ''}
        ${can('settings.edit') ? '<button class="btn btn-sm" id="ov-window">+ Значение и окно</button>' : ''}
        <button class="btn btn-sm" data-go="calendar">Календарь правил</button>
        <button class="btn btn-sm btn-ghost" data-go="shifts">Словарь смен</button>
      </div>`)}
    ${settingsDraftBarHtml()}`;

  settingsBindHealth(host);
  settingsBindDraftBar(host);
  settingsOn('#ov-versions', host, () => settingsVersionsModal());
  settingsOn('#ov-compare', host, () => settingsCompareWithPrevious());
  settingsOn('#ov-expert', host, () => settingsGo('expert'));
  settingsOn('#ov-calc', host, () => settingsGo('calc'));
  settingsOn('#ov-system', host, () => settingsGo('system'));
  settingsOn('#ov-wizard', host, () => settingsWizard());
  settingsOn('#ov-resolve', host, () => settingsResolverModal());
  settingsOn('#ov-code', host, () => settingsCodeModal(null));
  settingsOn('#ov-window', host, () => settingsWindowModal(null));
}

async function settingsCompareWithPrevious() {
  const engine = await settingsEngine();
  const versions = engine?.versions || [];
  const current = versions.find(v => v.id === engine?.active?.id);
  const idx = versions.findIndex(v => v.id === current?.id);
  const prev = versions[idx + 1];
  if (!prev) return toast('Предыдущей версии нет — сравнивать не с чем', 'warn');
  try {
    const old = await api(`/api/engine-settings?on=${prev.valid_from}`, { silent: true });
    settingsDiffModal(old.active.payload, engine.active.payload,
      `Версия #${prev.id} → #${engine.active.id}`);
  } catch (e) { toast(e.message, 'err'); }
}

function settingsVersionsModal() {
  const versions = settingsUI.engine?.versions || [];
  const activeId = settingsUI.engine?.active?.id;
  openModal({
    title: 'История версий справочников', wide: true,
    subtitle: 'Версия выбирается по дате начала периода; закрытые периоды читаются из хранилища',
    body: versions.length ? `<div class="table-wrap"><table class="data"><thead><tr>
        <th>№</th><th>Действует с</th><th>Комментарий</th><th>Кто</th><th>Создана</th><th></th>
      </tr></thead><tbody>${versions.map(v => `<tr${v.id === activeId ? ' style="background:#f7f1ea"' : ''}>
        <td><b>#${v.id}</b>${v.id === activeId ? ' <span class="badge ok">действует</span>' : ''}</td>
        <td>${esc(dateRu(v.valid_from))}</td><td>${esc(v.note || '—')}</td>
        <td>${esc(v.created_by || '—')}</td><td>${esc((v.created_at || '').replace('T', ' ').slice(0, 16))}</td>
        <td class="num"><button class="btn btn-sm btn-ghost" data-ver="${v.id}">показать payload</button></td>
      </tr>`).join('')}</tbody></table></div>`
      : '<p class="hint">Версий нет: расчёт идёт по справочникам по умолчанию.</p>',
    footer: '<button class="btn btn-primary" data-ok>Закрыть</button>',
    onMount(m) {
      m.querySelector('[data-ok]').onclick = closeModal;
      $$('[data-ver]', m).forEach(b => b.onclick = async () => {
        const v = versions.find(x => x.id === +b.dataset.ver);
        try {
          const d = await api(`/api/engine-settings?on=${v.valid_from}`, { silent: true });
          openModal({ title: `Версия #${v.id} · payload`, wide: true,
            subtitle: `действует с ${dateRu(v.valid_from)}${v.note ? ` · ${v.note}` : ''}`,
            body: `<pre style="max-height:60vh;overflow:auto;background:#f8f5f1;border:1px solid var(--line);
              border-radius:6px;padding:12px;font-size:12px">${esc(JSON.stringify(d.active.payload, null, 2))}</pre>`,
            footer: '<button class="btn btn-primary" data-ok>Закрыть</button>',
            onMount(mm) { mm.querySelector('[data-ok]').onclick = closeModal; } });
        } catch (e) { toast(e.message, 'err'); }
      });
    },
  });
}

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «РАСЧЁТ» — лимит опоздания, каркас, категории, веса, порядки
   Три блока с РАЗНОЙ механикой вступления в силу (план §3.2).
   ══════════════════════════════════════════════════════════════════════ */
const SETTINGS_STEPS = [15, 30, 60];
const SETTINGS_TZ = ['Europe/Moscow', 'Europe/Simferopol', 'Europe/Kaliningrad', 'Europe/Samara',
  'Asia/Yekaterinburg', 'Asia/Novosibirsk', 'Asia/Krasnoyarsk', 'Asia/Irkutsk', 'Asia/Yakutsk',
  'Asia/Vladivostok', 'Asia/Magadan', 'Asia/Kamchatka'];

async function settingsScreenCalc(host) {
  const [engine, health] = await Promise.all([settingsEngine(), settingsHealth().catch(() => null)]);
  const p = settingsPayload();
  const d = settingsDraft();
  if (!p || !d) { host.innerHTML = '<div class="empty">Справочники не загружены</div>'; return; }
  const edit = can('settings.edit');
  const dayCat = (d.categories || []).find(c => c.code === 'ДЯ') || { start_minute: 360, end_minute: 1320 };
  const nightCat = (d.categories || []).find(c => c.code === 'ДН') || null;
  const tzList = [...new Set([d.tz, ...SETTINGS_TZ].filter(Boolean))];
  const applies = settingsAppliesFrom(todayISO(), d.period_granularity);

  host.innerHTML = `
    ${settingsHead('Расчёт',
      'Как считаются часы: лимит опоздания, период, шаг, часовояс, категории дня и ночи, веса кодов УТ и порядки каскада. Изменения публикуются версией справочников.',
      `<span class="chip">версия #${engine?.active?.id ?? '—'} · с ${esc(dateRu(engine?.active?.valid_from))}</span>`)}
    ${settingsPanel('А · Лимит опоздания', `
      <div style="display:flex;gap:14px;align-items:flex-end;flex-wrap:wrap">
        <label class="field" style="margin:0;width:170px"><span>Минут, после которых ставится флаг</span>
          <input type="number" id="cl-late" min="0" max="240" step="1" value="${Number(d.late_limit_minutes) || 0}" ${edit ? '' : 'disabled'}></label>
        <div class="hint" style="margin:0;flex:1;min-width:240px">До какой задержки флаг <code>LATE</code> не ставится;
          тот же лимит применяется к раннему уходу (<code>EARLY_DEPARTURE</code>). Норма: CFG-LIMITS, 6.6.</div>
      </div>
      <p class="hint">Сейчас лимит — поле версии справочников, поэтому меняется вместе с публикацией
        (применится к периодам с <b>${esc(dateRu(applies))}</b>). Значение «с сегодняшнего дня» для группы
        или сотрудника появится, когда лимит станет правилом CFG-MODIFIERS (R41, этап 1б плана) —
        версия справочников выбирается по дате <b>начала периода</b>, а не подневно.</p>`,
      '')}
    ${settingsPanel('Б · Каркас расчёта — публикуется версией', `
      <div class="grid-2">
        <label class="field"><span>Часовой пояс объекта</span>
          <select id="cl-tz" ${edit ? '' : 'disabled'}>${tzList.map(t =>
            `<option value="${esc(t)}" ${t === d.tz ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select>
          <div class="hint">Должен совпадать с <code>APP_TZ</code> сервера. DST намеренно не поддерживается:
            локальные сутки = 1440 мин (R24)</div></label>
        <label class="field"><span>Период расчёта</span>
          <div class="seg" id="cl-gran" style="margin-top:4px">
            <button data-v="month" class="${d.period_granularity === 'month' ? 'active' : ''}" ${edit ? '' : 'disabled'}>месяц</button>
            <button data-v="half_month" class="${d.period_granularity === 'half_month' ? 'active' : ''}" ${edit ? '' : 'disabled'}>полмесяца</button></div>
          <div class="hint">Полмесяца = 1–15 / 16–конец. Определяет цепочку периодов и границу закрытия (R36)</div></label>
        <label class="field"><span>Шаг расчёта</span>
          <div class="seg" id="cl-step" style="margin-top:4px">${SETTINGS_STEPS.map(s =>
            `<button data-v="${s}" class="${Number(d.step_minutes) === s ? 'active' : ''}" ${edit ? '' : 'disabled'}>${s}</button>`).join('')}</div>
          <div class="hint">Округляются только моменты отметок и <code>now</code>; границы окон и категорий
            лежат на той же сетке (CHK-GRID)</div></label>
        <label class="field"><span>Лимит часов в дне</span>
          <input type="text" value="${Number(d.day_limit_minutes) || 1440} мин · фиксировано" readonly
            style="background:var(--panel-2)">
          <div class="hint">Ёмкость дня для переносов: лимит − длина окна − Σ размещённых кодов</div></label>
      </div>
      <div class="preview">
        <div class="row"><span class="k">Действующая версия</span><b>#${engine?.active?.id ?? '—'} · с ${esc(dateRu(engine?.active?.valid_from))}</b></div>
        <div class="row"><span class="k">Текущий период</span><b>${health?.periods?.current
          ? `${dateRu(health.periods.current.start)}–${dateRu(health.periods.current.end)}` : '—'}</b></div>
        <div class="row"><span class="k">Последний закрытый период</span><b>${health?.periods?.last_closed_start
          ? `начинается ${dateRu(health.periods.last_closed_start)} — доступен пересчёт` : 'закрытых периодов нет'}</b></div>
        <div class="row"><span class="k">Черновик применится</span><b>к периодам, начинающимся с ${esc(dateRu(applies))} (или позже — по дате публикации)</b></div>
      </div>`) }
    ${settingsPanel('В · Категории времени · CFG-CATEGORIES', `
      <div class="grid-2">
        <label class="field" style="margin:0"><span>Начало дневных часов (ДЯ)</span>
          <input type="time" id="cl-cat-start" value="${settingsHm(dayCat.start_minute)}" step="${(Number(d.step_minutes) || 15) * 60}" ${edit ? '' : 'disabled'}></label>
        <label class="field" style="margin:0"><span>Конец дневных часов (ДЯ)</span>
          <input type="time" id="cl-cat-end" value="${settingsHm(dayCat.end_minute)}" step="${(Number(d.step_minutes) || 15) * 60}" ${edit ? '' : 'disabled'}></label>
      </div>
      <p class="hint" style="margin-top:10px">Ночные (ДН) — дополнение суток:
        <b id="cl-night-text">${nightCat ? `${settingsHm(nightCat.start_minute)}–${settingsHm(nightCat.end_minute)}` : '—'}</b>.
        Две категории покрывают сутки целиком и не пересекаются (CHK-CATEGORIES-COVER);
        границы лежат на сетке шага (CHK-GRID). Дневные на полосе — зелёным.</p>
      <div id="cl-cat-timeline">${settingsTimeline([
        { label: 'ДЯ (день)', start: dayCat.start_minute, end: dayCat.end_minute, color: 'var(--accent)' },
        { label: 'ДН (ночь)', start: nightCat?.start_minute ?? dayCat.end_minute, end: nightCat?.end_minute ?? dayCat.start_minute, color: 'var(--navy)' },
      ])}</div>`) }
    ${settingsPanel('Г · Веса кодов УТ · CFG-WEIGHTS', `
      <p class="hint" style="margin:-4px 0 10px">Вес — множитель перевода часа в банк («две валюты», спека 4.1),
        а не признак двойного дня: <code>ДН = 2</code> даст двойное начисление в банк за ночные часы.
        Движок порождает только коды с весом 1 и 2 (<code>weight_of_day</code>), поэтому вес 3+ — мёртвая
        конфигурация, пока не добавлено правило R42.</p>
      <div class="table-wrap"><table class="data"><thead><tr>
        <th>Код УТ</th><th>Категория</th><th class="num">Вес</th><th>Смысл</th></tr></thead>
      <tbody>${Object.entries(d.weights || {}).map(([code, w]) => `<tr>
        <td>${settingsCodePill(code, d.day_code_policy)}</td>
        <td>${esc(code.replace(/2$/, ''))}</td>
        <td class="num"><input type="number" min="1" max="9" step="1" value="${Number(w) || 1}"
          data-weight="${esc(code)}" style="max-width:90px;text-align:right" ${edit ? '' : 'disabled'}></td>
        <td class="hint" style="margin:0">${Number(w) === 2 ? 'двойной тариф (ДЯ2/ДН2)' : 'одинарный тариф'}</td>
      </tr>`).join('')}</tbody></table></div>`) }
    ${settingsPanel('Д · Порядки · CFG-CASCADE и CFG-PLACEMENT', `
      <div class="opt-group-title">Каскад гашения недостачи и долга</div>
      <p class="hint" style="margin:0 0 8px">Банк часов гасит долг первым, далее — коды в этом порядке
        (CHK-CASCADE-FULL: все коды весов 1 и 2 должны присутствовать).</p>
      ${settingsOrderList('cascade', d.cascade_order || [], edit)}
      <div class="opt-group-title" style="margin-top:16px">Порядок размещения переработки по кодам</div>
      <p class="hint" style="margin:0 0 8px">Куда сначала кладутся часы переработки дня (CHK-PLACEMENT-FULL).</p>
      ${settingsOrderList('placement', d.placement_order || [], edit)}`) }
    ${settingsDraftBarHtml()}`;

  if (!edit) return;
  const touch = () => settingsUpdateDraftBars();
  $('#cl-late').onchange = e => { d.late_limit_minutes = Math.max(0, Number(e.target.value) || 0); touch(); };
  $('#cl-tz').onchange = e => { d.tz = e.target.value; touch(); };
  const seg = (sel, key, isNum) => $$(sel, host).forEach(b => b.onclick = () => {
    d[key] = isNum ? Number(b.dataset.v) : b.dataset.v;
    $$(sel, host).forEach(x => x.classList.toggle('active', x === b));
    if (key === 'period_granularity') {
      const ap = $('.preview .row:last-child b', host);
      if (ap) ap.textContent = `к периодам, начинающимся с ${dateRu(settingsAppliesFrom(todayISO(), d.period_granularity))} (или позже — по дате публикации)`;
    }
    touch();
  });
  seg('#cl-gran button', 'period_granularity', false);
  seg('#cl-step button', 'step_minutes', true);
  const catChange = () => {
    const s = settingsMin($('#cl-cat-start').value), e = settingsMin($('#cl-cat-end').value);
    if (s === null || e === null) return;
    d.categories = [{ code: 'ДЯ', start_minute: s, end_minute: e }, { code: 'ДН', start_minute: e, end_minute: s }];
    $('#cl-night-text').textContent = `${settingsHm(e)}–${settingsHm(s)}`;
    $('#cl-cat-timeline').innerHTML = settingsTimeline([
      { label: 'ДЯ (день)', start: s, end: e, color: 'var(--accent)' },
      { label: 'ДН (ночь)', start: e, end: s, color: 'var(--navy)' }]);
    touch();
  };
  $('#cl-cat-start').onchange = catChange;
  $('#cl-cat-end').onchange = catChange;
  $$('[data-weight]', host).forEach(i => i.onchange = () => {
    const v = Math.max(1, Math.round(Number(i.value) || 1));
    i.value = v; d.weights[i.dataset.weight] = v; touch();
  });
  settingsBindOrderList(host, 'cascade', d, touch);
  settingsBindOrderList(host, 'placement', d, touch);
  settingsBindDraftBar(host);
}

/* Полоса суток 00–24: окно или категория как процентная полоса; переход через
   полночь рисуется двумя кусками (ДН 22:00–06:00). */
function settingsTimeline(rows) {
  const pct = m => ((Number(m) || 0) / 1440) * 100;
  return `<div class="timeline">
    <div class="tl-scale">${[0, 4, 8, 12, 16, 20, 24].map(h => `<span>${h}</span>`).join('')}</div>
    ${rows.map(r => {
      const s = Number(r.start) || 0, e = Number(r.end) || 0;
      const bars = s < e
        ? [{ a: s, b: e }]
        : [{ a: s, b: 1440 }, { a: 0, b: e }];
      return `<div class="tl-row"><span class="lbl" title="${esc(r.label)}">${esc(r.label)}</span>
        <div class="tl-track">${bars.map(x => `<div class="tl-bar" style="left:${pct(x.a)}%;width:${Math.max(pct(x.b) - pct(x.a), 0)}%;background:${cssColor(r.color)}">
          ${x.b - x.a >= 120 ? esc(`${settingsHm(x.a)}–${settingsHm(x.b)}`) : ''}</div>`).join('')}</div></div>`;
    }).join('')}
  </div>`;
}

function settingsOrderList(key, order, edit) {
  return `<div class="order-list" data-order="${key}">${order.map((code, i) => `
    <span class="item${code === 'ДН2' || code === 'ДЯ2' ? '' : ''}">
      <span class="n">${i + 1}</span>${esc(code)}
      ${edit ? `<button data-move="${esc(code)}" data-dir="-1" ${i === 0 ? 'disabled' : ''} title="Раньше">‹</button>
      <button data-move="${esc(code)}" data-dir="1" ${i === order.length - 1 ? 'disabled' : ''} title="Позже">›</button>` : ''}
    </span>${i < order.length - 1 ? '<span class="arrow">→</span>' : ''}`).join('')}</div>`;
}
function settingsBindOrderList(host, key, draft, touch) {
  const field = key === 'cascade' ? 'cascade_order' : 'placement_order';
  $$(`[data-order="${key}"] [data-move]`, host).forEach(b => b.onclick = () => {
    const list = draft[field] || [];
    const i = list.indexOf(b.dataset.move);
    const j = i + Number(b.dataset.dir);
    if (i < 0 || j < 0 || j >= list.length) return;
    [list[i], list[j]] = [list[j], list[i]];
    draft[field] = list;
    const wrap = $(`[data-order="${key}"]`, host);
    if (wrap) wrap.outerHTML = settingsOrderList(key, list, true);
    settingsBindOrderList(host, key, draft, touch);
    touch();
  });
}

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «ПРАВИЛА ОПЛАТЫ» — четыре модификатора CFG-MODIFIERS как первый класс:
   глобальный дефолт, переопределения, мастер и «Проверитель»
   ══════════════════════════════════════════════════════════════════════ */
function settingsModValue(name, raw) {
  if (raw === null || raw === undefined || raw === '') return '—';
  if (name === 'plan_equals_fact') return { yes: 'Да', no: 'Нет', auto: 'Авто', 1: 'Да', 0: 'Нет' }[raw] || String(raw);
  return (raw === true || raw === 'true' || raw === '1' || raw === 1) ? 'Да' : 'Нет';
}
function settingsWhoText(m) {
  if (m.employee_id) {
    const e = (state.employees || []).find(x => x.id === m.employee_id);
    return e ? (e.short_name || e.full_name) : `сотрудник #${m.employee_id}`;
  }
  return m.group ? `группа «${m.group}»` : 'все сотрудники';
}
function settingsWhenText(m) {
  if (m.date) return dateRu(m.date);
  if (m.period_start) return `весь период с ${dateRu(m.period_start)}`;
  return '—';
}
function settingsLevelOf(f) {
  if (f.emp && !f.group && f.day) return 1;
  if (f.emp && !f.group && !f.day) return 2;
  if (!f.emp && f.group && f.day) return 3;
  if (!f.emp && f.group && !f.day) return 4;
  if (!f.emp && !f.group && f.day) return 5;
  return 6;
}

async function settingsScreenPay(host) {
  await settingsEngine();
  const p = settingsPayload();
  const d = settingsDraft();
  const gd = p?.global_defaults || {};
  const edit = can('settings.edit');
  const first = `${state.year}-${String(state.month).padStart(2, '0')}-01`;
  let mods = [];
  try {
    mods = await api(`/api/engine-settings/modifiers?year=${state.year}&month=${state.month}`, { silent: true });
  } catch (e) { mods = []; }
  const byMod = name => mods.filter(m => m.name === name);

  host.innerHTML = `
    ${settingsHead('Правила оплаты',
      'Четыре правила, которые определяют, попадут ли часы в УТ и по какому тарифу. Глобальное значение — уровень 7; переопределения на группу, сотрудника или день сильнее.',
      `<div class="month-nav"><button id="py-prev" aria-label="Предыдущий месяц">‹</button>
         <div class="label">${MONTHS[state.month - 1]} ${state.year}</div>
         <button id="py-next" aria-label="Следующий месяц">›</button></div>
       ${edit ? '<button class="btn btn-sm btn-primary" id="py-add">+ Переопределение</button>' : ''}
       <button class="btn btn-sm" id="py-resolve">Проверитель</button>`)}

    <div class="settings-list">
    ${SETTINGS_MODS.map(m => {
      const list = byMod(m.name);
      const draftVal = (d?.global_defaults || {})[m.name];
      const changed = m.name !== 'counts_in_ut' && String(gd[m.name]) !== String(draftVal);
      return `<div class="rule-card">
        <div class="rc-head">
          <h4>${esc(m.title)}</h4>
          ${settingsLevelBadge(7)}
          <span class="spacer"></span>
          ${m.name === 'counts_in_ut'
            ? `<span class="val-picker">по коду дня <button class="btn btn-sm btn-ghost" data-go="codes">коды Табеля →</button></span>`
            : m.type === 'tri'
              ? `<span class="val-picker">глобально
                  <select data-gd="${m.name}" ${edit ? '' : 'disabled'}>
                    ${[['no', 'Нет'], ['yes', 'Да'], ['auto', 'Авто (по коду Табеля)']].map(([v, t]) =>
                      `<option value="${v}" ${String(draftVal) === v ? 'selected' : ''}>${t}</option>`).join('')}
                  </select></span>`
              : `<span class="val-picker">глобально
                  <label class="switch"><input type="checkbox" data-gd="${m.name}"
                    ${draftVal ? 'checked' : ''} ${edit ? '' : 'disabled'}><span class="sl"></span></label>
                  <b>${esc(settingsModValue(m.name, draftVal))}</b></span>`}
          ${changed ? '<span class="badge warn">в черновике — не опубликовано</span>' : ''}
          <span class="badge ${list.length ? 'info' : 'muted'}">переопределений в месяце: ${list.length}</span>
        </div>
        <div class="rc-body">${esc(m.what)}<br><span class="spec-ref">Пример: ${esc(m.ex)}</span></div>
        <div class="rc-meta">
          <span>Норма: <b>${esc(m.spec)}</b></span>
          <span class="spacer"></span>
          ${edit ? `<button class="btn btn-sm" data-add="${m.name}">+ Переопределение</button>` : ''}
          <button class="btn btn-sm btn-ghost" data-check="${m.name}">Проверить для дня</button>
        </div>
        ${list.length ? `<div class="table-wrap" style="margin-top:10px"><table class="data"><thead><tr>
            <th>Значение</th><th>Кому</th><th>Когда</th><th>Уровень</th><th>Комментарий</th><th>Кто задал</th><th></th>
          </tr></thead><tbody>${list.map(x => `<tr>
            <td><b>${esc(settingsModValue(x.name, x.value))}</b></td>
            <td>${esc(settingsWhoText(x))}</td><td>${esc(settingsWhenText(x))}</td>
            <td>${settingsLevelBadge(settingsLevelOf({ emp: !!x.employee_id, group: !!x.group,
              day: !!x.date, period: !!x.period_start }))}</td>
            <td>${esc(x.note || '—')}</td><td>${esc(x.created_by || '—')}</td>
            <td class="num">${edit ? `<button class="btn btn-sm btn-ghost" data-del="${x.id}" title="Удалить переопределение">✕</button>` : ''}</td>
          </tr>`).join('')}</tbody></table></div>` : ''}
      </div>`;
    }).join('')}
    </div>

    ${settingsPanel('Как выбирается значение', `
      <p class="hint" style="margin:0 0 10px">Приоритет 1–7 (CFG-MODIFIERS, 3.5): первое совпадение
        сверху вниз и есть значение дня. Две записи одного уровня на один день — конфликт
        конфигурации (CHK-MODIFIER-CONFLICT): такое правило не сохраняется.</p>
      <div class="chain">${[1, 2, 3, 4, 5, 6, 7].map(lv => `${lv > 1 ? '<span class="arrow">→</span>' : ''}
        <span class="step">${settingsLevelBadge(lv)} ${esc(SETTINGS_LEVEL_FORMS[lv])}</span>`).join('')}</div>
      <p class="hint">Дни производственного календаря и ВИП-периоды подмешиваются как
        «Двойные переработки» автоматически — это уровни 5/6 и 1/2, а не отдельные сущности.
        «План=Факт = Авто» разрешается в «Да» только колонкой кода Табеля (R19, стартово у «К»).</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn btn-sm" data-go="calendar">Календарь правил</button>
        <button class="btn btn-sm btn-ghost" id="py-resolve2">Проверитель: какое значение подействовало</button>
      </div>`)}
    ${settingsDraftBarHtml()}`;

  settingsBindHealth(host);
  settingsBindDraftBar(host);
  const shiftMonth = delta => {
    let m = state.month + delta, y = state.year;
    if (m < 1) { m = 12; y--; } if (m > 12) { m = 1; y++; }
    state.month = m; state.year = y; settingsRenderScreen();
  };
  settingsOn('#py-prev', host, () => shiftMonth(-1));
  settingsOn('#py-next', host, () => shiftMonth(1));
  settingsOn('#py-add', host, () => settingsWizard());
  settingsOn('#py-resolve', host, () => settingsResolverModal());
  settingsOn('#py-resolve2', host, () => settingsResolverModal());
  $$('[data-add]', host).forEach(b => b.onclick = () => settingsWizard(b.dataset.add));
  $$('[data-check]', host).forEach(b => b.onclick = () => settingsResolverModal(b.dataset.check));
  $$('[data-del]', host).forEach(b => b.onclick = () => confirmDialog('Удалить переопределение?',
    'Значение дня вернётся к более слабому уровню приоритета (вплоть до глобального). Затронутые дни табеля пересчитаются.',
    async () => {
      try {
        await api(`/api/engine-settings/modifiers/${b.dataset.del}`, { method: 'DELETE' });
        toast('Переопределение удалено', 'ok');
        await settingsRefresh();
      } catch (e) { toast(e.message, 'err'); }
    }, 'Удалить'));
  if (edit) {
    $$('[data-gd]', host).forEach(el => {
      const apply = () => {
        const draft = settingsDraft();
        draft.global_defaults = { ...(draft.global_defaults || {}) };
        const name = el.dataset.gd;
        const val = el.type === 'checkbox' ? el.checked : el.value;
        draft.global_defaults[name] = name === 'plan_equals_fact' ? val : val;
        settingsUpdateDraftBars();
        const b = el.closest('.val-picker')?.querySelector('b');
        if (b) b.textContent = settingsModValue(name, val);
        const badge = el.closest('.rc-head')?.querySelector('.badge.warn');
        if (!badge) {
          const chip = document.createElement('span');
          chip.className = 'badge warn';
          chip.textContent = 'в черновике — не опубликовано';
          el.closest('.rc-head')?.appendChild(chip);
        }
      };
      if (el.type === 'checkbox') el.onchange = apply; else el.onchange = apply;
    });
  }
  void first;
}

/* ── мастер «что → кому → когда» ── */
function settingsWizard(modName) {
  const p = settingsPayload();
  const groups = p?.groups || [];
  const emps = (state.employees || []).slice().sort((a, b) =>
    (a.full_name || '').localeCompare(b.full_name || '', 'ru'));
  openModal({
    title: 'Переопределение правила', wide: true,
    subtitle: 'Что меняем → кому → когда. Уровень приоритета считается по форме области',
    body: `
      <div class="wizard-steps">
        <div class="ws on"><b>1 · Что</b>правило и значение</div>
        <div class="ws on"><b>2 · Кому</b>все, группа или сотрудник</div>
        <div class="ws on"><b>3 · Когда</b>день или период</div>
      </div>
      <div class="grid-2">
        <label class="field"><span>Правило</span><select id="wz-name">
          ${SETTINGS_MODS.filter(m => m.name !== 'counts_in_ut' || true).map(m =>
            `<option value="${m.name}" ${m.name === modName ? 'selected' : ''}>${esc(m.title)}</option>`).join('')}
        </select></label>
        <label class="field"><span>Значение</span><select id="wz-value"></select></label>
        <label class="field"><span>Кому</span><select id="wz-scope">
          <option value="all">все сотрудники</option>
          ${groups.map(g => `<option value="g:${esc(g)}">группа «${esc(g)}»</option>`).join('')}
          ${emps.map(e => `<option value="e:${e.id}">${esc(e.short_name || e.full_name)}${e.group ? ` · ${esc(e.group)}` : ''}</option>`).join('')}
        </select></label>
        <label class="field"><span>Когда</span><select id="wz-when">
          <option value="day">один день</option>
          <option value="period" selected>весь период (месяц)</option>
        </select></label>
        <label class="field"><span>Дата / начало периода</span>
          <input type="date" id="wz-date" value="${todayISO()}"></label>
        <label class="field"><span>Комментарий</span><input type="text" id="wz-note"
          placeholder="например: по письму C&amp;B от 12.10"></label>
      </div>
      <div class="preview" id="wz-preview"></div>
      <p class="hint">Диапазон «с 10.10 по 20.10» и правило «с даты и далее» появятся, когда у записей
        CFG-MODIFIERS будет конец периода (этап 4 плана): сейчас запись действует либо один день,
        либо весь период. Конфликт с существующим правилом того же уровня сервер не сохранит (409).</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-save>Сохранить правило</button>`,
    onMount(m) {
      const nameSel = m.querySelector('#wz-name'), valSel = m.querySelector('#wz-value');
      const scopeSel = m.querySelector('#wz-scope'), whenSel = m.querySelector('#wz-when');
      const dateInp = m.querySelector('#wz-date'), noteInp = m.querySelector('#wz-note');
      const preview = m.querySelector('#wz-preview');
      const fillValues = () => {
        const n = nameSel.value;
        valSel.innerHTML = n === 'plan_equals_fact'
          ? '<option value="0">Нет</option><option value="1">Да</option><option value="auto">Авто (по коду Табеля)</option>'
          : '<option value="1">Да</option><option value="0">Нет</option>';
      };
      const render = () => {
        const n = nameSel.value;
        const title = (SETTINGS_MODS.find(x => x.name === n) || {}).title || n;
        const scope = scopeSel.value;
        const who = scope === 'all' ? 'все сотрудники'
          : scope.startsWith('g:') ? `группа «${scope.slice(2)}»`
            : ((emps.find(e => e.id === +scope.slice(2)) || {}).full_name || scope);
        const when = whenSel.value === 'day' ? dateInp.value
          : `${dateInp.value.slice(0, 7)}-01`;
        const level = settingsLevelOf({ emp: scope.startsWith('e:'), group: scope.startsWith('g:'),
          day: whenSel.value === 'day', period: whenSel.value !== 'day' });
        preview.innerHTML = `
          <div class="row"><span class="k">Правило</span><b>${esc(title)}</b></div>
          <div class="row"><span class="k">Значение</span><b>${esc(settingsModValue(n, valSel.value))}</b></div>
          <div class="row"><span class="k">Область</span><b>${esc(who)}</b></div>
          <div class="row"><span class="k">Действует</span><b>${whenSel.value === 'day'
            ? esc(dateRu(when)) : `весь период с ${esc(dateRu(when))}`}</b></div>
          <div class="row"><span class="k">Уровень приоритета</span>
            <b>${settingsLevelBadge(level)} ${esc(SETTINGS_LEVEL_FORMS[level])}</b></div>`;
        return { n, when };
      };
      fillValues();
      [nameSel, scopeSel, whenSel, dateInp].forEach(el => el.onchange = () => { if (el === nameSel) fillValues(); render(); });
      valSel.onchange = render;
      render();
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        const scope = scopeSel.value;
        const day = whenSel.value === 'day' ? dateInp.value : null;
        const periodStart = day ? null : `${dateInp.value.slice(0, 7)}-01`;
        if (!day && !periodStart) return toast('Укажите дату', 'warn');
        const body = { name: nameSel.value, value: valSel.value, note: noteInp.value.trim(),
          date: day, period_start: periodStart,
          employee_id: scope.startsWith('e:') ? +scope.slice(2) : null,
          group: scope.startsWith('g:') ? scope.slice(2) : '' };
        try {
          await api('/api/engine-settings/modifiers', { method: 'POST', body });
          closeModal(); toast('Правило сохранено — затронутые дни пересчитаны', 'ok');
          await settingsRefresh();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ── «Проверитель»: какое значение подействовало для (сотрудник, день) и почему ── */
function settingsResolverModal(modName) {
  const emps = (state.employees || []).slice().sort((a, b) =>
    (a.full_name || '').localeCompare(b.full_name || '', 'ru'));
  openModal({
    title: 'Проверитель правил', wide: true,
    subtitle: 'Какое значение подействовало для сотрудника в конкретный день и на каком уровне приоритета',
    body: `
      <div class="grid-2">
        <label class="field" style="margin:0"><span>Сотрудник</span><select id="rs-emp">
          ${emps.map(e => `<option value="${e.id}">${esc(e.full_name)}${e.group ? ` · ${esc(e.group)}` : ''}</option>`).join('')}
        </select></label>
        <label class="field" style="margin:0"><span>День</span>
          <input type="date" id="rs-date" value="${todayISO()}"></label>
      </div>
      <div style="margin:12px 0"><button class="btn btn-primary btn-sm" id="rs-go">Проверить</button></div>
      <div id="rs-out"><p class="hint">Ответ приходит с сервера: приоритет 1–7 считает домен —
        тот же код, что и расчёт (<code>resolve_modifier_trace</code>), поэтому «Проверитель» не может
        разойтись с табелем.</p></div>`,
    footer: '<button class="btn btn-ghost" data-close>Закрыть</button>',
    onMount(m) {
      m.querySelector('[data-close]').onclick = closeModal;
      const out = m.querySelector('#rs-out');
      const run = async () => {
        const emp = m.querySelector('#rs-emp').value, date = m.querySelector('#rs-date').value;
        if (!emp || !date) return;
        out.innerHTML = '<div class="empty">Проверяем…</div>';
        try {
          const r = await api(`/api/engine-settings/rules/resolve?employee_id=${encodeURIComponent(emp)}&date=${date}`,
            { silent: true });
          out.innerHTML = `
            <div class="preview" style="margin-bottom:12px">
              <div class="row"><span class="k">Сотрудник</span><b>${esc(r.employee.full_name)} · группа «${esc(r.employee.group)}»</b></div>
              <div class="row"><span class="k">День</span><b>${esc(dateRu(r.date))}${r.code
                ? ` · код Табеля ${esc(r.code)}${r.plan_minutes ? ` · план строки ${settingsHoursText(r.plan_minutes)}` : ''}`
                : ' · строки в Табеле нет'}</b></div>
              <div class="row"><span class="k">Период</span><b>${esc(dateRu(r.period.start))}–${esc(dateRu(r.period.end))}
                (${esc(r.period.granularity === 'half_month' ? 'полмесяца' : 'месяц')})</b></div>
              <div class="row"><span class="k">Версия справочников</span><b>${r.version?.id ? '#' + r.version.id : 'по умолчанию'}</b></div>
            </div>
            ${r.modifiers.filter(x => !modName || x.name === modName).map(x => `
              <div class="rule-card">
                <div class="rc-head"><h4>${esc(x.title)}</h4>
                  <span class="badge ${x.value === '1' ? 'ok' : x.value === '0' ? 'muted' : 'info'}">${esc(x.text)}</span>
                  ${x.level ? settingsLevelBadge(x.level) : ''}
                  <span class="spacer"></span>
                  ${modName ? `<button class="btn btn-sm btn-ghost" data-all>показать все правила</button>` : ''}</div>
                <div class="rc-body">${esc(x.source.text)}${x.scope ? ` · область: ${esc(x.scope)}` : ''}</div>
                ${x.chain.length ? `<div style="margin-top:10px">${settingsChainHtml(x.chain)}</div>` : ''}
              </div>`).join('')}`;
          const all = out.querySelector('[data-all]');
          if (all) all.onclick = () => { const d = m.querySelector('#rs-date').value; modName = null; run(); void d; };
        } catch (e) {
          out.innerHTML = `<div class="panel"><div class="empty">${esc(e.message || e)}</div></div>`;
        }
      };
      m.querySelector('#rs-go').onclick = run;
      if (emps.length) run();
    },
  });
}

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «КОДЫ ТАБЕЛЯ» — нормы расчёта (CFG-DAY-CODES, CFG-WINDOWS).
   Словаря смен здесь НЕТ: это другой экран («Смены и отсутствия»), другая
   сущность и другое право (план, ред. 3, §3.4/§3.4б).
   ══════════════════════════════════════════════════════════════════════ */
const SETTINGS_CODE_FLAGS = [
  { key: 'carries_hours', title: 'Несёт часы', hint: 'Код задаёт план строки Табеля; план карточки = длина окна (R34)' },
  { key: 'accepts_ut', title: 'Принимает коды УТ', hint: 'В день с этим кодом можно разместить переработку/погашение' },
  { key: 'counts_in_ut', title: 'Учитывается в УТ', hint: 'Уровень 7 правила «Учитываются ли часы в УТ» (CHK-DEFAULTS)' },
  { key: 'plan_equals_fact_auto', title: '«План=Факт» = Авто', hint: 'Единственный источник, который разрешает «Авто» в «Да» (R19)' },
];

async function settingsScreenCodes(host) {
  await settingsEngine();
  if (!state.docKinds) {
    /* виды заявлений — для «Заявление по назначению кода» в карточке кода (16.10.2026) */
    try {
      const di = await api('/api/docs/kinds', { silent: true });
      state.docKinds = di.kinds || []; state.docPlaceholders = di.placeholders || {};
    } catch { state.docKinds = []; }
  }
  const p = settingsPayload();
  const d = settingsDraft();
  if (!p || !d) { host.innerHTML = '<div class="empty">Справочники не загружены</div>'; return; }
  const edit = can('settings.edit');
  const tab = settingsUI.codesTab || (settingsUI.codesTab = 'codes');
  const codes = Object.entries(d.day_code_policy || {});
  const windows = Object.entries(d.windows || {});
  const shifts = (state.shiftTypes || []);
  const step = Number(d.step_minutes) || 15;

  host.innerHTML = `
    ${settingsHead('Коды Табеля',
      'Нормы расчёта: какие коды бывают в Табеле, что они означают, какой у них режим отметок и заявление, и какие окна (значения) у них есть. Это не словарь смен — он на отдельном экране.',
      `<button class="btn btn-sm btn-ghost" data-go="shifts">Смены и отсутствия ↗</button>
       ${edit ? `<button class="btn btn-sm btn-primary" id="cd-add">${tab === 'codes' ? '+ Код Табеля' : '+ Значение и окно'}</button>` : ''}`)}
    <div class="tabs">
      <button data-tab="codes" class="${tab === 'codes' ? 'active' : ''}">Коды Табеля · ${codes.length}</button>
      <button data-tab="windows" class="${tab === 'windows' ? 'active' : ''}">Окна и значения · ${windows.length}</button>
    </div>
    <div id="cd-body">${tab === 'codes' ? settingsCodesCards(codes, windows, shifts, d, edit)
      : settingsWindowsTable(windows, codes, step, edit)}</div>
    ${settingsDraftBarHtml()}`;

  settingsBindHealth(host);
  settingsBindDraftBar(host);
  $$('[data-tab]', host).forEach(b => b.onclick = () => {
    settingsUI.codesTab = b.dataset.tab; settingsRenderScreen();
  });
  const add = $('#cd-add');
  if (add) add.onclick = () => (tab === 'codes' ? settingsCodeModal(null) : settingsWindowModal(null));
  settingsBindCodesBody(host, d, edit);
}

function settingsCodesCards(codes, windows, shifts, d, edit) {
  /* Карточка кода (решение владельца 16.10.2026): флаги — чекбоксы, режим отметок
     «Пришёл/Ушёл» — у кода, несущего часы, у кода без часов — заявление с выбором
     шаблона. Кнопки «Изменить» (модалка) и «✕» (удаление из черновика с серверной
     защитой при публикации). */
  const docKinds = state.docKinds || [];
  const docName = code => { const k = docKinds.find(x => x.code === code); return k ? k.name : code; };
  return `${settingsPanel('Коды Табеля · CFG-DAY-CODES', `
    <div class="code-cards">${codes.map(([code, row]) => {
      const win = windows.filter(([k]) => k.split(' ')[0] === code);
      const used = shifts.filter(s => s.tzh_code === code);
      const carries = !!row.carries_hours;
      return `<div class="code-card">
        <div class="cc-head">
          ${settingsCodePill(code, d.day_code_policy)}
          <div class="cc-name"><b>${esc(row.title || '—')}</b>
            <span class="hint" style="margin:0">${carries ? 'несёт часы' : 'часов не несёт'}</span></div>
          ${edit ? `<span class="cc-actions">
            <button class="btn btn-sm btn-ghost" data-cedit="${esc(code)}" title="Изменить карточку кода">Изменить</button>
            <button class="btn btn-sm btn-ghost" data-cdel="${esc(code)}" title="Удалить код из справочника">✕</button></span>` : ''}
        </div>
        <div class="cc-flags">${SETTINGS_CODE_FLAGS.map(f => `
          <label class="cc-flag" title="${esc(f.hint)}">
            <input type="checkbox" data-flag="${esc(code)}:${f.key}"
              ${row[f.key] ? 'checked' : ''} ${edit ? '' : 'disabled'}>
            <span>${esc(f.title)}</span></label>`).join('')}</div>
        <div class="cc-extra">${carries ? `
          <div class="opt-group-title" style="margin:0 0 4px">Отметки в день с этим кодом</div>
          <label class="cc-flag" title="Сервер не примет отметку, пока флаг снят">
            <input type="checkbox" data-punch="${esc(code)}:punch_in"
              ${row.punch_in !== false ? 'checked' : ''} ${edit ? '' : 'disabled'}>
            <span>«Пришёл на работу»</span></label>
          <label class="cc-flag" title="Сервер не примет отметку, пока флаг снят">
            <input type="checkbox" data-punch="${esc(code)}:punch_out"
              ${row.punch_out !== false ? 'checked' : ''} ${edit ? '' : 'disabled'}>
            <span>«Ушёл с работы»</span></label>`
          : `<div class="opt-group-title" style="margin:0 0 4px">Заявление по назначению кода</div>
            ${edit ? `<select data-doc="${esc(code)}" class="cc-doc">
              <option value="">— не печатать —</option>
              ${docKinds.filter(k => k.active !== false).map(k =>
                `<option value="${esc(k.code)}" ${row.doc_type === k.code ? 'selected' : ''}>${esc(k.name)}</option>`).join('')}
              ${row.doc_type && !docKinds.some(k => k.code === row.doc_type)
                ? `<option value="${esc(row.doc_type)}" selected>${esc(row.doc_type)} (вид удалён)</option>` : ''}
            </select>`
            : `<span class="hint" style="margin:0">${row.doc_type ? esc(docName(row.doc_type)) : 'не печатать'}</span>`}`}</div>
        <div class="cc-foot">
          <span>Окон: ${win.length
            ? `${win.length} <button class="btn btn-sm btn-ghost" data-winof="${esc(code)}">показать</button>`
            : '<span class="badge warn">нет</span>'}</span>
          <span>${used.length
            ? used.map(s => `<span class="chip" title="${esc(s.name)}">${esc(s.code)}</span>`).join(' ')
            : '<span class="badge muted">из Графика не ставится</span>'}</span>
        </div>
      </div>`;
    }).join('')}</div>
    <p class="hint">Флаги — то, как день считается: «Несёт часы» задаёт план строки, «Принимает коды УТ»
      разрешает разместить переработку, «Учитывается в УТ» — уровень 7 одноимённого правила,
      «План=Факт = Авто» — единственный источник, разрешающий «Авто» в «Да» (R19).
      Цвет и название — данные приложения (блок presentation версии), домен их не знает.</p>
    <p class="hint">Режим отметок и заявление — атрибуты карточки кода (16.10.2026): у кода с часами
      настраиваются кнопки «Пришёл на работу»/«Ушёл с работы» (сервер не примет отметку,
      пока флаг снят), у кода без часов — шаблон заявления, которым оформляется назначение.
      Отсутствие, у которого есть вид в словаре смен, дополнительно соблюдает режим этого вида.</p>
    <p class="hint"><b>Удаление кода</b> (✕) убирает его из черновика вместе с его значениями/окнами.
      Публикацию проверяет сервер: код, который стоит в Табеле или на который ссылается живой
      вид смены, удалить не получится — расчёт закрытых периодов сошёл бы с истории.
      Так из справочника изъяты «С» и «НВ» (12.10.2026) и «НБ» — артефакт старого
      наполнения (16.10.2026).</p>`)}
  ${settingsPanel('Связь словарей · справочно', `
    <p class="hint" style="margin:0">Единственная связь двух справочников — <code>shift_types.tzh_code</code>:
      код Табеля, который проставляется из ячейки Графика. Разрывы видны на экране «Обзор»
      (проверки APP-SHIFT-CODE и APP-CODE-NO-SHIFT). Документарному коду с «План=Факт = Авто»
      (R19) — например «К» (командировка) — вид смены не нужен: Табель первичен,
      График генерируется из Табеля.</p>
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px">
      ${shifts.filter(s => s.tzh_code).map(s => `<span class="chip">${esc(s.code)} → ${settingsCodePill(s.tzh_code, d.day_code_policy)}</span>`).join('')}
    </div>`)}`;
}

function settingsWindowsTable(windows, codes, step, edit) {
  const rows = windows.map(([key, w]) => {
    const code = key.split(' ')[0];
    const len = Number(w.end_minute) - Number(w.start_minute);
    return { key, code, w, len };
  }).sort((a, b) => a.code.localeCompare(b.code, 'ru') || a.w.start_minute - b.w.start_minute);
  return `${settingsPanel('Окна и значения · CFG-WINDOWS', `
    <div class="table-wrap"><table class="data responsive"><thead><tr>
      <th>Значение Табеля</th><th>Код</th><th>Окно</th><th class="num">Длина окна</th>
      <th>Часов в значении</th><th></th></tr></thead>
    <tbody>${rows.map(r => `<tr>
      <td data-label="Значение"><b>${esc(r.key)}</b></td>
      <td data-label="Код">${settingsCodePill(r.code, Object.fromEntries(codes))}</td>
      <td data-label="Окно" class="num">${esc(settingsHm(r.w.start_minute))}–${esc(settingsHm(r.w.end_minute))}</td>
      <td class="num" data-label="Длина">${esc(settingsHoursText(r.len))}</td>
      <td data-label="Часов">${esc(r.key.split(' ')[1] || '—')} <span class="hint" style="margin:0">зарплатный атрибут строки</span></td>
      <td class="num">${edit ? `<button class="btn btn-sm btn-ghost" data-win="${esc(r.key)}">Изменить</button>
        <button class="btn btn-sm btn-ghost" data-windel="${esc(r.key)}" title="Удалить значение">✕</button>` : ''}</td>
    </tr>`).join('') || '<tr><td colspan="6" class="empty">Окон нет — добавьте значение</td></tr>'}</tbody></table></div>
    <p class="hint">План карточки и недостача считаются от <b>окна</b>, а не от числа часов в значении:
      «Я 10,75» при окне 08:00–20:00 даёт план 12 ч, а часы значения — зарплатная норма строки
      (RUL-PLAN-BELOW-WINDOW, EX-51). Окно не пересекает полночь: смена через полночь оформляется
      одним значением в дне начала (CHK-WINDOW-BOUNDS).</p>`) }
  ${settingsPanel('Все окна на полосе суток · сетка = шаг ' + step + ' мин',
    settingsTimeline(rows.map(r => ({ label: r.key, start: r.w.start_minute, end: r.w.end_minute,
      color: settingsCodeColor(r.code, Object.fromEntries(codes)) }))))}`;
}

function settingsBindCodesBody(host, draft, edit) {
  if (!edit) {
    $$('[data-winof]', host).forEach(b => b.onclick = () => { settingsUI.codesTab = 'windows'; settingsRenderScreen(); });
    return;
  }
  const touch = () => settingsUpdateDraftBars();
  $$('[data-flag]', host).forEach(cb => cb.onchange = () => {
    const [code, flag] = cb.dataset.flag.split(':');
    draft.day_code_policy[code][flag] = cb.checked;
    /* «Несёт часы» переключает состав карточки: отметки (с часами) либо заявление
       (без часов) — перерисовываем экран, остальные флаги копятся молча */
    if (flag === 'carries_hours') settingsRenderScreen(); else touch();
  });
  $$('[data-punch]', host).forEach(cb => cb.onchange = () => {
    const [code, key] = cb.dataset.punch.split(':');
    draft.day_code_policy[code][key] = cb.checked; touch();
  });
  $$('[data-doc]', host).forEach(sel => sel.onchange = () => {
    draft.day_code_policy[sel.dataset.doc].doc_type = sel.value; touch();
  });
  $$('[data-cedit]', host).forEach(b => b.onclick = () => settingsCodeModal(b.dataset.cedit));
  $$('[data-cdel]', host).forEach(b => b.onclick = () => {
    const code = b.dataset.cdel;
    const row = draft.day_code_policy[code] || {};
    const winKeys = Object.keys(draft.windows || {}).filter(k => k.split(' ')[0] === code);
    confirmDialog('Удалить код Табеля?',
      `«${code}»${row.title ? ' (' + row.title + ')' : ''} исчезнет из справочника вместе со значениями/окнами: `
      + (winKeys.length ? winKeys.map(k => `«${k}»`).join(', ') : 'окон у кода нет')
      + '. При публикации сервер проверит: код, который стоит в Табеле или на который ссылается живая смена словаря, удалить не получится.',
      () => {
        delete draft.day_code_policy[code];
        winKeys.forEach(k => delete draft.windows[k]);
        toast('Код удалён из черновика — опубликуйте версию', 'ok');
        settingsRenderScreen();
      }, 'Удалить из черновика');
  });
  $$('[data-winof]', host).forEach(b => b.onclick = () => { settingsUI.codesTab = 'windows'; settingsRenderScreen(); });
  $$('[data-win]', host).forEach(b => b.onclick = () => settingsWindowModal(b.dataset.win));
  $$('[data-windel]', host).forEach(b => b.onclick = () => confirmDialog('Удалить значение Табеля?',
    `«${b.dataset.windel}» исчезнет из справочника вместе с окном. Строки Табеля с этим значением, которые уже сохранены, перестанут считаться (CHK-WINDOW-EXISTS) — сначала замените их в Табеле.`,
    () => {
      delete draft.windows[b.dataset.windel];
      toast('Значение удалено из черновика — опубликуйте версию', 'ok');
      settingsRenderScreen();
    }, 'Удалить из черновика'));
}

function settingsCodeModal(code) {
  const draft = settingsDraft();
  if (!draft) return;
  const isNew = !code;
  const row = isNew ? null : draft.day_code_policy[code];
  const docKinds = state.docKinds || [];
  openModal({
    title: isNew ? 'Новый код Табеля' : `Код «${code}»`,
    subtitle: 'Строка CFG-DAY-CODES: как день считается. Публикуется версией справочников',
    body: `
      <div class="grid-2">
        <label class="field"><span>Код (как в Т-13)</span>
          <input type="text" id="nc-code" value="${esc(code || '')}" ${isNew ? '' : 'readonly'} maxlength="4" placeholder="Я"></label>
        <label class="field"><span>Название</span>
          <input type="text" id="nc-title" value="${esc(row?.title || '')}" placeholder="Явка (дневная работа)"></label>
        <label class="field"><span>Цвет</span><input type="color" id="nc-color" value="${esc(row?.color || '#34a862')}" style="height:44px;padding:4px"></label>
      </div>
      ${SETTINGS_CODE_FLAGS.map(f => `<label style="display:flex;gap:9px;align-items:flex-start;font-size:13.5px;color:var(--muted);margin-bottom:8px">
        <input type="checkbox" id="nc-${f.key}" ${row?.[f.key] ? 'checked' : ''} style="width:17px;height:17px;accent-color:var(--primary);margin-top:2px">
        <span><b style="color:var(--text)">${esc(f.title)}</b><br><span class="hint" style="margin:0">${esc(f.hint)}</span></span></label>`).join('')}
      <div id="nc-punch-wrap" style="border-top:1px dashed var(--line);padding-top:10px;margin-bottom:10px">
        <div class="opt-group-title" style="margin:0 0 6px">Кнопки отметок в день с этим кодом</div>
        <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted);margin-bottom:6px">
          <input type="checkbox" id="nc-punch-in" ${row?.punch_in !== false ? 'checked' : ''} style="width:17px;height:17px;accent-color:var(--primary)">
          Разрешить «Пришёл на работу»</label>
        <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
          <input type="checkbox" id="nc-punch-out" ${row?.punch_out !== false ? 'checked' : ''} style="width:17px;height:17px;accent-color:var(--primary)">
          Разрешить «Ушёл с работы»</label>
        <div class="hint" style="margin-top:4px">Флаги соблюдает сервер: пока флаг снят, отметку принять нельзя
          (409 с текстом статуса), а кнопка в «Моих отметках» неактивна.</div>
      </div>
      <div id="nc-doc-wrap" style="border-top:1px dashed var(--line);padding-top:10px;margin-bottom:10px">
        <label class="field"><span>Заявление по назначению кода (шаблон)</span>
          <select id="nc-doc">
            <option value="">— не печатать —</option>
            ${docKinds.filter(k => k.active !== false).map(k => `<option value="${esc(k.code)}">${esc(k.name)}</option>`).join('')}
            ${row?.doc_type && !docKinds.some(k => k.code === row.doc_type)
              ? `<option value="${esc(row.doc_type)}" selected>${esc(row.doc_type)} (вид удалён — выберите другой)</option>` : ''}
          </select>
          <div class="hint" style="margin-top:2px">По этому шаблону печатается заявление, когда код назначен
            на период («Печать заявления» в Табеле и Графике). Виды и бланки — экран «Документы и справочники».</div></label>
      </div>
      <p class="hint">Код появится в Табеле после публикации версии. Окна (значения) кода настраиваются
        на вкладке «Окна и значения» — там же видно, что окно положено только коду, несущему часы.
        Чтобы код можно было поставить из Графика, нужен вид смены с этим кодом Табеля —
        экран «Смены и отсутствия».</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-save>${isNew ? 'Добавить в черновик' : 'Сохранить'}</button>`,
    onMount(m) {
      if (!isNew) m.querySelector('#nc-doc').value = row?.doc_type || '';
      /* «Пришёл/Ушёл» — у кода, несущего часы; заявление — у кода без часов
         (решение владельца 16.10.2026): блоки переключаются чекбоксом «Несёт часы» */
      const carriesBox = m.querySelector('#nc-carries_hours');
      const syncWraps = () => {
        const carries = carriesBox.checked;
        m.querySelector('#nc-punch-wrap').style.display = carries ? '' : 'none';
        m.querySelector('#nc-doc-wrap').style.display = carries ? 'none' : '';
      };
      carriesBox.onchange = syncWraps; syncWraps();
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = () => {
        const c = m.querySelector('#nc-code').value.trim().toUpperCase();
        if (!c) return toast('Введите код', 'warn');
        if (isNew && draft.day_code_policy[c]) return toast(`Код «${c}» уже есть в справочнике`, 'warn');
        const entry = { ...(draft.day_code_policy[c] || {}) };
        entry.title = m.querySelector('#nc-title').value.trim();
        entry.color = m.querySelector('#nc-color').value;
        SETTINGS_CODE_FLAGS.forEach(f => { entry[f.key] = m.querySelector(`#nc-${f.key}`).checked; });
        entry.punch_in = m.querySelector('#nc-punch-in').checked;
        entry.punch_out = m.querySelector('#nc-punch-out').checked;
        entry.doc_type = entry.carries_hours ? (entry.doc_type || '') : m.querySelector('#nc-doc').value;
        draft.day_code_policy = { ...draft.day_code_policy, [c]: entry };
        closeModal();
        toast(isNew ? `Код «${c}» добавлен в черновик` : `Код «${c}» обновлён в черновике`, 'ok');
        settingsUI.codesTab = 'codes';
        settingsRenderScreen();
      };
    },
  });
}

function settingsWindowModal(key) {
  const draft = settingsDraft();
  if (!draft) return;
  const isNew = !key;
  const w = isNew ? { start_minute: 480, end_minute: 1200 } : draft.windows[key];
  /* Стандартное окно и часы — только у кода, несущего часы (решение владельца
     16.10.2026): у кодов-отсутствий окна нет, день без часов не считается от окна.
     Прежнее значение можно открыть, даже если флаг у кода сняли (история). */
  const policy = draft.day_code_policy || {};
  const [curCode, curHours] = String(key || '').split(' ');
  const codes = Object.keys(policy).filter(c => policy[c].carries_hours || c === curCode);
  const step = Number(draft.step_minutes) || 15;
  openModal({
    title: isNew ? 'Новое значение и окно' : `Значение «${key}»`,
    subtitle: 'Строка CFG-WINDOWS: ключ «КОД ЧАСЫ» + окно в сутках. План карточки = длина окна',
    body: `
      <div class="grid-2">
        <label class="field"><span>Код Табеля</span><select id="nw-code" ${isNew ? '' : 'disabled'}>
          ${codes.map(c => `<option value="${esc(c)}" ${c === curCode ? 'selected' : ''}>${esc(c)}</option>`).join('')}
        </select></label>
        <label class="field"><span>Часов в значении (зарплатная норма)</span>
          <input type="text" id="nw-hours" value="${esc(curHours || '12')}" placeholder="12 / 10,75"
            list="nw-hours-list">
          <datalist id="nw-hours-list">${['12', '11', '10,75', '10', '9', '8'].map(h =>
            `<option value="${h}"></option>`).join('')}</datalist></label>
        <label class="field"><span>Начало окна</span>
          <input type="time" id="nw-start" value="${settingsHm(w.start_minute)}" step="${step * 60}"></label>
        <label class="field"><span>Конец окна</span>
          <input type="time" id="nw-end" value="${settingsHm(w.end_minute)}" step="${step * 60}"></label>
      </div>
      <div class="preview" id="nw-preview"></div>
      <p class="hint">В списке — только коды, несущие часы: стандартное окно и часы бывают лишь
        у рабочего дня (16.10.2026). Ключ значения канонический: <code>КОД ПРОБЕЛ ЧАСЫ</code>, часы — десятичной дробью
        через запятую (CHK-WINDOW-KEY). Окно не пересекает полночь (CHK-WINDOW-BOUNDS), границы лежат
        на сетке шага ${step} мин (CHK-GRID). Часов в значении может быть меньше длины окна —
        это зарплатная норма (RUL-PLAN-BELOW-WINDOW).</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-save>${isNew ? 'Добавить в черновик' : 'Сохранить'}</button>`,
    onMount(m) {
      const codeSel = m.querySelector('#nw-code'), hoursInp = m.querySelector('#nw-hours');
      const startInp = m.querySelector('#nw-start'), endInp = m.querySelector('#nw-end');
      const preview = m.querySelector('#nw-preview');
      const newKey = () => `${codeSel.value} ${hoursInp.value.trim().replace('.', ',')}`;
      const render = () => {
        const s = settingsSnap(settingsMin(startInp.value) ?? 0, step);
        const e = settingsSnap(settingsMin(endInp.value) ?? 0, step);
        const len = e - s;
        preview.innerHTML = `
          <div class="row"><span class="k">Значение Табеля</span><b>${esc(newKey())}</b></div>
          <div class="row"><span class="k">Окно</span><b>${esc(settingsHm(s))}–${esc(settingsHm(e))}</b></div>
          <div class="row"><span class="k">Длина окна = план карточки</span><b>${len > 0
            ? esc(settingsHoursText(len)) : '<span style="color:var(--danger)">конец должен быть позже начала</span>'}</b></div>`;
      };
      [codeSel, hoursInp, startInp, endInp].forEach(el => el.oninput = render);
      render();
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = () => {
        const k = newKey();
        const s = settingsSnap(settingsMin(startInp.value) ?? 0, step);
        const e = settingsSnap(settingsMin(endInp.value) ?? 0, step);
        if (!k.trim() || k.split(' ').length !== 2) return toast('Заполните код и часы значения', 'warn');
        if (!(e > s)) return toast('Конец окна должен быть позже начала: окно не пересекает полночь', 'warn');
        if (!draft.day_code_policy[k.split(' ')[0]]) return toast('Такого кода нет в справочнике — сначала добавьте код', 'warn');
        if (!draft.day_code_policy[k.split(' ')[0]].carries_hours) return toast('Окно положено только коду, который несёт часы', 'warn');
        if (isNew && draft.windows[k]) return toast(`Значение «${k}» уже есть`, 'warn');
        if (!isNew && k !== key) delete draft.windows[key];
        draft.windows = { ...draft.windows, [k]: { start_minute: s, end_minute: e } };
        closeModal();
        toast(`Значение «${k}» ${isNew ? 'добавлено' : 'обновлено'} в черновике`, 'ok');
        settingsUI.codesTab = 'windows';
        settingsRenderScreen();
      };
    },
  });
}

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «ГРУППЫ И ГРАФИКИ» — CFG-GROUPS + базовый цикл объекта
   ══════════════════════════════════════════════════════════════════════ */
async function settingsScreenGroups(host) {
  const [engine, health] = await Promise.all([settingsEngine(), settingsHealth().catch(() => null)]);
  const data = settingsUI.data || {};
  const d = settingsDraft();
  const edit = can('settings.edit');
  const emps = state.employees || [];
  const perGroup = {};
  emps.forEach(e => { const g = e.group || 'Другие смены'; perGroup[g] = (perGroup[g] || 0) + 1; });
  const workShifts = (state.shiftTypes || []).filter(x => x.kind === 'work');
  const base = data.base || {};
  const groupChecks = (health?.checks || []).filter(c => c.screen === 'groups');

  host.innerHTML = `
    ${settingsHead('Группы и графики',
      'Реестр групп CFG-GROUPS, базовый цикл объекта и то, как группы связаны с блоками смен. Группа сотрудника обязана быть в реестре (CHK-GROUP-EXISTS).',
      `<span class="chip">версия #${engine?.active?.id ?? '—'}</span>`)}
    ${groupChecks.length ? settingsHealthBanner({ ...health, checks: groupChecks }) : ''}
    ${settingsPanel('Группы · единый источник (CFG-GROUPS)', `
      <div class="table-wrap"><table class="data"><thead><tr>
        <th>Группа</th><th class="num">Сотрудников</th><th>Шаблон графика</th><th>Правил оплаты</th><th></th>
      </tr></thead><tbody>${(d?.groups || []).map(g => `<tr>
        <td><b>${esc(g)}</b></td>
        <td class="num">${perGroup[g] ?? 0}</td>
        <td>${esc(g === 'Смена 1' || g === 'Смена 2' ? `базовый цикл ${base.cycle || '2/2'}${g === 'Смена 2' && base.groups?.['Смена 2']?.invert !== false ? ' (противофаза)' : ''}`
          : g === 'Пятидневка' ? '5/2, выходные у каждого свои' : 'индивидуальный цикл или вручную')}</td>
        <td><span class="badge muted">см. «Календарь правил»</span></td>
        <td class="num">${edit ? `<button class="btn btn-sm btn-ghost" data-gdel="${esc(g)}" title="Исключить из реестра">✕</button>` : ''}</td>
      </tr>`).join('')}</tbody></table></div>
      ${edit ? `<div class="v4-filters" style="margin-top:10px">
        <label class="field"><span>Новая группа</span><input type="text" id="g-new" placeholder="например: Смена 3"></label>
        <button class="btn btn-sm" id="g-add">Добавить в черновик</button></div>` : ''}
      <p class="hint">Сотрудники, чьей группы нет в реестре:
        ${Object.keys(perGroup).filter(g => !(d?.groups || []).includes(g)).map(g =>
          `<span class="badge danger">${esc(g)} · ${perGroup[g]}</span>`).join(' ') || 'нет — реестр полный'}</p>`)}
    ${settingsPanel('Базовый цикл объекта · «Смена 1» и «Смена 2»', `
      <p class="hint" style="margin:-4px 0 12px">Задаётся один раз и действует на все месяцы вперёд и назад.
        Ручные ячейки Графика — исключения (отпуск, больничный, подмена) и перекрывают базовый цикл.
        Это данные приложения (таблица настроек), а не версия справочников — сохраняются сразу.</p>
      <div class="grid-2">
        <label class="field"><span>Цикл смен 1/2</span><select id="b-cycle" ${edit ? '' : 'disabled'}>
          ${['2/2', '3/3', '4/2', '4/3', '1/3'].map(c => `<option ${base.cycle === c ? 'selected' : ''}>${c}</option>`).join('')}
          <option value="custom" ${String(base.cycle || '').startsWith('custom') ? 'selected' : ''}>произвольный…</option>
        </select></label>
        <label class="field"><span>Опорная дата (день, когда Смена 1 рабочая)</span>
          <input type="date" id="b-anchor" value="${esc(base.anchor || '2024-01-01')}" ${edit ? '' : 'disabled'}></label>
        <label class="field hidden" id="b-cycle-wrap"><span>Произвольный цикл (Р/В)</span>
          <input type="text" id="b-cycle-custom" placeholder="РРВВВВРР"
            value="${esc(String(base.cycle || '').startsWith('custom') ? String(base.cycle).slice(7) : '')}" ${edit ? '' : 'disabled'}></label>
        <label class="field"><span>Смена блока «Смена 1»</span><select id="b-shift1" ${edit ? '' : 'disabled'}>
          ${workShifts.map(x => `<option value="${esc(x.code)}" ${base.groups?.['Смена 1']?.shift_code === x.code ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}
        </select></label>
        <label class="field"><span>Смена блока «Смена 2»</span><select id="b-shift2" ${edit ? '' : 'disabled'}>
          ${workShifts.map(x => `<option value="${esc(x.code)}" ${base.groups?.['Смена 2']?.shift_code === x.code ? 'selected' : ''}>${esc(x.name)}</option>`).join('')}
        </select></label>
      </div>
      <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
        <input type="checkbox" id="b-invert2" ${base.groups?.['Смена 2']?.invert !== false ? 'checked' : ''}
          style="width:17px;height:17px;accent-color:var(--primary)" ${edit ? '' : 'disabled'}>
        Смена 2 работает в противофазе со Сменой 1 (когда одни работают — другие отдыхают)
      </label>
      ${edit ? '<button class="btn btn-primary btn-sm" id="b-save" style="margin-top:10px">Сохранить базовый цикл</button>' : ''}`)}
    ${settingsPanel('Пятидневка и «Другие смены»', `
      <p class="hint" style="margin:0">Здесь не настраиваются. У «Пятидневки» выходные задаются для
        КАЖДОГО сотрудника индивидуально (Сотрудники → карточка → «Перевод в блок»: например у начальника
        вс/пн, у бэк-специалиста сб/вс). «Другие смены» — контейнер индивидуальных графиков: 3/3, 1/3,
        сутки через трое, произвольный цикл «custom:РРВВ» или ручное заполнение ячеек.</p>
      <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
        <button class="btn btn-sm btn-ghost" data-nav="employees">Карточки сотрудников ↗</button>
        <button class="btn btn-sm btn-ghost" data-nav="schedule">График ↗</button>
      </div>`)}
    ${settingsDraftBarHtml()}`;

  settingsBindHealth(host);
  settingsBindDraftBar(host);
  $$('[data-nav]', host).forEach(b => b.onclick = () => navigate(b.dataset.nav));
  if (!edit) return;
  $$('[data-gdel]', host).forEach(b => b.onclick = () => confirmDialog('Исключить группу из реестра?',
    `Группа «${b.dataset.gdel}» перестанет существовать для расчёта. Если в ней остались сотрудники, расчёт остановится (CHK-GROUP-EXISTS) — сначала переведите их.`,
    () => {
      d.groups = (d.groups || []).filter(g => g !== b.dataset.gdel);
      settingsRenderScreen();
    }, 'Исключить из черновика'));
  const addG = $('#g-add');
  if (addG) addG.onclick = () => {
    const name = $('#g-new').value.trim();
    if (!name) return toast('Введите название группы', 'warn');
    if ((d.groups || []).includes(name)) return toast('Такая группа уже есть', 'warn');
    d.groups = [...(d.groups || []), name];
    settingsRenderScreen();
  };
  const syncCycle = () => $('#b-cycle-wrap').classList.toggle('hidden', $('#b-cycle').value !== 'custom');
  $('#b-cycle').onchange = syncCycle; syncCycle();
  $('#b-save').onclick = async () => {
    const cycle = $('#b-cycle').value === 'custom' ? 'custom:' + $('#b-cycle-custom').value.trim() : $('#b-cycle').value;
    const body = { cycle, anchor: $('#b-anchor').value, groups: {
      'Смена 1': { shift_code: $('#b-shift1').value, invert: false },
      'Смена 2': { shift_code: $('#b-shift2').value, invert: $('#b-invert2').checked },
      'Пятидневка': base.groups?.['Пятидневка'] || { shift_code: 'DAY9', off_weekdays: [5, 6] },
    } };
    try {
      await api('/api/settings/base', { method: 'PUT', body });
      toast('Базовый цикл сохранён и действует на все месяцы', 'ok');
      await settingsRefresh();
    } catch (e) { toast(e.message, 'err'); }
  };
}

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «КАЛЕНДАРЬ ПРАВИЛ» — день × кто: слои переопределений, двойных дней,
   ВИП-периодов и версий справочников. Данные не сливаем — показываем слоями.
   ══════════════════════════════════════════════════════════════════════ */
async function settingsScreenCalendar(host) {
  const engine = await settingsEngine();
  const y = settingsUI.calYear || state.year, m = settingsUI.calMonth || state.month;
  const [mods, dp] = await Promise.all([
    api(`/api/engine-settings/modifiers?year=${y}&month=${m}`, { silent: true }).catch(() => []),
    api(`/api/doublepay?year=${y}`, { silent: true }).catch(() => ({ days: [], vip: [], scopes: [] })),
  ]);
  const marks = {};
  const add = (iso, key, text) => {
    if (!iso) return;
    marks[iso] = marks[iso] || { items: [] };
    marks[iso][key] = (marks[iso][key] || 0) + 1;
    marks[iso].items.push(text);
  };
  mods.forEach(x => {
    const iso = x.date || x.period_start;
    if (x.date) add(x.date, 'rule', `${x.title} = ${settingsModValue(x.name, x.value)} · ${settingsWhoText(x)}`);
    else if (x.period_start) add(x.period_start, 'rule', `${x.title} = ${settingsModValue(x.name, x.value)} · ${settingsWhoText(x)} · весь период`);
    void iso;
  });
  (dp.days || []).forEach(x => {
    const iso = `${y}-${String(x.month).padStart(2, '0')}-${String(x.day).padStart(2, '0')}`;
    add(iso, 'dbl', `день двойной оплаты (${x.scope_title || x.scope})${x.note ? ' · ' + x.note : ''}`);
  });
  (dp.vip || []).forEach(v => {
    const s = new Date(v.start_date + 'T12:00:00'), e = new Date(v.end_date + 'T12:00:00');
    for (let t = s; t <= e && t.getFullYear() === y; t.setDate(t.getDate() + 1)) {
      if (t.getMonth() + 1 !== m) continue;
      add(`${y}-${String(m).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`, 'vip',
        `ВИП: ${v.employee_full_name || v.employee_name}${v.note ? ' · ' + v.note : ''}`);
    }
  });
  (engine?.versions || []).forEach(v => add(v.valid_from, 'ver', `вступает версия справочников #${v.id}${v.note ? ' · ' + v.note : ''}`));

  host.innerHTML = `
    ${settingsHead('Календарь правил',
      'Один экран: какие правила действуют в конкретный день, откуда они взялись и что вступит в силу. Слои не сливаются — каждый источник виден отдельно.',
      `<div class="month-nav"><button id="cl-prev" aria-label="Предыдущий месяц">‹</button>
         <div class="label">${MONTHS[m - 1]} ${y}</div><button id="cl-next" aria-label="Следующий месяц">›</button></div>
       ${can('settings.edit') ? '<button class="btn btn-sm btn-primary" id="cl-add">+ Правило</button>' : ''}`)}
    ${settingsPanel('', `
      <table class="cal"><thead><tr>${WD_SHORT.map(w => `<th>${w}</th>`).join('')}</tr></thead>
      <tbody>${settingsCalRows(y, m, marks, settingsUI.calDay)}</tbody></table>
      <div class="cal-legend">
        <span><i class="mk rule" style="width:8px;height:8px;border-radius:99px;display:inline-block;background:#2c5f70"></i> переопределение правила</span>
        <span><i style="width:8px;height:8px;border-radius:99px;display:inline-block;background:#c0562f"></i> день двойной оплаты</span>
        <span><i style="width:8px;height:8px;border-radius:99px;display:inline-block;background:#6b3fa0"></i> ВИП-период</span>
        <span><i style="width:8px;height:8px;border-radius:99px;display:inline-block;background:var(--gold)"></i> версия справочников</span>
      </div>`)}
    <div id="cl-day">${settingsDayPanel(settingsUI.calDay, marks, mods, y, m)}</div>
    ${settingsPanel('Производственный календарь и ВИП-гости',
      '<div id="dp-body"><div class="empty">Загрузка…</div></div>')}
    <p class="hint">Массовые назначения («все субботы года», список дат из письма C&amp;B) — в форме выше:
      дни двойной оплаты подмешиваются в правила автоматически, отдельной сущности нет.</p>`;

  settingsOn('#cl-prev', host, () => { settingsUI.calMonth = m - 1 || 12; settingsUI.calYear = m - 1 ? y : y - 1; settingsUI.calDay = null; settingsRenderScreen(); });
  settingsOn('#cl-next', host, () => { settingsUI.calMonth = m + 1 > 12 ? 1 : m + 1; settingsUI.calYear = m + 1 > 12 ? y + 1 : y; settingsUI.calDay = null; settingsRenderScreen(); });
  settingsOn('#cl-add', host, () => settingsWizard());
  $$('[data-day]', host).forEach(td => td.onclick = () => {
    settingsUI.calDay = td.dataset.day;
    $('#cl-day').innerHTML = settingsDayPanel(settingsUI.calDay, marks, mods, y, m);
    $$('[data-day]', host).forEach(x => x.classList.toggle('sel', x.dataset.day === settingsUI.calDay));
    settingsBindDayPanel($('#cl-day'));
  });
  settingsBindDayPanel($('#cl-day'));
  refreshDoublePay();
}

function settingsCalRows(year, month, marks, selected) {
  const total = new Date(year, month, 0).getDate();
  const startWd = (new Date(year, month - 1, 1).getDay() + 6) % 7;
  const weeks = Math.ceil((startWd + total) / 7);
  let out = '', day = 1;
  for (let w = 0; w < weeks; w++) {
    out += '<tr>';
    for (let i = 0; i < 7; i++) {
      const idx = w * 7 + i;
      if (idx < startWd || day > total) { out += '<td class="cell out"></td>'; continue; }
      const iso = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const mk = marks[iso] || {};
      const wd = new Date(year, month - 1, day).getDay();
      out += `<td class="cell${wd === 0 || wd === 6 ? ' we' : ''}${iso === todayISO() ? ' today' : ''}${iso === selected ? ' sel' : ''}"
        data-day="${iso}" title="${esc((mk.items || []).join(' · '))}">
        <div>${day}</div><div class="marks">${['rule', 'dbl', 'vip', 'ver'].filter(k => mk[k])
          .map(k => `<span class="mk ${k}"></span>`).join('')}</div></td>`;
      day++;
    }
    out += '</tr>';
  }
  return out;
}

function settingsDayPanel(iso, marks, mods, year, month) {
  if (!iso) {
    return settingsPanel('День не выбран',
      '<p class="hint" style="margin:0">Кликните по дню календаря: покажем все правила, двойные дни, ВИП-периоды и версии, действующие в этот день, и дадим добавить правило прямо на него.</p>');
  }
  const mk = marks[iso] || {};
  const dayMods = mods.filter(x => x.date === iso || (x.period_start && x.period_start <= iso
    && iso <= `${year}-${String(month).padStart(2, '0')}-${String(new Date(year, month, 0).getDate()).padStart(2, '0')}`));
  return settingsPanel(`День ${dateRu(iso)}`, `
    ${(mk.items || []).length ? mk.items.map(t => `<div class="kv"><span class="v" style="text-align:left;font-weight:600">${esc(t)}</span></div>`).join('')
      : '<p class="hint" style="margin:0">На этот день отдельных правил нет — действуют глобальные значения (уровень 7) и правила на весь период.</p>'}
    ${dayMods.length ? `<div class="opt-group-title" style="margin-top:12px">Правила периода, накрывающие день</div>
      ${dayMods.filter(x => !x.date).map(x => `<div class="kv"><span class="k">${esc(x.title)} · ${esc(settingsWhoText(x))}</span>
        <span class="v">${esc(settingsModValue(x.name, x.value))}</span></div>`).join('')}` : ''}
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px">
      ${can('settings.edit') ? `<button class="btn btn-sm" data-day-rule="${iso}">+ Правило на этот день</button>` : ''}
      <button class="btn btn-sm btn-ghost" data-day-check="${iso}">Проверитель для дня</button>
      <button class="btn btn-sm btn-ghost" data-day-tabel="${iso}">Открыть Табель ↗</button>
    </div>`);
}

function settingsBindDayPanel(panel) {
  if (!panel) return;
  $$('[data-day-rule]', panel).forEach(b => b.onclick = () => settingsWizard());
  $$('[data-day-check]', panel).forEach(b => b.onclick = () => settingsResolverModal());
  $$('[data-day-tabel]', panel).forEach(b => b.onclick = () => navigate('timesheet'));
}

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «СМЕНЫ И ОТСУТСТВИЯ» — словарь Графика (shift_types + ревизии).
   Это инструмент ввода, НЕ расчёт: норм расчёта здесь нет (план, ред. 3, §3.4б).
   ══════════════════════════════════════════════════════════════════════ */
async function settingsScreenShifts(host) {
  await settingsEngine();
  const p = settingsPayload();
  const edit = can('settings.edit');
  let shiftList = state.shiftTypes || [];
  if (settingsUI.showArchived) {
    try { shiftList = await api('/api/shift-types?include_archived=true', { silent: true }); }
    catch { shiftList = state.shiftTypes || []; }
  }
  const tab = settingsUI.shiftTab || 'work';
  const shown = shiftList.filter(s => (tab === 'archived' ? !!s.archived
    : !s.archived && (tab === 'work' ? s.kind === 'work' : s.kind !== 'work')));
  const codes = p?.day_code_policy || {};
  const broken = shiftList.filter(s => s.tzh_code && !codes[s.tzh_code]);
  const orphan = Object.keys(codes).filter(c => !shiftList.some(s => s.tzh_code === c && !s.archived));

  host.innerHTML = `
    ${settingsHead('Смены и отсутствия',
      'Словарь ячеек Графика: рабочие смены любого времени и виды отсутствий. На расчёт влияет косвенно — через код Табеля и флаги. Нормы расчёта — на экране «Коды Табеля».',
      `<button class="btn btn-sm btn-ghost" data-go="codes">Коды Табеля ↗</button>
       ${edit ? '<button class="btn btn-sm btn-primary" id="sh-add">+ Новая смена / отсутствие</button>' : ''}`)}
    <div class="tabs">
      <button data-stab="work" class="${tab === 'work' ? 'active' : ''}">Смены · ${shiftList.filter(s => !s.archived && s.kind === 'work').length}</button>
      <button data-stab="absence" class="${tab === 'absence' ? 'active' : ''}">Отсутствия · ${shiftList.filter(s => !s.archived && s.kind !== 'work').length}</button>
      <button data-stab="archived" class="${tab === 'archived' ? 'active' : ''}">Архив · ${shiftList.filter(s => s.archived).length}</button>
    </div>
    ${settingsPanel('', `
      <div class="table-wrap" style="max-height:none"><table class="data responsive"><thead><tr>
        <th>Код</th><th>Название</th><th>Время</th><th class="num">Часов</th><th>Код Табеля</th><th>Признаки</th><th></th>
      </tr></thead><tbody>
      ${shown.map(s => `<tr${s.archived ? ' style="opacity:.62"' : ''}>
        <td data-label="Код"><span class="shift-pill" style="background:${cssColor(s.color, '#6b7280')};color:${textOn(cssColor(s.color, '#6b7280'))}">${esc(s.code)}</span></td>
        <td data-label="Название">${esc(s.name)}</td>
        <td class="num" data-label="Время">${s.kind === 'work'
          ? `${esc(s.start_time)}–${esc(s.end_time)}${s.overnight ? ' <span class="badge info">через полночь</span>' : ''}` : '—'}</td>
        <td class="num" data-label="Часов">${s.kind === 'work' ? esc(hours(s.planned_hours)) : '—'}</td>
        <td data-label="Код Табеля">${s.tzh_code ? settingsCodePill(s.tzh_code, codes) : '<span class="badge muted">нет</span>'}</td>
        <td data-label="Признаки">${s.kind === 'work' ? '<span class="badge ok">смена</span>' : '<span class="badge muted">отсутствие</span>'}
          ${s.doc_type ? '<span class="badge info" title="Из ячейки Графика печатается заявление">заявление</span>' : ''}
          ${s.kind !== 'work' && (s.punch_in_allowed === false || s.punch_out_allowed === false)
            ? '<span class="badge warn" title="Отмечаться во время этого отсутствия нельзя">без отметок</span>' : ''}
          ${s.deduct_from_bank ? '<span class="badge warn" title="Часы отсутствия списываются из банка часов">часы из банка</span>' : ''}
          ${s.archived ? `<span class="badge muted" title="В архиве${s.archived_at ? ' с ' + dateRu(s.archived_at) : ''}">архив</span>` : ''}
          ${s.revisions ? `<span class="badge" title="Есть история значений: прошлые даты считаются по прежним часам">${s.revisions} изм.</span>` : ''}</td>
        <td class="num" style="white-space:nowrap">
          ${edit ? `<button class="btn btn-sm btn-ghost" data-shift="${s.id}">Изменить</button>
          ${s.archived ? `<button class="btn btn-sm" data-restore="${s.id}">Вернуть</button>`
            : `<button class="btn btn-sm btn-ghost" data-archive="${s.id}" title="Убрать из словаря: прошлые графики продолжат считаться по этой смене">В архив</button>`}` : ''}
        </td></tr>`).join('') || '<tr><td colspan="7" class="empty">Пусто</td></tr>'}
      </tbody></table></div>
      <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">
        ${edit ? '<button class="btn btn-sm" id="sh-new">+ Новая смена / часы (например 08:00–17:00)</button>' : ''}
        <button class="btn btn-sm btn-ghost" id="sh-arch">${settingsUI.showArchived ? 'Скрыть архив' : 'Показать архив'}</button>
      </div>
      <p class="hint">«Удаление» смены = архив: она исчезает из новых назначений, но прошлые графики и табели
        продолжают считаться по ней. Изменение времени создаёт новую ревизию словаря: отработанные дни остаются
        посчитанными по ПРЕЖНИМ часам, дата вступления указывается в редакторе смены.</p>`)}
    ${settingsPanel('Связь словарей', `
      <p class="hint" style="margin:-4px 0 10px">Общее у двух справочников ровно одно:
        <code>shift_types.tzh_code</code> → код Табеля. По этому коду день заполняется из циклов
        и получает стандартное окно (Я 8 → 09:00–18:00, Я 10,75 → 08:00–20:00); те же часы
        попадают в График первоначальными сменами. В поле допустимы только коды справочника
        или пустое значение — редактор смены предлагает список, а не свободный текст (T1).
        Подпись ячейки («08–20») хранится отдельно, в «коде в сетке».</p>
      ${broken.length ? `<div class="opt-group-title">Битые ссылки</div>
        ${broken.map(s => `<div class="kv"><span class="k">${esc(s.code)} · ${esc(s.name)}</span>
          <span class="v" style="color:var(--danger)">код «${esc(s.tzh_code)}» отсутствует в справочнике Табеля
          ${edit ? `<button class="btn btn-sm btn-ghost" data-fix-tzh="${s.id}" style="margin-left:8px">Исправить</button>` : ''}</span></div>`).join('')}
        <p class="hint" style="margin:6px 0 0">Такой день не заполнится из циклов (APP-SHIFT-CODE). Исправление:
          выберите код из списка или оставьте поле пустым — границы смены уже хранятся в её времени.</p>` : ''}
      ${orphan.length ? `<div class="opt-group-title">Коды Табеля без смены</div>
        <p class="hint" style="margin:0">Ставятся только вручную в Табеле: ${orphan.map(c =>
          settingsCodePill(c, codes)).join(' ')}</p>` : ''}
      ${!broken.length && !orphan.length ? '<p class="hint" style="margin:0">Разрывов нет: у каждой смены код Табеля существует, у каждого кода есть смена.</p>' : ''}`)}`;

  settingsBindHealth(host);
  $$('[data-stab]', host).forEach(b => b.onclick = () => { settingsUI.shiftTab = b.dataset.stab; settingsRenderScreen(); });
  settingsOn('#sh-arch', host, async () => {
    settingsUI.showArchived = !settingsUI.showArchived;
    if (settingsUI.showArchived) { await loadDirectory(); }
    settingsRenderScreen();
  });
  settingsOn('#sh-add', host, () => shiftModal(null));
  settingsOn('#sh-new', host, () => shiftModal(null));
  $$('[data-shift]', host).forEach(b => b.onclick = () =>
    shiftModal(shiftList.find(x => x.id === +b.dataset.shift)));
  /* «Исправить» у битой ссылки — тот же редактор смены: «код в табеле» в нём выбирается
     из справочника, а прежнее значение предложено очистить (T1). */
  $$('[data-fix-tzh]', host).forEach(b => b.onclick = () =>
    shiftModal(shiftList.find(x => x.id === +b.dataset.fixTzh)));
  $$('[data-archive]', host).forEach(b => b.onclick = () => {
    const sh = shiftList.find(x => x.id === +b.dataset.archive);
    confirmDialog('Архивировать смену?',
      `«${sh?.name || ''}» исчезнет из словаря для НОВЫХ назначений, но все прошлые графики и табели продолжат считаться по этой смене — история не сломается. Смену можно вернуть из архива.`,
      async () => {
        try {
          await api(`/api/shift-types/${sh.id}`, { method: 'DELETE' });
          toast('Смена перенесена в архив', 'ok');
          await loadDirectory(); await settingsRefresh();
        } catch (e) { toast(e.message, 'err'); }
      }, 'В архив');
  });
  $$('[data-restore]', host).forEach(b => b.onclick = async () => {
    try {
      await api(`/api/shift-types/${b.dataset.restore}/restore`, { method: 'POST' });
      toast('Смена возвращена в словарь', 'ok');
      await loadDirectory(); await settingsRefresh();
    } catch (e) { toast(e.message, 'err'); }
  });
}

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «ДОКУМЕНТЫ И СПРАВОЧНИКИ» — реквизиты, виды заявлений, департаменты
   и службы, прочие правила объекта
   ══════════════════════════════════════════════════════════════════════ */
async function settingsScreenDocs(host) {
  const data = settingsUI.data || {};
  const edit = can('settings.edit');
  let docsInfo = { kinds: state.docKinds || [], placeholders: state.docPlaceholders || {} };
  try { docsInfo = await api('/api/docs/kinds', { silent: true }); } catch { /* работаем с кешем */ }
  state.docKinds = docsInfo.kinds || []; state.docPlaceholders = docsInfo.placeholders || {};

  const input = item => {
    if (item.type === 'bool') {
      return `<label class="switch"><input type="checkbox" data-k="${esc(item.key)}" ${item.value ? 'checked' : ''} ${edit ? '' : 'disabled'}><span class="sl"></span></label>`;
    }
    const type = item.type === 'int' ? 'number' : 'text';
    return `<input type="${type}" data-k="${esc(item.key)}" value="${esc(item.value ?? '')}" style="max-width:180px" ${edit ? '' : 'disabled'}>`;
  };

  host.innerHTML = `
    ${settingsHead('Документы и справочники',
      'Реквизиты для печати, виды заявлений и бланки, департаменты и службы, прочие правила объекта. На математику расчёта не влияют.',
      edit ? '<button class="btn btn-sm btn-primary" id="dc-save">Сохранить правила объекта</button>' : '')}
    ${settingsPanel('Реквизиты организации', `
      <div class="grid-2">
        <label class="field"><span>Организация</span><input type="text" id="d-company" value="${esc(data.doc?.company || '')}" ${edit ? '' : 'disabled'}></label>
        <label class="field"><span>Кому (шапка заявления)</span><input type="text" id="d-director" value="${esc(data.doc?.director || '')}" ${edit ? '' : 'disabled'}></label>
      </div>
      ${edit ? '<button class="btn btn-primary btn-sm" id="d-save">Сохранить реквизиты</button>' : ''}`)}
    ${settingsPanel('Виды заявлений и шаблоны', `
      <p class="hint" style="margin:-4px 0 12px">Виды заявлений — расширяемый справочник: у каждого свой текст
        с плейсхолдерами и (по желанию) фирменный бланк .docx. Вид привязывается к отсутствию в словаре смен —
        документ печатается из ячейки Графика («Печать заявления», DOCX, PDF).
        ${docsInfo?.pdf_available ? '' : '<br>PDF-конвертация станет доступна после установки LibreOffice на сервер (<code>soffice</code>); DOCX работает всегда.'}</p>
      <table class="data"><thead><tr><th>Вид заявления</th><th>Код</th><th>Фирменный бланк</th><th></th></tr></thead>
      <tbody>${(docsInfo?.kinds || []).map(k => `<tr>
        <td>${esc(k.name)}${k.builtin ? ' <span class="badge">встроенный</span>' : ''}${k.active ? '' : ' <span class="badge muted">скрыт</span>'}</td>
        <td><code>${esc(k.code)}</code></td>
        <td>${k.template?.uploaded ? `<span class="badge ok" title="${esc(k.template.filename || '')}">загружен</span>` : '<span class="badge muted">печать текстом</span>'}</td>
        <td class="num" style="white-space:nowrap">${edit ? `<button class="btn btn-sm btn-ghost" data-kind="${k.id}">Изменить</button>` : ''}</td>
      </tr>`).join('') || '<tr><td colspan="4" class="empty">Виды заявлений не найдены</td></tr>'}</tbody></table>
      <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
        ${edit ? '<button class="btn btn-sm" id="d-add-kind">+ Новый вид заявления</button>' : ''}
        <button class="btn btn-sm btn-ghost" id="d-kind-help">Справка по плейсхолдерам</button>
      </div>`)}
    ${settingsPanel('Департаменты и службы', `
      <p class="hint" style="margin:-4px 0 12px">Значения справочников попадают в карточку сотрудника и
        подставляются в документы. Переименование обновляет карточки, удаление — очищает поле у сотрудников,
        где значение было выбрано.</p>
      <div class="grid-2" id="dicts-body"><div class="empty">Загрузка…</div></div>`)}
    ${settingsPanel('Прочие правила объекта', `
      ${(data.items || []).map(i => `<div class="rule-row">
        <div><div class="lbl">${esc(i.description || i.key)}</div>
          <div class="desc"><code>${esc(i.key)}</code> · по умолчанию: ${esc(i.default)}</div></div>
        <div class="rule-input">${input(i)}${String(i.value) !== String(i.default)
          ? `<span class="badge warn" title="по умолчанию ${esc(i.default)}">изменено</span>` : ''}</div>
      </div>`).join('') || '<p class="hint">Правил нет</p>'}
      <p class="hint">Правила расчёта часов, переработок и банка — на экранах «Расчёт» и «Правила оплаты».</p>`)}`;

  renderDicts();
  settingsOn('#dc-save', host, async () => {
    const payload = $$('[data-k]', host).map(i => ({ key: i.dataset.k,
      value: String(i.type === 'checkbox' ? (i.checked ? '1' : '0') : i.value) }));
    try {
      await api('/api/settings', { method: 'PUT', body: payload });
      toast('Правила объекта сохранены', 'ok');
      await settingsRefresh();
    } catch (e) { toast(e.message, 'err'); }
  });
  settingsOn('#d-save', host, async () => {
    try {
      await api('/api/settings/doc', { method: 'PUT', body: {
        company: $('#d-company').value, director: $('#d-director').value } });
      toast('Реквизиты сохранены', 'ok');
      await settingsRefresh();
    } catch (e) { toast(e.message, 'err'); }
  });
  settingsOn('#d-add-kind', host, () => openKindModal(null));
  $$('[data-kind]', host).forEach(b => b.onclick = () =>
    openKindModal((docsInfo?.kinds || []).find(k => k.id === +b.dataset.kind)));
  settingsOn('#d-kind-help', host, () => openModal({
    title: 'Плейсхолдеры документов', wide: true,
    body: `<table class="data">${Object.entries(docsInfo?.placeholders || {}).map(([k, v]) =>
      `<tr><td><code>{${esc(k)}}</code></td><td>${esc(v)}</td></tr>`).join('')}</table>`,
    footer: '<button class="btn btn-primary" data-ok>Понятно</button>',
    onMount(m) { m.querySelector('[data-ok]').onclick = closeModal; },
  }));
}

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «СИСТЕМА» — данные, версии и откат, аудит настроек, диагностика, права
   ══════════════════════════════════════════════════════════════════════ */
async function settingsScreenSystem(host) {
  const [engine, health] = await Promise.all([settingsEngine(), settingsHealth().catch(() => null)]);
  const data = settingsUI.data || {};
  const c = data.counts || {};
  const versions = engine?.versions || [];

  host.innerHTML = `
    ${settingsHead('Система',
      'Данные объекта, версии справочников и откат, журнал изменений настроек, диагностика и права.',
      '<button class="btn btn-sm" id="sy-versions">История версий</button>')}
    ${settingsPanel('Данные системы', `
      <div class="stat-grid">
        <div class="stat"><div class="k">Сотрудников</div><div class="v">${c.employees ?? 0}</div></div>
        <div class="stat"><div class="k">Учётных записей</div><div class="v">${c.users ?? 0}</div></div>
        <div class="stat"><div class="k">Ячеек Графика</div><div class="v">${c.schedule_shifts ?? 0}</div></div>
        <div class="stat"><div class="k">Отметок</div><div class="v">${c.punches ?? 0}</div></div>
        <div class="stat"><div class="k">Ячеек Табеля</div><div class="v">${c.tabel_days ?? 0}</div></div>
        <div class="stat"><div class="k">Закрытий периодов</div><div class="v">${c.period_closings ?? 0}</div></div>
      </div>
      <p class="hint">Пересчёт «всего месяца» не нужен: управленческий табель считается при открытии (view),
        закрытые периоды меняются только явным пересчётом последнего закрытого.</p>`)}
    ${settingsPanel('Версии справочников и откат', `
      <div class="table-wrap"><table class="data"><thead><tr>
        <th>№</th><th>Действует с</th><th>Комментарий</th><th>Кто</th><th></th></tr></thead>
      <tbody>${versions.slice(0, 12).map(v => `<tr${v.id === engine?.active?.id ? ' style="background:#f7f1ea"' : ''}>
        <td><b>#${v.id}</b>${v.id === engine?.active?.id ? ' <span class="badge ok">действует</span>' : ''}</td>
        <td>${esc(dateRu(v.valid_from))}</td><td>${esc(v.note || '—')}</td><td>${esc(v.created_by || '—')}</td>
        <td class="num" style="white-space:nowrap">
          <button class="btn btn-sm btn-ghost" data-show="${v.id}">payload</button>
          ${can('settings.edit') ? `<button class="btn btn-sm btn-ghost" data-rollback="${v.id}"
            title="Скопировать payload этой версии в черновик и опубликовать новой датой">откатиться</button>` : ''}
        </td></tr>`).join('') || '<tr><td colspan="5" class="empty">Версий нет</td></tr>'}</tbody></table></div>
      <p class="hint">Откат — не удаление истории: payload прежней версии копируется в черновик и
        публикуется новой версией с новой датой (история версий остаётся полной). Закрытые периоды
        не меняются (RUL-CLOSED-PERIOD-IMMUTABLE).</p>`)}
    ${settingsPanel('Изменения настроек за 30 дней', health?.recent?.length
      ? health.recent.map(r => `<div class="kv"><span class="k">${esc((r.ts || '').replace('T', ' ').slice(0, 16))} · ${esc(r.actor || '—')}</span>
          <span class="v" style="text-align:left;font-weight:600">${esc(r.action)} · ${esc(r.target)}</span></div>`).join('')
        + '<div style="margin-top:10px"><button class="btn btn-sm btn-ghost" data-nav="audit">Весь журнал аудита →</button></div>'
      : '<p class="hint" style="margin:0">Изменений не было.</p>')}
    ${settingsPanel('Диагностика и права', `
      <div class="grid-2">
        <div>
          <div class="kv"><span class="k">Движок</span><span class="v">v7.1</span></div>
          <div class="kv"><span class="k">Действующая версия справочников</span><span class="v">#${engine?.active?.id ?? '—'}</span></div>
          <div class="kv"><span class="k">Замечаний конфигурации</span><span class="v">${(health?.checks || []).length}</span></div>
          <div class="kv"><span class="k">Последний закрытый период</span><span class="v">${health?.periods?.last_closed_start
            ? esc(dateRu(health.periods.last_closed_start)) : 'нет'}</span></div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-content:flex-start">
          <button class="btn btn-sm" id="sy-selfcheck">Самопроверка схемы БД</button>
          ${can('access.manage') ? '<button class="btn btn-sm" data-nav="access">Права доступа ↗</button>' : ''}
          <button class="btn btn-sm btn-ghost" data-go="expert">Режим эксперта (JSON)</button>
        </div>
      </div>`)}
    ${settingsDraftBarHtml()}`;

  settingsBindHealth(host);
  settingsBindDraftBar(host);
  settingsOn('#sy-versions', host, () => settingsVersionsModal());
  settingsOn('#sy-selfcheck', host, () => window.open('/api/selfcheck', '_blank', 'noopener'));
  $$('[data-nav]', host).forEach(b => b.onclick = () => navigate(b.dataset.nav));
  $$('[data-show]', host).forEach(b => b.onclick = async () => {
    const v = versions.find(x => x.id === +b.dataset.show);
    try {
      const r = await api(`/api/engine-settings?on=${v.valid_from}`, { silent: true });
      openModal({ title: `Версия #${v.id} · payload`, wide: true,
        subtitle: `действует с ${dateRu(v.valid_from)}${v.note ? ` · ${v.note}` : ''}`,
        body: `<pre style="max-height:60vh;overflow:auto;background:#f8f5f1;border:1px solid var(--line);border-radius:6px;padding:12px;font-size:12px">${esc(JSON.stringify(r.active.payload, null, 2))}</pre>`,
        footer: '<button class="btn btn-primary" data-ok>Закрыть</button>',
        onMount(m) { m.querySelector('[data-ok]').onclick = closeModal; } });
    } catch (e) { toast(e.message, 'err'); }
  });
  $$('[data-rollback]', host).forEach(b => b.onclick = async () => {
    const v = versions.find(x => x.id === +b.dataset.rollback);
    if (v.id === engine?.active?.id) return toast('Эта версия и так действует', 'warn');
    try {
      const r = await api(`/api/engine-settings?on=${v.valid_from}`, { silent: true });
      settingsUI.draft = JSON.parse(JSON.stringify(r.active.payload));
      settingsUI.screen = 'calc';
      await settingsRenderScreen();
      settingsUpdateDraftBars();
      toast(`Payload версии #${v.id} загружен в черновик — проверьте diff и опубликуйте`, 'ok');
    } catch (e) { toast(e.message, 'err'); }
  });
}

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «РЕЖИМ ЭКСПЕРТА» — тот же черновик, но вторым видом: сырой JSON
   версии справочников и полный список модификаторов (renderEngineSettings).
   ══════════════════════════════════════════════════════════════════════ */
async function settingsScreenExpert(host) {
  host.innerHTML = `
    ${settingsHead('Режим эксперта (JSON)',
      'Полный payload версии справочников и все модификаторы периода. Формы выше и этот экран правят ОДНУ конфигурацию: формы — два вида одного черновика, а не второй источник правды.',
      '<button class="btn btn-sm" data-go="overview">← Обзор</button>')}
    <div class="panel" id="st-expert"><div class="empty">Загрузка справочников движка…</div></div>`;
  settingsBindHealth(host);
  await renderEngineSettings($('#st-expert', host));
}

/* ══════════════════════════════════════════════════════════════════════
   ПОИСК ПО НАСТРОЙКАМ (⌘K / Ctrl+K) — любая настройка находится за 2 нажатия
   ══════════════════════════════════════════════════════════════════════ */
function settingsSearchIndex() {
  const out = [];
  SETTINGS_SCREENS.filter(s => s.id).forEach(s => out.push({
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
  (settingsUI.data?.items || []).forEach(i => out.push({
    title: i.description || i.key, hint: `прочие правила объекта · ${i.key}`, screen: 'docs' }));
  (state.shiftTypes || []).forEach(s => out.push({
    title: `${s.kind === 'work' ? 'Смена' : 'Отсутствие'} «${s.name}»`, hint: `${s.code}${s.tzh_code ? ' · код Табеля ' + s.tzh_code : ''}`, screen: 'shifts' }));
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
          <small>${esc(SETTINGS_TITLES[x.screen] || '')}${x.external ? ' ↗' : ''}</small></button>`).join('')
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
          `${x.title} ${x.hint || ''} ${SETTINGS_TITLES[x.screen] || ''}`.toLowerCase().includes(s)));
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
