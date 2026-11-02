/* ══════════════════════════════════════════════════════════════════════
   «ШАХМАТКА» — экраны Настроек (§6): сопровождение, настраиваемые поля, метки
   броней (фонд и категории — stays_fund.js). Запись — право stays.setup.
   Использует хелперы app.js / settings.js: $ $$ esc api openModal closeModal
   confirmDialog toast settingsHead settingsPanel.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

registerModule({ screens: {
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

/* ─────────────── Сопровождение ─────────────── */
const staysFactorText = n => String(Number(n)).replace('.', ',');

async function renderStaysEscort(host) {
  const date = host.dataset.escortDate || staysToday();
  const [fund, snap] = await Promise.all([api('/api/stays/fund', { silent: true }),
    api('/api/stays/fund/snapshot?date=' + date, { silent: true }).catch(() => null)]);   // дата до первой версии фонда — 404
  const rerender = () => { host.dataset.escortDate = $('#se-date', host)?.value || date; renderStaysEscort(host); };
  const on = Object.fromEntries(fund.escorts.map(e => [e.employee_id, e.active]));
  const s = fund.settings;
  const codes = fund.vip_codes || [];
  const escCats = snap ? snap.categories.filter(c => c.escorted) : [];
  const escGroups = snap ? snap.groups.filter(g => g.escorted) : [];
  host.innerHTML = `
    ${settingsHead('Сопровождение', 'Кто ведёт гостей, VIP-коды, коэффициент «Особого гостя» и дневной лимит нагрузки батлера.')}
    ${settingsPanel('Сопровождают гостей', `
      <div class="check-list" style="max-height:360px">${(fund.staff || []).map(p => `
        <label class="chk"><input type="checkbox" data-escort="${p.id}"${on[p.id] ? ' checked' : ''}>
          ${esc(p.name)} <span class="muted">${esc(p.position)}</span></label>`).join('') || '<div class="empty">Нет сотрудников</div>'}</div>`,
      '<button class="btn btn-sm" id="se-seed" style="float:right">Заполнить по должности «батлер»</button>')}
    ${settingsPanel('VIP-коды', `
      <div class="table-wrap"><table class="data" id="se-codes-table">
        <thead><tr><th>Код</th><th>Что значит</th><th>Сопровождение</th><th>Коэффициент</th><th>Порядок</th><th></th></tr></thead>
        <tbody>${codes.map(c => `<tr data-code-row="${c.id}"${c.archived ? ' class="muted"' : ''}>
          <td><b>${esc(c.code)}</b>${c.archived ? ' <span class="badge muted">в архиве</span>' : ''}</td><td>${esc(c.title)}</td>
          <td>${c.escorted ? 'да' : '—'}</td><td>×${esc(staysFactorText(c.factor))}</td><td>${esc(String(c.sort_order))}</td>
          <td class="num"><button class="btn btn-sm btn-ghost" data-code-edit="${c.id}">Изменить</button>
            <button class="btn btn-sm btn-ghost" data-code-arch="${c.id}">${c.archived ? 'Вернуть' : 'В архив'}</button>
            ${staysDeleteButton('data-code-del', c.id)}</td></tr>`).join('') || '<tr><td colspan="6" class="empty">Кодов пока нет</td></tr>'}</tbody></table></div>`,
      '<button class="btn btn-sm btn-primary" id="se-code-add" style="float:right">+ Код</button>')}
    ${settingsPanel('Нагрузка', `
      <div class="grid-2">
        ${sfRow('Коэффициент «Особого гостя»', sfInput('se-special', s.special_factor, 'number'))}
        ${sfRow('Дневной лимит', sfInput('se-limit', s.daily_limit, 'number'))}
        ${sfRow('Коды Табеля «нужна подмена»', sfInput('se-codes', s.replacement_codes))}
      </div>
      <p class="hint">Вес места = категория × коэффициент кода × (Особый гость ? коэффициент : 1); делится поровну между батлерами места.
      После смены коэффициентов подберите лимит нагрузки заново. Перегруз — предупреждение, сохранять не мешает.</p>
      <button class="btn btn-primary" id="se-save">Сохранить</button>`)}
    ${settingsPanel('Правила на дату', `
      <label class="field"><span>Дата</span><input type="date" id="se-date" value="${esc(date)}"></label>
      ${snap ? `
      <div data-rules-cats><b>Категории с сопровождением:</b> ${escCats.map(c => esc(c.code)).join(', ') || '<span class="muted">нет</span>'}</div>
      <div data-rules-groups><b>Узлы с сопровождением:</b> ${escGroups.map(g => esc(g.title)).join(', ') || '<span class="muted">нет</span>'}</div>`
      : '<div data-rules-missing class="muted">правила на эту дату недоступны</div>'}
      <p class="hint">Правятся в «Фонде» (черновиком с даты). <a href="#" id="se-to-fund">Открыть «Фонд»</a></p>`)}`;
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
        special_factor: Number($('#se-special', host).value),
        daily_limit: Number($('#se-limit', host).value), replacement_codes: $('#se-codes', host).value } });
      toast('Настройки сохранены');
    } catch (e) { toast(e.message, 'err'); }
  };
  $('#se-date', host).onchange = rerender;
  $('#se-to-fund', host).onclick = e => { e.preventDefault(); settingsOpen('stays_fund'); };
  const form = c => staysForm(c ? `Код «${c.code}»` : 'Новый код', [
    sfRow('Код (цифры, ведущий ноль значим)', sfInput('vc-code', c?.code)), sfRow('Что значит', sfInput('vc-title', c?.title)),
    sfCheck('vc-escorted', 'С сопровождением', c?.escorted),
    sfRow('Коэффициент нагрузки', sfInput('vc-factor', c?.factor ?? 1, 'number')),
    sfRow('Порядок', sfInput('vc-sort', c?.sort_order ?? 100, 'number')),
  ], async m => {
    const body = { code: $('#vc-code', m).value, title: $('#vc-title', m).value, escorted: $('#vc-escorted', m).checked,
      factor: Number($('#vc-factor', m).value), sort_order: Number($('#vc-sort', m).value) };   // PUT — объект целиком
    await api(c ? `/api/stays/vip-codes/${c.id}` : '/api/stays/vip-codes', { method: c ? 'PUT' : 'POST', body });
    staysState.fund = null; toast('Код сохранён'); rerender();
  });
  $('#se-code-add', host).onclick = () => form(null);
  $$('[data-code-edit]', host).forEach(b => { b.onclick = () => form(codes.find(c => c.id === Number(b.dataset.codeEdit))); });
  $$('[data-code-arch]', host).forEach(b => {
    b.onclick = async () => {
      const c = codes.find(x => x.id === Number(b.dataset.codeArch));
      try { await api(`/api/stays/vip-codes/${c.id}/archive`, { method: 'PUT', body: { archived: !c.archived } }); staysState.fund = null; rerender(); }
      catch (e) { toast(e.message, 'err'); }
    };
  });
  staysBindDeletes(host, 'data-code-del', '/api/stays/vip-codes', 'код', () => { staysState.fund = null; rerender(); });
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
