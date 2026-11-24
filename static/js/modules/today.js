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
import { openOtNoteModal } from './me.js';

registerModule({ views: { today: loadToday } });

const PREF_TITLES = { allergy: 'Аллергия', food: 'Питание', habits: 'Привычки' };

async function loadToday() {
  const started = authContextSnapshot(), owner = state.user, fresh = loadGeneration('today');
  const current = () => owner && owner === state.user && state.view === 'today' && fresh() && authContextIsCurrent(started);
  if (!current()) return;
  const view = { loaded: false, busy: false, current };
  async function refresh() {
    if (!current()) return;
    const read = path => api(path, { silent: true }).catch(() => null);
    const [status, mine, board] = await Promise.all([
      owner.employee_id ? read('/api/punches/status') : null,
      owner.employee_id && can('stays.mine') ? read('/api/stays/mine/today') : null,
      can('presence.view') ? read('/api/presence/board') : null,
    ]);
    if (!current()) return;
    Object.assign(view, { status, mine, board, loaded: true });
    if (status) syncServerClock(status.now);
    draw(view);
  }
  draw(view);
  await refresh();
  if (current()) poll('today', refresh);
}

function draw(view) {
  const host = $('#view-today');
  if (host) render(screen(view), mount(host));
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
      <div class="today-shift-v">Сегодня смены нет${canIn ? '' : ` · ${s.punch_status_hint || 'отметка недоступна'}`}</div>`;
    if (canIn) action = html`<button class="btn today-punch" id="today-punch" ?disabled=${view.busy} @click=${() => punch(view)}>Пришёл</button>`;
  }
  return html`<div class="today-shift"><div class="today-shift-text">${line}</div>${action}</div>`;
}

function head(view) {
  return html`<header class="today-head">
    <div class="today-date">${dateLine()}</div>
    <h2 class="today-hello">${greeting()}${firstName() ? html`, ${firstName()}` : nothing}</h2>
    ${shiftStrip(view)}
  </header>`;
}

/* ── батлер: мои брони ── */
const nightsBetween = (a, b) => Math.round((new Date(b) - new Date(a)) / 86400000);
const isArrival = (r, today) => r.check_in === today && !r.departing;

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
    .map(([k, v]) => `${PREF_TITLES[k] || k}: ${v}`));
  return [logisticsLine(r), r.note, ...prefs.slice(0, 2)].filter(Boolean).join('. ');
}

function resCard(r, today, urgent = false) {
  const tag = resTag(r, today);
  const soon = r.guests.flatMap(g => g.special_dates_soon || []);
  return html`<button class="today-card ${urgent ? 'urgent' : ''}" data-reservation=${r.reservation_id} @click=${() => navigate('mystays')}>
    <span class="today-card-top"><span class="badge ${tag.cls}">${tag.text}</span><span class="today-unit">${r.unit || 'без объекта'}</span></span>
    <span class="today-name">${leadName(r)}</span>
    ${resNotes(r) ? html`<span class="today-text">${resNotes(r)}</span>` : nothing}
    ${soon.length ? html`<span class="today-soon">${soon[0].what} — ${soon[0].date.slice(8, 10)}.${soon[0].date.slice(5, 7)}</span>` : nothing}
  </button>`;
}

function mineBlocks(view) {
  const m = view.mine;
  if (!m) return nothing;
  const today = m.date;
  const list = m.reservations;
  const arrivals = list.filter(r => isArrival(r, today));
  const departures = list.filter(r => r.departing);
  const important = arrivals[0] || departures[0] || null;
  const rest = list.filter(r => r !== important);
  return html`
    <div class="stat-grid today-stats">
      <div class="stat"><div class="v" data-stat="mine">${list.length}</div><div class="k">мои брони</div></div>
      <div class="stat"><div class="v" data-stat="in">${arrivals.length}</div><div class="k">заезд</div></div>
      <div class="stat"><div class="v" data-stat="out">${departures.length}</div><div class="k">выезд</div></div>
    </div>
    <h3 class="today-h">Сейчас важно</h3>
    ${important ? resCard(important, today, true) : html`<div class="alert info" data-empty="important">Срочного нет: заездов и выездов на сегодня нет.</div>`}
    <h3 class="today-h">Мои гости</h3>
    ${rest.length ? rest.map(r => resCard(r, today))
      : html`<div class="empty" data-empty="guests">${important ? 'Других гостей на сегодня нет' : 'Сегодня вы никого не ведёте'}</div>`}
    <div class="today-more-link"><button class="btn btn-sm btn-ghost" @click=${() => navigate('mystays')}>Все мои гости</button></div>`;
}

/* ── руководитель: присутствие ── */
function boardBlock(view) {
  const b = view.board;
  if (!b) return nothing;
  const late = b.yet_to_come.filter(a => a.already_started);
  return html`
    <h3 class="today-h">Присутствие</h3>
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
  if (!view.loaded) return html`<div class="today"><div class="skel-wrap"><div class="skel-line skel-lg"></div><div class="skel-line"></div><div class="skel-line"></div></div></div>`;
  const hasBlocks = view.status || view.mine || view.board;
  return html`<div class="today">
    ${head(view)}
    <div class="today-body">
      ${mineBlocks(view)}
      ${boardBlock(view)}
      ${hasBlocks && (view.mine || view.board) ? nothing : shortcuts()}
    </div>
  </div>`;
}
