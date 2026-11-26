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
import { guestPickContent } from '../ui/guest_picker.js';
import { openBoardFamily } from './stays_family_canvas.js';
import { renderFamilyTree } from './stays_family.js';
import {
  STAYS_COMPANION, openCoverageForm, openGroupForm, openGuestCard, openReservationForm, openStatusForm, openTransferForm,
  relativesView,
} from './stays_forms.js';
import { renderButlersBoard, renderDayBoard, renderOccupancyGrid } from './stays_board.js';
import { filterPanelTemplate, STAYS_SORTS, staysSortRows } from './stays_filters.js';
import { previewStaysPdf, printStaysBoard } from './stays_print.js';
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
  const toolbar = $('.sb-units-toolbar', body);
  if (toolbar && matchMedia('(max-width: 860px)').matches) {
    const viewport = grid.closest('.content');
    const top = viewport.getBoundingClientRect().top + toolbar.offsetHeight;
    viewport.scrollTop += grid.getBoundingClientRect().top - top;
  }
  cell.classList.add('flash-today');
  setTimeout(() => cell.classList.remove('flash-today'), 1800);
}

document.addEventListener('pointerdown', event => {
  const menu = $('#view-stays.active .sb-mobile-exports[open]');
  if (menu && !menu.contains(event.target)) menu.open = false;
});
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
export function staysResetGuestFind() {
  ++guestFindGeneration;
  clearTimeout(guestFindTimer);
  guestFindTimer = null;
}

/* микро-поиск гостя в шапке шахматки (ревью UI 22.11.2026): карточка открывается из любой
   вкладки; батлер ищет среди своих. Справочник целиком — раздел «Гости». */
function guestFindView() {
  const full = can('stays.guests');
  if (!full && !(can('stays.mine_guest_edit') && state.user?.employee_id != null)) return nothing;
  ++guestFindGeneration; // новый рендер шапки владеет всеми следующими ответами поиска
  return html`<div class="guest-find"><input type="search" id="sg-q" aria-label="Найти гостя"
    placeholder=${full ? 'ФИО, телефон или дата рождения' : 'ФИО гостя'}
    @input=${e => {
      clearTimeout(guestFindTimer);
      const input = e.currentTarget;
      const host = input.closest('.guest-find');
      const current = ++guestFindGeneration;
      guestFindTimer = setTimeout(async () => {
        if (current !== guestFindGeneration || !host.isConnected) return;
        const needle = input.value.trim();
        if (needle.length < 2) { render(nothing, $('[data-sg-res]', host)); return; }
        try {
          const found = await api(`/api/stays/guests?details=1&q=${encodeURIComponent(needle)}${full ? '' : '&mine=1'}`, { silent: true });
          if (current !== guestFindGeneration || !host.isConnected) return;
          render(found.length ? found.map(g => html`<button type="button" class="btn btn-sm btn-ghost guest-pick-button" data-sg-guest=${g.id}>${guestPickContent(g)}</button>`)
            : html`<span class="muted">не найдено</span>`, $('[data-sg-res]', host));
        } catch (err) { if (current === guestFindGeneration) toast(err.message, 'warn'); }
      }, 300);
    }}>
    <div class="guest-find-res" data-sg-res @click=${e => {
      const b = e.target.closest('[data-sg-guest]');
      if (!b) return;
      ++guestFindGeneration;
      clearTimeout(guestFindTimer);
      openGuestCard(Number(b.dataset.sgGuest), () => loadStays(), {
        onOpenFamily: openBoardFamily, isCurrent: () => state.view === 'stays',
      }).catch(err => toast(err.message, 'warn'));
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

function barTemplate(b, base, span, names, unit) {
  const left = Math.max(0, (b.start_pos - base) / span * 100);
  const right = Math.min(100, (b.end_pos - base + 1) / span * 100);
  if (right <= 0 || left >= 100) return nothing;
  const color = names && b.label ? b.label.color : '#3b6fd8';
  const text = names
    ? html`${staysGuestMarkView(b.special)}${b.main_guest || b.number || 'бронь'}${b.vip_code ? ` · ${b.vip_code}` : ''}`
    : `занято · ${b.guests_count} гост.`;
  const tip = names ? `${b.number} · ${dateRu(b.start)}–${dateRu(b.end)}` : `${dateRu(b.start)}–${dateRu(b.end)}`;
  const cls = 'sb-bar' + (b.status === 'tentative' ? ' tentative' : '') + (b.mine ? ' sb-mine' : '');
  const style = `left:${left}%;width:${right - left}%;background:${staysColor(color)};color:${textOn(staysColor(color))}`;
  const title = b.mine ? 'Ваша бронь · ' + tip : tip;
  if (!names) return html`<div class=${cls} style=${style} title=${title}>${text}</div>`;
  const label = [
    b.main_guest || b.number || 'Бронь', b.vip_code, unit, tip,
    b.mine && 'Ваша бронь', b.special && 'Особый гость', b.status === 'tentative' && 'Предварительная бронь',
  ].filter(Boolean).join(' · ');
  return html`<button type="button" class=${cls} data-bar=${b.reservation_id}
    data-start=${b.start_pos} data-end=${b.end_pos} tabindex="-1" style=${style} title=${title}
    data-booking-key=${[b.unit_id, b.reservation_id, b.start_pos, b.end_pos].join(':')}
    aria-label=${label}>${text}</button>`;
}

const boardBookingButtons = root => $$('button.sb-bar', root);
const findBoardBooking = (grid, key) => $(`button[data-booking-key="${CSS.escape(key)}"]`, grid);
const bookingPosition = button => Number(button.dataset.start);

function nextBoardBooking(grid, current, key) {
  const row = current.closest('[data-unit-row]');
  if (key === 'ArrowLeft' || key === 'ArrowRight') {
    const bookings = boardBookingButtons(row).sort((a, b) => bookingPosition(a) - bookingPosition(b));
    return bookings[bookings.indexOf(current) + (key === 'ArrowLeft' ? -1 : 1)];
  }
  const rows = $$('[data-unit-row]', grid).filter(row => boardBookingButtons(row).length);
  const adjacent = rows[rows.indexOf(row) + (key === 'ArrowUp' ? -1 : 1)];
  if (!adjacent) return;
  const date = bookingPosition(current);
  const distance = button => Math.max(bookingPosition(button) - date, date - Number(button.dataset.end), 0);
  return boardBookingButtons(adjacent).sort((a, b) => distance(a) - distance(b) ||
    Math.abs(bookingPosition(a) - date) - Math.abs(bookingPosition(b) - date))[0];
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

function showBoardBooking(grid, booking) {
  booking.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  const viewport = grid.closest('.content');
  const toolbar = $('.sb-toolbar:not(.sf-bar, .sf-panel)', grid.parentElement);
  const tabbar = $('#tabbar');
  const bounds = viewport.getBoundingClientRect();
  const top = Math.max(bounds.top, toolbar.getBoundingClientRect().bottom);
  const bottom = tabbar.getClientRects().length
    ? Math.min(bounds.bottom, tabbar.getBoundingClientRect().top)
    : bounds.bottom;
  const strip = booking.getBoundingClientRect();
  if (strip.top < top) viewport.scrollTop += strip.top - top;
  else if (strip.bottom > bottom) viewport.scrollTop += strip.bottom - bottom;
}

async function renderUnitsBoard(body) {
  /* ◀ ▶ и фильтры меняются подряд: запоздавший ответ перерисовал бы экран прежним месяцем
     (как Табель, PR #95) — поколение у контейнера вкладки (core.js) */
  const fresh = loadGenerationFor(body);
  const setExportDisabled = disabled => {
    for (const action of $$('[data-sb-export]', body)) action.disabled = disabled;
  };
  const disablePrint = () => setExportDisabled(true);
  disablePrint();
  const filters = staysState.filters;
  const monthLabel = `${MONTHS[state.month - 1]} ${state.year}`;
  const boardParams = staysBoardParams();
  const [fund, data] = await Promise.all([staysFund(),
    api('/api/stays/board/units?' + boardParams, { silent: true })]);
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
  const gridFocus = (grid, booking) => {
    const previous = $('button.sb-bar[tabindex="0"]', grid);
    if (previous && previous !== booking) previous.tabIndex = -1;
    if (booking) booking.tabIndex = 0;
    grid.tabIndex = booking ? -1 : 0;
  };
  const draw = () => {
    const previous = $('.sb-grid button.sb-bar[tabindex="0"]', body);
    const bookingKey = previous?.dataset.bookingKey;
    const hadFocus = !!previous && document.activeElement === previous;
    render(unitsTemplate(), mount(body));
    const grid = $('.sb-grid', body);
    const booking = (bookingKey && findBoardBooking(grid, bookingKey)) || boardBookingButtons(grid)[0];
    gridFocus(grid, booking);
    if (hadFocus && document.activeElement !== (booking || grid)) (booking || grid).focus();
    setExportDisabled(!canPrint());
  };
  const gridKey = event => {
    const current = event.target.closest('button.sb-bar');
    if (!current || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    nextBoardBooking(event.currentTarget, current, event.key)?.focus();
  };
  const onGridFocus = event => {
    const booking = event.target.closest('button.sb-bar');
    if (!booking) return;
    gridFocus(event.currentTarget, booking);
    showBoardBooking(event.currentTarget, booking);
  };
  const exportPath = (format, forPrint = false) => {
    const params = new URLSearchParams(boardParams);
    if (!names || format === 'xlsx' && !can('stays.export')) {
      for (const key of ['q', 'special', 'vip_code_ids']) params.delete(key);
    }
    params.set('format', format);
    if (forPrint) params.set('for_print', 'true');
    return '/api/stays/board/units/export?' + params;
  };
  const exportFilename = format => `shakhmatka_${boardParams.get('first').slice(0, 7)}.${format}`;
  const downloadBoard = format => {
    if (canPrint()) downloadBlob(exportPath(format), exportFilename(format));
  };
  const printBoard = () => {
    if (!canPrint()) return;
    return previewStaysPdf(exportPath('pdf', true), exportFilename('pdf'), canPrint, () =>
      printStaysBoard({ ...data, units: staysSortRows(data.units, st, fund) }, fund, filters,
        data.visibility, monthLabel));
  };
  const xlsx = kind => () => {
    const { first, last } = staysMonthRange();
    downloadBlob('/api/stays/export?' + new URLSearchParams({ first, last, kind }), `shakhmatka_${kind}_${first}.xlsx`);
  };
  /* сетка — одним обработчиком: строк до 440, и они перерисовываются при сортировке */
  let openCardGeneration = 0;
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
    if (bar) {
      const generation = ++openCardGeneration;
      const key = bar.dataset.bookingKey;
      const returnFocusTo = () => findBoardBooking(body, key);
      const isCurrent = () => generation === openCardGeneration && fresh() && returnFocusTo() &&
        state.view === 'stays' && staysState.tab === 'units';
      openReservationCard(Number(bar.dataset.bar), rerender, { isCurrent, returnFocusTo })
        .catch(error => { if (isCurrent()) toast(error.message, 'err'); });
      return;
    }
    if (!can('stays.edit')) return;
    /* блок / OOO: клик по объекту — новый, по полосе блока — правка или удаление */
    const hold = e.target.closest('[data-hold]');
    if (hold) { openOooForm(data.holds.find(h => h.id === Number(hold.dataset.hold)), rerender); return; }
    const unit = e.target.closest('.sb-unit');
    const row = unit && unit.closest('[data-unit-row]');
    if (row) openOooForm({ unit_id: Number(row.dataset.unitRow) }, rerender);
  };
  const sorting = (prefix, mobile = false) => html`
      <select id=${prefix + 'sort'} title="Сортировка строк" aria-label=${mobile ? 'Сортировка строк' : nothing}
        @change=${e => { st.by = e.target.value; draw(); }}>${STAYS_SORTS.map(([v, t]) =>
        html`<option value=${v} ?selected=${v === st.by}>${t}</option>`)}</select>
      <select id=${prefix + 'dir'} title="Направление сортировки" @change=${e => { st.dir = e.target.value; draw(); }}>
        <option value="asc" ?selected=${st.dir === 'asc'}>↑</option><option value="desc" ?selected=${st.dir === 'desc'}>↓</option></select>
      <label class="chk"><input type="checkbox" id=${prefix + 'grouped'} .checked=${st.grouped}
        @change=${e => { st.grouped = e.target.checked; draw(); }}> группировать по дереву</label>`;
  const exportScope = showNames => showNames ? 'с данными гостей' : 'без данных гостей';
  const closeExport = menu => {
    menu.open = false;
    $('summary', menu).focus();
  };
  const exportAction = (label, perform, board = false) => html`<button type="button"
    class="btn btn-sm btn-ghost" ?data-sb-export=${board} @click=${event => {
      closeExport(event.currentTarget.closest('details'));
      perform();
    }}>${label}</button>`;
  const mobileExport = () => html`<details class="sb-mobile-exports" @focusout=${event => {
    const menu = event.currentTarget;
    if (menu.open && !menu.contains(event.relatedTarget)) menu.open = false;
  }} @keydown=${event => {
    if (event.key === 'Escape' && event.currentTarget.open) {
      event.preventDefault();
      closeExport(event.currentTarget);
    }
  }}>
    <summary class="btn btn-sm btn-ghost">Экспорт</summary>
    <div class="sb-mobile-export-items">
      ${exportAction('Шахматка XLSX ' + exportScope(names && can('stays.export')), () => downloadBoard('xlsx'), true)}
      ${exportAction('Шахматка PDF ' + exportScope(names), () => downloadBoard('pdf'), true)}
      ${exportAction('Печать ' + exportScope(names), printBoard, true)}
      ${exportAction('Сводка XLSX без данных гостей', xlsx('anon'))}
      ${can('stays.export') && can('stays.guests') ? exportAction('Сводка XLSX с данными гостей', xlsx('full')) : nothing}
    </div>
  </details>`;
  const unitsTemplate = () => html`
    <div class="sb-toolbar sb-units-toolbar">
      ${staysMonthNavView(body, rerender)}
      <div class="sb-desktop-tools hide-mobile">${sorting('sb-')}
      <button class="btn btn-sm btn-ghost" id="sb-xlsx-anon" title="Объекты, даты, статусы, число гостей — без данных гостей" @click=${xlsx('anon')}>Выгрузить (без гостей)</button>
      ${can('stays.export') && can('stays.guests') ? html`<button class="btn btn-sm btn-ghost" id="sb-xlsx-full" @click=${xlsx('full')}>Выгрузить полностью</button>` : nothing}
      <button class="btn btn-sm btn-ghost" data-sb-export id="sb-board-xlsx"
        title=${can('stays.export') ? 'Скачать текущую шахматку' : 'Без данных и фильтров по гостям'} @click=${() => downloadBoard('xlsx')}>Шахматка XLSX</button>
      <button class="btn btn-sm btn-ghost" data-sb-export id="sb-board-pdf" @click=${() => downloadBoard('pdf')}>PDF</button>
      <button class="btn btn-sm btn-ghost" data-sb-export id="sb-print" @click=${printBoard}>Печать</button>
      ${can('stays.edit') ? html`<button class="btn btn-sm btn-primary" id="sb-new" @click=${() => openReservationForm(null, { onSaved: rerender })}>+ Бронь</button>` : nothing}</div>
      ${mobileExport()}
    </div>
    ${staysFilterView(fund, rerender, { people: names, onSearchInput: disablePrint,
      mobileTools: html`<div class="sb-mobile-sort">${sorting('sb-mobile-', true)}</div>` })}
    ${data.warnings.length ? html`<div class="dict-banner gold"><span>⚠</span><span>${data.warnings.map((w, i) => html`${i ? html`<br>` : nothing}${w.text}`)}</span></div>` : nothing}
    <div class="sb-grid" role="group" tabindex="0" style=${`--days:${data.days.length}`} aria-label="Шахматка объектов"
      @click=${gridClick} @keydown=${gridKey} @focusin=${onGridFocus}>${gridTemplate(data, fund, byUnit, holdsBy, blocksBy, names)}</div>
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
        ${(byUnit[u.unit_id] || []).map(b => barTemplate(b, base, span, names, u.label))}
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
export async function openReservationCard(rid, onChanged, { isCurrent = () => true, returnFocusTo, silent = false } = {}) {
  const [card, history] = await Promise.all([
    api(`/api/stays/reservations/${rid}/card`, { silent }), api(`/api/stays/reservations/${rid}/history`, { silent })]);
  if (!isCurrent()) return;
  const role = { main: 'главный', guest: 'проживает' };
  /* батлер в своей брони (card.mine): карточки гостей (stays.mine) и «Изменить» (stays.mine_res_edit) —
     как в «Моих гостях»; назначения, статус и совместное проживание — только stays.edit / stays.assign */
  const guestCard = can('stays.guests') || (card.mine && can('stays.mine'));
  const mineEdit = !can('stays.edit') && card.mine && can('stays.mine_res_edit');
  const diffText = diff => Object.entries(diff || {}).map(([k, [a, b]], i) =>
    html`${i ? html`<br>` : nothing}${k}: ${JSON.stringify(a)} → ${JSON.stringify(b)}`);
  const relatives = relativesView;
  openModal({
    title: `Бронь ${card.number || '#' + card.id}`, wide: true, returnFocusTo,
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
      $$('[data-guest-card]', m).forEach(b => { b.onclick = () => {
        const origin = state.view;
        closeModal();
        openGuestCard(Number(b.dataset.guestCard), onChanged, {
          onOpenFamily: origin === 'stays' ? openBoardFamily : undefined, isCurrent: () => state.view === origin,
        }).catch(e => toast(e.message, 'err'));
      }; });
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
