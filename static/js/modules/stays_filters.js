/* ══════════════════════════════════════════════════════════════════════
   «ШАХМАТКА» — панель фильтров (§7), сортировка строк шахматки объектов,
   сохранённые наборы фильтров (localStorage, у пользователя в браузере).
   Внутри измерения — «или», между измерениями — «и», флаги — всегда «и»: так
   считает сервер, панель только собирает повторяемые параметры.
   Модуль на lit-html (ADR-0013, раздел 7): панель — шаблон, поле поиска живёт между перерисовками
   вида, поэтому фокус и курсор остаются на месте.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

import { state, toast } from '../core.js';
import { html, nothing } from '../ui/html.js';
import { staysEmptyFilters, staysState } from './stays.js';
import { boardState } from './stays_board.js';
import { staysBook, staysBookEmpty } from './stays_bookings.js';
import { staysBlock, staysBlockEmpty } from './stays_blocks.js';
import { staysOoo, staysOooEmpty } from './stays_ooo.js';

const STAYS_FILTERS_KEY = 'stays.filters';   // + '.<id пользователя>': на общем устройстве наборы не смешиваются
export const STAYS_SORTS = [['tree', 'по дереву'], ['label', 'по номеру'], ['category', 'по категории'],
  ['floor', 'по этажу'], ['load', 'по загрузке за месяц']];
export const staysFilterOpen = new Set();   // раскрытые списки панели — переживают перерисовку
/* панель фильтров на телефоне свёрнута за кнопку «Фильтры (N)»: раскрытые списки и
   чекбоксы занимали весь первый экран до самой доски. Состояние — на уровне модуля,
   переживает перерисовки вида (сбрасывается сменой пользователя). */
let sfPanelOpen = false;
/* набираемый поиск: перерисовка вида после паузы не отнимает фокус и не теряет символы,
   набранные, пока шёл запрос (сбрасывается при смене пользователя) */
let staysSearchDraft = null;         // { value, caret }
/* чтение и запись черновика поиска для файлов раздела: staysSearchState() — прочитать, staysSearchState(v) — записать */
export function staysSearchState(...args) {
  if (args.length) staysSearchDraft = args[0];
  return staysSearchDraft;
}

/* смена пользователя устройства (resetUserViewState, app.js): ничего от прежнего не остаётся */
export function staysResetUserState() {
  Object.assign(staysState, { tab: 'units', fund: null, filters: staysEmptyFilters(),
    sort: { by: 'tree', dir: 'asc', grouped: true }, collapsed: {}, ocOpen: {}, ocMode: 'pct', focusDay: null });
  Object.assign(boardState, { day: null, tab: 'arrivals' });
  Object.assign(staysBook, staysBookEmpty());
  Object.assign(staysBlock, staysBlockEmpty());
  Object.assign(staysOoo, staysOooEmpty());
  staysFilterOpen.clear();
  sfPanelOpen = false;
  staysSearchDraft = null;
}

/* ─────────────── Сохранённые наборы ─────────────── */
/* Наборы — у каждого пользователя свои (ключ с id), и в них только устройство фонда:
   поиск (фамилия, № брони, телефон), «Особый гость» и VIP-код не сохраняются — персональные данные гостей не
   остаются в браузере после выхода. Хранилища может не быть (приватный режим, запрет
   сайта) — тогда наборов просто нет; без пользователя — тоже. */
function staysFiltersKey() {
  const id = state.user?.id;
  return id == null ? null : `${STAYS_FILTERS_KEY}.${id}`;
}
export function staysSavedFilters() {
  try {
    const key = staysFiltersKey();
    if (!key) return [];
    window.localStorage.removeItem(STAYS_FILTERS_KEY);   // общий ключ ранней сборки — с поиском внутри
    const list = JSON.parse(window.localStorage.getItem(key) || '[]');
    return Array.isArray(list) ? list.filter(x => x && typeof x.name === 'string' && x.filters) : [];
  } catch {
    return [];
  }
}
function staysWriteFilters(list) {
  try {
    const key = staysFiltersKey();
    if (!key) return false;
    window.localStorage.setItem(key, JSON.stringify(list));
    return true;
  } catch {
    return false;
  }
}
export function staysSaveFilter(name, filters) {
  const n = String(name || '').trim();
  if (!n) return false;
  const fund = staysCleanFilters(filters);
  delete fund.q;
  delete fund.special;
  delete fund.vip_code_ids;
  const { by, dir, grouped } = staysState.sort;
  return staysWriteFilters([...staysSavedFilters().filter(x => x.name !== n),
    { name: n, filters: fund, sort: { by, dir, grouped } }]);
}
function staysDeleteFilter(name) {
  return staysWriteFilters(staysSavedFilters().filter(x => x.name !== name));
}
/* набор из хранилища мог быть записан старой версией или руками — только известные поля */
export function staysCleanFilters(f) {
  const ids = v => (Array.isArray(v) ? v.map(Number).filter(Number.isInteger) : []);
  return { ...staysEmptyFilters(), group_ids: ids(f?.group_ids), category_ids: ids(f?.category_ids),
    flag_ids: ids(f?.flag_ids), kind_ids: ids(f?.kind_ids),
    escorted: !!f?.escorted, special: !!(f?.special ?? f?.vip),   // vip — прежнее имя поля сохранённого набора
    vip_code_ids: ids(f?.vip_code_ids), q: typeof f?.q === 'string' ? f.q : '' };
}

/* ─────────────── Панель ─────────────── */
/* узлы дерева в порядке обхода: родитель, затем дети по sort_order */
function staysTreeOrder(groups) {
  const kids = {};
  groups.forEach(g => { (kids[g.parent_id ?? 'root'] ||= []).push(g); });
  Object.values(kids).forEach(l => l.sort((a, b) => a.sort_order - b.sort_order || a.id - b.id));
  const out = [];
  const walk = (key, depth) => (kids[key] || []).forEach(g => { out.push({ g, depth }); walk(g.id, depth + 1); });
  walk('root', 0);
  return out;
}

/* виды для фильтра: архивный вид — только пока он стоит у категории фонда */
function staysKindChoices(fund) {
  const used = new Set(fund.categories.map(c => c.kind_id));
  return (fund.kinds || []).filter(k => !k.archived || used.has(k.id));
}

/* флажок списка: имя data-атрибута у каждого списка своё (его читают сценарии и обработчики) */
const CHECKBOX = {
  group: (v, on) => html`<input type="checkbox" data-sf-group=${v} .checked=${on}>`,
  cat: (v, on) => html`<input type="checkbox" data-sf-cat=${v} .checked=${on}>`,
  flag: (v, on) => html`<input type="checkbox" data-sf-flag=${v} .checked=${on}>`,
  kind: (v, on) => html`<input type="checkbox" data-sf-kind=${v} .checked=${on}>`,
  vipcode: (v, on) => html`<input type="checkbox" data-sf-vipcode=${v} .checked=${on}>`,
};
let lastSavedName = '';           // имя только что сохранённого набора: он выбран в списке после перерисовки панели

/* people — фильтры по гостям (поиск, VIP); уровню occupancy их не показываем: сервер их
   для него не применяет. Шаблон: панель встраивается прямо в вид. */
export function filterPanelTemplate(fund, filters, onChange, { people = true, onSearchInput } = {}) {
  const f = staysCleanFilters(filters);
  const emit = patch => { lastSavedName = ''; onChange({ ...f, ...patch }); };
  const list = (key, field, cast, title, items, chosen) => {
    const picked = items.filter(i => chosen.includes(i.value)).map(i => i.label);
    return html`<details class="sf-dd" data-sf-dd=${key} ?open=${staysFilterOpen.has(key)}
      @toggle=${e => { if (e.target.open) staysFilterOpen.add(key); else staysFilterOpen.delete(key); }}>
      <summary>${title}: <b>${picked.length ? picked.join(', ') : 'все'}</b></summary>
      <div class="sf-list">${items.length ? items.map(i => html`<label class="chk" style=${`padding-left:${(i.depth || 0) * 14}px`}>
        ${CHECKBOX[key](String(i.value), chosen.includes(i.value))} ${i.label}</label>`) : html`<span class="muted">нет</span>`}</div></details>`;
  };
  const onList = (field, key, cast) => e => {
    const box = e.target.closest('.sf-list');
    emit({ [field]: [...box.querySelectorAll('input[type=checkbox]')].filter(x => x.checked)
      .map(x => cast(x.getAttribute(`data-sf-${key}`))) });
  };
  const lists = [
    ['group', 'group_ids', 'Где', staysTreeOrder(fund.groups).map(({ g, depth }) => ({ value: g.id, label: g.title, depth })), f.group_ids],
    ['cat', 'category_ids', 'Категории', fund.categories.map(c => ({ value: c.id, label: c.code })), f.category_ids],
    ['flag', 'flag_ids', 'Флаги', (fund.flags || []).filter(x => !x.archived).map(x => ({ value: x.id, label: x.title })), f.flag_ids],
    ['kind', 'kind_ids', 'Вид', staysKindChoices(fund).map(k => ({ value: k.id, label: k.title })), f.kind_ids],
  ];
  const view = ([key, field, title, items, chosen]) => html`<div @change=${onList(field, key, Number)} style="display:contents">${list(key, field, Number, title, items, chosen)}</div>`;
  const vipItems = (fund.vip_codes || []).filter(c => !c.archived || f.vip_code_ids.includes(c.id))
    .map(c => ({ value: c.id, label: c.code + (c.archived ? ' (в архиве)' : '') }));
  const saved = staysSavedFilters();
  /* активные фильтры — чипами с индивидуальным снятием: видно, что доска отфильтрована,
     и что снять, не раскрывая списки. Значения — из тех же списков, что панель. */
  const titleOf = (items, id) => items.find(i => i.value === id)?.label ?? String(id);
  const chip = (label, clear) => html`<span class="chip">${label}<button class="chip-x" title="Убрать фильтр"
    aria-label=${`Убрать фильтр «${label}»`} @click=${clear}><span aria-hidden="true">✕</span></button></span>`;
  const chips = html`
    ${f.group_ids.map(id => chip(titleOf(lists[0][3], id), () => emit({ group_ids: f.group_ids.filter(x => x !== id) })))}
    ${f.category_ids.map(id => chip(titleOf(lists[1][3], id), () => emit({ category_ids: f.category_ids.filter(x => x !== id) })))}
    ${f.flag_ids.map(id => chip(titleOf(lists[2][3], id), () => emit({ flag_ids: f.flag_ids.filter(x => x !== id) })))}
    ${f.kind_ids.map(id => chip(titleOf(lists[3][3], id), () => emit({ kind_ids: f.kind_ids.filter(x => x !== id) })))}
    ${f.escorted ? chip('с сопровождением', () => emit({ escorted: false })) : nothing}
    ${people && f.special ? chip('◆ особый гость', () => emit({ special: false })) : nothing}
    ${people ? f.vip_code_ids.map(id => chip(titleOf(vipItems, id), () => emit({ vip_code_ids: f.vip_code_ids.filter(x => x !== id) }))) : nothing}`;
  const activeCount = f.group_ids.length + f.category_ids.length + f.flag_ids.length + f.kind_ids.length
    + (f.escorted ? 1 : 0) + (people && f.special ? 1 : 0) + f.vip_code_ids.length;
  let timer = null;
  return html`<div class="sb-toolbar sf-bar">
    <button class="btn btn-sm sf-toggle only-mobile" aria-expanded=${sfPanelOpen ? 'true' : 'false'}
      @click=${e => { sfPanelOpen = !sfPanelOpen; e.target.closest('.sf-bar').nextElementSibling.classList.toggle('open', sfPanelOpen);
        e.target.setAttribute('aria-expanded', String(sfPanelOpen)); }}>
      Фильтры${activeCount ? html` <b>(${activeCount})</b>` : nothing}</button>
    ${chips}
    ${people ? html`<input type="search" id="sf-q" placeholder="фамилия, № брони, объект, телефон" .value=${staysSearchDraft?.value ?? f.q}
        @input=${e => {
          staysSearchDraft = { value: e.target.value, caret: e.target.selectionStart };
          onSearchInput?.();
          clearTimeout(timer);
          const value = e.target.value;
          timer = setTimeout(() => emit({ q: value }), 350);
        }}>` : nothing}
  </div>
  <div class="sb-toolbar sf-panel${sfPanelOpen ? ' open' : ''}">
    ${lists.map(view)}
    <label class="chk"><input type="checkbox" id="sf-esc" .checked=${f.escorted} @change=${e => emit({ escorted: e.target.checked })}> с сопровождением</label>
    ${people ? html`<label class="chk"><input type="checkbox" id="sf-special" .checked=${f.special} @change=${e => emit({ special: e.target.checked })}> ◆ Особый гость</label>
      <div @change=${onList('vip_code_ids', 'vipcode', Number)} style="display:contents">${list('vipcode', 'vip_code_ids', Number, 'VIP-код', vipItems, f.vip_code_ids)}</div>` : nothing}
    <div class="sf-saved-row">
    <select id="sf-saved" title="Сохранённые наборы фильтров" @change=${e => {
        const s = staysSavedFilters().find(x => x.name === e.target.value);
        if (!s) return;
        /* набор — устройство фонда и сортировка; поиск, «Особый гость» и VIP-код остаются как были */
        const sort = s.sort || {};
        if (STAYS_SORTS.some(([v]) => v === sort.by)) staysState.sort.by = sort.by;
        if (sort.dir === 'asc' || sort.dir === 'desc') staysState.sort.dir = sort.dir;
        if (typeof sort.grouped === 'boolean') staysState.sort.grouped = sort.grouped;
        lastSavedName = '';
        onChange({ ...staysCleanFilters(s.filters), q: f.q, special: f.special, vip_code_ids: f.vip_code_ids });
      }}><option value="">Наборы…</option>${saved.map(s => html`<option value=${s.name} ?selected=${s.name === lastSavedName}>${s.name}</option>`)}</select>
    ${saved.length ? html`<button class="btn btn-sm btn-ghost" id="sf-del" title="Удалить выбранный набор" @click=${e => {
        const name = e.target.closest('.sf-panel').querySelector('#sf-saved').value;
        if (!name) { toast('Выберите набор в списке', 'warn'); return; }
        staysDeleteFilter(name);
        lastSavedName = '';
        onChange(f);
      }}>✕</button>` : nothing}
    <input type="text" id="sf-save-name" placeholder="имя набора" maxlength="60">
    <button class="btn btn-sm btn-ghost" id="sf-save" @click=${e => {
        const name = e.target.closest('.sf-panel').querySelector('#sf-save-name').value.trim();
        if (!name) { toast('Введите имя набора', 'warn'); return; }
        if (!staysSaveFilter(name, f)) { toast('Браузер не даёт сохранить набор', 'warn'); return; }
        toast('Набор «' + name + '» сохранён');
        lastSavedName = name;
        onChange(f);
      }}>Сохранить набор</button>
    <button class="btn btn-sm btn-ghost" id="sf-reset" @click=${() => { staysSearchDraft = null; lastSavedName = ''; onChange(staysEmptyFilters()); }}>Сбросить</button>
    </div>
  </div>`;
}


/* ─────────────── Сортировка строк шахматки объектов (§7) ─────────────── */
/* Номер и категория — по значению на первый день месяца (label / category_id строки).
   grouped — сортировка внутри разделов дерева; иначе плоский список. */
export function staysSortRows(rows, { by = 'tree', dir = 'asc', grouped = true } = {}, fund) {
  const cats = Object.fromEntries((fund?.categories || []).map(c => [c.id, c]));
  const groups = Object.fromEntries((fund?.groups || []).map(g => [g.id, g]));
  const nat = (a, b) => String(a).localeCompare(String(b), 'ru', { numeric: true, sensitivity: 'base' });
  const catOrder = r => cats[r.category_id]?.sort_order ?? 1e9;
  const node = id => [groups[id]?.sort_order ?? 1e9, id];
  /* разделы: по порядку узлов от корня; объекты самого узла — перед дочерними; без узла — в конце */
  const cmpTree = (a, b) => {
    const pa = a.group_path, pb = b.group_path;
    if (!pa.length || !pb.length) return (pa.length ? 0 : 1) - (pb.length ? 0 : 1);
    for (let i = 0; i < Math.min(pa.length, pb.length); i++) {
      if (pa[i] === pb[i]) continue;
      const [oa, ia] = node(pa[i]), [ob, ib] = node(pb[i]);
      return oa - ob || ia - ib;
    }
    return pa.length - pb.length;
  };
  const byTree = (a, b) => catOrder(a) - catOrder(b) || nat(a.label, b.label);
  const emptyLast = (a, b) => (a ? 0 : 1) - (b ? 0 : 1);
  const key = {
    tree: byTree,
    label: (a, b) => nat(a.label, b.label),
    category: (a, b) => catOrder(a) - catOrder(b) || nat(cats[a.category_id]?.code || '', cats[b.category_id]?.code || ''),
    floor: (a, b) => nat(a.floor || '', b.floor || ''),
    load: (a, b) => a.load - b.load,
  }[by] || byTree;
  const sign = dir === 'desc' ? -1 : 1;
  return [...rows].sort((a, b) => (grouped ? cmpTree(a, b) : 0)
    || (by === 'floor' ? emptyLast(a.floor, b.floor) : 0)
    || sign * key(a, b) || byTree(a, b) || a.unit_id - b.unit_id);
}
