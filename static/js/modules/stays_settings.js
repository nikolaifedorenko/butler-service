/* ══════════════════════════════════════════════════════════════════════
   «ШАХМАТКА» — экраны Настроек (§6): фонд и категории, сопровождение,
   настраиваемые поля, метки броней. Запись — право stays.setup.
   Использует хелперы app.js / settings.js: $ $$ esc api openModal closeModal
   confirmDialog toast settingsHead settingsPanel.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

registerModule({ screens: {
  stays_fund: { render: renderStaysFund, icon: 'home' },
  stays_escort: { render: renderStaysEscort, icon: 'people' },
  stays_fields: { render: renderStaysFields, icon: 'list' },
  stays_labels: { render: renderStaysLabels, icon: 'code' },
} });

const STAYS_FIELD_KINDS = { text: 'текст', choice: 'список', bool: 'да / нет', date: 'дата' };

/* форма-модалка: поля по описанию, кнопка [data-save] вызывает save(значения);
   mount(m) — по желанию, после отрисовки (динамические строки формы) */
function staysForm(title, rows, save, mount) {
  openModal({
    title,
    body: rows.join(''),
    footer: '<button class="btn btn-ghost" data-close>Отмена</button><button class="btn btn-primary" data-save>Сохранить</button>',
    onMount(m) {
      m.querySelector('[data-close]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        try { await save(m); closeModal(); } catch (e) { toast(e.message, 'err'); }
      };
      if (mount) mount(m);
    },
  });
}
const sfRow = (label, control) => `<label class="field"><span>${esc(label)}</span>${control}</label>`;
const sfInput = (id, value = '', type = 'text') => `<input id="${id}" type="${type}" value="${esc(String(value ?? ''))}">`;
const sfCheck = (id, label, on) => `<label class="chk"><input id="${id}" type="checkbox"${on ? ' checked' : ''}> ${esc(label)}</label>`;
const sfSelect = (id, options, value) => `<select id="${id}">${options.map(([v, t]) =>
  `<option value="${esc(String(v))}"${String(v) === String(value) ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select>`;

function staysDeleteButton(attr, id) {
  return `<button class="btn btn-sm btn-ghost" ${attr}="${id}">Удалить</button>`;
}
function staysBindDeletes(host, attr, url, what, rerender) {
  $$(`[${attr}]`, host).forEach(b => {
    b.onclick = () => confirmDialog(`Удалить ${what}?`, 'Действие попадёт в журнал аудита.', async () => {
      try { await api(`${url}/${b.getAttribute(attr)}`, { method: 'DELETE' }); toast('Удалено'); rerender(); }
      catch (e) { toast(e.message, 'err'); }
    }, 'Удалить');
  });
}

/* ─────────────── Фонд и категории ─────────────── */
async function renderStaysFund(host) {
  const fund = await staysFund(true);          // категории и объекты — фонд на сегодня
  const kinds = Object.fromEntries(fund.kinds.map(k => [k.code, k.title]));
  const cats = Object.fromEntries(fund.categories.map(c => [c.id, c]));
  const rerender = () => renderStaysFund(host);
  host.innerHTML = `
    ${settingsHead('Фонд и категории', 'Категории с видом, сопровождением и весом нагрузки; объекты по корпусам и этажам.')}
    ${settingsPanel('Категории', `
      <div class="table-wrap"><table class="data">
        <thead><tr><th>Код</th><th>Название</th><th>Вид</th><th>Сопровождение</th><th class="num">Вес</th><th></th></tr></thead>
        <tbody>${fund.categories.map(c => `<tr>
          <td><b>${esc(c.code)}</b></td><td>${esc(c.title)}</td><td>${esc(kinds[c.kind] || c.kind)}</td>
          <td>${c.escorted ? '<span class="badge ok">с батлером</span>' : '<span class="muted">нет</span>'}</td>
          <td class="num">${esc(String(c.weight))}</td>
          <td class="num"><button class="btn btn-sm btn-ghost" data-cat-edit="${c.id}">Изменить</button>${staysDeleteButton('data-cat-del', c.id)}</td>
        </tr>`).join('') || '<tr><td colspan="6" class="empty">Категорий пока нет</td></tr>'}</tbody></table></div>`,
      '<button class="btn btn-sm btn-primary" id="sf-cat-add" style="float:right">+ Категория</button>')}
    ${settingsPanel(`Объекты · ${fund.units.length}`, `
      <div class="table-wrap" style="max-height:420px"><table class="data">
        <thead><tr><th>Объект</th><th>Категория</th><th>Корпус</th><th>Этаж</th><th></th></tr></thead>
        <tbody>${fund.units.map(u => `<tr>
          <td><b>${esc(u.label)}</b>${u.active ? '' : ' <span class="badge muted">неактивен</span>'}</td>
          <td>${esc(cats[u.category_id]?.code || '—')}</td><td>${esc(u.building)}</td><td>${esc(u.floor)}</td>
          <td class="num"><button class="btn btn-sm btn-ghost" data-unit-edit="${u.id}">Изменить</button>${staysDeleteButton('data-unit-del', u.id)}</td>
        </tr>`).join('') || '<tr><td colspan="5" class="empty">Объектов пока нет</td></tr>'}</tbody></table></div>`,
      '<button class="btn btn-sm btn-primary" id="sf-unit-add" style="float:right">+ Объект</button>')}`;

  const catForm = c => staysForm(c ? `Категория ${c.code}` : 'Новая категория', [
    sfRow('Код', sfInput('sf-code', c?.code)), sfRow('Название', sfInput('sf-title', c?.title)),
    sfRow('Вид', sfSelect('sf-kind', fund.kinds.map(k => [k.code, k.title]), c?.kind || 'room')),
    sfRow('Вес нагрузки', sfInput('sf-weight', c?.weight ?? 1, 'number')),
    sfRow('Порядок', sfInput('sf-sort', c?.sort_order ?? 100, 'number')),
    sfCheck('sf-escorted', 'С батлер-сопровождением', c?.escorted),
  ], async m => {
    const body = { code: $('#sf-code', m).value, title: $('#sf-title', m).value, kind: $('#sf-kind', m).value,
      weight: Number($('#sf-weight', m).value), sort_order: Number($('#sf-sort', m).value),
      escorted: $('#sf-escorted', m).checked };
    await api(c ? `/api/stays/categories/${c.id}` : '/api/stays/categories', { method: c ? 'PUT' : 'POST', body });
    toast('Категория сохранена'); rerender();
  });
  const unitForm = u => staysForm(u ? `Объект ${u.label}` : 'Новый объект', [
    sfRow('Обозначение', sfInput('sf-label', u?.label)),
    sfRow('Категория', sfSelect('sf-cat', fund.categories.map(c => [c.id, `${c.code} · ${c.title}`]), u?.category_id)),
    sfRow('Корпус', sfInput('sf-building', u?.building)), sfRow('Этаж', sfInput('sf-floor', u?.floor)),
    sfRow('Порядок', sfInput('sf-usort', u?.sort_order ?? 100, 'number')),
    sfCheck('sf-active', 'Активен', u ? u.active : true),
  ], async m => {
    const body = { label: $('#sf-label', m).value, category_id: Number($('#sf-cat', m).value),
      building: $('#sf-building', m).value, floor: $('#sf-floor', m).value,
      sort_order: Number($('#sf-usort', m).value), active: $('#sf-active', m).checked };
    await api(u ? `/api/stays/units/${u.id}` : '/api/stays/units', { method: u ? 'PUT' : 'POST', body });
    toast('Объект сохранён'); rerender();
  });
  $('#sf-cat-add', host).onclick = () => catForm(null);
  $('#sf-unit-add', host).onclick = () => (fund.categories.length ? unitForm(null) : toast('Сначала заведите категорию', 'err'));
  $$('[data-cat-edit]', host).forEach(b => { b.onclick = () => catForm(cats[b.dataset.catEdit]); });
  $$('[data-unit-edit]', host).forEach(b => { b.onclick = () => unitForm(fund.units.find(u => u.id === Number(b.dataset.unitEdit))); });
  staysBindDeletes(host, 'data-cat-del', '/api/stays/categories', 'категорию', rerender);
  staysBindDeletes(host, 'data-unit-del', '/api/stays/units', 'объект', rerender);
}

/* ─────────────── Сопровождение ─────────────── */
async function renderStaysEscort(host) {
  const fund = await api('/api/stays/fund', { silent: true });
  const on = Object.fromEntries(fund.escorts.map(e => [e.employee_id, e.active]));
  const s = fund.settings;
  host.innerHTML = `
    ${settingsHead('Сопровождение', 'Кто ведёт гостей, надбавки за VIP/VVIP и дневной лимит нагрузки батлера.')}
    ${settingsPanel('Сопровождают гостей', `
      <div class="check-list" style="max-height:360px">${(fund.staff || []).map(p => `
        <label class="chk"><input type="checkbox" data-escort="${p.id}"${on[p.id] ? ' checked' : ''}>
          ${esc(p.name)} <span class="muted">${esc(p.position)}</span></label>`).join('') || '<div class="empty">Нет сотрудников</div>'}</div>`,
      '<button class="btn btn-sm" id="se-seed" style="float:right">Заполнить по должности «батлер»</button>')}
    ${settingsPanel('Нагрузка', `
      <div class="grid-2">
        ${sfRow('Надбавка VIP', sfInput('se-vip', s.vip_bonus, 'number'))}
        ${sfRow('Надбавка VVIP', sfInput('se-vvip', s.vvip_bonus, 'number'))}
        ${sfRow('Дневной лимит', sfInput('se-limit', s.daily_limit, 'number'))}
        ${sfRow('Коды Табеля «нужна подмена»', sfInput('se-codes', s.replacement_codes))}
      </div>
      <p class="hint">Вес объекта делится поровну между батлерами объекта; надбавка гостя — тому, кто его ведёт.
      Перегруз — предупреждение, сохранять не мешает.</p>
      <button class="btn btn-primary" id="se-save">Сохранить</button>`)}`;
  $$('[data-escort]', host).forEach(cb => {
    cb.onchange = async () => {
      try { await api(`/api/stays/escorts/${cb.dataset.escort}`, { method: 'PUT', body: { active: cb.checked } }); }
      catch (e) { cb.checked = !cb.checked; toast(e.message, 'err'); }
    };
  });
  $('#se-seed', host).onclick = async () => {
    try {
      const r = await api('/api/stays/escorts/seed', { method: 'POST', body: {} });
      toast(r.added ? `Добавлено: ${r.added}` : 'Новых батлеров не найдено');
      renderStaysEscort(host);
    } catch (e) { toast(e.message, 'err'); }
  };
  $('#se-save', host).onclick = async () => {
    try {
      await api('/api/stays/settings', { method: 'PUT', body: {
        vip_bonus: Number($('#se-vip', host).value), vvip_bonus: Number($('#se-vvip', host).value),
        daily_limit: Number($('#se-limit', host).value), replacement_codes: $('#se-codes', host).value } });
      toast('Настройки сохранены');
    } catch (e) { toast(e.message, 'err'); }
  };
}

/* ─────────────── Настраиваемые поля ─────────────── */
async function renderStaysFields(host) {
  const fund = await api('/api/stays/fund', { silent: true });
  const rerender = () => renderStaysFields(host);
  const target = { guest: 'гость', reservation: 'бронь' };
  host.innerHTML = `
    ${settingsHead('Настраиваемые поля', 'Дополнительные сведения о гостях и бронях; по отмеченным полям работает поиск.')}
    ${settingsPanel('Поля', `
      <div class="table-wrap"><table class="data">
        <thead><tr><th>К чему</th><th>Название</th><th>Код</th><th>Тип</th><th>Поиск</th><th></th></tr></thead>
        <tbody>${fund.fields.map(f => `<tr>
          <td>${esc(target[f.target])}</td><td><b>${esc(f.title)}</b></td><td>${esc(f.code)}</td>
          <td>${esc(STAYS_FIELD_KINDS[f.kind])}${f.kind === 'choice' ? ` <span class="muted">${esc(f.choices.join(', '))}</span>` : ''}</td>
          <td>${f.searchable ? 'да' : '—'}</td>
          <td class="num"><button class="btn btn-sm btn-ghost" data-fl-edit="${f.id}">Изменить</button>${staysDeleteButton('data-fl-del', f.id)}</td>
        </tr>`).join('') || '<tr><td colspan="6" class="empty">Полей пока нет</td></tr>'}</tbody></table></div>`,
      '<button class="btn btn-sm btn-primary" id="sfl-add" style="float:right">+ Поле</button>')}`;
  const form = f => staysForm(f ? `Поле «${f.title}»` : 'Новое поле', [
    sfRow('К чему', sfSelect('sfl-target', Object.entries(target), f?.target || 'guest')),
    sfRow('Код (латиница)', sfInput('sfl-code', f?.code)), sfRow('Название', sfInput('sfl-title', f?.title)),
    sfRow('Тип', sfSelect('sfl-kind', Object.entries(STAYS_FIELD_KINDS), f?.kind || 'text')),
    sfRow('Варианты списка — по одному в строке', `<textarea id="sfl-choices" rows="4">${esc((f?.choices || []).join('\n'))}</textarea>`),
    sfCheck('sfl-searchable', 'Искать по полю', f?.searchable),
  ], async m => {
    const body = { target: $('#sfl-target', m).value, code: $('#sfl-code', m).value, title: $('#sfl-title', m).value,
      kind: $('#sfl-kind', m).value, choices: $('#sfl-choices', m).value.split('\n'),
      searchable: $('#sfl-searchable', m).checked, sort_order: f?.sort_order ?? 100 };
    await api(f ? `/api/stays/fields/${f.id}` : '/api/stays/fields', { method: f ? 'PUT' : 'POST', body });
    toast('Поле сохранено'); rerender();
  });
  $('#sfl-add', host).onclick = () => form(null);
  $$('[data-fl-edit]', host).forEach(b => { b.onclick = () => form(fund.fields.find(f => f.id === Number(b.dataset.flEdit))); });
  staysBindDeletes(host, 'data-fl-del', '/api/stays/fields', 'поле', rerender);
}

/* ─────────────── Метки броней ─────────────── */
async function renderStaysLabels(host) {
  const fund = await api('/api/stays/fund', { silent: true });
  const rerender = () => renderStaysLabels(host);
  host.innerHTML = `
    ${settingsHead('Метки броней', 'Цвет полосы брони на шахматке: «От руководства», «Открытый рынок»…')}
    ${settingsPanel('Метки', `
      <div class="check-list">${fund.labels.map(l => `
        <div class="rule-row" style="grid-template-columns:1fr auto">
          <div class="lbl"><span class="stays-swatch" style="background:${esc(l.color)}"></span> ${esc(l.title)}</div>
          <div style="display:flex;gap:6px"><button class="btn btn-sm btn-ghost" data-lb-edit="${l.id}">Изменить</button>${staysDeleteButton('data-lb-del', l.id)}</div>
        </div>`).join('') || '<div class="empty">Меток пока нет</div>'}</div>`,
      '<button class="btn btn-sm btn-primary" id="slb-add" style="float:right">+ Метка</button>')}`;
  const form = l => staysForm(l ? `Метка «${l.title}»` : 'Новая метка', [
    sfRow('Название', sfInput('slb-title', l?.title)), sfRow('Цвет', sfInput('slb-color', l?.color || '#3b6fd8', 'color')),
  ], async m => {
    const body = { title: $('#slb-title', m).value, color: $('#slb-color', m).value };
    await api(l ? `/api/stays/labels/${l.id}` : '/api/stays/labels', { method: l ? 'PUT' : 'POST', body });
    toast('Метка сохранена'); rerender();
  });
  $('#slb-add', host).onclick = () => form(null);
  $$('[data-lb-edit]', host).forEach(b => { b.onclick = () => form(fund.labels.find(l => l.id === Number(b.dataset.lbEdit))); });
  staysBindDeletes(host, 'data-lb-del', '/api/stays/labels', 'метку', rerender);
}
