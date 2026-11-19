/* ══════════════════════════════════════════════════════════════════════
   РАЗДЕЛ «ЭЛЕКТРОКАРЫ» — парк, операции (Взял / Передать / Вернул / Выдать),
   закрепление, статусы, история. Справочник парка и мест стоянки — экран Настроек
   (cars_dict.js). Модуль на lit-html (ADR-0013, раздел 7): разметка — шаблоны,
   вставки экранируются сами. Общие для раздела и ночного обхода куски — места стоянки,
   выбор и миниатюры фото — экспортируются отсюда.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

import { can, poll, registerModule } from '../app.js';
import {
  $, api, closeModal, confirmDialog, dateRu, hhmm, mediaHint, multipartApi, openModal, state, toast,
} from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { checkField } from '../ui/form.js';
import { loadMe } from './me.js';
import { settingsOpen } from './settings.js';

/* бейдж статуса кара (используется и в «Моих отметках», и в ночном обходе) */
export const CAR_BADGE = { free: 'ok', busy: 'warn', charging: 'info', maintenance: 'danger', disabled: 'muted' };

export const carsState = { data: null, meta: null, locations: [], filter: 'all', q: '', error: '' };

/* dateRu() из app.js рассчитан на «YYYY-MM-DD»; для datetime берём только дату */
const dRuCar = iso => (iso ? dateRu(String(iso).slice(0, 10)) : '');

/* ─────────────────────────── раздел ─────────────────────────── */
registerModule({ views: { cars: loadCars } });

async function loadCars() {
  paintCars();
  await fetchCars();
  poll('cars', () => { if (state.view === 'cars') fetchCars(true); });
}

const paintCars = () => render(carsPage(), mount($('#view-cars')));

async function fetchCars(silent) {
  try {
    const [data, meta] = await Promise.all([
      api('/api/cars', { silent: !!silent }),
      carsState.meta ? Promise.resolve(carsState.meta) : api('/api/cars/meta', { silent: true }),
    ]);
    carsState.data = data;
    carsState.meta = meta;
    carsState.error = '';
    await ensureCarLocations();
  } catch (e) {
    carsState.error = e.message;
  }
  paintCars();
}

function carFilterSeg() {
  const counts = { all: carsState.data.cars.length };
  carsState.data.cars.forEach(c => { counts[c.status] = (counts[c.status] || 0) + 1; });
  const items = [['all', 'Все'], ['free', 'Свободные'], ['busy', 'Занятые'],
                 ['charging', 'На зарядке'], ['maintenance', 'Обслуживание']];
  return items.filter(([k]) => k === 'all' || counts[k]).map(([k, t]) =>
    html`<button data-f=${k} class=${carsState.filter === k ? 'active' : ''}
      @click=${() => { carsState.filter = k; paintCars(); }}>${t} <b>${counts[k] || 0}</b></button>`);
}

const carsPage = () => {
  const meta = carsState.meta || { can_manage: false, can_edit_park: false };
  return html`
    <div class="page-head">
      <div><h2>Электрокары</h2><div class="sub">Парк, держатели, заряд и состояние · история не редактируется</div></div>
      <div class="spacer"></div>
      <button class="btn btn-sm" id="cars-refresh" @click=${() => fetchCars()}>Обновить</button>
      <button class=${`btn btn-sm btn-ghost${can('settings.view') ? '' : ' hidden'}`} id="cars-locations"
        title="Места стоянки — Настройки → Электрокары" @click=${() => settingsOpen('cars')}>Места ↗</button>
      <button class=${`btn btn-sm btn-primary${meta.can_manage ? '' : ' hidden'}`} id="cars-add"
        title="Парк — Настройки → Электрокары" @click=${() => settingsOpen('cars')}>+ Кар ↗</button>
    </div>
    <div class="toolbar">
      <div class="seg" id="cars-filter">${carsState.data ? carFilterSeg() : nothing}</div>
      <input type="search" id="cars-q" placeholder="Поиск: номер, место, кто держит…" style="max-width:280px"
        @input=${e => { carsState.q = e.target.value.trim().toLowerCase(); paintCars(); }}>
    </div>
    <div id="cars-body">${carsBody()}</div>`;
};

function carsBody() {
  const d = carsState.data;
  if (carsState.error && !d) {
    return html`<div class="panel"><h3 class="panel-title">Парк не загрузился</h3>
      <p style="color:var(--danger);font-weight:600">${carsState.error}</p>
      <p class="hint">Проверьте связь и нажмите «Обновить». Состояние каров также видно
      в разделе «Ночной отчёт» → шаг «Проверка электрокаров».</p></div>`;
  }
  if (!d) return html`<div class="empty">Загрузка…</div>`;
  const meta = carsState.meta || { can_manage: false, can_edit_park: false };
  const me = d.me || {};
  const list = d.cars.filter(c => {
    if (carsState.filter !== 'all' && c.status !== carsState.filter) return false;
    if (!carsState.q) return true;
    const hay = `${c.number} ${c.location} ${c.holder_name} ${c.assigned_name} ${c.note}`.toLowerCase();
    return hay.includes(carsState.q);
  });
  const stats = {
    free: d.cars.filter(c => c.status === 'free').length,
    busy: d.cars.filter(c => c.status === 'busy').length,
    charging: d.cars.filter(c => c.status === 'charging').length,
    bad: d.cars.filter(c => c.condition === 'bad' || c.trash || !c.clean).length,
  };
  const myCar = d.cars.find(c => c.id === me.held);
  const refresh = () => fetchCars(true);
  const byId = id => d.cars.find(c => c.id === Number(id));
  /* одна кнопка операции: data-act / data-id нужны сценариям и тестам */
  const act = (car, kind, label, cls, title) => html`<button class=${`btn btn-sm ${cls}`} data-act=${kind} data-id=${car.id}
    title=${title || nothing} @click=${() => runAct(byId(car.id), kind, refresh)}>${label}</button>`;

  const row = c => {
    const mine = c.id === me.held;
    const assignedToMe = c.id === me.assigned;
    /* Кнопки операций не существуют одновременно:
       свободный кар — «Взять»/«Выдать»; мой кар — «Вернул»/«Передать»; чужой занятый —
       операции держателя скрыты, менеджеру (cars.issue) доступны возврат/передача
       от имени держателя. Права: cars.use — свои операции, cars.issue — выдача и т.п. */
    const takeable = c.status === 'free' || c.status === 'charging';
    const heldBySomeone = c.status === 'busy';
    const acts = [];
    if (meta.can_use && !mine && takeable) acts.push(act(c, 'take', 'Взять', 'btn-accent'));
    if (meta.can_use && mine) {
      acts.push(act(c, 'return', 'Вернул', ''));
      acts.push(act(c, 'handover', 'Передать', 'btn-ghost'));
    } else if (meta.can_issue && heldBySomeone) {
      acts.push(act(c, 'return', 'Вернул', '', 'Оформить возврат от имени держателя'));
      acts.push(act(c, 'handover', 'Передать', 'btn-ghost', 'Передать от имени держателя'));
    }
    if (meta.can_issue && !mine && takeable) acts.push(act(c, 'give', 'Выдать', 'btn-ghost'));
    if (meta.can_issue) {
      acts.push(act(c, 'assign', 'Закрепить', 'btn-ghost', 'Рекомендательное закрепление'));
      acts.push(act(c, 'status', 'Статус', 'btn-ghost'));
    }
    acts.push(act(c, 'history', 'История', 'btn-ghost'));
    if (meta.can_edit_park) acts.push(act(c, 'edit', 'Карточка', 'btn-ghost'));
    const flags = [
      c.canopy ? nothing : html`<span class="badge warn">нет тента</span>`,
      c.condition === 'bad' ? html`<span class="badge danger">неисправен</span>` : nothing,
      c.trash ? html`<span class="badge warn">в салоне вещи</span>` : nothing,
      c.clean ? nothing : html`<span class="badge warn">не убран</span>`,
      c.on_charge && c.status !== 'charging' ? html`<span class="badge info">на зарядке</span>` : nothing,
    ];
    return html`<tr class=${mine ? 'row-mine' : ''}>
      <td class="who" data-label="Кар"><b>№${c.number}</b>
        ${mine ? html`<span class="badge ok">у вас</span>` : nothing}${assignedToMe && !mine ? html`<span class="badge info">закреплён за вами</span>` : nothing}
        ${c.active ? nothing : html`<span class="badge muted">отключён</span>`}
        <small>${flags}</small></td>
      <td data-label="Статус"><span class=${`badge ${CAR_BADGE[c.status] || 'muted'}`}>${c.status_title}</span></td>
      <td data-label="Место">${c.location || '—'}</td>
      <td data-label="Заряд">${c.charge_title || '—'}</td>
      <td data-label="Держит">${c.holder_name || html`<span class="muted">—</span>`}</td>
      <td data-label="Закреплён">${c.assigned_name || html`<span class="muted">—</span>`}</td>
      <td data-label="Ключ">${c.has_key ? 'в карточке' : html`<span class="muted">нет</span>`}</td>
      <td data-label="Проверен" class="num">${c.last_checked_at ? hhmm(c.last_checked_at) : '—'}</td>
      <td data-label="Действия"><div class="row-actions">${acts}</div></td>
    </tr>`;
  };
  const rec = me.free_recommended && !me.held ? d.cars.find(c => c.id === me.free_recommended) : null;
  return html`
    <div class="stat-grid">
      <div class="stat accent"><div class="k">Всего в парке</div><div class="v">${d.cars.length}</div></div>
      <div class="stat"><div class="k">Свободны</div><div class="v">${stats.free}</div></div>
      <div class="stat warn"><div class="k">Заняты</div><div class="v">${stats.busy}</div></div>
      <div class="stat info"><div class="k">На зарядке</div><div class="v">${stats.charging}</div></div>
      <div class="stat danger"><div class="k">С замечаниями</div><div class="v">${stats.bad}</div></div>
    </div>
    ${myCar ? html`<div class="panel"><h3 class="panel-title">Ваш кар</h3>
      <div class="rule-row"><div>
        <div class="lbl">№${myCar.number} <span class=${`badge ${CAR_BADGE[myCar.status] || 'muted'}`}>${myCar.status_title}</span></div>
        <div class="desc">место: ${myCar.location || '—'} · заряд: ${myCar.charge_title || '—'}${myCar.has_key ? ' · ключ у вас' : ''}</div>
      </div><div class="rule-input" style="display:flex;gap:8px;flex-wrap:wrap">
        ${act(myCar, 'return', 'Вернул', '')}${act(myCar, 'handover', 'Передать', 'btn-ghost')}
      </div></div></div>` : nothing}
    ${rec ? html`<div class="panel"><h3 class="panel-title">Рекомендуемый свободный кар</h3>
      <div class="rule-row"><div>
        <div class="lbl">№${rec.number} · ${rec.location || 'место не указано'}</div>
        <div class="desc">Взять можно и кар на зарядке. Если он закреплён за другим — система спросит подтверждение (закрепление рекомендательное).</div>
      </div><div class="rule-input">${act(rec, 'take', `Взять №${rec.number}`, 'btn-accent')}</div></div></div>` : nothing}
    <div class="table-wrap" tabindex="0">
      <table class="data responsive">
        <thead><tr><th>Кар</th><th>Статус</th><th>Место</th><th>Заряд</th><th>Держит</th>
          <th>Закреплён</th><th>Ключ</th><th>Проверен</th><th>Действия</th></tr></thead>
        <tbody>${list.length ? list.map(row) : html`<tr><td colspan="9" class="empty">Нет каров по фильтру</td></tr>`}</tbody>
      </table>
    </div>
    <p class="hint">Правила: один сотрудник — один кар; вернуть может тот, кто брал (внешнего — любой);
    замечания при возврате автоматически переводят кар в «на обслуживании», снять — менеджер или администратор.
    Время всех операций — по часовому поясу объекта${state.appTz ? ` (${state.appTz})` : ''}.</p>`;
}

async function runAct(car, kind, refresh) {
  if (!car) return toast('Кар не найден — обновите список', 'warn');
  try {
    if (kind === 'take') await carTake(car, refresh);
    else if (kind === 'return') carReturnModal(car, refresh);
    else if (kind === 'handover') carHandoverModal(car, refresh);
    else if (kind === 'give') carGiveModal(car, refresh);
    else if (kind === 'assign') carAssignModal(car, refresh);
    else if (kind === 'status') carStatusModal(car, refresh);
    else if (kind === 'history') await carHistoryModal(car);
    else if (kind === 'edit') carEditModal(car, refresh);
  } catch (e) { toast(e.message || String(e), 'err'); }
}

/* ─────────────────── взять кар (с подтверждением перехвата) ─────────────────── */
async function carTake(car, after, ack = false) {
  try {
    await api(`/api/cars/${car.id}/take`, { method: 'POST', body: { ack_assigned: ack } });
    toast(`Кар №${car.number} взят${car.has_key ? '' : ' · ключа в карточке нет'}`, 'ok');
    if (after) await after();
  } catch (e) {
    if (e.payload?.interception) {
      confirmDialog('Кар закреплён за другим', e.payload.message,
        () => carTake(car, after, true), 'Всё равно взять', false);
    } else throw e;
  }
}

/* ─────────────────── общий блок «кто» (сотрудник или внешний) ─────────────────── */
function personField(prefix) {
  const emps = (state.employees || []).filter(e => !e.deleted);
  return html`
    <label class="field"><span>Кому / кто (сотрудник из списка)</span>
      <select id=${`${prefix}-emp`}><option value="">— не выбран —</option>${emps.map(e =>
        html`<option value=${e.id}>${e.full_name} · ${e.position || ''}</option>`)}</select></label>
    <label class="field"><span>…или ФИО внешнего сотрудника (если нет в списке)</span>
      <input type="text" id=${`${prefix}-name`} placeholder="Например: Петров П.П. (клининг)" maxlength="120"></label>
    ${emps.length ? nothing : html`<p class="hint">Список сотрудников доступен менеджерам; сотрудник может указать ФИО текстом.</p>`}`;
}

function personFieldValue(prefix) {
  const id = Number($(`#${prefix}-emp`)?.value || 0);
  const name = ($(`#${prefix}-name`)?.value || '').trim();
  return { employee_id: id || null, name };
}

/* Справочник мест стоянки нужен не только разделу «Электрокары», но и ночному
   обходу (место там — выпадающий список, как в окне возврата). Грузим один раз. */
export async function ensureCarLocations() {
  if (!carsState.locations.length) {
    try { carsState.locations = (await api('/api/cars/locations', { silent: true })).locations || []; }
    catch { carsState.locations = []; }
  }
  return carsState.locations;
}

export function locationOptions(selected) {
  const names = [...new Set([...(carsState.locations || []).filter(l => l.active).map(l => l.name),
                             ...(selected ? [selected] : [])].filter(Boolean))];
  return names.map(n => html`<option value=${n} ?selected=${n === selected}>${n}</option>`);
}

export const CHARGE_OPTS = [['full', 'полный'], ['half', 'половина'], ['empty', 'разряжен']];

/* ─────────── выбор фото: съёмка камерой смартфона или из галереи ───────────
   Блок общий для окна возврата кара и отметки ночного обхода: на смартфоне «Снять на камеру» открывает
   камеру сразу со съёмкой (capture=environment), «Из галереи» — готовый снимок.
   bindPhotoPick() возвращает функцию-геттер выбранного файла для FormData. */
/* Выбор медиа: фото и видео (этап 2 ночного отчёта v2). Видео снимается
   camcorder-режимом камеры, лимиты и сроки хранения — из настроек объекта. */
export function photoPick(prefix) {
  const lim = state.mediaLimits || {};
  return html`<div class="field" style="margin-top:12px"><span>Фото или видео (необязательно, ${mediaHint()}, хранится оригинал)</span>
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
      <label class="btn btn-sm">📷 Снять фото
        <input type="file" id=${`${prefix}-cam`} accept="image/*" capture="environment" hidden></label>
      <label class="btn btn-sm btn-ghost">Фото из галереи
        <input type="file" id=${`${prefix}-file`} accept="image/*" hidden></label>
      <label class="btn btn-sm">🎥 Снять видео
        <input type="file" id=${`${prefix}-vcam`} accept="video/*" capture="camcorder" hidden></label>
      <label class="btn btn-sm btn-ghost">Видео из галереи
        <input type="file" id=${`${prefix}-vfile`} accept="video/*" hidden></label>
      <span class="hint" id=${`${prefix}-file-name`} style="margin:0">файл не выбран</span>
    </div>
    <div class="hint" style="margin-top:4px">На смартфоне «Снять фото» и «Снять видео» открывают камеру
      сразу в нужном режиме; «из галереи» — выбор готового файла. Хранение: фото
      ${lim.photo_retention_days || 180} дн., видео ${lim.video_retention_days || 180} дн.</div></div>`;
}

export function bindPhotoPick(m, prefix) {
  let pendingPhoto = null;
  const showName = () => {
    const el = m.querySelector(`#${prefix}-file-name`);
    if (el) el.textContent = pendingPhoto
      ? `${pendingPhoto.name || 'снимок камеры'} (${Math.round((pendingPhoto.size || 0) / 1024)} КБ)`
      : 'файл не выбран';
  };
  [`#${prefix}-cam`, `#${prefix}-file`, `#${prefix}-vcam`, `#${prefix}-vfile`].forEach(sel => {
    const inp = m.querySelector(sel);
    if (inp) inp.onchange = () => { pendingPhoto = inp.files?.[0] || null; showName(); };
  });
  return () => pendingPhoto;
}

/* ─────────────────── возврат кара (multipart + фото) ─────────────────── */
export function carReturnModal(car, after) {
  openModal({
    title: `Возврат кара №${car.number}`,
    subtitle: `Сейчас: ${car.status_title}${car.holder_name ? ' · держит ' + car.holder_name : ''}`,
    wide: true,
    body: html`
      <div class="grid-2">
        <label class="field"><span>Место, где оставили</span>
          <select id="cr-location">${locationOptions(car.location)}</select></label>
        <label class="field"><span>Заряд</span>
          <select id="cr-charge">${CHARGE_OPTS.map(([v, t]) =>
            html`<option value=${v} ?selected=${v === car.charge}>${t}</option>`)}</select></label>
      </div>
      ${can('cars.issue') ? personField('cr') : nothing}
      <div class="opt-group-title">Состояние при возврате</div>
      <div class="check-list" id="cr-state" style="max-height:none">
        ${checkField('cr-ok', 'Технически исправен', car.condition !== 'bad')}
        ${checkField('cr-clean', 'Чистый', car.clean)}
        ${checkField('cr-things', 'В салоне вещи', car.trash)}
        ${checkField('cr-canopy', 'Тент', car.canopy)}
        ${checkField('cr-oncharge', 'Заряжается', car.on_charge)}
      </div>
      ${car.has_key ? html`<label class="chk" style="margin-top:8px"><input type="checkbox" id="cr-key" checked> Ключ сдал</label>` : nothing}
      <label class="field" style="margin-top:12px"><span>Комментарий (что случилось, куда поставили)</span>
        <textarea id="cr-comment" rows="2" maxlength="255" placeholder="Например: оставил у главного входа, левое колесо спущено" .value=${car.note || ''}></textarea></label>
      ${photoPick('cr')}
      <p class="hint">Снятый с галочки «Технически исправен», а также «В салоне вещи» или не «Чистый»
      автоматически переводят кар в статус «на обслуживании». Оставить на зарядке можно кар
      с любым зарядом, включая полный.</p>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Отметить возврат</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      /* фото: съёмка камерой смартфона (capture) или выбор из галереи */
      const pickPhoto = bindPhotoPick(m, 'cr');
      m.querySelector('[data-ok]').onclick = async () => {
        const charge = $('#cr-charge').value;
        const onCharge = $('#cr-oncharge').checked;
        const fd = new FormData();
        // «кто вернул» за другого — только с правом выдачи
        const person = can('cars.issue') ? personFieldValue('cr') : { employee_id: null, name: '' };
        if (person.employee_id) fd.append('by_employee_id', String(person.employee_id));
        if (person.name) fd.append('by_name', person.name);
        fd.append('location', $('#cr-location').value || '');
        fd.append('charge', charge);
        fd.append('canopy', $('#cr-canopy').checked ? 'true' : 'false');
        fd.append('condition', $('#cr-ok').checked ? 'ok' : 'bad');
        fd.append('trash', $('#cr-things').checked ? 'true' : 'false');
        fd.append('clean', $('#cr-clean').checked ? 'true' : 'false');
        fd.append('on_charge', onCharge ? 'true' : 'false');
        if ($('#cr-key')) fd.append('key_returned', $('#cr-key').checked ? 'true' : 'false');
        fd.append('comment', $('#cr-comment').value.trim());
        const pendingPhoto = pickPhoto();
        if (pendingPhoto) fd.append('file', pendingPhoto, pendingPhoto.name || 'photo.jpg');
        try {
          await multipartApi(`/api/cars/${car.id}/return`, fd);
          closeModal();
          toast(`Кар №${car.number} возвращён`, 'ok');
          if (after) await after();
          if (typeof loadMe === 'function' && state.view === 'me') loadMe();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ─────────────────── передача другому (с согласия держателя) ─────────────────── */
export function carHandoverModal(car, after) {
  openModal({
    title: `Передать кар №${car.number}`,
    subtitle: car.holder_name ? `Держит: ${car.holder_name}` : 'Кар никто не держит',
    body: html`${personField('ch')}
      ${checkField('ch-key', 'Передаю с ключом', car.has_key)}
      <label class="field" style="margin-top:10px"><span>Комментарий</span>
        <input type="text" id="ch-comment" maxlength="255" placeholder="Например: передал на время обеда"></label>
      <p class="hint">Передача фиксируется в истории отдельно от возврата: после неё кар
      возвращает тот, кто принял (или супервайзер).</p>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Передать</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        const p = personFieldValue('ch');
        if (!p.employee_id && !p.name) return toast('Выберите сотрудника или укажите ФИО', 'warn');
        try {
          await api(`/api/cars/${car.id}/handover`, { method: 'POST',
            body: { ...p, with_key: $('#ch-key').checked, comment: $('#ch-comment').value.trim() } });
          closeModal(); toast(`Кар №${car.number} передан`, 'ok');
          if (after) await after();
          if (typeof loadMe === 'function' && state.view === 'me') loadMe();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ─────────────────── выдача (менеджмент) ─────────────────── */
function carGiveModal(car, after) {
  openModal({
    title: `Выдать кар №${car.number}`,
    subtitle: 'Операция менеджмента: кар закрепляется за сотрудником без его действия',
    body: html`${personField('cg')}
      ${checkField('cg-key', 'Выдаю с ключом', true)}`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Выдать</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        const p = personFieldValue('cg');
        if (!p.employee_id && !p.name) return toast('Выберите сотрудника или укажите ФИО', 'warn');
        try {
          await api(`/api/cars/${car.id}/give`, { method: 'POST', body: { ...p, with_key: $('#cg-key').checked } });
          closeModal(); toast(`Кар №${car.number} выдан`, 'ok');
          if (after) await after();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ─────────────────── закрепление / статус / карточка ─────────────────── */
function carAssignModal(car, after) {
  const emps = (state.employees || []).filter(e => !e.deleted);
  openModal({
    title: `Закрепить кар №${car.number}`,
    subtitle: 'Закрепление рекомендательное: взять кар может любой, система лишь предупредит',
    body: html`<label class="field"><span>Сотрудник</span>
        <select id="ca-emp"><option value="">— не закреплять —</option>
          ${emps.map(e => html`<option value=${e.id} ?selected=${e.id === car.assigned_to}>${e.full_name}</option>`)}
        </select></label>
      ${emps.length ? nothing : html`<p class="hint">Список сотрудников доступен после загрузки раздела «Сотрудники» (менеджеры).</p>`}
      <p class="hint">Сейчас закреплён: ${car.assigned_name || 'ни за кем'}.</p>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Сохранить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        try {
          await api(`/api/cars/${car.id}/assign`, { method: 'POST',
            body: { employee_id: Number($('#ca-emp').value) || null } });
          closeModal(); toast('Закрепление сохранено', 'ok');
          if (after) await after();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

function carStatusModal(car, after) {
  const statuses = (carsState.meta?.statuses || []);
  openModal({
    title: `Статус кара №${car.number}`,
    subtitle: `Сейчас: ${car.status_title}`,
    body: html`<label class="field"><span>Новый статус</span>
        <select id="cs-status">${statuses.map(s =>
          html`<option value=${s.code} ?selected=${s.code === car.status}>${s.title}</option>`)}
        </select></label>
      <label class="field"><span>Причина / примечание</span>
        <input type="text" id="cs-note" maxlength="255" placeholder="Например: снят с обслуживания после ремонта"></label>
      <p class="hint">Правила сервера: «занят» без держателя поставить нельзя; с «занят» — только через возврат;
      снять с обслуживания может менеджер или администратор.</p>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Изменить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        try {
          await api(`/api/cars/${car.id}/status`, { method: 'POST',
            body: { status: $('#cs-status').value, note: $('#cs-note').value.trim() } });
          closeModal(); toast('Статус изменён', 'ok');
          if (after) await after();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

export function carEditModal(car, after) {
  openModal({
    title: `Карточка кара №${car.number}`,
    body: html`<label class="field"><span>Номер</span><input type="text" id="ce-number" .value=${car.number} maxlength="40"></label>
      <label class="field"><span>Место стоянки</span><select id="ce-location">${locationOptions(car.location)}</select></label>
      <label class="field"><span>Примечание</span><input type="text" id="ce-note" .value=${car.note || ''} maxlength="255"></label>
      ${checkField('ce-active', 'Кар в работе (виден сотрудникам)', car.active)}
      <p class="hint">Отключённый кар виден только менеджменту; история операций сохраняется.</p>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Сохранить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        try {
          await api(`/api/cars/${car.id}`, { method: 'PUT', body: {
            number: $('#ce-number').value.trim(), location: $('#ce-location').value,
            note: $('#ce-note').value.trim(), active: $('#ce-active').checked } });
          closeModal(); toast('Карточка обновлена', 'ok');
          if (after) await after();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

export function carAddModal(after) {
  openModal({
    title: 'Новый кар',
    body: html`<label class="field"><span>Номер (обязательно)</span>
        <input type="text" id="ca-number" maxlength="40" placeholder="Например: 04"></label>
      <p class="hint">Место стоянки и состояние указываются при возврате и в карточке кара —
        новый кар создаётся свободным без места.</p>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Добавить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        const number = $('#ca-number').value.trim();
        if (!number) return toast('Укажите номер кара', 'warn');
        try {
          await api('/api/cars', { method: 'POST', body: { number } });
          closeModal(); toast(`Кар №${number} добавлен`, 'ok');
          if (after) after(); else fetchCars();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ─────────────────── история кара (только чтение) ─────────────────── */
async function carHistoryModal(car) {
  const data = await api(`/api/cars/${car.id}/history?limit=200`);
  const history = data.history || [];
  openModal({
    title: `История кара №${car.number}`,
    subtitle: `${history.length} операций · записи не редактируются и не удаляются`,
    wide: true,
    body: html`<div class="history">${history.length ? history.map(h => html`
    <div class="history-item">
      <div class="ts">${h.ts ? dRuCar(h.ts) + ' ' + hhmm(h.ts) : '—'}</div>
      <div class="what"><b>${h.action_title || h.action}</b>
        ${h.person ? ` · ${h.person}` : ''}${h.location ? ` · ${h.location}` : ''}
        ${h.with_key === null || h.with_key === undefined ? '' : (h.with_key ? ' · с ключом' : ' · без ключа')}
        <small class="muted">${h.actor_name || ''}</small>
        ${h.photos?.length ? html`<div class="thumbs">${h.photos.map(p => photoThumb(p))}</div>` : nothing}
        ${h.details?.comment ? html`<div class="muted" style="font-size:12.5px">${h.details.comment}</div>` : nothing}
      </div>
    </div>`) : html`<div class="empty">Операций пока не было</div>`}</div>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Закрыть</button>`,
    onMount(m) { m.querySelector('[data-cancel]').onclick = closeModal; },
  });
}

/* ─────────────────── фото: превью + просмотр + удаление ─────────────────── */
/* Миниатюра медиа: фото — картинкой, видео — первым кадром с кнопкой ▶.
   Клик открывает оригинал в новой вкладке (видео отдаётся с Range, плеер мотает).
   after — что сделать после удаления (обновить окно); без него удаление не показывает крестика-обновления. */
export function photoThumb(p, after) {
  const isVideo = p.media_type === 'video';
  const kind = isVideo ? 'видео' : 'фото';
  if (!p.url) return html`<span class="badge muted" title="файл удалён по сроку хранения">${kind} недоступно</span>`;
  return html`<a class=${`thumb${isVideo ? ' thumb-video' : ''}`} href=${p.url} target="_blank"
      rel="noopener" title=${p.filename || kind}>${isVideo
    ? html`<video src=${p.url} muted playsinline preload="metadata"></video><span class="thumb-play">▶</span>`
    : html`<img src=${p.url} alt=${p.filename || 'фото'} loading="lazy">`}</a>
    <button class="icon-btn thumb-del" data-photo-del=${p.id} title=${`Удалить ${kind}`}
      @click=${() => confirmDialog('Удалить фото?', 'Файл будет удалён с сервера без возможности восстановления.', async () => {
        try { await api(`/api/photos/${p.id}`, { method: 'DELETE' }); toast('Фото удалено', 'ok'); if (after) after(); }
        catch (e) { toast(e.message, 'err'); }
      }, 'Удалить')}>✕</button>`;
}
