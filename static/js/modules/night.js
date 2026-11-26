/* ══════════════════════════════════════════════════════════════════════
   РАЗДЕЛ «НОЧНОЙ ОТЧЁТ» — смена 20:00–08:00: зоны обхода → объекты → чек-листы,
   отметки ОК/Не ОК с комментариями и фото, перехваты областей, шаг
   «Проверка электрокаров», закрытие смены, архив и выгрузка DOCX/PDF.
   Справочник обхода (зоны, объекты, чек-листы, службы) — экран Настроек (night_dict.js).
   Модуль на lit-html (ADR-0013, раздел 7): разметка — шаблоны, вставки экранируются сами.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

import { can, poll, registerModule } from '../app.js';
import {
  $, $$, api, authContextIsCurrent, authContextSnapshot, closeModal, confirmDialog, dateRu, downloadBlob,
  hhmm, loading, multipartApi, openModal, state, toast,
} from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { checkField } from '../ui/form.js';
import { settingsOpen } from './settings.js';
import {
  CAR_BADGE, CHARGE_OPTS, bindPhotoPick, ensureCarLocations, locationOptions, photoPick, photoThumb,
} from './cars.js';

/* Навигация обхода (v2): зона → объект → чек-лист.
   zoneId: null — экран зон; 0 — объекты «Без зоны»; иначе id зоны.
   areaId: id объекта, чей чек-лист открыт (null — список объектов). */
export const nightState = { reportId: null, today: null, areas: null,
  zoneId: null, areaId: null, q: '', filter: 'all',
  dictTab: 'zones', dictZone: null, dictArea: null,
  /* экран «Недостатки смены»: выбор позиций и показ отправленных/исправленных */
  defectsSelected: new Set(), defectsShowSent: false };

/* то, что сейчас на экране: отчёт (или его отсутствие с пояснением) либо ошибка загрузки */
const view = { rep: null, note: '', error: '' };
let loadingPage = false;      // первая загрузка раздела
let headActionsOpen = false;
let fetchGeneration = 0;

/* dateRu() из app.js рассчитан на «YYYY-MM-DD»; для datetime берём только дату */
const dRu = iso => (iso ? dateRu(String(iso).slice(0, 10)) : '');

const NIGHT_SECTION_BADGE = { free: 'muted', taken: 'warn', done: 'ok' };
const NIGHT_ANSWER_BADGE = { ok: 'ok', bad: 'danger', '': 'muted' };

/* ─────────────────────────── раздел ─────────────────────────── */
registerModule({ views: { night: loadNight } });

async function loadNight() {
  Object.assign(view, { rep: null, note: '', error: '' });
  loadingPage = true;
  headActionsOpen = false;
  paintNight();
  await fetchNight();
  if (state.view === 'night' && state.user) poll('night', () => fetchNight(true));
}

const paintNight = () => render(nightPage(), mount($('#view-night')));

async function fetchNight(silent) {
  const generation = ++fetchGeneration;
  const reportId = nightState.reportId;
  const auth = authContextSnapshot();
  let today, report = null, note = '', error = '';
  try {
    if (reportId) {
      report = (await api(`/api/night/reports/${reportId}`, { silent: !!silent })).report;
    } else {
      today = await api('/api/night/today', { silent: !!silent });
      if (today.available) report = today.report;
      else note = today.note || 'Ночная смена ещё не началась';
    }
  } catch (e) {
    error = e.message;
  }
  if (generation !== fetchGeneration || reportId !== nightState.reportId ||
      state.view !== 'night' || !authContextIsCurrent(auth)) return null;
  if (today) nightState.today = today;
  Object.assign(view, { rep: report, note, error });
  loadingPage = false;
  paintNight();
  return report;
}

function showNightReport(id) {
  Object.assign(nightState, { reportId: id, zoneId: null, areaId: null, q: '', filter: 'all' });
  if (headActionsOpen) $('.night-head-toggle')?.focus({ preventScroll: true });
  headActionsOpen = false;
  Object.assign(view, { rep: null, note: '', error: '' });
  loadingPage = true;
  paintNight();
  return fetchNight();
}

/* ─────────────── три уровня обхода: зоны → объекты → чек-лист объекта ─────────────── */
const nightCrumb = parts => html`<div class="crumb">${parts.map((x, i) => html`${i ? html`<span class="sep">/</span>` : nothing}${i === parts.length - 1
  ? html`<b>${x.t}</b>` : html`<a data-crumb=${x.go} @click=${x.click}>${x.t}</a>`}`)}</div>`;

/* id зоны у объекта; 0 — «Без зоны» (в отчёте zone_id может быть null) */
const zoneKeyOf = a => a.zone_id || 0;

function nightZoneBar(z) {
  const t = z.items_total || 0;
  const ok = Math.max(0, z.items_answered - z.items_bad);
  const w = n => (t ? Math.round(n / t * 100) : 0);
  return html`<div class="zone-bar" title=${`отмечено ${z.items_answered} из ${t} пунктов`}>
    <i class="ok" style=${`width:${w(ok)}%`}></i><i class="bad" style=${`width:${w(z.items_bad)}%`}></i>
    <i class="todo" style=${`width:${w(t - z.items_answered)}%`}></i></div>`;
}

const openZone = id => {
  nightState.zoneId = id; nightState.areaId = null;
  nightState.q = ''; nightState.filter = 'all';
  paintNight();
};

function nightZoneCard(z) {
  const cls = z.items_bad ? 'bad' : (z.areas_total && z.done === z.areas_total ? 'done' : '');
  const zid = z.zone_id || 0;
  return html`<div class=${`panel night-zone ${cls}`} data-zone=${zid}>
    <div class="night-area-head">
      <div><b>${z.name}</b> <span class="badge muted">${z.areas_total} объектов</span>
        ${z.areas_total ? nothing : html`<span class="badge warn">объектов нет</span>`}</div>
      <div class="night-area-prog">пунктов ${z.items_answered} / ${z.items_total}
        ${z.items_bad ? html`<span class="badge danger">Не ОК: ${z.items_bad}</span>` : nothing}
        ${z.items_unanswered ? html`<span class="badge muted">не отмечено ${z.items_unanswered}</span>` : nothing}</div>
    </div>
    ${nightZoneBar(z)}
    <div class="row-actions">
      <span class="badge ok">закрыто ${z.done}</span>
      ${z.taken ? html`<span class="badge warn">в работе ${z.taken}</span>` : nothing}
      ${z.free ? html`<span class="badge muted">свободно ${z.free}</span>` : nothing}
      <div style="flex:1"></div>
      <button class="btn btn-sm btn-primary" data-zone-open=${zid} @click=${() => openZone(zid)}>Объекты зоны →</button>
    </div>
  </div>`;
}

/* открыть объект: сразу берём его в работу (или перехватываем с подтверждением) */
async function openArea(rep, id, { take = true } = {}) {
  const a = (rep.areas || []).find(x => x.id === id);
  if (a && zoneKeyOf(a) !== nightState.zoneId) {
    Object.assign(nightState, { zoneId: zoneKeyOf(a), q: '', filter: 'all' });
  }
  nightState.areaId = id;
  if (take && !rep.readonly && a && a.status !== 'done') await sectionTake(id, false, reloadNight);
  else paintNight();
}
const reloadNight = () => fetchNight(true);

const isMyTakenArea = a => a.status === 'taken' && a.taken_by === state.user?.id;

async function resumeArea(reportId, areaId) {
  const rep = await fetchNight(true);
  if (rep?.id !== reportId || rep.readonly || view.rep !== rep || state.view !== 'night' ||
      nightState.zoneId !== null || nightState.areaId !== null) return;
  const area = rep.areas?.find(a => a.id === areaId && isMyTakenArea(a));
  if (area) openArea(rep, areaId, { take: false });
}

const reopenArea = async id => {
  try { await api(`/api/night/sections/${id}/reopen`, { method: 'POST' }); toast('Область переоткрыта', 'ok'); reloadNight(); }
  catch (e) { toast(e.message, 'err'); }
};

function nightObjectRow(a, rep) {
  const mine = a.taken_by === state.user?.id;
  const label = a.status === 'done' ? 'Посмотреть'
    : (a.status === 'taken' && !mine ? 'Перехватить' : (mine ? 'Продолжить' : 'Взять в работу'));
  return html`<div class=${`panel night-object ${a.status}`} data-area=${a.id}>
    <div class="night-area-head">
      <div><b>${a.name}</b>
        <span class=${`badge ${NIGHT_SECTION_BADGE[a.status] || 'muted'}`}>${a.status_title}</span>
        ${mine ? html`<span class="badge ok">ведёте вы</span>`
          : (a.taken_by_name ? html`<span class="badge info">${a.taken_by_name}</span>` : nothing)}</div>
      <div class="night-area-prog">${a.items_answered} / ${a.items_total}
        ${a.items_bad ? html`<span class="badge danger">Не ОК: ${a.items_bad}</span>` : nothing}
        ${a.items_unanswered ? html`<span class="badge muted">не отмечено ${a.items_unanswered}</span>` : nothing}
        ${a.closed_at ? html`<span class="muted">закрыт ${hhmm(a.closed_at)}</span>` : nothing}</div>
    </div>
    ${rep.readonly ? html`<div class="row-actions" style="margin-top:8px">
        <button class="btn btn-sm btn-ghost" data-sec-open=${a.id} @click=${() => openArea(rep, a.id)}>Посмотреть</button></div>`
      : html`<div class="row-actions" style="margin-top:8px">
        <button class=${`btn btn-sm ${mine || a.status === 'done' ? 'btn-ghost' : 'btn-accent'}`}
          data-sec-open=${a.id} @click=${() => openArea(rep, a.id)}>${label}</button>
        ${a.status === 'done'
          ? html`<button class="btn btn-sm btn-ghost" data-sec-reopen=${a.id} @click=${() => reopenArea(a.id)}>Переоткрыть</button>`
          : html`<button class="btn btn-sm" data-sec-close=${a.id} @click=${() => sectionClose(a.id, false, reloadNight)}>Завершить объект</button>`}</div>`}
  </div>`;
}

const interceptions = rep => ((rep.interceptions || []).length ? html`<div class="panel"><h3 class="panel-title">Перехваты областей</h3>
  <div class="history">${rep.interceptions.map(i => html`<div class="history-item">
    <div class="ts">${i.ts ? dRu(i.ts) + ' ' + hhmm(i.ts) : ''}</div>
    <div class="what"><b>${i.area_name}</b>: ${i.from_user_name || '—'} → ${i.to_user_name || '—'}</div>
  </div>`)}</div></div>` : nothing);

/* кнопки шапки: видимость зависит от того, есть ли отчёт и что можно делать */
function nightHead(rep) {
  const carsSection = rep?.areas?.find(a => a.is_cars);
  const hid = on => (on ? '' : ' hidden');
  const sendable = rep ? (rep.areas || []).reduce((n, a) => n
    + (a.items || []).filter(i => i.answer === 'bad' && !i.dispatched_at).length, 0) : 0;
  /* закрытие/переоткрытие смены — право night.close из каталога,
     а не проверка роли: базово оно у supervisor+, но выдаётся и снимается грантами */
  const sub = !rep ? 'Смена 20:00–08:00 · отчёт относится к дате начала смены'
    : (rep.reopened_at
      ? `Смена ${dateRu(rep.date)} · ${rep.shift_label || ''} · переоткрыта вручную — автозакрытие отключено`
      : `Смена ${dateRu(rep.date)} · ${rep.shift_label || ''} · автозакрытие ${hhmm(rep.deadline)}`);
  return html`<div class="page-head night-head">
      <div class="night-head-title"><h2>Ночной отчёт</h2><div class="sub" id="night-sub">${sub}</div></div>
      <div class="spacer"></div>
      <button type="button" class="btn btn-sm btn-ghost night-head-toggle" aria-controls="night-head-actions"
        aria-expanded=${String(headActionsOpen)} @click=${() => { headActionsOpen = !headActionsOpen; paintNight(); }}>Действия</button>
      <div class=${`night-head-actions${headActionsOpen ? ' open' : ''}`} id="night-head-actions">
        ${carsSection ? html`<button class="btn btn-sm btn-ghost night-head-mobile-action"
          @click=${() => nightCarsModal(rep, carsSection, reloadNight)}>${rep.readonly || rep.cars_step_done
            ? 'Посмотреть обход электрокаров' : 'Проверить электрокары'}</button>` : nothing}
        <button class="btn btn-sm" id="night-refresh" @click=${() => fetchNight()}>Обновить</button>
        <button class=${`btn btn-sm btn-ghost${hid(!!nightState.reportId)}`} id="night-today-btn"
          @click=${() => showNightReport(null)}>К текущей смене</button>
        <button class="btn btn-sm btn-ghost" id="night-archive" @click=${() => nightArchiveModal()}>Архив</button>
        <button class=${`btn btn-sm btn-ghost${hid(!!rep)}`} id="night-defects" @click=${() => nightDefectsModal()}>${sendable ? `Недостатки · ${sendable}` : 'Недостатки'}</button>
        <button class=${`btn btn-sm btn-ghost${hid(can('settings.view'))}`} id="night-dict" title="Настройки → Ночной обход"
          @click=${() => settingsOpen('night')}>Справочник ↗</button>
        <button class=${`btn btn-sm btn-ghost${hid(!!rep)}`} id="night-docx" @click=${() => exportNight('docx')}>DOCX</button>
        <button class=${`btn btn-sm btn-ghost${hid(!!rep)}`} id="night-pdf" @click=${() => exportNight('pdf')}>PDF</button>
        <button class=${`btn btn-sm btn-danger${hid(!!rep && !rep.readonly && can('night.close'))}`} id="night-close"
          @click=${() => closeReportModal()}>Закрыть смену</button>
        <button class=${`btn btn-sm btn-ghost${hid(!!rep && rep.readonly && can('night.close'))}`} id="night-reopen"
          @click=${() => reopenReport()}>Переоткрыть</button>
      </div>
    </div>`;
}

const nightPage = () => html`${nightHead(view.rep)}<div id="night-body">${nightBody()}</div>`;

function nightBody() {
  if (view.error) {
    return html`<div class="panel"><h3 class="panel-title">Отчёт не загрузился</h3>
      <p style="color:var(--danger);font-weight:600">${view.error}</p>
      <p class="hint">Нажмите «Обновить». Если ошибка повторяется — откройте «Архив» и выберите смену вручную.</p></div>`;
  }
  if (loadingPage) return html`<div class="skel-wrap"><div class="skel-line skel-lg"></div><div class="skel-line"></div><div class="skel-line"></div></div>`;
  const rep = view.rep;
  if (!rep) {
    return html`<div class="panel"><h3 class="panel-title">Отчёта пока нет</h3>
      <p class="hint" style="margin:0">${view.note || 'Ночная смена ещё не началась — отчёт появится в 20:00.'}</p>
      <p class="hint">Откройте «Архив», чтобы посмотреть прошлые смены.</p></div>`;
  }
  const p = rep.progress || { total: 0, done: 0, taken: 0, free: 0 };
  const areas = (rep.areas || []).filter(a => !a.is_cars);
  const carsSection = (rep.areas || []).find(a => a.is_cars);
  const zones = rep.zones || [];
  const bad = areas.reduce((s, a) => s + (a.items_bad || 0), 0);
  const unanswered = areas.reduce((s, a) => s + (a.items_unanswered || 0), 0);
  const toZones = () => { nightState.zoneId = null; nightState.areaId = null; paintNight(); };
  const toZone = () => { nightState.areaId = null; paintNight(); };

  /* ── уровень 3: чек-лист объекта ── */
  const area = areas.find(a => a.id === nightState.areaId) || null;
  if (nightState.areaId && !area) nightState.areaId = null;    // объекта в отчёте больше нет
  if (area) {
    return html`${nightCrumb([{ t: 'Ночной отчёт', go: 'zones', click: toZones },
      { t: area.zone_name || 'Без зоны', go: 'zone', click: toZone }, { t: area.name }])}
      ${nightAreaCard(area, rep)}
      <p class="hint">Пункты объекта — из шаблона его зоны (индивидуальные правки видны в справочнике).
      Закрыть объект можно и с неотмеченными пунктами — после подтверждения.</p>`;
  }

  /* ── уровень 2: объекты зоны ── */
  if (nightState.zoneId !== null) {
    const list = areas.filter(a => zoneKeyOf(a) === nightState.zoneId);
    const z = zones.find(x => (x.zone_id || 0) === nightState.zoneId) || {
      name: 'Без зоны', areas_total: list.length, items_total: 0, items_answered: 0, items_bad: 0,
      items_unanswered: 0, done: 0, taken: 0, free: list.length };
    const q = nightState.q.toLowerCase();
    const filtered = list.filter(a => {
      if (q && !a.name.toLowerCase().includes(q)) return false;
      if (nightState.filter === 'all') return true;
      if (nightState.filter === 'bad') return (a.items_bad || 0) > 0;
      return a.status === nightState.filter;
    });
    const firstFree = () => {
      const open = areas.filter(a => zoneKeyOf(a) === nightState.zoneId && a.status !== 'done');
      if (!open.length) { toast('В зоне все объекты закрыты', 'ok'); return; }
      nightState.areaId = open[0].id;
      sectionTake(open[0].id, false, reloadNight);
    };
    return html`${nightCrumb([{ t: 'Ночной отчёт', go: 'zones', click: toZones }, { t: z.name }])}
      <div class="page-head" style="margin-bottom:10px">
        <div><h2 style="margin:0">${z.name}</h2>
          <div class="sub">объектов ${z.areas_total} · закрыто ${z.done} · в работе ${z.taken}
            · пунктов ${z.items_answered} / ${z.items_total}
            ${z.items_bad ? html`· <b style="color:var(--danger)">Не ОК: ${z.items_bad}</b>` : nothing}</div></div>
        <div class="spacer"></div>
        ${rep.readonly ? nothing : html`<button class="btn btn-sm" id="night-first-free" @click=${firstFree}>К первому незакрытому</button>`}
      </div>
      ${nightZoneBar(z)}
      ${interceptions(rep)}
      <div class="toolbar">
        <div class="seg">${[['all', 'Все'], ['free', 'Свободны'], ['taken', 'В работе'],
                           ['done', 'Закрыты'], ['bad', 'С замечаниями']]
          .map(([k, t]) => html`<button data-ofilter=${k} class=${nightState.filter === k ? 'active' : ''}
            @click=${() => { nightState.filter = k; paintNight(); }}>${t}</button>`)}</div>
        <input type="search" id="night-obj-q" placeholder="Поиск по объектам…"
          .value=${nightState.q} style="max-width:240px"
          @input=${e => { nightState.q = e.target.value.trim(); paintNight(); }}>
        <div class="spacer"></div>
        <span class="hint" style="margin:0">показано ${filtered.length} из ${list.length}</span>
      </div>
      <div class="night-objects">${filtered.length ? filtered.map(a => nightObjectRow(a, rep))
        : html`<div class="empty">Объектов в зоне нет или ничего не найдено</div>`}</div>
      <p class="hint">Объект ведёт один человек: «Взять в работу» закрепляет его за вами, чужой — только
      через подтверждение (перехват фиксируется в отчёте).</p>`;
  }

  /* ── уровень 1: зоны ── */
  const ongoingArea = rep.readonly ? null : areas.find(isMyTakenArea);
  return html`<div class="night-work">
    ${rep.readonly ? html`<div class="night-work-result ro-banner">
      Смена закрыта ${rep.closed_at ? dRu(rep.closed_at) + ' ' + hhmm(rep.closed_at) : ''}
      · <strong>итог: ${rep.result_title || '—'}</strong> · правки недоступны</div>` : nothing}
    ${ongoingArea ? html`<div class="night-work-resume panel">
      <div><strong>${ongoingArea.name}</strong><div class="muted">${ongoingArea.zone_name || 'Без зоны'}</div></div>
      <button class="btn btn-primary" @click=${() => resumeArea(rep.id, ongoingArea.id)}>Продолжить обход</button>
    </div>` : nothing}

    <div class="night-zones">${zones.length ? zones.map(nightZoneCard)
      : html`<div class="empty">Зоны обхода не настроены. Добавьте их в «Настройки → Ночной обход».</div>`}</div>

    <div class="night-work-summary stat-grid">
      <div class="stat"><div class="k">Зон</div><div class="v">${zones.length}</div></div>
      <div class="stat"><div class="k">Объектов</div><div class="v">${p.total}</div></div>
      <div class="stat accent"><div class="k">Объектов закрыто</div><div class="v">${p.done} <small>/ ${p.total}</small></div></div>
      <div class="stat warn"><div class="k">В работе</div><div class="v">${p.taken}</div></div>
      <div class="stat danger"><div class="k">Замечаний (Не ОК)</div><div class="v">${bad}</div></div>
      <div class="stat info"><div class="k">Не отмечено пунктов</div><div class="v">${unanswered}</div></div>
      <div class=${`stat ${rep.cars_step_done ? '' : 'warn'}`}><div class="k">Электрокары</div>
        <div class="v">${rep.cars_step_done ? 'готово' : 'не завершено'}</div></div>
    </div>

    <div class="night-work-secondary">
      ${carsSection ? html`<div class="panel"><h3 class="panel-title">Шаг «Проверка электрокаров»
          <span class=${`badge ${carsSection.status === 'done' ? 'ok' : 'warn'}`}>${carsSection.status_title}</span></h3>
        <p class="hint" style="margin:0 0 10px">Отдельный шаг обхода (не зона): где кар, заряд, тент, состояние,
        «кар найден на месте», перепарковка и фото. Замечания попадают супервайзеру, состояние карточек
        каров обновляется автоматически.</p>
        <button class="btn btn-primary" id="night-cars-open"
          @click=${() => nightCarsModal(rep, carsSection, reloadNight)}>${rep.cars_step_done ? 'Посмотреть обход' : 'Проверить электрокары'}</button>
        ${carsSection.closed_at ? html`<span class="hint"> · завершено в ${hhmm(carsSection.closed_at)}</span>` : nothing}
      </div>` : nothing}
      ${interceptions(rep)}
    </div>
  </div>`;
}

function nightAreaCard(a, rep) {
  const mine = a.taken_by === state.user?.id;
  return html`<div class=${`panel night-area ${a.status}`} data-area=${a.id}>
    <div class="night-area-head">
      <div><b>${a.name}</b>
        <span class=${`badge ${NIGHT_SECTION_BADGE[a.status] || 'muted'}`}>${a.status_title}</span>
        ${mine ? html`<span class="badge ok">ведёте вы</span>` : (a.taken_by_name ? html`<span class="badge info">${a.taken_by_name}</span>` : nothing)}
      </div>
      <div class="night-area-prog">${a.items_answered} / ${a.items_total}
        ${a.items_bad ? html`<span class="badge danger">Не ОК: ${a.items_bad}</span>` : nothing}
        ${a.closed_at ? html`<span class="muted">закрыта ${hhmm(a.closed_at)}</span>` : nothing}</div>
    </div>
    ${rep.readonly ? nothing : html`<div class="row-actions" style="margin:8px 0">
      ${a.status === 'done'
        ? html`<button class="btn btn-sm btn-ghost" data-sec-reopen=${a.id} @click=${() => reopenArea(a.id)}>Переоткрыть</button>`
        : html`<button class=${`btn btn-sm ${mine ? 'btn-ghost' : 'btn-accent'}`} data-sec-take=${a.id}
            @click=${() => sectionTake(a.id, false, reloadNight)}>${a.status === 'taken' && !mine ? 'Перехватить' : (mine ? 'Продолжить' : 'Взять в работу')}</button>
           <button class="btn btn-sm" data-sec-close=${a.id} @click=${() => sectionClose(a.id, false, reloadNight)}>Завершить область</button>`}
    </div>`}
    <div class="night-items">${(a.items || []).length ? a.items.map(it => nightItemRow(it, rep, a.status === 'done'))
      : html`<div class="hint" style="margin:0">Пунктов нет — справочник областей: кнопка «Области».</div>`}</div>
  </div>`;
}

/* ответ на пункт: повторный тап по тому же ответу — снять */
async function answerItem(rep, it, next) {
  const cur = it.answer === next ? '' : next;
  try {
    await api(`/api/night/items/${it.id}/answer`, { method: 'PUT', body: { answer: cur, comment: it.comment || '' } });
    reloadNight();
  } catch (e) { toast(e.message, 'err'); }
}

/* фото и видео грузятся одним маршрутом: тип сервер определяет по содержимому */
async function uploadMedia(it, e) {
  const f = e.target.files?.[0];
  if (!f) return;
  const fd = new FormData();
  fd.append('file', f, f.name);
  try {
    const r = await multipartApi(`/api/night/items/${it.id}/photo`, fd);
    toast(r?.photo?.media_type === 'video' ? 'Видео добавлено' : 'Фото добавлено', 'ok'); reloadNight();
  } catch (err) { toast(err.message, 'err'); }
}

function nightItemRow(it, rep, sectionDone = false) {
  // закрытая смена или закрытая область — только просмотр (сервер отвечает 409)
  const readonly = rep.readonly || sectionDone;
  const photos = (it.photos || []);
  return html`<div class=${`night-item ${it.answer || 'none'}`} data-item=${it.id}>
    <div class="night-item-text">${it.text}
      ${it.service_name ? html`<span class="badge info" title="Ответственная служба: недостаток уйдёт ей">⚖ ${it.service_name}</span>` : nothing}
      ${it.answered_by_name ? html`<small class="muted">· ${it.answered_by_name}${it.answered_at ? ' ' + hhmm(it.answered_at) : ''}</small>` : nothing}
    </div>
    <div class="night-item-acts">
      ${readonly
        ? html`<span class=${`badge ${NIGHT_ANSWER_BADGE[it.answer] || 'muted'}`}>${it.answer_title}</span>`
        : html`<button class=${`btn btn-sm ${it.answer === 'ok' ? 'btn-primary' : 'btn-ghost'}`} data-ans="ok" data-id=${it.id}
            @click=${() => answerItem(rep, it, 'ok')}>ОК</button>
           <button class=${`btn btn-sm ${it.answer === 'bad' ? 'btn-danger' : 'btn-ghost'}`} data-ans="bad" data-id=${it.id}
            @click=${() => answerItem(rep, it, 'bad')}>Не ОК</button>
           <button class="btn btn-sm btn-ghost" data-cmt=${it.id} title="Комментарий"
            @click=${() => itemCommentModal(it, reloadNight)}>💬${it.comment ? ' •' : ''}</button>
           <label class="btn btn-sm btn-ghost" title="Добавить фото">📷
             <input type="file" accept="image/*" data-photo=${it.id} class="hidden-file" @change=${e => uploadMedia(it, e)}></label>
           <label class="btn btn-sm btn-ghost" title="Снять видео">🎥
             <input type="file" accept="video/*" capture="camcorder" data-video=${it.id} class="hidden-file" @change=${e => uploadMedia(it, e)}></label>`}
      ${photos.length ? html`<div class="thumbs">${photos.map(p => photoThumb(p, reloadNight))}</div>` : nothing}
      ${it.comment ? html`<div class="night-item-cmt">${it.comment}</div>` : nothing}
    </div>
  </div>`;
}

/* ─────────────── взять / закрыть область (с подтверждениями 409) ─────────────── */
async function sectionTake(sectionId, ack, after) {
  try {
    const r = await api(`/api/night/sections/${sectionId}/take`, { method: 'POST', body: { ack: !!ack } });
    if (r.warning) toast(r.warning, 'warn');
    else if (!r.already) toast('Область за вами', 'ok');
    if (after) await after();
  } catch (e) {
    if (e.payload?.interception) {
      confirmDialog('Область уже ведут', e.payload.message, () => sectionTake(sectionId, true, after),
        'Продолжить (перехват)', false);
    } else toast(e.message, 'err');
  }
}

async function sectionClose(sectionId, force, after) {
  try {
    await api(`/api/night/sections/${sectionId}/close`, { method: 'POST', body: { force_unanswered: !!force } });
    toast('Область закрыта', 'ok');
    if (after) await after();
  } catch (e) {
    if (e.status === 409 && e.payload?.unanswered !== undefined) {
      confirmDialog('Есть неотмеченные пункты', e.payload.message, () => sectionClose(sectionId, true, after),
        'Закрыть всё равно');
    } else toast(e.message, 'err');
  }
}

function itemCommentModal(item, after) {
  openModal({
    title: 'Комментарий к пункту',
    subtitle: item.text,
    body: html`<textarea id="ni-comment" rows="4" maxlength="2000" placeholder="Что не так, что сделали, кому сообщили" .value=${item.comment || ''}></textarea>
      <p class="hint">Ответ: <b>${item.answer_title}</b>. Комментарий сохраняется вместе с автором и временем,
      попадает в выгрузку DOCX/PDF.</p>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Сохранить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        try {
          await api(`/api/night/items/${item.id}/answer`, { method: 'PUT',
            body: { answer: item.answer || '', comment: $('#ni-comment').value } });
          closeModal(); toast('Комментарий сохранён', 'ok');
          if (after) await after();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ─────────────── шаг «Проверка электрокаров» внутри отчёта ─────────────── */
async function nightCarsModal(rep, section, after) {
  const draw = async () => {
    const st = await api(`/api/night/reports/${rep.id}/cars`);
    openModal({
      title: 'Проверка электрокаров',
      subtitle: `Смена ${dateRu(rep.date)} · проверено ${st.checked} из ${st.total}${st.problems ? ` · замечаний: ${st.problems}` : ''}`,
      wide: true,
      body: html`<div class="check-list" style="max-height:52vh">${st.list.length ? st.list.map(e => {
        const c = e.car, k = e.check;
        return html`<div class="rule-row" style="grid-template-columns:1fr auto">
          <div><div class="lbl">№${c.number}
              <span class=${`badge ${CAR_BADGE[c.status] || 'muted'}`}>${c.status_title}</span>
              ${e.checked ? (k.found ? html`<span class="badge ok">проверен</span>` : html`<span class="badge danger">не найден</span>`) : html`<span class="badge muted">не проверен</span>`}
              ${k?.taken_after_check ? html`<span class="badge warn">взят после проверки</span>` : nothing}
              ${k?.moved ? html`<span class="badge info" title="батлер переставил кар">перепаркован</span>` : nothing}
              ${k?.photos?.length ? html`<span class="badge info" title="фото отметки">📷 ${k.photos.length}</span>` : nothing}</div>
            <div class="desc">${nightCarPlace(c, k)} · заряд: ${k ? (k.charge || '—') : (c.charge_title || '—')}
              ${k ? ` · ${hhmm(k.checked_at || '')} ${k.checker_name || ''}` : ''}
              ${k?.comment ? ` · ${k.comment}` : ''}</div></div>
          <div style="display:flex;gap:6px;align-items:center">
            ${rep.readonly ? nothing : html`<button class=${`btn btn-sm ${e.checked ? 'btn-ghost' : 'btn-primary'}`} data-car-check=${c.id}
              @click=${async () => { try { await nightCarCheckModal(rep, c.id, draw); } catch (err) { toast(err.message || String(err), 'err'); } }}>${e.checked ? 'Изменить' : 'Отметить'}</button>`}
          </div></div>`;
      }) : html`<div class="empty">Активных каров нет</div>`}</div>
      <p class="hint">Отметка обновляет карточку кара в общей базе. «Не ОК» по состоянию и «кар не найден»
      попадают в замечания супервайзеру; отсутствие тента — просто факт.</p>`,
      footer: html`<button class="btn btn-ghost" data-cancel>Закрыть</button>
               ${rep.readonly ? nothing : html`<button class="btn btn-primary" data-finish>${st.cars_step_done ? 'Шаг завершён · отметить снова' : 'Завершить шаг'}</button>`}`,
      onMount(m) {
        m.querySelector('[data-cancel]').onclick = closeModal;
        const fin = m.querySelector('[data-finish]');
        if (fin) fin.onclick = () => carsFinish(rep, st.unchecked, async () => { closeModal(); if (after) await after(); });
      },
    });
  };
  await draw();
}

/* Место кара в списке обхода: при перепарковке показываем переход
   «где нашёл → куда переставил», иначе — где кар стоит сейчас. */
function nightCarPlace(c, k) {
  if (!k) return c.location || 'место не указано';
  if (k.moved && k.location) return `${k.found_location || '—'} → ${k.location}`;
  return k.found_location || k.location || c.location || 'место не указано';
}

/* Окно отметки кара в ночном обходе приведено к виду окна возврата кара
   («Электрокары» → «Вернул»): те же чекбоксы состояния, место — выпадающим
   списком из справочника, заряд, комментарий и фото (камера/галерея).
   Сверху — чекбокс «Кар найден на месте»: без него отметка уходит в замечания
   супервайзеру, а карточка кара не меняется. Данные берём свежими (отметку
   мог изменить второй батлер), поэтому окно само загружает состояние обхода. */
async function nightCarCheckModal(rep, carId, after) {
  const [st] = await Promise.all([api(`/api/night/reports/${rep.id}/cars`), ensureCarLocations()]);
  const entry = st.list.find(x => x.car.id === carId);
  if (!entry) return toast('Кар не найден в обходе — обновите список', 'warn');
  const c = entry.car, k = entry.check || null;
  /* первая отметка — значения из карточки кара, повторная — уже сохранённые в отметке */
  const pick = (carVal, checkVal) => (k ? checkVal : carVal);
  /* места два: где батлер нашёл кар и куда переставил (у прежних отметок
     было одно поле location — берём его как «где нашёл», если перепарковки не было) */
  const foundLoc = k ? (k.found_location || (k.moved ? '' : k.location) || '') : (c.location || '');
  const newLoc = k?.moved ? (k.location || '') : '';
  const reopen = () => nightCarCheckModal(rep, carId, after);

  openModal({
    title: `Кар №${c.number} — ночной обход`,
    subtitle: `${c.status_title}${c.holder_name ? ' · держит ' + c.holder_name : ''} · ${c.location || 'место не указано'}`,
    wide: true,
    body: html`
      <div class="check-list" style="max-height:none;margin-bottom:10px">
        ${checkField('nc-found', 'Кар найден на месте', !k || k.found)}
      </div>
      <p class="hint hidden" id="nc-notfound" style="margin:0 0 10px;color:var(--danger)">Кар не найден — отметка
      уйдёт в замечания супервайзеру, карточка кара не изменится. Напишите в комментарии, где кар (если известно).</p>
      <div class="grid-2">
        <label class="field"><span id="nc-found-loc-label">Где нашёл</span>
          <select id="nc-found-location"><option value="">— не указывать —</option>${locationOptions(foundLoc)}</select></label>
        <label class="field"><span>Заряд</span>
          <select id="nc-charge"><option value="">— не отмечать —</option>${CHARGE_OPTS.map(([v, t]) =>
            html`<option value=${v} ?selected=${v === pick(c.charge, k?.charge)}>${t}</option>`)}</select></label>
      </div>
      <div id="nc-moved-row" style="margin-top:8px">${checkField('nc-moved', 'Перепаркован на другое место', !!newLoc)}</div>
      <label class="field hidden" id="nc-newloc-row"><span>Куда переставил</span>
        <select id="nc-location"><option value="">— не указывать —</option>${locationOptions(newLoc)}</select></label>
      <div class="opt-group-title">Состояние кара</div>
      <div class="check-list" id="nc-state" style="max-height:none">
        ${checkField('nc-ok', 'Технически исправен', pick(c.condition, k?.condition) !== 'bad')}
        ${checkField('nc-clean', 'Чистый', pick(c.clean, k?.clean))}
        ${checkField('nc-things', 'В салоне вещи', pick(c.trash, k?.trash))}
        ${checkField('nc-canopy', 'Тент', pick(c.canopy, k?.canopy))}
        ${checkField('nc-oncharge', 'Заряжается', pick(c.on_charge, k?.on_charge))}
      </div>
      <label class="field" style="margin-top:12px"><span>Комментарий (что случилось, куда поставили)</span>
        <textarea id="nc-comment" rows="2" maxlength="2000" placeholder="Например: кар не на месте, тент снят, оставлен у главного входа" .value=${k?.comment || ''}></textarea></label>
      ${k?.photos?.length ? html`<div class="field" style="margin-top:12px"><span>Фото отметки</span>
        <div class="thumbs">${k.photos.map(p => photoThumb(p, reopen))}</div></div>` : nothing}
      ${photoPick('nc')}
      <p class="hint">Снятая галочка «Технически исправен» переводит кар в статус «на обслуживании»
      (снимает менеджер или администратор); «кар не найден» и «не исправен» попадают в замечания
      супервайзеру. «В салоне вещи», «Тент», «Заряжается» — факты: они видны в карточке кара.
      «Перепаркован на другое место» — тоже факт: место в карточке кара обновится, а переход
      «где нашёл → куда переставил» супервайзер увидит в обходе и в выгрузке DOCX/PDF.
      Новый снимок добавляется к отметке, прежние удаляются крестиком.</p>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Сохранить отметку</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      /* «Кар найден на месте» подсказывает, что отметка не изменит карточку кара;
         нет кара — нет и перепарковки, а место имеет смысл только «если известно» */
      const found = m.querySelector('#nc-found'), nf = m.querySelector('#nc-notfound');
      const moved = m.querySelector('#nc-moved'), movedRow = m.querySelector('#nc-moved-row');
      const newLocRow = m.querySelector('#nc-newloc-row');
      const foundLocLabel = m.querySelector('#nc-found-loc-label');
      const syncMoved = () => newLocRow.classList.toggle('hidden', !(found.checked && moved.checked));
      const syncFound = () => {
        nf.classList.toggle('hidden', found.checked);
        movedRow.classList.toggle('hidden', !found.checked);
        foundLocLabel.textContent = found.checked ? 'Где нашёл' : 'Место (если известно)';
        syncMoved();
      };
      moved.onchange = syncMoved;
      found.onchange = syncFound; syncFound();
      const pickPhoto = bindPhotoPick(m, 'nc');
      m.querySelector('[data-ok]').onclick = async () => {
        const wantMove = found.checked && moved.checked;
        if (wantMove && !$('#nc-location').value) {
          return toast('Укажите место, куда переставили кар', 'warn');
        }
        const fd = new FormData();
        fd.append('found', found.checked ? 'true' : 'false');
        fd.append('found_location', $('#nc-found-location').value || '');
        fd.append('moved', wantMove ? 'true' : 'false');
        fd.append('location', wantMove ? ($('#nc-location').value || '') : '');
        fd.append('charge', $('#nc-charge').value || '');
        fd.append('canopy', $('#nc-canopy').checked ? 'true' : 'false');
        fd.append('condition', $('#nc-ok').checked ? 'ok' : 'bad');
        fd.append('trash', $('#nc-things').checked ? 'true' : 'false');
        fd.append('clean', $('#nc-clean').checked ? 'true' : 'false');
        fd.append('on_charge', $('#nc-oncharge').checked ? 'true' : 'false');
        fd.append('comment', $('#nc-comment').value.trim());
        const photo = pickPhoto();
        if (photo) fd.append('file', photo, photo.name || 'photo.jpg');
        try {
          await multipartApi(`/api/night/reports/${rep.id}/cars/${c.id}/check`, fd);
          closeModal(); toast(`Кар №${c.number} отмечен`, 'ok');
          if (after) await after();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

async function carsFinish(rep, unchecked, after) {
  const send = async ack => {
    try {
      await api(`/api/night/reports/${rep.id}/cars/finish`, { method: 'POST', body: { ack: !!ack } });
      toast('Шаг «Проверка электрокаров» завершён', 'ok');
      if (after) await after();
    } catch (e) {
      if (e.status === 409 && e.payload?.message) confirmDialog('Не все кары проверены', e.payload.message,
        () => send(true), 'Завершить всё равно');
      else toast(e.message, 'err');
    }
  };
  await send(false);
}

/* ─────────────── закрытие / переоткрытие смены (супервайзер и выше) ─────────────── */
function closeReportModal() {
  confirmDialog('Закрыть ночную смену?',
    'После закрытия правки недоступны (только переоткрытие супервайзером). Если остались незакрытые области или не завершён шаг электрокаров — смена получит итог «неполный».',
    async () => {
      const send = async force => {
        try {
          await api(`/api/night/reports/${nightState.reportId || nightState.today?.report?.id}/close`,
            { method: 'POST', body: { force_unanswered: !!force } });
          toast('Смена закрыта', 'ok'); showNightReport(nightState.reportId);
        } catch (e) {
          if (e.status === 409 && e.payload?.message) confirmDialog('Смена будет неполной', e.payload.message,
            () => send(true), 'Закрыть всё равно');
          else toast(e.message, 'err');
        }
      };
      await send(false);
    }, 'Закрыть смену');
}

async function reopenReport() {
  const id = nightState.reportId || nightState.today?.report?.id;
  if (!id) return;
  confirmDialog('Переоткрыть смену?',
    'Отчёт снова станет доступным для правок; итог будет пересчитан при закрытии. Автозакрытие в 08:00 для него отключится — закройте смену вручную, когда закончите правки.',
    async () => {
      try { await api(`/api/night/reports/${id}/reopen`, { method: 'POST' }); toast('Смена переоткрыта', 'ok'); fetchNight(); }
      catch (e) { toast(e.message, 'err'); }
    }, 'Переоткрыть', false);
}

/* ─────────────── архив смен ─────────────── */
async function nightArchiveModal() {
  const { reports } = await api('/api/night/reports?limit=60');
  openModal({
    title: 'Архив ночных отчётов',
    subtitle: `${reports.length} смен · последние 60`,
    wide: true,
    body: html`<div class="table-wrap" tabindex="0" style="max-height:56vh"><table class="data responsive">
        <thead><tr><th>Дата</th><th>Статус</th><th>Итог</th><th>Области</th><th>Электрокары</th><th>Закрыт</th><th></th></tr></thead>
        <tbody>${reports.length ? reports.map(r => html`<tr>
          <td data-label="Дата"><b>${dateRu(r.date)}</b><small>${r.shift_label || ''}</small></td>
          <td data-label="Статус"><span class=${`badge ${r.status === 'closed' ? 'ok' : 'warn'}`}>${r.status === 'closed' ? 'закрыт' : (r.reopened_at ? 'открыт · переоткрыт' : 'открыт')}</span></td>
          <td data-label="Итог">${r.result_title || '—'}</td>
          <td data-label="Области" class="num">${r.progress?.done || 0} / ${r.progress?.total || 0}</td>
          <td data-label="Электрокары">${r.cars_step_done ? html`<span class="badge ok">готово</span>` : html`<span class="badge muted">—</span>`}</td>
          <td data-label="Закрыт">${r.closed_at ? dRu(r.closed_at) + ' ' + hhmm(r.closed_at) : '—'}</td>
          <td data-label=""><button class="btn btn-sm btn-ghost" data-open=${r.id}
            @click=${() => { closeModal(); showNightReport(r.id); }}>Открыть</button></td>
        </tr>`) : html`<tr><td colspan="7" class="empty">Отчётов пока нет</td></tr>`}</tbody></table></div>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Закрыть</button>`,
    onMount(m) { m.querySelector('[data-cancel]').onclick = closeModal; },
  });
}

/* ─────────────── выгрузка ─────────────── */
function exportNight(fmt) {
  const id = nightState.reportId || nightState.today?.report?.id;
  if (!id) return toast('Нет отчёта для выгрузки', 'warn');
  downloadBlob(`/api/night/reports/${id}/export.${fmt}`, `night-${fmt}.docx`);
}

/* ══════════════════════════════════════════════════════════════════
   НЕДОСТАТКИ СМЕНЫ: консолидированная отправка службам (этап 5)
   ══════════════════════════════════════════════════════════════════ */
/* «Не ОК» и «Не проверено» группируются по ответственным службам и отправляются
   вручную — всё скопом или выборочно. Отправленное помечается и повторно не
   уходит; если пункт исправили ПОСЛЕ отправки, ничего не отправляем и не отзываем.
   Транспорт и шаблоны — общие настройки приложения («Настройки → Чаты и Почта»). */

function defectRow(d, selected, again) {
  const media = (d.media || []).filter(x => x.url);
  return html`<label class=${`rule-row defect-row${d.sendable ? '' : ' sent'}`} style="grid-template-columns:auto 1fr">
    <input type="checkbox" data-def=${d.id} .checked=${selected} ?disabled=${!d.sendable}
      title=${d.sendable ? 'включить в отправку' : 'уже отправлено или исправлено после отправки'}>
    <div>
      <div class="lbl">${d.area} <span class="muted">· ${d.zone || ''}</span>
        ${d.kind === 'bad' ? html`<span class="badge danger">Не ОК</span>`
          : d.kind === 'fixed' ? html`<span class="badge info">было в отправке</span>`
            : html`<span class="badge muted">Не проверено</span>`}
        ${d.fixed_after_dispatch ? html`<span class="badge info" title="Ничего не отправляем и не отзываем">исправлено после отправки</span>`
          : (d.dispatched ? html`<span class="badge ok" title=${`Отправлено ${d.dispatched_at || ''}`}>отправлено${d.dispatched_at ? ' ' + hhmm(d.dispatched_at) : ''}</span>` : nothing)}
        ${media.length ? html`<span class="badge info" title=${`вложений: ${media.length}`}>📎 ${media.length}</span>` : nothing}</div>
      <div class="desc">${d.text}${d.comment ? html` — <i>${d.comment}</i>` : nothing}
        ${d.answered_by_name ? html`<span class="muted">· ${d.answered_by_name}${d.answered_at ? ' ' + hhmm(d.answered_at) : ''}</span>` : nothing}</div>
      ${media.length ? html`<div class="thumbs">${media.map(p => photoThumb(p, again))}</div>` : nothing}
    </div></label>`;
}

function defectGroup(g, selectedIds, again) {
  const problems = (g.problems || []).join('; ');
  return html`<div class=${`panel defect-group${g.ready ? '' : ' not-ready'}`}>
    <h3 class="panel-title">⚖ ${g.service_name}
      <span class=${`badge ${g.counts.sendable ? 'warn' : 'muted'}`}>к отправке: ${g.counts.sendable}</span>
      ${g.counts.dispatched ? html`<span class="badge ok">отправлено: ${g.counts.dispatched}</span>` : nothing}
      ${g.counts.fixed_after_dispatch ? html`<span class="badge info">исправлено после отправки: ${g.counts.fixed_after_dispatch}</span>` : nothing}
      ${(g.channels || []).map(c => (c === 'telegram'
        ? html` <span class="badge info">чат · ${g.chat_ids.length}</span>`
        : html` <span class="badge info">письмо · ${(g.email_to || []).join(', ')}</span>`))}</h3>
    ${problems ? html`<p class="hint" style="color:var(--danger);margin:0 0 8px">Нельзя отправить: ${problems}</p>` : nothing}
    ${g.note ? html`<p class="hint" style="margin:0 0 8px">${g.note}</p>` : nothing}
    <div class="check-list" style="max-height:34vh">${g.defects.map(d => defectRow(d, selectedIds.has(d.id), again))}</div>
    ${g.counts.sendable && g.ready && can('night.dispatch') ? html`<div class="row-actions" style="margin-top:8px">
      <button class="btn btn-sm btn-primary" data-send-service=${g.service_id}>Отправить службе</button></div>` : nothing}
  </div>`;
}

function defectJournal(rows) {
  if (!rows.length) return html`<div class="empty">Отправок пока не было</div>`;
  return html`<div class="table-wrap" tabindex="0"><table class="data"><thead><tr>
      <th>Время</th><th>Кто</th><th>Служба</th><th>Канал</th><th>Получатель</th>
      <th>Позиций</th><th>Вложений</th><th>Статус</th><th></th></tr></thead><tbody>
    ${rows.map(d => html`<tr>
      <td>${d.ts ? d.ts.slice(5, 16).replace('T', ' ') : ''}</td>
      <td>${d.actor_name}</td><td>${d.recipient_name}</td>
      <td>${d.channel_title}</td><td><code>${d.target}</code></td>
      <td class="num">${d.items_count}</td><td class="num">${d.media_count}</td>
      <td>${d.status === 'sent' ? html`<span class="badge ok">отправлено${d.attempts > 1 ? ` (попыток: ${d.attempts})` : ''}</span>`
        : d.status === 'failed' ? html`<span class="badge danger" title=${d.error}>ошибка</span>`
        : html`<span class="badge warn">${d.status_title}</span>`}</td>
      <td class="num"><button class="btn btn-sm btn-ghost" data-msg=${d.id}>текст</button>
        ${d.can_retry ? html`<button class="btn btn-sm" data-retry=${d.id}>повторить</button>` : nothing}</td></tr>`)}
    </tbody></table></div>`;
}

async function nightDefectsModal() {
  /* смена — как в остальном разделе: выбранная в архиве или текущая */
  const reportId = nightState.reportId || nightState.today?.report?.id;
  if (!reportId) return toast('Сначала откройте смену', 'warn');
  const sel = nightState.defectsSelected;

  const draw = async () => {
    let d;
    try { d = await api(`/api/night/reports/${reportId}/defects`); }
    catch (e) { return toast(e.message, 'err'); }
    const c = d.counts || {};
    const transport = d.transport || {};
    const groups = d.groups || [];
    const sendableGroups = groups.filter(g => g.counts.sendable > 0);
    const canSend = can('night.dispatch');
    openModal({
      title: `Недостатки смены · ${dateRu(d.report.date)}`,
      subtitle: `Ночные батлеры смены: ${d.duty} · к отправке ${c.sendable || 0} из ${c.total || 0}`
        + ` · отправлено ${c.dispatched || 0}` + (c.fixed_after_dispatch ? ` · исправлено после отправки ${c.fixed_after_dispatch}` : ''),
      wide: true,
      body: html`
        ${(!transport.telegram && !transport.email) ? html`<p class="hint" style="color:var(--danger);margin:0 0 10px">
          Доставка не настроена: заполните токен бота и/или почту в «Настройки → Чаты и Почта».</p>` : nothing}
        <div class="toolbar" style="margin-bottom:10px">
          <button class="btn btn-sm btn-primary" id="df-all" ?disabled=${!(c.sendable && canSend)}>Отправить всё (${c.sendable || 0})</button>
          <button class="btn btn-sm" id="df-sel" ?disabled=${!(sel.size && canSend)}>Отправить выбранное (${sel.size})</button>
          <button class="btn btn-sm" id="df-preview">Предпросмотр</button>
          <label class="chk" style="margin:0"><input type="checkbox" id="df-sent" .checked=${nightState.defectsShowSent}>
            показывать отправленные и исправленные</label>
          <div class="spacer"></div>
          <span class="hint" style="margin:0">${canSend ? '«Не проверено» включается в отчёт'
            : html`Отправка службам — право <b>night.dispatch</b> («Настройки → Права доступа»)`}</span>
        </div>
        ${sendableGroups.length ? nothing : html`<div class="empty">Недостатков к отправке нет</div>`}
        ${groups.filter(g => nightState.defectsShowSent || g.counts.sendable > 0).map(g => defectGroup(g, sel, draw))}
        <div class="opt-group-title">Журнал отправок смены</div>
        <div class="row-actions" style="margin-bottom:6px">
          <button class="btn btn-sm btn-ghost" id="df-csv">Выгрузить журнал (CSV)</button>
          <span class="hint" style="margin:0">журнал общий для всех разделов приложения</span></div>
        ${defectJournal(d.dispatches || [])}`,
      footer: html`<button class="btn btn-ghost" data-cancel>Закрыть</button>`,
      onMount(m) {
        m.querySelector('[data-cancel]').onclick = closeModal;
        $$('[data-def]', m).forEach(cb => cb.onchange = () => {
          const id = Number(cb.dataset.def);
          if (cb.checked) sel.add(id); else sel.delete(id);
          const btn = $('#df-sel', m);
          if (btn) { btn.textContent = `Отправить выбранное (${sel.size})`; btn.disabled = !sel.size || !canSend; }
        });
        const sent = $('#df-sent', m);
        if (sent) sent.onchange = () => { nightState.defectsShowSent = sent.checked; draw(); };
        const send = async (body, okText) => {
          loading(true);
          try {
            // службы и каналы идут по очереди, у каждого канала свой таймаут до 300 с (UI-03)
            const r = await api(`/api/night/reports/${reportId}/dispatch`, { method: 'POST', body, timeout: 300000 });
            const warn = [];
            if (r.failed) warn.push(`ошибок доставки: ${r.failed}`);
            if (r.queued) warn.push(`ещё отправляется: ${r.queued} — статус появится в журнале`);
            (r.skipped || []).forEach(s => warn.push(`${s.service_name}: ${s.problems.join('; ')}`));
            toast(`${okText}: отправлено ${r.sent}, отмечено позиций ${r.marked}`
              + (warn.length ? ` · ${warn.join(' · ')}` : ''), warn.length ? 'warn' : 'ok', warn);
            sel.clear();
            await draw();
            fetchNight(true);
          } catch (e) { toast(e.message, 'err'); }
          finally { loading(false); }
        };
        const allBtn = $('#df-all', m);
        if (allBtn) allBtn.onclick = () => confirmDialog('Отправить все недостатки?',
          `Службам уйдёт ${c.sendable} позиц(ии): «Не ОК» и «Не проверено». Отправленное повторно не уходит; `
          + 'если недостаток исправят после отправки, уведомлений не будет.',
          () => send({ mode: 'all' }, 'Отправлено всё'), 'Отправить всё', false);
        const selBtn = $('#df-sel', m);
        if (selBtn) selBtn.onclick = () => send({ mode: 'selected', item_ids: [...sel] }, 'Отправлено выбранное');
        $$('[data-send-service]', m).forEach(b => b.onclick = () => {
          const sid = Number(b.dataset.sendService);
          const g = groups.find(x => x.service_id === sid);
          confirmDialog(`Отправить службе «${g.service_name}»?`,
            `Позиций: ${g.counts.sendable}. Каналы: ${(g.channels || []).join(', ') || '—'}.`,
            () => send({ mode: 'all', service_ids: [sid] }, 'Отправлено службе'), 'Отправить', false);
        });
        const prev = $('#df-preview', m);
        if (prev) prev.onclick = async () => {
          const body = sel.size ? { mode: 'selected', item_ids: [...sel] } : { mode: 'all' };
          try {
            const r = await api(`/api/night/reports/${reportId}/defects/preview`, { method: 'POST', body });
            openModal({
              title: 'Предпросмотр сообщений', wide: true,
              subtitle: `${(r.messages || []).length} получател(ям) · ${sel.size ? 'выбранное' : 'всё к отправке'}`,
              body: (r.messages || []).length ? html`${r.messages.map(msg => html`<div class="panel">
                  <h3 class="panel-title">⚖ ${msg.service_name}
                    <span class="badge info">${(msg.channels || []).join(', ') || 'каналы не заполнены'}</span></h3>
                  ${msg.problems && msg.problems.length
                    ? html`<p class="hint" style="color:var(--danger);margin:0 0 8px">${msg.problems.join('; ')}</p>` : nothing}
                  <pre style="white-space:pre-wrap;font:inherit;margin:0">${msg.message}</pre></div>`)}`
                : html`<div class="empty">Отправлять нечего</div>`,
              footer: html`<button class="btn btn-ghost" data-cancel>Закрыть</button>`,
              onMount(mm) { mm.querySelector('[data-cancel]').onclick = () => { closeModal(); draw(); }; },
            });
          } catch (e) { toast(e.message, 'err'); }
        };
        $$('[data-msg]', m).forEach(b => b.onclick = () => {
          const row = (d.dispatches || []).find(x => x.id === Number(b.dataset.msg));
          if (!row) return;
          openModal({ title: 'Отправленное сообщение', subtitle: `${row.recipient_name} · ${row.channel_title} · ${row.target}`,
            body: html`<pre style="white-space:pre-wrap;font:inherit;margin:0">${row.message}</pre>
              ${row.error ? html`<p class="hint" style="color:var(--danger)">Ошибка: ${row.error}</p>` : nothing}`,
            footer: html`<button class="btn btn-ghost" data-cancel>Закрыть</button>`,
            onMount(mm) { mm.querySelector('[data-cancel]').onclick = () => { closeModal(); draw(); }; } });
        });
        const csv = $('#df-csv', m);
        if (csv) csv.onclick = () => downloadBlob(
          `/api/notify/dispatches/export.csv?domain=night`, `otpravki-${d.report.date}.csv`);
        $$('[data-retry]', m).forEach(b => b.onclick = async () => {
          try {
            const r = await api(`/api/notify/dispatches/${b.dataset.retry}/resend`, { method: 'POST', timeout: 300000 });
            toast(r.dispatch.status === 'sent' ? 'Доставлено при повторе' : `Повтор не удался: ${r.dispatch.error}`,
              r.dispatch.status === 'sent' ? 'ok' : 'err');
            draw();
          } catch (e) { toast(e.message, 'err'); }
        });
      },
    });
  };
  await draw();
}
