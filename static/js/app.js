/* ══════════════════════════════════════════════════════════════════════
   TimeTrack — веб-интерфейс (SPA без сборки), светлая тема
   Состав меню и экранов Настроек — из манифестов модулей (app/modules/<имя>/manifest.py,
   приходит в /api/auth/me уже по правам); файлы разделов регистрируют свои загрузчики
   через registerModule. Права доступа и Журнал
   аудита — экраны Настроек (группа «Администрирование»), navigate('access'/'audit') работает.
   Ядро (утилиты, api, состояние, модалки) вынесено в core.js — подключается раньше этого файла.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

import { $, $$, adoptAuthContext, api, authContextIsCurrent, authContextSnapshot, closeDrawer, closeModal, getCookie,
  expireAuthContext, initials, loadMediaLimits, openDrawer, openModal, publishAuthContext, roleTitle, setLoginHandler, serverShiftMs, state,
  subscribeAuthContext, subscribeSessionRejection, syncServerClock, toast, todayISO } from './core.js';
import { html, mount, nothing, render } from './ui/html.js';
import { MODULE_SCREENS, MODULE_VIEWS, registerModule } from './registry.js';
import { close as closePalette, paletteBoot, paletteInit, togglePalette } from './ui/palette.js';
import { carsState } from './modules/cars.js';
import { nightState } from './modules/night.js';
import { settingsUI } from './modules/settings.js';
import { staysResetUserState } from './modules/stays_filters.js';
import { staysGuestsResetUserState } from './modules/stays_guests.js';

/* ───────────────────────────── вкладки ───────────────────────────── */
const ICONS = {
  sections: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  today: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
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
  stays: '<svg viewBox="0 0 24 24"><rect x="3.5" y="3.5" width="17" height="17" rx="2.5" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M9.3 3.5v17M14.7 3.5v17M3.5 9.3h17M3.5 14.7h17" stroke="currentColor" stroke-width="1.6"/></svg>',
  mystays: '<svg viewBox="0 0 24 24"><circle cx="12" cy="7.6" r="3.3" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M5 20c1.2-3.6 3.9-5.4 7-5.4 1.6 0 3 .4 4.2 1.2" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/><path d="M17.6 15.2l.9 1.9 2 .3-1.5 1.4.4 2-1.8-1-1.8 1 .4-2-1.5-1.4 2-.3z" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linejoin="round"/></svg>',
  guests: '<svg viewBox="0 0 24 24"><circle cx="9" cy="7.6" r="3.2" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M3.5 20c1-3.4 3-5.2 5.5-5.2s4.5 1.8 5.5 5.2" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/><path d="M15.5 8.5h5M15.5 12.5h5M15.5 16.5h3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  cars: '<svg viewBox="0 0 24 24"><path d="M4 16v-3.2L6.2 8h11.6L20 12.8V16" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/><rect x="3" y="15" width="18" height="4.5" rx="1.6" stroke="currentColor" stroke-width="1.8" fill="none"/><circle cx="7.3" cy="17.2" r="1" fill="currentColor"/><circle cx="16.7" cy="17.2" r="1" fill="currentColor"/></svg>',
  mgmt: '<svg viewBox="0 0 24 24"><rect x="4" y="3" width="16" height="18" rx="2" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M8 8h8M8 12h8M8 16h5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M15.5 16.5l1.5 1.5 3-3" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  access: '<svg viewBox="0 0 24 24"><path d="M12 3l7 3v5c0 4.5-3 8.2-7 10-4-1.8-7-5.5-7-10V6z" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/><circle cx="12" cy="11" r="2.2" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M12 13.2V16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  audit: '<svg viewBox="0 0 24 24"><path d="M6 3h9l4 4v14H6z" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linejoin="round"/><path d="M9 11h7M9 15h7M9 7h4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  settings: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.8" fill="none"/><path d="M12 3v2.5M12 18.5V21M4.2 7.5l2.2 1.3M17.6 15.2l2.2 1.3M4.2 16.5l2.2-1.3M17.6 8.8l2.2-1.3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
};

/* Иконка пункта меню: ICONS — собственные постоянные строки с svg (не данные сервера), узел
   разбирается DOM-ом, каждый раз новый. */
const icon = id => (ICONS[id] ? document.createRange().createContextualFragment(ICONS[id]) : nothing);

/* Права приходят с сервера (/api/auth/me → permissions): роль + группы + индивидуальные. */
export function can(perm) { return (state.perms || []).includes(perm); }

/* Реестр разделов (registry.js): файл модуля сообщает загрузчики разделов и экраны Настроек.
   Здесь — повторный экспорт, чтобы модули по-прежнему брали registerModule из app.js. */
export { MODULE_SCREENS, registerModule };

/* «График» — один пункт меню с четырьмя слоями (modules/grafik.js). */
/* старые имена разделов — алиасы слоёв: navigate('timesheet') и др. продолжают
   работать (переходы из модалок, сценарии, смоук harness) */
const GRAFIK_ALIAS = { timesheet: 'grafik', schedule: 'grafik', fact: 'grafik', mgmt: 'grafik' };

/* Пункты меню — из манифестов модулей (MenuItem), сервер уже отфильтровал их по правам. */
/* «Сегодня» — первый пункт для всех: набор блоков внутри зависит от прав (modules/today.js) */
const TODAY_TAB = { id: 'today', title: 'Сегодня' };
function visibleTabs() { return [TODAY_TAB, ...(state.menu || [])]; }

const MOBILE_DEFAULTS = {
  employee: ['mystays', 'night', 'cars'],
  supervisor: ['mystays', 'night', 'stays'],
  manager: ['stays', 'grafik', 'marks'],
  admin: ['stays', 'grafik', 'settings'],
};
const MOBILE_SLOTS = ['Первая вкладка', 'Вторая вкладка', 'Третья вкладка'];
const MOBILE_LABELS = { cars: 'Кары' };
const mobilePreferenceKey = () => `butler.mobile-tabs.v1.${state.user.id}`;

function defaultMobileIds(available) {
  return [...new Set([...(MOBILE_DEFAULTS[state.user.role] || []), ...available.map(tab => tab.id)])]
    .filter(id => available.some(tab => tab.id === id)).slice(0, MOBILE_SLOTS.length);
}

function mobileIds(available) {
  if (state.user.impersonated) return defaultMobileIds(available);
  try {
    const saved = JSON.parse(localStorage.getItem(mobilePreferenceKey()));
    if (Array.isArray(saved)) {
      return MOBILE_SLOTS.map((_, slot) => {
        const id = saved[slot];
        return saved.indexOf(id) === slot && available.some(tab => tab.id === id) ? id : '';
      });
    }
  } catch { /* настройки по умолчанию, если хранилище недоступно */ }
  return defaultMobileIds(available);
}

function configureMobileTabs(available) {
  let draft = mobileIds(available);
  const form = html`<div id="mobile-tabs-picker"></div>`;
  openModal({ title: 'Быстрые вкладки', body: form,
    subtitle: 'Выберите до трёх разделов для нижней панели.',
    footer: html`<button class="btn btn-ghost" data-default>Вернуть набор по роли</button>
      <button class="btn btn-primary" data-save>Сохранить</button>`,
    onMount(dialog) {
      const picker = $('#mobile-tabs-picker', dialog);
      const paint = () => render(MOBILE_SLOTS.map((label, index) => html`<label class="field"><span>${label}</span>
        <select @change=${e => { draft[index] = e.target.value; paint(); }}>
          <option value="" ?selected=${!draft[index]}>Не закреплять</option>
          ${available.map(tab => html`<option value=${tab.id} ?selected=${draft[index] === tab.id}
            ?disabled=${draft.some((id, slot) => slot !== index && id === tab.id)}>${tab.title}</option>`)}
        </select></label>`), picker);
      $('[data-default]', dialog).onclick = () => { draft = defaultMobileIds(available); paint(); };
      $('[data-save]', dialog).onclick = () => {
        const slots = MOBILE_SLOTS.map((_, slot) => draft[slot] || '');
        try { localStorage.setItem(mobilePreferenceKey(), JSON.stringify(slots)); }
        catch { toast('Не удалось сохранить настройки панели.', 'err'); return; }
        renderNav();
        closeModal();
      };
      paint();
    },
  });
}

function mobileCatalog(tabs, activeView) {
  openDrawer({ title: 'Разделы', returnFocusTo: () => $('#mobile-sections'),
    body: html`<nav class="mobile-catalog" aria-label="Все разделы">${tabs.map(tab => html`<button type="button"
      class=${`nav-item${tab.id === activeView ? ' active' : ''}`} aria-current=${tab.id === activeView ? 'page' : nothing}
      @click=${() => { closeDrawer(); navigate(tab.id); }}>${icon(tab.id)}<span>${tab.title}</span></button>`)}</nav>`,
    footer: !state.user.impersonated && tabs.length > 1 ? html`<button class="btn btn-sm"
      @click=${() => configureMobileTabs(tabs.slice(1))}>Настроить панель</button>` : nothing,
  });
}

let settingsNavExpanded = false;
const inSettings = view => view === 'settings' || view === 'access' || view === 'audit';
let hideNavTooltipTimer;
const navTooltip = $('#sidenav-tooltip');
function hideNavTooltip() {
  clearTimeout(hideNavTooltipTimer);
  navTooltip.classList.add('hidden');
}
function showNavTooltip(button, title) {
  hideNavTooltip();
  if (!$('#sidenav').classList.contains('compact')) return;
  const bounds = button.getBoundingClientRect();
  navTooltip.textContent = title;
  navTooltip.style.left = `${bounds.right + 10}px`;
  navTooltip.style.top = `${bounds.top + bounds.height / 2}px`;
  navTooltip.classList.remove('hidden');
}

function applySettingsNavigation() {
  const fold = $('#sidenav-fold');
  const inside = state.view === 'settings';
  const compact = inside && !settingsNavExpanded;
  $('#sidenav').classList.toggle('compact', compact);
  fold.classList.toggle('hidden', !inside);
  fold.setAttribute('aria-expanded', String(!compact));
  const name = compact ? 'Развернуть основное меню' : 'Свернуть основное меню';
  fold.setAttribute('aria-label', name);
  fold.title = name;
  hideNavTooltip();
}

$('#sidenav-fold').onclick = () => {
  settingsNavExpanded = !settingsNavExpanded;
  applySettingsNavigation();
};
navTooltip.onpointerenter = () => clearTimeout(hideNavTooltipTimer);
navTooltip.onpointerleave = hideNavTooltip;
$('#sidenav').addEventListener('scroll', () => {
  const focused = $('#sidenav .nav-item:focus-visible');
  if (focused && !navTooltip.classList.contains('hidden')) showNavTooltip(focused, focused.getAttribute('aria-label'));
  else hideNavTooltip();
}, { passive: true });
window.addEventListener('resize', hideNavTooltip);
document.addEventListener('keydown', event => { if (event.key === 'Escape') hideNavTooltip(); });

function renderNav() {
  const tabs = visibleTabs();
  /* «Права доступа» и «Журнал аудита» открываются из Настроек (external-экраны):
     их содержимое — отдельные view, но в меню подсвечиваем «Настройки», откуда пришли. */
  const activeView = inSettings(state.view) ? 'settings' : state.view;
  applySettingsNavigation();
  $('#sidenav').querySelectorAll('.nav-item').forEach(el => el.remove());
  const foot = $('#sidenav-foot');
  tabs.forEach(t => {
    const b = document.createElement('button');
    b.className = 'nav-item' + (activeView === t.id ? ' active' : '');
    b.dataset.view = t.id;
    b.setAttribute('aria-label', t.title);
    if (activeView === t.id) b.setAttribute('aria-current', 'page');
    render(html`${icon(t.id)}<span>${t.title}</span>`, b);
    b.onclick = () => navigate(t.id);
    b.onfocus = b.onpointerenter = () => showNavTooltip(b, t.title);
    b.onblur = hideNavTooltip;
    b.onpointerleave = () => {
      if (!b.matches(':focus-visible')) hideNavTooltipTimer = setTimeout(hideNavTooltip, 150);
    };
    $('#sidenav').insertBefore(b, foot);
  });
  const quickTabs = [TODAY_TAB, ...mobileIds(tabs.slice(1)).map(id => tabs.find(tab => tab.id === id))];
  const inCatalog = !quickTabs.some(tab => tab?.id === activeView);
  render(html`${quickTabs.map((t, index) => t ? html`<button type="button" data-view=${t.id}
    class=${activeView === t.id ? 'active' : ''} style=${`grid-column:${index + 1}`} aria-label=${t.title}
    aria-current=${activeView === t.id ? 'page' : nothing}
    @click=${() => navigate(t.id)}>${icon(t.id)}<span>${MOBILE_LABELS[t.id] || t.title}</span></button>` : nothing)}
    <button type="button" id="mobile-sections" class=${inCatalog ? 'active' : ''} aria-current=${inCatalog ? 'true' : nothing}
      aria-haspopup="dialog" @click=${() => mobileCatalog(tabs, activeView)}>${icon('sections')}<span>Разделы</span></button>`,
  mount($('#tabbar')));
  render(html`Учёт кратен шагу (по умолчанию 1 ч)<br><span id="nav-categories"></span>Часы — по календарным дням`, mount(foot));
  renderCategoryFooter(state.timeCategories);
}

/* Категории времени в подвале меню — из настроек периода, когда их прислал Факт;
   раньше здесь были зашиты 22:00–06:00. */
export function renderCategoryFooter(categories) {
  if (categories && categories.length) state.timeCategories = categories;
  const el = $('#nav-categories');
  if (!el) return;
  render(state.timeCategories
    ? html`${state.timeCategories.map(c => `${c.code} ${c.start}–${c.end}`).join(' · ')}<br>` : nothing, mount(el));
}

export function navigate(view) {
  if (!state.user) return;
  if (GRAFIK_ALIAS[view]) { state.grafikLayer = view; view = GRAFIK_ALIAS[view]; }
  if (!inSettings(state.view) && inSettings(view)) settingsNavExpanded = false;
  state.view = view;
  $$('.view').forEach(v => v.classList.remove('active'));
  let el = $(`#view-${view}`);
  if (!el && MODULE_VIEWS[view]) {     // раздел нового модуля: контейнер не нужно вписывать в index.html
    el = document.createElement('section');
    el.id = `view-${view}`; el.className = 'view';
    $('main.content').appendChild(el);
  }
  if (el) el.classList.add('active');
  renderNav();
  clearTimers();
  /* Загрузчики регистрируют файлы разделов (registerModule) прямыми ссылками — линтер ловит
     отсутствующую функцию (no-undef); раньше здесь был `window[fnName]`, и потерянный
     loadNight не видел ни один инструмент. Если файл раздела не загрузился (старый кэш,
     ошибка в файле) или загрузчик упал — вместо пустого экрана заглушка с причиной. */
  const run = MODULE_VIEWS[view] || (() => {
    if (!el) return;
    render(html`<div class="panel"><h3 class="panel-title">Раздел не найден</h3>
      <p class="hint">Неизвестный раздел <code>${view}</code>. Обновите страницу
      с очисткой кэша (Cmd/Ctrl+Shift+R).</p></div>`, mount(el));
  });
  Promise.resolve().then(run).catch(err => {
    console.error(err);
    if (el) render(html`<div class="panel"><h3 class="panel-title">Раздел не загрузился</h3>
      <p style="color:var(--danger);font-weight:600">${String(err?.message || err)}</p>
      <p class="hint">Что сделать: 1) обновите страницу с очисткой кеша (Cmd/Ctrl+Shift+R);
      2) перезапустите сервер (Ctrl+C и ./run.sh) — миграции применяются при старте;
      3) откройте http://127.0.0.1:8000/api/selfcheck — он покажет, не отстаёт ли схема БД;
      4) если ошибка повторяется, пришлите хвост server.log и текст из консоли браузера (F12 → Console).</p></div>`, mount(el));
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
/* Интервалы опроса разделов, мс (HARD-02: раньше числа были разбросаны по модулям).
   Доска и «Мои отметки» живые — 30 с; ночной обход и кары меняются реже — 60 с. */
const POLL_MS = { marks: 30000, me: 30000, night: 60000, cars: 60000 };
export function poll(view, fn, ms = POLL_MS[view] || 30000) {
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


function deactivateShell() {
  state.user = null;
  $('#app').classList.add('hidden');
  clearTimers();
  closeModal();
  closeDrawer();
  closePalette();
  applyMe({});
  for (const id of ['#user-name', '#user-avatar', '#user-role']) $(id).textContent = '';
  resetUserViewState();
  renderSchemaBanner(null);
}

subscribeAuthContext(event => { if (event.external && event.context) deactivateShell(); });
subscribeSessionRejection(deactivateShell);

export function showLogin() {
  deactivateShell();
  $('#login-screen').classList.remove('hidden');
  $('#login-password').value = '';   // после выхода форма логина пустая
}
setLoginHandler(showLogin);

/* Ответ /api/auth/me → права и роли. Роли — данные сервера (ADR-0011): названия своих ролей
   и список ролей, которые пользователь вправе назначать (иерархия считается там же). */
export function applyMe(me) {
  state.perms = me.permissions || [];
  state.menu = me.menu || [];
  state.settingsScreens = me.settings_screens || [];
  state.roleTitles = Object.fromEntries((me.roles || []).map(r => [r.code, r.title]));
  state.assignableRoles = me.assignable_roles || [];
}

export async function loadPerms() {
  const started = authContextSnapshot();
  try {
    const me = await api('/api/auth/me', { silent: true });
    if (authContextIsCurrent(started) && me.auth_context === started.context) applyMe(me);
  } catch { if (authContextIsCurrent(started)) applyMe({}); }
}

function startView() {
  /* Стартовый экран — «Сегодня»; у него свой набор блоков для каждой роли.
     Прежний выбор «Мои отметки» для сотрудника теперь внутри «Сегодня» (кнопка «Пришёл / Ушёл»). */
  return 'today';
}

/* Сброс состояния при смене пользователя (вход, вход/выход из режима
   «посмотреть глазами сотрудника»): выход не перезагружает страницу, поэтому
   кэши и DOM разделов не должны доставаться следующему пользователю.
   Сброс полный: кэши справочников, сетки, фильтры, позиция UI, fact-поля, employees, grafikLayer,
   вкладки «Графика» и состояния модулей (carsState/nightState/settingsUI) не переживают смену
   пользователя. loadDirectory и загрузчики
   разделов наполнят всё заново при входе. */
export function resetUserViewState() {
  state.factMode = null; state.factMonth = null; state.factDay = null;
  state.factEmp = null; state.factFrom = null; state.factTo = null;
  state.employees = [];
  /* Кэши справочников: у сотрудника loadDirectory не вызывается — в памяти не
     должно оставаться данных предыдущего менеджера. */
  state.shiftTypes = []; state.departments = []; state.subdivisions = [];
  state.docKinds = []; state.docPlaceholders = {}; state.tabelCodes = [];
  state.grid = null; state.timesheet = null; state.status = null;
  state.doc = null; state.tabel = null; state.pendingTabelCell = null; state.factDayData = null;
  state.enginePayload = null; state.mgmt = null; state.mgmtHalf = null; state.timeCategories = null;
  state.access = null; state.accessTab = 'roles';
  state.auditQ = { q: '', action: '', actor: '', date_from: '', date_to: '', offset: 0 };
  state.filterDept = 'all'; state.filterText = ''; state.expanded = new Set();
  /* Позиция UI — на «сегодня» по часам объекта (serverShiftMs из core). */
  const nowObj = new Date(Date.now() + serverShiftMs);
  state.year = nowObj.getFullYear(); state.month = nowObj.getMonth() + 1;
  state.attDate = todayISO(); state.dpYear = nowObj.getFullYear();
  state.grafikLayer = null;
  /* шахматка: фильтры (в них поиск — фамилия, телефон гостя), разделы, вкладка — не
     переходят к следующему пользователю устройства; сохранённые наборы — у каждого свои */
  staysResetUserState();
  staysGuestsResetUserState();
  Object.assign(carsState, { data: null, meta: null, locations: [], filter: 'all', q: '', error: false, loading: false });
  Object.assign(nightState, { reportId: null, today: null, areas: null, zoneId: null,
    areaId: null, q: '', filter: 'all', dictTab: 'zones', dictZone: null,
    dictArea: null, defectsSelected: new Set(), defectsShowSent: false });
  Object.assign(settingsUI, { screen: null, data: null, health: null, engine: null,
    draft: null, calYear: 0, calMonth: 0, shiftTab: 'work', payFilter: '' });
  /* DOM разделов — в начальное пустое состояние: в index.html все .view пустые,
     их рисуют загрузчики при открытии; каркас #view-grafik восстановит
     mount() в modules/grafik.js. Прежняя очистка одного
     #grafik-tabs оставляла чужую разметку остальных разделов до первого открытия. */
  $$('.view').forEach(v => v.replaceChildren());
}

/* Перечень расхождений схемы сервер отдаёт только администратору (/api/selfcheck), остальным —
   строку details: раньше chk.missing.slice у них падал TypeError, и предупреждение терялось. */
export function selfcheckDetails(chk, limit = 6) {
  if (Array.isArray(chk.missing)) return chk.missing.slice(0, limit);
  return chk.details ? [chk.details] : [];
}

/* Плашка «Схема БД не в порядке» — до закрытия (тост исчезал через 5 с и вмещал 6 строк).
   Перечень — у администратора целиком: для пропущенного индекса там команда его создания. */
export function renderSchemaBanner(chk) {
  const el = $('#schema-banner');
  if (!el) return;
  if (!chk || chk.ok !== false) { el.classList.add('hidden'); el.replaceChildren(); return; }
  const items = selfcheckDetails(chk, 50);
  render(html`<div class="sb-text"><b>Схема БД не в порядке.</b> ${chk.hint || ''}
      ${items.length ? html`<ul>${items.map(i => html`<li><code>${i}</code></li>`)}</ul>` : nothing}</div>
    <button class="icon-btn" data-schema-close title="Скрыть до следующего входа" aria-label="Скрыть"
      @click=${() => el.classList.add('hidden')}>✕</button>`, mount(el));
  el.classList.remove('hidden');
}

async function enterApp(me, view = startView()) {
  resetUserViewState();
  applyMe(me);
  $('#login-screen').classList.add('hidden');
  $('#app').classList.remove('hidden');
  renderUserChip();
  try {
    renderSchemaBanner(await api('/api/selfcheck', { silent: true, allow401: true }));
  } catch { /* самодиагностика недоступна — не критично */ }
  if (can('employees.view')) {        // справочник — по праву, а не по роли (UI-02)
    try {
      await loadDirectory();
    } catch (e) {
      // справочник не загрузился — не блокируем интерфейс: разделы покажут свои ошибки
      toast('Справочники не загрузились: ' + (e.message || e) +
            ' — откройте Console/Network и пришлите ошибку', 'err');
    }
  }
  if (state.user === me.user) navigate(view);
}

export function renderUserChip() {
  const u = state.user;
  $('#user-name').textContent = u.name;
  $('#user-role').textContent = roleTitle(u.role);
  $('#user-avatar').textContent = initials(u.name);
  $('#impersonation-bar').classList.toggle('hidden', !u.impersonated);
}

export async function loadDirectory() {
  const started = authContextSnapshot();
  const [emps, types] = await Promise.all([api('/api/employees'), api('/api/shift-types')]);
  if (!authContextIsCurrent(started)) return;
  state.employees = emps;
  state.shiftTypes = types;
  try {
    const [deps, subs] = await Promise.all([api('/api/departments', { silent: true }),
                                            api('/api/subdivisions', { silent: true })]);
    if (!authContextIsCurrent(started)) return;
    state.departments = deps; state.subdivisions = subs;
  } catch { /* справочник недоступен — редактор сотрудника обойдётся кешем */ }
  try {
    const kd = await api('/api/docs/kinds', { silent: true });
    if (!authContextIsCurrent(started)) return;
    state.docKinds = kd.kinds || []; state.docPlaceholders = kd.placeholders || {};
  } catch { state.docKinds = state.docKinds || []; }
  /* Коды Табеля нужны редактору смены: «код в табеле» — выбор из справочника,
     а не свободный текст (T1). Недоступен — редактор покажет текущее значение. */
  try {
    const tc = await api('/api/shift-types/tabel-codes', { silent: true });
    if (!authContextIsCurrent(started)) return;
    state.tabelCodes = tc.codes || [];
  } catch { state.tabelCodes = state.tabelCodes || []; }
}

/* ══════════════════════════════════════════════════════════════════
   ГРАФИК: блоки смен, цвета должностей, произвольные циклы
   ══════════════════════════════════════════════════════════════════ */
/* Разделы «Отметки» (доска), «Факт» (история сессий), «Табель», «Управленческий табель»,
   «Права доступа» и «Журнал аудита» — по файлу на экран: modules/marks.js, fact.js,
   tabel.js, mgmt.js, access.js, audit.js (движок v7.1). */



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

// Нативный вход завершается редиректом. Отличаем его от обычного открытия новой вкладки.
const loginSubmitted = 'butler.login-submitted';
$('#login-form').addEventListener('submit', () => {
  try { sessionStorage.setItem(loginSubmitted, '1'); } catch { /* /me всё равно привяжет вкладку */ }
});

$('#logout-btn').onclick = async () => {
  const started = authContextSnapshot();
  if (!authContextIsCurrent(started)) return;
  try { await api('/api/auth/logout', { method: 'POST', silent: true }); }
  catch { await expireAuthContext(started); }
};
$('#change-pass-btn').onclick = () => openModal({
  title: 'Смена пароля',
  subtitle: 'Потребуется старый пароль для подтверждения',
  body: html`
    <label class="field"><span>Старый пароль</span><input type="password" id="cp-old" autocomplete="current-password"></label>
    <label class="field"><span>Новый пароль</span><input type="password" id="cp-new" autocomplete="new-password"></label>
    <label class="field"><span>Подтверждение нового пароля</span><input type="password" id="cp-new2" autocomplete="new-password"></label>`,
  footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button>
           <button class="btn btn-primary" data-save>Сменить пароль</button>`,
  onMount(m) {
    m.querySelector('[data-cancel]').onclick = closeModal;
    m.querySelector('[data-save]').onclick = async () => {
      const nw = $('#cp-new').value, nw2 = $('#cp-new2').value;
      if (!$('#cp-old').value) return toast('Введите старый пароль', 'warn');
      if (nw.length < 8) return toast('Новый пароль слишком короткий (минимум 8 символов)', 'warn');
      if (nw !== nw2) return toast('Новый пароль и подтверждение не совпадают', 'warn');
      const view = state.view;
      try {
        const res = await api('/api/auth/change-password', { method: 'POST',
          body: { old_password: $('#cp-old').value, new_password: nw } });
        const started = authContextSnapshot();
        if (started.context !== res.auth_context || !authContextIsCurrent(started)) return;
        closeModal();
        if (state.user) navigate(view);
        else {
          // Foreground validation may have cleared the shell while the issuer body was in flight.
          try {
            const me = await api('/api/auth/me');
            if (!authContextIsCurrent(started) || me.auth_context !== started.context) return;
            state.user = me.user;
            await enterApp(me, view);
          } catch { await expireAuthContext(started); return; }
        }
        toast('Пароль изменён', 'ok');
      } catch (e) { toast(e.message, 'err'); }
    };
  },
});
$('#stop-impersonation').onclick = async () => {
  const r = await api('/api/auth/impersonate/stop', { method: 'POST' });
  if (await switchImpersonation(r, startView())) toast('Вы вернулись в свой интерфейс', 'ok');
};

export async function switchImpersonation(session, view) {
  if (getCookie('tt_auth_context') !== session.auth_context) return false;
  deactivateShell();
  const started = authContextSnapshot();
  $('#user-name').textContent = session.user.name;
  try {
    const me = await api('/api/auth/me');
    if (!authContextIsCurrent(started)) return false;
    if (me.auth_context === session.auth_context) {
      state.user = me.user;
      applyMe(me);
      renderUserChip();
      $('#app').classList.remove('hidden');
      navigate(view);
      return true;
    }
  } catch { /* при 401 уже показан вход; при потере связи заново загрузим оболочку */ }
  if (authContextSnapshot().context === session.auth_context) location.reload();
  return false;
}


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

export async function bootApp() {
  const initial = authContextSnapshot();
  let fromLogin = false;
  try {
    fromLogin = sessionStorage.getItem(loginSubmitted) === '1';
    sessionStorage.removeItem(loginSubmitted);
  } catch { /* хранилище может быть отключено */ }
  api('/api/health', { silent: true, allow401: true })
    .then(h => { syncServerClock(h?.server_time_local); state.appTz = h?.tz || ''; }).catch(() => {});
  const loginErr = new URLSearchParams(location.search).get('login_error');
  if (loginErr) history.replaceState(null, '', location.pathname + location.hash);
  try {
    const me = await api('/api/auth/me', { silent: true, allow401: true });
    if (authContextSnapshot().eventId !== initial.eventId) return;
    if (me?.user) {
      const marker = getCookie('tt_auth_context');
      if (marker && marker !== me.auth_context) {
        adoptAuthContext(me.auth_context);
        await expireAuthContext(authContextSnapshot());
        return;
      }
      if (fromLogin) publishAuthContext(me.auth_context);
      else adoptAuthContext(me.auth_context);
      const started = authContextSnapshot();
      await loadMediaLimits();     // лимиты фото/видео для подсказок загрузки
      if (!authContextIsCurrent(started) || started.context !== me.auth_context) {
        await expireAuthContext(started);
        return;
      }
      state.user = me.user;
      await enterApp(me);
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
/* Точка входа для сквозных тестов (Playwright) и отладки в консоли браузера: остальные имена модулей
   снаружи не видны. Код интерфейса этими свойствами не пользуется. */
Object.assign(window, { navigate, state, toast, openModal });
/* Точка входа для сквозных тестов (Playwright) и отладки в консоли браузера: остальные имена модулей
   снаружи не видны. Код интерфейса этими свойствами не пользуется. */
Object.assign(window, { navigate, state, toast, openModal });
paletteInit({ menu: visibleTabs, navigate });
paletteBoot();
document.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && (e.code === 'KeyK' || String(e.key).toLowerCase() === 'k')) {
    e.preventDefault();
    togglePalette();
  }
});
bootApp();
