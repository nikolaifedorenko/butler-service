/* ══════════════════════════════════════════════════════════════════════
   РАЗДЕЛ «ЭЛЕКТРОКАРЫ» — парк, операции (Взял / Передать / Вернул / Выдать),
   закрепление, статусы, история, справочник мест стоянки.
   Отдельный файл: раздел добавлен позже основного интерфейса.
   Использует хелперы app.js: $ $$ esc api multipartApi openModal closeModal
   confirmDialog toast downloadBlob hours hhmm dateRu poll loading state.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

/* бейдж статуса кара (используется и в «Моих отметках», и в ночном обходе) */
const CAR_BADGE = { free: 'ok', busy: 'warn', charging: 'info', maintenance: 'danger', disabled: 'muted' };

const carsState = { data: null, meta: null, locations: [], filter: 'all', q: '' };

/* dateRu() из app.js рассчитан на «YYYY-MM-DD»; для datetime берём только дату */
const dRuCar = iso => (iso ? dateRu(String(iso).slice(0, 10)) : '');

/* ─────────────────────────── раздел ─────────────────────────── */
async function loadCars() {
  $('#view-cars').innerHTML = `
    <div class="page-head">
      <div><h2>Электрокары</h2><div class="sub">Парк, держатели, заряд и состояние · история не редактируется</div></div>
      <div class="spacer"></div>
      <button class="btn btn-sm" id="cars-refresh">Обновить</button>
      <button class="btn btn-sm btn-ghost hidden" id="cars-locations" title="Места стоянки — Настройки → Электрокары">Места ↗</button>
      <button class="btn btn-sm btn-primary hidden" id="cars-add" title="Парк — Настройки → Электрокары">+ Кар ↗</button>
    </div>
    <div class="toolbar">
      <div class="seg" id="cars-filter"></div>
      <input type="search" id="cars-q" placeholder="Поиск: номер, место, кто держит…" style="max-width:280px">
    </div>
    <div id="cars-body"><div class="empty">Загрузка…</div></div>`;

  $('#cars-refresh').onclick = () => fetchCars();
  /* 19.10.2026: справочники парка и мест переехали в «Настройки → Электрокары» —
     кнопки раздела стали deep-link'ами (единственное место правки). */
  $('#cars-locations').onclick = () => settingsOpen('cars');
  $('#cars-add').onclick = () => settingsOpen('cars');
  $('#cars-q').oninput = e => { carsState.q = e.target.value.trim().toLowerCase(); renderCars(); };
  await fetchCars();
  poll('cars', () => { if (state.view === 'cars') fetchCars(true); }, 60000);
}

async function fetchCars(silent) {
  try {
    const [data, meta] = await Promise.all([
      api('/api/cars', { silent: !!silent }),
      carsState.meta ? Promise.resolve(carsState.meta) : api('/api/cars/meta', { silent: true }),
    ]);
    carsState.data = data;
    carsState.meta = meta;
    await ensureCarLocations();
    $('#cars-add')?.classList.toggle('hidden', !meta.can_manage);
    $('#cars-locations')?.classList.toggle('hidden', !can('settings.view'));
    renderCars();
  } catch (e) {
    $('#cars-body').innerHTML = `<div class="panel"><h3 class="panel-title">Парк не загрузился</h3>
      <p style="color:var(--danger);font-weight:600">${esc(e.message)}</p>
      <p class="hint">Проверьте связь и нажмите «Обновить». Состояние каров также видно
      в разделе «Ночной отчёт» → шаг «Проверка электрокаров».</p></div>`;
  }
}

function carFilterSeg() {
  const counts = { all: carsState.data.cars.length };
  carsState.data.cars.forEach(c => { counts[c.status] = (counts[c.status] || 0) + 1; });
  const items = [['all', 'Все'], ['free', 'Свободные'], ['busy', 'Занятые'],
                 ['charging', 'На зарядке'], ['maintenance', 'Обслуживание']];
  return items.filter(([k]) => k === 'all' || counts[k]).map(([k, t]) =>
    `<button data-f="${k}" class="${carsState.filter === k ? 'active' : ''}">${t} <b>${counts[k] || 0}</b></button>`).join('');
}

function renderCars() {
  const d = carsState.data;
  if (!d) return;
  const meta = carsState.meta || { can_manage: false, can_edit_park: false };
  $('#cars-filter').innerHTML = carFilterSeg();
  $$('#cars-filter button').forEach(b => b.onclick = () => { carsState.filter = b.dataset.f; renderCars(); });

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

  const rows = list.map(c => {
    const mine = c.id === me.held;
    const assignedToMe = c.id === me.assigned;
    /* Кнопки операций не существуют одновременно (решение владельца 18.10.2026):
       свободный кар — «Взять»/«Выдать»; мой кар — «Вернул»/«Передать»; чужой занятый —
       операции держателя скрыты, менеджеру (cars.issue) доступны возврат/передача
       от имени держателя. Права: cars.use — свои операции, cars.issue — выдача и т.п. */
    const takeable = c.status === 'free' || c.status === 'charging';
    const heldBySomeone = c.status === 'busy';
    const acts = [];
    if (meta.can_use && !mine && takeable) acts.push(`<button class="btn btn-sm btn-accent" data-act="take" data-id="${c.id}">Взять</button>`);
    if (meta.can_use && mine) {
      acts.push(`<button class="btn btn-sm" data-act="return" data-id="${c.id}">Вернул</button>`);
      acts.push(`<button class="btn btn-sm btn-ghost" data-act="handover" data-id="${c.id}">Передать</button>`);
    } else if (meta.can_issue && heldBySomeone) {
      acts.push(`<button class="btn btn-sm" data-act="return" data-id="${c.id}" title="Оформить возврат от имени держателя">Вернул</button>`);
      acts.push(`<button class="btn btn-sm btn-ghost" data-act="handover" data-id="${c.id}" title="Передать от имени держателя">Передать</button>`);
    }
    if (meta.can_issue && !mine && takeable) {
      acts.push(`<button class="btn btn-sm btn-ghost" data-act="give" data-id="${c.id}">Выдать</button>`);
    }
    if (meta.can_issue) {
      acts.push(`<button class="btn btn-sm btn-ghost" data-act="assign" data-id="${c.id}" title="Рекомендательное закрепление">Закрепить</button>`);
      acts.push(`<button class="btn btn-sm btn-ghost" data-act="status" data-id="${c.id}">Статус</button>`);
    }
    acts.push(`<button class="btn btn-sm btn-ghost" data-act="history" data-id="${c.id}">История</button>`);
    if (meta.can_edit_park) acts.push(`<button class="btn btn-sm btn-ghost" data-act="edit" data-id="${c.id}">Карточка</button>`);

    const flags = [
      c.canopy ? '' : '<span class="badge warn">нет тента</span>',
      c.condition === 'bad' ? '<span class="badge danger">неисправен</span>' : '',
      c.trash ? '<span class="badge warn">в салоне вещи</span>' : '',
      c.clean ? '' : '<span class="badge warn">не убран</span>',
      c.on_charge && c.status !== 'charging' ? '<span class="badge info">на зарядке</span>' : '',
    ].filter(Boolean).join(' ');

    return `<tr class="${mine ? 'row-mine' : ''}">
      <td class="who" data-label="Кар"><b>№${esc(c.number)}</b>
        ${mine ? '<span class="badge ok">у вас</span>' : ''}${assignedToMe && !mine ? '<span class="badge info">закреплён за вами</span>' : ''}
        ${c.active ? '' : '<span class="badge muted">отключён</span>'}
        <small>${flags}</small></td>
      <td data-label="Статус"><span class="badge ${CAR_BADGE[c.status] || 'muted'}">${esc(c.status_title)}</span></td>
      <td data-label="Место">${esc(c.location || '—')}</td>
      <td data-label="Заряд">${esc(c.charge_title || '—')}</td>
      <td data-label="Держит">${c.holder_name ? esc(c.holder_name) : '<span class="muted">—</span>'}</td>
      <td data-label="Закреплён">${c.assigned_name ? esc(c.assigned_name) : '<span class="muted">—</span>'}</td>
      <td data-label="Ключ">${c.has_key ? 'в карточке' : '<span class="muted">нет</span>'}</td>
      <td data-label="Проверен" class="num">${c.last_checked_at ? esc(hhmm(c.last_checked_at)) : '—'}</td>
      <td data-label="Действия"><div class="row-actions">${acts.join('')}</div></td>
    </tr>`;
  }).join('');

  $('#cars-body').innerHTML = `
    <div class="stat-grid">
      <div class="stat accent"><div class="k">Всего в парке</div><div class="v">${d.cars.length}</div></div>
      <div class="stat"><div class="k">Свободны</div><div class="v">${stats.free}</div></div>
      <div class="stat warn"><div class="k">Заняты</div><div class="v">${stats.busy}</div></div>
      <div class="stat info"><div class="k">На зарядке</div><div class="v">${stats.charging}</div></div>
      <div class="stat danger"><div class="k">С замечаниями</div><div class="v">${stats.bad}</div></div>
    </div>
    ${myCar ? `<div class="panel"><h3 class="panel-title">Ваш кар</h3>
      <div class="rule-row"><div>
        <div class="lbl">№${esc(myCar.number)} <span class="badge ${CAR_BADGE[myCar.status] || 'muted'}">${esc(myCar.status_title)}</span></div>
        <div class="desc">место: ${esc(myCar.location || '—')} · заряд: ${esc(myCar.charge_title || '—')}${myCar.has_key ? ' · ключ у вас' : ''}</div>
      </div><div class="rule-input" style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn btn-sm" data-act="return" data-id="${myCar.id}">Вернул</button>
        <button class="btn btn-sm btn-ghost" data-act="handover" data-id="${myCar.id}">Передать</button>
      </div></div></div>` : ''}
    ${me.free_recommended && !me.held ? (() => {
      const rec = d.cars.find(c => c.id === me.free_recommended);
      return rec ? `<div class="panel"><h3 class="panel-title">Рекомендуемый свободный кар</h3>
        <div class="rule-row"><div>
          <div class="lbl">№${esc(rec.number)} · ${esc(rec.location || 'место не указано')}</div>
          <div class="desc">Взять можно и кар на зарядке. Если он закреплён за другим — система спросит подтверждение (закрепление рекомендательное).</div>
        </div><div class="rule-input"><button class="btn btn-sm btn-accent" data-act="take" data-id="${rec.id}">Взять №${esc(rec.number)}</button></div></div></div>` : '';
    })() : ''}
    <div class="table-wrap">
      <table class="data responsive">
        <thead><tr><th>Кар</th><th>Статус</th><th>Место</th><th>Заряд</th><th>Держит</th>
          <th>Закреплён</th><th>Ключ</th><th>Проверен</th><th>Действия</th></tr></thead>
        <tbody>${rows || `<tr><td colspan="9" class="empty">Нет каров по фильтру</td></tr>`}</tbody>
      </table>
    </div>
    <p class="hint">Правила: один сотрудник — один кар; вернуть может тот, кто брал (внешнего — любой);
    замечания при возврате автоматически переводят кар в «на обслуживании», снять — менеджер или администратор.
    Время всех операций — часовому поясу объекта (${esc(APP_TZ_LABEL)}).</p>`;

  bindCarActions($('#cars-body'));
}

const APP_TZ_LABEL = 'Europe/Moscow';

function bindCarActions(root) {
  const byId = id => (carsState.data?.cars || []).find(c => c.id === Number(id));
  $$('[data-act]', root).forEach(b => b.onclick = async () => {
    const car = byId(b.dataset.id);
    if (!car) return toast('Кар не найден — обновите список', 'warn');
    const act = b.dataset.act;
    const refresh = () => fetchCars(true);
    try {
      if (act === 'take') await carTake(car, refresh);
      else if (act === 'return') carReturnModal(car, refresh);
      else if (act === 'handover') carHandoverModal(car, refresh);
      else if (act === 'give') carGiveModal(car, refresh);
      else if (act === 'assign') carAssignModal(car, refresh);
      else if (act === 'status') carStatusModal(car, refresh);
      else if (act === 'history') await carHistoryModal(car);
      else if (act === 'edit') carEditModal(car, refresh);
    } catch (e) { toast(e.message || String(e), 'err'); }
  });
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
function personFieldHtml(prefix) {
  const emps = (state.employees || []).filter(e => !e.deleted);
  const opts = emps.map(e => `<option value="${e.id}">${esc(e.full_name)} · ${esc(e.position || '')}</option>`).join('');
  return `
    <label class="field"><span>Кому / кто (сотрудник из списка)</span>
      <select id="${prefix}-emp"><option value="">— не выбран —</option>${opts}</select></label>
    <label class="field"><span>…или ФИО внешнего сотрудника (если нет в списке)</span>
      <input type="text" id="${prefix}-name" placeholder="Например: Петров П.П. (клининг)" maxlength="120"></label>
    ${emps.length ? '' : '<p class="hint">Список сотрудников доступен менеджерам; сотрудник может указать ФИО текстом.</p>'}`;
}

function personFieldValue(prefix) {
  const id = Number($(`#${prefix}-emp`)?.value || 0);
  const name = ($(`#${prefix}-name`)?.value || '').trim();
  return { employee_id: id || null, name };
}

/* Справочник мест стоянки нужен не только разделу «Электрокары», но и ночному
   обходу (место там — выпадающий список, как в окне возврата). Грузим один раз. */
async function ensureCarLocations() {
  if (!carsState.locations.length) {
    try { carsState.locations = (await api('/api/cars/locations', { silent: true })).locations || []; }
    catch { carsState.locations = []; }
  }
  return carsState.locations;
}

function locationOptions(selected) {
  const names = [...new Set([...(carsState.locations || []).filter(l => l.active).map(l => l.name),
                             ...(selected ? [selected] : [])].filter(Boolean))];
  return names.map(n => `<option value="${esc(n)}" ${n === selected ? 'selected' : ''}>${esc(n)}</option>`).join('');
}

const CHARGE_OPTS = [['full', 'полный'], ['half', 'половина'], ['empty', 'разряжен']];

/* ─────────── выбор фото: съёмка камерой смартфона или из галереи ───────────
   Блок общий для окна возврата кара и отметки ночного обхода (камера — с
   18.10.2026, в обходе — с 19.10.2026): на смартфоне «Снять на камеру» открывает
   камеру сразу со съёмкой (capture=environment), «Из галереи» — готовый снимок.
   bindPhotoPick() возвращает функцию-геттер выбранного файла для FormData. */
/* Выбор медиа: фото и видео (этап 2 ночного отчёта v2). Видео снимается
   camcorder-режимом камеры, лимиты и сроки хранения — из настроек объекта. */
function photoPickHtml(prefix) {
  const lim = state.mediaLimits || {};
  return `<div class="field" style="margin-top:12px"><span>Фото или видео (необязательно, ${mediaHint()}, хранится оригинал)</span>
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
      <label class="btn btn-sm">📷 Снять фото
        <input type="file" id="${prefix}-cam" accept="image/*" capture="environment" hidden></label>
      <label class="btn btn-sm btn-ghost">Фото из галереи
        <input type="file" id="${prefix}-file" accept="image/*" hidden></label>
      <label class="btn btn-sm">🎥 Снять видео
        <input type="file" id="${prefix}-vcam" accept="video/*" capture="camcorder" hidden></label>
      <label class="btn btn-sm btn-ghost">Видео из галереи
        <input type="file" id="${prefix}-vfile" accept="video/*" hidden></label>
      <span class="hint" id="${prefix}-file-name" style="margin:0">файл не выбран</span>
    </div>
    <div class="hint" style="margin-top:4px">На смартфоне «Снять фото» и «Снять видео» открывают камеру
      сразу в нужном режиме; «из галереи» — выбор готового файла. Хранение: фото
      ${lim.photo_retention_days || 180} дн., видео ${lim.video_retention_days || 180} дн.</div></div>`;
}

function bindPhotoPick(m, prefix) {
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
function carReturnModal(car, after) {
  openModal({
    title: `Возврат кара №${car.number}`,
    subtitle: `Сейчас: ${car.status_title}${car.holder_name ? ' · держит ' + car.holder_name : ''}`,
    wide: true,
    body: `
      <div class="grid-2">
        <label class="field"><span>Место, где оставили</span>
          <select id="cr-location">${locationOptions(car.location)}</select></label>
        <label class="field"><span>Заряд</span>
          <select id="cr-charge">${CHARGE_OPTS.map(([v, t]) =>
            `<option value="${v}" ${v === car.charge ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
      </div>
      ${state.user?.role !== 'employee' ? personFieldHtml('cr') : ''}
      <div class="opt-group-title">Состояние при возврате</div>
      <div class="check-list" id="cr-state" style="max-height:none">
        <label class="chk"><input type="checkbox" id="cr-ok" ${car.condition !== 'bad' ? 'checked' : ''}> Технически исправен</label>
        <label class="chk"><input type="checkbox" id="cr-clean" ${car.clean ? 'checked' : ''}> Чистый</label>
        <label class="chk"><input type="checkbox" id="cr-things" ${car.trash ? 'checked' : ''}> В салоне вещи</label>
        <label class="chk"><input type="checkbox" id="cr-canopy" ${car.canopy ? 'checked' : ''}> Тент</label>
        <label class="chk"><input type="checkbox" id="cr-oncharge" ${car.on_charge ? 'checked' : ''}> Заряжается</label>
      </div>
      ${car.has_key ? '<label class="chk" style="margin-top:8px"><input type="checkbox" id="cr-key" checked> Ключ сдал</label>' : ''}
      <label class="field" style="margin-top:12px"><span>Комментарий (что случилось, куда поставили)</span>
        <textarea id="cr-comment" rows="2" maxlength="255" placeholder="Например: оставил у главного входа, левое колесо спущено">${esc(car.note || '')}</textarea></label>
      ${photoPickHtml('cr')}
      <p class="hint">Снятый с галочки «Технически исправен», а также «В салоне вещи» или не «Чистый»
      автоматически переводят кар в статус «на обслуживании». Оставить на зарядке можно кар
      с любым зарядом, включая полный.</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Отметить возврат</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      /* фото: съёмка камерой смартфона (capture) или выбор из галереи (18.10.2026) */
      const pickPhoto = bindPhotoPick(m, 'cr');
      m.querySelector('[data-ok]').onclick = async () => {
        const charge = $('#cr-charge').value;
        const onCharge = $('#cr-oncharge').checked;
        const fd = new FormData();
        const person = state.user?.role !== 'employee' ? personFieldValue('cr') : { employee_id: null, name: '' };
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
function carHandoverModal(car, after) {
  openModal({
    title: `Передать кар №${car.number}`,
    subtitle: car.holder_name ? `Держит: ${car.holder_name}` : 'Кар никто не держит',
    body: `${personFieldHtml('ch')}
      <label class="chk"><input type="checkbox" id="ch-key" ${car.has_key ? 'checked' : ''}> Передаю с ключом</label>
      <label class="field" style="margin-top:10px"><span>Комментарий</span>
        <input type="text" id="ch-comment" maxlength="255" placeholder="Например: передал на время обеда"></label>
      <p class="hint">Передача фиксируется в истории отдельно от возврата: после неё кар
      возвращает тот, кто принял (или супервайзер).</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
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
    body: `${personFieldHtml('cg')}
      <label class="chk"><input type="checkbox" id="cg-key" checked> Выдаю с ключом</label>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
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
    body: `<label class="field"><span>Сотрудник</span>
        <select id="ca-emp"><option value="">— не закреплять —</option>
          ${emps.map(e => `<option value="${e.id}" ${e.id === car.assigned_to ? 'selected' : ''}>${esc(e.full_name)}</option>`).join('')}
        </select></label>
      ${emps.length ? '' : '<p class="hint">Список сотрудников доступен после загрузки раздела «Сотрудники» (менеджеры).</p>'}
      <p class="hint">Сейчас закреплён: ${esc(car.assigned_name || 'ни за кем')}.</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
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
    body: `<label class="field"><span>Новый статус</span>
        <select id="cs-status">${statuses.map(s =>
          `<option value="${esc(s.code)}" ${s.code === car.status ? 'selected' : ''}>${esc(s.title)}</option>`).join('')}
        </select></label>
      <label class="field"><span>Причина / примечание</span>
        <input type="text" id="cs-note" maxlength="255" placeholder="Например: снят с обслуживания после ремонта"></label>
      <p class="hint">Правила сервера: «занят» без держателя поставить нельзя; с «занят» — только через возврат;
      снять с обслуживания может менеджер или администратор.</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
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

function carEditModal(car, after) {
  openModal({
    title: `Карточка кара №${car.number}`,
    body: `<label class="field"><span>Номер</span><input type="text" id="ce-number" value="${esc(car.number)}" maxlength="40"></label>
      <label class="field"><span>Место стоянки</span><select id="ce-location">${locationOptions(car.location)}</select></label>
      <label class="field"><span>Примечание</span><input type="text" id="ce-note" value="${esc(car.note || '')}" maxlength="255"></label>
      <label class="chk"><input type="checkbox" id="ce-active" ${car.active ? 'checked' : ''}> Кар в работе (виден сотрудникам)</label>
      <p class="hint">Отключённый кар виден только менеджменту; история операций сохраняется.</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
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

function carAddModal(after) {
  openModal({
    title: 'Новый кар',
    body: `<label class="field"><span>Номер (обязательно)</span>
        <input type="text" id="ca-number" maxlength="40" placeholder="Например: 04"></label>
      <p class="hint">Место стоянки и состояние указываются при возврате и в карточке кара —
        новый кар создаётся свободным без места (решение владельца 18.10.2026).</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
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
  const rows = (data.history || []).map(h => `
    <div class="history-item">
      <div class="ts">${esc(h.ts ? dRuCar(h.ts) + ' ' + hhmm(h.ts) : '—')}</div>
      <div class="what"><b>${esc(h.action_title || h.action)}</b>
        ${h.person ? ` · ${esc(h.person)}` : ''}${h.location ? ` · ${esc(h.location)}` : ''}
        ${h.with_key === null || h.with_key === undefined ? '' : (h.with_key ? ' · с ключом' : ' · без ключа')}
        <small class="muted">${esc(h.actor_name || '')}</small>
        ${h.photos?.length ? `<div class="thumbs">${h.photos.map(photoThumb).join('')}</div>` : ''}
        ${h.details?.comment ? `<div class="muted" style="font-size:12.5px">${esc(h.details.comment)}</div>` : ''}
      </div>
    </div>`).join('');
  openModal({
    title: `История кара №${car.number}`,
    subtitle: `${(data.history || []).length} операций · записи не редактируются и не удаляются`,
    wide: true,
    body: `<div class="history">${rows || '<div class="empty">Операций пока не было</div>'}</div>`,
    footer: `<button class="btn btn-ghost" data-cancel>Закрыть</button>`,
    onMount(m) { m.querySelector('[data-cancel]').onclick = closeModal; },
  });
}

/* ─────────────────── фото: превью + просмотр + удаление ─────────────────── */
/* Миниатюра медиа: фото — картинкой, видео — первым кадром с кнопкой ▶.
   Клик открывает оригинал в новой вкладке (видео отдаётся с Range, плеер мотает). */
function photoThumb(p) {
  const isVideo = p.media_type === 'video';
  const kind = isVideo ? 'видео' : 'фото';
  if (!p.url) return `<span class="badge muted" title="файл удалён по сроку хранения">${kind} недоступно</span>`;
  const inner = isVideo
    ? `<video src="${esc(p.url)}" muted playsinline preload="metadata"></video><span class="thumb-play">▶</span>`
    : `<img src="${esc(p.url)}" alt="${esc(p.filename || 'фото')}" loading="lazy">`;
  return `<a class="thumb${isVideo ? ' thumb-video' : ''}" href="${esc(p.url)}" target="_blank"
      rel="noopener" title="${esc(p.filename || kind)}">${inner}</a>
    <button class="icon-btn thumb-del" data-photo-del="${p.id}" title="Удалить ${kind}">✕</button>`;
}

function bindPhotoDelete(root, after) {
  $$('[data-photo-del]', root).forEach(b => b.onclick = () =>
    confirmDialog('Удалить фото?', 'Файл будет удалён с сервера без возможности восстановления.', async () => {
      try { await api(`/api/photos/${b.dataset.photoDel}`, { method: 'DELETE' }); toast('Фото удалено', 'ok'); if (after) after(); }
      catch (e) { toast(e.message, 'err'); }
    }, 'Удалить'));
}

/* ─────────── экран Настроек «Электрокары» (19.10.2026): парк и места стоянки ───────────
   Единственное место правки парка и справочника мест — экран в «Настройках»
   (группа «Объект», адрес #/settings/cars; docs/PROPOSAL-SETTINGS-IA-2026-10-19.md).
   Переехал из кнопок «+ Кар» и «Места» раздела «Электрокары»: раздел остался
   ежедневным рабочим местом (взять/вернуть/передать/выдать), кнопки — deep-link
   сюда (settingsOpen). Прежняя модалка «Места стоянки» заменена этим экраном.

   Права: видимость экрана — cars.view (+ вход в «Настройки»), правки — cars.manage.
   Вызывается из реестра modules/settings.js (подключается после этого файла). */
async function renderCarsDictScreen(host) {
  const render = async () => {
    const [data, meta, locs] = await Promise.all([
      api('/api/cars', { silent: true }),
      carsState.meta ? Promise.resolve(carsState.meta) : api('/api/cars/meta', { silent: true }),
      api('/api/cars/locations', { silent: true }),
    ]);
    carsState.data = data; carsState.meta = meta;
    carsState.locations = locs.locations || [];
    const canEdit = !!meta.can_manage;
    const cars = data.cars || [];
    host.innerHTML = `
      ${settingsHead('Электрокары',
        'Парк и места стоянки — справочник. Ежедневные операции (взять / вернуть / передать / выдать) — в разделе «Электрокары».',
        `<button class="btn btn-sm btn-ghost" id="cd-to-cars">К операциям ↗</button>
         ${canEdit ? '<button class="btn btn-sm btn-primary" id="cd-add">+ Кар</button>' : ''}`)}
      ${canEdit ? '' : '<div class="dict-banner gold"><span>🔒</span><span>Только просмотр: для правок парка и мест нужно право <b>cars.manage</b> (выдаётся в «Настройки → Права доступа»).</span></div>'}
      ${settingsPanel('Парк', `
        <div class="table-wrap"><table class="data">
          <thead><tr><th>Кар</th><th>Статус</th><th>Место стоянки</th><th>Закреплён</th><th>Примечание</th><th></th></tr></thead>
          <tbody>${cars.map(c => `<tr>
            <td><b>№${esc(c.number)}</b>${c.active ? '' : ' <span class="badge muted">отключён</span>'}</td>
            <td><span class="badge ${CAR_BADGE[c.status] || 'muted'}">${esc(c.status_title)}</span></td>
            <td>${c.location ? esc(c.location) : '<span class="muted">не указано</span>'}</td>
            <td>${c.assigned_name ? esc(c.assigned_name) : '<span class="muted">—</span>'}</td>
            <td>${esc(c.note || '')}</td>
            <td class="num">${canEdit ? `<button class="btn btn-sm btn-ghost" data-cd-edit="${c.id}">Карточка</button>` : ''}</td>
          </tr>`).join('') || '<tr><td colspan="6" class="empty">Парк пуст</td></tr>'}</tbody></table></div>
        <p class="hint">Новый кар создаётся свободным без места стоянки — место указывается при возврате
        и в карточке (решение владельца 18.10.2026). Отключение кара (чекбокс в карточке) убирает его
        из списка сотрудников; история операций сохраняется.</p>`)}
      ${settingsPanel('Места стоянки', `
        <div class="check-list" style="max-height:320px">${carsState.locations.map(l => `
          <div class="rule-row" style="grid-template-columns:1fr auto">
            <div><div class="lbl">${esc(l.name)}</div>
              <div class="desc">${l.active ? '' : '<span class="badge muted">отключено</span>'}${l.builtin ? ' · встроенное' : ''}</div></div>
            ${canEdit ? `<div style="display:flex;gap:6px">
              <button class="btn btn-sm btn-ghost" data-loc-rename="${l.id}">Переименовать</button>
              <button class="btn btn-sm btn-ghost" data-loc-toggle="${l.id}">${l.active ? 'Отключить' : 'Включить'}</button>
              <button class="btn btn-sm btn-ghost" data-loc-del="${l.id}" title="Удалить место (если оно не указано у активных каров)">Удалить</button></div>` : ''}
          </div>`).join('') || '<div class="empty">Мест пока нет</div>'}</div>
        ${canEdit ? `<div class="grid-2" style="margin-top:12px">
          <input type="text" id="loc-new" placeholder="Новое место (например: Парковка у корпуса B)" maxlength="160">
          <button class="btn btn-primary" data-loc-add>Добавить</button></div>
        <p class="hint">Удаление места, указанного у активного кара, сервер отклонит (409) — сначала смените
        место у кара или отключите место. Прошлые возвраты хранят место текстом, история не ломается.</p>` : ''}`)}`;
    bindCarsDictScreen(host, render);
  };
  await render();
}

function bindCarsDictScreen(host, render) {
  const toCars = $('#cd-to-cars', host);
  if (toCars) toCars.onclick = () => navigate('cars');
  const add = $('#cd-add', host);
  if (add) add.onclick = () => carAddModal(render);
  $$('[data-cd-edit]', host).forEach(b => b.onclick = () => {
    const car = (carsState.data?.cars || []).find(c => c.id === Number(b.dataset.cdEdit));
    if (car) carEditModal(car, render);
  });
  const locAdd = $('[data-loc-add]', host);
  if (locAdd) locAdd.onclick = async () => {
    const name = $('#loc-new', host).value.trim();
    if (!name) return toast('Введите название места', 'warn');
    try { await api('/api/cars/locations', { method: 'POST', body: { name } }); toast('Место добавлено', 'ok'); render(); }
    catch (e) { toast(e.message, 'err'); }
  };
  $$('[data-loc-rename]', host).forEach(b => b.onclick = async () => {
    const loc = carsState.locations.find(x => x.id === Number(b.dataset.locRename));
    const name = prompt('Новое название места', loc.name);
    if (!name || name.trim() === loc.name) return;
    try { await api(`/api/cars/locations/${loc.id}`, { method: 'PUT', body: { name: name.trim() } }); toast('Переименовано', 'ok'); render(); }
    catch (e) { toast(e.message, 'err'); }
  });
  $$('[data-loc-toggle]', host).forEach(b => b.onclick = async () => {
    const loc = carsState.locations.find(x => x.id === Number(b.dataset.locToggle));
    try { await api(`/api/cars/locations/${loc.id}`, { method: 'PUT', body: { active: !loc.active } }); toast(loc.active ? 'Место отключено' : 'Место включено', 'ok'); render(); }
    catch (e) { toast(e.message, 'err'); }
  });
  $$('[data-loc-del]', host).forEach(b => b.onclick = () => {
    const loc = carsState.locations.find(x => x.id === Number(b.dataset.locDel));
    confirmDialog('Удалить место стоянки?',
      `«${loc.name}» исчезнет из справочника. Прошлые возвраты хранят место текстом — история не сломается. Если место указано у активного кара, сервер отклонит удаление.`,
      async () => {
        try { await api(`/api/cars/locations/${loc.id}`, { method: 'DELETE' }); toast('Место удалено', 'ok'); render(); }
        catch (e) { toast(e.message, 'err'); }
      }, 'Удалить');
  });
}
