/* ══════════════════════════════════════════════════════════════════════
   РАЗДЕЛ «ШАХМАТКА» — фонд, гости, брони, сопровождение батлерами
   (спецификация docs/superpowers/specs/2026-10-23-stays-chessboard-design.md).
   Вкладки: шахматка объектов, шахматка батлеров, табло дня, сводная загрузка.
   Полосы броней — по половинкам суток (PoC §5): позиция = ordinal·2 + half.
   Сервер сам решает, какие поля гостя видны (§8): без прав полос нет фамилий.
   Модуль на lit-html (ADR-0013, раздел 7): разметка — шаблоны, вставки экранируются сами.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

import { can, registerModule } from '../app.js';
import {
  $, $$, api, closeModal, dateRu, downloadBlob, loadGenerationFor, MONTHS, openModal, state, textOn, todayISO, toast, WD_SHORT,
} from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { renderBookings } from './stays_bookings.js';
import { openBlockCard, renderBlocksTab } from './stays_blocks.js';
import { openOooForm, renderOooTab } from './stays_ooo.js';
import { renderMine } from './stays_mine.js';
import { renderFamilyTree } from './stays_family.js';
import {
  STAYS_COMPANION, openCoverageForm, openGroupForm, openGuestCard, openReservationForm, openStatusForm, openTransferForm,
  relativesView,
} from './stays_forms.js';
import { renderButlersBoard, renderDayBoard, renderOccupancyGrid } from './stays_board.js';
import { filterPanelTemplate, STAYS_SORTS, staysSortRows } from './stays_filters.js';
import { printStaysBoard } from './stays_print.js';
import { paletteRegister } from '../ui/palette.js';

registerModule({ views: { stays: loadStays, mystays: loadMyStays } });

/* палитра команд (⌘K): создание брони — с правом; поиск гостей живёт в самой палитре */
paletteRegister({ id: 'stays.new-booking', title: 'Создать бронь', hint: 'шахматка',
  when: () => can('stays.edit'), run: () => openReservationForm(null, {}) });

/* вкладки шахматки — оперативные (сезон «время × объекты»); справочник гостей вынесен
   в самостоятельный раздел «Гости» (ревью UI 22.11.2026), там же создание гостей батлером */
const STAYS_TABS = [['units', 'Объекты'], ['butlers', 'Батлеры'], ['day', 'Табло дня'], ['occupancy', 'Загрузка'], ['bookings', 'Брони'],
  ['blocks', 'Блоки'], ['ooo', 'OOO']];
/* «Особый гость» — ◆ у имени; VIP-код брони — рядом с главным гостем (правила сопровождения §6) */
export const STAYS_SPECIAL_MARK = '◆ ';
export const STAYS_ESCORT_MODE = { rules: 'по правилам', required: 'требуется', declined: 'не требуется (гость отказался)' };
export const staysGuestMarkView = special => (special ? html`<span class="sb-star">${STAYS_SPECIAL_MARK}</span>` : nothing);
export const staysCodeTagView = code => (code ? html` <span class="badge muted" data-vip-code>${code}</span>` : nothing);

/* месяц видов — общий state.year / state.month (как Табель и График, §6); фильтры — одна
   панель на все виды (§7); collapsed — разделы дерева, свёрнутые / развёрнутые пользователем */
export const staysState = {
  tab: 'units', fund: null, filters: staysEmptyFilters(),
  sort: { by: 'tree', dir: 'asc', grouped: true }, collapsed: {},
  ocOpen: {}, ocMode: 'pct', focusDay: null,
};
export function staysEmptyFilters() {
  return { group_ids: [], category_ids: [], flag_ids: [], kind_ids: [], escorted: false, special: false, vip_code_ids: [], q: '' };
}

/* PoC §5.1: ordinal как в Python date.toordinal() — клиент и сервер считают позиции одинаково */
export function staysOrdinal(y, m, d) { return Math.round(Date.UTC(y, m - 1, d) / 86400000) + 719163; }
export function staysPos(iso, half) { const [y, m, d] = iso.split('-').map(Number); return staysOrdinal(y, m, d) * 2 + half; }
export function staysAddDays(iso, n) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}
/* «сегодня» — по часам объекта (APP_TZ сервера), как Табель: todayISO() из core.js */
export function staysToday() { return todayISO(); }
/* границы общего месяца разделов */
export function staysMonthRange() {
  const mm = String(state.month).padStart(2, '0');
  const days = new Date(Date.UTC(state.year, state.month, 0)).getUTCDate();
  return { first: `${state.year}-${mm}-01`, last: `${state.year}-${mm}-${String(days).padStart(2, '0')}` };
}
/* ◀ ▶ — как Табель; «Сегодня» — текущий месяц, докрутка и подсветка дня */
function shiftMonth(delta, rerender) {
  let m = state.month + delta, y = state.year;
  if (m < 1) { m = 12; y--; } if (m > 12) { m = 1; y++; }
  state.month = m; state.year = y;
  staysState.focusDay = null;     // «Сегодня» прошлого месяца не докручивает новый
  rerender();
}
function goToday(body, rerender) {
  const today = staysToday();
  const [y, m] = today.split('-').map(Number);
  staysState.focusDay = today;
  if (y === state.year && m === state.month) staysFocusDay(body);
  else { state.year = y; state.month = m; rerender(); }
}
/* шаблон навигации по месяцам — для видов на шаблонах; body — контейнер вкладки (докрутка к дню) */
export const staysMonthNavView = (body, rerender) => html`<div class="month-nav"><button id="sm-prev" title="Предыдущий месяц" @click=${() => shiftMonth(-1, rerender)}>◀</button>
    <div class="label" id="sm-label">${MONTHS[state.month - 1]} ${state.year}</div>
    <button id="sm-next" title="Следующий месяц" @click=${() => shiftMonth(1, rerender)}>▶</button></div>
    <button class="btn btn-sm" id="sm-today" title="Текущий месяц и колонка сегодняшнего дня" @click=${() => goToday(body, rerender)}>Сегодня</button>`;
/* докрутка сетки к колонке staysState.focusDay и подсветка (как scrollTabelToToday) */
export function staysFocusDay(body) {
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
export function staysFundParams(p) {
  const f = staysState.filters;
  f.group_ids.forEach(v => p.append('group_ids', v));
  f.category_ids.forEach(v => p.append('category_ids', v));
  f.flag_ids.forEach(v => p.append('flag_ids', v));
  f.kind_ids.forEach(v => p.append('kind_ids', v));
  return p;
}
/* фильтры по гостям: «◆ Особый гость», VIP-код (или), поиск */
export function staysPeopleParams(p, f) {
  if (f.special) p.set('special', '1');
  f.vip_code_ids.forEach(v => p.append('vip_code_ids', v));
  if (f.q.trim()) p.set('q', f.q.trim());
}
/* вес места/нагрузка: один знак, запятая («5,5») */
export function staysWeight(n) { return Number(n).toFixed(1).replace('.', ','); }
/* панель фильтров вида шаблоном: изменение — новые фильтры и перерисовка вида */
export const staysFilterView = (fund, rerender, opts) => filterPanelTemplate(fund, staysState.filters,
  f => { staysState.filters = f; rerender(); }, opts);

/* Справочники модуля + фонд на сегодня (категории, узлы, объекты — версиями с даты, GET /fund/snapshot) */
export async function staysFund(force = false) {
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

export async function loadStays() {
  const host = $('#view-stays');
  render(html`
    <div class="page-head"><div><h2>Шахматка</h2><div class="sub">Кто где живёт и кто из батлеров ведёт гостей</div></div>
      <div class="spacer"></div>${guestFindView()}</div>
    <div class="layer-tabs">${STAYS_TABS.filter(staysTabAllowed).map(([id, t]) => html`<button
      class="btn btn-sm${staysState.tab === id ? ' btn-primary' : ''}" data-stab=${id}
      @click=${() => { staysState.tab = id; loadStays(); }}>${t}</button>`)}</div>
    <div id="stays-body"></div>`, mount(host));
  const body = $('#stays-body', host);
  // Вкладки переиспользуют один #stays-body: инвалидируем async-render прежней вкладки
  // до ожидания фонда, иначе её запоздавший ответ мог вернуть действия поверх скелетона новой.
  loadGenerationFor(body);
  const loadGen = String((Number(body.dataset.staysLoadGen) || 0) + 1);
  body.dataset.staysLoadGen = loadGen;
  const fresh = () => body.dataset.staysLoadGen === loadGen;
  const tab = staysState.tab;
  render(html`<div class="skel-wrap"><div class="skel-line skel-lg"></div><div class="skel-line"></div><div class="skel-line"></div></div>`, mount(body));
  try {
    await staysFund(true);          // фонд меняют в Настройках — при каждом открытии раздела заново
    if (!fresh() || tab !== staysState.tab) return;
    await staysTabRender(tab)(body);
  } catch (e) {
    if (!fresh()) return;
    render(html`<div class="panel"><p class="muted">${e.message}</p></div>`, mount(body));
  }
}
/* «Батлеры» и «Брони» — с уровня «с фамилиями» */
export function staysTabAllowed([id]) {
  return (id !== 'butlers' && id !== 'bookings') || can('stays.view');
}
/* вкладка → функция отрисовки */
function staysTabRender(tab) {
  return { units: renderUnitsBoard, butlers: renderButlersBoard, day: renderDayBoard,
    occupancy: renderOccupancyGrid, bookings: renderBookings, blocks: renderBlocksTab, ooo: renderOooTab }[tab] || renderUnitsBoard;
}

let guestFindGeneration = 0;
let guestFindTimer = null;

/* микро-поиск гостя в шапке шахматки (ревью UI 22.11.2026): карточка открывается из любой
   вкладки; батлер ищет среди своих. Справочник целиком — раздел «Гости». */
function guestFindView() {
  const full = can('stays.guests');
  if (!full && !(can('stays.mine_guest_edit') && state.user?.employee_id != null)) return nothing;
  ++guestFindGeneration; // новый рендер шапки владеет всеми следующими ответами поиска
  return html`<div class="guest-find"><input type="search" id="sg-q" placeholder="Найти гостя…"
    @input=${e => {
      clearTimeout(guestFindTimer);
      const input = e.currentTarget;
      const host = input.closest('.guest-find');
      const current = ++guestFindGeneration;
      guestFindTimer = setTimeout(async () => {
        const needle = input.value.trim();
        if (needle.length < 2) { render(nothing, $('[data-sg-res]', host)); return; }
        try {
          const found = await api(`/api/stays/guests?q=${encodeURIComponent(needle)}${full ? '' : '&mine=1'}`, { silent: true });
          if (current !== guestFindGeneration || !host.isConnected) return;
          render(found.length ? found.map(g => html`<button type="button" class="btn btn-sm btn-ghost" data-sg-guest=${g.id}>${g.short}</button>`)
            : html`<span class="muted">не найдено</span>`, $('[data-sg-res]', host));
        } catch (err) { if (current === guestFindGeneration) toast(err.message, 'warn'); }
      }, 300);
    }}>
    <div class="guest-find-res" data-sg-res @click=${e => {
      const b = e.target.closest('[data-sg-guest]');
      if (!b) return;
      ++guestFindGeneration;
      clearTimeout(guestFindTimer);
      openGuestCard(Number(b.dataset.sgGuest), () => loadStays());
      const host = e.currentTarget.closest('.guest-find');
      $('input', host).value = '';
      render(nothing, e.currentTarget);
    }}></div></div>`;
}

async function loadMyStays() {
  await renderMine();
}

/* ─────────────── Шахматка объектов ─────────────── */
export function staysBoardParams() {
  const f = staysState.filters;
  const { first, last } = staysMonthRange();
  const p = staysFundParams(new URLSearchParams({ first, last }));
  if (f.escorted) p.set('escorted', '1');
  staysPeopleParams(p, f);
  return p;
}

/* заголовок колонок дня — общий для видов месяца: data-day, «сегодня», выходные */
const weekdayOf = d => new Date(d + 'T12:00:00Z').getUTCDay();
export const staysDayHeadView = (d, today) => {
  const wd = weekdayOf(d);
  return html`<div data-day=${d} class="${d === today ? 'today' : ''}${wd === 0 || wd === 6 ? ' we' : ''}">${Number(d.slice(8))}<small>${WD_SHORT[(wd + 6) % 7]}</small></div>`;
};

/* цвет в style — только #RGB / #RRGGBB(AA): иначе текст цвета дописал бы CSS в атрибут */
export function staysColor(c) { return /^#[0-9a-f]{3,8}$/i.test(c || '') ? c : '#999'; }

/* «4003 → 4103 с 15.11» — смена обозначения и категории внутри месяца (§6) */
export function staysRowChanges(u, cats) {
  const ddmm = iso => `${iso.slice(8)}.${iso.slice(5, 7)}`;
  const chain = (items, name) => items.length > 1
    ? items.map((x, i) => (i ? ` → ${name(x)} с ${ddmm(x.from)}` : name(x))).join('') : '';
  return [chain(u.labels, x => x.label), chain(u.categories, x => x.code ?? cats[x.category_id]?.code ?? '#' + x.category_id)]
    .filter(Boolean).join(' · ');
}

function barTemplate(b, base, span, names) {
  const left = Math.max(0, (b.start_pos - base) / span * 100);
  const right = Math.min(100, (b.end_pos - base + 1) / span * 100);
  if (right <= 0 || left >= 100) return nothing;
  const color = names && b.label ? b.label.color : '#3b6fd8';
  const text = names
    ? html`${staysGuestMarkView(b.special)}${b.main_guest || b.number || 'бронь'}${b.vip_code ? ` · ${b.vip_code}` : ''}`
    : `занято · ${b.guests_count} гост.`;
  const tip = names ? `${b.number} · ${dateRu(b.start)}–${dateRu(b.end)}` : `${dateRu(b.start)}–${dateRu(b.end)}`;
  return html`<div class="sb-bar${b.status === 'tentative' ? ' tentative' : ''}${b.mine ? ' sb-mine' : ''}" data-bar=${b.reservation_id}
    style=${`left:${left}%;width:${right - left}%;background:${staysColor(color)};color:${textOn(staysColor(color))}`} title=${b.mine ? 'Ваша бронь · ' + tip : tip}>${text}</div>`;
}

/* Цвет блока — по его номеру из небольшой палитры (в БД цвета нет); полосы блока пунктиром и не
   перетаскиваются: слот блока не закреплён за объектом, объект выбирает распределение (§2, §6) */
const STAYS_BLOCK_HUES = [262, 28, 172, 330, 48, 200, 94, 8];
function blockBarTemplate(b, base, span) {
  const left = Math.max(0, (b.start_pos - base) / span * 100);
  const right = Math.min(100, (b.end_pos - base + 1) / span * 100);
  if (right <= 0 || left >= 100) return nothing;
  const hue = STAYS_BLOCK_HUES[b.block_id % STAYS_BLOCK_HUES.length];
  return html`<div class="sb-block" data-block=${b.block_id} data-slot=${b.slot} draggable="false"
    style=${`left:${left}%;width:${right - left}%;--bh:${hue}`} title=${(b.title || 'Блок') + ' · ' + dateRu(b.start) + '–' + dateRu(b.end)}>${b.title || 'Блок'}</div>`;
}

async function renderUnitsBoard(body) {
  /* ◀ ▶ и фильтры меняются подряд: запоздавший ответ перерисовал бы экран прежним месяцем
     (как Табель, PR #95) — поколение у контейнера вкладки (core.js) */
  const fresh = loadGenerationFor(body);
  const disablePrint = () => {
    const action = $('#sb-print', body);
    if (action) action.disabled = true;
  };
  disablePrint();
  const filters = staysState.filters;
  const monthLabel = `${MONTHS[state.month - 1]} ${state.year}`;
  const [fund, data] = await Promise.all([staysFund(),
    api('/api/stays/board/units?' + staysBoardParams(), { silent: true })]);
  if (!fresh()) return;
  const names = data.visibility !== 'occupancy';
  const byUnit = {};
  data.bars.forEach(b => { (byUnit[b.unit_id ?? 'none'] ||= []).push(b); });
  const holdsBy = {};
  data.holds.forEach(h => { (holdsBy[h.unit_id] ||= []).push(h); });
  const blocksBy = {};
  data.blocks.forEach(b => { (blocksBy[b.unit_id] ||= []).push(b); });
  const rerender = () => renderUnitsBoard(body);
  const st = staysState.sort;
  const canPrint = () => fresh() && (!names || $('#sf-q', body)?.value.trim() === filters.q.trim());
  const draw = () => {
    render(unitsTemplate(), mount(body));
    $('#sb-print', body).disabled = !canPrint();
  };
  const xlsx = kind => () => {
    const { first, last } = staysMonthRange();
    downloadBlob('/api/stays/export?' + new URLSearchParams({ first, last, kind }), `shakhmatka_${kind}_${first}.xlsx`);
  };
  /* сетка — одним обработчиком: строк до 440, и они перерисовываются при сортировке */
  const gridClick = e => {
    const sec = e.target.closest('[data-sec]');
    if (sec) {
      staysState.collapsed[sec.dataset.sec] = sec.dataset.open === '1';
      draw();
      return;
    }
    /* слот блока — карточка блока (сетка, разложено, нехватка); полоса не перетаскивается */
    const blk = e.target.closest('[data-block]');
    if (blk) { openBlockCard(Number(blk.dataset.block), rerender); return; }
    const bar = e.target.closest('[data-bar]');
    if (bar) { if (names) openReservationCard(Number(bar.dataset.bar), rerender); return; }
    if (!can('stays.edit')) return;
    /* блок / OOO: клик по объекту — новый, по полосе блока — правка или удаление */
    const hold = e.target.closest('[data-hold]');
    if (hold) { openOooForm(data.holds.find(h => h.id === Number(hold.dataset.hold)), rerender); return; }
    const unit = e.target.closest('.sb-unit');
    const row = unit && unit.closest('[data-unit-row]');
    if (row) openOooForm({ unit_id: Number(row.dataset.unitRow) }, rerender);
  };
  const unitsTemplate = () => html`
    <div class="sb-toolbar">
      ${staysMonthNavView(body, rerender)}
      <select id="sb-sort" title="Сортировка строк" @change=${e => { st.by = e.target.value; draw(); }}>${STAYS_SORTS.map(([v, t]) =>
        html`<option value=${v} ?selected=${v === st.by}>${t}</option>`)}</select>
      <select id="sb-dir" title="Направление" @change=${e => { st.dir = e.target.value; draw(); }}>
        <option value="asc" ?selected=${st.dir === 'asc'}>↑</option><option value="desc" ?selected=${st.dir === 'desc'}>↓</option></select>
      <label class="chk"><input type="checkbox" id="sb-grouped" .checked=${st.grouped}
        @change=${e => { st.grouped = e.target.checked; draw(); }}> группировать по дереву</label>
      <button class="btn btn-sm btn-ghost" id="sb-xlsx-anon" title="Объекты, даты, статусы, число гостей — без данных гостей" @click=${xlsx('anon')}>Выгрузить (без гостей)</button>
      ${can('stays.export') && can('stays.guests') ? html`<button class="btn btn-sm btn-ghost" id="sb-xlsx-full" @click=${xlsx('full')}>Выгрузить полностью</button>` : nothing}
      <button class="btn btn-sm btn-ghost" id="sb-print" @click=${() => canPrint() && printStaysBoard(
        { ...data, units: staysSortRows(data.units, st, fund) }, fund, filters, data.visibility, monthLabel)}>Печать</button>
      ${can('stays.edit') ? html`<button class="btn btn-sm btn-primary hide-mobile" id="sb-new" @click=${() => openReservationForm(null, { onSaved: rerender })}>+ Бронь</button>` : nothing}
    </div>
    ${staysFilterView(fund, rerender, { people: names, onSearchInput: disablePrint })}
    ${data.warnings.length ? html`<div class="dict-banner gold"><span>⚠</span><span>${data.warnings.map((w, i) => html`${i ? html`<br>` : nothing}${w.text}`)}</span></div>` : nothing}
    <div class="sb-grid" tabindex="0" style=${`--days:${data.days.length}`} @click=${gridClick}>${gridTemplate(data, fund, byUnit, holdsBy, blocksBy, names)}</div>
    ${(byUnit.none || []).length ? html`<div class="panel"><h3 class="panel-title">Не распределено</h3>${byUnit.none.map(b =>
      html`<div class="sb-unassigned${b.overbooked ? ' overbooked' : ''}" data-bar=${b.reservation_id}
        @click=${names ? () => openReservationCard(b.reservation_id, rerender) : nothing}>${b.overbooked ? html`<span class="badge danger">овербукинг</span> ` : nothing}${names ? (b.number + ' · ' + (b.main_guest || '')) : 'бронь'} · ${dateRu(b.start)}–${dateRu(b.end)}</div>`)}</div>` : nothing}
    ${can('stays.edit') ? html`<button class="fab only-mobile" id="sb-new-fab" aria-label="Новая бронь" title="Новая бронь"
      @click=${() => openReservationForm(null, { onSaved: rerender })}>+</button>` : nothing}`;
  draw();
  staysFocusDay(body);
}

/* Разделы дерева: по умолчанию развёрнут корневой раздел, где есть категория вида с
   «раскрывать» (справочник видов, §1 дополнения: виллы развёрнуты, корпус свёрнут), вложенные —
   развёрнуты; выбор пользователя — staysState.collapsed. Строки свёрнутого раздела в DOM не рисуются. */
function gridTemplate(data, fund, byUnit, holdsBy, blocksBy, names) {
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
  const rowTemplate = u => {
    const changes = staysRowChanges(u, cats);
    return html`<div class="sb-row" data-unit-row=${u.unit_id} data-root=${pathOf(u)[0]} data-load=${u.load}>
      <div class="sb-unit"><b>${u.label}</b><small>${u.category}${u.floor ? ' · эт. ' + u.floor : ''}
        ${u.flags.map(id => html`<span class="sb-flag" style=${`background:${staysColor(flags[id]?.color)}`} title=${flags[id]?.title || ''}></span>`)}</small>
        ${changes ? html`<small class="sb-change">${changes}</small>` : nothing}</div>
      <div class="sb-track">
        ${u.off.map(([a, b, why]) => html`<div class="sb-off ${why}" data-from=${a} data-to=${b}
          style=${pct(dayIdx[a], dayIdx[b])} title=${OFF[why] || why}></div>`)}
        ${(holdsBy[u.unit_id] || []).map(h => {
          const l = Math.max(0, (h.start_pos - base) / span * 100), r = Math.min(100, (h.end_pos - base + 1) / span * 100);
          const tip = `OOO · ${dateRu(h.start)} ${h.start_half === 'AM' ? 'с утра' : 'с вечера'} – ${dateRu(h.end)} ${h.end_half === 'PM' ? 'до вечера' : 'до утра'}`;
          return html`<div class="sb-hold ${h.kind}" data-hold=${h.id} style=${`left:${l}%;width:${r - l}%`} title=${tip + (h.title ? ' · ' + h.title : '')}>${h.title || 'OOO'}</div>`;
        })}
        ${(blocksBy[u.unit_id] || []).map(b => blockBarTemplate(b, base, span))}
        ${(byUnit[u.unit_id] || []).map(b => barTemplate(b, base, span, names))}
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
        out.push(html`<div class="sb-sec" data-sec=${path[k]} data-open=${isOpen ? 1 : 0} style=${`--depth:${k}`}>
          <span>${isOpen ? '▾' : '▸'} ${title(u, k)}</span><small>${under[path[k]].length}</small></div>`);
      }
      prev = path;
      if (!path.every((key, d) => open(key, d))) return;
    }
    out.push(rowTemplate(u));
  });
  const today = staysToday();
  return html`<div class="sb-row sb-head"><div class="sb-unit">Объект</div><div class="sb-track sb-days">${days.map(d => staysDayHeadView(d, today))}</div></div>
    ${out.length ? out : html`<div class="empty">Объектов по фильтру нет</div>`}`;
}

/* «сопровождение: отказался», «требуется — отмечено вручную», «нужен — узел Винные виллы, …» (§2, §4.1) */
function staysEscortTitle(card) {
  const e = card.escort || {};
  if (card.escort_mode === 'declined') return 'отказался';
  if (!e.required_nights) return 'не нужно';
  return `нужно${e.reasons?.length ? ' — ' + e.reasons.join(', ') : ''}`;
}

/* ─────────────── Карточка брони ─────────────── */
export async function openReservationCard(rid, onChanged) {
  const [card, history] = await Promise.all([
    api(`/api/stays/reservations/${rid}/card`), api(`/api/stays/reservations/${rid}/history`)]);
  const role = { main: 'главный', guest: 'проживает' };
  /* батлер в своей брони (card.mine): карточки гостей (stays.mine) и «Изменить» (stays.mine_res_edit) —
     как в «Моих гостях»; назначения, статус и совместное проживание — только stays.edit / stays.assign */
  const guestCard = can('stays.guests') || (card.mine && can('stays.mine'));
  const mineEdit = !can('stays.edit') && card.mine && can('stays.mine_res_edit');
  const diffText = diff => Object.entries(diff || {}).map(([k, [a, b]], i) =>
    html`${i ? html`<br>` : nothing}${k}: ${JSON.stringify(a)} → ${JSON.stringify(b)}`);
  const relatives = relativesView;
  openModal({
    title: `Бронь ${card.number || '#' + card.id}`, wide: true,
    subtitle: `${card.status_title} · ${dateRu(card.check_in)}–${dateRu(card.check_out)}`,
    body: html`${card.upgrade ? html`<p><span class="badge muted">${card.upgrade}</span></p>` : nothing}
      <div class="grid-2">
        <div><h4>Объекты</h4>${card.segments.map(s => html`<div>${dateRu(s.start)}–${dateRu(s.end)}: <b>${s.unit || 'без объекта'}</b>
          ${can('stays.edit') ? html`<button class="btn btn-sm btn-ghost" data-move-seg=${s.index}>Перенести</button>` : nothing}</div>`)}
          ${card.pref ? html`<div class="muted" data-pref-status=${card.pref.met ? 'met' : card.pref.partial ? 'partial' : card.pref.met === null ? 'none' : 'unmet'}>${card.pref.title}</div>` : nothing}</div>
        <div><h4>Гости</h4>${card.occupants.length ? card.occupants.map(o => html`<div>${staysGuestMarkView(o.special)}${o.guest}${o.role === 'main' ? staysCodeTagView(card.vip_code?.code) : nothing}
          <span class="muted">${role[o.role]} · ${dateRu(o.date_from)}–${dateRu(o.date_to)}</span>${relatives(o.relatives)}
          <button class="btn btn-sm btn-ghost" data-family=${o.guest_id}>Семья</button>
          ${guestCard ? html`<button class="btn btn-sm btn-ghost" data-guest-card=${o.guest_id}>Карточка</button>` : nothing}
          <div class="ft" data-family-box=${o.guest_id} hidden></div></div>`) : html`<span class="muted">состав не указан</span>`}</div>
      </div>
      <p data-card-escort>Сопровождение: <b>${staysEscortTitle(card)}</b>${card.vip_code
        ? ` · VIP-код ${card.vip_code.code}${card.vip_code.title ? ' — ' + card.vip_code.title : ''}${card.vip_code.archived ? ' (в архиве)' : ''}` : ''}</p>
      ${card.companions?.length ? html`<h4>Сопровождающие</h4>${card.companions.map(c => html`<div>${STAYS_COMPANION[c.kind] || c.kind} — ${c.description}</div>`)}` : nothing}
      ${card.logistics ? html`<h4>Логистика</h4>${card.logistics.length ? card.logistics.map(l => html`<div>${l.date ? dateRu(l.date) : ''} ${l.time} ${l.description}</div>`) : html`<span class="muted">нет</span>`}
        ${card.note ? html`<h4>Примечание</h4><p>${card.note}</p>` : nothing}` : nothing}
      <h4>История изменений</h4>
      <div class="sb-history">${history.length ? history.map(h => html`<div><b>${h.ts.slice(0, 16).replace('T', ' ')}</b> · ${h.actor} · ${h.title}
        <div class="muted">${diffText(h.diff)}</div></div>`) : html`<span class="muted">записей нет</span>`}</div>`,
    footer: html`<button class="btn btn-ghost" data-close>Закрыть</button>
      ${can('stays.assign') && card.status !== 'cancelled' && card.status !== 'no_show' ? html`<button class="btn" id="rc-assign">Назначить батлеров</button>` : nothing}
      ${can('stays.edit') ? html`<button class="btn" id="rc-group">Совместное проживание…</button>
        <button class="btn" id="rc-status">Статус…</button><button class="btn btn-primary" id="rc-edit">Изменить</button>` : nothing}
      ${mineEdit ? html`<button class="btn btn-primary" id="rc-edit">Изменить</button>` : nothing}`,
    onMount(m) {
      $('[data-close]', m).onclick = closeModal;
      const edit = $('#rc-edit', m);
      if (edit) edit.onclick = () => openReservationForm(rid, { mine: mineEdit, onSaved: onChanged });
      const assign = $('#rc-assign', m);
      if (assign) assign.onclick = () => openCoverageForm(card, onChanged);
      const st = $('#rc-status', m);
      if (st) st.onclick = () => openStatusForm(card, onChanged);
      /* гость своей брони, которого явно ведёт другой батлер, — чужой: сервер ответит 403.
         Карточка — боковая панель: модалку закрываем, иначе она (z-100) накроет её (z-90) */
      $$('[data-guest-card]', m).forEach(b => { b.onclick = () => { closeModal();
        openGuestCard(Number(b.dataset.guestCard), onChanged).catch(e => toast(e.message, 'err')); }; });
      /* семейное дерево гостя — только просмотр: правится в карточке гостя (§4, с уровня «с фамилиями») */
      $$('[data-family]', m).forEach(b => {
        b.onclick = () => {
          const box = $(`[data-family-box="${b.dataset.family}"]`, m);
          box.hidden = !box.hidden;
          /* загружено — только при успехе: после ошибки следующий клик запросит дерево снова */
          if (!box.hidden && box.dataset.loaded !== '1') {
            renderFamilyTree(box, Number(b.dataset.family)).then(ok => { if (ok) box.dataset.loaded = '1'; })
              .catch(e => toast(e.message, 'err'));
          }
        };
      });
      const grp = $('#rc-group', m);
      if (grp) grp.onclick = () => openGroupForm(card, onChanged);
      $$('[data-move-seg]', m).forEach(b => { b.onclick = () => openTransferForm(rid, Number(b.dataset.moveSeg), onChanged); });
    },
  });
}
