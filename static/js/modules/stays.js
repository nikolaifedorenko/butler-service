/* ══════════════════════════════════════════════════════════════════════
   РАЗДЕЛ «ШАХМАТКА» — фонд, гости, брони, сопровождение батлерами
   (спецификация docs/superpowers/specs/2026-10-23-stays-chessboard-design.md).
   Вкладки: шахматка объектов, шахматка батлеров, табло дня, сводная загрузка.
   Полосы броней — по половинкам суток (PoC §5): позиция = ordinal·2 + half.
   Сервер сам решает, какие поля гостя видны (§8): без прав полос нет фамилий.
   Использует хелперы app.js: $ $$ esc api openModal closeModal toast can dateRu.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

registerModule({ views: { stays: loadStays, mystays: loadMyStays } });

const STAYS_TABS = [['units', 'Объекты'], ['butlers', 'Батлеры'], ['day', 'Табло дня'], ['occupancy', 'Загрузка'], ['bookings', 'Брони']];
const STAYS_LEVEL_MARK = { vip: '★VIP ', vvip: '★VVIP ' };
/* месяц видов — общий state.year / state.month (как Табель и График, §6); фильтры — одна
   панель на все виды (§7); collapsed — разделы дерева, свёрнутые / развёрнутые пользователем */
const staysState = {
  tab: 'units', fund: null, filters: staysEmptyFilters(),
  sort: { by: 'tree', dir: 'asc', grouped: true }, collapsed: {},
  ocOpen: {}, ocMode: 'pct', focusDay: null,
};
function staysEmptyFilters() {
  return { group_ids: [], category_ids: [], flag_ids: [], kind_ids: [], escorted: false, vip: false, q: '' };
}

/* PoC §5.1: ordinal как в Python date.toordinal() — клиент и сервер считают позиции одинаково */
function staysOrdinal(y, m, d) { return Math.round(Date.UTC(y, m - 1, d) / 86400000) + 719163; }
function staysPos(iso, half) { const [y, m, d] = iso.split('-').map(Number); return staysOrdinal(y, m, d) * 2 + half; }
function staysAddDays(iso, n) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}
/* «сегодня» — по часам объекта (APP_TZ сервера), как Табель: todayISO() из core.js */
function staysToday() { return todayISO(); }
/* границы общего месяца разделов */
function staysMonthRange() {
  const mm = String(state.month).padStart(2, '0');
  const days = new Date(Date.UTC(state.year, state.month, 0)).getUTCDate();
  return { first: `${state.year}-${mm}-01`, last: `${state.year}-${mm}-${String(days).padStart(2, '0')}` };
}
function staysMonthNav() {
  return `<div class="month-nav"><button id="sm-prev" title="Предыдущий месяц">◀</button>
    <div class="label" id="sm-label">${esc(MONTHS[state.month - 1])} ${state.year}</div>
    <button id="sm-next" title="Следующий месяц">▶</button></div>
    <button class="btn btn-sm" id="sm-today" title="Текущий месяц и колонка сегодняшнего дня">Сегодня</button>`;
}
/* ◀ ▶ — как Табель (v4BindMonthNav); «Сегодня» — текущий месяц, докрутка и подсветка дня */
function staysBindMonthNav(body, rerender) {
  const shift = delta => {
    let m = state.month + delta, y = state.year;
    if (m < 1) { m = 12; y--; } if (m > 12) { m = 1; y++; }
    state.month = m; state.year = y;
    staysState.focusDay = null;     // «Сегодня» прошлого месяца не докручивает новый
    rerender();
  };
  $('#sm-prev', body).onclick = () => shift(-1);
  $('#sm-next', body).onclick = () => shift(1);
  $('#sm-today', body).onclick = () => {
    const today = staysToday();
    const [y, m] = today.split('-').map(Number);
    staysState.focusDay = today;
    if (y === state.year && m === state.month) staysFocusDay(body);
    else { state.year = y; state.month = m; rerender(); }
  };
}
/* докрутка сетки к колонке staysState.focusDay и подсветка (как scrollTabelToToday) */
function staysFocusDay(body) {
  const day = staysState.focusDay;
  if (!day) return;
  staysState.focusDay = null;
  const grid = $('.sb-grid', body);
  const cell = grid && grid.querySelector(`.sb-head [data-day="${day}"]`);
  if (!cell) { toast('День не входит в открытый месяц', 'warn'); return; }
  /* позиция колонки в прокручиваемой сетке (offsetParent у разных видов разный); колонка
     объекта закреплена слева — середина видимой части без неё */
  const unitCol = cell.closest('.sb-head')?.firstElementChild?.clientWidth || 0;
  const x = cell.getBoundingClientRect().left - grid.getBoundingClientRect().left + grid.scrollLeft;
  grid.scrollTo({ left: Math.max(0, x - unitCol - (grid.clientWidth - unitCol) / 2 + cell.clientWidth / 2),
    behavior: 'smooth' });
  cell.classList.add('flash-today');
  setTimeout(() => cell.classList.remove('flash-today'), 1800);
}
/* измерения фонда (§7) — повторяемые параметры; общие для шахматки, «Загрузки» и табло */
function staysFundParams(p) {
  const f = staysState.filters;
  f.group_ids.forEach(v => p.append('group_ids', v));
  f.category_ids.forEach(v => p.append('category_ids', v));
  f.flag_ids.forEach(v => p.append('flag_ids', v));
  f.kind_ids.forEach(v => p.append('kind_ids', v));
  return p;
}
/* панель фильтров вида: изменение — новые фильтры и перерисовка вида */
function staysPanelInto(body, fund, rerender, opts) {
  const slot = $('[data-sf-slot]', body);
  if (!slot) return;
  const panel = staysFilterPanel(fund, staysState.filters, f => { staysState.filters = f; rerender(); }, opts);
  slot.replaceWith(panel);
  /* перерисовка после набора в поиске — фокус и курсор остаются в поле */
  const q = $('#sf-q', panel);
  if (staysSearchDraft && q) {
    q.focus();
    const c = Math.min(staysSearchDraft.caret ?? q.value.length, q.value.length);
    q.setSelectionRange(c, c);
    if (staysSearchDraft.value === staysState.filters.q) staysSearchDraft = null;
  }
}
/* Справочники модуля + фонд на сегодня (категории, узлы, объекты — версиями с даты, GET /fund/snapshot) */
async function staysFund(force = false) {
  if (!staysState.fund || force) {
    const [dicts, snap] = await Promise.all([api('/api/stays/fund', { silent: true }),
      api('/api/stays/fund/snapshot?date=' + staysToday(), { silent: true })]);
    const groups = Object.fromEntries(snap.groups.map(g => [g.id, g]));
    staysState.fund = { ...dicts, categories: snap.categories, groups: snap.groups, flags: snap.flags, kinds: snap.kinds,
      /* объект снимка есть в фонде дня — «активен»; путь узла названиями — для подписи */
      units: snap.units.map(u => ({ ...u, active: true, group: u.path.map(id => groups[id]?.title || '').join(' / ') })) };
  }
  return staysState.fund;
}

async function loadStays() {
  const host = $('#view-stays');
  host.innerHTML = `
    <div class="page-head"><div><h2>Шахматка</h2><div class="sub">Кто где живёт и кто из батлеров ведёт гостей</div></div></div>
    <div class="layer-tabs">${STAYS_TABS.filter(([id]) => (id !== 'butlers' && id !== 'bookings') || can('stays.view')).map(([id, t]) =>
      `<button class="btn btn-sm${staysState.tab === id ? ' btn-primary' : ''}" data-stab="${id}">${esc(t)}</button>`).join('')}</div>
    <div id="stays-body"><div class="empty">Загрузка…</div></div>`;
  $$('[data-stab]', host).forEach(b => { b.onclick = () => { staysState.tab = b.dataset.stab; loadStays(); }; });
  const body = $('#stays-body', host);
  try {
    await staysFund(true);          // фонд меняют в Настройках — при каждом открытии раздела заново
    await staysTabRender(staysState.tab)(body);
  } catch (e) {
    body.innerHTML = `<div class="panel"><p class="muted">${esc(e.message)}</p></div>`;
  }
}
/* вкладки из других файлов раздела — по имени при вызове: файлы грузятся по алфавиту */
function staysTabRender(tab) {
  return { units: renderUnitsBoard, butlers: renderButlersBoard, day: renderDayBoard,
    occupancy: renderOccupancyGrid, bookings: renderBookings }[tab] || renderUnitsBoard;
}

async function loadMyStays() {
  await renderMine();
}

/* ─────────────── Шахматка объектов ─────────────── */
function staysToolbar() {
  const st = staysState.sort;
  return `<div class="sb-toolbar">
    ${staysMonthNav()}
    <select id="sb-sort" title="Сортировка строк">${STAYS_SORTS.map(([v, t]) =>
      `<option value="${v}"${v === st.by ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select>
    <select id="sb-dir" title="Направление"><option value="asc"${st.dir === 'asc' ? ' selected' : ''}>↑</option>
      <option value="desc"${st.dir === 'desc' ? ' selected' : ''}>↓</option></select>
    <label class="chk"><input type="checkbox" id="sb-grouped"${st.grouped ? ' checked' : ''}> группировать по дереву</label>
    <button class="btn btn-sm btn-ghost" id="sb-xlsx-anon" title="Объекты, даты, статусы, число гостей — без данных гостей">Выгрузить (без гостей)</button>
    ${can('stays.export') && can('stays.guests') ? '<button class="btn btn-sm btn-ghost" id="sb-xlsx-full">Выгрузить полностью</button>' : ''}
    ${can('stays.edit') ? '<button class="btn btn-sm btn-primary" id="sb-new">+ Бронь</button>' : ''}
  </div>`;
}

function staysBoardParams() {
  const f = staysState.filters;
  const { first, last } = staysMonthRange();
  const p = staysFundParams(new URLSearchParams({ first, last }));
  if (f.escorted) p.set('escorted', '1');
  if (f.vip) p.set('vip', '1');
  if (f.q.trim()) p.set('q', f.q.trim());
  return p;
}

/* заголовок колонок дня — общий для видов месяца: data-day, «сегодня», выходные */
function staysDayHead(d, today) {
  const wd = new Date(d + 'T12:00:00Z').getUTCDay();
  return `<div data-day="${esc(d)}" class="${d === today ? 'today' : ''}${wd === 0 || wd === 6 ? ' we' : ''}">${Number(d.slice(8))}<small>${esc(WD_SHORT[(wd + 6) % 7])}</small></div>`;
}

/* цвет в style — только #RGB / #RRGGBB(AA): иначе текст цвета дописал бы CSS в атрибут */
function staysColor(c) { return /^#[0-9a-f]{3,8}$/i.test(c || '') ? c : '#999'; }

/* «4003 → 4103 с 15.11» — смена обозначения и категории внутри месяца (§6) */
function staysRowChanges(u, cats) {
  const ddmm = iso => `${iso.slice(8)}.${iso.slice(5, 7)}`;
  const chain = (items, name) => items.length > 1
    ? items.map((x, i) => (i ? ` → ${name(x)} с ${ddmm(x.from)}` : name(x))).join('') : '';
  return [chain(u.labels, x => x.label), chain(u.categories, x => cats[x.category_id]?.code || '#' + x.category_id)]
    .filter(Boolean).join(' · ');
}

function staysBarHtml(b, base, span, names) {
  const left = Math.max(0, (b.start_pos - base) / span * 100);
  const right = Math.min(100, (b.end_pos - base + 1) / span * 100);
  if (right <= 0 || left >= 100) return '';
  const color = names && b.label ? b.label.color : '#3b6fd8';
  const textHtml = names
    ? `${b.level !== 'regular' ? `<span class="sb-star">${esc(STAYS_LEVEL_MARK[b.level] || '')}</span>` : ''}${esc(b.main_guest || b.number || 'бронь')}`
    : `занято · ${b.guests_count} гост.`;
  const tip = names ? `${b.number} · ${dateRu(b.start)}–${dateRu(b.end)}` : `${dateRu(b.start)}–${dateRu(b.end)}`;
  return `<div class="sb-bar${b.status === 'tentative' ? ' tentative' : ''}" data-bar="${b.reservation_id}"
    style="left:${left}%;width:${right - left}%;background:${esc(color)}" title="${esc(tip)}">${textHtml}</div>`;
}

async function renderUnitsBoard(body) {
  const fund = await staysFund();
  /* ◀ ▶ и фильтры меняются подряд: запоздавший ответ перерисовал бы экран прежним месяцем
     (как Табель, PR #95) — поколение у контейнера вкладки (core.js) */
  const fresh = loadGenerationFor(body);
  const data = await api('/api/stays/board/units?' + staysBoardParams(), { silent: true });
  if (!fresh()) return;
  const names = data.visibility !== 'occupancy';
  const byUnit = {};
  data.bars.forEach(b => { (byUnit[b.unit_id ?? 'none'] ||= []).push(b); });
  const holdsBy = {};
  data.holds.forEach(h => { (holdsBy[h.unit_id] ||= []).push(h); });
  const rerender = () => renderUnitsBoard(body);
  body.innerHTML = `
    ${staysToolbar()}
    <div data-sf-slot></div>
    ${data.warnings.length ? `<div class="dict-banner gold"><span>⚠</span><span>${data.warnings.map(w => esc(w.text)).join('<br>')}</span></div>` : ''}
    <div class="sb-grid" style="--days:${data.days.length}"></div>
    ${(byUnit.none || []).length ? `<div class="panel"><h3 class="panel-title">Без объекта</h3>${byUnit.none.map(b =>
      `<div class="sb-unassigned" data-bar="${b.reservation_id}">${esc(names ? (b.number + ' · ' + (b.main_guest || '')) : 'бронь')} · ${esc(dateRu(b.start))}–${esc(dateRu(b.end))}</div>`).join('')}</div>` : ''}`;
  staysPanelInto(body, fund, rerender, { people: names });
  const grid = $('.sb-grid', body);
  /* сортировка и разделы — без нового запроса: перерисовка одной сетки */
  const paint = () => { grid.innerHTML = staysUnitsGridHtml(data, fund, byUnit, holdsBy, names); };
  paint();
  staysBindMonthNav(body, rerender);
  const st = staysState.sort;
  $('#sb-sort', body).onchange = e => { st.by = e.target.value; paint(); };
  $('#sb-dir', body).onchange = e => { st.dir = e.target.value; paint(); };
  $('#sb-grouped', body).onchange = e => { st.grouped = e.target.checked; paint(); };
  const xlsx = kind => () => {
    const { first, last } = staysMonthRange();
    downloadBlob('/api/stays/export?' + new URLSearchParams({ first, last, kind }), `shakhmatka_${kind}_${first}.xlsx`);
  };
  $('#sb-xlsx-anon', body).onclick = xlsx('anon');
  const full = $('#sb-xlsx-full', body);
  if (full) full.onclick = xlsx('full');
  const add = $('#sb-new', body);
  if (add) add.onclick = () => openReservationForm(null, { onSaved: rerender });
  if (names) $$('.sb-unassigned[data-bar]', body).forEach(el => { el.onclick = () => openReservationCard(Number(el.dataset.bar), rerender); });
  /* сетка — одним обработчиком: строк до 440, и они перерисовываются при сортировке */
  grid.onclick = e => {
    const sec = e.target.closest('[data-sec]');
    if (sec) {
      staysState.collapsed[sec.dataset.sec] = sec.dataset.open === '1';
      paint();
      return;
    }
    const bar = e.target.closest('[data-bar]');
    if (bar) { if (names) openReservationCard(Number(bar.dataset.bar), rerender); return; }
    if (!can('stays.edit')) return;
    /* блок / OOO: клик по объекту — новый, по полосе блока — правка или удаление */
    const hold = e.target.closest('[data-hold]');
    if (hold) { openHoldForm(data.holds.find(h => h.id === Number(hold.dataset.hold)), rerender); return; }
    const unit = e.target.closest('.sb-unit');
    const row = unit && unit.closest('[data-unit-row]');
    if (row) openHoldForm({ unit_id: Number(row.dataset.unitRow) }, rerender);
  };
  staysFocusDay(body);
}

/* Разделы дерева: по умолчанию развёрнут корневой раздел, где есть категория вида с
   «раскрывать» (справочник видов, §1 дополнения: виллы развёрнуты, корпус свёрнут), вложенные —
   развёрнуты; выбор пользователя — staysState.collapsed. Строки свёрнутого раздела в DOM не рисуются. */
function staysUnitsGridHtml(data, fund, byUnit, holdsBy, names) {
  const days = data.days;
  const n = days.length;
  const base = staysPos(days[0], 0);
  const span = n * 2;
  const dayIdx = Object.fromEntries(days.map((d, i) => [d, i]));
  const cats = Object.fromEntries(fund.categories.map(c => [c.id, c]));
  const groups = Object.fromEntries(fund.groups.map(g => [g.id, g]));
  const flags = Object.fromEntries((fund.flags || []).map(f => [f.id, f]));
  const expanded = new Set((fund.kinds || []).filter(k => k.expanded).map(k => k.id));
  const st = staysState.sort;
  const rows = staysSortRows(data.units, st, fund);
  const pathOf = u => (u.group_path.length ? u.group_path.map(String) : ['none']);
  const under = {};
  rows.forEach(u => pathOf(u).forEach(k => { (under[k] ||= []).push(u); }));
  const open = (key, depth) => {
    if (key in staysState.collapsed) return !staysState.collapsed[key];
    return depth > 0 || under[key].some(u => u.categories.some(c => expanded.has(cats[c.category_id]?.kind_id)));
  };
  const title = (u, i) => (u.group_path.length ? groups[u.group_path[i]]?.title || u.group.split(' / ')[i] || '#' + u.group_path[i] : 'Без группы');
  const pct = (a, b) => `left:${a / n * 100}%;width:${(b - a + 1) / n * 100}%`;
  const OFF = { absent: 'нет в фонде', filtered: 'вне фильтра' };
  const rowHtml = u => {
    const changes = staysRowChanges(u, cats);
    return `<div class="sb-row" data-unit-row="${u.unit_id}" data-root="${esc(pathOf(u)[0])}" data-load="${u.load}">
      <div class="sb-unit"><b>${esc(u.label)}</b><small>${esc(u.category)}${u.floor ? ' · эт. ' + esc(u.floor) : ''}
        ${u.flags.map(id => `<span class="sb-flag" style="background:${staysColor(flags[id]?.color)}" title="${esc(flags[id]?.title || '')}"></span>`).join('')}</small>
        ${changes ? `<small class="sb-change">${esc(changes)}</small>` : ''}</div>
      <div class="sb-track">
        ${u.off.map(([a, b, why]) => `<div class="sb-off ${esc(why)}" data-from="${esc(a)}" data-to="${esc(b)}"
          style="${pct(dayIdx[a], dayIdx[b])}" title="${esc(OFF[why] || why)}"></div>`).join('')}
        ${(holdsBy[u.unit_id] || []).map(h => {
          const l = Math.max(0, (h.start_pos - base) / span * 100), r = Math.min(100, (h.end_pos - base + 1) / span * 100);
          return `<div class="sb-hold ${h.kind}" data-hold="${h.id}" style="left:${l}%;width:${r - l}%">${esc(h.kind === 'ooo' ? 'OOO' : (h.title || 'Блок'))}</div>`;
        }).join('')}
        ${(byUnit[u.unit_id] || []).map(b => staysBarHtml(b, base, span, names)).join('')}
      </div></div>`;
  };
  const out = [];
  let prev = [];
  rows.forEach(u => {
    const path = pathOf(u);
    if (st.grouped) {
      let i = 0;
      while (i < prev.length && i < path.length && prev[i] === path[i]) i++;
      for (let k = i; k < path.length; k++) {
        if (path.slice(0, k).some((key, d) => !open(key, d))) break;
        const isOpen = open(path[k], k);
        out.push(`<div class="sb-sec" data-sec="${esc(path[k])}" data-open="${isOpen ? 1 : 0}" style="--depth:${k}">
          <span>${isOpen ? '▾' : '▸'} ${esc(title(u, k))}</span><small>${under[path[k]].length}</small></div>`);
      }
      prev = path;
      if (!path.every((key, d) => open(key, d))) return;
    }
    out.push(rowHtml(u));
  });
  const today = staysToday();
  return `<div class="sb-row sb-head"><div class="sb-unit">Объект</div><div class="sb-track sb-days">${days.map(d => staysDayHead(d, today)).join('')}</div></div>
    ${out.join('') || '<div class="empty">Объектов по фильтру нет</div>'}`;
}

/* ─────────────── Карточка брони ─────────────── */
async function openReservationCard(rid, onChanged) {
  const [card, history] = await Promise.all([
    api(`/api/stays/reservations/${rid}/card`), api(`/api/stays/reservations/${rid}/history`)]);
  const role = { main: 'главный', guest: 'проживает' };
  const diffText = diff => Object.entries(diff || {}).map(([k, [a, b]]) =>
    `${esc(k)}: ${esc(JSON.stringify(a))} → ${esc(JSON.stringify(b))}`).join('<br>');
  openModal({
    title: `Бронь ${card.number || '#' + card.id}`, wide: true,
    subtitle: `${card.status_title} · ${dateRu(card.check_in)}–${dateRu(card.check_out)}`,
    body: `
      <div class="grid-2">
        <div><h4>Объекты</h4>${card.segments.map(s => `<div>${esc(dateRu(s.start))}–${esc(dateRu(s.end))}: <b>${esc(s.unit || 'без объекта')}</b>
          ${can('stays.edit') ? `<button class="btn btn-sm btn-ghost" data-move-seg="${s.index}">Перенести</button>` : ''}</div>`).join('')}</div>
        <div><h4>Гости</h4>${card.occupants.map(o => `<div>${o.level !== 'regular' ? esc(STAYS_LEVEL_MARK[o.level]) : ''}${esc(o.guest)}
          <span class="muted">${esc(role[o.role])} · ${esc(dateRu(o.date_from))}–${esc(dateRu(o.date_to))}</span>
          ${can('stays.guests') ? `<button class="btn btn-sm btn-ghost" data-guest-card="${o.guest_id}">Карточка</button>` : ''}</div>`).join('') || '<span class="muted">состав не указан</span>'}</div>
      </div>
      ${card.companions?.length ? `<h4>Сопровождающие</h4>${card.companions.map(c => `<div>${esc(STAYS_COMPANION[c.kind] || c.kind)} — ${esc(c.description)}</div>`).join('')}` : ''}
      ${card.logistics ? `<h4>Логистика</h4>${card.logistics.map(l => `<div>${esc(l.date ? dateRu(l.date) : '')} ${esc(l.time)} ${esc(l.description)}</div>`).join('') || '<span class="muted">нет</span>'}
        ${card.note ? `<h4>Примечание</h4><p>${esc(card.note)}</p>` : ''}` : ''}
      <h4>История изменений</h4>
      <div class="sb-history">${history.map(h => `<div><b>${esc(h.ts.slice(0, 16).replace('T', ' '))}</b> · ${esc(h.actor)} · ${esc(h.title)}
        <div class="muted">${diffText(h.diff)}</div></div>`).join('') || '<span class="muted">записей нет</span>'}</div>`,
    footer: `<button class="btn btn-ghost" data-close>Закрыть</button>
      ${can('stays.assign') && card.status !== 'cancelled' && card.status !== 'no_show' ? '<button class="btn" id="rc-assign">Назначить батлеров</button>' : ''}
      ${can('stays.edit') ? `<button class="btn" id="rc-group">Совместное проживание…</button>
        <button class="btn" id="rc-status">Статус…</button><button class="btn btn-primary" id="rc-edit">Изменить</button>` : ''}`,
    onMount(m) {
      $('[data-close]', m).onclick = closeModal;
      const edit = $('#rc-edit', m);
      if (edit) edit.onclick = () => openReservationForm(rid, { onSaved: onChanged });
      const assign = $('#rc-assign', m);
      if (assign) assign.onclick = () => openCoverageForm(card, onChanged);
      const st = $('#rc-status', m);
      if (st) st.onclick = () => openStatusForm(card, onChanged);
      $$('[data-guest-card]', m).forEach(b => { b.onclick = () => openGuestCard(Number(b.dataset.guestCard), onChanged); });
      const grp = $('#rc-group', m);
      if (grp) grp.onclick = () => openGroupForm(card, onChanged);
      $$('[data-move-seg]', m).forEach(b => { b.onclick = () => openTransferForm(rid, Number(b.dataset.moveSeg), onChanged); });
    },
  });
}
