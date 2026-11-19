/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН НАСТРОЕК «НОЧНОЙ ОБХОД» — зоны, объекты, чек-листы, службы (выделен из night.js в шаге 6е).
   Модуль на lit-html (ADR-0013, раздел 7).
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

import { navigate, registerModule } from '../app.js';
import { $, $$, api, closeModal, confirmDialog, openModal, toast } from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { nightState } from './night.js';
import { settingsHeadView } from './settings.js';

registerModule({ screens: { night: { render: renderNightDictScreen, icon: 'moon' } } });

/* ─────────── экран Настроек «Ночной обход»: зоны · объекты · чек-листы · службы ───────────
   Единственное место правки справочника обхода — экран в «Настройках» (группа
   «Объект», адрес #/settings/night; docs/archive/PROPOSAL-SETTINGS-IA-2026-10-19.md).
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
  const [zr, ar, sr] = await Promise.all([api('/api/night/zones'), api('/api/night/areas'),
                                           api('/api/night/services')]);
  const zones = zr.zones || [], areas = ar.areas || [], services = sr.services || [];
  const canEdit = !!zr.can_edit;
  if (!['areas', 'items', 'services'].includes(nightState.dictTab)) nightState.dictTab = 'areas';
  const t = nightState.dictTab;
  if (t !== 'services' && zones.length && !zones.some(z => z.id === nightState.dictZone)) {
    nightState.dictZone = zones[0].id; nightState.dictArea = null;
  }
  const again = () => renderNightDictScreen(host);

  /* вкладка «Чек-листы» нужна свежих данных зоны и объекта — берём до отрисовки */
  let items = null;
  if (t === 'items' && zones.length) items = await loadItems(zones);

  const pickZone = (z, e) => {
    if (e.target.closest('button')) return;      /* «Править»/«Отключить» — не выбор зоны */
    nightState.dictZone = z.id;
    nightState.dictArea = null;
    if (nightState.dictTab === 'services') nightState.dictTab = 'areas';
    again();
  };
  const addZone = async () => {
    const name = $('#nz-name', host).value.trim();
    if (!name) return toast('Введите название зоны', 'warn');
    try {
      const r = await api('/api/night/zones', { method: 'POST',
        body: { name, sort_order: Number($('#nz-order', host).value) || 100, active: true } });
      nightState.dictZone = r.id; nightState.dictTab = 'areas';
      toast(`Зона «${name}» добавлена`, 'ok'); again();
    } catch (e) { toast(e.message, 'err'); }
  };
  const dropZone = z => confirmDialog('Отключить зону?',
    `«${z.name}» перестанет предлагаться в справочниках; объекты зоны (${z.areas_total}) останутся — `
    + 'отключите их отдельно, если они больше не проверяются. История закрытых смен сохранится.',
    async () => {
      try { const r = await api(`/api/night/zones/${z.id}`, { method: 'DELETE' });
        toast(`Зона отключена (объектов осталось: ${r.areas_left})`, 'ok'); again(); }
      catch (e) { toast(e.message, 'err'); }
    }, 'Отключить');

  render(html`
    ${settingsHeadView('Ночной обход',
      'Зоны → объекты → чек-листы → службы. Шаблон задаётся на зону, индивидуальные пункты — у объекта. Сам обход — в разделе «Ночной отчёт».',
      html`<div class="seg">${[['areas', 'Объекты'], ['items', 'Чек-листы'], ['services', 'Службы']]
          .map(([k, l]) => html`<button data-dtab=${k} class=${t === k ? 'active' : ''}
            @click=${() => { nightState.dictTab = k; again(); }}>${l}</button>`)}</div>
         <button class="btn btn-sm btn-ghost" id="nd-to-night" title="Открыть раздел «Ночной отчёт»" @click=${() => navigate('night')}>К обходу ↗</button>`)}
    <div class="dict-banner"><span>🌙</span><span>Правки применяются к <b>ещё не начатым объектам</b> —
      в текущей и следующих сменах; чек-листы начатых объектов и закрытых смен зафиксированы
      снимком в отчёте и не изменятся.</span></div>
    ${canEdit ? nothing : html`<div class="dict-banner gold"><span>🔒</span><span>Только просмотр: для правок нужно право <b>night.edit</b> (выдаётся в «Настройки → Права доступа»).</span></div>`}
    <div class="dict-md">
      <div class="dict-zones">
        <div class="panel-title">Зоны обхода</div>
        ${zones.length ? zones.map(z => html`
          <div class=${`dict-zone${z.id === nightState.dictZone && t !== 'services' ? ' active' : ''}`} data-dz=${z.id} @click=${e => pickZone(z, e)}>
            <div class="dz-name">${z.name}${z.active ? nothing : html` <span class="badge muted">отключена</span>`}</div>
            <div class="dz-meta">объектов: ${z.areas_total} · пунктов шаблона: ${z.items_total}</div>
            ${canEdit ? html`<div class="row-actions">
              <button class="btn btn-sm btn-ghost" data-zedit=${z.id} @click=${() => nightZoneEditModal(z, again)}>Править</button>
              <button class="btn btn-sm btn-ghost" data-zdel=${z.id} @click=${() => dropZone(z)}>Отключить</button></div>` : nothing}
          </div>`) : html`<div class="empty" style="padding:14px">Зон нет — добавьте первую</div>`}
        ${canEdit ? html`<div class="opt-group-title">Новая зона</div>
          <div style="display:grid;gap:8px">
            <input type="text" id="nz-name" maxlength="160" placeholder="Название зоны (например: Семейные виллы)">
            <div style="display:flex;gap:8px">
              <input type="number" id="nz-order" .value=${'100'} title="Порядок" style="width:96px;flex:none">
              <button class="btn btn-primary" id="nz-add" style="flex:1" @click=${addZone}>Добавить зону</button></div></div>` : nothing}
        <p class="hint">Зона — первый уровень обхода. Чек-лист задаётся на зону и действует
          для всех её объектов; отключение зоны не трогает историю закрытых смен.</p>
      </div>
      <div id="dict-host">${t === 'areas' ? areasTab(zones, areas, canEdit, again, host)
        : t === 'services' ? servicesTab(services, canEdit, again, host)
        : itemsTab(items, zones, services, canEdit, again, host)}</div>
    </div>`, mount(host));
}

/* ── вкладка «Объекты» ── */
const zoneOptions = (zones, selected, placeholder) => html`<option value="">${placeholder || '— не выбрано —'}</option>${
  zones.map(z => html`<option value=${z.id} ?selected=${z.id === selected}>${z.name}</option>`)}`;

function areasTab(zones, areas, canEdit, again, host) {
  const zid = nightState.dictZone;
  const list = areas.filter(a => !zid || a.zone_id === zid);
  const addArea = async () => {
    const name = $('#da-name', host).value.trim();
    if (!name) return toast('Введите название объекта', 'warn');
    const zoneId = Number($('#da-new-zone', host).value) || null;
    const zone = zones.find(z => z.id === zoneId);
    try {
      await api('/api/night/areas', { method: 'POST', body: {
        name, zone_id: zoneId, category: zone ? zone.name : '',
        sort_order: Number($('#da-order', host).value) || 100, active: true } });
      toast(`Объект «${name}» добавлен`, 'ok'); again();
    } catch (e) { toast(e.message, 'err'); }
  };
  const addBulk = async () => {
    const zoneId = Number($('#db-zone', host).value) || null;
    const zone = zones.find(z => z.id === zoneId);
    try {
      const r = await api('/api/night/areas/bulk', { method: 'POST', body: {
        prefix: $('#db-prefix', host).value, start: Number($('#db-start', host).value) || 1,
        count: Number($('#db-count', host).value) || 1, zone_id: zoneId,
        category: zone ? zone.name : '' } });
      toast(`Создано объектов: ${r.created} — чек-лист зоны применится автоматически`, 'ok'); again();
    } catch (e) { toast(e.message, 'err'); }
  };
  const del = a => confirmDialog('Удалить объект?',
    `«${a.name}» будет отключён и убран из открытых (ещё не начатых) отчётов. История закрытых смен сохранится.`,
    async () => {
      try { const r = await api(`/api/night/areas/${a.id}`, { method: 'DELETE' });
        toast(`Объект отключён${r.sections_removed ? `, убрано из отчётов: ${r.sections_removed}` : ''}`, 'ok'); again(); }
      catch (e) { toast(e.message, 'err'); }
    }, 'Удалить');
  return html`
    <div class="toolbar" style="margin-bottom:10px">
      <label class="field" style="margin:0;min-width:230px"><span>Зона</span>
        <select id="da-zone" @change=${e => { nightState.dictZone = Number(e.target.value) || null; again(); }}>${zoneOptions(zones, zid, '— все зоны —')}</select></label>
      <div class="spacer"></div>
      <span class="hint" style="margin:0">объектов: ${list.length}</span></div>
    ${canEdit ? html`<div class="grid-3" style="margin-bottom:10px">
        <label class="field"><span>Новый объект</span>
          <input type="text" id="da-name" maxlength="160" placeholder="Вилла 4013"></label>
        <label class="field"><span>Зона</span><select id="da-new-zone">${zoneOptions(zones, zid)}</select></label>
        <label class="field"><span>Порядок</span><input type="number" id="da-order" .value=${'100'}></label></div>
      <div class="row-actions" style="margin-bottom:14px">
        <button class="btn btn-primary" id="da-add" @click=${addArea}>Добавить объект</button></div>
      <div class="opt-group-title">Серия однотипных объектов</div>
      <div class="grid-3" style="margin-bottom:10px">
        <label class="field"><span>Префикс</span><input type="text" id="db-prefix" placeholder="Вилла "></label>
        <label class="field"><span>Первый номер</span><input type="number" id="db-start" .value=${'4013'}></label>
        <label class="field"><span>Количество</span><input type="number" id="db-count" .value=${'6'} min="1" max="200"></label></div>
      <div class="row-actions" style="margin-bottom:14px">
        <label class="field" style="margin:0 12px 0 0;min-width:210px"><span>Зона серии</span>
          <select id="db-zone">${zoneOptions(zones, zid)}</select></label>
        <button class="btn" id="db-add" @click=${addBulk}>Создать серию</button></div>` : nothing}
    <div class="check-list" style="max-height:38vh">${list.length ? list.map(a => html`
      <div class="rule-row" style="grid-template-columns:1fr auto">
        <div><div class="lbl">${a.name} ${a.active ? nothing : html`<span class="badge muted">отключён</span>`}</div>
          <div class="desc">зона: ${a.zone_name || '—'} · чек-лист объекта: ${a.effective_total}
            (своих пунктов: ${a.items_total})</div></div>
        <div class="row-actions">
          <button class="btn btn-sm btn-ghost" data-acheck=${a.id} @click=${() => {
            nightState.dictZone = a.zone_id || nightState.dictZone;
            nightState.dictArea = a.id; nightState.dictTab = 'items'; again(); }}>Чек-лист</button>
          <button class="btn btn-sm btn-ghost" data-aitems=${a.id} @click=${() => nightItemsModal(a, again)}>Свои пункты</button>
          ${canEdit ? html`<button class="btn btn-sm btn-ghost" data-aedit=${a.id} @click=${() => nightAreaEditModal(a, zones, again)}>Править</button>
          <button class="btn btn-sm btn-ghost" data-adel=${a.id} @click=${() => del(a)}>Удалить</button>` : nothing}
        </div></div>`) : html`<div class="empty">Объектов нет</div>`}</div>
    <p class="hint">Удаление объекта мягкое: он отключается и убирается из ещё не начатых смен,
    история закрытых смен сохраняется.</p>`;
}

function nightZoneEditModal(z, after) {
  openModal({
    title: 'Зона: ' + z.name,
    body: html`<label class="field"><span>Название</span>
        <input type="text" id="ze-name" .value=${z.name} maxlength="160"></label>
      <div class="grid-2">
        <label class="field"><span>Порядок</span><input type="number" id="ze-order" .value=${String(z.sort_order)}></label>
        <label class="field"><span>Активна</span><select id="ze-active">
          <option value="1" ?selected=${z.active}>да</option>
          <option value="0" ?selected=${!z.active}>нет</option></select></label>
      </div>
      <p class="hint">Объектов в зоне: ${z.areas_total} · пунктов шаблона: ${z.items_total}.
      Переименование зоны обновит её название в открытых сменах; закрытые останутся как есть.</p>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Сохранить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        try {
          await api(`/api/night/zones/${z.id}`, { method: 'PUT', body: {
            name: $('#ze-name', m).value.trim(), sort_order: Number($('#ze-order', m).value) || 100,
            active: $('#ze-active', m).value === '1' } });
          closeModal(); toast('Зона сохранена', 'ok'); if (after) after();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

function nightAreaEditModal(a, zones, after) {
  openModal({
    title: 'Объект: ' + a.name,
    body: html`<label class="field"><span>Название</span>
        <input type="text" id="ae-name" .value=${a.name} maxlength="160"></label>
      <div class="grid-2">
        <label class="field"><span>Зона обхода</span>
          <select id="ae-zone">${zoneOptions(zones, a.zone_id)}</select></label>
        <label class="field"><span>Порядок</span><input type="number" id="ae-order" .value=${String(a.sort_order)}></label>
      </div>
      <label class="field"><span>Категория (историческая подпись группировки в выгрузке)</span>
        <input type="text" id="ae-cat" .value=${a.category || ''} maxlength="80"></label>
      <label class="chk"><input type="checkbox" id="ae-active" .checked=${!!a.active}> Объект активен</label>
      <p class="hint">Смена зоны меняет чек-лист объекта: в открытых сменах, где объект ещё не взят
      в работу, снимок пересобирается; начатые и закрытые не трогаются.</p>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Сохранить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        const zone = zones.find(z => z.id === (Number($('#ae-zone', m).value) || null));
        /* категория — историческая подпись группировки; если её не задали, берём название зоны */
        const category = $('#ae-cat', m).value.trim() || (zone ? zone.name : '');
        try {
          const r = await api(`/api/night/areas/${a.id}`, { method: 'PUT', body: {
            name: $('#ae-name', m).value.trim(), category,
            zone_id: Number($('#ae-zone', m).value) || null,
            sort_order: Number($('#ae-order', m).value) || 100, active: $('#ae-active', m).checked } });
          closeModal();
          toast(r.sections_refreshed ? `Сохранено · пересобрано смен: ${r.sections_refreshed}` : 'Сохранено', 'ok');
          if (after) after();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ── вкладка «Службы»: получатели недостатков и их каналы доставки ── */
const serviceOptions = (services, selected, placeholder = '— не задана —') => html`<option value="">${placeholder}</option>${
  services.filter(s => s.active || s.id === selected).map(s => html`<option value=${s.id} ?selected=${s.id === selected}>${s.name}</option>`)}`;

function serviceChannels(s) {
  const parts = [];
  if (s.use_telegram) parts.push(s.ready_telegram ? 'чат' : 'чат (не закреплён)');
  if (s.use_email) parts.push(s.ready_email ? 'письмо' : 'письмо (нет ящика)');
  return parts.join(' + ') || 'каналы не выбраны';
}

function servicesTab(services, canEdit, again, host) {
  const add = async () => {
    const name = $('#ns-name', host).value.trim();
    if (!name) return toast('Введите название службы', 'warn');
    try {
      await api('/api/night/services', { method: 'POST', body: {
        name, sort_order: Number($('#ns-order', host).value) || 100, active: true,
        use_telegram: true, use_email: false, chat_ids: [] } });
      toast('Служба добавлена — укажите каналы и получателей', 'ok'); again();
    } catch (e) { toast(e.message, 'err'); }
  };
  const off = s => confirmDialog('Отключить службу?',
    `«${s.name}» перестанет предлагаться в справочнике и не будет участвовать в новых отправках. `
    + `Закреплённых пунктов: ${s.items_total} — их стоит переназначить. История закрытых смен не изменится.`,
    async () => {
      try { await api(`/api/night/services/${s.id}`, { method: 'DELETE' }); toast('Служба отключена', 'ok'); again(); }
      catch (e) { toast(e.message, 'err'); }
    }, 'Отключить');
  return html`
    ${canEdit ? html`<div class="grid-2" style="grid-template-columns:1fr 110px auto;margin-bottom:12px">
        <input type="text" id="ns-name" maxlength="160" placeholder="Название службы (например: Хозяйственная служба)">
        <input type="number" id="ns-order" .value=${'100'} title="Порядок">
        <button class="btn btn-primary" id="ns-add" @click=${add}>Добавить службу</button></div>` : nothing}
    <div class="check-list" style="max-height:46vh">${services.length ? services.map(s => html`
      <div class="rule-row" style="grid-template-columns:1fr auto">
        <div><div class="lbl">${s.name} <small class="muted">порядок ${s.sort_order}</small>
            ${s.active ? nothing : html` <span class="badge muted">отключена</span>`}
            ${s.ready ? nothing : html` <span class="badge warn" title="Канал выбран, но получатель не заполнен">не готова к отправке</span>`}</div>
          <div class="desc">каналы: ${serviceChannels(s)}${s.email_to ? ` · ящик: ${s.email_to}` : ''}${s.chat_ids.length ? ` · чатов: ${s.chat_ids.length}` : ''}
            · пунктов закреплено: ${s.items_total}${s.note ? ` · ${s.note}` : ''}</div></div>
        ${canEdit ? html`<div class="row-actions">
          <button class="btn btn-sm btn-ghost" data-sedit=${s.id} @click=${() => serviceEditModal(s, again)}>Править</button>
          ${s.active ? html`<button class="btn btn-sm btn-ghost" data-sdel=${s.id} @click=${() => off(s)}>Отключить</button>` : nothing}</div>` : nothing}
      </div>`) : html`<div class="empty">Служб нет — добавьте первую</div>`}</div>
    <p class="hint">Служба — получатель недостатков: закрепляется за пунктом шаблона зоны (вкладка
    «Чек-листы»), а у отдельного объекта её можно переопределить. Каналы — чекбоксы «чат» и «письмо».
    Токен бота, каталог чатов и почтовый сервер настраиваются в общих настройках приложения —
    «Настройки → Чаты и Почта»: транспорт один на всё приложение.</p>`;
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
    body: html`<label class="field"><span>Название</span>
        <input type="text" id="sv-name" .value=${s.name} maxlength="160"></label>
      <div class="opt-group-title">Каналы доставки</div>
      <label class="chk"><input type="checkbox" id="sv-tg" .checked=${!!s.use_telegram}>
        Чат (Telegram)</label>
      <label class="chk"><input type="checkbox" id="sv-mail" .checked=${!!s.use_email}>
        Письмо (e-mail)</label>
      <div class="grid-2">
        <label class="field"><span>Ящик службы</span>
          <input type="email" id="sv-to" .value=${s.email_to || ''} maxlength="200" placeholder="service@resort.example"></label>
        <label class="field"><span>Копия (через запятую)</span>
          <input type="text" id="sv-copy" .value=${s.email_copy || ''} maxlength="400"></label>
      </div>
      <label class="field"><span>Примечание</span>
        <input type="text" id="sv-note" .value=${s.note || ''} maxlength="300" placeholder="круглосуточный пост, дежурный инженер…"></label>
      <div class="grid-2">
        <label class="field"><span>Порядок</span><input type="number" id="sv-order" .value=${String(s.sort_order)}></label>
        <label class="field"><span>Активна</span><select id="sv-active">
          <option value="1" ?selected=${s.active}>да</option>
          <option value="0" ?selected=${!s.active}>нет</option></select></label>
      </div>
      <div class="opt-group-title">Чаты Telegram — отметить галочками</div>
      ${chats.length ? html`<div class="check-list" style="max-height:180px;overflow:auto">
          ${chats.map(c => html`<label class="chk"><input type="checkbox" data-chat=${c.chat_id}
              .checked=${picked.has(Number(c.chat_id))}>
            <span style="flex:1">${c.title} <code>${String(c.chat_id)}</code>
              <span class="badge muted">${c.kind}</span>
              ${c.used_by && c.used_by.filter(n => n !== s.name).length
                ? html`<span class="badge info">уже: ${c.used_by.filter(n => n !== s.name).join(', ')}</span>` : nothing}</span></label>`)}
        </div>
        <p class="hint" style="margin-top:6px">Список общий для всего приложения: бот добавляется в группы
        служб, каталог обновляется кнопкой «Обновить список чатов (getUpdates)» в
        «Настройки → Чаты и Почта». Один чат можно закрепить за несколькими службами —
        тогда каждая получит своё сообщение.</p>`
        : html`<div class="hint" style="margin-top:0">Каталог чатов пуст. Чтобы чат появился:
        1) в «Настройки → Чаты и Почта» сохраните токен бота и нажмите «Проверить бота»;
        2) в Telegram добавьте бота в группу службы и напишите в группу любое сообщение;
        3) там же нажмите «Обновить список чатов (getUpdates)»; 4) вернитесь сюда и
        отметьте чат галочкой. Личные чаты попадают в каталог так же — напишите боту.</div>`}`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Сохранить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        const chatIds = $$('[data-chat]', m).filter(cb => cb.checked)
          .map(cb => Number(cb.dataset.chat));
        try {
          const r = await api(`/api/night/services/${s.id}`, { method: 'PUT', body: {
            name: $('#sv-name', m).value.trim(), sort_order: Number($('#sv-order', m).value) || 100,
            active: $('#sv-active', m).value === '1', use_telegram: $('#sv-tg', m).checked,
            use_email: $('#sv-mail', m).checked, email_to: $('#sv-to', m).value.trim(),
            email_copy: $('#sv-copy', m).value.trim(), chat_ids: chatIds,
            note: $('#sv-note', m).value.trim() } });
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
async function loadItems(zones) {
  if (!zones.some(z => z.id === nightState.dictZone)) nightState.dictZone = zones[0].id;
  const zid = nightState.dictZone;
  let zd;
  try { zd = await api(`/api/night/zones/${zid}/items`); }
  catch (e) { return { error: e.message }; }
  const zoneAreas = zd.areas || [];
  if (!zoneAreas.some(a => a.id === nightState.dictArea)) {
    nightState.dictArea = zoneAreas.length ? zoneAreas[0].id : null;
  }
  let cl = null;
  if (nightState.dictArea) {
    try { cl = await api(`/api/night/areas/${nightState.dictArea}/checklist`); }
    catch { cl = null; }
  }
  return { zid, zd, zoneAreas, cl };
}

function itemsTab(items, zones, services, canEdit, again, host) {
  if (!zones.length) return html`<div class="empty">Сначала создайте зону — форма в списке слева</div>`;
  if (!items) return html`<div class="empty">Загрузка…</div>`;
  if (items.error) return html`<div class="empty">${items.error}</div>`;
  const { zid, zd, zoneAreas, cl } = items;
  const addItem = async () => {
    const text = $('#di-text', host).value.trim();
    if (!text) return toast('Введите текст пункта', 'warn');
    try {
      const r = await api(`/api/night/zones/${zid}/items`, { method: 'POST',
        body: { text, sort_order: Number($('#di-order', host).value) || 100, active: true,
                service_id: Number($('#di-service', host).value) || null } });
      toast(`Пункт добавлен в шаблон зоны${r.sections_refreshed ? ` · пересобрано смен: ${r.sections_refreshed}` : ''}`, 'ok');
      again();
    } catch (e) { toast(e.message, 'err'); }
  };
  const toggle = async i => {
    try {
      await api(`/api/night/zone-items/${i.id}`, { method: 'PUT',
        body: { text: i.text, sort_order: i.sort_order, active: !i.active,
                service_id: i.service_id || null } });
      again();
    } catch (e) { toast(e.message, 'err'); }
  };
  const del = i => confirmDialog('Удалить пункт шаблона зоны?',
    `«${i.text}» исчезнет из чек-листов всех объектов зоны (${zoneAreas.length}) в ещё не начатых сменах. `
    + 'В закрытых сменах останется навсегда.',
    async () => {
      try { const r = await api(`/api/night/zone-items/${i.id}`, { method: 'DELETE' });
        toast(`Пункт удалён${r.removed_from_open ? `, убрано из смен: ${r.removed_from_open}` : ''}`, 'ok'); again(); }
      catch (e) { toast(e.message, 'err'); }
    }, 'Удалить');
  return html`
    <label class="field"><span>Зона</span><select id="di-zone"
      @change=${e => { nightState.dictZone = Number(e.target.value); nightState.dictArea = null; again(); }}>
      ${zones.map(z => html`<option value=${z.id} ?selected=${z.id === zid}>${z.name}</option>`)}
    </select></label>
    <div class="opt-group-title">Шаблон чек-листа зоны · объектов в зоне: ${zoneAreas.length}</div>
    ${canEdit ? html`<div class="grid-2" style="grid-template-columns:1fr 200px 90px auto;margin-bottom:10px">
        <input type="text" id="di-text" maxlength="300" placeholder="Пункт шаблона (например: Витражи закрыты)">
        <select id="di-service" title="Ответственная служба">${serviceOptions(services, null)}</select>
        <input type="number" id="di-order" .value=${'100'} title="Порядок">
        <button class="btn btn-primary" id="di-add" @click=${addItem}>Добавить в зону</button></div>` : nothing}
    <div class="check-list" style="max-height:24vh">${zd.items.length ? zd.items.map(i => html`
      <div class="rule-row" style="grid-template-columns:1fr auto">
        <div><div class="lbl">${i.text} <small class="muted">порядок ${i.sort_order}</small>
            ${i.active ? nothing : html` <span class="badge muted">отключён</span>`}
            ${i.service_name ? html`<span class="badge info" title="Ответственная служба">⚖ ${i.service_name}</span>`
              : html`<span class="badge muted" title="Служба не задана — недостаток никуда не уйдёт">без службы</span>`}
            ${i.overrides ? html`<span class="badge warn" title="у объектов зоны своя формулировка/отключение">индивидуально: ${i.overrides}</span>` : nothing}</div>
          <div class="desc">действует для всех объектов зоны</div></div>
        ${canEdit ? html`<div class="row-actions">
          <button class="btn btn-sm btn-ghost" data-ziedit=${i.id} @click=${() => nightZoneItemEditModal(i, services, again)}>Править</button>
          <button class="btn btn-sm btn-ghost" data-zitoggle=${i.id} @click=${() => toggle(i)}>${i.active ? 'Отключить' : 'Включить'}</button>
          <button class="btn btn-sm btn-ghost" data-zidel=${i.id} @click=${() => del(i)}>Удалить</button></div>` : nothing}
      </div>`) : html`<div class="empty">Пунктов шаблона нет — добавьте первый</div>`}</div>

    <div class="opt-group-title">Индивидуальные особенности объекта</div>
    ${cl ? html`
      <label class="field"><span>Объект зоны</span><select id="di-area"
        @change=${e => { nightState.dictArea = Number(e.target.value); again(); }}>
        ${zoneAreas.map(a => html`<option value=${a.id} ?selected=${a.id === cl.area.id}>${a.name}</option>`)}
      </select></label>
      <div class="check-list" style="max-height:26vh">${cl.zone_items.length ? cl.zone_items.map(i => html`
        <div class="rule-row" style="grid-template-columns:1fr auto">
          <div><div class="lbl">${i.in_checklist ? i.effective_text : i.text}
              ${i.disabled ? html` <span class="badge muted">не проверяется</span>`
                : (i.override_text ? html` <span class="badge warn">своя формулировка</span>` : nothing)}
              ${i.effective_service_name ? html`<span class="badge info" title="Кто получает недостаток">⚖ ${i.effective_service_name}</span>` : nothing}
              ${i.override_service_id ? html`<span class="badge warn">своя служба</span>` : nothing}</div>
            <div class="desc">${i.override_text || i.disabled || i.override_service_id
              ? `в шаблоне зоны: ${i.text}${i.service_name ? ` · ${i.service_name}` : ''}`
              : 'как в шаблоне зоне'}</div></div>
          ${canEdit ? html`<div class="row-actions">
            <button class="btn btn-sm btn-ghost" data-ov=${i.id} @click=${() => nightOverrideModal(i, cl.area, services, again)}>Правка</button></div>` : nothing}
        </div>`) : html`<div class="empty">Шаблон зоны пуст</div>`}</div>
      <div class="row-actions" style="margin-top:10px">
        <button class="btn btn-sm" data-own=${cl.area.id}
          @click=${() => nightItemsModal({ id: cl.area.id, name: cl.area.name }, again)}>Свои пункты объекта (${cl.own_items.length})</button>
        <span class="hint" style="margin:0">итоговый чек-лист объекта: ${cl.effective.length} пунктов</span></div>`
      : html`<div class="empty">В зоне нет объектов — добавьте их на вкладке «Объекты»</div>`}`;
}

function nightZoneItemEditModal(i, services, after) {
  openModal({
    title: 'Пункт шаблона зоны',
    subtitle: i.text,
    body: html`<label class="field"><span>Текст</span>
        <input type="text" id="zi-text" .value=${i.text} maxlength="300"></label>
      <label class="field"><span>Ответственная служба</span>
        <select id="zi-service">${serviceOptions(services, i.service_id)}</select></label>
      <div class="grid-2">
        <label class="field"><span>Порядок</span><input type="number" id="zi-order" .value=${String(i.sort_order)}></label>
        <label class="field"><span>Активен</span><select id="zi-active">
          <option value="1" ?selected=${i.active}>да</option>
          <option value="0" ?selected=${!i.active}>нет</option></select></label>
      </div>
      <p class="hint">Служба — получатель недостатка по этому пункту: она действует для всех объектов
      зоны, а у отдельного объекта её можно переопределить. Правка текста и службы обновляет пункт
      во всех объектах зоны и в незакрытых сменах; в закрытых останется снимок.</p>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Сохранить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        try {
          await api(`/api/night/zone-items/${i.id}`, { method: 'PUT', body: {
            text: $('#zi-text', m).value.trim(), sort_order: Number($('#zi-order', m).value) || 100,
            active: $('#zi-active', m).value === '1',
            service_id: Number($('#zi-service', m).value) || null } });
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
    body: html`<label class="field"><span>Формулировка у этого объекта</span>
        <input type="text" id="ov-text" .value=${i.override_text || i.text} maxlength="300"></label>
      <label class="field"><span>Ответственная служба</span>
        <select id="ov-service">${serviceOptions(services, i.override_service_id || i.service_id,
          i.service_name ? `как в шаблоне зоны (${i.service_name})` : '— как в шаблоне зоны —')}</select></label>
      <label class="chk"><input type="checkbox" id="ov-dis" .checked=${!!i.disabled}>
        Не проверять этот пункт у объекта</label>
      <p class="hint">В шаблоне зоны пункт останется прежним — правка касается только «${area.name}».
      Своя служба нужна, когда за объект отвечает не та же служба, что за зону (например, детскую
      комнату проверяет батлер-сервис, а не хозяйственная служба). Применяется к ещё не начатым
      объектам в открытых сменах; начатые и закрытые не трогаются.</p>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button>
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
            text: $('#ov-text', m).value.trim(), disabled: $('#ov-dis', m).checked,
            service_id: Number($('#ov-service', m).value) || null } });
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
  const draw = async () => {
    const [ar, sr] = await Promise.all([api('/api/night/areas'), api('/api/night/services')]);
    const fresh = ar.areas.find(x => x.id === a.id);
    const services = sr.services || [];
    openModal({
      title: 'Свои пункты: ' + fresh.name,
      subtitle: 'Пункты только этого объекта — дополнительно к шаблону зоны. Правка текста обновляет пункт в незакрытых сменах',
      wide: true,
      body: html`<div class="grid-2" style="grid-template-columns:1fr 200px 90px auto;margin-bottom:12px">
          <input type="text" id="it-text" maxlength="300" placeholder="Например: Детская кроватка установлена">
          <select id="it-service" title="Ответственная служба">${serviceOptions(services, null)}</select>
          <input type="number" id="it-order" .value=${'100'} title="Порядок">
          <button class="btn btn-primary" id="it-add">Добавить</button></div>
        <div class="check-list" style="max-height:46vh">${fresh.items.length ? fresh.items.map(it => html`
          <div class="rule-row" style="grid-template-columns:1fr auto">
            <div><div class="lbl">${it.text} <small class="muted">· порядок ${it.sort_order}</small>
              ${it.active ? nothing : html` <span class="badge muted">отключён</span>`}
              ${it.service_name ? html`<span class="badge info" title="Ответственная служба">⚖ ${it.service_name}</span>` : nothing}</div>
              <div class="desc">зона: ${fresh.zone_name || '—'} · всего в чек-листе объекта: ${fresh.effective_total}</div></div>
            <div class="row-actions">
              <button class="btn btn-sm btn-ghost" data-it-edit=${it.id} @click=${() => editItem(it, services)}>Править</button>
              <button class="btn btn-sm btn-ghost" data-it-toggle=${it.id} @click=${() => toggleItem(it)}>${it.active ? 'Отключить' : 'Включить'}</button>
              <button class="btn btn-sm btn-ghost" data-it-del=${it.id} @click=${() => delItem(it)}>Удалить</button>
            </div></div>`) : html`<div class="empty">Своих пунктов нет — объект проверяется по шаблону зоны</div>`}</div>`,
      footer: html`<button class="btn" data-back>← К чек-листам</button><button class="btn btn-ghost" data-cancel>Закрыть</button>`,
      onMount(m) {
        m.querySelector('[data-cancel]').onclick = closeModal;
        m.querySelector('[data-back]').onclick = () => { closeModal(); if (after) after(); };
        $('#it-add', m).onclick = async () => {
          const text = $('#it-text', m).value.trim();
          if (!text) return toast('Введите текст пункта', 'warn');
          try {
            const r = await api(`/api/night/areas/${fresh.id}/items`, { method: 'POST',
              body: { text, sort_order: Number($('#it-order', m).value) || 100, active: true,
                      service_id: Number($('#it-service', m).value) || null } });
            toast(`Пункт добавлен${r.added_to_open_sections ? ` (попал в открытых смен: ${r.added_to_open_sections})` : ''}`, 'ok');
            draw();
          } catch (e) { toast(e.message, 'err'); }
        };
      },
    });
  };
  const editItem = (it, services) => openModal({
    title: 'Пункт объекта',
    body: html`<label class="field"><span>Текст</span><input type="text" id="ie-text" .value=${it.text} maxlength="300"></label>
      <label class="field"><span>Ответственная служба</span>
        <select id="ie-service">${serviceOptions(services, it.service_id)}</select></label>
      <div class="grid-2">
        <label class="field"><span>Порядок</span><input type="number" id="ie-order" .value=${String(it.sort_order)}></label>
        <label class="field"><span>Активен</span><select id="ie-active">
          <option value="1" ?selected=${it.active}>да</option>
          <option value="0" ?selected=${!it.active}>нет</option></select></label>
      </div>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button><button class="btn btn-primary" data-ok>Сохранить</button>`,
    onMount(mm) {
      mm.querySelector('[data-cancel]').onclick = () => { closeModal(); draw(); };
      mm.querySelector('[data-ok]').onclick = async () => {
        try {
          await api(`/api/night/items/${it.id}`, { method: 'PUT', body: {
            text: $('#ie-text', mm).value.trim(), sort_order: Number($('#ie-order', mm).value) || 100,
            active: $('#ie-active', mm).value === '1',
            service_id: Number($('#ie-service', mm).value) || null } });
          toast('Пункт сохранён', 'ok'); draw();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
  const toggleItem = async it => {
    try {
      await api(`/api/night/items/${it.id}`, { method: 'PUT', body: { text: it.text, sort_order: it.sort_order, active: !it.active, service_id: it.service_id || null } });
      draw();
    } catch (e) { toast(e.message, 'err'); }
  };
  const delItem = it => confirmDialog('Удалить пункт?', `«${it.text}» исчезнет из незакрытых смен; в закрытых останется.`,
    async () => { try { await api(`/api/night/items/${it.id}`, { method: 'DELETE' }); toast('Пункт удалён', 'ok'); draw(); }
                  catch (e) { toast(e.message, 'err'); } }, 'Удалить');
  await draw();
}
