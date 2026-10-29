/* ══════════════════════════════════════════════════════════════════════
   «ШАХМАТКА» — вкладка «Брони»: плоский список бронирований за период
   (спецификация docs/superpowers/specs/2026-10-26-stays-fund-versions-design.md §8).
   Фильтры, сортировка и срез страницы — на сервере (GET /api/stays/bookings); клиент держит
   накопленные страницы («Показать ещё» — +200). Период — общий месяц разделов или свой диапазон
   (не больше 366 дней: поля дат это ограничивают, сообщение сервера 422 показывается тостом).
   Использует хелперы app.js: $ $$ esc api toast can dateRu downloadBlob.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

const STAYS_BOOK_MODES = [['stay', 'проживает в период'], ['check_in', 'заезд в период'],
  ['check_out', 'выезд в период'], ['created', 'создана в период']];
const STAYS_BOOK_STATUSES = [['tentative', 'предварительная'], ['confirmed', 'подтверждена'], ['in_house', 'заселён'],
  ['checked_out', 'выехал'], ['cancelled', 'отменена'], ['no_show', 'не заехал']];
/* колонки: ключ сортировки сервера — заголовок */
const STAYS_BOOK_COLS = [['number', '№ брони'], ['guest', 'Гость'], ['check_in', 'Заезд'], ['check_out', 'Выезд'],
  ['nights', 'Ночей'], ['category', 'Категория'], ['unit', 'Объект'], ['status', 'Статус'], ['created_at', 'Создана']];
const STAYS_BOOK_MAX_DAYS = 366;
const STAYS_BOOK_PAGE = 200;

function staysBookEmpty() {
  return { custom: false, first: '', last: '', mode: 'stay', statuses: [], label_ids: [],
    unassigned: false, with_warnings: false, sort: 'check_in', dir: 'asc' };
}
const staysBook = staysBookEmpty();

/* период запроса: свой диапазон или общий месяц */
function staysBookRange() {
  return staysBook.custom && staysBook.first && staysBook.last
    ? { first: staysBook.first, last: staysBook.last } : staysMonthRange();
}
function staysBookParams() {
  const f = staysState.filters;
  const { first, last } = staysBookRange();
  const p = staysFundParams(new URLSearchParams({ first, last, mode: staysBook.mode,
    sort: staysBook.sort, dir: staysBook.dir }));
  staysBook.statuses.forEach(v => p.append('statuses', v));
  staysBook.label_ids.forEach(v => p.append('label_ids', v));
  if (staysBook.unassigned) p.set('unassigned', '1');
  if (staysBook.with_warnings) p.set('with_warnings', '1');
  if (f.escorted) p.set('escorted', '1');
  if (f.vip) p.set('vip', '1');
  if (f.q.trim()) p.set('q', f.q.trim());
  return p;
}

function staysBookToolbar(fund) {
  const b = staysBook;
  const { first, last } = staysBookRange();
  const pick = (key, title, items, chosen) => {
    const picked = items.filter(([v]) => chosen.includes(v)).map(([, t]) => t);
    return `<details class="sf-dd" data-bk-dd="${key}"${staysFilterOpen.has('bk-' + key) ? ' open' : ''}>
      <summary>${esc(title)}: <b>${esc(picked.length ? picked.join(', ') : 'все')}</b></summary>
      <div class="sf-list">${items.map(([v, t]) => `<label class="chk">
        <input type="checkbox" data-bk-${key}="${esc(String(v))}"${chosen.includes(v) ? ' checked' : ''}> ${esc(t)}</label>`).join('')
        || '<span class="muted">нет</span>'}</div></details>`;
  };
  return `<div class="sb-toolbar">
    <select id="bk-period" title="Период списка"><option value="month"${b.custom ? '' : ' selected'}>Месяц разделов</option>
      <option value="custom"${b.custom ? ' selected' : ''}>Свой период</option></select>
    ${b.custom
    ? `<input type="date" id="bk-first" value="${esc(first)}" max="${esc(last)}" title="Начало периода">
      <input type="date" id="bk-last" value="${esc(last)}" min="${esc(first)}" max="${esc(staysAddDays(first, STAYS_BOOK_MAX_DAYS - 1))}"
        title="Конец периода (не позже ${STAYS_BOOK_MAX_DAYS} дней от начала)">
      <span class="muted">не больше ${STAYS_BOOK_MAX_DAYS} дней</span>`
    : staysMonthNav()}
    <select id="bk-mode" title="Какие брони попадают в период">${STAYS_BOOK_MODES.map(([v, t]) =>
    `<option value="${v}"${v === b.mode ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select>
    ${pick('status', 'Статусы', STAYS_BOOK_STATUSES, b.statuses)}
    ${pick('label', 'Метки', (fund.labels || []).map(l => [l.id, l.title]), b.label_ids)}
    <label class="chk"><input type="checkbox" id="bk-unassigned"${b.unassigned ? ' checked' : ''}> без объекта</label>
    <label class="chk"><input type="checkbox" id="bk-warn"${b.with_warnings ? ' checked' : ''}> с предупреждениями</label>
    ${can('stays.export') ? '<button class="btn btn-sm btn-ghost" id="bk-xlsx" title="Выгрузить список по текущим фильтрам">Выгрузить</button>' : ''}
  </div>
  <div data-sf-slot></div>`;
}

function staysBookRowHtml(r) {
  const lb = r.label ? `<span class="sb-star" style="color:${esc(staysColor(r.label.color))}" title="${esc(r.label.title)}">●</span> ` : '';
  return `<tr class="bk-row" data-bk-row="${r.id}" tabindex="0">
    <td>${lb}${esc(r.number || '#' + r.id)}</td>
    <td>${r.level !== 'regular' ? `<span class="sb-star">${esc(STAYS_LEVEL_MARK[r.level] || '')}</span>` : ''}${esc(r.main_guest)}</td>
    <td>${esc(dateRu(r.check_in))}${r.early ? ' <span class="muted" title="Ранний заезд">РЗ</span>' : ''}</td>
    <td>${esc(dateRu(r.check_out))}${r.late ? ' <span class="muted" title="Поздний выезд">ПВ</span>' : ''}</td>
    <td>${r.nights}</td><td>${esc(r.category)}${r.upgrade ? ` <span class="badge muted" title="${esc(r.upgrade)}">${esc(r.upgrade)}</span>` : ''}</td><td>${esc(r.unit || '—')}</td>
    <td>${esc(r.status_title)}</td><td>${esc(r.created_at.slice(0, 16).replace('T', ' '))}</td></tr>`;
}

function staysBookTableHtml(rows, total) {
  const arrow = key => (staysBook.sort === key ? (staysBook.dir === 'asc' ? ' ↑' : ' ↓') : '');
  return `<div class="muted" id="bk-total">Найдено броней: ${total}${rows.length < total ? ` · показано ${rows.length}` : ''}</div>
    <div class="sb-scroll"><table class="bk-table"><thead><tr>${STAYS_BOOK_COLS.map(([k, t]) =>
    `<th data-bk-sort="${k}" title="Сортировать" style="cursor:pointer">${esc(t)}${arrow(k)}</th>`).join('')}</tr></thead>
    <tbody>${rows.map(staysBookRowHtml).join('') || `<tr><td colspan="${STAYS_BOOK_COLS.length}" class="empty">Броней по фильтру нет</td></tr>`}</tbody></table></div>
    ${rows.length < total ? `<button class="btn" id="bk-more">Показать ещё ${Math.min(STAYS_BOOK_PAGE, total - rows.length)}</button>` : ''}`;
}

async function renderBookings(body) {
  const fund = await staysFund();
  const fresh = loadGenerationFor(body);
  const b = staysBook;
  let rows = [];
  let total = 0;
  let error = '';
  const page = async offset => {
    const p = staysBookParams();
    p.set('offset', offset);
    p.set('limit', STAYS_BOOK_PAGE);
    return api('/api/stays/bookings?' + p, { silent: true });
  };
  try {
    ({ rows, total } = await page(0));
  } catch (e) {
    error = e.message;
    toast(error, 'warn');
  }
  if (!fresh()) return;
  body.innerHTML = `${staysBookToolbar(fund)}<div id="bk-result"></div>`;
  const rerender = () => renderBookings(body);
  staysPanelInto(body, fund, rerender, { people: true });
  const result = $('#bk-result', body);
  const paint = () => {
    result.innerHTML = error ? `<div class="panel"><p class="muted">${esc(error)}</p></div>` : staysBookTableHtml(rows, total);
    const more = $('#bk-more', result);
    if (more) more.onclick = async () => {
      more.disabled = true;
      try {
        const next = await page(rows.length);
        if (!fresh()) return;
        rows = rows.concat(next.rows);
        total = next.total;
      } catch (e) { toast(e.message, 'warn'); }
      paint();
    };
  };
  paint();
  /* сортировка: клик — по возрастанию, повторный — направление */
  result.onclick = e => {
    const th = e.target.closest('[data-bk-sort]');
    if (th) {
      const key = th.dataset.bkSort;
      if (b.sort === key) b.dir = b.dir === 'asc' ? 'desc' : 'asc'; else { b.sort = key; b.dir = 'asc'; }
      rerender();
      return;
    }
    const tr = e.target.closest('[data-bk-row]');
    if (tr) openReservationCard(Number(tr.dataset.bkRow), rerender).catch(err => toast(err.message, 'warn'));
  };
  result.onkeydown = e => {
    const tr = e.target.closest?.('[data-bk-row]');
    if (tr && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); tr.click(); }
  };

  if (!b.custom) staysBindMonthNav(body, rerender);
  $('#bk-period', body).onchange = e => {
    b.custom = e.target.value === 'custom';
    if (b.custom && !(b.first && b.last)) ({ first: b.first, last: b.last } = staysMonthRange());
    rerender();
  };
  const first = $('#bk-first', body);
  if (first) {
    first.onchange = () => {
      if (!first.value) return;
      b.first = first.value;
      const cap = staysAddDays(b.first, STAYS_BOOK_MAX_DAYS - 1);
      if (b.last < b.first) b.last = b.first;
      if (b.last > cap) b.last = cap;
      rerender();
    };
    const last = $('#bk-last', body);
    last.onchange = () => {
      if (!last.value) return;
      b.last = last.value;
      if (b.last < b.first) { toast('Конец периода раньше начала', 'warn'); b.last = b.first; }
      rerender();
    };
  }
  $('#bk-mode', body).onchange = e => { b.mode = e.target.value; rerender(); };
  [['status', 'statuses', String], ['label', 'label_ids', Number]].forEach(([key, field, cast]) => {
    $$(`[data-bk-${key}]`, body).forEach(cb => {
      cb.onchange = () => {
        b[field] = $$(`[data-bk-${key}]`, body).filter(x => x.checked).map(x => cast(x.getAttribute(`data-bk-${key}`)));
        rerender();
      };
    });
  });
  $$('[data-bk-dd]', body).forEach(d => {
    d.addEventListener('toggle', () => {
      if (d.open) staysFilterOpen.add('bk-' + d.dataset.bkDd); else staysFilterOpen.delete('bk-' + d.dataset.bkDd);
    });
  });
  $('#bk-unassigned', body).onchange = e => { b.unassigned = e.target.checked; rerender(); };
  $('#bk-warn', body).onchange = e => { b.with_warnings = e.target.checked; rerender(); };
  const xlsx = $('#bk-xlsx', body);
  if (xlsx) xlsx.onclick = () => {
    const { first: f0, last: l0 } = staysBookRange();
    downloadBlob('/api/stays/bookings/export?' + staysBookParams(), `bookings_${f0}_${l0}.xlsx`)
      .catch(err => toast(err.message, 'warn'));
  };
}
