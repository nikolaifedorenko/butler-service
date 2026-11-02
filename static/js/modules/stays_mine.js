/* ══════════════════════════════════════════════════════════════════════
   «МОИ ГОСТИ» (часть 4 §5): экран батлера с телефона, три вкладки —
   «Сегодня» (карточки броней этой ночи), «Мой месяц» (мини-шахматка с полосой нагрузки,
   месяц общий с Табелем: state.year/state.month) и «Все мои гости» (поиск по фамилии, карточка
   с историей: кто вёл). Данные — GET /api/stays/mine/{today,month,guests}. Кнопки «Изменить» — по
   правам stays.mine_res_edit / stays.mine_guest_edit (или stays.edit); открывают общие формы.
   Использует хелперы app.js: $ $$ esc api openModal closeModal toast can dateRu loadGenerationFor.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

const MINE_TABS = [['today', 'Сегодня'], ['month', 'Мой месяц'], ['guests', 'Все мои гости']];
const MINE_LEVEL = { one: 'один гость', many: 'несколько гостей', over: 'выше лимита' };
const MINE_PAGE = 50;
const mineState = { tab: 'today', q: '' };

const mineDdmm = iso => dateRu(iso).slice(0, 5);
const mineCanResEdit = () => can('stays.edit') || can('stays.mine_res_edit');
const mineCanGuestEdit = () => can('stays.edit') || can('stays.mine_guest_edit');

async function renderMine() {
  const host = $('#view-mystays');
  host.innerHTML = `<div class="page-head"><div><h2>Мои гости</h2></div></div>
    <div class="layer-tabs mine-tabs">${MINE_TABS.map(([id, title]) =>
      `<button class="btn btn-sm${mineState.tab === id ? ' btn-primary' : ''}" data-mtab="${id}">${esc(title)}</button>`).join('')}</div>
    <div id="mine-body" class="empty">Загрузка…</div>`;
  $$('[data-mtab]', host).forEach(b => { b.onclick = () => { mineState.tab = b.dataset.mtab; renderMine(); }; });
  const body = $('#mine-body', host);
  const fresh = loadGenerationFor(body);
  const draw = { today: renderMineToday, month: renderMineMonth, guests: renderMineGuests }[mineState.tab];
  try {
    await draw(body, fresh);
  } catch (e) {
    if (fresh()) { body.className = ''; body.innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
  }
}

/* ─────────────── «Сегодня» ─────────────── */
function mineLogisticsDay(date, today) {
  if (!date) return 'без даты';
  if (date === today) return 'сегодня';
  return date === staysAddDays(today, 1) ? 'завтра' : mineDdmm(date);
}

function mineTodayCardHtml(r, today) {
  const guests = r.guests.map(g => `<div class="mine-guest" data-mine-guest-row="${g.guest_id}">
      <b>${staysGuestMark(g.special)}${esc(g.name)}</b>${staysCodeTag(g.vip_code)}
      <span class="muted">${esc(STAYS_ROLE[g.role] || g.role)}${g.phone ? ' · ' + esc(g.phone) : ''}</span>
      ${g.departing && !r.departing ? ' <span class="badge warn">выезд сегодня</span>' : ''}
      ${Object.entries(g.preferences).filter(([, v]) => v).map(([k, v]) => `<div class="muted">${esc(k)}: ${esc(v)}</div>`).join('')}
      ${g.special_dates_soon.map(s => `<div class="muted" data-mine-soon>🎉 ${esc(dateRu(s.date))} — ${esc(s.what)}</div>`).join('')}
      <button class="btn btn-sm btn-ghost" data-mine-guest="${g.guest_id}">Карточка гостя</button></div>`).join('');
  return `<div class="panel mine-card" data-mine-card="${r.reservation_id}">
    <h3 class="panel-title">${esc(r.unit || 'без объекта')}${r.departing ? ' <span class="badge warn">выезд сегодня</span>' : ''}${r.status === 'tentative' ? ' <span class="badge muted">предварительная</span>' : ''}</h3>
    <div class="muted">${esc(r.number || '')} · заезд ${esc(dateRu(r.check_in))} — выезд ${esc(dateRu(r.check_out))}</div>
    ${guests}
    ${r.logistics.map(l => `<div data-mine-logistics>🚗 <b>${esc(mineLogisticsDay(l.date, today))}</b> ${esc(l.time)} ${esc(l.description)}</div>`).join('')}
    <div class="sb-line"><button class="btn btn-sm btn-ghost" data-mine-open="${r.reservation_id}">Бронь…</button>
      ${mineCanResEdit() ? `<button class="btn btn-sm" data-mine-res="${r.reservation_id}">Изменить</button>` : ''}</div>
  </div>`;
}

async function renderMineToday(body, fresh) {
  const data = await api('/api/stays/mine/today', { silent: true });
  if (!fresh()) return;
  body.className = '';
  body.innerHTML = `<div class="muted mine-date">Сегодня, ${esc(dateRu(data.date))}</div>
    ${data.reservations.map(r => mineTodayCardHtml(r, data.date)).join('') || '<div class="empty">Сегодня гостей, которых вы ведёте, нет</div>'}`;
  mineBindActions(body);
}

/* кнопки карточек: «Бронь…», «Изменить», «Карточка гостя» */
function mineBindActions(body) {
  $$('[data-mine-open]', body).forEach(b => {
    b.onclick = () => openReservationCard(Number(b.dataset.mineOpen), renderMine).catch(e => toast(e.message, 'err'));
  });
  $$('[data-mine-res]', body).forEach(b => {
    b.onclick = () => openReservationForm(Number(b.dataset.mineRes), { mine: !can('stays.edit'), onSaved: renderMine });
  });
  $$('[data-mine-guest]', body).forEach(b => {
    b.onclick = () => openMineGuest(Number(b.dataset.mineGuest), renderMine).catch(e => toast(e.message, 'err'));
  });
}

/* ─────────────── «Мой месяц» ─────────────── */
function mineBarHtml(b, base, span, none) {
  const left = Math.max(0, (b.start_pos - base) / span * 100);
  const right = Math.min(100, (b.end_pos - base + 1) / span * 100);
  if (right <= 0 || left >= 100) return '';
  const tentative = b.status === 'tentative';
  const text = `${staysGuestMark(b.special)}${esc(b.main_guest || 'бронь')}${tentative ? ' · предв.' : ''}`;
  return `<div class="sb-bar mm-bar${tentative ? ' tentative' : ''}${none ? ' mm-none' : ''}" data-bar="${b.reservation_id}"
    style="left:${left}%;width:${right - left}%" title="${esc((tentative ? 'Предварительная · ' : '') + (b.main_guest || 'бронь'))}">${text}</div>`;
}

/* полоса нагрузки: число гостей в день, цвет — один / несколько / выше лимита; «О» — отсутствие по Графику
   (день может быть и с нагрузкой, и с «О» — рисуются обе отметки) */
function mineLoadCellHtml(day, load, absent, limit) {
  const l = load[day];
  const tip = [l ? `${MINE_LEVEL[l.level]}: ${l.guests} гост., нагрузка ${staysWeight(l.value)} из ${staysWeight(limit)}` : '', absent.has(day) ? 'отсутствие по Графику' : ''].filter(Boolean).join(' · ');
  return `<div class="mm-lc${l ? ' lv-' + l.level : ''}" data-day="${esc(day)}"${l ? ` data-load-level="${l.level}"` : ''}${absent.has(day) ? ' data-absent="1"' : ''}${tip ? ` title="${esc(tip)}"` : ''}>${l ? l.guests : ''}${absent.has(day) ? '<b class="mm-abs">О</b>' : ''}</div>`;
}

function mineMonthGridHtml(data) {
  const today = staysToday();
  const base = staysPos(data.days[0], 0);
  const span = data.days.length * 2;
  const load = Object.fromEntries(data.load.map(x => [x.day, x]));
  const absent = new Set(data.absences);
  return `<div class="sb-row sb-head"><div class="sb-unit">Объект</div><div class="sb-track sb-days">${data.days.map(d => staysDayHead(d, today)).join('')}</div></div>
    <div class="sb-row mm-load" data-mine-load><div class="sb-unit"><b>Нагрузка</b><small>лимит ${staysWeight(data.limit)}</small></div>
      <div class="sb-track sb-days">${data.days.map(d => mineLoadCellHtml(d, load, absent, data.limit)).join('')}</div></div>
    ${data.rows.map(row => `<div class="sb-row${row.unit_id == null ? ' mm-none-row' : ''}" data-mine-row="${row.unit_id ?? 'none'}">
      <div class="sb-unit"><b>${esc(row.label)}</b></div>
      <div class="sb-track">${row.bars.map(b => mineBarHtml(b, base, span, row.unit_id == null)).join('')}</div></div>`).join('')
      || '<div class="empty">В этом месяце своих броней нет</div>'}`;
}

async function renderMineMonth(body, fresh) {
  const { first, last } = staysMonthRange();
  const data = await api(`/api/stays/mine/month?first=${first}&last=${last}`, { silent: true });
  if (!fresh()) return;
  body.className = '';
  body.innerHTML = `<div class="sb-toolbar">${staysMonthNav()}</div>
    <div class="muted mm-legend"><span class="mm-key lv-one"></span> один гость <span class="mm-key lv-many"></span> несколько
      <span class="mm-key lv-over"></span> выше лимита · <b class="mm-abs">О</b> — отсутствие</div>
    <div class="sb-grid mm-grid" style="--days:${data.days.length}">${mineMonthGridHtml(data)}</div>`;
  staysBindMonthNav(body, renderMine);
  $$('[data-bar]', body).forEach(el => {
    el.onclick = () => openReservationCard(Number(el.dataset.bar), renderMine).catch(e => toast(e.message, 'err'));
  });
  staysFocusDay(body);
}

/* ─────────────── «Все мои гости» ─────────────── */
function mineGuestRowHtml(g) {
  return `<div class="mine-grow" data-mine-grow="${g.guest_id}" tabindex="0">
    <b>${staysGuestMark(g.special)}${esc(g.name)}</b>${staysCodeTag(g.vip_code)}
    <span class="muted">${g.last_stay ? 'последний заезд ' + esc(dateRu(g.last_stay)) : 'не жил'} · проживаний ${g.stays}</span></div>`;
}

async function renderMineGuests(body) {
  body.className = '';
  body.innerHTML = `<div class="sb-toolbar"><input type="search" id="mg-q" value="${esc(mineState.q)}" placeholder="Фамилия гостя"></div>
    <div id="mg-result"><div class="empty">Загрузка…</div></div>`;
  const result = $('#mg-result', body);
  let rows = [];
  let total = 0;
  const page = offset => api(`/api/stays/mine/guests?q=${encodeURIComponent(mineState.q.trim())}&offset=${offset}&limit=${MINE_PAGE}`, { silent: true });
  const paint = () => {
    result.innerHTML = `<div class="muted" id="mg-total">Гостей: ${total}</div>
      ${rows.map(mineGuestRowHtml).join('') || '<div class="empty">Своих гостей по запросу нет</div>'}
      ${rows.length < total ? `<button class="btn" id="mg-more">Показать ещё ${Math.min(MINE_PAGE, total - rows.length)}</button>` : ''}`;
    const more = $('#mg-more', result);
    if (more) more.onclick = async () => {
      more.disabled = true;
      const fresh = loadGenerationFor(result);
      try {
        const next = await page(rows.length);
        if (!fresh()) return;
        rows = rows.concat(next.rows); total = next.total;
      } catch (e) { toast(e.message, 'warn'); }
      paint();
    };
  };
  const reload = async () => {
    const fresh = loadGenerationFor(result);
    try {
      ({ rows, total } = await page(0));
    } catch (e) {
      if (fresh()) result.innerHTML = `<p class="muted">${esc(e.message)}</p>`;
      return;
    }
    if (fresh()) paint();
  };
  const open = el => { if (el) openMineGuest(Number(el.dataset.mineGrow), renderMine).catch(e => toast(e.message, 'err')); };
  result.onclick = e => open(e.target.closest('[data-mine-grow]'));
  result.onkeydown = e => {
    const el = e.target.closest?.('[data-mine-grow]');
    if (el && e.target === el && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); open(el); }
  };
  let timer = null;
  $('#mg-q', body).oninput = e => {
    clearTimeout(timer);
    timer = setTimeout(() => { mineState.q = e.target.value; reload(); }, 300);
  };
  await reload();
}

/* «вёл я 03.05–08.05» / «вёл(а) Кузнецова 03.05–08.05»: last с сервера — утро после последней ночи, как есть */
function mineLedHtml(l) {
  return `<div class="muted" data-mine-led${l.me ? ' data-me="1"' : ''}>${l.me ? 'вёл я' : 'вёл(а) ' + esc(l.name)} ${esc(mineDdmm(l.first))}–${esc(mineDdmm(l.last))}</div>`;
}

async function openMineGuest(gid, onChanged) {
  const [g, fund] = await Promise.all([api(`/api/stays/mine/guests/${gid}`), staysFund()]);
  const titles = Object.fromEntries(fund.fields.filter(f => f.target === 'guest').map(f => [f.code, f.title]));
  const prefs = Object.entries(g.preferences).filter(([, v]) => v);
  const canEdit = mineCanGuestEdit();
  openModal({
    title: `${g.special ? STAYS_SPECIAL_MARK : ''}${g.last_name} ${g.first_name} ${g.middle_name}`.trim(), wide: true,
    subtitle: [g.vip_code ? `VIP-код ${g.vip_code.code}` : '', g.phone_display, g.birth_date ? 'др ' + dateRu(g.birth_date) : ''].filter(Boolean).join(' · '),
    body: `<h4>Предпочтения</h4>${prefs.map(([k, v]) => `<div>${esc(k)}: ${esc(v)}</div>`).join('') || '<span class="muted">нет</span>'}
      ${g.special_dates.length ? `<h4>Особые даты</h4>${g.special_dates.map(d => `<div>${esc(dateRu(d.date))} — ${esc(d.what)}</div>`).join('')}` : ''}
      ${Object.keys(g.fields).length ? `<h4>Дополнительно</h4>${Object.entries(g.fields).map(([k, v]) => `<div>${esc(titles[k] || k)}: ${esc(String(v))}</div>`).join('')}` : ''}
      ${g.note ? `<h4>Примечание</h4><p data-mine-note>${esc(g.note)}</p>` : ''}
      ${g.links.length ? `<h4>Связи</h4>${g.links.map(l => `<div>${esc(l.name)} <span class="muted">${esc(l.label)}</span></div>`).join('')}` : ''}
      <h4>История проживаний</h4>
      <div id="mg-history" class="sb-history">${g.history.map(h => `<div data-mine-hist="${h.reservation_id}"><b>${esc(h.number || '#' + h.reservation_id)}</b> · ${esc(h.unit)}
        · ${esc(dateRu(h.check_in))}–${esc(dateRu(h.check_out))} · ${esc(STAYS_STATUS[h.status] || h.status)}
        ${h.led.map(mineLedHtml).join('') || '<div class="muted">батлер не назначался</div>'}</div>`).join('') || '<span class="muted">проживаний нет</span>'}</div>`,
    footer: `<button class="btn btn-ghost" data-close>Закрыть</button>
      <button class="btn" id="mg-family">Семья, связи, пожелания…</button>
      ${canEdit ? '<button class="btn btn-primary" id="mg-edit">Изменить профиль</button>' : ''}`,
    onMount(m) {
      $('[data-close]', m).onclick = closeModal;
      const reopen = () => { openMineGuest(gid, onChanged).catch(e => toast(e.message, 'err')); if (onChanged) onChanged(); };
      $('#mg-family', m).onclick = () => openGuestCard(gid, onChanged).catch(e => toast(e.message, 'err'));
      const edit = $('#mg-edit', m);
      if (edit) edit.onclick = () => openGuestForm(gid, reopen, { mine: !can('stays.edit') }).catch(e => toast(e.message, 'err'));
    },
  });
}
