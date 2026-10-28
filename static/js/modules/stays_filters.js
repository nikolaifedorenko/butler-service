/* ══════════════════════════════════════════════════════════════════════
   «ШАХМАТКА» — панель фильтров (§7), сортировка строк шахматки объектов,
   сохранённые наборы фильтров (localStorage, у пользователя в браузере).
   Внутри измерения — «или», между измерениями — «и», флаги — всегда «и»: так
   считает сервер, панель только собирает повторяемые параметры.
   Использует хелперы app.js: $ $$ esc toast.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

const STAYS_FILTERS_KEY = 'stays.filters';   // + '.<id пользователя>': на общем устройстве наборы не смешиваются
const STAYS_SORTS = [['tree', 'по дереву'], ['label', 'по номеру'], ['category', 'по категории'],
  ['floor', 'по этажу'], ['load', 'по загрузке за месяц']];
const staysFilterOpen = new Set();   // раскрытые списки панели — переживают перерисовку
/* набираемый поиск: перерисовка вида после паузы не отнимает фокус и не теряет символы,
   набранные, пока шёл запрос (сбрасывается при смене пользователя) */
let staysSearchDraft = null;         // { value, caret }

/* смена пользователя устройства (resetUserViewState, app.js): ничего от прежнего не остаётся */
function staysResetUserState() {
  Object.assign(staysState, { tab: 'units', fund: null, filters: staysEmptyFilters(),
    sort: { by: 'tree', dir: 'asc', grouped: true }, collapsed: {}, ocOpen: {}, ocMode: 'pct', focusDay: null });
  Object.assign(boardState, { day: null, tab: 'arrivals' });
  staysFilterOpen.clear();
  staysSearchDraft = null;
}

/* ─────────────── Сохранённые наборы ─────────────── */
/* Наборы — у каждого пользователя свои (ключ с id), и в них только устройство фонда:
   поиск (фамилия, № брони, телефон) и VIP не сохраняются — персональные данные гостей не
   остаются в браузере после выхода. Хранилища может не быть (приватный режим, запрет
   сайта) — тогда наборов просто нет; без пользователя — тоже. */
function staysFiltersKey() {
  const id = state.user?.id;
  return id == null ? null : `${STAYS_FILTERS_KEY}.${id}`;
}
function staysSavedFilters() {
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
function staysSaveFilter(name, filters) {
  const n = String(name || '').trim();
  if (!n) return false;
  const fund = staysCleanFilters(filters);
  delete fund.q;
  delete fund.vip;
  const { by, dir, grouped } = staysState.sort;
  return staysWriteFilters([...staysSavedFilters().filter(x => x.name !== n),
    { name: n, filters: fund, sort: { by, dir, grouped } }]);
}
function staysDeleteFilter(name) {
  return staysWriteFilters(staysSavedFilters().filter(x => x.name !== name));
}
/* набор из хранилища мог быть записан старой версией или руками — только известные поля */
function staysCleanFilters(f) {
  const ids = v => (Array.isArray(v) ? v.map(Number).filter(Number.isInteger) : []);
  return { ...staysEmptyFilters(), group_ids: ids(f?.group_ids), category_ids: ids(f?.category_ids),
    flag_ids: ids(f?.flag_ids), kinds: Array.isArray(f?.kinds) ? f.kinds.map(String) : [],
    escorted: !!f?.escorted, vip: !!f?.vip, q: typeof f?.q === 'string' ? f.q : '' };
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

/* people — фильтры по гостям (поиск, VIP); уровню occupancy их не показываем: сервер их
   для него не применяет (находка C1 аудита) */
function staysFilterPanel(fund, filters, onChange, { people = true } = {}) {
  const f = staysCleanFilters(filters);
  const el = document.createElement('div');
  el.className = 'sb-toolbar sf-panel';
  const list = (key, title, items, chosen) => {
    const picked = items.filter(i => chosen.includes(i.value)).map(i => i.label);
    return `<details class="sf-dd" data-sf-dd="${key}"${staysFilterOpen.has(key) ? ' open' : ''}>
      <summary>${esc(title)}: <b>${esc(picked.length ? picked.join(', ') : 'все')}</b></summary>
      <div class="sf-list">${items.map(i => `<label class="chk" style="padding-left:${(i.depth || 0) * 14}px">
        <input type="checkbox" data-sf-${key}="${esc(String(i.value))}"${chosen.includes(i.value) ? ' checked' : ''}> ${esc(i.label)}</label>`).join('')
        || '<span class="muted">нет</span>'}</div></details>`;
  };
  const saved = staysSavedFilters();
  el.innerHTML = `
    ${list('group', 'Где', staysTreeOrder(fund.groups).map(({ g, depth }) => ({ value: g.id, label: g.title, depth })), f.group_ids)}
    ${list('cat', 'Категории', fund.categories.map(c => ({ value: c.id, label: c.code })), f.category_ids)}
    ${list('flag', 'Флаги', (fund.flags || []).filter(x => !x.archived).map(x => ({ value: x.id, label: x.title })), f.flag_ids)}
    ${list('kind', 'Вид', fund.kinds.map(k => ({ value: k.code, label: k.title })), f.kinds)}
    <label class="chk"><input type="checkbox" id="sf-esc"${f.escorted ? ' checked' : ''}> с сопровождением</label>
    ${people ? `<label class="chk"><input type="checkbox" id="sf-vip"${f.vip ? ' checked' : ''}> VIP/VVIP</label>
      <input type="search" id="sf-q" placeholder="фамилия, № брони, объект, телефон" value="${esc(staysSearchDraft?.value ?? f.q)}">` : ''}
    <select id="sf-saved" title="Сохранённые наборы фильтров"><option value="">Наборы…</option>${saved.map(s =>
      `<option value="${esc(s.name)}">${esc(s.name)}</option>`).join('')}</select>
    ${saved.length ? '<button class="btn btn-sm btn-ghost" id="sf-del" title="Удалить выбранный набор">✕</button>' : ''}
    <input type="text" id="sf-save-name" placeholder="имя набора" maxlength="60">
    <button class="btn btn-sm btn-ghost" id="sf-save">Сохранить набор</button>
    <button class="btn btn-sm btn-ghost" id="sf-reset">Сбросить</button>`;

  const emit = patch => onChange({ ...f, ...patch });
  $$('[data-sf-dd]', el).forEach(d => {
    d.addEventListener('toggle', () => { if (d.open) staysFilterOpen.add(d.dataset.sfDd); else staysFilterOpen.delete(d.dataset.sfDd); });
  });
  [['group', 'group_ids', Number], ['cat', 'category_ids', Number], ['flag', 'flag_ids', Number], ['kind', 'kinds', String]]
    .forEach(([key, field, cast]) => {
      $$(`[data-sf-${key}]`, el).forEach(cb => {
        cb.onchange = () => emit({ [field]: $$(`[data-sf-${key}]`, el).filter(x => x.checked).map(x => cast(x.getAttribute(`data-sf-${key}`))) });
      });
    });
  $('#sf-esc', el).onchange = e => emit({ escorted: e.target.checked });
  if (people) {
    $('#sf-vip', el).onchange = e => emit({ vip: e.target.checked });
    let timer = null;
    $('#sf-q', el).oninput = e => {
      staysSearchDraft = { value: e.target.value, caret: e.target.selectionStart };
      clearTimeout(timer);
      timer = setTimeout(() => emit({ q: e.target.value }), 350);
    };
  }
  $('#sf-saved', el).onchange = e => {
    const s = staysSavedFilters().find(x => x.name === e.target.value);
    if (!s) return;
    /* набор — устройство фонда и сортировка; поиск и VIP остаются как были */
    const sort = s.sort || {};
    if (STAYS_SORTS.some(([v]) => v === sort.by)) staysState.sort.by = sort.by;
    if (sort.dir === 'asc' || sort.dir === 'desc') staysState.sort.dir = sort.dir;
    if (typeof sort.grouped === 'boolean') staysState.sort.grouped = sort.grouped;
    onChange({ ...staysCleanFilters(s.filters), q: f.q, vip: f.vip });
  };
  const del = $('#sf-del', el);
  if (del) del.onclick = () => {
    const name = $('#sf-saved', el).value;
    if (!name) { toast('Выберите набор в списке', 'warn'); return; }
    staysDeleteFilter(name);
    el.replaceWith(staysFilterPanel(fund, f, onChange, { people }));
  };
  $('#sf-save', el).onclick = () => {
    const name = $('#sf-save-name', el).value.trim();
    if (!name) { toast('Введите имя набора', 'warn'); return; }
    if (!staysSaveFilter(name, f)) { toast('Браузер не даёт сохранить набор', 'warn'); return; }
    toast('Набор «' + name + '» сохранён');
    const fresh = staysFilterPanel(fund, f, onChange, { people });
    el.replaceWith(fresh);
    $('#sf-saved', fresh).value = name;
  };
  $('#sf-reset', el).onclick = () => { staysSearchDraft = null; onChange(staysEmptyFilters()); };
  return el;
}

/* ─────────────── Сортировка строк шахматки объектов (§7) ─────────────── */
/* Номер и категория — по значению на первый день месяца (label / category_id строки).
   grouped — сортировка внутри разделов дерева; иначе плоский список. */
function staysSortRows(rows, { by = 'tree', dir = 'asc', grouped = true } = {}, fund) {
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
