/* ══════════════════════════════════════════════════════════════════════
   «ШАХМАТКА» — экраны Настроек (§6): сопровождение, настраиваемые поля, метки
   броней (фонд и категории — stays_fund.js). Запись — право stays.setup.
   Модуль на lit-html (ADR-0013, раздел 7).
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

import { registerModule } from '../app.js';
import { $, api, closeModal, confirmDialog, openModal, toast } from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { checkField, fieldRow, selectField, textInput } from '../ui/form.js';
import { settingsHeadView, settingsOpen, settingsPanelView } from './settings.js';
import { staysState, staysToday } from './stays.js';

registerModule({ screens: {
  stays_escort: { render: renderStaysEscort, icon: 'people' },
  stays_fields: { render: renderStaysFields, icon: 'list' },
  stays_labels: { render: renderStaysLabels, icon: 'code' },
} });

export const STAYS_FIELD_KINDS = { text: 'текст', choice: 'список', bool: 'да / нет', date: 'дата' };

const staysFormFootView = () => html`<button class="btn btn-ghost" data-close>Отмена</button><button class="btn btn-primary" data-save>Сохранить</button>`;

/* форма-модалка: rows — шаблон полей, кнопка [data-save] вызывает save(окно);
   mountForm(окно) — по желанию, после отрисовки */
export function staysForm(title, rows, save, mountForm) {
  openModal({
    title,
    body: html`${rows}`,
    footer: staysFormFootView(),
    onMount(m) {
      m.querySelector('[data-close]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        try { await save(m); closeModal(); } catch (e) { toast(e.message, 'err'); }
      };
      if (mountForm) mountForm(m);
    },
  });
}

/* удаление записи справочника с подтверждением; rerender — перерисовать экран */
export function staysConfirmDelete(url, id, what, rerender) {
  confirmDialog(`Удалить ${what}?`, 'Действие попадёт в журнал аудита.', async () => {
    try { await api(`${url}/${id}`, { method: 'DELETE' }); toast('Удалено'); rerender(); }
    catch (e) { toast(e.message, 'err'); }
  }, 'Удалить');
}

/* ─────────────── Сопровождение ─────────────── */
const staysFactorText = n => String(Number(n)).replace('.', ',');

export async function renderStaysEscort(host) {
  const date = host.dataset.escortDate || staysToday();
  const [fund, snap] = await Promise.all([api('/api/stays/fund', { silent: true }),
    api('/api/stays/fund/snapshot?date=' + date, { silent: true }).catch(() => null)]);   // дата до первой версии фонда — 404
  const rerender = () => { host.dataset.escortDate = $('#se-date', host)?.value || date; renderStaysEscort(host); };
  const on = Object.fromEntries(fund.escorts.map(e => [e.employee_id, e.active]));
  const s = fund.settings;
  const codes = fund.vip_codes || [];
  const escCats = snap ? snap.categories.filter(c => c.escorted) : [];
  const escGroups = snap ? snap.groups.filter(g => g.escorted) : [];
  const refresh = () => { staysState.fund = null; rerender(); };

  const toggleEscort = async (e, id) => {
    const cb = e.target;
    try { await api(`/api/stays/escorts/${id}`, { method: 'PUT', body: { active: cb.checked } }); }
    catch (err) { cb.checked = !cb.checked; toast(err.message, 'err'); }
  };
  const seed = async () => {
    try {
      const r = await api('/api/stays/escorts/seed', { method: 'POST', body: {} });
      toast(r.added ? `Добавлено: ${r.added}` : 'Новых батлеров не найдено');
      renderStaysEscort(host);
    } catch (e) { toast(e.message, 'err'); }
  };
  const saveSettings = async () => {
    try {
      await api('/api/stays/settings', { method: 'PUT', body: {
        special_factor: Number($('#se-special', host).value),
        daily_limit: Number($('#se-limit', host).value), replacement_codes: $('#se-codes', host).value } });
      toast('Настройки сохранены');
    } catch (e) { toast(e.message, 'err'); }
  };
  const archive = async c => {
    try { await api(`/api/stays/vip-codes/${c.id}/archive`, { method: 'PUT', body: { archived: !c.archived } }); refresh(); }
    catch (e) { toast(e.message, 'err'); }
  };
  const form = c => staysForm(c ? `Код «${c.code}»` : 'Новый код', html`
    ${fieldRow('Код (цифры, ведущий ноль значим)', textInput('vc-code', c?.code))}${fieldRow('Что значит', textInput('vc-title', c?.title))}
    ${checkField('vc-escorted', 'С сопровождением', c?.escorted)}
    ${fieldRow('Коэффициент нагрузки', textInput('vc-factor', c?.factor ?? 1, 'number'))}
    ${fieldRow('Порядок', textInput('vc-sort', c?.sort_order ?? 100, 'number'))}`,
  async m => {
    const body = { code: $('#vc-code', m).value, title: $('#vc-title', m).value, escorted: $('#vc-escorted', m).checked,
      factor: Number($('#vc-factor', m).value), sort_order: Number($('#vc-sort', m).value) };   // PUT — объект целиком
    await api(c ? `/api/stays/vip-codes/${c.id}` : '/api/stays/vip-codes', { method: c ? 'PUT' : 'POST', body });
    staysState.fund = null; toast('Код сохранён'); rerender();
  });

  render(html`
    ${settingsHeadView('Сопровождение', 'Кто ведёт гостей, VIP-коды, коэффициент «Особого гостя» и дневной лимит нагрузки батлера.')}
    ${settingsPanelView('Сопровождают гостей', html`
      <div class="check-list" style="max-height:360px">${(fund.staff || []).length ? fund.staff.map(p => html`
        <label class="chk"><input type="checkbox" data-escort=${p.id} .checked=${!!on[p.id]} @change=${e => toggleEscort(e, p.id)}>
          ${p.name} <span class="muted">${p.position}</span></label>`) : html`<div class="empty">Нет сотрудников</div>`}</div>`,
      html`<button class="btn btn-sm" id="se-seed" style="float:right" @click=${seed}>Заполнить по должности «батлер»</button>`)}
    ${settingsPanelView('VIP-коды', html`
      <div class="table-wrap"><table class="data" id="se-codes-table">
        <thead><tr><th>Код</th><th>Что значит</th><th>Сопровождение</th><th>Коэффициент</th><th>Порядок</th><th></th></tr></thead>
        <tbody>${codes.length ? codes.map(c => html`<tr data-code-row=${c.id} class=${c.archived ? 'muted' : ''}>
          <td><b>${c.code}</b>${c.archived ? html` <span class="badge muted">в архиве</span>` : nothing}</td><td>${c.title}</td>
          <td>${c.escorted ? 'да' : '—'}</td><td>×${staysFactorText(c.factor)}</td><td>${String(c.sort_order)}</td>
          <td class="num"><button class="btn btn-sm btn-ghost" data-code-edit=${c.id} @click=${() => form(c)}>Изменить</button>
            <button class="btn btn-sm btn-ghost" data-code-arch=${c.id} @click=${() => archive(c)}>${c.archived ? 'Вернуть' : 'В архив'}</button>
            <button class="btn btn-sm btn-ghost" data-code-del=${c.id} @click=${() => staysConfirmDelete('/api/stays/vip-codes', c.id, 'код', refresh)}>Удалить</button></td></tr>`)
          : html`<tr><td colspan="6" class="empty">Кодов пока нет</td></tr>`}</tbody></table></div>`,
      html`<button class="btn btn-sm btn-primary" id="se-code-add" style="float:right" @click=${() => form(null)}>+ Код</button>`)}
    ${settingsPanelView('Нагрузка', html`
      <div class="grid-2">
        ${fieldRow('Коэффициент «Особого гостя»', textInput('se-special', s.special_factor, 'number'))}
        ${fieldRow('Дневной лимит', textInput('se-limit', s.daily_limit, 'number'))}
        ${fieldRow('Коды Табеля «нужна подмена»', textInput('se-codes', s.replacement_codes))}
      </div>
      <p class="hint">Вес места = категория × коэффициент кода × (Особый гость ? коэффициент : 1); делится поровну между батлерами места.
      После смены коэффициентов подберите лимит нагрузки заново. Перегруз — предупреждение, сохранять не мешает.</p>
      <button class="btn btn-primary" id="se-save" @click=${saveSettings}>Сохранить</button>`)}
    ${settingsPanelView('Правила на дату', html`
      <label class="field"><span>Дата</span><input type="date" id="se-date" .value=${date} @change=${rerender}></label>
      ${snap ? html`
      <div data-rules-cats><b>Категории с сопровождением:</b> ${escCats.length ? escCats.map(c => c.code).join(', ') : html`<span class="muted">нет</span>`}</div>
      <div data-rules-groups><b>Узлы с сопровождением:</b> ${escGroups.length ? escGroups.map(g => g.title).join(', ') : html`<span class="muted">нет</span>`}</div>`
      : html`<div data-rules-missing class="muted">правила на эту дату недоступны</div>`}
      <p class="hint">Правятся в «Фонде» (черновиком с даты). <a href="#" id="se-to-fund" @click=${e => { e.preventDefault(); settingsOpen('stays_fund'); }}>Открыть «Фонд»</a></p>`)}`,
  mount(host));
}

/* ─────────────── Настраиваемые поля ─────────────── */
export async function renderStaysFields(host) {
  const fund = await api('/api/stays/fund', { silent: true });
  const rerender = () => renderStaysFields(host);
  const target = { guest: 'гость', reservation: 'бронь' };
  const form = f => staysForm(f ? `Поле «${f.title}»` : 'Новое поле', html`
    ${fieldRow('К чему', selectField('sfl-target', Object.entries(target), f?.target || 'guest'))}
    ${fieldRow('Код (латиница)', textInput('sfl-code', f?.code))}${fieldRow('Название', textInput('sfl-title', f?.title))}
    ${fieldRow('Тип', selectField('sfl-kind', Object.entries(STAYS_FIELD_KINDS), f?.kind || 'text'))}
    ${fieldRow('Варианты списка — по одному в строке', html`<textarea id="sfl-choices" rows="4" .value=${(f?.choices || []).join('\n')}></textarea>`)}
    ${checkField('sfl-searchable', 'Искать по полю', f?.searchable)}`,
  async m => {
    const body = { target: $('#sfl-target', m).value, code: $('#sfl-code', m).value, title: $('#sfl-title', m).value,
      kind: $('#sfl-kind', m).value, choices: $('#sfl-choices', m).value.split('\n'),
      searchable: $('#sfl-searchable', m).checked, sort_order: f?.sort_order ?? 100 };
    await api(f ? `/api/stays/fields/${f.id}` : '/api/stays/fields', { method: f ? 'PUT' : 'POST', body });
    toast('Поле сохранено'); rerender();
  });
  render(html`
    ${settingsHeadView('Настраиваемые поля', 'Дополнительные сведения о гостях и бронях; по отмеченным полям работает поиск.')}
    ${settingsPanelView('Поля', html`
      <div class="table-wrap"><table class="data">
        <thead><tr><th>К чему</th><th>Название</th><th>Код</th><th>Тип</th><th>Поиск</th><th></th></tr></thead>
        <tbody>${fund.fields.length ? fund.fields.map(f => html`<tr>
          <td>${target[f.target]}</td><td><b>${f.title}</b></td><td>${f.code}</td>
          <td>${STAYS_FIELD_KINDS[f.kind]}${f.kind === 'choice' ? html` <span class="muted">${f.choices.join(', ')}</span>` : nothing}</td>
          <td>${f.searchable ? 'да' : '—'}</td>
          <td class="num"><button class="btn btn-sm btn-ghost" data-fl-edit=${f.id} @click=${() => form(f)}>Изменить</button>
            <button class="btn btn-sm btn-ghost" data-fl-del=${f.id} @click=${() => staysConfirmDelete('/api/stays/fields', f.id, 'поле', rerender)}>Удалить</button></td>
        </tr>`) : html`<tr><td colspan="6" class="empty">Полей пока нет</td></tr>`}</tbody></table></div>`,
      html`<button class="btn btn-sm btn-primary" id="sfl-add" style="float:right" @click=${() => form(null)}>+ Поле</button>`)}`,
  mount(host));
}

/* ─────────────── Метки броней ─────────────── */
export async function renderStaysLabels(host) {
  const fund = await api('/api/stays/fund', { silent: true });
  const rerender = () => renderStaysLabels(host);
  const form = l => staysForm(l ? `Метка «${l.title}»` : 'Новая метка', html`
    ${fieldRow('Название', textInput('slb-title', l?.title))}${fieldRow('Цвет', textInput('slb-color', l?.color || '#3b6fd8', 'color'))}`,
  async m => {
    const body = { title: $('#slb-title', m).value, color: $('#slb-color', m).value };
    await api(l ? `/api/stays/labels/${l.id}` : '/api/stays/labels', { method: l ? 'PUT' : 'POST', body });
    toast('Метка сохранена'); rerender();
  });
  render(html`
    ${settingsHeadView('Метки броней', 'Цвет полосы брони на шахматке: «От руководства», «Открытый рынок»…')}
    ${settingsPanelView('Метки', html`
      <div class="check-list">${fund.labels.length ? fund.labels.map(l => html`
        <div class="rule-row" style="grid-template-columns:1fr auto">
          <div class="lbl"><span class="stays-swatch" style=${`background:${l.color}`}></span> ${l.title}</div>
          <div style="display:flex;gap:6px"><button class="btn btn-sm btn-ghost" data-lb-edit=${l.id} @click=${() => form(l)}>Изменить</button>
            <button class="btn btn-sm btn-ghost" data-lb-del=${l.id} @click=${() => staysConfirmDelete('/api/stays/labels', l.id, 'метку', rerender)}>Удалить</button></div>
        </div>`) : html`<div class="empty">Меток пока нет</div>`}</div>`,
      html`<button class="btn btn-sm btn-primary" id="slb-add" style="float:right" @click=${() => form(null)}>+ Метка</button>`)}`,
  mount(host));
}

/* ── мост к общей области имён (генерируется tools/gen_js_globals.py; уйдёт вместе с переходом файла на import/export) ── */
Object.assign(globalThis, {
  STAYS_FIELD_KINDS,
  staysForm,
  staysConfirmDelete,
  renderStaysEscort,
  renderStaysFields,
  renderStaysLabels,
});
/* ── конец моста ── */
