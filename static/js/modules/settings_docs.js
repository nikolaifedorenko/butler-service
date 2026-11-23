/* Раздел «Настройки»: экран «Документы и справочники».
   Оболочка, черновик версии справочников и общие помощники — в settings.js.
   Модуль на lit-html (ADR-0013, раздел 7). */
'use strict';

import { can, registerModule } from '../app.js';
import { $, $$, api, closeModal, openModal, state, toast } from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { settingsHeadView, settingsPanelView, settingsRefresh, settingsUI } from './settings.js';
import { openKindModal, renderDicts } from './dicts.js';

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
      return html`<label class="switch"><input type="checkbox" aria-label=${item.description || item.key} data-k=${item.key} .checked=${!!item.value} ?disabled=${!edit}><span class="sl"></span></label>`;
    }
    return html`<input type=${item.type === 'int' ? 'number' : 'text'} aria-label=${item.description || item.key} data-k=${item.key} .value=${String(item.value ?? '')} style="max-width:180px" ?disabled=${!edit}>`;
  };
  const saveRules = async () => {
    const payload = $$('[data-k]', host).map(i => ({ key: i.dataset.k,
      value: String(i.type === 'checkbox' ? (i.checked ? '1' : '0') : i.value) }));
    try {
      await api('/api/settings', { method: 'PUT', body: payload });
      toast('Правила объекта сохранены', 'ok');
      await settingsRefresh();
    } catch (e) { toast(e.message, 'err'); }
  };
  const saveDoc = async () => {
    try {
      await api('/api/settings/doc', { method: 'PUT', body: {
        company: $('#d-company', host).value, director: $('#d-director', host).value } });
      toast('Реквизиты сохранены', 'ok');
      await settingsRefresh();
    } catch (e) { toast(e.message, 'err'); }
  };
  const help = () => openModal({
    title: 'Плейсхолдеры документов', wide: true,
    body: html`<table class="data">${Object.entries(docsInfo?.placeholders || {}).map(([k, v]) =>
      html`<tr><td><code>{${k}}</code></td><td>${v}</td></tr>`)}</table>`,
    footer: html`<button class="btn btn-primary" data-ok>Понятно</button>`,
    onMount(m) { m.querySelector('[data-ok]').onclick = closeModal; },
  });
  const kinds = docsInfo?.kinds || [];
  render(html`
    ${settingsHeadView('Документы и справочники',
      'Реквизиты для печати, виды заявлений и бланки, департаменты и службы, прочие правила объекта. На математику расчёта не влияют.',
      edit ? html`<button class="btn btn-sm btn-primary" id="dc-save" @click=${saveRules}>Сохранить правила объекта</button>` : nothing)}
    ${settingsPanelView('Реквизиты организации', html`
      <div class="grid-2">
        <label class="field"><span>Организация</span><input type="text" id="d-company" .value=${data.doc?.company || ''} ?disabled=${!edit}></label>
        <label class="field"><span>Кому (шапка заявления)</span><input type="text" id="d-director" .value=${data.doc?.director || ''} ?disabled=${!edit}></label>
      </div>
      ${edit ? html`<button class="btn btn-primary btn-sm" id="d-save" @click=${saveDoc}>Сохранить реквизиты</button>` : nothing}`)}
    ${settingsPanelView('Виды заявлений и шаблоны', html`
      <p class="hint" style="margin:-4px 0 12px">Виды заявлений — расширяемый справочник: у каждого свой текст
        с плейсхолдерами и (по желанию) фирменный бланк .docx. Вид привязывается к отсутствию в словаре смен —
        документ печатается из ячейки Графика («Печать заявления», DOCX, PDF).
        ${docsInfo?.pdf_available ? nothing : html`<br>PDF на сервере недоступен: ${docsInfo?.pdf?.error || 'не установлен reportlab'}. DOCX работает всегда.`}</p>
      <table class="data"><thead><tr><th>Вид заявления</th><th>Код</th><th>Фирменный бланк</th><th></th></tr></thead>
      <tbody>${kinds.length ? kinds.map(k => html`<tr>
        <td>${k.name}${k.builtin ? html` <span class="badge">встроенный</span>` : nothing}${k.active ? nothing : html` <span class="badge muted">скрыт</span>`}</td>
        <td><code>${k.code}</code></td>
        <td>${k.template?.uploaded ? html`<span class="badge ok" title=${k.template.filename || ''}>загружен</span>` : html`<span class="badge muted">печать текстом</span>`}</td>
        <td class="num" style="white-space:nowrap">${edit ? html`<button class="btn btn-sm btn-ghost" data-kind=${k.id} @click=${() => openKindModal(k)}>Изменить</button>` : nothing}</td>
      </tr>`) : html`<tr><td colspan="4" class="empty">Виды заявлений не найдены</td></tr>`}</tbody></table>
      <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
        ${edit ? html`<button class="btn btn-sm" id="d-add-kind" @click=${() => openKindModal(null)}>+ Новый вид заявления</button>` : nothing}
        <button class="btn btn-sm btn-ghost" id="d-kind-help" @click=${help}>Справка по плейсхолдерам</button>
      </div>`)}
    ${settingsPanelView('Департаменты и службы', html`
      <p class="hint" style="margin:-4px 0 12px">Значения справочников попадают в карточку сотрудника и
        подставляются в документы. Переименование обновляет карточки, удаление — очищает поле у сотрудников,
        где значение было выбрано.</p>
      <div class="grid-2" id="dicts-body"><div class="skel-wrap"><div class="skel-line skel-lg"></div><div class="skel-line"></div><div class="skel-line"></div></div></div>`)}
    ${settingsPanelView('Прочие правила объекта', html`
      ${(data.items || []).length ? data.items.map(i => html`<div class="rule-row">
        <div><div class="lbl">${i.description || i.key}</div>
          <div class="desc"><code>${i.key}</code> · по умолчанию: ${i.default}</div></div>
        <div class="rule-input">${input(i)}${String(i.value) !== String(i.default)
          ? html`<span class="badge warn" title=${`по умолчанию ${i.default}`}>изменено</span>` : nothing}</div>
      </div>`) : html`<p class="hint">Правил нет</p>`}
      <p class="hint">Правила расчёта часов, переработок и банка — на экранах «Расчёт» и «Правила оплаты».</p>`)}`, mount(host));
  renderDicts();
}
