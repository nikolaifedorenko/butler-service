/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН НАСТРОЕК «НОЧНОЙ ОБХОД» — зоны, объекты, чек-листы, службы (выделен из night.js в шаге 6е;
   на шаблоны переедет вместе с остальными экранами Настроек, шаг 6ж).
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

registerModule({ screens: { night: { render: renderNightDictScreen, icon: 'moon' } } });

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

/* ── мост к общей области имён (генерируется tools/gen_js_globals.py; уйдёт вместе с переходом файла на import/export) ── */
Object.assign(globalThis, {
  renderNightDictScreen,
  bindNightDictScreen,
  nightZoneEditModal,
  zoneOptions,
  dictAreasHtml,
  bindDictAreas,
  nightAreaEditModal,
  serviceOptions,
  serviceChannels,
  dictServicesHtml,
  bindDictServices,
  serviceEditModal,
  dictItemsTab,
  nightZoneItemEditModal,
  nightOverrideModal,
  nightItemsModal,
});
/* ── конец моста ── */
