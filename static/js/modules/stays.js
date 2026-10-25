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

const STAYS_TABS = [['units', 'Объекты'], ['butlers', 'Батлеры'], ['day', 'Табло дня'], ['occupancy', 'Загрузка']];
const STAYS_LEVEL_MARK = { vip: '★VIP ', vvip: '★VVIP ' };
const staysState = {
  tab: 'units', first: null, days: 14, fund: null,
  filters: { kind: '', building: '', category_id: '', escorted: false, vip: false, q: '' },
};

/* PoC §5.1: ordinal как в Python date.toordinal() — клиент и сервер считают позиции одинаково */
function staysOrdinal(y, m, d) { return Math.round(Date.UTC(y, m - 1, d) / 86400000) + 719163; }
function staysPos(iso, half) { const [y, m, d] = iso.split('-').map(Number); return staysOrdinal(y, m, d) * 2 + half; }
function staysAddDays(iso, n) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}
function staysToday() { return new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10); }
async function staysFund(force = false) {
  if (!staysState.fund || force) staysState.fund = await api('/api/stays/fund', { silent: true });
  return staysState.fund;
}

async function loadStays() {
  const host = $('#view-stays');
  if (!staysState.first) staysState.first = staysToday();
  host.innerHTML = `
    <div class="page-head"><div><h2>Шахматка</h2><div class="sub">Кто где живёт и кто из батлеров ведёт гостей</div></div></div>
    <div class="layer-tabs">${STAYS_TABS.filter(([id]) => id !== 'butlers' || can('stays.view')).map(([id, t]) =>
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
    occupancy: renderOccupancyGrid }[tab] || renderUnitsBoard;
}

async function loadMyStays() {
  await renderMine();
}

/* ─────────────── Шахматка объектов ─────────────── */
function staysToolbar(fund) {
  const f = staysState.filters;
  const buildings = [...new Set(fund.units.map(u => u.building).filter(Boolean))].sort();
  const opt = (v, t, cur) => `<option value="${esc(String(v))}"${String(v) === String(cur) ? ' selected' : ''}>${esc(t)}</option>`;
  return `<div class="sb-toolbar">
    <input type="date" id="sb-first" value="${esc(staysState.first)}">
    <select id="sb-days">${[7, 14, 31].map(n => opt(n, `${n} дн.`, staysState.days)).join('')}</select>
    <select id="sb-kind">${opt('', 'Все виды', f.kind)}${fund.kinds.map(k => opt(k.code, k.title, f.kind)).join('')}</select>
    <select id="sb-building">${opt('', 'Все корпуса', f.building)}${buildings.map(b => opt(b, `Корпус ${b}`, f.building)).join('')}</select>
    <select id="sb-cat">${opt('', 'Все категории', f.category_id)}${fund.categories.map(c => opt(c.id, c.code, f.category_id)).join('')}</select>
    <label class="chk"><input type="checkbox" id="sb-esc"${f.escorted ? ' checked' : ''}> с сопровождением</label>
    <label class="chk"><input type="checkbox" id="sb-vip"${f.vip ? ' checked' : ''}> VIP/VVIP</label>
    <input type="search" id="sb-q" placeholder="фамилия, № брони, объект, телефон" value="${esc(f.q)}">
    <button class="btn btn-sm btn-ghost" id="sb-xlsx-anon" title="Объекты, даты, статусы, число гостей — без данных гостей">Выгрузить (без гостей)</button>
    ${can('stays.export') && can('stays.guests') ? '<button class="btn btn-sm btn-ghost" id="sb-xlsx-full">Выгрузить полностью</button>' : ''}
    ${can('stays.edit') ? '<button class="btn btn-sm btn-primary" id="sb-new">+ Бронь</button>' : ''}
  </div>`;
}

function staysBoardParams() {
  const f = staysState.filters;
  const p = new URLSearchParams({ first: staysState.first, last: staysAddDays(staysState.first, staysState.days - 1) });
  if (f.kind) p.set('kind', f.kind);
  if (f.building) p.set('building', f.building);
  if (f.category_id) p.set('category_id', f.category_id);
  if (f.escorted) p.set('escorted', '1');
  if (f.vip) p.set('vip', '1');
  if (f.q.trim()) p.set('q', f.q.trim());
  return p;
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
  /* фильтры меняются подряд (дата → категория): запоздавший ответ перерисовал бы экран
     без фильтра (как Табель, PR #95) — поколение у контейнера вкладки (core.js) */
  const fresh = loadGenerationFor(body);
  const data = await api('/api/stays/board/units?' + staysBoardParams(), { silent: true });
  if (!fresh()) return;
  const names = data.visibility !== 'occupancy';
  const base = staysPos(data.days[0], 0);
  const span = data.days.length * 2;
  const byUnit = {};
  data.bars.forEach(b => { (byUnit[b.unit_id ?? 'none'] ||= []).push(b); });
  const holdsBy = {};
  data.holds.forEach(h => { (holdsBy[h.unit_id] ||= []).push(h); });
  const today = staysToday();
  body.innerHTML = `
    ${staysToolbar(fund)}
    ${data.warnings.length ? `<div class="dict-banner gold"><span>⚠</span><span>${data.warnings.map(w => esc(w.text)).join('<br>')}</span></div>` : ''}
    <div class="sb-grid">
      <div class="sb-row sb-head"><div class="sb-unit">Объект</div><div class="sb-track sb-days">${data.days.map(d =>
        `<div class="${d === today ? 'today' : ''}">${esc(d.slice(8))}.${esc(d.slice(5, 7))}</div>`).join('')}</div></div>
      ${data.units.map(u => `<div class="sb-row" data-unit-row="${u.id}">
        <div class="sb-unit"><b>${esc(u.label)}</b><small>${esc(u.category)}${u.building ? ' · к.' + esc(u.building) : ''}</small></div>
        <div class="sb-track" style="--days:${data.days.length}">
          ${(holdsBy[u.id] || []).map(h => {
            const l = Math.max(0, (h.start_pos - base) / span * 100), r = Math.min(100, (h.end_pos - base + 1) / span * 100);
            return `<div class="sb-hold ${h.kind}" data-hold="${h.id}" style="left:${l}%;width:${r - l}%">${esc(h.kind === 'ooo' ? 'OOO' : (h.title || 'Блок'))}</div>`;
          }).join('')}
          ${(byUnit[u.id] || []).map(b => staysBarHtml(b, base, span, names)).join('')}
        </div></div>`).join('') || '<div class="empty">Объектов по фильтру нет</div>'}
    </div>
    ${(byUnit.none || []).length ? `<div class="panel"><h3 class="panel-title">Без объекта</h3>${byUnit.none.map(b =>
      `<div class="sb-unassigned" data-bar="${b.reservation_id}">${esc(names ? (b.number + ' · ' + (b.main_guest || '')) : 'бронь')} · ${esc(dateRu(b.start))}–${esc(dateRu(b.end))}</div>`).join('')}</div>` : ''}`;

  const f = staysState.filters;
  const rerender = () => renderUnitsBoard(body);
  $('#sb-first', body).onchange = e => { staysState.first = e.target.value || staysToday(); rerender(); };
  $('#sb-days', body).onchange = e => { staysState.days = Number(e.target.value); rerender(); };
  [['#sb-kind', 'kind'], ['#sb-building', 'building'], ['#sb-cat', 'category_id']].forEach(([sel, key]) => {
    $(sel, body).onchange = e => { f[key] = e.target.value; rerender(); };
  });
  $('#sb-esc', body).onchange = e => { f.escorted = e.target.checked; rerender(); };
  $('#sb-vip', body).onchange = e => { f.vip = e.target.checked; rerender(); };
  let timer = null;
  $('#sb-q', body).oninput = e => { clearTimeout(timer); timer = setTimeout(() => { f.q = e.target.value; rerender(); }, 350); };
  const xlsx = kind => () => {
    const p = new URLSearchParams({ first: staysState.first, last: staysAddDays(staysState.first, staysState.days - 1), kind });
    downloadBlob('/api/stays/export?' + p, `shakhmatka_${kind}_${staysState.first}.xlsx`);
  };
  $('#sb-xlsx-anon', body).onclick = xlsx('anon');
  const full = $('#sb-xlsx-full', body);
  if (full) full.onclick = xlsx('full');
  const add = $('#sb-new', body);
  if (add) add.onclick = () => openReservationForm(null, { onSaved: rerender });
  if (names) $$('[data-bar]', body).forEach(el => { el.onclick = () => openReservationCard(Number(el.dataset.bar), rerender); });
  if (can('stays.edit')) {
    /* блок / OOO: клик по объекту — новый, по полосе блока — правка или удаление */
    $$('[data-unit-row] .sb-unit', body).forEach(el => {
      el.style.cursor = 'pointer';
      el.title = 'Поставить блок или OOO';
      el.onclick = () => openHoldForm({ unit_id: Number(el.closest('[data-unit-row]').dataset.unitRow) }, rerender);
    });
    $$('[data-hold]', body).forEach(el => {
      el.onclick = () => openHoldForm(data.holds.find(h => h.id === Number(el.dataset.hold)), rerender);
    });
  }
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
