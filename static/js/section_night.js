/* ══════════════════════════════════════════════════════════════════════
   РАЗДЕЛ «НОЧНОЙ ОТЧЁТ» — смена 20:00–08:00: области обхода, чек-листы,
   отметки ОК/Не ОК с комментариями и фото, перехваты областей, шаг
   «Проверка электрокаров», закрытие смены, архив и выгрузка DOCX/PDF.
   Отдельный файл: раздел добавлен позже основного интерфейса.
   Хелперы app.js: $ $$ esc api multipartApi openModal closeModal confirmDialog
   toast downloadBlob hhmm dateRu poll state.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

const nightState = { reportId: null, today: null, areas: null, canEditDict: false };

/* dateRu() из app.js рассчитан на «YYYY-MM-DD»; для datetime берём только дату */
const dRu = iso => (iso ? dateRu(String(iso).slice(0, 10)) : '');

const NIGHT_SECTION_BADGE = { free: 'muted', taken: 'warn', done: 'ok' };
const NIGHT_ANSWER_BADGE = { ok: 'ok', bad: 'danger', '': 'muted' };

function nightIsSupervisor() {
  return ['supervisor', 'manager', 'admin'].includes(state.user?.role);
}

/* ─────────────────────────── раздел ─────────────────────────── */
async function loadNight() {
  $('#view-night').innerHTML = `
    <div class="page-head">
      <div><h2>Ночной отчёт</h2><div class="sub" id="night-sub">Смена 20:00–08:00 · отчёт относится к дате начала смены</div></div>
      <div class="spacer"></div>
      <button class="btn btn-sm" id="night-refresh">Обновить</button>
      <button class="btn btn-sm btn-ghost hidden" id="night-today-btn">К текущей смене</button>
      <button class="btn btn-sm btn-ghost hidden" id="night-archive">Архив</button>
      <button class="btn btn-sm btn-ghost hidden" id="night-dict">Области</button>
      <button class="btn btn-sm btn-ghost hidden" id="night-docx">DOCX</button>
      <button class="btn btn-sm btn-ghost hidden" id="night-pdf">PDF</button>
      <button class="btn btn-sm btn-danger hidden" id="night-close">Закрыть смену</button>
      <button class="btn btn-sm btn-ghost hidden" id="night-reopen">Переоткрыть</button>
    </div>
    <div id="night-body"><div class="empty">Загрузка…</div></div>`;

  $('#night-refresh').onclick = () => fetchNight();
  $('#night-today-btn').onclick = () => { nightState.reportId = null; fetchNight(); };
  $('#night-archive').onclick = () => nightArchiveModal();
  $('#night-dict').onclick = () => nightAreasModal();
  $('#night-docx').onclick = () => exportNight('docx');
  $('#night-pdf').onclick = () => exportNight('pdf');
  $('#night-close').onclick = () => closeReportModal();
  $('#night-reopen').onclick = () => reopenReport();

  await fetchNight();
  poll('night', () => { if (state.view === 'night') fetchNight(true); }, 60000);
}

async function fetchNight(silent) {
  try {
    let report = null, note = '';
    if (nightState.reportId) {
      report = (await api(`/api/night/reports/${nightState.reportId}`, { silent: !!silent })).report;
    } else {
      const t = await api('/api/night/today', { silent: !!silent });
      nightState.today = t;
      if (!t.available) { note = t.note || 'Ночная смена ещё не началась'; }
      else report = t.report;
    }
    renderNight(report, note);
  } catch (e) {
    $('#night-body').innerHTML = `<div class="panel"><h3 class="panel-title">Отчёт не загрузился</h3>
      <p style="color:var(--danger);font-weight:600">${esc(e.message)}</p>
      <p class="hint">Нажмите «Обновить». Если ошибка повторяется — откройте «Архив» и выберите смену вручную.</p></div>`;
  }
}

function renderNight(rep, note) {
  const show = (id, on) => $(id)?.classList.toggle('hidden', !on);
  show('#night-archive', true);
  show('#night-dict', true);
  show('#night-today-btn', !!nightState.reportId);
  show('#night-docx', !!rep);
  show('#night-pdf', !!rep);
  show('#night-close', !!rep && !rep.readonly && nightIsSupervisor());
  show('#night-reopen', !!rep && rep.readonly && nightIsSupervisor());

  if (!rep) {
    $('#night-sub').textContent = 'Смена 20:00–08:00 · отчёт относится к дате начала смены';
    $('#night-body').innerHTML = `<div class="panel"><h3 class="panel-title">Отчёта пока нет</h3>
      <p class="hint" style="margin:0">${esc(note || 'Ночная смена ещё не началась — отчёт появится в 20:00.')}</p>
      <p class="hint">Архив прошлых смен доступен по кнопке «Архив» справа вверху.</p></div>`;
    return;
  }

  $('#night-sub').textContent = `Смена ${dateRu(rep.date)} · ${rep.shift_label || ''} · автозакрытие ${hhmm(rep.deadline)}`;
  const p = rep.progress || { total: 0, done: 0, taken: 0, free: 0 };
  const bad = (rep.areas || []).reduce((s, a) => s + (a.items_bad || 0), 0);
  const unanswered = (rep.areas || []).reduce((s, a) => s + (a.items_unanswered || 0), 0);

  const areas = (rep.areas || []).filter(a => !a.is_cars);
  const carsSection = (rep.areas || []).find(a => a.is_cars);
  const byCat = {};
  areas.forEach(a => { (byCat[a.category || 'Без категории'] ||= []).push(a); });

  $('#night-body').innerHTML = `
    ${rep.readonly ? `<div class="ro-banner">Смена закрыта ${rep.closed_at ? dRu(rep.closed_at) + ' ' + hhmm(rep.closed_at) : ''} ·
      итог: ${esc(rep.result_title || '—')} · правки недоступны</div>` : ''}
    <div class="stat-grid">
      <div class="stat accent"><div class="k">Областей закрыто</div><div class="v">${p.done} / ${p.total}</div></div>
      <div class="stat warn"><div class="k">В работе</div><div class="v">${p.taken}</div></div>
      <div class="stat"><div class="k">Свободны</div><div class="v">${p.free}</div></div>
      <div class="stat danger"><div class="k">Замечаний (Не ОК)</div><div class="v">${bad}</div></div>
      <div class="stat info"><div class="k">Не отмечено пунктов</div><div class="v">${unanswered}</div></div>
      <div class="stat ${rep.cars_step_done ? '' : 'warn'}"><div class="k">Электрокары</div>
        <div class="v">${rep.cars_step_done ? 'готово' : 'не завершено'}</div></div>
    </div>

    ${(rep.interceptions || []).length ? `<div class="panel"><h3 class="panel-title">Перехваты областей</h3>
      <div class="history">${rep.interceptions.map(i => `<div class="history-item">
        <div class="ts">${esc(i.ts ? dRu(i.ts) + ' ' + hhmm(i.ts) : '')}</div>
        <div class="what"><b>${esc(i.area_name)}</b>: ${esc(i.from_user_name || '—')} → ${esc(i.to_user_name || '—')}</div>
      </div>`).join('')}</div></div>` : ''}

    ${carsSection ? `<div class="panel"><h3 class="panel-title">Шаг «Проверка электрокаров»
        <span class="badge ${carsSection.status === 'done' ? 'ok' : 'warn'}">${esc(carsSection.status_title)}</span></h3>
      <p class="hint" style="margin:0 0 10px">Обход всего активного парка: где кар, заряд, тент, состояние, мусор.
      Замечания попадают супервайзеру, состояние карточек каров обновляется автоматически.</p>
      <button class="btn btn-primary" id="night-cars-open">${rep.cars_step_done ? 'Посмотреть обход' : 'Проверить электрокары'}</button>
      ${carsSection.closed_at ? `<span class="hint"> · завершено в ${esc(hhmm(carsSection.closed_at))}</span>` : ''}
    </div>` : ''}

    ${Object.keys(byCat).length ? Object.entries(byCat).map(([cat, list]) => `
      <div class="opt-group-title">${esc(cat)}</div>
      <div class="night-areas">${list.map(a => nightAreaCard(a, rep)).join('')}</div>`).join('')
      : '<div class="empty">Области обхода не настроены — справочник: кнопка «Области» справа вверху</div>'}

    <p class="hint">Область ведёт один человек: «Взять в работу» закрепляет её за вами, чужую — только через
    подтверждение (перехват фиксируется в отчёте). Закрыть область можно и с неотмеченными пунктами —
    после подтверждения; пункты останутся как «не отмечено».</p>`;

  bindNight(rep, carsSection);
}

function nightAreaCard(a, rep) {
  const mine = a.taken_by === state.user?.id;
  return `<div class="panel night-area ${a.status}" data-area="${a.id}">
    <div class="night-area-head">
      <div><b>${esc(a.name)}</b>
        <span class="badge ${NIGHT_SECTION_BADGE[a.status] || 'muted'}">${esc(a.status_title)}</span>
        ${mine ? '<span class="badge ok">ведёте вы</span>' : (a.taken_by_name ? `<span class="badge info">${esc(a.taken_by_name)}</span>` : '')}
      </div>
      <div class="night-area-prog">${a.items_answered} / ${a.items_total}
        ${a.items_bad ? `<span class="badge danger">Не ОК: ${a.items_bad}</span>` : ''}
        ${a.closed_at ? `<span class="muted">закрыта ${esc(hhmm(a.closed_at))}</span>` : ''}</div>
    </div>
    ${rep.readonly ? '' : `<div class="row-actions" style="margin:8px 0">
      ${a.status === 'done'
        ? `<button class="btn btn-sm btn-ghost" data-sec-reopen="${a.id}">Переоткрыть</button>`
        : `<button class="btn btn-sm ${mine ? 'btn-ghost' : 'btn-accent'}" data-sec-take="${a.id}">${a.status === 'taken' && !mine ? 'Перехватить' : (mine ? 'Продолжить' : 'Взять в работу')}</button>
           <button class="btn btn-sm" data-sec-close="${a.id}">Завершить область</button>`}
    </div>`}
    <div class="night-items">${(a.items || []).map(it => nightItemRow(it, rep)).join('') ||
      '<div class="hint" style="margin:0">Пунктов нет — справочник областей: кнопка «Области».</div>'}</div>
  </div>`;
}

function nightItemRow(it, rep) {
  const photos = (it.photos || []);
  return `<div class="night-item ${it.answer || 'none'}" data-item="${it.id}">
    <div class="night-item-text">${esc(it.text)}
      ${it.answered_by_name ? `<small class="muted">· ${esc(it.answered_by_name)}${it.answered_at ? ' ' + esc(hhmm(it.answered_at)) : ''}</small>` : ''}
    </div>
    <div class="night-item-acts">
      ${rep.readonly
        ? `<span class="badge ${NIGHT_ANSWER_BADGE[it.answer] || 'muted'}">${esc(it.answer_title)}</span>`
        : `<button class="btn btn-sm ${it.answer === 'ok' ? 'btn-primary' : 'btn-ghost'}" data-ans="ok" data-id="${it.id}">ОК</button>
           <button class="btn btn-sm ${it.answer === 'bad' ? 'btn-danger' : 'btn-ghost'}" data-ans="bad" data-id="${it.id}">Не ОК</button>
           <button class="btn btn-sm btn-ghost" data-cmt="${it.id}" title="Комментарий">💬${it.comment ? ' •' : ''}</button>
           <label class="btn btn-sm btn-ghost" title="Добавить фото">📷
             <input type="file" accept="image/*" data-photo="${it.id}" class="hidden-file"></label>`}
      ${photos.length ? `<div class="thumbs">${photos.map(photoThumb).join('')}</div>` : ''}
      ${it.comment ? `<div class="night-item-cmt">${esc(it.comment)}</div>` : ''}
    </div>
  </div>`;
}

function bindNight(rep, carsSection) {
  const reload = () => fetchNight(true);

  $$('[data-sec-take]').forEach(b => b.onclick = () => sectionTake(Number(b.dataset.secTake), false, reload));
  $$('[data-sec-close]').forEach(b => b.onclick = () => sectionClose(Number(b.dataset.secClose), false, reload));
  $$('[data-sec-reopen]').forEach(b => b.onclick = async () => {
    try { await api(`/api/night/sections/${b.dataset.secReopen}/reopen`, { method: 'POST' }); toast('Область переоткрыта', 'ok'); reload(); }
    catch (e) { toast(e.message, 'err'); }
  });

  $$('[data-ans]').forEach(b => b.onclick = async () => {
    const id = Number(b.dataset.id);
    const next = b.dataset.ans;
    const item = findItem(rep, id);
    const cur = item?.answer === next ? '' : next;      // повторный тап по тому же ответу — снять
    try {
      await api(`/api/night/items/${id}/answer`, { method: 'PUT', body: { answer: cur, comment: item?.comment || '' } });
      reload();
    } catch (e) { toast(e.message, 'err'); }
  });

  $$('[data-cmt]').forEach(b => b.onclick = () => {
    const id = Number(b.dataset.cmt);
    const item = findItem(rep, id);
    itemCommentModal(item, reload);
  });

  $$('[data-photo]').forEach(inp => inp.onchange = async () => {
    const f = inp.files?.[0];
    if (!f) return;
    const fd = new FormData();
    fd.append('file', f, f.name);
    try {
      await multipartApi(`/api/night/items/${inp.dataset.photo}/photo`, fd);
      toast('Фото добавлено', 'ok'); reload();
    } catch (e) { toast(e.message, 'err'); }
  });

  bindPhotoDelete($('#night-body'), reload);

  const carsBtn = $('#night-cars-open');
  if (carsBtn) carsBtn.onclick = () => nightCarsModal(rep, carsSection, reload);
}

function findItem(rep, itemId) {
  for (const a of rep.areas || []) for (const it of a.items || []) if (it.id === itemId) return it;
  return null;
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
    body: `<textarea id="ni-comment" rows="4" maxlength="2000" placeholder="Что не так, что сделали, кому сообщили">${esc(item.comment || '')}</textarea>
      <p class="hint">Ответ: <b>${esc(item.answer_title)}</b>. Комментарий сохраняется вместе с автором и временем,
      попадает в выгрузку DOCX/PDF.</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
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
  const render = async () => {
    const st = await api(`/api/night/reports/${rep.id}/cars`);
    openModal({
      title: 'Проверка электрокаров',
      subtitle: `Смена ${dateRu(rep.date)} · проверено ${st.checked} из ${st.total}${st.problems ? ` · замечаний: ${st.problems}` : ''}`,
      wide: true,
      body: `<div class="check-list" style="max-height:52vh">${st.list.map(e => {
        const c = e.car, k = e.check;
        return `<div class="rule-row" style="grid-template-columns:1fr auto">
          <div><div class="lbl">№${esc(c.number)}
              <span class="badge ${(typeof CAR_BADGE !== 'undefined' ? CAR_BADGE[c.status] : '') || 'muted'}">${esc(c.status_title)}</span>
              ${e.checked ? (k.found ? '<span class="badge ok">проверен</span>' : '<span class="badge danger">не найден</span>') : '<span class="badge muted">не проверен</span>'}
              ${k?.taken_after_check ? '<span class="badge warn">взят после проверки</span>' : ''}</div>
            <div class="desc">${esc(c.location || 'место не указано')} · заряд: ${esc(k ? (k.charge || '—') : (c.charge_title || '—'))}
              ${k ? ` · ${esc(hhmm(k.checked_at || ''))} ${esc(k.checker_name || '')}` : ''}
              ${k?.comment ? ` · ${esc(k.comment)}` : ''}</div></div>
          <div style="display:flex;gap:6px;align-items:center">
            ${rep.readonly ? '' : `<button class="btn btn-sm ${e.checked ? 'btn-ghost' : 'btn-primary'}" data-car-check="${c.id}">${e.checked ? 'Изменить' : 'Отметить'}</button>`}
          </div></div>`;
      }).join('') || '<div class="empty">Активных каров нет</div>'}</div>
      <p class="hint">Отметка обновляет карточку кара в общей базе. «Не ОК» по состоянию и «кар не найден»
      попадают в замечания супервайзеру; отсутствие тента — просто факт.</p>`,
      footer: `<button class="btn btn-ghost" data-cancel>Закрыть</button>
               ${rep.readonly ? '' : `<button class="btn btn-primary" data-finish>${st.cars_step_done ? 'Шаг завершён · отметить снова' : 'Завершить шаг'}</button>`}`,
      onMount(m) {
        m.querySelector('[data-cancel]').onclick = closeModal;
        $$('[data-car-check]', m).forEach(b => b.onclick = () =>
          nightCarCheckModal(rep, st.list.find(x => x.car.id === Number(b.dataset.carCheck)), render));
        const fin = m.querySelector('[data-finish]');
        if (fin) fin.onclick = () => carsFinish(rep, st.unchecked, async () => { closeModal(); if (after) await after(); });
      },
    });
  };
  await render();
}

function nightCarCheckModal(rep, entry, after) {
  const c = entry.car, k = entry.check || {};
  openModal({
    title: `Кар №${c.number} — ночной обход`,
    subtitle: `${c.status_title} · ${c.location || 'место не указано'}`,
    wide: true,
    body: `
      <div class="check-list" style="max-height:none">
        <label class="chk"><input type="checkbox" id="nc-found" ${k.found === undefined ? 'checked' : (k.found ? 'checked' : '')}> Кар найден на месте</label>
        <label class="chk"><input type="checkbox" id="nc-canopy" ${k.canopy === undefined ? (c.canopy ? 'checked' : '') : (k.canopy ? 'checked' : '')}> Тент на месте</label>
        <label class="chk"><input type="checkbox" id="nc-oncharge" ${k.on_charge === undefined ? (c.on_charge ? 'checked' : '') : (k.on_charge ? 'checked' : '')}> Стоит на зарядке</label>
        <label class="chk"><input type="checkbox" id="nc-trash" ${k.trash ? 'checked' : ''}> В салоне мусор</label>
        <label class="chk"><input type="checkbox" id="nc-clean" ${k.clean === undefined ? (c.clean ? 'checked' : '') : (k.clean ? 'checked' : '')}> Салон убран</label>
        <label class="chk"><input type="radio" name="nc-cond" value="ok" ${(k.condition || c.condition || 'ok') !== 'bad' ? 'checked' : ''}> Технически исправен</label>
        <label class="chk"><input type="radio" name="nc-cond" value="bad" ${(k.condition || c.condition) === 'bad' ? 'checked' : ''}> Есть замечания (уйдёт «на обслуживании»)</label>
      </div>
      <div class="grid-2" style="margin-top:12px">
        <label class="field"><span>Где стоит</span><input type="text" id="nc-location" maxlength="160" value="${esc(k.location || c.location || '')}"></label>
        <label class="field"><span>Заряд</span><select id="nc-charge">
          <option value="">— не отмечать —</option>
          ${CHARGE_OPTS.map(([v, t]) => `<option value="${v}" ${(k.charge || c.charge) === v ? 'selected' : ''}>${t}</option>`).join('')}
        </select></label>
      </div>
      <label class="field"><span>Комментарий</span><textarea id="nc-comment" rows="2" maxlength="2000">${esc(k.comment || '')}</textarea></label>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Сохранить отметку</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        try {
          await api(`/api/night/reports/${rep.id}/cars/${c.id}/check`, { method: 'POST', body: {
            found: $('#nc-found').checked, location: $('#nc-location').value.trim(),
            canopy: $('#nc-canopy').checked, charge: $('#nc-charge').value,
            on_charge: $('#nc-oncharge').checked, condition: ($('[name=nc-cond]:checked') || {}).value || 'ok',
            trash: $('#nc-trash').checked, clean: $('#nc-clean').checked, comment: $('#nc-comment').value.trim() } });
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
          toast('Смена закрыта', 'ok'); fetchNight();
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
  confirmDialog('Переоткрыть смену?', 'Отчёт снова станет доступным для правок; итог будет пересчитан при закрытии.',
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
    body: `<div class="table-wrap" style="max-height:56vh"><table class="data responsive">
        <thead><tr><th>Дата</th><th>Статус</th><th>Итог</th><th>Области</th><th>Электрокары</th><th>Закрыт</th><th></th></tr></thead>
        <tbody>${reports.map(r => `<tr>
          <td data-label="Дата"><b>${esc(dateRu(r.date))}</b><small>${esc(r.shift_label || '')}</small></td>
          <td data-label="Статус"><span class="badge ${r.status === 'closed' ? 'ok' : 'warn'}">${r.status === 'closed' ? 'закрыт' : 'открыт'}</span></td>
          <td data-label="Итог">${esc(r.result_title || '—')}</td>
          <td data-label="Области" class="num">${r.progress?.done || 0} / ${r.progress?.total || 0}</td>
          <td data-label="Электрокары">${r.cars_step_done ? '<span class="badge ok">готово</span>' : '<span class="badge muted">—</span>'}</td>
          <td data-label="Закрыт">${r.closed_at ? esc(dRu(r.closed_at) + ' ' + hhmm(r.closed_at)) : '—'}</td>
          <td data-label=""><button class="btn btn-sm btn-ghost" data-open="${r.id}">Открыть</button></td>
        </tr>`).join('') || '<tr><td colspan="7" class="empty">Отчётов пока нет</td></tr>'}</tbody></table></div>`,
    footer: `<button class="btn btn-ghost" data-cancel>Закрыть</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      $$('[data-open]', m).forEach(b => b.onclick = () => {
        closeModal(); nightState.reportId = Number(b.dataset.open); fetchNight();
      });
    },
  });
}

/* ─────────────── выгрузка ─────────────── */
function exportNight(fmt) {
  const id = nightState.reportId || nightState.today?.report?.id;
  if (!id) return toast('Нет отчёта для выгрузки', 'warn');
  downloadBlob(`/api/night/reports/${id}/export.${fmt}`, `night-${fmt}.docx`);
}

/* ─────────────── справочник областей и пунктов (менеджер/админ) ─────────────── */
async function nightAreasModal() {
  const render = async () => {
    const data = await api('/api/night/areas');
    nightState.canEditDict = data.can_edit;
    if (!data.can_edit) {
      openModal({
        title: 'Области ночного обхода',
        subtitle: 'Просмотр справочника (правка — менеджер или администратор)',
        wide: true,
        body: `<div class="check-list" style="max-height:56vh">${data.areas.map(a => `
          <div class="rule-row" style="grid-template-columns:1fr auto"><div>
            <div class="lbl">${esc(a.name)} <small class="muted">${esc(a.category || '')}</small></div>
            <div class="desc">пунктов: ${a.items_total}${a.active ? '' : ' · <span class="badge muted">отключена</span>'}</div>
          </div></div>`).join('') || '<div class="empty">Областей нет</div>'}</div>`,
        footer: `<button class="btn btn-ghost" data-cancel>Закрыть</button>`,
        onMount(m) { m.querySelector('[data-cancel]').onclick = closeModal; },
      });
      return;
    }
    openModal({
      title: 'Области ночного обхода',
      subtitle: 'Справочник: что проверяем и по каким пунктам. Изменения попадают только в ещё не начатые области',
      wide: true,
      body: `
        <div class="panel" style="margin-bottom:12px"><h3 class="panel-title">Добавить область</h3>
          <div class="grid-2">
            <label class="field"><span>Название</span><input type="text" id="na-name" maxlength="160" placeholder="Например: Вилла 4001"></label>
            <label class="field"><span>Категория (группа в отчёте)</span><input type="text" id="na-cat" maxlength="80" placeholder="Например: Виллы"></label>
          </div>
          <div class="row-actions"><button class="btn btn-primary" id="na-add">Добавить</button></div>
        </div>
        <div class="panel" style="margin-bottom:12px"><h3 class="panel-title">Массовое создание однотипных</h3>
          <div class="grid-2">
            <label class="field"><span>Префикс</span><input type="text" id="nb-prefix" placeholder="Вилла "></label>
            <label class="field"><span>Первый номер</span><input type="number" id="nb-start" value="4001"></label>
            <label class="field"><span>Количество</span><input type="number" id="nb-count" value="12" min="1" max="200"></label>
            <label class="field"><span>Категория</span><input type="text" id="nb-cat" placeholder="Виллы"></label>
          </div>
          <div class="row-actions"><button class="btn" id="nb-add">Создать серию</button></div>
        </div>
        <div class="check-list" style="max-height:44vh">${data.areas.map(a => `
          <div class="night-dict-area">
            <div class="rule-row" style="grid-template-columns:1fr auto">
              <div><div class="lbl">${esc(a.name)} <small class="muted">${esc(a.category || '')} · порядок ${a.sort_order}</small>
                ${a.active ? '' : ' <span class="badge muted">отключена</span>'}</div>
                <div class="desc">пунктов: ${a.items_total}</div></div>
              <div class="row-actions">
                <button class="btn btn-sm btn-ghost" data-items="${a.id}">Пункты</button>
                <button class="btn btn-sm btn-ghost" data-area-edit="${a.id}">Править</button>
                <button class="btn btn-sm btn-ghost" data-area-del="${a.id}">Удалить</button>
              </div>
            </div>
          </div>`).join('') || '<div class="empty">Областей нет</div>'}</div>`,
      footer: `<button class="btn btn-ghost" data-cancel>Закрыть</button>`,
      onMount(m) {
        m.querySelector('[data-cancel]').onclick = closeModal;
        $('#na-add').onclick = async () => {
          const name = $('#na-name').value.trim();
          if (!name) return toast('Введите название области', 'warn');
          try {
            await api('/api/night/areas', { method: 'POST', body: { name, category: $('#na-cat').value.trim(), sort_order: 100, active: true } });
            toast('Область добавлена', 'ok'); render();
          } catch (e) { toast(e.message, 'err'); }
        };
        $('#nb-add').onclick = async () => {
          try {
            const r = await api('/api/night/areas/bulk', { method: 'POST', body: {
              prefix: $('#nb-prefix').value, start: Number($('#nb-start').value) || 1,
              count: Number($('#nb-count').value) || 1, category: $('#nb-cat').value.trim() } });
            toast(`Создано областей: ${r.created}`, 'ok'); render();
          } catch (e) { toast(e.message, 'err'); }
        };
        $$('[data-items]', m).forEach(b => b.onclick = () =>
          nightItemsModal(data.areas.find(a => a.id === Number(b.dataset.items)), render));
        $$('[data-area-edit]', m).forEach(b => b.onclick = () =>
          nightAreaEditModal(data.areas.find(a => a.id === Number(b.dataset.areaEdit)), render));
        $$('[data-area-del]', m).forEach(b => b.onclick = () => {
          const a = data.areas.find(x => x.id === Number(b.dataset.areaDel));
          confirmDialog('Удалить область?',
            `«${a.name}» будет отключена и убрана из открытых (ещё не начатых) отчётов. История закрытых смен сохранится.`,
            async () => {
              try { const r = await api(`/api/night/areas/${a.id}`, { method: 'DELETE' });
                toast(`Область отключена${r.sections_removed ? `, убрано из отчётов: ${r.sections_removed}` : ''}`, 'ok'); render(); }
              catch (e) { toast(e.message, 'err'); }
            }, 'Удалить');
        });
      },
    });
  };

  const nightAreaEditModal = (a, after) => openModal({
    title: 'Область: ' + a.name,
    body: `<label class="field"><span>Название</span><input type="text" id="ae-name" value="${esc(a.name)}" maxlength="160"></label>
      <div class="grid-2">
        <label class="field"><span>Категория</span><input type="text" id="ae-cat" value="${esc(a.category || '')}" maxlength="80"></label>
        <label class="field"><span>Порядок</span><input type="number" id="ae-order" value="${a.sort_order}"></label>
      </div>
      <label class="chk"><input type="checkbox" id="ae-active" ${a.active ? 'checked' : ''}> Область активна</label>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button><button class="btn btn-primary" data-ok>Сохранить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        try {
          await api(`/api/night/areas/${a.id}`, { method: 'PUT', body: {
            name: $('#ae-name').value.trim(), category: $('#ae-cat').value.trim(),
            sort_order: Number($('#ae-order').value) || 100, active: $('#ae-active').checked } });
          closeModal(); toast('Сохранено', 'ok'); if (after) after();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });

  const nightItemsModal = async (a, after) => {
    const renderItems = async () => {
      const fresh = (await api('/api/night/areas')).areas.find(x => x.id === a.id);
      openModal({
        title: 'Пункты: ' + fresh.name,
        subtitle: 'Правка текста обновляет пункт только в незакрытых областях; удалённый пункт остаётся в истории закрытых смен',
        wide: true,
        body: `<div class="grid-2" style="grid-template-columns:1fr 110px auto;margin-bottom:12px">
            <input type="text" id="it-text" maxlength="300" placeholder="Текст пункта (например: Окна закрыты, свет выключен)">
            <input type="number" id="it-order" value="100" title="Порядок">
            <button class="btn btn-primary" id="it-add">Добавить</button></div>
          <div class="check-list" style="max-height:46vh">${fresh.items.map(it => `
            <div class="rule-row" style="grid-template-columns:1fr auto">
              <div><div class="lbl">${esc(it.text)} <small class="muted">· порядок ${it.sort_order}</small>
                ${it.active ? '' : ' <span class="badge muted">отключён</span>'}</div></div>
              <div class="row-actions">
                <button class="btn btn-sm btn-ghost" data-it-edit="${it.id}">Править</button>
                <button class="btn btn-sm btn-ghost" data-it-toggle="${it.id}">${it.active ? 'Отключить' : 'Включить'}</button>
                <button class="btn btn-sm btn-ghost" data-it-del="${it.id}">Удалить</button>
              </div></div>`).join('') || '<div class="empty">Пунктов нет</div>'}</div>`,
        footer: `<button class="btn" data-back>← К областям</button><button class="btn btn-ghost" data-cancel>Закрыть</button>`,
        onMount(m) {
          m.querySelector('[data-cancel]').onclick = closeModal;
          m.querySelector('[data-back]').onclick = () => { closeModal(); if (after) after(); };
          $('#it-add').onclick = async () => {
            const text = $('#it-text').value.trim();
            if (!text) return toast('Введите текст пункта', 'warn');
            try {
              const r = await api(`/api/night/areas/${fresh.id}/items`, { method: 'POST',
                body: { text, sort_order: Number($('#it-order').value) || 100, active: true } });
              toast(`Пункт добавлен${r.added_to_open_sections ? ` (попал в открытых областей: ${r.added_to_open_sections})` : ''}`, 'ok');
              renderItems();
            } catch (e) { toast(e.message, 'err'); }
          };
          const editItem = (it) => openModal({
            title: 'Пункт области',
            body: `<label class="field"><span>Текст</span><input type="text" id="ie-text" value="${esc(it.text)}" maxlength="300"></label>
              <div class="grid-2">
                <label class="field"><span>Порядок</span><input type="number" id="ie-order" value="${it.sort_order}"></label>
                <label class="field"><span>Активен</span><select id="ie-active">
                  <option value="1" ${it.active ? 'selected' : ''}>да</option>
                  <option value="0" ${it.active ? '' : 'selected'}>нет</option></select></label>
              </div>`,
            footer: `<button class="btn btn-ghost" data-cancel>Отмена</button><button class="btn btn-primary" data-ok>Сохранить</button>`,
            onMount(mm) {
              mm.querySelector('[data-cancel]').onclick = () => { closeModal(); renderItems(); };
              mm.querySelector('[data-ok]').onclick = async () => {
                try {
                  await api(`/api/night/items/${it.id}`, { method: 'PUT', body: {
                    text: $('#ie-text').value.trim(), sort_order: Number($('#ie-order').value) || 100,
                    active: $('#ie-active').value === '1' } });
                  toast('Пункт сохранён', 'ok'); renderItems();
                } catch (e) { toast(e.message, 'err'); }
              };
            },
          });
          $$('[data-it-edit]', m).forEach(b => b.onclick = () => editItem(fresh.items.find(x => x.id === Number(b.dataset.itEdit))));
          $$('[data-it-toggle]', m).forEach(b => b.onclick = async () => {
            const it = fresh.items.find(x => x.id === Number(b.dataset.itToggle));
            try {
              await api(`/api/night/items/${it.id}`, { method: 'PUT', body: { text: it.text, sort_order: it.sort_order, active: !it.active } });
              renderItems();
            } catch (e) { toast(e.message, 'err'); }
          });
          $$('[data-it-del]', m).forEach(b => b.onclick = () => {
            const it = fresh.items.find(x => x.id === Number(b.dataset.itDel));
            confirmDialog('Удалить пункт?', `«${it.text}» исчезнет из незакрытых областей; в закрытых сменах останется.`,
              async () => { try { await api(`/api/night/items/${it.id}`, { method: 'DELETE' }); toast('Пункт удалён', 'ok'); renderItems(); }
                            catch (e) { toast(e.message, 'err'); } }, 'Удалить');
          });
        },
      });
    };
    await renderItems();
  };

  await render();
}
