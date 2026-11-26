/* ══════════════════════════════════════════════════════════════════════
   ПАЛИТРА КОМАНД (⌘K / Ctrl+K): разделы меню, действия модулей, живой
   поиск гостей. Открывается из любого места, Esc/✕ закрывает, ↑↓ + Enter
   или клик. На телефоне — почти на весь экран. Компонент живёт в ui/ и
   не знает о модулях: app.js сообщает переходы (из меню), модули
   добавляют свои действия через register(), поиск гостей — здесь же.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

import {
  $, authContextIsCurrent, authContextSnapshot, pushOverlay, removeOverlay, state,
} from '../core.js';
import { paletteProviders } from '../registry.js';
import { html, mount, nothing, render } from './html.js';

/* действия модулей: {id, title, hint, run, when?} — when() решает видимость по правам */
let actions = [];
export function paletteRegister(action) { actions = [...actions.filter(a => a.id !== action.id), action]; }

let open = false;
let query = '';
let index = 0;            /* выбранный пункт списка */
let found = [];           /* результаты зарегистрированных providers */
let searching = false;
let timer = null;
let searchController = null;
let searchGeneration = 0;

let navProvider = () => [];       /* пункты меню: [{id, title}] */
let navigateFn = () => {};
export function paletteInit({ menu, navigate }) {
  navProvider = menu;
  navigateFn = navigate;
}

const norm = s => String(s || '').toLowerCase();
const matches = (title, q) => norm(title).includes(norm(q));

/* пункты: навигация + действия; гости добавляются отдельно после поиска */
function navItems(q) {
  return navProvider()
    .filter(m => !q || matches(m.title, q))
    .map(m => ({ key: 'nav:' + m.id, icon: m.id, title: m.title, hint: 'раздел',
                 run: () => navigateFn(m.id) }));
}
function actionItems(q) {
  return actions
    .filter(a => (!a.when || a.when()) && (!q || matches(a.title, q)))
    .map(a => ({ key: 'act:' + a.id, icon: a.icon || 'settings', title: a.title, hint: a.hint || 'действие',
                 run: a.run }));
}
function providerItems() {
  return found.map(({ provider, item }, i) => ({
    key: `provider:${provider.id}:${item.id ?? i}`,
    icon: item.icon || provider.icon || 'search',
    title: item.title || item.short || String(item.id || ''),
    hint: item.hint || provider.hint || 'результат',
    detail: item.detail,
    run: () => provider.activate(item),
  }));
}

function items() { return [...navItems(query), ...actionItems(query), ...providerItems()]; }

function paint() {
  const box = $('#palette');
  if (!box) return;
  const list = items();
  index = Math.max(0, Math.min(index, list.length - 1));
  render(html`<div class="palette" role="dialog" aria-modal="true" aria-label="Команды">
    <input id="palette-q" type="search" placeholder="Раздел, действие, гость…"
      .value=${query} @input=${e => { query = e.target.value; index = 0; scheduleSearch(); paint(); }}
      @keydown=${onKeys}>
    <div class="palette-list" role="listbox">${list.length ? list.map((it, i) => html`
      <button class="palette-item${i === index ? ' active' : ''}" role="option" aria-selected=${i === index}
        @click=${() => pick(it)} @mousemove=${() => { if (index !== i) { index = i; paint(); } }}>
        <span class="palette-item-title">${it.title}
          ${it.detail ? html`<small class="guest-pick-details muted">${it.detail}</small>` : nothing}
        </span><span class="muted">${it.hint}</span>
      </button>`) : html`<div class="muted" style="padding:10px 12px">${searching ? 'ищем…' : 'ничего не найдено'}</div>`}
    </div></div>`, mount(box));
}

function retireSearch() {
  clearTimeout(timer);
  timer = null;
  searchController?.abort();
  searchController = null;
  ++searchGeneration;
  searching = false;
}

function scheduleSearch() {
  retireSearch();
  found = [];
  const q = query.trim();
  if (q.length < 2) return;
  const generation = searchGeneration;
  const controller = new AbortController();
  searchController = controller;
  timer = setTimeout(async () => {
    const started = authContextSnapshot();
    searching = true;
    if (open) paint();
    const results = await Promise.all(paletteProviders().map(async provider => {
      try {
        const providerFound = await provider.search(q, controller.signal);
        return (Array.isArray(providerFound) ? providerFound : []).map(item => ({ provider, item }));
      } catch { return []; }
    }));
    if (controller.signal.aborted || generation !== searchGeneration || !authContextIsCurrent(started) ||
        !open || q !== query.trim()) return;
    found = results.flat();
    searching = false;
    searchController = null;
    if (open) paint();
  }, 200);
}

function pick(it) { close(); it.run(); }

function onKeys(e) {
  const list = items();
  if (e.key === 'ArrowDown') { e.preventDefault(); index = Math.min(index + 1, list.length - 1); paint(); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); index = Math.max(index - 1, 0); paint(); }
  else if (e.key === 'Enter') { e.preventDefault(); if (list[index]) pick(list[index]); }
}

export function togglePalette() { open ? close() : show(); }
export function show() {
  if (open || !state.user || !authContextIsCurrent(authContextSnapshot())) return;
  const backFocus = document.activeElement;
  retireSearch();
  open = true;
  query = ''; index = 0; found = [];
  pushOverlay('palette', close, () => {
    if (!(backFocus instanceof HTMLElement) || !backFocus.isConnected) return false;
    backFocus.focus();
    return document.activeElement === backFocus;
  });
  $('#palette-backdrop')?.classList.remove('hidden');
  paint();
  $('#palette-q')?.focus();
}
export function close() {
  if (!open) return;
  open = false;
  found = []; query = ''; searching = false;
  retireSearch();
  const box = $('#palette');
  if (box) box.replaceChildren();
  $('#palette-backdrop')?.classList.add('hidden');
  removeOverlay('palette');
}

export function paletteBoot() {
  $('#palette-backdrop')?.addEventListener('click', e => { if (e.target.id === 'palette-backdrop') close(); });
}
