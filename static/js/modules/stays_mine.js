/* ══════════════════════════════════════════════════════════════════════
   «МОИ ГОСТИ» (часть 4 §5): экран батлера с телефона, три вкладки —
   «Сегодня» (карточки броней этой ночи), «Мой месяц» (мини-шахматка с полосой нагрузки,
   месяц общий с Табелем: state.year/state.month) и «Все мои гости» (поиск по фамилии, карточка
   с историей: кто вёл). Данные — GET /api/stays/mine/{today,month,guests}. Кнопки «Изменить» — по
   правам stays.mine_res_edit / stays.mine_guest_edit (или stays.edit); открывают общие формы.
   Модуль на lit-html (ADR-0013, раздел 7).
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

import { can } from '../app.js';
import { $, api, closeModal, dateRu, loadGenerationFor, openModal, toast } from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { STAYS_ROLE, STAYS_STATUS, openGuestCard, openGuestForm, openReservationForm } from './stays_forms.js';
import {
  STAYS_SPECIAL_MARK, openReservationCard, staysAddDays, staysCodeTagView, staysDayHeadView, staysFocusDay, staysFund,
  staysGuestMarkView, staysMonthNavView, staysMonthRange, staysPos, staysToday, staysWeight,
} from './stays.js';

const MINE_TABS = [['today', 'Сегодня'], ['month', 'Мой месяц'], ['guests', 'Все мои гости']];
const MINE_LEVEL = { one: 'один гость', many: 'несколько гостей', over: 'выше лимита' };
const MINE_PAGE = 50;
export const mineState = { tab: 'today', q: '' };

const mineDdmm = iso => dateRu(iso).slice(0, 5);
const mineCanResEdit = () => can('stays.edit') || can('stays.mine_res_edit');
const mineCanGuestEdit = () => can('stays.edit') || can('stays.mine_guest_edit');

export async function renderMine() {
  const host = $('#view-mystays');
  render(html`<div class="page-head"><div><h2>Мои гости</h2></div></div>
    <div class="layer-tabs mine-tabs">${MINE_TABS.map(([id, title]) =>
      html`<button class=${`btn btn-sm${mineState.tab === id ? ' btn-primary' : ''}`} data-mtab=${id}
        @click=${() => { mineState.tab = id; renderMine(); }}>${title}</button>`)}</div>
    <div id="mine-body"></div>`, mount(host));
  const body = $('#mine-body', host);
  body.className = 'empty';
  render(html`Загрузка…`, mount(body));
  const fresh = loadGenerationFor(body);
  const draw = { today: renderMineToday, month: renderMineMonth, guests: renderMineGuests }[mineState.tab];
  try {
    await draw(body, fresh);
  } catch (e) {
    if (fresh()) { body.className = ''; render(html`<p class="muted">${e.message}</p>`, mount(body)); }
  }
}

/* ─────────────── «Сегодня» ─────────────── */
function mineLogisticsDay(date, today) {
  if (!date) return 'без даты';
  if (date === today) return 'сегодня';
  return date === staysAddDays(today, 1) ? 'завтра' : mineDdmm(date);
}

const mineTodayCard = (r, today) => html`<div class="panel mine-card" data-mine-card=${r.reservation_id}>
    <h3 class="panel-title">${r.unit || 'без объекта'}${r.departing ? html` <span class="badge warn">выезд сегодня</span>` : nothing}${r.status === 'tentative' ? html` <span class="badge muted">предварительная</span>` : nothing}</h3>
    <div class="muted">${r.number || ''} · заезд ${dateRu(r.check_in)} — выезд ${dateRu(r.check_out)}</div>
    ${r.note ? html`<p class="muted" data-mine-note>${r.note}</p>` : nothing}
    ${r.guests.map(g => html`<div class="mine-guest" data-mine-guest-row=${g.guest_id}>
      <b>${staysGuestMarkView(g.special)}${g.name}</b>${staysCodeTagView(g.vip_code)}
      <span class="muted">${STAYS_ROLE[g.role] || g.role}${g.phone ? ' · ' + g.phone : ''}</span>
      ${g.departing && !r.departing ? html` <span class="badge warn">выезд сегодня</span>` : nothing}
      ${Object.entries(g.preferences).filter(([, v]) => v).map(([k, v]) => html`<div class="muted">${k}: ${v}</div>`)}
      ${g.special_dates_soon.map(s => html`<div class="muted" data-mine-soon>🎉 ${dateRu(s.date)} — ${s.what}</div>`)}
      <button class="btn btn-sm btn-ghost" data-mine-guest=${g.guest_id}
        @click=${() => openMineGuest(g.guest_id, renderMine).catch(e => toast(e.message, 'err'))}>Карточка гостя</button></div>`)}
    ${r.logistics.map(l => html`<div data-mine-logistics>🚗 <b>${mineLogisticsDay(l.date, today)}</b> ${l.time} ${l.description}</div>`)}
    <div class="sb-line"><button class="btn btn-sm btn-ghost" data-mine-open=${r.reservation_id}
        @click=${() => openReservationCard(r.reservation_id, renderMine).catch(e => toast(e.message, 'err'))}>Бронь…</button>
      ${mineCanResEdit() ? html`<button class="btn btn-sm" data-mine-res=${r.reservation_id}
        @click=${() => openReservationForm(r.reservation_id, { mine: !can('stays.edit'), onSaved: renderMine })}>Изменить</button>` : nothing}</div>
  </div>`;

async function renderMineToday(body, fresh) {
  const data = await api('/api/stays/mine/today', { silent: true });
  if (!fresh()) return;
  body.className = '';
  render(html`<div class="muted mine-date">Сегодня, ${dateRu(data.date)}</div>
    ${data.reservations.length ? data.reservations.map(r => mineTodayCard(r, data.date))
      : html`<div class="empty">Сегодня гостей, которых вы ведёте, нет</div>`}`, mount(body));
}

/* ─────────────── «Мой месяц» ─────────────── */
function mineBar(b, base, span, none) {
  const left = Math.max(0, (b.start_pos - base) / span * 100);
  const right = Math.min(100, (b.end_pos - base + 1) / span * 100);
  if (right <= 0 || left >= 100) return nothing;
  const tentative = b.status === 'tentative';
  return html`<div class=${`sb-bar mm-bar${tentative ? ' tentative' : ''}${none ? ' mm-none' : ''}`} data-bar=${b.reservation_id}
    style=${`left:${left}%;width:${right - left}%`} title=${(tentative ? 'Предварительная · ' : '') + (b.main_guest || 'бронь')}
    @click=${() => openReservationCard(b.reservation_id, renderMine).catch(e => toast(e.message, 'err'))}>${staysGuestMarkView(b.special)}${b.main_guest || 'бронь'}${tentative ? ' · предв.' : ''}</div>`;
}

/* полоса нагрузки: число гостей в день, цвет — один / несколько / выше лимита; «О» — отсутствие по Графику
   (день может быть и с нагрузкой, и с «О» — рисуются обе отметки) */
function mineLoadCell(day, load, absent, limit) {
  const l = load[day];
  const tip = [l ? `${MINE_LEVEL[l.level]}: ${l.guests} гост., нагрузка ${staysWeight(l.value)} из ${staysWeight(limit)}` : '', absent.has(day) ? 'отсутствие по Графику' : ''].filter(Boolean).join(' · ');
  return html`<div class=${`mm-lc${l ? ' lv-' + l.level : ''}`} data-day=${day} data-load-level=${l ? l.level : nothing}
    data-absent=${absent.has(day) ? '1' : nothing} title=${tip || nothing}>${l ? l.guests : ''}${absent.has(day) ? html`<b class="mm-abs">О</b>` : nothing}</div>`;
}

function mineMonthGrid(data) {
  const today = staysToday();
  const base = staysPos(data.days[0], 0);
  const span = data.days.length * 2;
  const load = Object.fromEntries(data.load.map(x => [x.day, x]));
  const absent = new Set(data.absences);
  return html`<div class="sb-row sb-head"><div class="sb-unit">Объект</div><div class="sb-track sb-days">${data.days.map(d => staysDayHeadView(d, today))}</div></div>
    <div class="sb-row mm-load" data-mine-load><div class="sb-unit"><b>Нагрузка</b><small>лимит ${staysWeight(data.limit)}</small></div>
      <div class="sb-track sb-days">${data.days.map(d => mineLoadCell(d, load, absent, data.limit))}</div></div>
    ${data.rows.length ? data.rows.map(row => html`<div class=${`sb-row${row.unit_id == null ? ' mm-none-row' : ''}`} data-mine-row=${row.unit_id ?? 'none'}>
      <div class="sb-unit"><b>${row.label}</b></div>
      <div class="sb-track">${row.bars.map(b => mineBar(b, base, span, row.unit_id == null))}</div></div>`)
      : html`<div class="empty">В этом месяце своих броней нет</div>`}`;
}

async function renderMineMonth(body, fresh) {
  const { first, last } = staysMonthRange();
  const data = await api(`/api/stays/mine/month?first=${first}&last=${last}`, { silent: true });
  if (!fresh()) return;
  body.className = '';
  render(html`<div class="sb-toolbar">${staysMonthNavView(body, renderMine)}</div>
    <div class="muted mm-legend"><span class="mm-key lv-one"></span> один гость <span class="mm-key lv-many"></span> несколько
      <span class="mm-key lv-over"></span> выше лимита · <b class="mm-abs">О</b> — отсутствие</div>
    <div class="sb-grid mm-grid" style=${`--days:${data.days.length}`}>${mineMonthGrid(data)}</div>`, mount(body));
  staysFocusDay(body);
}

/* ─────────────── «Все мои гости» ─────────────── */
const mineGuestRow = g => html`<div class="mine-grow" data-mine-grow=${g.guest_id} tabindex="0"
    @click=${() => openMineGuest(g.guest_id, renderMine).catch(e => toast(e.message, 'err'))}
    @keydown=${e => { if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); e.currentTarget.click(); } }}>
    <b>${staysGuestMarkView(g.special)}${g.name}</b>${staysCodeTagView(g.vip_code)}
    <span class="muted">${g.last_stay ? 'последний заезд ' + dateRu(g.last_stay) : 'не жил'} · проживаний ${g.stays}${
      g.next_stay ? ' · следующий заезд ' + dateRu(g.next_stay) : ''}</span></div>`;

async function renderMineGuests(body) {
  body.className = '';
  let timer = null;
  render(html`<div class="sb-toolbar"><input type="search" id="mg-q" .value=${mineState.q} placeholder="Фамилия гостя" @input=${e => {
      clearTimeout(timer);
      const value = e.target.value;
      timer = setTimeout(() => { mineState.q = value; reload(); }, 300);
    }}></div>
    <div id="mg-result"></div>`, mount(body));
  const result = $('#mg-result', body);
  render(html`<div class="empty">Загрузка…</div>`, result);
  let rows = [];
  let total = 0;
  const page = offset => api(`/api/stays/mine/guests?q=${encodeURIComponent(mineState.q.trim())}&offset=${offset}&limit=${MINE_PAGE}`, { silent: true });
  const paint = () => {
    const more = async e => {
      e.currentTarget.disabled = true;
      const fresh = loadGenerationFor(result);
      try {
        const next = await page(rows.length);
        if (!fresh()) return;
        rows = rows.concat(next.rows); total = next.total;
      } catch (err) { toast(err.message, 'warn'); }
      paint();
    };
    render(html`<div class="muted" id="mg-total">Гостей: ${total}</div>
      ${rows.length ? rows.map(mineGuestRow) : html`<div class="empty">Своих гостей по запросу нет</div>`}
      ${rows.length < total ? html`<button class="btn" id="mg-more" @click=${more}>Показать ещё ${Math.min(MINE_PAGE, total - rows.length)}</button>` : nothing}`, result);
  };
  const reload = async () => {
    const fresh = loadGenerationFor(result);
    try {
      ({ rows, total } = await page(0));
    } catch (e) {
      if (fresh()) render(html`<p class="muted">${e.message}</p>`, result);
      return;
    }
    if (fresh()) paint();
  };
  await reload();
}

/* «вёл я 03.05–08.05» / «вёл(а) Кузнецова 03.05–08.05»: last с сервера — утро после последней ночи, как есть */
const mineLed = l => html`<div class="muted" data-mine-led data-me=${l.me ? '1' : nothing}>${l.me ? 'вёл я' : 'вёл(а) ' + l.name} ${mineDdmm(l.first)}–${mineDdmm(l.last)}</div>`;

async function openMineGuest(gid, onChanged) {
  const [g, fund] = await Promise.all([api(`/api/stays/mine/guests/${gid}`), staysFund().catch(() => ({ fields: [] }))]);
  const titles = Object.fromEntries(fund.fields.filter(f => f.target === 'guest').map(f => [f.code, f.title]));
  const prefs = Object.entries(g.preferences).filter(([, v]) => v);
  const canEdit = mineCanGuestEdit();
  openModal({
    title: `${g.special ? STAYS_SPECIAL_MARK : ''}${g.last_name} ${g.first_name} ${g.middle_name}`.trim(), wide: true,
    subtitle: [g.vip_code ? `VIP-код ${g.vip_code.code}` : '', g.phone_display, g.birth_date ? 'др ' + dateRu(g.birth_date) : ''].filter(Boolean).join(' · '),
    body: html`<h4>Предпочтения</h4>${prefs.length ? prefs.map(([k, v]) => html`<div>${k}: ${v}</div>`) : html`<span class="muted">нет</span>`}
      ${g.special_dates.length ? html`<h4>Особые даты</h4>${g.special_dates.map(d => html`<div>${dateRu(d.date)} — ${d.what}</div>`)}` : nothing}
      ${Object.keys(g.fields).length ? html`<h4>Дополнительно</h4>${Object.entries(g.fields).map(([k, v]) => html`<div>${titles[k] || k}: ${String(v)}</div>`)}` : nothing}
      ${g.note ? html`<h4>Примечание</h4><p data-mine-note>${g.note}</p>` : nothing}
      ${g.links.length ? html`<h4>Связи</h4>${g.links.map(l => html`<div>${l.name} <span class="muted">${l.label}</span></div>`)}` : nothing}
      <h4>История проживаний</h4>
      <div id="mg-history" class="sb-history">${g.history.length ? g.history.map(h => html`<div data-mine-hist=${h.reservation_id}><b>${h.number || '#' + h.reservation_id}</b> · ${h.unit}
        · ${dateRu(h.check_in)}–${dateRu(h.check_out)} · ${STAYS_STATUS[h.status] || h.status}
        ${h.led.length ? h.led.map(mineLed) : html`<div class="muted">батлер не назначался</div>`}</div>`) : html`<span class="muted">проживаний нет</span>`}</div>`,
    footer: html`<button class="btn btn-ghost" data-close>Закрыть</button>
      <button class="btn" id="mg-family">Семья, связи, пожелания…</button>
      ${canEdit ? html`<button class="btn btn-primary" id="mg-edit">Изменить профиль</button>` : nothing}`,
    onMount(m) {
      $('[data-close]', m).onclick = closeModal;
      const reopen = () => { openMineGuest(gid, onChanged).catch(e => toast(e.message, 'err')); if (onChanged) onChanged(); };
      $('#mg-family', m).onclick = () => openGuestCard(gid, onChanged).catch(e => toast(e.message, 'err'));
      const edit = $('#mg-edit', m);
      if (edit) edit.onclick = () => openGuestForm(gid, reopen, { mine: !can('stays.edit') }).catch(e => toast(e.message, 'err'));
    },
  });
}

/* ── мост к общей области имён (генерируется tools/gen_js_globals.py; уйдёт вместе с переходом файла на import/export) ── */
Object.assign(globalThis, {
  mineState,
  renderMine,
});
/* ── конец моста ── */
