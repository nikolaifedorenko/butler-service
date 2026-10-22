/* Раздел «Настройки»: экран «Документы и справочники» (вынесено из settings.js, шаг 6.5 аудита).
   Оболочка, черновик версии справочников и общие помощники — в settings.js. */
'use strict';

registerModule({ screens: { docs: { render: settingsScreenDocs, icon: 'doc' } } });

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «ДОКУМЕНТЫ И СПРАВОЧНИКИ» — реквизиты, виды заявлений, департаменты
   и службы, прочие правила объекта
   ══════════════════════════════════════════════════════════════════════ */
async function settingsScreenDocs(host) {
  const data = settingsUI.data || {};
  const edit = can('settings.edit');
  let docsInfo = { kinds: state.docKinds || [], placeholders: state.docPlaceholders || {} };
  try { docsInfo = await api('/api/docs/kinds', { silent: true }); } catch { /* работаем с кешем */ }
  state.docKinds = docsInfo.kinds || []; state.docPlaceholders = docsInfo.placeholders || {};

  const input = item => {
    if (item.type === 'bool') {
      return `<label class="switch"><input type="checkbox" data-k="${esc(item.key)}" ${item.value ? 'checked' : ''} ${edit ? '' : 'disabled'}><span class="sl"></span></label>`;
    }
    const type = item.type === 'int' ? 'number' : 'text';
    return `<input type="${type}" data-k="${esc(item.key)}" value="${esc(item.value ?? '')}" style="max-width:180px" ${edit ? '' : 'disabled'}>`;
  };

  host.innerHTML = `
    ${settingsHead('Документы и справочники',
      'Реквизиты для печати, виды заявлений и бланки, департаменты и службы, прочие правила объекта. На математику расчёта не влияют.',
      edit ? '<button class="btn btn-sm btn-primary" id="dc-save">Сохранить правила объекта</button>' : '')}
    ${settingsPanel('Реквизиты организации', `
      <div class="grid-2">
        <label class="field"><span>Организация</span><input type="text" id="d-company" value="${esc(data.doc?.company || '')}" ${edit ? '' : 'disabled'}></label>
        <label class="field"><span>Кому (шапка заявления)</span><input type="text" id="d-director" value="${esc(data.doc?.director || '')}" ${edit ? '' : 'disabled'}></label>
      </div>
      ${edit ? '<button class="btn btn-primary btn-sm" id="d-save">Сохранить реквизиты</button>' : ''}`)}
    ${settingsPanel('Виды заявлений и шаблоны', `
      <p class="hint" style="margin:-4px 0 12px">Виды заявлений — расширяемый справочник: у каждого свой текст
        с плейсхолдерами и (по желанию) фирменный бланк .docx. Вид привязывается к отсутствию в словаре смен —
        документ печатается из ячейки Графика («Печать заявления», DOCX, PDF).
        ${docsInfo?.pdf_available ? '' : '<br>PDF-конвертация станет доступна после установки LibreOffice на сервер (<code>soffice</code>); DOCX работает всегда.'}</p>
      <table class="data"><thead><tr><th>Вид заявления</th><th>Код</th><th>Фирменный бланк</th><th></th></tr></thead>
      <tbody>${(docsInfo?.kinds || []).map(k => `<tr>
        <td>${esc(k.name)}${k.builtin ? ' <span class="badge">встроенный</span>' : ''}${k.active ? '' : ' <span class="badge muted">скрыт</span>'}</td>
        <td><code>${esc(k.code)}</code></td>
        <td>${k.template?.uploaded ? `<span class="badge ok" title="${esc(k.template.filename || '')}">загружен</span>` : '<span class="badge muted">печать текстом</span>'}</td>
        <td class="num" style="white-space:nowrap">${edit ? `<button class="btn btn-sm btn-ghost" data-kind="${k.id}">Изменить</button>` : ''}</td>
      </tr>`).join('') || '<tr><td colspan="4" class="empty">Виды заявлений не найдены</td></tr>'}</tbody></table>
      <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
        ${edit ? '<button class="btn btn-sm" id="d-add-kind">+ Новый вид заявления</button>' : ''}
        <button class="btn btn-sm btn-ghost" id="d-kind-help">Справка по плейсхолдерам</button>
      </div>`)}
    ${settingsPanel('Департаменты и службы', `
      <p class="hint" style="margin:-4px 0 12px">Значения справочников попадают в карточку сотрудника и
        подставляются в документы. Переименование обновляет карточки, удаление — очищает поле у сотрудников,
        где значение было выбрано.</p>
      <div class="grid-2" id="dicts-body"><div class="empty">Загрузка…</div></div>`)}
    ${settingsPanel('Прочие правила объекта', `
      ${(data.items || []).map(i => `<div class="rule-row">
        <div><div class="lbl">${esc(i.description || i.key)}</div>
          <div class="desc"><code>${esc(i.key)}</code> · по умолчанию: ${esc(i.default)}</div></div>
        <div class="rule-input">${input(i)}${String(i.value) !== String(i.default)
          ? `<span class="badge warn" title="по умолчанию ${esc(i.default)}">изменено</span>` : ''}</div>
      </div>`).join('') || '<p class="hint">Правил нет</p>'}
      <p class="hint">Правила расчёта часов, переработок и банка — на экранах «Расчёт» и «Правила оплаты».</p>`)}`;

  renderDicts();
  settingsOn('#dc-save', host, async () => {
    const payload = $$('[data-k]', host).map(i => ({ key: i.dataset.k,
      value: String(i.type === 'checkbox' ? (i.checked ? '1' : '0') : i.value) }));
    try {
      await api('/api/settings', { method: 'PUT', body: payload });
      toast('Правила объекта сохранены', 'ok');
      await settingsRefresh();
    } catch (e) { toast(e.message, 'err'); }
  });
  settingsOn('#d-save', host, async () => {
    try {
      await api('/api/settings/doc', { method: 'PUT', body: {
        company: $('#d-company').value, director: $('#d-director').value } });
      toast('Реквизиты сохранены', 'ok');
      await settingsRefresh();
    } catch (e) { toast(e.message, 'err'); }
  });
  settingsOn('#d-add-kind', host, () => openKindModal(null));
  $$('[data-kind]', host).forEach(b => b.onclick = () =>
    openKindModal((docsInfo?.kinds || []).find(k => k.id === +b.dataset.kind)));
  settingsOn('#d-kind-help', host, () => openModal({
    title: 'Плейсхолдеры документов', wide: true,
    body: `<table class="data">${Object.entries(docsInfo?.placeholders || {}).map(([k, v]) =>
      `<tr><td><code>{${esc(k)}}</code></td><td>${esc(v)}</td></tr>`).join('')}</table>`,
    footer: '<button class="btn btn-primary" data-ok>Понятно</button>',
    onMount(m) { m.querySelector('[data-ok]').onclick = closeModal; },
  }));
}
