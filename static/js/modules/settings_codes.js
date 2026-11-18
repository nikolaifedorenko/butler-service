/* Раздел «Настройки»: экран «Коды Табеля» (вынесено из settings.js, шаг 6.5 аудита).
   Оболочка, черновик версии справочников и общие помощники — в settings.js.
   Модуль на lit-html (ADR-0013, раздел 7). */
'use strict';

import { can, registerModule } from '../app.js';
import { api, closeModal, confirmDialog, openModal, state, toast } from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { settingsTimeline } from './settings_calc.js';
import {
  settingsCodeColor, settingsCodePillView, settingsDraft, settingsDraftBarView, settingsEngine, settingsGo,
  settingsHeadView, settingsHm, settingsHoursText, settingsMin, settingsPanelView, settingsPayload,
  settingsRenderScreen, settingsSnap, settingsUI, settingsUpdateDraftBars,
} from './settings.js';

registerModule({ screens: { codes: { render: settingsScreenCodes, icon: 'codes' } } });

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «КОДЫ ТАБЕЛЯ» — нормы расчёта (CFG-DAY-CODES, CFG-WINDOWS).
   Словаря смен здесь НЕТ: это другой экран («Смены и отсутствия»), другая
   сущность и другое право (план, ред. 3, §3.4/§3.4б).
   ══════════════════════════════════════════════════════════════════════ */
export const SETTINGS_CODE_FLAGS = [
  { key: 'carries_hours', title: 'Несёт часы', hint: 'Код задаёт план строки Табеля; план карточки = длина окна (R34)' },
  { key: 'accepts_ut', title: 'Принимает коды УТ', hint: 'В день с этим кодом можно разместить переработку/погашение' },
  { key: 'counts_in_ut', title: 'Учитывается в УТ', hint: 'Уровень 7 правила «Учитываются ли часы в УТ» (CHK-DEFAULTS)' },
  { key: 'plan_equals_fact_auto', title: '«План=Факт» = Авто', hint: 'Единственный источник, который разрешает «Авто» в «Да» (R19)' },
];

async function settingsScreenCodes(host) {
  await settingsEngine();
  if (!state.docKinds) {
    /* виды заявлений — для «Заявление по назначению кода» в карточке кода (16.10.2026) */
    try {
      const di = await api('/api/docs/kinds', { silent: true });
      state.docKinds = di.kinds || []; state.docPlaceholders = di.placeholders || {};
    } catch { state.docKinds = []; }
  }
  const p = settingsPayload();
  const d = settingsDraft();
  if (!p || !d) { render(html`<div class="empty">Справочники не загружены</div>`, mount(host)); return; }
  const edit = can('settings.edit');
  const tab = settingsUI.codesTab || (settingsUI.codesTab = 'codes');
  const codes = Object.entries(d.day_code_policy || {});
  const windows = Object.entries(d.windows || {});
  const step = Number(d.step_minutes) || 15;
  const setTab = t => () => { settingsUI.codesTab = t; settingsRenderScreen(); };

  render(html`
    ${settingsHeadView('Коды Табеля',
      'Нормы расчёта: какие коды бывают в Табеле, что они означают, какой у них режим отметок и заявление, и какие окна (значения) у них есть. Это не словарь смен — он на отдельном экране.',
      html`<button class="btn btn-sm btn-ghost" data-go="shifts" @click=${() => settingsGo('shifts')}>Смены и отсутствия ↗</button>
       ${edit ? html`<button class="btn btn-sm btn-primary" id="cd-add"
         @click=${() => (tab === 'codes' ? settingsCodeModal(null) : settingsWindowModal(null))}>${tab === 'codes' ? '+ Код Табеля' : '+ Значение и окно'}</button>` : nothing}`)}
    <div class="tabs">
      <button data-tab="codes" class=${tab === 'codes' ? 'active' : ''} @click=${setTab('codes')}>Коды Табеля · ${codes.length}</button>
      <button data-tab="windows" class=${tab === 'windows' ? 'active' : ''} @click=${setTab('windows')}>Окна и значения · ${windows.length}</button>
    </div>
    <div id="cd-body">${tab === 'codes' ? codesCards(codes, d, edit) : windowsTable(windows, codes, step, edit, d)}</div>
    ${settingsDraftBarView()}`, mount(host));
}

function codesCards(codes, d, edit) {
  /* Компактный список (решение владельца 18.10.2026): строка = пилюля + название +
     «Изменить» + «✕». Флаги расчёта, режим отметок и заявление настраиваются ТОЛЬКО
     в модалке «Изменить» — дублирование в списке убрано; окна и значения — на
     вкладке «Окна и значения». Логика и сервер не менялись. */
  const del = code => {
    const row = d.day_code_policy[code] || {};
    const winKeys = Object.keys(d.windows || {}).filter(k => k.split(' ')[0] === code);
    confirmDialog('Удалить код Табеля?',
      `«${code}»${row.title ? ' (' + row.title + ')' : ''} исчезнет из справочника вместе со значениями/окнами: `
      + (winKeys.length ? winKeys.map(k => `«${k}»`).join(', ') : 'окон у кода нет')
      + '. При публикации сервер проверит: код, который стоит в Табеле или на который ссылается живая смена словаря, удалить не получится.',
      () => {
        delete d.day_code_policy[code];
        winKeys.forEach(k => delete d.windows[k]);
        toast('Код удалён из черновика — опубликуйте версию', 'ok');
        settingsRenderScreen();
      }, 'Удалить из черновика');
  };
  return settingsPanelView('Коды Табеля · CFG-DAY-CODES', html`
    <div class="code-cards">${codes.map(([code, row]) => html`
      <div class="code-card" style="padding:10px 14px">
        <div class="cc-head">
          ${settingsCodePillView(code, d.day_code_policy)}
          <div class="cc-name"><b>${row.title || '—'}</b></div>
          <div style="flex:1"></div>
          ${edit ? html`<span class="cc-actions">
            <button class="btn btn-sm btn-ghost" data-cedit=${code} title="Изменить карточку кода" @click=${() => settingsCodeModal(code)}>Изменить</button>
            <button class="btn btn-sm btn-ghost" data-cdel=${code} title="Удалить код из справочника" @click=${() => del(code)}>✕</button></span>` : nothing}
        </div>
      </div>`)}</div>
    <p class="hint">Флаги расчёта, режим отметок «Пришёл/Ушёл» и шаблон заявления настраиваются
      в карточке кода («Изменить») и больше не дублируются в списке (18.10.2026).
      Значения и окна кода — на вкладке «Окна и значения».</p>`);
}

function windowsTable(windows, codes, step, edit, draft) {
  const rows = windows.map(([key, w]) => {
    const code = key.split(' ')[0];
    const len = Number(w.end_minute) - Number(w.start_minute);
    return { key, code, w, len };
  }).sort((a, b) => a.code.localeCompare(b.code, 'ru') || a.w.start_minute - b.w.start_minute);
  const policy = Object.fromEntries(codes);
  const del = key => confirmDialog('Удалить значение Табеля?',
    `«${key}» исчезнет из справочника вместе с окном. Строки Табеля с этим значением, которые уже сохранены, перестанут считаться (CHK-WINDOW-EXISTS) — сначала замените их в Табеле.`,
    () => {
      delete draft.windows[key];
      toast('Значение удалено из черновика — опубликуйте версию', 'ok');
      settingsRenderScreen();
    }, 'Удалить из черновика');
  return html`${settingsPanelView('Окна и значения · CFG-WINDOWS', html`
    <div class="table-wrap"><table class="data responsive"><thead><tr>
      <th>Значение Табеля</th><th>Код</th><th>Окно</th><th class="num">Длина окна</th>
      <th>Часов в значении</th><th></th></tr></thead>
    <tbody>${rows.length ? rows.map(r => html`<tr>
      <td data-label="Значение"><b>${r.key}</b></td>
      <td data-label="Код">${settingsCodePillView(r.code, policy)}</td>
      <td data-label="Окно" class="num">${settingsHm(r.w.start_minute)}–${settingsHm(r.w.end_minute)}</td>
      <td class="num" data-label="Длина">${settingsHoursText(r.len)}</td>
      <td data-label="Часов">${r.key.split(' ')[1] || '—'} <span class="hint" style="margin:0">зарплатный атрибут строки</span></td>
      <td class="num">${edit ? html`<button class="btn btn-sm btn-ghost" data-win=${r.key} @click=${() => settingsWindowModal(r.key)}>Изменить</button>
        <button class="btn btn-sm btn-ghost" data-windel=${r.key} title="Удалить значение" @click=${() => del(r.key)}>✕</button>` : nothing}</td>
    </tr>`) : html`<tr><td colspan="6" class="empty">Окон нет — добавьте значение</td></tr>`}</tbody></table></div>
    <p class="hint">План карточки и недостача считаются от <b>окна</b>, а не от числа часов в значении:
      «Я 10,75» при окне 08:00–20:00 даёт план 12 ч, а часы значения — зарплатная норма строки
      (RUL-PLAN-BELOW-WINDOW, EX-51). Окно не пересекает полночь: смена через полночь оформляется
      одним значением в дне начала (CHK-WINDOW-BOUNDS).</p>`)}
  ${settingsPanelView('Все окна на полосе суток · сетка = шаг ' + step + ' мин',
    settingsTimeline(rows.map(r => ({ label: r.key, start: r.w.start_minute, end: r.w.end_minute,
      color: settingsCodeColor(r.code, policy) }))))}`;
}

export function settingsCodeModal(code) {
  const draft = settingsDraft();
  if (!draft) return;
  const isNew = !code;
  const row = isNew ? null : draft.day_code_policy[code];
  const docKinds = state.docKinds || [];
  const flag = (id, label, on) => html`<label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted);margin-bottom:6px">
    <input type="checkbox" id=${id} .checked=${on} style="width:17px;height:17px;accent-color:var(--primary)"> ${label}</label>`;
  openModal({
    title: isNew ? 'Новый код Табеля' : `Код «${code}»`,
    subtitle: 'Строка CFG-DAY-CODES: как день считается. Публикуется версией справочников',
    body: html`
      <div class="grid-2">
        <label class="field"><span>Код (как в Т-13)</span>
          <input type="text" id="nc-code" .value=${code || ''} ?readonly=${!isNew} maxlength="4" placeholder="Я"></label>
        <label class="field"><span>Название</span>
          <input type="text" id="nc-title" .value=${row?.title || ''} placeholder="Явка (дневная работа)"></label>
        <label class="field"><span>Цвет</span><input type="color" id="nc-color" .value=${row?.color || '#34a862'} style="height:44px;padding:4px"></label>
      </div>
      ${SETTINGS_CODE_FLAGS.map(f => html`<label style="display:flex;gap:9px;align-items:flex-start;font-size:13.5px;color:var(--muted);margin-bottom:8px">
        <input type="checkbox" id=${`nc-${f.key}`} .checked=${!!row?.[f.key]} style="width:17px;height:17px;accent-color:var(--primary);margin-top:2px">
        <span><b style="color:var(--text)">${f.title}</b><br><span class="hint" style="margin:0">${f.hint}</span></span></label>`)}
      <div id="nc-punch-wrap" style="border-top:1px dashed var(--line);padding-top:10px;margin-bottom:10px">
        <div class="opt-group-title" style="margin:0 0 6px">Кнопки отметок в день с этим кодом</div>
        ${flag('nc-punch-in', 'Разрешить «Пришёл на работу»', row?.punch_in !== false)}
        ${flag('nc-punch-out', 'Разрешить «Ушёл с работы»', row?.punch_out !== false)}
        <div class="hint" style="margin-top:4px">Флаги соблюдает сервер: пока флаг снят, отметку принять нельзя
          (409 с текстом статуса), а кнопка в «Моих отметках» неактивна.</div>
      </div>
      <div id="nc-doc-wrap" style="border-top:1px dashed var(--line);padding-top:10px;margin-bottom:10px">
        <label class="field"><span>Заявление по назначению кода (шаблон)</span>
          <select id="nc-doc">
            <option value="">— не печатать —</option>
            ${docKinds.filter(k => k.active !== false).map(k => html`<option value=${k.code} ?selected=${row?.doc_type === k.code}>${k.name}</option>`)}
            ${row?.doc_type && !docKinds.some(k => k.code === row.doc_type)
              ? html`<option value=${row.doc_type} selected>${row.doc_type} (вид удалён — выберите другой)</option>` : nothing}
          </select>
          <div class="hint" style="margin-top:2px">По этому шаблону печатается заявление, когда код назначен
            на период («Печать заявления» в Табеле и Графике). Виды и бланки — экран «Документы и справочники».</div></label>
      </div>
      <p class="hint">Код появится в Табеле после публикации версии. Окна (значения) кода настраиваются
        на вкладке «Окна и значения» — там же видно, что окно положено только коду, несущему часы.
        Чтобы код можно было поставить из Графика, нужен вид смены с этим кодом Табеля —
        экран «Смены и отсутствия».</p>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-save>${isNew ? 'Добавить в черновик' : 'Сохранить'}</button>`,
    onMount(m) {
      /* «Пришёл/Ушёл» — у кода, несущего часы; заявление — у кода без часов
         (решение владельца 16.10.2026): блоки переключаются чекбоксом «Несёт часы» */
      const carriesBox = m.querySelector('#nc-carries_hours');
      const syncWraps = () => {
        const carries = carriesBox.checked;
        m.querySelector('#nc-punch-wrap').style.display = carries ? '' : 'none';
        m.querySelector('#nc-doc-wrap').style.display = carries ? 'none' : '';
      };
      carriesBox.onchange = syncWraps; syncWraps();
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = () => {
        const c = m.querySelector('#nc-code').value.trim().toUpperCase();
        if (!c) return toast('Введите код', 'warn');
        if (isNew && draft.day_code_policy[c]) return toast(`Код «${c}» уже есть в справочнике`, 'warn');
        const entry = { ...(draft.day_code_policy[c] || {}) };
        entry.title = m.querySelector('#nc-title').value.trim();
        entry.color = m.querySelector('#nc-color').value;
        SETTINGS_CODE_FLAGS.forEach(f => { entry[f.key] = m.querySelector(`#nc-${f.key}`).checked; });
        entry.punch_in = m.querySelector('#nc-punch-in').checked;
        entry.punch_out = m.querySelector('#nc-punch-out').checked;
        entry.doc_type = entry.carries_hours ? (entry.doc_type || '') : m.querySelector('#nc-doc').value;
        draft.day_code_policy = { ...draft.day_code_policy, [c]: entry };
        closeModal();
        toast(isNew ? `Код «${c}» добавлен в черновик` : `Код «${c}» обновлён в черновике`, 'ok');
        settingsUI.codesTab = 'codes';
        settingsRenderScreen();
        settingsUpdateDraftBars();
      };
    },
  });
}

export function settingsWindowModal(key) {
  const draft = settingsDraft();
  if (!draft) return;
  const isNew = !key;
  const w = isNew ? { start_minute: 480, end_minute: 1200 } : draft.windows[key];
  /* Стандартное окно и часы — только у кода, несущего часы (решение владельца
     16.10.2026): у кодов-отсутствий окна нет, день без часов не считается от окна.
     Прежнее значение можно открыть, даже если флаг у кода сняли (история). */
  const policy = draft.day_code_policy || {};
  const [curCode, curHours] = String(key || '').split(' ');
  const codes = Object.keys(policy).filter(c => policy[c].carries_hours || c === curCode);
  const step = Number(draft.step_minutes) || 15;
  openModal({
    title: isNew ? 'Новое значение и окно' : `Значение «${key}»`,
    subtitle: 'Строка CFG-WINDOWS: ключ «КОД ЧАСЫ» + окно в сутках. План карточки = длина окна',
    body: html`
      <div class="grid-2">
        <label class="field"><span>Код Табеля</span><select id="nw-code" ?disabled=${!isNew}>
          ${codes.map(c => html`<option value=${c} ?selected=${c === curCode}>${c}</option>`)}
        </select></label>
        <label class="field"><span>Часов в значении (зарплатная норма)</span>
          <input type="text" id="nw-hours" .value=${curHours || '12'} placeholder="12 / 10,75"
            list="nw-hours-list">
          <datalist id="nw-hours-list">${['12', '11', '10,75', '10', '9', '8'].map(h =>
            html`<option value=${h}></option>`)}</datalist></label>
        <label class="field"><span>Начало окна</span>
          <input type="time" id="nw-start" .value=${settingsHm(w.start_minute)} step=${step * 60}></label>
        <label class="field"><span>Конец окна</span>
          <input type="time" id="nw-end" .value=${settingsHm(w.end_minute)} step=${step * 60}></label>
      </div>
      <div class="preview" id="nw-preview"></div>
      <p class="hint">В списке — только коды, несущие часы: стандартное окно и часы бывают лишь
        у рабочего дня (16.10.2026). Ключ значения канонический: <code>КОД ПРОБЕЛ ЧАСЫ</code>, часы — десятичной дробью
        через запятую (CHK-WINDOW-KEY). Окно не пересекает полночь (CHK-WINDOW-BOUNDS), границы лежат
        на сетке шага ${step} мин (CHK-GRID). Часов в значении может быть меньше длины окна —
        это зарплатная норма (RUL-PLAN-BELOW-WINDOW).</p>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-save>${isNew ? 'Добавить в черновик' : 'Сохранить'}</button>`,
    onMount(m) {
      const codeSel = m.querySelector('#nw-code'), hoursInp = m.querySelector('#nw-hours');
      const startInp = m.querySelector('#nw-start'), endInp = m.querySelector('#nw-end');
      const preview = m.querySelector('#nw-preview');
      const newKey = () => `${codeSel.value} ${hoursInp.value.trim().replace('.', ',')}`;
      const draw = () => {
        const s = settingsSnap(settingsMin(startInp.value) ?? 0, step);
        const e = settingsSnap(settingsMin(endInp.value) ?? 0, step);
        const len = e - s;
        render(html`
          <div class="row"><span class="k">Значение Табеля</span><b>${newKey()}</b></div>
          <div class="row"><span class="k">Окно</span><b>${settingsHm(s)}–${settingsHm(e)}</b></div>
          <div class="row"><span class="k">Длина окна = план карточки</span><b>${len > 0
            ? settingsHoursText(len) : html`<span style="color:var(--danger)">конец должен быть позже начала</span>`}</b></div>`, preview);
      };
      [codeSel, hoursInp, startInp, endInp].forEach(el => { el.oninput = draw; });
      draw();
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = () => {
        const k = newKey();
        const s = settingsSnap(settingsMin(startInp.value) ?? 0, step);
        const e = settingsSnap(settingsMin(endInp.value) ?? 0, step);
        if (!k.trim() || k.split(' ').length !== 2) return toast('Заполните код и часы значения', 'warn');
        if (!(e > s)) return toast('Конец окна должен быть позже начала: окно не пересекает полночь', 'warn');
        if (!draft.day_code_policy[k.split(' ')[0]]) return toast('Такого кода нет в справочнике — сначала добавьте код', 'warn');
        if (!draft.day_code_policy[k.split(' ')[0]].carries_hours) return toast('Окно положено только коду, который несёт часы', 'warn');
        if (isNew && draft.windows[k]) return toast(`Значение «${k}» уже есть`, 'warn');
        if (!isNew && k !== key) delete draft.windows[key];
        draft.windows = { ...draft.windows, [k]: { start_minute: s, end_minute: e } };
        closeModal();
        toast(`Значение «${k}» ${isNew ? 'добавлено' : 'обновлено'} в черновике`, 'ok');
        settingsUI.codesTab = 'windows';
        settingsRenderScreen();
      };
    },
  });
}
