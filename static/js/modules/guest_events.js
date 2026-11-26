import { can, registerModule } from '../app.js';
import { $, api, authContextIsCurrent, authContextSnapshot, loadGenerationFor, state, toast, todayISO } from '../core.js';
import { dataState } from '../ui/data_state.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { periodNav } from '../ui/period_nav.js';
import { openReservationCard } from './stays.js';
import { openGuestCard } from './stays_forms.js';

const TITLE = 'Календарь событий';
const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
const KINDS = [
  ['birthday', 'Дни рождения', 'День рождения'],
  ['wedding', 'Годовщины свадьбы', 'Годовщина свадьбы'],
  ['special', 'Особые даты', 'Особая дата'],
];
const KIND_LABELS = Object.fromEntries(KINDS.map(([id, , singular]) => [id, singular]));
const STAY_STATUS = {
  staying: 'Проживает', arrival: 'Заезд', checkout: 'Выезд', tentative: 'Предварительная бронь',
  none: 'Брони на эту дату нет', unavailable: 'Сведения о брони недоступны',
};
const CONFIRMED = new Set(['staying', 'arrival', 'checkout']);
const locale = options => new Intl.DateTimeFormat('ru-RU', { ...options, timeZone: 'UTC' });
const monthLabel = locale({ month: 'long' });
const dayLabel = locale({ day: 'numeric', month: 'long' });
const weekdayLabel = locale({ weekday: 'long' });
const accessibleDate = locale({ day: 'numeric', month: 'long', year: 'numeric' });
const plurals = new Intl.PluralRules('ru');
const cap = label => label[0].toUpperCase() + label.slice(1);
const dateValue = iso => new Date(iso + 'T00:00:00Z');
const iso = date => date.toISOString().slice(0, 10);
const firstOfMonth = date => date.slice(0, 7) + '-01';
const dayNumber = date => Number(date.slice(8, 10));
const weekday = date => (dateValue(date).getUTCDay() + 6) % 7;
const eventCount = count => count + ' ' + ({ one: 'событие', few: 'события', many: 'событий' }[plurals.select(count)] || 'события');
const emptyFilters = () => ({ kind: '', confirmed: false, vip: [], special: false });
const denied = () => dataState('error', 'Календарь событий недоступен.');
const isDate = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
  && Number.isFinite(dateValue(value).valueOf()) && iso(dateValue(value)) === value;

registerModule({ views: { guestevents: loadGuestEvents } });

function stepDay(day, delta) {
  const date = dateValue(day);
  date.setUTCDate(date.getUTCDate() + delta);
  return iso(date);
}

function stepMonth(month, delta) {
  const date = dateValue(month);
  date.setUTCMonth(date.getUTCMonth() + delta);
  return iso(date);
}

function monthWeeks(month) {
  const first = stepDay(month, -weekday(month));
  const last = stepDay(stepMonth(month, 1), -1);
  const end = stepDay(last, 6 - weekday(last));
  const weeks = [];
  for (let start = first; start <= end; start = stepDay(start, 7)) {
    weeks.push(WEEKDAYS.map((_, index) => stepDay(start, index)));
  }
  return weeks;
}

function calendarGrid(month, selected, today, eventsByDate, busy, pick, keydown) {
  return html`<div class="ge-calendar" role="grid" aria-label="Месяц" aria-busy=${busy}
    @keydown=${keydown}>
    <div class="ge-week ge-week-labels" role="row">${WEEKDAYS.map(name => html`<div role="columnheader">${name}</div>`)}</div>
    ${monthWeeks(month).map(week => html`<div class="ge-week" role="row">${week.map(day => {
      if (firstOfMonth(day) !== month) return html`<div role="gridcell" class="ge-filler">${dayNumber(day)}</div>`;
      const events = eventsByDate.get(day) || [];
      const date = dateValue(day);
      const label = (day === today ? 'Сегодня ' : '') + accessibleDate.format(date) + ', ' + weekdayLabel.format(date);
      return html`<div role="gridcell" class="ge-cell"><button type="button" class="ge-day" data-ge-date=${day}
        tabindex=${selected === day ? '0' : '-1'} aria-pressed=${selected === day} aria-current=${day === today ? 'date' : nothing}
        aria-label=${label + (events.length ? ' · ' + eventCount(events.length) : '')}
        @click=${() => pick(day)}>
        <span class="ge-day-number" aria-hidden="true">${day === today ? html`<span>Сегодня</span> ` : nothing}${dayNumber(day)}</span>
      </button>
      ${events.length ? html`<div class="ge-cell-events" aria-hidden="true">
        ${events.slice(0, 2).map(event => html`<span class="ge-preview" data-ge-kind=${event.kind}>
          <span class="ge-preview-name">${event.people.map(g => g.name).join(' и ')}</span>
          <span class="ge-preview-type">${KIND_LABELS[event.kind]}</span>
        </span>`)}
        ${events.length > 2 ? html`<span class="ge-overflow">Ещё ${events.length - 2}</span>` : nothing}
        <span class="ge-mobile-count">${events.length}</span>
      </div>` : nothing}</div>`;
    })}</div>`)}
  </div>`;
}

function filterPanel(filters, allowed, update, reset, close, moveFocus) {
  const count = Number(!!filters.kind) + Number(filters.confirmed) + filters.vip.length + Number(filters.special);
  function dismiss(event) {
    if (event.key !== 'Escape' || !event.currentTarget.open) return;
    event.stopPropagation();
    event.preventDefault();
    close();
  }
  return html`<details class="ge-filters" @keydown=${dismiss}>
    <summary class="btn btn-sm" aria-controls="ge-filter-panel">Фильтры${count ? html` (${count})` : nothing}</summary>
    <div class="ge-filter-panel panel" id="ge-filter-panel">
      <label class="field"><span>Тип события</span><select .value=${filters.kind}
        @change=${e => update({ kind: e.currentTarget.value })}>
        <option value="">Все события</option>
        ${KINDS.map(([id, title]) => html`<option value=${id}>${title}</option>`)}
      </select></label>
      <label class="chk"><input type="checkbox" .checked=${filters.confirmed}
        @change=${e => update({ confirmed: e.currentTarget.checked })}> С подтверждённым проживанием</label>
      ${allowed?.guest_details ? html`
        ${allowed.vip_codes.length ? html`<fieldset class="ge-vip"><legend>VIP-код</legend>
          ${allowed.vip_codes.map(code => html`<label class="chk"><input type="checkbox" .checked=${filters.vip.includes(code.id)}
            @change=${e => update({ vip: e.currentTarget.checked
              ? [...filters.vip, code.id] : filters.vip.filter(id => id !== code.id) })}> ${code.code}</label>`)}
        </fieldset>` : nothing}
        <label class="chk"><input type="checkbox" .checked=${filters.special}
          @change=${e => update({ special: e.currentTarget.checked })}> Особый гость</label>` : nothing}
      ${count ? html`<button type="button" class="btn btn-sm btn-ghost ge-reset"
        @click=${() => { reset(); moveFocus(); }}>Сбросить</button>` : nothing}
    </div>
  </details>`;
}

function eventCard(event, today, details, openCard) {
  return html`<article class="ge-event" data-ge-event=${event.id}>
    <h4 data-ge-kind=${event.kind}>${event.title}</h4>
    ${event.people.map(person => {
      const text = person.status === 'staying' && event.date !== today
        ? (event.date > today ? 'Будет проживать' : 'Проживал(а)')
        : (STAY_STATUS[person.status] || STAY_STATUS.unavailable);
      const status = person.unit && person.status !== 'unavailable' ? text + ' · ' + person.unit : text;
      return html`<div class="ge-person">
        <button type="button" class="btn btn-ghost ge-person-name" data-ge-guest=${person.guest_id}
          aria-haspopup="dialog" @click=${() => openCard(event, person, false)}>${person.name}</button>
        ${details && (person.vip_code || person.special) ? html`<div class="ge-person-meta">
          ${person.vip_code ? html`<span class="badge muted">VIP ${person.vip_code}</span>` : nothing}
          ${person.special ? html`<span class="badge warn">Особый гость</span>` : nothing}
        </div>` : nothing}
        <div class="ge-status" data-ge-status=${person.status} ?data-confirmed=${CONFIRMED.has(person.status)}>${status}</div>
        ${can('stays.view') && person.reservation_id ? html`<button type="button" class="btn btn-sm btn-ghost ge-booking"
          data-ge-booking=${person.guest_id} aria-haspopup="dialog" aria-label=${'Открыть бронь гостя ' + person.name}
          @click=${() => openCard(event, person, true)}>Открыть бронь</button>` : nothing}
      </div>`;
    })}
  </article>`;
}

function loadGuestEvents() {
  const host = $('#view-guestevents');
  const auth = authContextSnapshot();
  const fresh = loadGenerationFor(host);
  const current = () => fresh() && state.view === 'guestevents' && authContextIsCurrent(auth);
  if (!(can('stays.guests') || (can('stays.mine') && state.user?.employee_id != null))) {
    render(denied(), mount(host));
    return;
  }

  let today = todayISO();
  let selected = today;
  let filters = emptyFilters();
  let payload = null;
  let fault = '';
  let pending = false;
  let controller = null;
  let cardRequest = 0;
  let followToday = true;
  const month = () => firstOfMonth(selected);
  const dayButton = () => $(`[data-ge-date="${selected}"]`, host);
  const filterButton = () => $('.ge-filters summary', host);

  async function refresh() {
    if (!current()) return;
    controller?.abort();
    const request = new AbortController();
    controller = request;
    pending = true;
    fault = '';
    draw();
    const params = new URLSearchParams();
    if (!followToday) params.set('month', month());
    if (filters.kind) params.set('kind', filters.kind);
    if (filters.confirmed) params.set('confirmed_only', 'true');
    filters.vip.forEach(id => params.append('vip_code_ids', id));
    if (filters.special) params.set('special', 'true');
    try {
      const data = await api(`/api/stays/guest-events?${params}`, { silent: true, signal: request.signal });
      if (request !== controller || !current()) return;
      if (!isDate(data?.today) || !isDate(data?.month) || !Array.isArray(data?.events)
          || !Array.isArray(data?.filters?.vip_codes)) throw new Error('Некорректный ответ');
      const focusDay = document.activeElement === dayButton();
      today = data.today;
      if (followToday) selected = today;
      followToday = false;
      payload = data;
      if (!data.filters.guest_details) filters = { ...filters, vip: [], special: false };
      pending = false;
      draw();
      if (focusDay) dayButton()?.focus({ preventScroll: true });
    } catch (error) {
      if (request !== controller || !current()) return;
      fault = error.status === 403 ? 'denied' : 'error';
      pending = false;
      const focusRetry = document.activeElement?.hasAttribute('data-ge-retry') && host.contains(document.activeElement);
      draw();
      if (focusRetry) $('[data-ge-retry]', host)?.focus();
    }
  }

  function pick(day, focus = false) {
    const previousMonth = month();
    selected = day;
    if (month() !== previousMonth || followToday) {
      followToday = false;
      refresh();
    } else draw();
    if (focus) dayButton()?.focus({ preventScroll: true });
  }

  function showToday() {
    selected = today;
    followToday = true;
    refresh();
  }

  function keydown(event) {
    const origin = event.target.closest('[data-ge-date]')?.dataset.geDate;
    if (!origin || event.altKey || event.ctrlKey || event.metaKey) return;
    const offset = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7,
      Home: -weekday(origin), End: 6 - weekday(origin) }[event.key];
    if (offset !== undefined) {
      event.preventDefault();
      pick(stepDay(origin, offset), true);
    } else if (event.key === 'PageUp' || event.key === 'PageDown') {
      event.preventDefault();
      pick(stepMonth(firstOfMonth(origin), event.key === 'PageUp' ? -1 : 1), true);
    }
  }

  function openCard(event, person, booking) {
    const request = ++cardRequest;
    const key = booking ? 'data-ge-booking' : 'data-ge-guest';
    const trigger = () => $(`[data-ge-event="${CSS.escape(event.id)}"] [${key}="${person.guest_id}"]`, host);
    const returnFocusTo = () => current() ? trigger() || dayButton() : null;
    const isCurrent = () => current() && request === cardRequest && selected === event.date;
    const canOpen = () => trigger()?.closest('[inert]') === null;
    if (!canOpen()) return;
    const options = { returnFocusTo, silent: true };
    const opening = booking
      ? openReservationCard(person.reservation_id, refresh, { ...options, isCurrent: () => isCurrent() && canOpen() })
      : openGuestCard(person.guest_id, refresh, { ...options, isCurrent, canOpen });
    opening.catch(() => {
      if (isCurrent() && canOpen()) toast(booking ? 'Не удалось открыть бронь.' : 'Не удалось открыть карточку гостя.', 'err');
    });
  }

  function draw() {
    if (fault === 'denied') {
      render(html`<div class="page-head"><h2>${TITLE}</h2></div>${denied()}`, mount(host));
      return;
    }
    const eventsByDate = new Map();
    if (payload && !pending && !fault && payload.month === month()) {
      for (const event of payload.events) {
        if (!eventsByDate.has(event.date)) eventsByDate.set(event.date, []);
        eventsByDate.get(event.date).push(event);
      }
    }
    const available = payload?.filters;
    const daily = eventsByDate.get(selected) || [];
    const display = dateValue(selected);
    const monthDate = dateValue(month());
    const title = `${cap(monthLabel.format(monthDate))} ${monthDate.getUTCFullYear()}`;
    const update = patch => { filters = { ...filters, ...patch }; refresh(); };
    const closeFilter = () => { $('.ge-filters', host).open = false; filterButton()?.focus(); };
    const retry = event => { refresh(); dayButton()?.focus({ preventScroll: true }); event.preventDefault(); };
    const agendaBody = pending ? dataState('loading', 'Загружаем события…')
      : fault ? dataState('error', 'События не загрузились. Проверьте связь и повторите.',
        html`<button class="btn btn-sm" type="button" data-ge-retry @click=${retry}>Повторить</button>`)
      : daily.length ? daily.map(event => eventCard(event, today, available?.guest_details, openCard))
      : dataState('empty', 'На эту дату событий нет');
    render(html`<div class="ge">
      <header class="page-head"><h2>${TITLE}</h2></header>
      <div class="ge-toolbar">
        ${periodNav('ge-period', title, delta => pick(stepMonth(month(), delta)))}
        <button type="button" class="btn btn-sm" @click=${showToday}>Сегодня</button>
        ${filterPanel(filters, available, update, () => update(emptyFilters()), closeFilter, () => filterButton()?.focus())}
      </div>
      <div class="ge-content"><div class="ge-columns">
        ${calendarGrid(month(), selected, today, eventsByDate, pending, pick, keydown)}
        <section class="ge-agenda" aria-label="События дня">
          <header class="ge-agenda-head" aria-live="polite">
            <div>${cap(weekdayLabel.format(display))}</div><h3>${dayLabel.format(display)}</h3>
          </header>
          <div class="ge-agenda-body" aria-busy=${pending}>${agendaBody}</div>
        </section>
      </div></div>
    </div>`, mount(host));
  }

  refresh();
}
