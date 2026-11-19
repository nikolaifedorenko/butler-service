/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН НАСТРОЕК «ЭЛЕКТРОКАРЫ» — парк и места стоянки (выделен из cars.js в шаге 6е).
   Модуль на lit-html (ADR-0013, раздел 7).
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

import { navigate, registerModule } from '../app.js';
import { $, api, confirmDialog, toast } from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { CAR_BADGE, carAddModal, carEditModal, carsState } from './cars.js';
import { settingsHeadView, settingsPanelView } from './settings.js';

registerModule({ screens: { cars: { render: renderCarsDictScreen, icon: 'car' } } });

/* ─────────── экран Настроек «Электрокары»: парк и места стоянки ───────────
   Единственное место правки парка и справочника мест — экран в «Настройках»
   (группа «Объект», адрес #/settings/cars; docs/PROPOSAL-SETTINGS-IA-2026-10-19.md).
   Переехал из кнопок «+ Кар» и «Места» раздела «Электрокары»: раздел остался
   ежедневным рабочим местом (взять/вернуть/передать/выдать), кнопки — deep-link
   сюда (settingsOpen). Прежняя модалка «Места стоянки» заменена этим экраном.

   Права: видимость экрана — cars.view (+ вход в «Настройки»), правки — cars.manage.
   Вызывается из реестра modules/settings.js (подключается после этого файла). */
async function renderCarsDictScreen(host) {
  const [data, meta, locs] = await Promise.all([
    api('/api/cars', { silent: true }),
    carsState.meta ? Promise.resolve(carsState.meta) : api('/api/cars/meta', { silent: true }),
    api('/api/cars/locations', { silent: true }),
  ]);
  carsState.data = data; carsState.meta = meta;
  carsState.locations = locs.locations || [];
  const canEdit = !!meta.can_manage;
  const cars = data.cars || [];
  const again = () => renderCarsDictScreen(host);

  const addLoc = async () => {
    const name = $('#loc-new', host).value.trim();
    if (!name) return toast('Введите название места', 'warn');
    try { await api('/api/cars/locations', { method: 'POST', body: { name } }); toast('Место добавлено', 'ok'); again(); }
    catch (e) { toast(e.message, 'err'); }
  };
  const rename = async loc => {
    const name = prompt('Новое название места', loc.name);
    if (!name || name.trim() === loc.name) return;
    try { await api(`/api/cars/locations/${loc.id}`, { method: 'PUT', body: { name: name.trim() } }); toast('Переименовано', 'ok'); again(); }
    catch (e) { toast(e.message, 'err'); }
  };
  const toggle = async loc => {
    try { await api(`/api/cars/locations/${loc.id}`, { method: 'PUT', body: { active: !loc.active } }); toast(loc.active ? 'Место отключено' : 'Место включено', 'ok'); again(); }
    catch (e) { toast(e.message, 'err'); }
  };
  const del = loc => confirmDialog('Удалить место стоянки?',
    `«${loc.name}» исчезнет из справочника. Прошлые возвраты хранят место текстом — история не сломается. Если место указано у активного кара, сервер отклонит удаление.`,
    async () => {
      try { await api(`/api/cars/locations/${loc.id}`, { method: 'DELETE' }); toast('Место удалено', 'ok'); again(); }
      catch (e) { toast(e.message, 'err'); }
    }, 'Удалить');

  render(html`
    ${settingsHeadView('Электрокары',
      'Парк и места стоянки — справочник. Ежедневные операции (взять / вернуть / передать / выдать) — в разделе «Электрокары».',
      html`<button class="btn btn-sm btn-ghost" id="cd-to-cars" @click=${() => navigate('cars')}>К операциям ↗</button>
       ${canEdit ? html`<button class="btn btn-sm btn-primary" id="cd-add" @click=${() => carAddModal(again)}>+ Кар</button>` : nothing}`)}
    ${canEdit ? nothing : html`<div class="dict-banner gold"><span>🔒</span><span>Только просмотр: для правок парка и мест нужно право <b>cars.manage</b> (выдаётся в «Настройки → Права доступа»).</span></div>`}
    ${settingsPanelView('Парк', html`
      <div class="table-wrap"><table class="data">
        <thead><tr><th>Кар</th><th>Статус</th><th>Место стоянки</th><th>Закреплён</th><th>Примечание</th><th></th></tr></thead>
        <tbody>${cars.length ? cars.map(c => html`<tr>
          <td><b>№${c.number}</b>${c.active ? nothing : html` <span class="badge muted">отключён</span>`}</td>
          <td><span class=${`badge ${CAR_BADGE[c.status] || 'muted'}`}>${c.status_title}</span></td>
          <td>${c.location || html`<span class="muted">не указано</span>`}</td>
          <td>${c.assigned_name || html`<span class="muted">—</span>`}</td>
          <td>${c.note || ''}</td>
          <td class="num">${canEdit ? html`<button class="btn btn-sm btn-ghost" data-cd-edit=${c.id} @click=${() => carEditModal(c, again)}>Карточка</button>` : nothing}</td>
        </tr>`) : html`<tr><td colspan="6" class="empty">Парк пуст</td></tr>`}</tbody></table></div>
      <p class="hint">Новый кар создаётся свободным без места стоянки — место указывается при возврате
      и в карточке (решение владельца 18.10.2026). Отключение кара (чекбокс в карточке) убирает его
      из списка сотрудников; история операций сохраняется.</p>`)}
    ${settingsPanelView('Места стоянки', html`
      <div class="check-list" style="max-height:320px">${carsState.locations.length ? carsState.locations.map(l => html`
        <div class="rule-row" style="grid-template-columns:1fr auto">
          <div><div class="lbl">${l.name}</div>
            <div class="desc">${l.active ? nothing : html`<span class="badge muted">отключено</span>`}${l.builtin ? ' · встроенное' : ''}</div></div>
          ${canEdit ? html`<div style="display:flex;gap:6px">
            <button class="btn btn-sm btn-ghost" data-loc-rename=${l.id} @click=${() => rename(l)}>Переименовать</button>
            <button class="btn btn-sm btn-ghost" data-loc-toggle=${l.id} @click=${() => toggle(l)}>${l.active ? 'Отключить' : 'Включить'}</button>
            <button class="btn btn-sm btn-ghost" data-loc-del=${l.id} title="Удалить место (если оно не указано у активных каров)" @click=${() => del(l)}>Удалить</button></div>` : nothing}
        </div>`) : html`<div class="empty">Мест пока нет</div>`}</div>
      ${canEdit ? html`<div class="grid-2" style="margin-top:12px">
        <input type="text" id="loc-new" placeholder="Новое место (например: Парковка у корпуса B)" maxlength="160">
        <button class="btn btn-primary" data-loc-add @click=${addLoc}>Добавить</button></div>
      <p class="hint">Удаление места, указанного у активного кара, сервер отклонит (409) — сначала смените
      место у кара или отключите место. Прошлые возвраты хранят место текстом, история не ломается.</p>` : nothing}`)}`, mount(host));
}
