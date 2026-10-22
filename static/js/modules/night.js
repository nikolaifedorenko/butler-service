/* ══════════════════════════════════════════════════════════════════════
   РАЗДЕЛ «НОЧНОЙ ОТЧЁТ» — смена 20:00–08:00: зоны обхода → объекты → чек-листы,
   отметки ОК/Не ОК с комментариями и фото, перехваты областей, шаг
   «Проверка электрокаров», закрытие смены, архив и выгрузка DOCX/PDF.
   Отдельный файл: раздел добавлен позже основного интерфейса.
   Хелперы app.js: $ $$ esc api multipartApi openModal closeModal confirmDialog
   toast downloadBlob hhmm dateRu poll state.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

/* Навигация обхода (v2): зона → объект → чек-лист.
   zoneId: null — экран зон; 0 — объекты «Без зоны»; иначе id зоны.
   areaId: id объекта, чей чек-лист открыт (null — список объектов). */
const nightState = { reportId: null, today: null, areas: null,
  zoneId: null, areaId: null, q: '', filter: 'all',
  dictTab: 'zones', dictZone: null, dictArea: null,
  /* экран «Недостатки смены»: выбор позиций и показ отправленных/исправленных */
  defectsSelected: new Set(), defectsShowSent: false };

/* dateRu() из app.js рассчитан на «YYYY-MM-DD»; для datetime берём только дату */
const dRu = iso => (iso ? dateRu(String(iso).slice(0, 10)) : '');

const NIGHT_SECTION_BADGE = { free: 'muted', taken: 'warn', done: 'ok' };
const NIGHT_ANSWER_BADGE = { ok: 'ok', bad: 'danger', '': 'muted' };


/* ─────────────────────────── раздел ─────────────────────────── */
registerModule({ views: { night: loadNight },
  screens: { night: { render: renderNightDictScreen, icon: 'moon' } } });

async function loadNight() {
  $('#view-night').innerHTML = `
    <div class="page-head">
      <div><h2>Ночной отчёт</h2><div class="sub" id="night-sub">Смена 20:00–08:00 · отчёт относится к дате начала смены</div></div>
      <div class="spacer"></div>
      <button class="btn btn-sm" id="night-refresh">Обновить</button>
      <button class="btn btn-sm btn-ghost hidden" id="night-today-btn">К текущей смене</button>
      <button class="btn btn-sm btn-ghost hidden" id="night-archive">Архив</button>
      <button class="btn btn-sm btn-ghost hidden" id="night-defects">Недостатки</button>
      <button class="btn btn-sm btn-ghost hidden" id="night-dict" title="Настройки → Ночной обход">Справочник ↗</button>
      <button class="btn btn-sm btn-ghost hidden" id="night-docx">DOCX</button>
      <button class="btn btn-sm btn-ghost hidden" id="night-pdf">PDF</button>
      <button class="btn btn-sm btn-danger hidden" id="night-close">Закрыть смену</button>
      <button class="btn btn-sm btn-ghost hidden" id="night-reopen">Переоткрыть</button>
    </div>
    <div id="night-body"><div class="empty">Загрузка…</div></div>`;

  $('#night-refresh').onclick = () => fetchNight();
  $('#night-today-btn').onclick = () => { nightState.reportId = null; fetchNight(); };
  $('#night-archive').onclick = () => nightArchiveModal();
  /* 19.10.2026: справочник переехал в «Настройки → Ночной обход» — кнопка ведёт туда
     (единственное место правки); видна только тем, кто может войти в Настройки. */
  $('#night-dict').onclick = () => settingsOpen('night');
  $('#night-defects').onclick = () => nightDefectsModal();
  $('#night-docx').onclick = () => exportNight('docx');
  $('#night-pdf').onclick = () => exportNight('pdf');
  $('#night-close').onclick = () => closeReportModal();
  $('#night-reopen').onclick = () => reopenReport();

  await fetchNight();
  poll('night', () => { if (state.view === 'night') fetchNight(true); });
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

/* ─────────────── три уровня обхода: зоны → объекты → чек-лист объекта ─────────────── */
function nightCrumb(parts) {
  return `<div class="crumb">${parts.map((x, i) => (i === parts.length - 1
    ? `<b>${esc(x.t)}</b>` : `<a data-crumb="${x.go}">${esc(x.t)}</a>`))
    .join('<span class="sep">/</span>')}</div>`;
}

/* id зоны у объекта; 0 — «Без зоны» (в отчёте zone_id может быть null) */
function zoneKeyOf(a) { return a.zone_id || 0; }

function nightZoneBar(z) {
  const t = z.items_total || 0;
  const ok = Math.max(0, z.items_answered - z.items_bad);
  const w = n => (t ? Math.round(n / t * 100) : 0);
  return `<div class="zone-bar" title="отмечено ${z.items_answered} из ${t} пунктов">
    <i class="ok" style="width:${w(ok)}%"></i><i class="bad" style="width:${w(z.items_bad)}%"></i>
    <i class="todo" style="width:${w(t - z.items_answered)}%"></i></div>`;
}

function nightZoneCard(z) {
  const cls = z.items_bad ? 'bad' : (z.areas_total && z.done === z.areas_total ? 'done' : '');
  const zid = z.zone_id || 0;
  return `<div class="panel night-zone ${cls}" data-zone="${zid}">
    <div class="night-area-head">
      <div><b>${esc(z.name)}</b> <span class="badge muted">${z.areas_total} объектов</span>
        ${z.areas_total ? '' : '<span class="badge warn">объектов нет</span>'}</div>
      <div class="night-area-prog">пунктов ${z.items_answered} / ${z.items_total}
        ${z.items_bad ? `<span class="badge danger">Не ОК: ${z.items_bad}</span>` : ''}
        ${z.items_unanswered ? `<span class="badge muted">не отмечено ${z.items_unanswered}</span>` : ''}</div>
    </div>
    ${nightZoneBar(z)}
    <div class="row-actions">
      <span class="badge ok">закрыто ${z.done}</span>
      ${z.taken ? `<span class="badge warn">в работе ${z.taken}</span>` : ''}
      ${z.free ? `<span class="badge muted">свободно ${z.free}</span>` : ''}
      <div style="flex:1"></div>
      <button class="btn btn-sm btn-primary" data-zone-open="${zid}">Объекты зоны →</button>
    </div>
  </div>`;
}

function nightObjectRow(a, rep) {
  const mine = a.taken_by === state.user?.id;
  const label = a.status === 'done' ? 'Посмотреть'
    : (a.status === 'taken' && !mine ? 'Перехватить' : (mine ? 'Продолжить' : 'Взять в работу'));
  return `<div class="panel night-object ${a.status}" data-area="${a.id}">
    <div class="night-area-head">
      <div><b>${esc(a.name)}</b>
        <span class="badge ${NIGHT_SECTION_BADGE[a.status] || 'muted'}">${esc(a.status_title)}</span>
        ${mine ? '<span class="badge ok">ведёте вы</span>'
          : (a.taken_by_name ? `<span class="badge info">${esc(a.taken_by_name)}</span>` : '')}</div>
      <div class="night-area-prog">${a.items_answered} / ${a.items_total}
        ${a.items_bad ? `<span class="badge danger">Не ОК: ${a.items_bad}</span>` : ''}
        ${a.items_unanswered ? `<span class="badge muted">не отмечено ${a.items_unanswered}</span>` : ''}
        ${a.closed_at ? `<span class="muted">закрыт ${esc(hhmm(a.closed_at))}</span>` : ''}</div>
    </div>
    ${rep.readonly ? `<div class="row-actions" style="margin-top:8px">
        <button class="btn btn-sm btn-ghost" data-sec-open="${a.id}">Посмотреть</button></div>`
      : `<div class="row-actions" style="margin-top:8px">
        <button class="btn btn-sm ${mine || a.status === 'done' ? 'btn-ghost' : 'btn-accent'}"
          data-sec-open="${a.id}">${label}</button>
        ${a.status === 'done'
          ? `<button class="btn btn-sm btn-ghost" data-sec-reopen="${a.id}">Переоткрыть</button>`
          : `<button class="btn btn-sm" data-sec-close="${a.id}">Завершить объект</button>`}</div>`}
  </div>`;
}

function renderNight(rep, note) {
  const show = (id, on) => $(id)?.classList.toggle('hidden', !on);
  show('#night-archive', true);
  show('#night-dict', can('settings.view'));
  show('#night-defects', !!rep);
  /* счётчик недостатков, которые можно отправить: видно до открытия экрана */
  const dfBtn = $('#night-defects');
  if (dfBtn && rep) {
    const sendable = (rep.areas || []).reduce((n, a) => n
      + (a.items || []).filter(i => i.answer === 'bad' && !i.dispatched_at).length, 0);
    dfBtn.textContent = sendable ? `Недостатки · ${sendable}` : 'Недостатки';
  }
  show('#night-today-btn', !!nightState.reportId);
  show('#night-docx', !!rep);
  show('#night-pdf', !!rep);
  /* закрытие/переоткрытие смены — право night.close из каталога (этап B, 20.10.2026),
     а не проверка роли: базово оно у supervisor+, но выдаётся и снимается грантами */
  show('#night-close', !!rep && !rep.readonly && can('night.close'));
  show('#night-reopen', !!rep && rep.readonly && can('night.close'));

  if (!rep) {
    $('#night-sub').textContent = 'Смена 20:00–08:00 · отчёт относится к дате начала смены';
    $('#night-body').innerHTML = `<div class="panel"><h3 class="panel-title">Отчёта пока нет</h3>
      <p class="hint" style="margin:0">${esc(note || 'Ночная смена ещё не началась — отчёт появится в 20:00.')}</p>
      <p class="hint">Архив прошлых смен доступен по кнопке «Архив» справа вверху.</p></div>`;
    return;
  }

  /* переоткрытый вручную отчёт автоматически не закроется — не обещаем дедлайн */
  $('#night-sub').textContent = rep.reopened_at
    ? `Смена ${dateRu(rep.date)} · ${rep.shift_label || ''} · переоткрыта вручную — автозакрытие отключено`
    : `Смена ${dateRu(rep.date)} · ${rep.shift_label || ''} · автозакрытие ${hhmm(rep.deadline)}`;
  const p = rep.progress || { total: 0, done: 0, taken: 0, free: 0 };
  const areas = (rep.areas || []).filter(a => !a.is_cars);
  const carsSection = (rep.areas || []).find(a => a.is_cars);
  const zones = rep.zones || [];
  const bad = areas.reduce((s, a) => s + (a.items_bad || 0), 0);
  const unanswered = areas.reduce((s, a) => s + (a.items_unanswered || 0), 0);

  /* ── уровень 3: чек-лист объекта ── */
  const area = areas.find(a => a.id === nightState.areaId) || null;
  if (nightState.areaId && !area) nightState.areaId = null;    // объекта в отчёте больше нет
  if (area) {
    $('#night-body').innerHTML =
      nightCrumb([{ t: 'Ночной отчёт', go: 'zones' }, { t: area.zone_name || 'Без зоны', go: 'zone' },
                  { t: area.name }]) +
      nightAreaCard(area, rep) +
      `<p class="hint">Пункты объекта — из шаблона его зоны (индивидуальные правки видны в справочнике).
      Закрыть объект можно и с неотмеченными пунктами — после подтверждения.</p>`;
    bindNight(rep, carsSection);
    return;
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
    $('#night-body').innerHTML =
      nightCrumb([{ t: 'Ночной отчёт', go: 'zones' }, { t: z.name }]) + `
      <div class="page-head" style="margin-bottom:10px">
        <div><h2 style="margin:0">${esc(z.name)}</h2>
          <div class="sub">объектов ${z.areas_total} · закрыто ${z.done} · в работе ${z.taken}
            · пунктов ${z.items_answered} / ${z.items_total}
            ${z.items_bad ? `· <b style="color:var(--danger)">Не ОК: ${z.items_bad}</b>` : ''}</div></div>
        <div class="spacer"></div>
        ${rep.readonly ? '' : `<button class="btn btn-sm" id="night-first-free">К первому незакрытому</button>`}
      </div>
      ${nightZoneBar(z)}
      ${(rep.interceptions || []).length ? `<div class="panel"><h3 class="panel-title">Перехваты областей</h3>
        <div class="history">${rep.interceptions.map(i => `<div class="history-item">
          <div class="ts">${esc(i.ts ? dRu(i.ts) + ' ' + hhmm(i.ts) : '')}</div>
          <div class="what"><b>${esc(i.area_name)}</b>: ${esc(i.from_user_name || '—')} → ${esc(i.to_user_name || '—')}</div>
        </div>`).join('')}</div></div>` : ''}
      <div class="toolbar">
        <div class="seg">${[['all', 'Все'], ['free', 'Свободны'], ['taken', 'В работе'],
                           ['done', 'Закрыты'], ['bad', 'С замечаниями']]
          .map(([k, t]) => `<button data-ofilter="${k}" class="${nightState.filter === k ? 'active' : ''}">${t}</button>`).join('')}</div>
        <input type="search" id="night-obj-q" placeholder="Поиск по объектам…"
          value="${esc(nightState.q)}" style="max-width:240px">
        <div class="spacer"></div>
        <span class="hint" style="margin:0">показано ${filtered.length} из ${list.length}</span>
      </div>
      <div class="night-objects">${filtered.map(a => nightObjectRow(a, rep)).join('') ||
        '<div class="empty">Объектов в зоне нет или ничего не найдено</div>'}</div>
      <p class="hint">Объект ведёт один человек: «Взять в работу» закрепляет его за вами, чужой — только
      через подтверждение (перехват фиксируется в отчёте).</p>`;
    bindNight(rep, carsSection);
    return;
  }

  /* ── уровень 1: зоны ── */
  $('#night-body').innerHTML = `
    ${rep.readonly ? `<div class="ro-banner">Смена закрыта ${rep.closed_at ? dRu(rep.closed_at) + ' ' + hhmm(rep.closed_at) : ''} ·
      итог: ${esc(rep.result_title || '—')} · правки недоступны</div>` : ''}
    <div class="stat-grid">
      <div class="stat"><div class="k">Зон</div><div class="v">${zones.length}</div></div>
      <div class="stat"><div class="k">Объектов</div><div class="v">${p.total}</div></div>
      <div class="stat accent"><div class="k">Объектов закрыто</div><div class="v">${p.done} <small>/ ${p.total}</small></div></div>
      <div class="stat warn"><div class="k">В работе</div><div class="v">${p.taken}</div></div>
      <div class="stat danger"><div class="k">Замечаний (Не ОК)</div><div class="v">${bad}</div></div>
      <div class="stat info"><div class="k">Не отмечено пунктов</div><div class="v">${unanswered}</div></div>
      <div class="stat ${rep.cars_step_done ? '' : 'warn'}"><div class="k">Электрокары</div>
        <div class="v">${rep.cars_step_done ? 'готово' : 'не завершено'}</div></div>
    </div>

    ${carsSection ? `<div class="panel"><h3 class="panel-title">Шаг «Проверка электрокаров»
        <span class="badge ${carsSection.status === 'done' ? 'ok' : 'warn'}">${esc(carsSection.status_title)}</span></h3>
      <p class="hint" style="margin:0 0 10px">Отдельный шаг обхода (не зона): где кар, заряд, тент, состояние,
      «кар найден на месте», перепарковка и фото. Замечания попадают супервайзеру, состояние карточек
      каров обновляется автоматически.</p>
      <button class="btn btn-primary" id="night-cars-open">${rep.cars_step_done ? 'Посмотреть обход' : 'Проверить электрокары'}</button>
      ${carsSection.closed_at ? `<span class="hint"> · завершено в ${esc(hhmm(carsSection.closed_at))}</span>` : ''}
    </div>` : ''}

    ${(rep.interceptions || []).length ? `<div class="panel"><h3 class="panel-title">Перехваты областей</h3>
      <div class="history">${rep.interceptions.map(i => `<div class="history-item">
        <div class="ts">${esc(i.ts ? dRu(i.ts) + ' ' + hhmm(i.ts) : '')}</div>
        <div class="what"><b>${esc(i.area_name)}</b>: ${esc(i.from_user_name || '—')} → ${esc(i.to_user_name || '—')}</div>
      </div>`).join('')}</div></div>` : ''}

    ${zones.length ? `<div class="night-zones">${zones.map(z => nightZoneCard(z)).join('')}</div>`
      : `<div class="empty">Зоны обхода не настроены — добавьте их в «Настройки → Ночной обход» (кнопка «Справочник ↗» справа вверху)</div>`}

    <p class="hint">Обход: зона → объект → чек-лист. Чек-лист задаётся на зону, поэтому у всех однотипных
    объектов он одинаковый; индивидуальные особенности объекта настраиваются в справочнике.</p>`;

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
      ${it.service_name ? `<span class="badge info" title="Ответственная служба: недостаток уйдёт ей">⚖ ${esc(it.service_name)}</span>` : ''}
      ${it.answered_by_name ? `<small class="muted">· ${esc(it.answered_by_name)}${it.answered_at ? ' ' + esc(hhmm(it.answered_at)) : ''}</small>` : ''}
    </div>
    <div class="night-item-acts">
      ${rep.readonly
        ? `<span class="badge ${NIGHT_ANSWER_BADGE[it.answer] || 'muted'}">${esc(it.answer_title)}</span>`
        : `<button class="btn btn-sm ${it.answer === 'ok' ? 'btn-primary' : 'btn-ghost'}" data-ans="ok" data-id="${it.id}">ОК</button>
           <button class="btn btn-sm ${it.answer === 'bad' ? 'btn-danger' : 'btn-ghost'}" data-ans="bad" data-id="${it.id}">Не ОК</button>
           <button class="btn btn-sm btn-ghost" data-cmt="${it.id}" title="Комментарий">💬${it.comment ? ' •' : ''}</button>
           <label class="btn btn-sm btn-ghost" title="Добавить фото">📷
             <input type="file" accept="image/*" data-photo="${it.id}" class="hidden-file"></label>
           <label class="btn btn-sm btn-ghost" title="Снять видео">🎥
             <input type="file" accept="video/*" capture="camcorder" data-video="${it.id}" class="hidden-file"></label>`}
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

  /* фото и видео грузятся одним маршрутом: тип сервер определяет по содержимому */
  $$('[data-photo], [data-video]').forEach(inp => inp.onchange = async () => {
    const f = inp.files?.[0];
    if (!f) return;
    const fd = new FormData();
    fd.append('file', f, f.name);
    try {
      const r = await multipartApi(`/api/night/items/${inp.dataset.photo || inp.dataset.video}/photo`, fd);
      toast(r?.photo?.media_type === 'video' ? 'Видео добавлено' : 'Фото добавлено', 'ok'); reload();
    } catch (e) { toast(e.message, 'err'); }
  });

  bindPhotoDelete($('#night-body'), reload);

  /* переходы между уровнями: зоны → объекты → чек-лист (данные уже в rep) */
  $$('[data-zone-open]').forEach(b => b.onclick = () => {
    nightState.zoneId = Number(b.dataset.zoneOpen); nightState.areaId = null;
    nightState.q = ''; nightState.filter = 'all';
    renderNight(rep, '');
  });
  $$('[data-crumb]').forEach(b => b.onclick = () => {
    if (b.dataset.crumb === 'zones') { nightState.zoneId = null; nightState.areaId = null; }
    else nightState.areaId = null;
    renderNight(rep, '');
  });
  $$('[data-ofilter]').forEach(b => b.onclick = () => {
    nightState.filter = b.dataset.ofilter; renderNight(rep, '');
  });
  const qInp = $('#night-obj-q');
  if (qInp) qInp.oninput = e => {
    nightState.q = e.target.value.trim(); renderNight(rep, '');
    const el = $('#night-obj-q');
    if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); }
  };
  /* открыть объект: сразу берём его в работу (или перехватываем с подтверждением) */
  $$('[data-sec-open]').forEach(b => b.onclick = async () => {
    const id = Number(b.dataset.secOpen);
    const a = (rep.areas || []).find(x => x.id === id);
    nightState.areaId = id;
    if (!rep.readonly && a && a.status !== 'done') await sectionTake(id, false, reload);
    else renderNight(rep, '');
  });
  const firstFree = $('#night-first-free');
  if (firstFree) firstFree.onclick = () => {
    const list = (rep.areas || []).filter(a => !a.is_cars && zoneKeyOf(a) === nightState.zoneId
      && a.status !== 'done');
    if (!list.length) { toast('В зоне все объекты закрыты', 'ok'); return; }
    nightState.areaId = list[0].id;
    sectionTake(list[0].id, false, reload);
  };

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
              ${k?.taken_after_check ? '<span class="badge warn">взят после проверки</span>' : ''}
              ${k?.moved ? '<span class="badge info" title="батлер переставил кар">перепаркован</span>' : ''}
              ${k?.photos?.length ? `<span class="badge info" title="фото отметки">📷 ${k.photos.length}</span>` : ''}</div>
            <div class="desc">${esc(nightCarPlace(c, k))} · заряд: ${esc(k ? (k.charge || '—') : (c.charge_title || '—'))}
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
        $$('[data-car-check]', m).forEach(b => b.onclick = async () => {
          try { await nightCarCheckModal(rep, Number(b.dataset.carCheck), render); }
          catch (err) { toast(err.message || String(err), 'err'); }
        });
        const fin = m.querySelector('[data-finish]');
        if (fin) fin.onclick = () => carsFinish(rep, st.unchecked, async () => { closeModal(); if (after) await after(); });
      },
    });
  };
  await render();
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
  /* места два: где батлер нашёл кар и куда переставил (у отметок до 19.10.2026
     было одно поле location — берём его как «где нашёл», если перепарковки не было) */
  const foundLoc = k ? (k.found_location || (k.moved ? '' : k.location) || '') : (c.location || '');
  const newLoc = k?.moved ? (k.location || '') : '';
  const reopen = () => nightCarCheckModal(rep, carId, after);

  openModal({
    title: `Кар №${c.number} — ночной обход`,
    subtitle: `${c.status_title}${c.holder_name ? ' · держит ' + c.holder_name : ''} · ${c.location || 'место не указано'}`,
    wide: true,
    body: `
      <div class="check-list" style="max-height:none;margin-bottom:10px">
        <label class="chk"><input type="checkbox" id="nc-found" ${!k || k.found ? 'checked' : ''}> Кар найден на месте</label>
      </div>
      <p class="hint hidden" id="nc-notfound" style="margin:0 0 10px;color:var(--danger)">Кар не найден — отметка
      уйдёт в замечания супервайзеру, карточка кара не изменится. Напишите в комментарии, где кар (если известно).</p>
      <div class="grid-2">
        <label class="field"><span id="nc-found-loc-label">Где нашёл</span>
          <select id="nc-found-location"><option value="">— не указывать —</option>${locationOptions(foundLoc)}</select></label>
        <label class="field"><span>Заряд</span>
          <select id="nc-charge"><option value="">— не отмечать —</option>${CHARGE_OPTS.map(([v, t]) =>
            `<option value="${v}" ${v === pick(c.charge, k?.charge) ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
      </div>
      <label class="chk" id="nc-moved-row" style="margin-top:8px">
        <input type="checkbox" id="nc-moved" ${newLoc ? 'checked' : ''}> Перепаркован на другое место</label>
      <label class="field hidden" id="nc-newloc-row"><span>Куда переставил</span>
        <select id="nc-location"><option value="">— не указывать —</option>${locationOptions(newLoc)}</select></label>
      <div class="opt-group-title">Состояние кара</div>
      <div class="check-list" id="nc-state" style="max-height:none">
        <label class="chk"><input type="checkbox" id="nc-ok" ${pick(c.condition, k?.condition) !== 'bad' ? 'checked' : ''}> Технически исправен</label>
        <label class="chk"><input type="checkbox" id="nc-clean" ${pick(c.clean, k?.clean) ? 'checked' : ''}> Чистый</label>
        <label class="chk"><input type="checkbox" id="nc-things" ${pick(c.trash, k?.trash) ? 'checked' : ''}> В салоне вещи</label>
        <label class="chk"><input type="checkbox" id="nc-canopy" ${pick(c.canopy, k?.canopy) ? 'checked' : ''}> Тент</label>
        <label class="chk"><input type="checkbox" id="nc-oncharge" ${pick(c.on_charge, k?.on_charge) ? 'checked' : ''}> Заряжается</label>
      </div>
      <label class="field" style="margin-top:12px"><span>Комментарий (что случилось, куда поставили)</span>
        <textarea id="nc-comment" rows="2" maxlength="2000" placeholder="Например: кар не на месте, тент снят, оставлен у главного входа">${esc(k?.comment || '')}</textarea></label>
      ${k?.photos?.length ? `<div class="field" style="margin-top:12px"><span>Фото отметки</span>
        <div class="thumbs">${k.photos.map(photoThumb).join('')}</div></div>` : ''}
      ${photoPickHtml('nc')}
      <p class="hint">Снятая галочка «Технически исправен» переводит кар в статус «на обслуживании»
      (снимает менеджер или администратор); «кар не найден» и «не исправен» попадают в замечания
      супервайзеру. «В салоне вещи», «Тент», «Заряжается» — факты: они видны в карточке кара.
      «Перепаркован на другое место» — тоже факт: место в карточке кара обновится, а переход
      «где нашёл → куда переставил» супервайзер увидит в обходе и в выгрузке DOCX/PDF.
      Новый снимок добавляется к отметке, прежние удаляются крестиком.</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
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
      bindPhotoDelete(m, reopen);
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
    body: `<div class="table-wrap" style="max-height:56vh"><table class="data responsive">
        <thead><tr><th>Дата</th><th>Статус</th><th>Итог</th><th>Области</th><th>Электрокары</th><th>Закрыт</th><th></th></tr></thead>
        <tbody>${reports.map(r => `<tr>
          <td data-label="Дата"><b>${esc(dateRu(r.date))}</b><small>${esc(r.shift_label || '')}</small></td>
          <td data-label="Статус"><span class="badge ${r.status === 'closed' ? 'ok' : 'warn'}">${r.status === 'closed' ? 'закрыт' : (r.reopened_at ? 'открыт · переоткрыт' : 'открыт')}</span></td>
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

/* ─────────── экран Настроек «Ночной обход» (19.10.2026): зоны · объекты · чек-листы · службы ───────────
   Единственное место правки справочника обхода — экран в «Настройках» (группа
   «Объект», адрес #/settings/night; docs/PROPOSAL-SETTINGS-IA-2026-10-19.md).
   Заменил модалку «Справочник» из раздела «Ночной отчёт» (4 вкладки и
   модалка-в-модалке): зоны — список слева (master-detail), справа вкладки
   «Объекты / Чек-листы / Службы»; модалки правки переиспользованы прежние.
   Кнопка «Справочник» в разделе стала deep-link'ом сюда (settingsOpen).

   Права: видимость экрана — night.view (и вход в «Настройки»), правки —
   night.edit: ключ каталога прав вместо прежней ролевой проверки is_manager
   (базово выдан admin/manager/supervisor — поведение не изменилось, но право
   можно выдать/снять грантом в «Настройках → Права доступа»).
   Вызывается из реестра modules/settings.js (подключается после этого файла). */
async function renderNightDictScreen(host) {
  const render = async () => {
    const [zr, ar, sr] = await Promise.all([api('/api/night/zones'), api('/api/night/areas'),
                                             api('/api/night/services')]);
    const zones = zr.zones || [], areas = ar.areas || [], services = sr.services || [];
    const canEdit = !!zr.can_edit;
    if (!['areas', 'items', 'services'].includes(nightState.dictTab)) nightState.dictTab = 'areas';
    const t = nightState.dictTab;
    if (t !== 'services' && zones.length && !zones.some(z => z.id === nightState.dictZone)) {
      nightState.dictZone = zones[0].id; nightState.dictArea = null;
    }
    host.innerHTML = `
      ${settingsHead('Ночной обход',
        'Зоны → объекты → чек-листы → службы. Шаблон задаётся на зону, индивидуальные пункты — у объекта. Сам обход — в разделе «Ночной отчёт».',
        `<div class="seg">${[['areas', 'Объекты'], ['items', 'Чек-листы'], ['services', 'Службы']]
          .map(([k, l]) => `<button data-dtab="${k}" class="${t === k ? 'active' : ''}">${l}</button>`).join('')}</div>
         <button class="btn btn-sm btn-ghost" id="nd-to-night" title="Открыть раздел «Ночной отчёт»">К обходу ↗</button>`)}
      <div class="dict-banner"><span>🌙</span><span>Правки применяются к <b>ещё не начатым объектам</b> —
        в текущей и следующих сменах; чек-листы начатых объектов и закрытых смен зафиксированы
        снимком в отчёте и не изменятся.</span></div>
      ${canEdit ? '' : '<div class="dict-banner gold"><span>🔒</span><span>Только просмотр: для правок нужно право <b>night.edit</b> (выдаётся в «Настройки → Права доступа»).</span></div>'}
      <div class="dict-md">
        <div class="dict-zones">
          <div class="panel-title">Зоны обхода</div>
          ${zones.map(z => `
            <div class="dict-zone${z.id === nightState.dictZone && t !== 'services' ? ' active' : ''}" data-dz="${z.id}">
              <div class="dz-name">${esc(z.name)}${z.active ? '' : ' <span class="badge muted">отключена</span>'}</div>
              <div class="dz-meta">объектов: ${z.areas_total} · пунктов шаблона: ${z.items_total}</div>
              ${canEdit ? `<div class="row-actions">
                <button class="btn btn-sm btn-ghost" data-zedit="${z.id}">Править</button>
                <button class="btn btn-sm btn-ghost" data-zdel="${z.id}">Отключить</button></div>` : ''}
            </div>`).join('') || '<div class="empty" style="padding:14px">Зон нет — добавьте первую</div>'}
          ${canEdit ? `<div class="opt-group-title">Новая зона</div>
            <div style="display:grid;gap:8px">
              <input type="text" id="nz-name" maxlength="160" placeholder="Название зоны (например: Семейные виллы)">
              <div style="display:flex;gap:8px">
                <input type="number" id="nz-order" value="100" title="Порядок" style="width:96px;flex:none">
                <button class="btn btn-primary" id="nz-add" style="flex:1">Добавить зону</button></div></div>` : ''}
          <p class="hint">Зона — первый уровень обхода. Чек-лист задаётся на зону и действует
            для всех её объектов; отключение зоны не трогает историю закрытых смен.</p>
        </div>
        <div id="dict-host">${t === 'areas' ? dictAreasHtml(zones, areas, canEdit)
          : t === 'services' ? dictServicesHtml(services, canEdit)
          : '<div class="empty">Загрузка…</div>'}</div>
      </div>`;
    bindNightDictScreen(host, zones, canEdit, render);
    if (t === 'areas') bindDictAreas(host, zones, areas, canEdit, render);
    if (t === 'services') bindDictServices(host, services, canEdit, render);
    if (t === 'items') await dictItemsTab(host, zones, services, canEdit, render);
  };
  await render();
}

function bindNightDictScreen(host, zones, canEdit, render) {
  $$('[data-dtab]', host).forEach(b => b.onclick = () => { nightState.dictTab = b.dataset.dtab; render(); });
  const toNight = $('#nd-to-night', host);
  if (toNight) toNight.onclick = () => navigate('night');
  $$('[data-dz]', host).forEach(row => row.onclick = e => {
    if (e.target.closest('button')) return;      /* «Править»/«Отключить» — не выбор зоны */
    nightState.dictZone = Number(row.dataset.dz);
    nightState.dictArea = null;
    if (nightState.dictTab === 'services') nightState.dictTab = 'areas';
    render();
  });
  const add = $('#nz-add', host);
  if (add) add.onclick = async () => {
    const name = $('#nz-name').value.trim();
    if (!name) return toast('Введите название зоны', 'warn');
    try {
      const r = await api('/api/night/zones', { method: 'POST',
        body: { name, sort_order: Number($('#nz-order').value) || 100, active: true } });
      nightState.dictZone = r.id; nightState.dictTab = 'areas';
      toast(`Зона «${name}» добавлена`, 'ok'); render();
    } catch (e) { toast(e.message, 'err'); }
  };
  $$('[data-zedit]', host).forEach(b => b.onclick = () =>
    nightZoneEditModal(zones.find(z => z.id === Number(b.dataset.zedit)), render));
  $$('[data-zdel]', host).forEach(b => b.onclick = () => {
    const z = zones.find(x => x.id === Number(b.dataset.zdel));
    confirmDialog('Отключить зону?',
      `«${z.name}» перестанет предлагаться в справочниках; объекты зоны (${z.areas_total}) останутся — `
      + 'отключите их отдельно, если они больше не проверяются. История закрытых смен сохранится.',
      async () => {
        try { const r = await api(`/api/night/zones/${z.id}`, { method: 'DELETE' });
          toast(`Зона отключена (объектов осталось: ${r.areas_left})`, 'ok'); render(); }
        catch (e) { toast(e.message, 'err'); }
      }, 'Отключить');
  });
}

function nightZoneEditModal(z, after) {
  openModal({
    title: 'Зона: ' + z.name,
    body: `<label class="field"><span>Название</span>
        <input type="text" id="ze-name" value="${esc(z.name)}" maxlength="160"></label>
      <div class="grid-2">
        <label class="field"><span>Порядок</span><input type="number" id="ze-order" value="${z.sort_order}"></label>
        <label class="field"><span>Активна</span><select id="ze-active">
          <option value="1" ${z.active ? 'selected' : ''}>да</option>
          <option value="0" ${z.active ? '' : 'selected'}>нет</option></select></label>
      </div>
      <p class="hint">Объектов в зоне: ${z.areas_total} · пунктов шаблона: ${z.items_total}.
      Переименование зоны обновит её название в открытых сменах; закрытые останутся как есть.</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Сохранить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        try {
          await api(`/api/night/zones/${z.id}`, { method: 'PUT', body: {
            name: $('#ze-name').value.trim(), sort_order: Number($('#ze-order').value) || 100,
            active: $('#ze-active').value === '1' } });
          closeModal(); toast('Зона сохранена', 'ok'); if (after) after();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ── вкладка «Объекты» ── */
function zoneOptions(zones, selected, placeholder) {
  return `<option value="">${esc(placeholder || '— не выбрано —')}</option>`
    + zones.map(z => `<option value="${z.id}" ${z.id === selected ? 'selected' : ''}>${esc(z.name)}</option>`).join('');
}

function dictAreasHtml(zones, areas, canEdit) {
  const zid = nightState.dictZone;
  const list = areas.filter(a => !zid || a.zone_id === zid);
  return `
    <div class="toolbar" style="margin-bottom:10px">
      <label class="field" style="margin:0;min-width:230px"><span>Зона</span>
        <select id="da-zone">${zoneOptions(zones, zid, '— все зоны —')}</select></label>
      <div class="spacer"></div>
      <span class="hint" style="margin:0">объектов: ${list.length}</span></div>
    ${canEdit ? `<div class="grid-3" style="margin-bottom:10px">
        <label class="field"><span>Новый объект</span>
          <input type="text" id="da-name" maxlength="160" placeholder="Вилла 4013"></label>
        <label class="field"><span>Зона</span><select id="da-new-zone">${zoneOptions(zones, zid)}</select></label>
        <label class="field"><span>Порядок</span><input type="number" id="da-order" value="100"></label></div>
      <div class="row-actions" style="margin-bottom:14px">
        <button class="btn btn-primary" id="da-add">Добавить объект</button></div>
      <div class="opt-group-title">Серия однотипных объектов</div>
      <div class="grid-3" style="margin-bottom:10px">
        <label class="field"><span>Префикс</span><input type="text" id="db-prefix" placeholder="Вилла "></label>
        <label class="field"><span>Первый номер</span><input type="number" id="db-start" value="4013"></label>
        <label class="field"><span>Количество</span><input type="number" id="db-count" value="6" min="1" max="200"></label></div>
      <div class="row-actions" style="margin-bottom:14px">
        <label class="field" style="margin:0 12px 0 0;min-width:210px"><span>Зона серии</span>
          <select id="db-zone">${zoneOptions(zones, zid)}</select></label>
        <button class="btn" id="db-add">Создать серию</button></div>` : ''}
    <div class="check-list" style="max-height:38vh">${list.map(a => `
      <div class="rule-row" style="grid-template-columns:1fr auto">
        <div><div class="lbl">${esc(a.name)} ${a.active ? '' : '<span class="badge muted">отключён</span>'}</div>
          <div class="desc">зона: ${esc(a.zone_name || '—')} · чек-лист объекта: ${a.effective_total}
            (своих пунктов: ${a.items_total})</div></div>
        <div class="row-actions">
          <button class="btn btn-sm btn-ghost" data-acheck="${a.id}">Чек-лист</button>
          <button class="btn btn-sm btn-ghost" data-aitems="${a.id}">Свои пункты</button>
          ${canEdit ? `<button class="btn btn-sm btn-ghost" data-aedit="${a.id}">Править</button>
          <button class="btn btn-sm btn-ghost" data-adel="${a.id}">Удалить</button>` : ''}
        </div></div>`).join('') || '<div class="empty">Объектов нет</div>'}</div>
    <p class="hint">Удаление объекта мягкое: он отключается и убирается из ещё не начатых смен,
    история закрытых смен сохраняется.</p>`;
}

function bindDictAreas(m, zones, areas, canEdit, render) {
  const zf = m.querySelector('#da-zone');
  if (zf) zf.onchange = () => { nightState.dictZone = Number(zf.value) || null; render(); };
  const add = m.querySelector('#da-add');
  if (add) add.onclick = async () => {
    const name = $('#da-name').value.trim();
    if (!name) return toast('Введите название объекта', 'warn');
    const zoneId = Number($('#da-new-zone').value) || null;
    const zone = zones.find(z => z.id === zoneId);
    try {
      await api('/api/night/areas', { method: 'POST', body: {
        name, zone_id: zoneId, category: zone ? zone.name : '',
        sort_order: Number($('#da-order').value) || 100, active: true } });
      toast(`Объект «${name}» добавлен`, 'ok'); render();
    } catch (e) { toast(e.message, 'err'); }
  };
  const bulk = m.querySelector('#db-add');
  if (bulk) bulk.onclick = async () => {
    const zoneId = Number($('#db-zone').value) || null;
    const zone = zones.find(z => z.id === zoneId);
    try {
      const r = await api('/api/night/areas/bulk', { method: 'POST', body: {
        prefix: $('#db-prefix').value, start: Number($('#db-start').value) || 1,
        count: Number($('#db-count').value) || 1, zone_id: zoneId,
        category: zone ? zone.name : '' } });
      toast(`Создано объектов: ${r.created} — чек-лист зоны применится автоматически`, 'ok'); render();
    } catch (e) { toast(e.message, 'err'); }
  };
  $$('[data-acheck]', m).forEach(b => b.onclick = () => {
    const a = areas.find(x => x.id === Number(b.dataset.acheck));
    nightState.dictZone = a.zone_id || nightState.dictZone;
    nightState.dictArea = a.id; nightState.dictTab = 'items'; render();
  });
  $$('[data-aitems]', m).forEach(b => b.onclick = () =>
    nightItemsModal(areas.find(a => a.id === Number(b.dataset.aitems)), render));
  $$('[data-aedit]', m).forEach(b => b.onclick = () =>
    nightAreaEditModal(areas.find(a => a.id === Number(b.dataset.aedit)), zones, render));
  $$('[data-adel]', m).forEach(b => b.onclick = () => {
    const a = areas.find(x => x.id === Number(b.dataset.adel));
    confirmDialog('Удалить объект?',
      `«${a.name}» будет отключён и убран из открытых (ещё не начатых) отчётов. История закрытых смен сохранится.`,
      async () => {
        try { const r = await api(`/api/night/areas/${a.id}`, { method: 'DELETE' });
          toast(`Объект отключён${r.sections_removed ? `, убрано из отчётов: ${r.sections_removed}` : ''}`, 'ok'); render(); }
        catch (e) { toast(e.message, 'err'); }
      }, 'Удалить');
  });
}

function nightAreaEditModal(a, zones, after) {
  openModal({
    title: 'Объект: ' + a.name,
    body: `<label class="field"><span>Название</span>
        <input type="text" id="ae-name" value="${esc(a.name)}" maxlength="160"></label>
      <div class="grid-2">
        <label class="field"><span>Зона обхода</span>
          <select id="ae-zone">${zoneOptions(zones, a.zone_id)}</select></label>
        <label class="field"><span>Порядок</span><input type="number" id="ae-order" value="${a.sort_order}"></label>
      </div>
      <label class="field"><span>Категория (историческая подпись группировки в выгрузке)</span>
        <input type="text" id="ae-cat" value="${esc(a.category || '')}" maxlength="80"></label>
      <label class="chk"><input type="checkbox" id="ae-active" ${a.active ? 'checked' : ''}> Объект активен</label>
      <p class="hint">Смена зоны меняет чек-лист объекта: в открытых сменах, где объект ещё не взят
      в работу, снимок пересобирается; начатые и закрытые не трогаются.</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Сохранить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        const zone = zones.find(z => z.id === (Number($('#ae-zone').value) || null));
        /* категория — историческая подпись группировки; если её не задали, берём название зоны */
        const category = $('#ae-cat').value.trim() || (zone ? zone.name : '');
        try {
          const r = await api(`/api/night/areas/${a.id}`, { method: 'PUT', body: {
            name: $('#ae-name').value.trim(), category,
            zone_id: Number($('#ae-zone').value) || null,
            sort_order: Number($('#ae-order').value) || 100, active: $('#ae-active').checked } });
          closeModal();
          toast(r.sections_refreshed ? `Сохранено · пересобрано смен: ${r.sections_refreshed}` : 'Сохранено', 'ok');
          if (after) after();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ── вкладка «Службы»: получатели недостатков и их каналы доставки ── */
function serviceOptions(services, selected, placeholder = '— не задана —') {
  return `<option value="">${esc(placeholder)}</option>`
    + services.filter(s => s.active || s.id === selected).map(s =>
      `<option value="${s.id}" ${s.id === selected ? 'selected' : ''}>${esc(s.name)}</option>`).join('');
}

function serviceChannels(s) {
  const parts = [];
  if (s.use_telegram) parts.push(s.ready_telegram ? 'чат' : 'чат (не закреплён)');
  if (s.use_email) parts.push(s.ready_email ? 'письмо' : 'письмо (нет ящика)');
  return parts.join(' + ') || 'каналы не выбраны';
}

function dictServicesHtml(services, canEdit) {
  return `
    ${canEdit ? `<div class="grid-2" style="grid-template-columns:1fr 110px auto;margin-bottom:12px">
        <input type="text" id="ns-name" maxlength="160" placeholder="Название службы (например: Хозяйственная служба)">
        <input type="number" id="ns-order" value="100" title="Порядок">
        <button class="btn btn-primary" id="ns-add">Добавить службу</button></div>` : ''}
    <div class="check-list" style="max-height:46vh">${services.map(s => `
      <div class="rule-row" style="grid-template-columns:1fr auto">
        <div><div class="lbl">${esc(s.name)} <small class="muted">порядок ${s.sort_order}</small>
            ${s.active ? '' : ' <span class="badge muted">отключена</span>'}
            ${s.ready ? '' : ' <span class="badge warn" title="Канал выбран, но получатель не заполнен">не готова к отправке</span>'}</div>
          <div class="desc">каналы: ${esc(serviceChannels(s))}${s.email_to ? ` · ящик: ${esc(s.email_to)}` : ''}${s.chat_ids.length ? ` · чатов: ${s.chat_ids.length}` : ''}
            · пунктов закреплено: ${s.items_total}${s.note ? ` · ${esc(s.note)}` : ''}</div></div>
        ${canEdit ? `<div class="row-actions">
          <button class="btn btn-sm btn-ghost" data-sedit="${s.id}">Править</button>
          ${s.active ? `<button class="btn btn-sm btn-ghost" data-sdel="${s.id}">Отключить</button>` : ''}</div>` : ''}
      </div>`).join('') || '<div class="empty">Служб нет — добавьте первую</div>'}</div>
    <p class="hint">Служба — получатель недостатков: закрепляется за пунктом шаблона зоны (вкладка
    «Чек-листы»), а у отдельного объекта её можно переопределить. Каналы — чекбоксы «чат» и «письмо».
    Токен бота, каталог чатов и почтовый сервер настраиваются в общих настройках приложения —
    «Настройки → Чаты и Почта»: транспорт один на всё приложение.</p>`;
}

function bindDictServices(m, services, canEdit, render) {
  const add = m.querySelector('#ns-add');
  if (add) add.onclick = async () => {
    const name = $('#ns-name').value.trim();
    if (!name) return toast('Введите название службы', 'warn');
    try {
      await api('/api/night/services', { method: 'POST', body: {
        name, sort_order: Number($('#ns-order').value) || 100, active: true,
        use_telegram: true, use_email: false, chat_ids: [] } });
      toast('Служба добавлена — укажите каналы и получателей', 'ok'); render();
    } catch (e) { toast(e.message, 'err'); }
  };
  $$('[data-sedit]', m).forEach(b => b.onclick = () =>
    serviceEditModal(services.find(x => x.id === Number(b.dataset.sedit)), render));
  $$('[data-sdel]', m).forEach(b => b.onclick = () => {
    const s = services.find(x => x.id === Number(b.dataset.sdel));
    confirmDialog('Отключить службу?',
      `«${s.name}» перестанет предлагаться в справочнике и не будет участвовать в новых отправках. `
      + `Закреплённых пунктов: ${s.items_total} — их стоит переназначить. История закрытых смен не изменится.`,
      async () => {
        try { await api(`/api/night/services/${s.id}`, { method: 'DELETE' }); toast('Служба отключена', 'ok'); render(); }
        catch (e) { toast(e.message, 'err'); }
      }, 'Отключить');
  });
}

async function serviceEditModal(s, after) {
  /* Чаты закрепляются прямо здесь: каталог общий (Настройки → Чаты и Почта),
     а выбор «какие чаты получают недостатки этой службы» — свойство службы. */
  let chats = [];
  try { chats = (await api('/api/notify/chats')).chats || []; } catch { chats = []; }
  const picked = new Set((s.chat_ids || []).map(Number));
  openModal({
    title: 'Ответственная служба',
    subtitle: s.name,
    wide: true,
    body: `<label class="field"><span>Название</span>
        <input type="text" id="sv-name" value="${esc(s.name)}" maxlength="160"></label>
      <div class="opt-group-title">Каналы доставки</div>
      <label class="chk"><input type="checkbox" id="sv-tg" ${s.use_telegram ? 'checked' : ''}>
        Чат (Telegram)</label>
      <label class="chk"><input type="checkbox" id="sv-mail" ${s.use_email ? 'checked' : ''}>
        Письмо (e-mail)</label>
      <div class="grid-2">
        <label class="field"><span>Ящик службы</span>
          <input type="email" id="sv-to" value="${esc(s.email_to)}" maxlength="200" placeholder="service@resort.example"></label>
        <label class="field"><span>Копия (через запятую)</span>
          <input type="text" id="sv-copy" value="${esc(s.email_copy)}" maxlength="400"></label>
      </div>
      <label class="field"><span>Примечание</span>
        <input type="text" id="sv-note" value="${esc(s.note)}" maxlength="300" placeholder="круглосуточный пост, дежурный инженер…"></label>
      <div class="grid-2">
        <label class="field"><span>Порядок</span><input type="number" id="sv-order" value="${s.sort_order}"></label>
        <label class="field"><span>Активна</span><select id="sv-active">
          <option value="1" ${s.active ? 'selected' : ''}>да</option>
          <option value="0" ${s.active ? '' : 'selected'}>нет</option></select></label>
      </div>
      <div class="opt-group-title">Чаты Telegram — отметить галочками</div>
      ${chats.length ? `<div class="check-list" style="max-height:180px;overflow:auto">
          ${chats.map(c => `<label class="chk"><input type="checkbox" data-chat="${c.chat_id}"
              ${picked.has(Number(c.chat_id)) ? 'checked' : ''}>
            <span style="flex:1">${esc(c.title)} <code>${esc(String(c.chat_id))}</code>
              <span class="badge muted">${esc(c.kind)}</span>
              ${c.used_by && c.used_by.filter(n => n !== s.name).length
                ? `<span class="badge info">уже: ${esc(c.used_by.filter(n => n !== s.name).join(', '))}</span>` : ''}</span></label>`).join('')}
        </div>
        <p class="hint" style="margin-top:6px">Список общий для всего приложения: бот добавляется в группы
        служб, каталог обновляется кнопкой «Обновить список чатов (getUpdates)» в
        «Настройки → Чаты и Почта». Один чат можно закрепить за несколькими службами —
        тогда каждая получит своё сообщение.</p>`
        : `<div class="hint" style="margin-top:0">Каталог чатов пуст. Чтобы чат появился:
        1) в «Настройки → Чаты и Почта» сохраните токен бота и нажмите «Проверить бота»;
        2) в Telegram добавьте бота в группу службы и напишите в группу любое сообщение;
        3) там же нажмите «Обновить список чатов (getUpdates)»; 4) вернитесь сюда и
        отметьте чат галочкой. Личные чаты попадают в каталог так же — напишите боту.</div>`}`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Сохранить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        const chatIds = $$('[data-chat]', m).filter(cb => cb.checked)
          .map(cb => Number(cb.dataset.chat));
        try {
          const r = await api(`/api/night/services/${s.id}`, { method: 'PUT', body: {
            name: $('#sv-name').value.trim(), sort_order: Number($('#sv-order').value) || 100,
            active: $('#sv-active').value === '1', use_telegram: $('#sv-tg').checked,
            use_email: $('#sv-mail').checked, email_to: $('#sv-to').value.trim(),
            email_copy: $('#sv-copy').value.trim(), chat_ids: chatIds,
            note: $('#sv-note').value.trim() } });
          closeModal();
          toast(r.open_items_updated ? `Служба сохранена · обновлено пунктов в открытых сменах: ${r.open_items_updated}`
                                     : 'Служба сохранена', 'ok');
          if (after) after();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ── вкладка «Чек-листы»: шаблон зоны + индивидуальные правки объекта ── */
async function dictItemsTab(m, zones, services, canEdit, render) {
  const host = m.querySelector('#dict-host');
  if (!zones.length) { host.innerHTML = '<div class="empty">Сначала создайте зону — форма в списке слева</div>'; return; }
  if (!zones.some(z => z.id === nightState.dictZone)) nightState.dictZone = zones[0].id;
  const zid = nightState.dictZone;
  let zd;
  try { zd = await api(`/api/night/zones/${zid}/items`); }
  catch (e) { host.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  const zoneAreas = zd.areas || [];
  if (!zoneAreas.some(a => a.id === nightState.dictArea)) {
    nightState.dictArea = zoneAreas.length ? zoneAreas[0].id : null;
  }
  let cl = null;
  if (nightState.dictArea) {
    try { cl = await api(`/api/night/areas/${nightState.dictArea}/checklist`); }
    catch { cl = null; }
  }

  host.innerHTML = `
    <label class="field"><span>Зона</span><select id="di-zone">
      ${zones.map(z => `<option value="${z.id}" ${z.id === zid ? 'selected' : ''}>${esc(z.name)}</option>`).join('')}
    </select></label>
    <div class="opt-group-title">Шаблон чек-листа зоны · объектов в зоне: ${zoneAreas.length}</div>
    ${canEdit ? `<div class="grid-2" style="grid-template-columns:1fr 200px 90px auto;margin-bottom:10px">
        <input type="text" id="di-text" maxlength="300" placeholder="Пункт шаблона (например: Витражи закрыты)">
        <select id="di-service" title="Ответственная служба">${serviceOptions(services, null)}</select>
        <input type="number" id="di-order" value="100" title="Порядок">
        <button class="btn btn-primary" id="di-add">Добавить в зону</button></div>` : ''}
    <div class="check-list" style="max-height:24vh">${zd.items.map(i => `
      <div class="rule-row" style="grid-template-columns:1fr auto">
        <div><div class="lbl">${esc(i.text)} <small class="muted">порядок ${i.sort_order}</small>
            ${i.active ? '' : ' <span class="badge muted">отключён</span>'}
            ${i.service_name ? `<span class="badge info" title="Ответственная служба">⚖ ${esc(i.service_name)}</span>`
              : '<span class="badge muted" title="Служба не задана — недостаток никуда не уйдёт">без службы</span>'}
            ${i.overrides ? `<span class="badge warn" title="у объектов зоны своя формулировка/отключение">индивидуально: ${i.overrides}</span>` : ''}</div>
          <div class="desc">действует для всех объектов зоны</div></div>
        ${canEdit ? `<div class="row-actions">
          <button class="btn btn-sm btn-ghost" data-ziedit="${i.id}">Править</button>
          <button class="btn btn-sm btn-ghost" data-zitoggle="${i.id}">${i.active ? 'Отключить' : 'Включить'}</button>
          <button class="btn btn-sm btn-ghost" data-zidel="${i.id}">Удалить</button></div>` : ''}
      </div>`).join('') || '<div class="empty">Пунктов шаблона нет — добавьте первый</div>'}</div>

    <div class="opt-group-title">Индивидуальные особенности объекта</div>
    ${cl ? `
      <label class="field"><span>Объект зоны</span><select id="di-area">
        ${zoneAreas.map(a => `<option value="${a.id}" ${a.id === cl.area.id ? 'selected' : ''}>${esc(a.name)}</option>`).join('')}
      </select></label>
      <div class="check-list" style="max-height:26vh">${cl.zone_items.map(i => `
        <div class="rule-row" style="grid-template-columns:1fr auto">
          <div><div class="lbl">${esc(i.in_checklist ? i.effective_text : i.text)}
              ${i.disabled ? ' <span class="badge muted">не проверяется</span>'
                : (i.override_text ? ' <span class="badge warn">своя формулировка</span>' : '')}
              ${i.effective_service_name ? `<span class="badge info" title="Кто получает недостаток">⚖ ${esc(i.effective_service_name)}</span>` : ''}
              ${i.override_service_id ? '<span class="badge warn">своя служба</span>' : ''}</div>
            <div class="desc">${i.override_text || i.disabled || i.override_service_id
              ? `в шаблоне зоны: ${esc(i.text)}${i.service_name ? ` · ${esc(i.service_name)}` : ''}`
              : 'как в шаблоне зоне'}</div></div>
          ${canEdit ? `<div class="row-actions">
            <button class="btn btn-sm btn-ghost" data-ov="${i.id}">Правка</button></div>` : ''}
        </div>`).join('') || '<div class="empty">Шаблон зоны пуст</div>'}</div>
      <div class="row-actions" style="margin-top:10px">
        <button class="btn btn-sm" data-own="${cl.area.id}">Свои пункты объекта (${cl.own_items.length})</button>
        <span class="hint" style="margin:0">итоговый чек-лист объекта: ${cl.effective.length} пунктов</span></div>`
      : '<div class="empty">В зоне нет объектов — добавьте их на вкладке «Объекты»</div>'}`;

  const zoneSel = host.querySelector('#di-zone');
  if (zoneSel) zoneSel.onchange = () => {
    nightState.dictZone = Number(zoneSel.value); nightState.dictArea = null; render();
  };
  const add = host.querySelector('#di-add');
  if (add) add.onclick = async () => {
    const text = $('#di-text').value.trim();
    if (!text) return toast('Введите текст пункта', 'warn');
    try {
      const r = await api(`/api/night/zones/${zid}/items`, { method: 'POST',
        body: { text, sort_order: Number($('#di-order').value) || 100, active: true,
                service_id: Number($('#di-service').value) || null } });
      toast(`Пункт добавлен в шаблон зоны${r.sections_refreshed ? ` · пересобрано смен: ${r.sections_refreshed}` : ''}`, 'ok');
      render();
    } catch (e) { toast(e.message, 'err'); }
  };
  $$('[data-ziedit]', host).forEach(b => b.onclick = () =>
    nightZoneItemEditModal(zd.items.find(i => i.id === Number(b.dataset.ziedit)), services, render));
  $$('[data-zitoggle]', host).forEach(b => b.onclick = async () => {
    const i = zd.items.find(x => x.id === Number(b.dataset.zitoggle));
    try {
      await api(`/api/night/zone-items/${i.id}`, { method: 'PUT',
        body: { text: i.text, sort_order: i.sort_order, active: !i.active,
                service_id: i.service_id || null } });
      render();
    } catch (e) { toast(e.message, 'err'); }
  });
  $$('[data-zidel]', host).forEach(b => b.onclick = () => {
    const i = zd.items.find(x => x.id === Number(b.dataset.zidel));
    confirmDialog('Удалить пункт шаблона зоны?',
      `«${i.text}» исчезнет из чек-листов всех объектов зоны (${zoneAreas.length}) в ещё не начатых сменах. `
      + 'В закрытых сменах останется навсегда.',
      async () => {
        try { const r = await api(`/api/night/zone-items/${i.id}`, { method: 'DELETE' });
          toast(`Пункт удалён${r.removed_from_open ? `, убрано из смен: ${r.removed_from_open}` : ''}`, 'ok'); render(); }
        catch (e) { toast(e.message, 'err'); }
      }, 'Удалить');
  });
  const areaSel = host.querySelector('#di-area');
  if (areaSel) areaSel.onchange = () => { nightState.dictArea = Number(areaSel.value); render(); };
  $$('[data-ov]', host).forEach(b => b.onclick = () => {
    const i = cl.zone_items.find(x => x.id === Number(b.dataset.ov));
    nightOverrideModal(i, cl.area, services, render);
  });
  const own = host.querySelector('[data-own]');
  if (own) own.onclick = () => nightItemsModal(
    { id: Number(own.dataset.own), name: cl.area.name }, render);
}

function nightZoneItemEditModal(i, services, after) {
  openModal({
    title: 'Пункт шаблона зоны',
    subtitle: i.text,
    body: `<label class="field"><span>Текст</span>
        <input type="text" id="zi-text" value="${esc(i.text)}" maxlength="300"></label>
      <label class="field"><span>Ответственная служба</span>
        <select id="zi-service">${serviceOptions(services, i.service_id)}</select></label>
      <div class="grid-2">
        <label class="field"><span>Порядок</span><input type="number" id="zi-order" value="${i.sort_order}"></label>
        <label class="field"><span>Активен</span><select id="zi-active">
          <option value="1" ${i.active ? 'selected' : ''}>да</option>
          <option value="0" ${i.active ? '' : 'selected'}>нет</option></select></label>
      </div>
      <p class="hint">Служба — получатель недостатка по этому пункту: она действует для всех объектов
      зоны, а у отдельного объекта её можно переопределить. Правка текста и службы обновляет пункт
      во всех объектах зоны и в незакрытых сменах; в закрытых останется снимок.</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Сохранить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        try {
          await api(`/api/night/zone-items/${i.id}`, { method: 'PUT', body: {
            text: $('#zi-text').value.trim(), sort_order: Number($('#zi-order').value) || 100,
            active: $('#zi-active').value === '1',
            service_id: Number($('#zi-service').value) || null } });
          closeModal(); toast('Пункт шаблона сохранён', 'ok'); if (after) after();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

function nightOverrideModal(i, area, services, after) {
  openModal({
    title: 'Индивидуальная правка',
    subtitle: `${area.name} · ${i.text}`,
    body: `<label class="field"><span>Формулировка у этого объекта</span>
        <input type="text" id="ov-text" value="${esc(i.override_text || i.text)}" maxlength="300"></label>
      <label class="field"><span>Ответственная служба</span>
        <select id="ov-service">${serviceOptions(services, i.override_service_id || i.service_id,
          i.service_name ? `как в шаблоне зоны (${i.service_name})` : '— как в шаблоне зоны —')}</select></label>
      <label class="chk"><input type="checkbox" id="ov-dis" ${i.disabled ? 'checked' : ''}>
        Не проверять этот пункт у объекта</label>
      <p class="hint">В шаблоне зоны пункт останется прежним — правка касается только «${esc(area.name)}».
      Своя служба нужна, когда за объект отвечает не та же служба, что за зону (например, детскую
      комнату проверяет батлер-сервис, а не хозяйственная служба). Применяется к ещё не начатым
      объектам в открытых сменах; начатые и закрытые не трогаются.</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn" data-reset>Сбросить к шаблону</button>
             <button class="btn btn-primary" data-ok>Сохранить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-reset]').onclick = async () => {
        try {
          await api(`/api/night/areas/${area.id}/overrides/${i.id}`, { method: 'DELETE' });
          closeModal(); toast('Пункт снова как в шаблоне зоны', 'ok'); if (after) after();
        } catch (e) { toast(e.message, 'err'); }
      };
      m.querySelector('[data-ok]').onclick = async () => {
        try {
          const r = await api(`/api/night/areas/${area.id}/overrides/${i.id}`, { method: 'PUT', body: {
            text: $('#ov-text').value.trim(), disabled: $('#ov-dis').checked,
            service_id: Number($('#ov-service').value) || null } });
          closeModal();
          toast(r.sections_refreshed ? `Сохранено · пересобрано смен: ${r.sections_refreshed}` : 'Сохранено', 'ok');
          if (after) after();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ── свои пункты одного объекта (не из шаблона зоны) ── */
async function nightItemsModal(a, after) {
  const renderItems = async () => {
    const [ar, sr] = await Promise.all([api('/api/night/areas'), api('/api/night/services')]);
    const fresh = ar.areas.find(x => x.id === a.id);
    const services = sr.services || [];
    openModal({
      title: 'Свои пункты: ' + fresh.name,
      subtitle: 'Пункты только этого объекта — дополнительно к шаблону зоны. Правка текста обновляет пункт в незакрытых сменах',
      wide: true,
      body: `<div class="grid-2" style="grid-template-columns:1fr 200px 90px auto;margin-bottom:12px">
          <input type="text" id="it-text" maxlength="300" placeholder="Например: Детская кроватка установлена">
          <select id="it-service" title="Ответственная служба">${serviceOptions(services, null)}</select>
          <input type="number" id="it-order" value="100" title="Порядок">
          <button class="btn btn-primary" id="it-add">Добавить</button></div>
        <div class="check-list" style="max-height:46vh">${fresh.items.map(it => `
          <div class="rule-row" style="grid-template-columns:1fr auto">
            <div><div class="lbl">${esc(it.text)} <small class="muted">· порядок ${it.sort_order}</small>
              ${it.active ? '' : ' <span class="badge muted">отключён</span>'}
              ${it.service_name ? `<span class="badge info" title="Ответственная служба">⚖ ${esc(it.service_name)}</span>` : ''}</div>
              <div class="desc">зона: ${esc(fresh.zone_name || '—')} · всего в чек-листе объекта: ${fresh.effective_total}</div></div>
            <div class="row-actions">
              <button class="btn btn-sm btn-ghost" data-it-edit="${it.id}">Править</button>
              <button class="btn btn-sm btn-ghost" data-it-toggle="${it.id}">${it.active ? 'Отключить' : 'Включить'}</button>
              <button class="btn btn-sm btn-ghost" data-it-del="${it.id}">Удалить</button>
            </div></div>`).join('') || '<div class="empty">Своих пунктов нет — объект проверяется по шаблону зоны</div>'}</div>`,
      footer: `<button class="btn" data-back>← К чек-листам</button><button class="btn btn-ghost" data-cancel>Закрыть</button>`,
      onMount(m) {
        m.querySelector('[data-cancel]').onclick = closeModal;
        m.querySelector('[data-back]').onclick = () => { closeModal(); if (after) after(); };
        $('#it-add').onclick = async () => {
          const text = $('#it-text').value.trim();
          if (!text) return toast('Введите текст пункта', 'warn');
          try {
            const r = await api(`/api/night/areas/${fresh.id}/items`, { method: 'POST',
              body: { text, sort_order: Number($('#it-order').value) || 100, active: true,
                      service_id: Number($('#it-service').value) || null } });
            toast(`Пункт добавлен${r.added_to_open_sections ? ` (попал в открытых смен: ${r.added_to_open_sections})` : ''}`, 'ok');
            renderItems();
          } catch (e) { toast(e.message, 'err'); }
        };
        const editItem = (it) => openModal({
          title: 'Пункт объекта',
          body: `<label class="field"><span>Текст</span><input type="text" id="ie-text" value="${esc(it.text)}" maxlength="300"></label>
            <label class="field"><span>Ответственная служба</span>
              <select id="ie-service">${serviceOptions(services, it.service_id)}</select></label>
            <div class="grid-2">
              <label class="field"><span>Порядок</span><input type="number" id="ie-order" value="${it.sort_order}"></label>
              <label class="field"><span>Активен</span><select id="ie-active">
                <option value="1" ${it.active ? 'selected' : ''}>да</option>
                <option value="0" ${it.active ? '' : 'selected'}>нет</option></select></label>
            </div>`,
          footer: `<button class="btn btn-ghost" data-cancel">Отмена</button><button class="btn btn-primary" data-ok>Сохранить</button>`,
          onMount(mm) {
            mm.querySelector('[data-cancel]').onclick = () => { closeModal(); renderItems(); };
            mm.querySelector('[data-ok]').onclick = async () => {
              try {
                await api(`/api/night/items/${it.id}`, { method: 'PUT', body: {
                  text: $('#ie-text').value.trim(), sort_order: Number($('#ie-order').value) || 100,
                  active: $('#ie-active').value === '1',
                  service_id: Number($('#ie-service').value) || null } });
                toast('Пункт сохранён', 'ok'); renderItems();
              } catch (e) { toast(e.message, 'err'); }
            };
          },
        });
        $$('[data-it-edit]', m).forEach(b => b.onclick = () => editItem(fresh.items.find(x => x.id === Number(b.dataset.itEdit))));
        $$('[data-it-toggle]', m).forEach(b => b.onclick = async () => {
          const it = fresh.items.find(x => x.id === Number(b.dataset.itToggle));
          try {
            await api(`/api/night/items/${it.id}`, { method: 'PUT', body: { text: it.text, sort_order: it.sort_order, active: !it.active, service_id: it.service_id || null } });
            renderItems();
          } catch (e) { toast(e.message, 'err'); }
        });
        $$('[data-it-del]', m).forEach(b => b.onclick = () => {
          const it = fresh.items.find(x => x.id === Number(b.dataset.itDel));
          confirmDialog('Удалить пункт?', `«${it.text}» исчезнет из незакрытых смен; в закрытых останется.`,
            async () => { try { await api(`/api/night/items/${it.id}`, { method: 'DELETE' }); toast('Пункт удалён', 'ok'); renderItems(); }
                          catch (e) { toast(e.message, 'err'); } }, 'Удалить');
        });
      },
    });
  };
  await renderItems();
}


/* ══════════════════════════════════════════════════════════════════
   НЕДОСТАТКИ СМЕНЫ: консолидированная отправка службам (этап 5)
   ══════════════════════════════════════════════════════════════════ */
/* «Не ОК» и «Не проверено» группируются по ответственным службам и отправляются
   вручную — всё скопом или выборочно. Отправленное помечается и повторно не
   уходит; если пункт исправили ПОСЛЕ отправки, ничего не отправляем и не отзываем.
   Транспорт и шаблоны — общие настройки приложения («Настройки → Чаты и Почта»). */

function defectRow(d, selected) {
  const media = (d.media || []).filter(x => x.url);
  const badges = [
    d.kind === 'bad' ? '<span class="badge danger">Не ОК</span>'
      : d.kind === 'fixed' ? '<span class="badge info">было в отправке</span>'
        : '<span class="badge muted">Не проверено</span>',
    d.fixed_after_dispatch ? '<span class="badge info" title="Ничего не отправляем и не отзываем">исправлено после отправки</span>'
      : (d.dispatched ? `<span class="badge ok" title="Отправлено ${esc(d.dispatched_at || '')}">отправлено${d.dispatched_at ? ' ' + esc(hhmm(d.dispatched_at)) : ''}</span>` : ''),
    media.length ? `<span class="badge info" title="вложений: ${media.length}">📎 ${media.length}</span>` : '',
  ].join(' ');
  return `<label class="rule-row defect-row${d.sendable ? '' : ' sent'}" style="grid-template-columns:auto 1fr">
    <input type="checkbox" data-def="${d.id}" ${selected ? 'checked' : ''} ${d.sendable ? '' : 'disabled'}
      title="${d.sendable ? 'включить в отправку' : 'уже отправлено или исправлено после отправки'}">
    <div>
      <div class="lbl">${esc(d.area)} <span class="muted">· ${esc(d.zone || '')}</span> ${badges}</div>
      <div class="desc">${esc(d.text)}${d.comment ? ` — <i>${esc(d.comment)}</i>` : ''}
        ${d.answered_by_name ? `<span class="muted">· ${esc(d.answered_by_name)}${d.answered_at ? ' ' + esc(hhmm(d.answered_at)) : ''}</span>` : ''}</div>
      ${media.length ? `<div class="thumbs">${media.map(photoThumb).join('')}</div>` : ''}
    </div></label>`;
}

function defectGroup(g, selectedIds) {
  const problems = (g.problems || []).map(esc).join('; ');
  const ch = (g.channels || []).map(c => c === 'telegram'
    ? `<span class="badge info">чат · ${g.chat_ids.length}</span>`
    : `<span class="badge info">письмо · ${esc((g.email_to || []).join(', '))}</span>`).join(' ');
  return `<div class="panel defect-group${g.ready ? '' : ' not-ready'}">
    <h3 class="panel-title">⚖ ${esc(g.service_name)}
      <span class="badge ${g.counts.sendable ? 'warn' : 'muted'}">к отправке: ${g.counts.sendable}</span>
      ${g.counts.dispatched ? `<span class="badge ok">отправлено: ${g.counts.dispatched}</span>` : ''}
      ${g.counts.fixed_after_dispatch ? `<span class="badge info">исправлено после отправки: ${g.counts.fixed_after_dispatch}</span>` : ''}
      ${ch}</h3>
    ${problems ? `<p class="hint" style="color:var(--danger);margin:0 0 8px">Нельзя отправить: ${problems}</p>` : ''}
    ${g.note ? `<p class="hint" style="margin:0 0 8px">${esc(g.note)}</p>` : ''}
    <div class="check-list" style="max-height:34vh">${g.defects.map(d => defectRow(d, selectedIds.has(d.id))).join('')}</div>
    ${g.counts.sendable && g.ready && can('night.dispatch') ? `<div class="row-actions" style="margin-top:8px">
      <button class="btn btn-sm btn-primary" data-send-service="${g.service_id}">Отправить службе</button></div>` : ''}
  </div>`;
}

function defectJournal(rows) {
  if (!rows.length) return '<div class="empty">Отправок пока не было</div>';
  return `<div class="table-wrap"><table class="data"><thead><tr>
      <th>Время</th><th>Кто</th><th>Служба</th><th>Канал</th><th>Получатель</th>
      <th>Позиций</th><th>Вложений</th><th>Статус</th><th></th></tr></thead><tbody>
    ${rows.map(d => `<tr>
      <td>${esc(d.ts ? d.ts.slice(5, 16).replace('T', ' ') : '')}</td>
      <td>${esc(d.actor_name)}</td><td>${esc(d.recipient_name)}</td>
      <td>${esc(d.channel_title)}</td><td><code>${esc(d.target)}</code></td>
      <td class="num">${d.items_count}</td><td class="num">${d.media_count}</td>
      <td>${d.status === 'sent' ? `<span class="badge ok">отправлено${d.attempts > 1 ? ` (попыток: ${d.attempts})` : ''}</span>`
        : d.status === 'failed' ? `<span class="badge danger" title="${esc(d.error)}">ошибка</span>`
        : `<span class="badge warn">${esc(d.status_title)}</span>`}</td>
      <td class="num"><button class="btn btn-sm btn-ghost" data-msg="${d.id}">текст</button>
        ${d.can_retry ? `<button class="btn btn-sm" data-retry="${d.id}">повторить</button>` : ''}</td></tr>`).join('')}
    </tbody></table></div>`;
}

async function nightDefectsModal() {
  /* смена — как в остальном разделе: выбранная в архиве или текущая */
  const reportId = nightState.reportId || nightState.today?.report?.id;
  if (!reportId) return toast('Сначала откройте смену', 'warn');
  const sel = nightState.defectsSelected;

  const render = async () => {
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
      subtitle: `Ночные батлеры смены: ${esc(d.duty)} · к отправке ${c.sendable || 0} из ${c.total || 0}`
        + ` · отправлено ${c.dispatched || 0}` + (c.fixed_after_dispatch ? ` · исправлено после отправки ${c.fixed_after_dispatch}` : ''),
      wide: true,
      body: `
        ${(!transport.telegram && !transport.email) ? `<p class="hint" style="color:var(--danger);margin:0 0 10px">
          Доставка не настроена: заполните токен бота и/или почту в «Настройки → Чаты и Почта».</p>` : ''}
        <div class="toolbar" style="margin-bottom:10px">
          <button class="btn btn-sm btn-primary" id="df-all" ${c.sendable && canSend ? '' : 'disabled'}>Отправить всё (${c.sendable || 0})</button>
          <button class="btn btn-sm" id="df-sel" ${sel.size && canSend ? '' : 'disabled'}>Отправить выбранное (${sel.size})</button>
          <button class="btn btn-sm" id="df-preview">Предпросмотр</button>
          <label class="chk" style="margin:0"><input type="checkbox" id="df-sent" ${nightState.defectsShowSent ? 'checked' : ''}>
            показывать отправленные и исправленные</label>
          <div class="spacer"></div>
          <span class="hint" style="margin:0">${canSend ? '«Не проверено» включается в отчёт'
            : 'Отправка службам — право <b>night.dispatch</b> («Настройки → Права доступа»)'}</span>
        </div>
        ${sendableGroups.length ? '' : '<div class="empty">Недостатков к отправке нет</div>'}
        ${groups.filter(g => nightState.defectsShowSent || g.counts.sendable > 0)
          .map(g => defectGroup(g, sel)).join('')}
        <div class="opt-group-title">Журнал отправок смены</div>
        <div class="row-actions" style="margin-bottom:6px">
          <button class="btn btn-sm btn-ghost" id="df-csv">Выгрузить журнал (CSV)</button>
          <span class="hint" style="margin:0">журнал общий для всех разделов приложения</span></div>
        ${defectJournal(d.dispatches || [])}`,
      footer: `<button class="btn btn-ghost" data-cancel>Закрыть</button>`,
      onMount(m) {
        m.querySelector('[data-cancel]').onclick = closeModal;
        $$('[data-def]', m).forEach(cb => cb.onchange = () => {
          const id = Number(cb.dataset.def);
          if (cb.checked) sel.add(id); else sel.delete(id);
          const btn = $('#df-sel');
          if (btn) { btn.textContent = `Отправить выбранное (${sel.size})`; btn.disabled = !sel.size || !canSend; }
        });
        const sent = $('#df-sent', m);
        if (sent) sent.onchange = () => { nightState.defectsShowSent = sent.checked; render(); };
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
            await render();
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
              body: (r.messages || []).map(msg => `<div class="panel">
                  <h3 class="panel-title">⚖ ${esc(msg.service_name)}
                    <span class="badge info">${esc((msg.channels || []).join(', ') || 'каналы не заполнены')}</span></h3>
                  ${msg.problems && msg.problems.length
                    ? `<p class="hint" style="color:var(--danger);margin:0 0 8px">${esc(msg.problems.join('; '))}</p>` : ''}
                  <pre style="white-space:pre-wrap;font:inherit;margin:0">${esc(msg.message)}</pre></div>`).join('')
                || '<div class="empty">Отправлять нечего</div>',
              footer: '<button class="btn btn-ghost" data-cancel>Закрыть</button>',
              onMount(mm) { mm.querySelector('[data-cancel]').onclick = () => { closeModal(); render(); }; },
            });
          } catch (e) { toast(e.message, 'err'); }
        };
        $$('[data-msg]', m).forEach(b => b.onclick = () => {
          const row = (d.dispatches || []).find(x => x.id === Number(b.dataset.msg));
          if (!row) return;
          openModal({ title: 'Отправленное сообщение', subtitle: `${row.recipient_name} · ${row.channel_title} · ${row.target}`,
            body: `<pre style="white-space:pre-wrap;font:inherit;margin:0">${esc(row.message)}</pre>
              ${row.error ? `<p class="hint" style="color:var(--danger)">Ошибка: ${esc(row.error)}</p>` : ''}`,
            footer: '<button class="btn btn-ghost" data-cancel>Закрыть</button>',
            onMount(mm) { mm.querySelector('[data-cancel]').onclick = () => { closeModal(); render(); }; } });
        });
        const csv = $('#df-csv', m);
        if (csv) csv.onclick = () => downloadBlob(
          `/api/notify/dispatches/export.csv?domain=night`, `otpravki-${d.report.date}.csv`);
        $$('[data-retry]', m).forEach(b => b.onclick = async () => {
          try {
            const r = await api(`/api/notify/dispatches/${b.dataset.retry}/resend`, { method: 'POST', timeout: 300000 });
            toast(r.dispatch.status === 'sent' ? 'Доставлено при повторе' : `Повтор не удался: ${r.dispatch.error}`,
              r.dispatch.status === 'sent' ? 'ok' : 'err');
            render();
          } catch (e) { toast(e.message, 'err'); }
        });
        bindPhotoDelete(m, null);
      },
    });
  };
  await render();
}
