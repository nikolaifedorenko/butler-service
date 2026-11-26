'use strict';
/* ══════════════════════════════════════════════════════════════════
   СЕГОДНЯ — стартовый экран.
   Свой набор блоков у каждого по правам и привязке к сотруднику:
     * сотрудник — смена и кнопка «Пришёл / Ушёл»;
     * батлер (stays.mine) — мои брони, что важно сейчас, мои гости;
     * руководитель (presence.view) — сколько на работе и кого ещё ждём;
     * все остальные — быстрые переходы по их меню.
   Данные — те же ответы API, что у разделов: отдельного серверного кода у экрана нет.
   ══════════════════════════════════════════════════════════════════ */
import { can, navigate, poll, registerModule } from '../app.js';
import {
  $, api, authContextIsCurrent, authContextSnapshot, hhmm, loadGeneration, MONTHS_GEN, serverShiftMs, state, syncServerClock, toast, todayISO, WD,
} from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { dataState } from '../ui/data_state.js';
import { openOtNoteModal } from './me.js';
import { openOwnReservationCard, openReservationCard, openTodayDayBoard } from './stays.js';
import { guestPreferenceLabel } from './stays_forms.js';

registerModule({ views: { today: loadToday } });

const READ_ERRORS = {
  status: 'Не удалось загрузить статус смены.',
  mine: 'Не удалось загрузить гостей.',
  board: 'Не удалось загрузить данные о присутствии.',
  all: 'Не удалось загрузить данные на сегодня.',
};
const RETRY_LABELS = {
  status: 'Повторить загрузку статуса смены',
  mine: 'Повторить загрузку гостей',
  board: 'Повторить загрузку данных о присутствии',
  all: 'Повторить загрузку данных на сегодня',
};
const READ_CHECKS = {
  status: data => typeof data?.on_shift === 'boolean',
  mine: data => typeof data?.date === 'string' && Array.isArray(data.reservations),
  board: data => Array.isArray(data?.yet_to_come),
};

async function loadToday() {
  const started = authContextSnapshot(), owner = state.user, fresh = loadGeneration('today');
  const current = () => owner && owner === state.user && state.view === 'today' && fresh() && authContextIsCurrent(started);
  if (!current()) return;
  const paths = {
    status: owner.employee_id && '/api/punches/status',
    mine: owner.employee_id && can('stays.mine') && '/api/stays/mine/today',
    board: can('presence.view') && '/api/presence/board',
  };
  const blocks = Object.keys(paths).filter(key => paths[key]);
  const errors = new Set(), pending = new Set();
  const view = { busy: false, statusRevision: 0, cardRequest: 0, current, blocks, errors, pending, refresh };

  async function read(key) {
    const revision = view.statusRevision;
    const data = await api(paths[key], { silent: true }).catch(() => null);
    pending.delete(key);
    if (!current() || (key === 'status' && revision !== view.statusRevision)) return;
    if (READ_CHECKS[key](data)) {
      view[key] = data;
      errors.delete(key);
      if (key === 'status') syncServerClock(data.now);
    } else {
      view[key] = null;
      errors.add(key);
    }
    draw(view);
  }

  async function refresh(keys = blocks) {
    if (!current()) return;
    const keysToRead = keys.filter(key => !pending.has(key) && !(key === 'status' && view.busy));
    keysToRead.forEach(key => pending.add(key));
    draw(view);
    await Promise.all(keysToRead.map(read));
  }
  await refresh();
  if (current()) poll('today', refresh);
}

function draw(view) {
  const host = $('#view-today');
  if (!host) return;
  const previous = document.activeElement;
  const target = host.contains(previous) && previous.dataset.todayRetry;
  const reservation = host.contains(previous) && previous.dataset.reservation;
  render(screen(view), mount(host));
  if (reservation && document.activeElement?.dataset.reservation !== reservation) {
    (bookingTrigger(reservation) || bookingFallback())?.focus();
  }
  if (target && !previous.isConnected && document.activeElement === document.body) {
    const recovered = $(`[data-today-ready="${target}"]`, host) || $('[data-today-retry]', host) || $('.today-hello', host);
    recovered?.focus({ preventScroll: true });
  }
}

/* ── шапка: приветствие, дата, смена ── */
function greeting() {
  const hour = new Date(Date.now() + serverShiftMs).getUTCHours();
  return hour < 5 ? 'Доброй ночи' : hour < 12 ? 'Доброе утро' : hour < 18 ? 'Добрый день' : 'Добрый вечер';
}

function firstName() {
  const parts = String(state.user.name || '').trim().split(/\s+/);
  return parts[1] || parts[0] || '';
}

function dateLine() {
  const d = new Date(todayISO() + 'T00:00:00');
  const wd = WD[d.getDay()];
  return `${wd[0].toUpperCase()}${wd.slice(1)}, ${d.getDate()} ${MONTHS_GEN[d.getMonth()]}`;
}

async function punch(view) {
  const s = view.status;
  if (!s || view.busy || !view.current()) return;
  view.busy = true;
  view.statusRevision++;
  draw(view);
  try {
    const res = await api('/api/punches', { method: 'POST', body: { kind: s.on_shift ? 'out' : 'in' } });
    if (!view.current()) return;
    toast(res.message, 'ok', res.warnings || []);
    view.status = res.status;
    state.status = res.status;
    if (res.punch?.kind === 'OUT') openOtNoteModal(res.punch.id, '', 0);
  } catch (e) {
    if (view.current()) toast(e.message, 'err');
  } finally {
    view.busy = false;
    if (view.current()) draw(view);
  }
}

function shiftStrip(view) {
  const s = view.status;
  if (!s) return nothing;
  const canIn = s.punch_in_allowed !== false;
  const canOut = s.punch_out_allowed !== false;
  let line; let action = nothing;
  if (s.on_shift) {
    line = html`<div class="today-shift-k">${s.shift ? `Смена ${s.shift.start_hm}–${s.shift.end_hm}` : 'Вне графика'}</div>
      <div class="today-shift-v">На смене с ${hhmm(s.session_start)}${s.planned_end ? ` · до ${hhmm(s.planned_end)}` : ''}</div>`;
    if (canOut) action = html`<button class="btn today-punch" id="today-punch" ?disabled=${view.busy} @click=${() => punch(view)}>Ушёл</button>`;
  } else if (s.shift) {
    line = html`<div class="today-shift-k">Смена ${s.shift.start_hm}–${s.shift.end_hm}</div>
      <div class="today-shift-v">${canIn ? 'Ещё не на смене' : (s.punch_status_hint || 'Отметка сейчас недоступна')}</div>`;
    if (canIn) action = html`<button class="btn today-punch" id="today-punch" ?disabled=${view.busy} @click=${() => punch(view)}>Пришёл</button>`;
  } else {
    /* по Графику смены нет, но отметиться можно: часы учтутся как переработка — как в «Моих отметках» */
    line = html`<div class="today-shift-k">График</div>
      <div class="today-shift-v">Сегодня смены нет${canIn ? '' : ` · ${s.punch_status_hint || 'отметка недоступна'}`}</div>
      ${canIn ? html`<div class="today-shift-k">Часы будут учтены как переработка.</div>` : nothing}`;
    if (canIn) action = html`<button class="btn today-punch" id="today-punch" ?disabled=${view.busy} @click=${() => punch(view)}>Пришёл</button>`;
  }
  return html`<div class="today-shift" data-today-ready="status" tabindex="-1"><div class="today-shift-text">${line}</div>${action}</div>`;
}

function loadError(view, key) {
  const blocks = key === 'all' ? view.blocks : [key];
  const waiting = blocks.some(block => view.pending.has(block));
  return html`<div class="today-load-error" data-today-error=${key}>
    ${dataState('error', waiting ? 'Повторяем загрузку…' : READ_ERRORS[key], html`
      <button class="btn btn-sm" data-today-retry=${key} aria-label=${RETRY_LABELS[key]} aria-disabled=${waiting}
        @click=${() => { if (!blocks.some(block => view.pending.has(block))) view.refresh(blocks); }}>Повторить</button>`)}
  </div>`;
}

function todayBlock(view, key, content) {
  if (view.errors.has(key)) return loadError(view, key);
  if (!view[key] && view.pending.has(key)) {
    return dataState('loading', { status: 'Загружаем смену…', mine: 'Загружаем гостей…', board: 'Загружаем присутствие…' }[key]);
  }
  return content(view);
}

function head(view, allFailed) {
  return html`<header class="today-head">
    <div class="today-date">${dateLine()}</div>
    <h2 class="today-hello" tabindex="-1">${greeting()}${firstName() ? html`, ${firstName()}` : nothing}</h2>
    ${allFailed ? nothing : todayBlock(view, 'status', shiftStrip)}
  </header>`;
}

/* ── батлер: мои брони ── */
const nightsBetween = (a, b) => Math.round((new Date(b) - new Date(a)) / 86400000);
const isArrival = (r, today) => r.check_in === today && !r.departing;
const WEDDING_ANNIVERSARY = 'Годовщина свадьбы';

function resTag(r, today) {
  if (r.departing) return { cls: 'warn', text: 'Выезд сегодня' };
  if (isArrival(r, today)) return { cls: 'info', text: 'Заезд сегодня' };
  const day = nightsBetween(r.check_in, today) + 1;
  return { cls: 'muted', text: `Проживает · ночь ${day} из ${nightsBetween(r.check_in, r.check_out)}` };
}

function leadName(r) {
  const [first, ...rest] = r.guests;
  if (!first) return 'Гость брони';
  return html`${first.name}${first.vip_code ? html` <span class="badge warn today-vip">VIP ${first.vip_code}</span>` : nothing}${
    rest.length ? html` <span class="today-more">и ещё ${rest.length}</span>` : nothing}`;
}

function logisticsLine(r) {
  const items = (r.logistics || []).map(l => `${l.time ? l.time + ' ' : ''}${l.description}`.trim()).filter(Boolean);
  return items.join(' · ');
}

function resNotes(r) {
  const prefs = r.guests.flatMap(g => Object.entries(g.preferences || {}).filter(([, v]) => v)
    .map(([k, v]) => `${guestPreferenceLabel(k)}: ${v}`));
  return [logisticsLine(r), r.note, ...prefs.slice(0, 2)].filter(Boolean).join('. ');
}

const bookingTrigger = id => $(`#view-today [data-reservation="${CSS.escape(String(id))}"]`);
const bookingFallback = () => $('#view-today [data-today-ready="mine"]') ||
  $('#view-today [data-today-retry="mine"]') || $('#view-today .today-hello');

function openTodayBooking(view, r) {
  if (view.pendingCard === r.reservation_id) return;
  const returnFocusTo = () => bookingTrigger(r.reservation_id) || bookingFallback();
  const request = ++view.cardRequest;
  const isCurrent = () => {
    const card = bookingTrigger(r.reservation_id);
    return view.current() && request === view.cardRequest && card && !card.closest('[inert]');
  };
  if (!isCurrent()) return;
  if (!can('stays.view')) {
    openOwnReservationCard(r, { returnFocusTo, detail: resNotes(r) });
    return;
  }
  view.pendingCard = r.reservation_id;
  draw(view);
  openReservationCard(r.reservation_id, () => view.refresh(), { isCurrent, returnFocusTo, silent: true })
    .catch(() => { if (isCurrent()) toast('Не удалось открыть бронь. Попробуйте ещё раз.', 'err'); })
    .finally(() => {
      if (request !== view.cardRequest) return;
      view.pendingCard = null;
      if (view.current()) draw(view);
    });
}

function resCard(view, r, today, anniversaryGuests) {
  const tag = resTag(r, today);
  const soon = r.guests.flatMap(g => (g.special_dates_soon || []).filter(mark =>
    !anniversaryGuests.has(g.guest_id) || mark.date !== today
    || mark.what.trim().toLowerCase() !== WEDDING_ANNIVERSARY.toLowerCase()));
  const opening = view.pendingCard === r.reservation_id;
  return html`<button class="today-card" data-reservation=${r.reservation_id}
    aria-busy=${opening ? 'true' : nothing} @click=${() => openTodayBooking(view, r)}>
    <span class="today-card-top"><span class="badge ${tag.cls}">${tag.text}</span><span class="today-unit">${r.unit || 'без объекта'}</span></span>
    <span class="today-name">${leadName(r)}</span>
    ${resNotes(r) ? html`<span class="today-text">${resNotes(r)}</span>` : nothing}
    ${opening ? html`<span class="today-text">Открываем бронь…</span>` : nothing}
    ${soon.length ? html`<span class="today-soon">${soon[0].what} — ${soon[0].date.slice(8, 10)}.${soon[0].date.slice(5, 7)}</span>` : nothing}
  </button>`;
}

function anniversaryBlock(anniversaries) {
  if (!anniversaries?.length) return nothing;
  return html`<section class="today-body" aria-labelledby="today-important-heading">
    <h3 class="today-h" id="today-important-heading">Сейчас важно</h3>
    ${anniversaries.map(({ guests }) => html`<div class="alert info">
      <div><strong>${WEDDING_ANNIVERSARY}</strong><div>${guests.map(g => g.name).join(' и ')}</div></div>
    </div>`)}
  </section>`;
}

function mineBlocks(view) {
  const m = view.mine;
  if (!m) return nothing;
  const today = m.date;
  const list = m.reservations;
  const anniversaries = m.anniversaries || [];
  const anniversaryGuests = new Set(anniversaries.flatMap(a => a.guests.map(g => g.guest_id)));
  const arrivals = list.filter(r => isArrival(r, today));
  const departures = list.filter(r => r.departing);
  const movements = [...arrivals, ...departures];
  const rest = list.filter(r => !r.departing && !isArrival(r, today));
  return html`
    <div class="stat-grid today-stats">
      <div class="stat"><div class="v" data-stat="mine">${list.length}</div><div class="k">мои брони</div></div>
      <div class="stat"><div class="v" data-stat="in">${arrivals.length}</div><div class="k">заезд</div></div>
      <div class="stat"><div class="v" data-stat="out">${departures.length}</div><div class="k">выезд</div></div>
    </div>
    ${anniversaryBlock(anniversaries)}
    <section class="today-body" aria-labelledby="today-movements-heading">
      <h3 class="today-h" id="today-movements-heading">Заезды и выезды сегодня</h3>
      ${movements.length ? movements.map(r => resCard(view, r, today, anniversaryGuests))
        : html`<div class="alert info" data-empty="movements">Сегодня заездов и выездов нет.</div>`}
    </section>
    <h3 class="today-h" data-today-ready="mine" tabindex="-1">Мои гости</h3>
    ${rest.length ? rest.map(r => resCard(view, r, today, anniversaryGuests))
      : html`<div data-empty="guests">${dataState('empty', movements.length ? 'Других гостей на сегодня нет' : 'Сегодня вы никого не ведёте')}</div>`}
    <div class="today-more-link"><button class="btn btn-sm btn-ghost" @click=${() => navigate('mystays')}>Все мои гости</button></div>`;
}

/* ── руководитель: присутствие ── */
function boardBlock(view) {
  const b = view.board;
  if (!b) return nothing;
  const late = b.yet_to_come.filter(a => a.already_started);
  return html`
    <h3 class="today-h" data-today-ready="board" tabindex="-1">Присутствие</h3>
    <div class="stat-grid today-stats">
      <div class="stat accent"><div class="v" data-stat="at-work">${b.at_work_now}</div><div class="k">на работе</div></div>
      <div class="stat"><div class="v" data-stat="expected">${b.expected_now}</div><div class="k">по графику сейчас</div></div>
      <div class="stat ${late.length ? 'danger' : ''}"><div class="v" data-stat="late">${late.length}</div><div class="k">не пришли вовремя</div></div>
    </div>
    ${late.length ? html`<div class="alert warn" data-late>${late.slice(0, 5).map(a => (a.employee || {}).short_name || a.employee_id).join(', ')}${
      late.length > 5 ? ` и ещё ${late.length - 5}` : ''} — ожидались раньше.</div>` : nothing}
    <div class="today-more-link"><button class="btn btn-sm" @click=${() => navigate('marks')}>Открыть «Отметки»</button></div>`;
}

/* ── остальные: быстрые переходы по своему меню ── */
function shortcuts() {
  const items = (state.menu || []).filter(t => t.id !== 'today').slice(0, 8);
  if (!items.length) return nothing;
  return html`<h3 class="today-h">Разделы</h3>
    <div class="today-shortcuts">${items.map(t => html`<button class="btn" data-go=${t.id} @click=${() => navigate(t.id)}>${t.title}</button>`)}</div>`;
}

function screen(view) {
  const allFailed = view.blocks.length > 0 && view.errors.size === view.blocks.length;
  return html`<div class="today">
    ${head(view, allFailed)}
    <div class="today-body">
      ${state.user.role === 'supervisor' && can('stays.view') ? html`<div class="only-mobile today-day-link">
        <button class="btn" @click=${openTodayDayBoard}>Табло дня</button>
      </div>` : nothing}
      ${allFailed ? loadError(view, 'all') : html`
        ${todayBlock(view, 'mine', mineBlocks)}
        ${todayBlock(view, 'board', boardBlock)}
        ${view.blocks.includes('mine') || view.blocks.includes('board') ? nothing : shortcuts()}`}
    </div>
  </div>`;
}
