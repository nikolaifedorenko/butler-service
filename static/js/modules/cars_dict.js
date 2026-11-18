/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН НАСТРОЕК «ЭЛЕКТРОКАРЫ» — парк и места стоянки (выделен из cars.js в шаге 6е;
   на шаблоны переедет вместе с остальными экранами Настроек, шаг 6ж).
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

registerModule({ screens: { cars: { render: renderCarsDictScreen, icon: 'car' } } });

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

/* ── мост к общей области имён (генерируется tools/gen_js_globals.py; уйдёт вместе с переходом файла на import/export) ── */
Object.assign(globalThis, {
  renderCarsDictScreen,
  bindCarsDictScreen,
});
/* ── конец моста ── */
