/* ══════════════════════════════════════════════════════════════════════
   ПАЛИТРА КОМАНД (⌘K / Ctrl+K): разделы меню, действия модулей, живой
   поиск гостей. Открывается из любого места, Esc/✕ закрывает, ↑↓ + Enter
   или клик. На телефоне — почти на весь экран. Компонент живёт в ui/ и
   не знает о модулях: app.js сообщает переходы (из меню), модули
   добавляют свои действия через register(), поиск гостей — здесь же.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

import { $, api, authContextIsCurrent, authContextSnapshot, state, toast } from '../core.js';
import { html, mount, render } from './html.js';

/* действия модулей: {id, title, hint, run, when?} — when() решает видимость по правам */
let actions = [];
export function paletteRegister(action) { actions = [...actions.filter(a => a.id !== action.id), action]; }

let open = false;
let query = '';
let index = 0;            /* выбранный пункт списка */
let found = [];           /* гости из живого поиска */
let searching = false;
let timer = null;
let backFocus = null;

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
function guestItems() {
  return found.map(g => ({ key: 'guest:' + g.id, icon: 'guests', title: g.short, hint: 'гость',
                           run: () => { close(); import('../modules/stays_forms.js').then(m => m.openGuestCard(g.id)).catch(e => toast(e.message, 'err')); } }));
}

function items() { return [...navItems(query), ...actionItems(query), ...guestItems()]; }

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
        <span class="palette-item-title">${it.title}</span><span class="muted">${it.hint}</span>
      </button>`) : html`<div class="muted" style="padding:10px 12px">${searching ? 'ищем…' : 'ничего не найдено'}</div>`}
    </div></div>`, mount(box));
  $('#palette-q')?.focus();
}

function scheduleSearch() {
  clearTimeout(timer);
  const q = query.trim();
  if (q.length < 2) { found = []; return; }
  timer = setTimeout(async () => {
    const started = authContextSnapshot();
    searching = true;
    try {
      const guests = await api(`/api/stays/guests?q=${encodeURIComponent(q)}${canAllGuests() ? '' : '&mine=1'}`, { silent: true });
      if (!authContextIsCurrent(started) || !open || q !== query.trim()) return;
      found = guests;
    } catch { found = []; }
    searching = false;
    if (open) paint();
  }, 200);
}
const canAllGuests = () => (state.perms || []).includes('stays.guests');

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
  open = true;
  query = ''; index = 0; found = [];
  backFocus = document.activeElement;
  $('#palette-backdrop')?.classList.remove('hidden');
  paint();
}
export function close() {
  if (!open) return;
  open = false;
  found = []; query = ''; searching = false;
  clearTimeout(timer);
  const box = $('#palette');
  if (box) box.replaceChildren();
  $('#palette-backdrop')?.classList.add('hidden');
  backFocus?.focus?.();
}

export function paletteBoot() {
  document.addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); togglePalette(); }
  });
  /* Esc — в фазе захвата и с отсечкой: палитра закрывается первой, drawer и
     модалка под ней (их обработчик в core.js — пузырьковая фаза) остаются */
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && open) { e.stopPropagation(); close(); }
  }, true);
  $('#palette-backdrop')?.addEventListener('click', e => { if (e.target.id === 'palette-backdrop') close(); });
}
