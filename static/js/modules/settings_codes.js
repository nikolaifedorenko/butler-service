/* Раздел «Настройки»: экран «Коды Табеля» (вынесено из settings.js, шаг 6.5 аудита).
   Оболочка, черновик версии справочников и общие помощники — в settings.js. */
'use strict';

registerModule({ screens: { codes: { render: settingsScreenCodes, icon: 'codes' } } });

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «КОДЫ ТАБЕЛЯ» — нормы расчёта (CFG-DAY-CODES, CFG-WINDOWS).
   Словаря смен здесь НЕТ: это другой экран («Смены и отсутствия»), другая
   сущность и другое право (план, ред. 3, §3.4/§3.4б).
   ══════════════════════════════════════════════════════════════════════ */
const SETTINGS_CODE_FLAGS = [
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
  if (!p || !d) { host.innerHTML = '<div class="empty">Справочники не загружены</div>'; return; }
  const edit = can('settings.edit');
  const tab = settingsUI.codesTab || (settingsUI.codesTab = 'codes');
  const codes = Object.entries(d.day_code_policy || {});
  const windows = Object.entries(d.windows || {});
  const shifts = (state.shiftTypes || []);
  const step = Number(d.step_minutes) || 15;

  host.innerHTML = `
    ${settingsHead('Коды Табеля',
      'Нормы расчёта: какие коды бывают в Табеле, что они означают, какой у них режим отметок и заявление, и какие окна (значения) у них есть. Это не словарь смен — он на отдельном экране.',
      `<button class="btn btn-sm btn-ghost" data-go="shifts">Смены и отсутствия ↗</button>
       ${edit ? `<button class="btn btn-sm btn-primary" id="cd-add">${tab === 'codes' ? '+ Код Табеля' : '+ Значение и окно'}</button>` : ''}`)}
    <div class="tabs">
      <button data-tab="codes" class="${tab === 'codes' ? 'active' : ''}">Коды Табеля · ${codes.length}</button>
      <button data-tab="windows" class="${tab === 'windows' ? 'active' : ''}">Окна и значения · ${windows.length}</button>
    </div>
    <div id="cd-body">${tab === 'codes' ? settingsCodesCards(codes, windows, shifts, d, edit)
      : settingsWindowsTable(windows, codes, step, edit)}</div>
    ${settingsDraftBarHtml()}`;

  settingsBindHealth(host);
  settingsBindDraftBar(host);
  $$('[data-tab]', host).forEach(b => b.onclick = () => {
    settingsUI.codesTab = b.dataset.tab; settingsRenderScreen();
  });
  const add = $('#cd-add');
  if (add) add.onclick = () => (tab === 'codes' ? settingsCodeModal(null) : settingsWindowModal(null));
  settingsBindCodesBody(host, d, edit);
}

function settingsCodesCards(codes, windows, shifts, d, edit) {
  /* Компактный список (решение владельца 18.10.2026): строка = пилюля + название +
     «Изменить» + «✕». Флаги расчёта, режим отметок и заявление настраиваются ТОЛЬКО
     в модалке «Изменить» — дублирование в списке убрано; окна и значения — на
     вкладке «Окна и значения». Логика и сервер не менялись. */
  return `${settingsPanel('Коды Табеля · CFG-DAY-CODES', `
    <div class="code-cards">${codes.map(([code, row]) => `
      <div class="code-card" style="padding:10px 14px">
        <div class="cc-head">
          ${settingsCodePill(code, d.day_code_policy)}
          <div class="cc-name"><b>${esc(row.title || '—')}</b></div>
          <div style="flex:1"></div>
          ${edit ? `<span class="cc-actions">
            <button class="btn btn-sm btn-ghost" data-cedit="${esc(code)}" title="Изменить карточку кода">Изменить</button>
            <button class="btn btn-sm btn-ghost" data-cdel="${esc(code)}" title="Удалить код из справочника">✕</button></span>` : ''}
        </div>
      </div>`).join('')}</div>
    <p class="hint">Флаги расчёта, режим отметок «Пришёл/Ушёл» и шаблон заявления настраиваются
      в карточке кода («Изменить») и больше не дублируются в списке (18.10.2026).
      Значения и окна кода — на вкладке «Окна и значения».</p>`)}`;
}

function settingsWindowsTable(windows, codes, step, edit) {
  const rows = windows.map(([key, w]) => {
    const code = key.split(' ')[0];
    const len = Number(w.end_minute) - Number(w.start_minute);
    return { key, code, w, len };
  }).sort((a, b) => a.code.localeCompare(b.code, 'ru') || a.w.start_minute - b.w.start_minute);
  return `${settingsPanel('Окна и значения · CFG-WINDOWS', `
    <div class="table-wrap"><table class="data responsive"><thead><tr>
      <th>Значение Табеля</th><th>Код</th><th>Окно</th><th class="num">Длина окна</th>
      <th>Часов в значении</th><th></th></tr></thead>
    <tbody>${rows.map(r => `<tr>
      <td data-label="Значение"><b>${esc(r.key)}</b></td>
      <td data-label="Код">${settingsCodePill(r.code, Object.fromEntries(codes))}</td>
      <td data-label="Окно" class="num">${esc(settingsHm(r.w.start_minute))}–${esc(settingsHm(r.w.end_minute))}</td>
      <td class="num" data-label="Длина">${esc(settingsHoursText(r.len))}</td>
      <td data-label="Часов">${esc(r.key.split(' ')[1] || '—')} <span class="hint" style="margin:0">зарплатный атрибут строки</span></td>
      <td class="num">${edit ? `<button class="btn btn-sm btn-ghost" data-win="${esc(r.key)}">Изменить</button>
        <button class="btn btn-sm btn-ghost" data-windel="${esc(r.key)}" title="Удалить значение">✕</button>` : ''}</td>
    </tr>`).join('') || '<tr><td colspan="6" class="empty">Окон нет — добавьте значение</td></tr>'}</tbody></table></div>
    <p class="hint">План карточки и недостача считаются от <b>окна</b>, а не от числа часов в значении:
      «Я 10,75» при окне 08:00–20:00 даёт план 12 ч, а часы значения — зарплатная норма строки
      (RUL-PLAN-BELOW-WINDOW, EX-51). Окно не пересекает полночь: смена через полночь оформляется
      одним значением в дне начала (CHK-WINDOW-BOUNDS).</p>`) }
  ${settingsPanel('Все окна на полосе суток · сетка = шаг ' + step + ' мин',
    settingsTimeline(rows.map(r => ({ label: r.key, start: r.w.start_minute, end: r.w.end_minute,
      color: settingsCodeColor(r.code, Object.fromEntries(codes)) }))))}`;
}

function settingsBindCodesBody(host, draft, edit) {
  if (!edit) {
    $$('[data-winof]', host).forEach(b => b.onclick = () => { settingsUI.codesTab = 'windows'; settingsRenderScreen(); });
    return;
  }
  const touch = () => settingsUpdateDraftBars();
  $$('[data-flag]', host).forEach(cb => cb.onchange = () => {
    const [code, flag] = cb.dataset.flag.split(':');
    draft.day_code_policy[code][flag] = cb.checked;
    /* «Несёт часы» переключает состав карточки: отметки (с часами) либо заявление
       (без часов) — перерисовываем экран, остальные флаги копятся молча */
    if (flag === 'carries_hours') settingsRenderScreen(); else touch();
  });
  $$('[data-punch]', host).forEach(cb => cb.onchange = () => {
    const [code, key] = cb.dataset.punch.split(':');
    draft.day_code_policy[code][key] = cb.checked; touch();
  });
  $$('[data-doc]', host).forEach(sel => sel.onchange = () => {
    draft.day_code_policy[sel.dataset.doc].doc_type = sel.value; touch();
  });
  $$('[data-cedit]', host).forEach(b => b.onclick = () => settingsCodeModal(b.dataset.cedit));
  $$('[data-cdel]', host).forEach(b => b.onclick = () => {
    const code = b.dataset.cdel;
    const row = draft.day_code_policy[code] || {};
    const winKeys = Object.keys(draft.windows || {}).filter(k => k.split(' ')[0] === code);
    confirmDialog('Удалить код Табеля?',
      `«${code}»${row.title ? ' (' + row.title + ')' : ''} исчезнет из справочника вместе со значениями/окнами: `
      + (winKeys.length ? winKeys.map(k => `«${k}»`).join(', ') : 'окон у кода нет')
      + '. При публикации сервер проверит: код, который стоит в Табеле или на который ссылается живая смена словаря, удалить не получится.',
      () => {
        delete draft.day_code_policy[code];
        winKeys.forEach(k => delete draft.windows[k]);
        toast('Код удалён из черновика — опубликуйте версию', 'ok');
        settingsRenderScreen();
      }, 'Удалить из черновика');
  });
  $$('[data-winof]', host).forEach(b => b.onclick = () => { settingsUI.codesTab = 'windows'; settingsRenderScreen(); });
  $$('[data-win]', host).forEach(b => b.onclick = () => settingsWindowModal(b.dataset.win));
  $$('[data-windel]', host).forEach(b => b.onclick = () => confirmDialog('Удалить значение Табеля?',
    `«${b.dataset.windel}» исчезнет из справочника вместе с окном. Строки Табеля с этим значением, которые уже сохранены, перестанут считаться (CHK-WINDOW-EXISTS) — сначала замените их в Табеле.`,
    () => {
      delete draft.windows[b.dataset.windel];
      toast('Значение удалено из черновика — опубликуйте версию', 'ok');
      settingsRenderScreen();
    }, 'Удалить из черновика'));
}

function settingsCodeModal(code) {
  const draft = settingsDraft();
  if (!draft) return;
  const isNew = !code;
  const row = isNew ? null : draft.day_code_policy[code];
  const docKinds = state.docKinds || [];
  openModal({
    title: isNew ? 'Новый код Табеля' : `Код «${code}»`,
    subtitle: 'Строка CFG-DAY-CODES: как день считается. Публикуется версией справочников',
    body: `
      <div class="grid-2">
        <label class="field"><span>Код (как в Т-13)</span>
          <input type="text" id="nc-code" value="${esc(code || '')}" ${isNew ? '' : 'readonly'} maxlength="4" placeholder="Я"></label>
        <label class="field"><span>Название</span>
          <input type="text" id="nc-title" value="${esc(row?.title || '')}" placeholder="Явка (дневная работа)"></label>
        <label class="field"><span>Цвет</span><input type="color" id="nc-color" value="${esc(row?.color || '#34a862')}" style="height:44px;padding:4px"></label>
      </div>
      ${SETTINGS_CODE_FLAGS.map(f => `<label style="display:flex;gap:9px;align-items:flex-start;font-size:13.5px;color:var(--muted);margin-bottom:8px">
        <input type="checkbox" id="nc-${f.key}" ${row?.[f.key] ? 'checked' : ''} style="width:17px;height:17px;accent-color:var(--primary);margin-top:2px">
        <span><b style="color:var(--text)">${esc(f.title)}</b><br><span class="hint" style="margin:0">${esc(f.hint)}</span></span></label>`).join('')}
      <div id="nc-punch-wrap" style="border-top:1px dashed var(--line);padding-top:10px;margin-bottom:10px">
        <div class="opt-group-title" style="margin:0 0 6px">Кнопки отметок в день с этим кодом</div>
        <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted);margin-bottom:6px">
          <input type="checkbox" id="nc-punch-in" ${row?.punch_in !== false ? 'checked' : ''} style="width:17px;height:17px;accent-color:var(--primary)">
          Разрешить «Пришёл на работу»</label>
        <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
          <input type="checkbox" id="nc-punch-out" ${row?.punch_out !== false ? 'checked' : ''} style="width:17px;height:17px;accent-color:var(--primary)">
          Разрешить «Ушёл с работы»</label>
        <div class="hint" style="margin-top:4px">Флаги соблюдает сервер: пока флаг снят, отметку принять нельзя
          (409 с текстом статуса), а кнопка в «Моих отметках» неактивна.</div>
      </div>
      <div id="nc-doc-wrap" style="border-top:1px dashed var(--line);padding-top:10px;margin-bottom:10px">
        <label class="field"><span>Заявление по назначению кода (шаблон)</span>
          <select id="nc-doc">
            <option value="">— не печатать —</option>
            ${docKinds.filter(k => k.active !== false).map(k => `<option value="${esc(k.code)}">${esc(k.name)}</option>`).join('')}
            ${row?.doc_type && !docKinds.some(k => k.code === row.doc_type)
              ? `<option value="${esc(row.doc_type)}" selected>${esc(row.doc_type)} (вид удалён — выберите другой)</option>` : ''}
          </select>
          <div class="hint" style="margin-top:2px">По этому шаблону печатается заявление, когда код назначен
            на период («Печать заявления» в Табеле и Графике). Виды и бланки — экран «Документы и справочники».</div></label>
      </div>
      <p class="hint">Код появится в Табеле после публикации версии. Окна (значения) кода настраиваются
        на вкладке «Окна и значения» — там же видно, что окно положено только коду, несущему часы.
        Чтобы код можно было поставить из Графика, нужен вид смены с этим кодом Табеля —
        экран «Смены и отсутствия».</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-save>${isNew ? 'Добавить в черновик' : 'Сохранить'}</button>`,
    onMount(m) {
      if (!isNew) m.querySelector('#nc-doc').value = row?.doc_type || '';
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
      };
    },
  });
}

function settingsWindowModal(key) {
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
    body: `
      <div class="grid-2">
        <label class="field"><span>Код Табеля</span><select id="nw-code" ${isNew ? '' : 'disabled'}>
          ${codes.map(c => `<option value="${esc(c)}" ${c === curCode ? 'selected' : ''}>${esc(c)}</option>`).join('')}
        </select></label>
        <label class="field"><span>Часов в значении (зарплатная норма)</span>
          <input type="text" id="nw-hours" value="${esc(curHours || '12')}" placeholder="12 / 10,75"
            list="nw-hours-list">
          <datalist id="nw-hours-list">${['12', '11', '10,75', '10', '9', '8'].map(h =>
            `<option value="${h}"></option>`).join('')}</datalist></label>
        <label class="field"><span>Начало окна</span>
          <input type="time" id="nw-start" value="${settingsHm(w.start_minute)}" step="${step * 60}"></label>
        <label class="field"><span>Конец окна</span>
          <input type="time" id="nw-end" value="${settingsHm(w.end_minute)}" step="${step * 60}"></label>
      </div>
      <div class="preview" id="nw-preview"></div>
      <p class="hint">В списке — только коды, несущие часы: стандартное окно и часы бывают лишь
        у рабочего дня (16.10.2026). Ключ значения канонический: <code>КОД ПРОБЕЛ ЧАСЫ</code>, часы — десятичной дробью
        через запятую (CHK-WINDOW-KEY). Окно не пересекает полночь (CHK-WINDOW-BOUNDS), границы лежат
        на сетке шага ${step} мин (CHK-GRID). Часов в значении может быть меньше длины окна —
        это зарплатная норма (RUL-PLAN-BELOW-WINDOW).</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-save>${isNew ? 'Добавить в черновик' : 'Сохранить'}</button>`,
    onMount(m) {
      const codeSel = m.querySelector('#nw-code'), hoursInp = m.querySelector('#nw-hours');
      const startInp = m.querySelector('#nw-start'), endInp = m.querySelector('#nw-end');
      const preview = m.querySelector('#nw-preview');
      const newKey = () => `${codeSel.value} ${hoursInp.value.trim().replace('.', ',')}`;
      const render = () => {
        const s = settingsSnap(settingsMin(startInp.value) ?? 0, step);
        const e = settingsSnap(settingsMin(endInp.value) ?? 0, step);
        const len = e - s;
        preview.innerHTML = `
          <div class="row"><span class="k">Значение Табеля</span><b>${esc(newKey())}</b></div>
          <div class="row"><span class="k">Окно</span><b>${esc(settingsHm(s))}–${esc(settingsHm(e))}</b></div>
          <div class="row"><span class="k">Длина окна = план карточки</span><b>${len > 0
            ? esc(settingsHoursText(len)) : '<span style="color:var(--danger)">конец должен быть позже начала</span>'}</b></div>`;
      };
      [codeSel, hoursInp, startInp, endInp].forEach(el => el.oninput = render);
      render();
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
