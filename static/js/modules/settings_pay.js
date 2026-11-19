/* Раздел «Настройки»: экран «Правила оплаты», мастер и «Проверитель».
   Оболочка, черновик версии справочников и общие помощники — в settings.js.
   Модуль на lit-html (ADR-0013, раздел 7). */
'use strict';

import { can, registerModule } from '../app.js';
import { api, closeModal, confirmDialog, dateRu, MONTHS, openModal, state, todayISO, toast } from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import {
  SETTINGS_LEVEL_FORMS, SETTINGS_MODS, settingsChainView, settingsDraft, settingsDraftBarView, settingsEngine,
  settingsGo, settingsHeadView, settingsHoursText, settingsLevelBadgeView, settingsPanelView, settingsPayload,
  settingsRefresh, settingsRenderScreen, settingsUpdateDraftBars,
} from './settings.js';

registerModule({ screens: { pay: { render: settingsScreenPay, icon: 'money' } } });

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «ПРАВИЛА ОПЛАТЫ» — четыре модификатора CFG-MODIFIERS как первый класс:
   глобальный дефолт, переопределения, мастер и «Проверитель»
   ══════════════════════════════════════════════════════════════════════ */
export function settingsModValue(name, raw) {
  if (raw === null || raw === undefined || raw === '') return '—';
  if (name === 'plan_equals_fact') return { yes: 'Да', no: 'Нет', auto: 'Авто', 1: 'Да', 0: 'Нет' }[raw] || String(raw);
  return (raw === true || raw === 'true' || raw === '1' || raw === 1) ? 'Да' : 'Нет';
}
export function settingsWhoText(m) {
  if (m.employee_id) {
    const e = (state.employees || []).find(x => x.id === m.employee_id);
    return e ? (e.short_name || e.full_name) : `сотрудник #${m.employee_id}`;
  }
  return m.group ? `группа «${m.group}»` : 'все сотрудники';
}
function settingsWhenText(m) {
  if (m.date) return dateRu(m.date);
  if (m.period_start) return `весь период с ${dateRu(m.period_start)}`;
  return '—';
}
function settingsLevelOf(f) {
  if (f.emp && !f.group && f.day) return 1;
  if (f.emp && !f.group && !f.day) return 2;
  if (!f.emp && f.group && f.day) return 3;
  if (!f.emp && f.group && !f.day) return 4;
  if (!f.emp && !f.group && f.day) return 5;
  return 6;
}

async function settingsScreenPay(host) {
  await settingsEngine();
  const p = settingsPayload();
  const gd = p?.global_defaults || {};
  const edit = can('settings.edit');
  let mods = [];
  try {
    mods = await api(`/api/engine-settings/modifiers?year=${state.year}&month=${state.month}`, { silent: true });
  } catch { mods = []; }
  const byMod = name => mods.filter(m => m.name === name);

  const shiftMonth = delta => {
    let m = state.month + delta, y = state.year;
    if (m < 1) { m = 12; y--; } if (m > 12) { m = 1; y++; }
    state.month = m; state.year = y; settingsRenderScreen();
  };
  /* глобальный дефолт правится в черновике; экран рисуется заново из того же черновика */
  const setDefault = (name, val) => {
    const draft = settingsDraft();
    draft.global_defaults = { ...(draft.global_defaults || {}), [name]: val };
    settingsUpdateDraftBars();
    draw();
  };
  const del = x => confirmDialog('Удалить переопределение?',
    'Значение дня вернётся к более слабому уровню приоритета (вплоть до глобального). Затронутые дни табеля пересчитаются.',
    async () => {
      try {
        await api(`/api/engine-settings/modifiers/${x.id}`, { method: 'DELETE' });
        toast('Переопределение удалено', 'ok');
        await settingsRefresh();
      } catch (e) { toast(e.message, 'err'); }
    }, 'Удалить');

  const card = m => {
    const list = byMod(m.name);
    const draftVal = (settingsDraft()?.global_defaults || {})[m.name];
    const changed = m.name !== 'counts_in_ut' && String(gd[m.name]) !== String(draftVal);
    return html`<div class="rule-card">
        <div class="rc-head">
          <h4>${m.title}</h4>
          ${settingsLevelBadgeView(7)}
          <span class="spacer"></span>
          ${m.name === 'counts_in_ut'
            ? html`<span class="val-picker">по коду дня <button class="btn btn-sm btn-ghost" data-go="codes" @click=${() => settingsGo('codes')}>коды Табеля →</button></span>`
            : m.type === 'tri'
              ? html`<span class="val-picker">глобально
                  <select data-gd=${m.name} ?disabled=${!edit} @change=${e => setDefault(m.name, e.target.value)}>
                    ${[['no', 'Нет'], ['yes', 'Да'], ['auto', 'Авто (по коду Табеля)']].map(([v, t]) =>
                      html`<option value=${v} ?selected=${String(draftVal) === v}>${t}</option>`)}
                  </select></span>`
              : html`<span class="val-picker">глобально
                  <label class="switch"><input type="checkbox" data-gd=${m.name}
                    .checked=${!!draftVal} ?disabled=${!edit} @change=${e => setDefault(m.name, e.target.checked)}><span class="sl"></span></label>
                  <b>${settingsModValue(m.name, draftVal)}</b></span>`}
          ${changed ? html`<span class="badge warn">в черновике — не опубликовано</span>` : nothing}
          <span class=${`badge ${list.length ? 'info' : 'muted'}`}>переопределений в месяце: ${list.length}</span>
        </div>
        <div class="rc-body">${m.what}<br><span class="spec-ref">Пример: ${m.ex}</span></div>
        <div class="rc-meta">
          <span>Норма: <b>${m.spec}</b></span>
          <span class="spacer"></span>
          ${edit ? html`<button class="btn btn-sm" data-add=${m.name} @click=${() => settingsWizard(m.name)}>+ Переопределение</button>` : nothing}
          <button class="btn btn-sm btn-ghost" data-check=${m.name} @click=${() => settingsResolverModal(m.name)}>Проверить для дня</button>
        </div>
        ${list.length ? html`<div class="table-wrap" style="margin-top:10px"><table class="data"><thead><tr>
            <th>Значение</th><th>Кому</th><th>Когда</th><th>Уровень</th><th>Комментарий</th><th>Кто задал</th><th></th>
          </tr></thead><tbody>${list.map(x => html`<tr>
            <td><b>${settingsModValue(x.name, x.value)}</b></td>
            <td>${settingsWhoText(x)}</td><td>${settingsWhenText(x)}</td>
            <td>${settingsLevelBadgeView(settingsLevelOf({ emp: !!x.employee_id, group: !!x.group,
              day: !!x.date, period: !!x.period_start }))}</td>
            <td>${x.note || '—'}</td><td>${x.created_by || '—'}</td>
            <td class="num">${edit ? html`<button class="btn btn-sm btn-ghost" data-del=${x.id} title="Удалить переопределение" @click=${() => del(x)}>✕</button>` : nothing}</td>
          </tr>`)}</tbody></table></div>` : nothing}
      </div>`;
  };

  const draw = () => render(html`
    ${settingsHeadView('Правила оплаты',
      'Четыре правила, которые определяют, попадут ли часы в УТ и по какому тарифу. Глобальное значение — уровень 7; переопределения на группу, сотрудника или день сильнее.',
      html`<div class="month-nav"><button id="py-prev" aria-label="Предыдущий месяц" @click=${() => shiftMonth(-1)}>‹</button>
         <div class="label">${MONTHS[state.month - 1]} ${state.year}</div>
         <button id="py-next" aria-label="Следующий месяц" @click=${() => shiftMonth(1)}>›</button></div>
       ${edit ? html`<button class="btn btn-sm btn-primary" id="py-add" @click=${() => settingsWizard()}>+ Переопределение</button>` : nothing}
       <button class="btn btn-sm" id="py-resolve" @click=${() => settingsResolverModal()}>Проверитель</button>`)}

    <div class="settings-list">${SETTINGS_MODS.map(card)}</div>

    ${settingsPanelView('Как выбирается значение', html`
      <p class="hint" style="margin:0 0 10px">Приоритет 1–7 (CFG-MODIFIERS, 3.5): первое совпадение
        сверху вниз и есть значение дня. Две записи одного уровня на один день — конфликт
        конфигурации (CHK-MODIFIER-CONFLICT): такое правило не сохраняется.</p>
      <div class="chain">${[1, 2, 3, 4, 5, 6, 7].map(lv => html`${lv > 1 ? html`<span class="arrow">→</span>` : nothing}
        <span class="step">${settingsLevelBadgeView(lv)} ${SETTINGS_LEVEL_FORMS[lv]}</span>`)}</div>
      <p class="hint">Дни производственного календаря и ВИП-периоды подмешиваются как
        «Двойные переработки» автоматически — это уровни 5/6 и 1/2, а не отдельные сущности.
        «План=Факт = Авто» разрешается в «Да» только колонкой кода Табеля (R19, стартово у «К»).</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn btn-sm" data-go="calendar" @click=${() => settingsGo('calendar')}>Календарь правил</button>
        <button class="btn btn-sm btn-ghost" id="py-resolve2" @click=${() => settingsResolverModal()}>Проверитель: какое значение подействовало</button>
      </div>`)}
    ${settingsDraftBarView()}`, mount(host));
  draw();
}

/* ── мастер «что → кому → когда» ── */
export function settingsWizard(modName) {
  const p = settingsPayload();
  const groups = p?.groups || [];
  const emps = (state.employees || []).slice().sort((a, b) =>
    (a.full_name || '').localeCompare(b.full_name || '', 'ru'));
  openModal({
    title: 'Переопределение правила', wide: true,
    subtitle: 'Что меняем → кому → когда. Уровень приоритета считается по форме области',
    body: html`
      <div class="wizard-steps">
        <div class="ws on"><b>1 · Что</b>правило и значение</div>
        <div class="ws on"><b>2 · Кому</b>все, группа или сотрудник</div>
        <div class="ws on"><b>3 · Когда</b>день или период</div>
      </div>
      <div class="grid-2">
        <label class="field"><span>Правило</span><select id="wz-name">
          ${SETTINGS_MODS.map(m => html`<option value=${m.name} ?selected=${m.name === modName}>${m.title}</option>`)}
        </select></label>
        <label class="field"><span>Значение</span><select id="wz-value"></select></label>
        <label class="field"><span>Кому</span><select id="wz-scope">
          <option value="all">все сотрудники</option>
          ${groups.map(g => html`<option value=${`g:${g}`}>группа «${g}»</option>`)}
          ${emps.map(e => html`<option value=${`e:${e.id}`}>${e.short_name || e.full_name}${e.group ? ` · ${e.group}` : ''}</option>`)}
        </select></label>
        <label class="field"><span>Когда</span><select id="wz-when">
          <option value="day">один день</option>
          <option value="period" selected>весь период (месяц)</option>
        </select></label>
        <label class="field"><span>Дата / начало периода</span>
          <input type="date" id="wz-date" .value=${todayISO()}></label>
        <label class="field"><span>Комментарий</span><input type="text" id="wz-note"
          placeholder="например: по письму C&B от 12.10"></label>
      </div>
      <div class="preview" id="wz-preview"></div>
      <p class="hint">Диапазон «с 10.10 по 20.10» и правило «с даты и далее» появятся, когда у записей
        CFG-MODIFIERS будет конец периода (этап 4 плана): сейчас запись действует либо один день,
        либо весь период. Конфликт с существующим правилом того же уровня сервер не сохранит (409).</p>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-save>Сохранить правило</button>`,
    onMount(m) {
      const nameSel = m.querySelector('#wz-name'), valSel = m.querySelector('#wz-value');
      const scopeSel = m.querySelector('#wz-scope'), whenSel = m.querySelector('#wz-when');
      const dateInp = m.querySelector('#wz-date'), noteInp = m.querySelector('#wz-note');
      const preview = m.querySelector('#wz-preview');
      const fillValues = () => {
        render(nameSel.value === 'plan_equals_fact'
          ? html`<option value="0">Нет</option><option value="1">Да</option><option value="auto">Авто (по коду Табеля)</option>`
          : html`<option value="1">Да</option><option value="0">Нет</option>`, valSel);
      };
      const draw = () => {
        const n = nameSel.value;
        const title = (SETTINGS_MODS.find(x => x.name === n) || {}).title || n;
        const scope = scopeSel.value;
        const who = scope === 'all' ? 'все сотрудники'
          : scope.startsWith('g:') ? `группа «${scope.slice(2)}»`
            : ((emps.find(e => e.id === +scope.slice(2)) || {}).full_name || scope);
        const when = whenSel.value === 'day' ? dateInp.value
          : `${dateInp.value.slice(0, 7)}-01`;
        const level = settingsLevelOf({ emp: scope.startsWith('e:'), group: scope.startsWith('g:'),
          day: whenSel.value === 'day', period: whenSel.value !== 'day' });
        render(html`
          <div class="row"><span class="k">Правило</span><b>${title}</b></div>
          <div class="row"><span class="k">Значение</span><b>${settingsModValue(n, valSel.value)}</b></div>
          <div class="row"><span class="k">Область</span><b>${who}</b></div>
          <div class="row"><span class="k">Действует</span><b>${whenSel.value === 'day'
            ? dateRu(when) : `весь период с ${dateRu(when)}`}</b></div>
          <div class="row"><span class="k">Уровень приоритета</span>
            <b>${settingsLevelBadgeView(level)} ${SETTINGS_LEVEL_FORMS[level]}</b></div>`, preview);
      };
      fillValues();
      [nameSel, scopeSel, whenSel, dateInp].forEach(el => { el.onchange = () => { if (el === nameSel) fillValues(); draw(); }; });
      valSel.onchange = draw;
      draw();
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        const scope = scopeSel.value;
        const day = whenSel.value === 'day' ? dateInp.value : null;
        const periodStart = day ? null : `${dateInp.value.slice(0, 7)}-01`;
        if (!day && !periodStart) return toast('Укажите дату', 'warn');
        const body = { name: nameSel.value, value: valSel.value, note: noteInp.value.trim(),
          date: day, period_start: periodStart,
          employee_id: scope.startsWith('e:') ? +scope.slice(2) : null,
          group: scope.startsWith('g:') ? scope.slice(2) : '' };
        try {
          await api('/api/engine-settings/modifiers', { method: 'POST', body });
          closeModal(); toast('Правило сохранено — затронутые дни пересчитаны', 'ok');
          await settingsRefresh();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ── «Проверитель»: какое значение подействовало для (сотрудник, день) и почему ── */
export function settingsResolverModal(modName) {
  const emps = (state.employees || []).slice().sort((a, b) =>
    (a.full_name || '').localeCompare(b.full_name || '', 'ru'));
  openModal({
    title: 'Проверитель правил', wide: true,
    subtitle: 'Какое значение подействовало для сотрудника в конкретный день и на каком уровне приоритета',
    body: html`
      <div class="grid-2">
        <label class="field" style="margin:0"><span>Сотрудник</span><select id="rs-emp">
          ${emps.map(e => html`<option value=${e.id}>${e.full_name}${e.group ? ` · ${e.group}` : ''}</option>`)}
        </select></label>
        <label class="field" style="margin:0"><span>День</span>
          <input type="date" id="rs-date" .value=${todayISO()}></label>
      </div>
      <div style="margin:12px 0"><button class="btn btn-primary btn-sm" id="rs-go">Проверить</button></div>
      <div id="rs-out"><p class="hint">Ответ приходит с сервера: приоритет 1–7 считает домен —
        тот же код, что и расчёт (<code>resolve_modifier_trace</code>), поэтому «Проверитель» не может
        разойтись с табелем.</p></div>`,
    footer: html`<button class="btn btn-ghost" data-close>Закрыть</button>`,
    onMount(m) {
      m.querySelector('[data-close]').onclick = closeModal;
      const out = m.querySelector('#rs-out');
      let only = modName;
      const run = async () => {
        const emp = m.querySelector('#rs-emp').value, date = m.querySelector('#rs-date').value;
        if (!emp || !date) return;
        render(html`<div class="empty">Проверяем…</div>`, out);
        try {
          const r = await api(`/api/engine-settings/rules/resolve?employee_id=${encodeURIComponent(emp)}&date=${date}`,
            { silent: true });
          render(html`
            <div class="preview" style="margin-bottom:12px">
              <div class="row"><span class="k">Сотрудник</span><b>${r.employee.full_name} · группа «${r.employee.group}»</b></div>
              <div class="row"><span class="k">День</span><b>${dateRu(r.date)}${r.code
                ? ` · код Табеля ${r.code}${r.plan_minutes ? ` · план строки ${settingsHoursText(r.plan_minutes)}` : ''}`
                : ' · строки в Табеле нет'}</b></div>
              <div class="row"><span class="k">Период</span><b>${dateRu(r.period.start)}–${dateRu(r.period.end)}
                (${r.period.granularity === 'half_month' ? 'полмесяца' : 'месяц'})</b></div>
              <div class="row"><span class="k">Версия справочников</span><b>${r.version?.id ? '#' + r.version.id : 'по умолчанию'}</b></div>
            </div>
            ${r.modifiers.filter(x => !only || x.name === only).map(x => html`
              <div class="rule-card">
                <div class="rc-head"><h4>${x.title}</h4>
                  <span class=${`badge ${x.value === '1' ? 'ok' : x.value === '0' ? 'muted' : 'info'}`}>${x.text}</span>
                  ${x.level ? settingsLevelBadgeView(x.level) : nothing}
                  <span class="spacer"></span>
                  ${only ? html`<button class="btn btn-sm btn-ghost" data-all @click=${() => { only = null; run(); }}>показать все правила</button>` : nothing}</div>
                <div class="rc-body">${x.source.text}${x.scope ? ` · область: ${x.scope}` : ''}</div>
                ${x.chain.length ? html`<div style="margin-top:10px">${settingsChainView(x.chain)}</div>` : nothing}
              </div>`)}`, out);
        } catch (e) {
          render(html`<div class="panel"><div class="empty">${e.message || e}</div></div>`, out);
        }
      };
      m.querySelector('#rs-go').onclick = run;
      if (emps.length) run();
    },
  });
}
