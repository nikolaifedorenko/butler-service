'use strict';
/* ══ НАСТРОЙКИ (продолжение): справочники, виды заявлений, двойные оплаты, словарь смен ══
   Вынесено из app.js (15.10.2026) без изменения логики: границы разделов —
   файлами (сборки намеренно нет, ADR-0008), общие функции — через глобальную
   область (реестр tools/js_globals.json, ESLint no-undef ловит пропуски). */

/* ══════════════════════════════════════════════════════════════════
   НАСТРОЙКИ: правила + словарь смен (произвольные часы)
   ══════════════════════════════════════════════════════════════════ */
/* ── справочники «Департаменты и службы» (панель настроек) ── */
async function renderDicts() {
  const host = $('#dicts-body');
  if (!host) return;
  let deps = [], subs = [];
  try { deps = await api('/api/departments', { silent: true }); } catch {}
  try { subs = await api('/api/subdivisions', { silent: true }); } catch {}
  state.departments = deps; state.subdivisions = subs;
  const dictCol = (items, kind, title, ph) => `
    <div>
      <div class="opt-group-title">${title}</div>
      <table class="data"><tbody>
        ${items.length ? items.map(d => `<tr>
          <td>${esc(d.name)}</td>
          <td class="num" style="white-space:nowrap">
            <button class="btn btn-sm btn-ghost" data-${kind}-ren="${d.id}">Переименовать</button>
            <button class="btn btn-sm btn-ghost" data-${kind}-del="${d.id}">Удалить</button>
          </td></tr>`).join('') : '<tr><td class="empty">Пока не созданы</td></tr>'}
      </tbody></table>
      <div style="display:flex;gap:8px;margin-top:8px">
        <input type="text" id="${kind}-new" placeholder="${ph}" style="flex:1">
        <button class="btn btn-sm" id="${kind}-add">+ Добавить</button>
      </div>
    </div>`;
  host.innerHTML = dictCol(deps, 'dep', 'Департаменты', 'Новый департамент')
                 + dictCol(subs, 'sub', 'Службы / подразделения', 'Новая служба');

  const wire = (kind, url) => {
    const items = () => (kind === 'dep' ? state.departments : state.subdivisions);
    const add = async () => {
      const inp = $(`#${kind}-new`);
      const name = inp.value.trim();
      if (!name) return toast('Введите название', 'warn');
      try { await api(url, { method: 'POST', body: { name } }); toast('Добавлено', 'ok'); renderDicts(); }
      catch (e) { toast(e.message, 'err'); }
    };
    $(`#${kind}-add`).onclick = add;
    $(`#${kind}-new`).onkeydown = ev => { if (ev.key === 'Enter') add(); };
    $$(`[data-${kind}-ren]`, host).forEach(b => b.onclick = () =>
      renameDictModal(url, items().find(x => x.id === +b.dataset[`${kind}Ren`])));
    $$(`[data-${kind}-del]`, host).forEach(b => b.onclick = () => {
      const item = items().find(x => x.id === +b.dataset[`${kind}Del`]);
      if (!item) return;
      confirmDialog(`Удалить «${item.name}»?`,
        'У сотрудников, где это значение выбрано, поле будет очищено. История документов не меняется.',
        async () => {
          try { await api(`${url}/${item.id}`, { method: 'DELETE' }); toast('Удалено', 'ok'); renderDicts(); }
          catch (e) { toast(e.message, 'err'); }
        }, 'Удалить');
    });
  };
  wire('dep', '/api/departments');
  wire('sub', '/api/subdivisions');
}

function renameDictModal(url, item) {
  if (!item) return;
  openModal({
    title: 'Переименовать',
    body: `<label class="field"><span>Название</span><input type="text" id="dict-name" value="${esc(item.name)}"></label>
           <p class="hint">Новое название автоматически обновится в карточках сотрудников.</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Сохранить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        const name = $('#dict-name').value.trim();
        if (!name) return toast('Введите название', 'warn');
        try {
          await api(`${url}/${item.id}`, { method: 'PUT', body: { name } });
          closeModal(); toast('Переименовано', 'ok'); renderDicts();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ── вид заявления: название, текст с плейсхолдерами, фирменный бланк .docx ── */
function openKindModal(kind) {
  const isNew = !kind;
  openModal({
    title: isNew ? 'Новый вид заявления' : kind.name,
    subtitle: isNew ? 'Код — строчная латиница: по нему хранится фирменный бланк .docx'
                    : `Код: ${kind.code}${kind.builtin ? ' · встроенный вид' : ''}`,
    wide: true,
    body: `
      <div class="grid-2">
        <label class="field"><span>Код (латиницей${isNew ? '' : ', неизменяемый'})</span>
          <input type="text" id="k-code" value="${esc(kind?.code || '')}" placeholder="mat_aid" ${isNew ? '' : 'disabled'}></label>
        <label class="field"><span>Название (как в списках)</span>
          <input type="text" id="k-name" value="${esc(kind?.name || '')}" placeholder="Заявление на материальную помощь"></label>
      </div>
      <label class="field"><span>Текст заявления (плейсхолдеры в фигурных скобках)</span>
        <textarea id="k-text" rows="12" style="font-family:ui-monospace,monospace;font-size:12px"
          placeholder="{director} / {company} / от {full_name_genitive} … ЗАЯВЛЕНИЕ … Прошу … {today} / {short_name}">${esc(kind?.text || '')}</textarea></label>
      <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
        <input type="checkbox" id="k-active" ${kind?.active !== false ? 'checked' : ''} style="width:17px;height:17px;accent-color:var(--primary)">
        Показывать вид в списках выбора (снимите, чтобы скрыть устаревший, но оставить в истории)
      </label>
      ${kind ? `<div class="rule-row" style="margin-top:10px;align-items:flex-start">
        <div><div class="lbl">Фирменный бланк компании (.docx)</div>
          <div class="desc">${kind.template?.uploaded
            ? `загружен: ${esc(kind.template.filename || '')} · найдено плейсхолдеров: ${(kind.template?.placeholders || []).length}`
            : 'не загружен — документ печатается текстом выше; бланк перекрывает текст и сохраняет шрифты, логотип и колонтитулы Word'}</div></div>
        <div class="rule-input" style="gap:6px;display:flex">
          <button class="btn btn-sm" id="k-sample" type="button">Пример .docx</button>
          <label class="btn btn-sm" style="cursor:pointer">Загрузить .docx
            <input type="file" accept=".docx" id="k-file" style="display:none"></label>
          ${kind.template?.uploaded ? '<button class="btn btn-sm btn-danger" id="k-tpl-del" type="button">Удалить бланк</button>' : ''}
        </div></div>`
        : '<p class="hint">После создания вида можно загрузить фирменный бланк .docx — он перекроет текст, сохранив оформление Word.</p>'}
      <details style="margin-top:8px"><summary class="hint" style="cursor:pointer">Доступные плейсхолдеры</summary>
        <table class="data" style="margin-top:8px">${Object.entries(state.docPlaceholders || {}).map(([k, v]) =>
          `<tr><td><code>{${esc(k)}}</code></td><td>${esc(v)}</td></tr>`).join('')}</table></details>`,
    footer: `${isNew ? '' : '<button class="btn btn-danger" data-del>Удалить вид</button>'}
             <div style="flex:1"></div>
             <button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-save>${isNew ? 'Создать' : 'Сохранить'}</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      const sampleBtn = m.querySelector('#k-sample');
      if (sampleBtn) sampleBtn.onclick = () =>
        downloadBlob(`/api/docs/sample?type=${encodeURIComponent(kind.code)}`, `sample_${kind.code}.docx`);
      const fileInp = m.querySelector('#k-file');
      if (fileInp) fileInp.onchange = async () => {
        const f = fileInp.files[0];
        if (!f) return;
        const fd = new FormData();
        fd.append('file', f);
        loading(true);
        try {
          const res = await fetch(`/api/docs/templates?type=${encodeURIComponent(kind.code)}`,
            { method: 'POST', credentials: 'same-origin', body: fd,
              headers: { 'X-CSRF-Token': getCookie('tt_csrf') } });
          const d = await res.json().catch(() => ({}));
          if (!res.ok) throw new Error(d.detail || `Ошибка ${res.status}`);
          toast(`Бланк загружен · найдено плейсхолдеров: ${d.placeholders.length}`, 'ok');
          closeModal(); loadSettings();
        } catch (e) { toast(e.message, 'err'); }
        finally { loading(false); }
      };
      const tplDel = m.querySelector('#k-tpl-del');
      if (tplDel) tplDel.onclick = async () => {
        if (!confirm('Удалить загруженный бланк? Документ будет печататься текстом из карточки вида.')) return;
        try {
          await api(`/api/docs/templates?type=${encodeURIComponent(kind.code)}`, { method: 'DELETE' });
          toast('Бланк удалён', 'ok');
          closeModal(); loadSettings();
        } catch (e) { toast(e.message, 'err'); }
      };
      const delBtn = m.querySelector('[data-del]');
      if (delBtn) delBtn.onclick = () => confirmDialog(`Удалить вид «${kind.name}»?`,
        'У смен словаря, привязанных к этому виду, печать заявления отключится. Загруженный бланк будет удалён.',
        async () => {
          try {
            const r = await api(`/api/docs/kinds/${kind.id}`, { method: 'DELETE' });
            closeModal();
            toast(`Вид удалён${r.shifts_cleared ? ` · отвязано смен: ${r.shifts_cleared}` : ''}`, 'ok');
            loadSettings();
          } catch (e) { toast(e.message, 'err'); }
        }, 'Удалить');
      m.querySelector('[data-save]').onclick = async () => {
        const body = { name: $('#k-name').value.trim(), text: $('#k-text').value,
                       active: $('#k-active').checked, sort_order: kind?.sort_order ?? 100 };
        if (!body.name) return toast('Введите название', 'warn');
        try {
          if (isNew) {
            await api('/api/docs/kinds', { method: 'POST',
              body: { ...body, code: $('#k-code').value.trim() } });
          } else {
            await api(`/api/docs/kinds/${kind.id}`, { method: 'PUT', body });
          }
          closeModal();
          toast(isNew ? 'Вид заявления создан' : 'Вид заявления сохранён', 'ok');
          loadSettings();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

const DEFAULT_TITLES = { pays_overtime: 'Оплачиваются ли переработки',
                         double_overtime: 'Двойные переработки', plan_equals_fact: 'План=Факт' };
function fmtGdValue(name, v) {
  if (name === 'plan_equals_fact') return { yes: 'Да', no: 'Нет', auto: 'Авто' }[v] || String(v);
  return (v === true || v === 'true' || v === 1) ? 'Да' : 'Нет';
}


/* ══════════════════════════════════════════════════════════════════
   ДНИ ДВОЙНОЙ ОПЛАТЫ: производственный календарь + ВИП-гости
   ══════════════════════════════════════════════════════════════════ */
const DP_MONTHS = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
                   'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'];
const DP_WD = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];

async function refreshDoublePay() {
  const body = document.querySelector('#dp-body');
  if (!body) return;
  const year = state.dpYear || (state.dpYear = new Date().getFullYear());
  let data;
  try {
    data = await api(`/api/doublepay?year=${year}`, { silent: true });
  } catch (e) {
    body.innerHTML = `<div class="empty">Не загрузилось: ${esc(e.message || e)}</div>`;
    return;
  }
  const canWrite = can('settings.doublepay');   // право, а не роль: гранты и группы учитываются
  const scopeShort = { shift: 'сменщики', week5: 'пятидневка', all: 'все' };
  const byMonth = {};
  data.days.forEach(d => { (byMonth[d.month] ||= []).push(d); });

  body.innerHTML = `
    <div class="dp-head">
      <div class="month-nav">
        <button id="dp-prev">‹</button><div class="label">${year}</div><button id="dp-next">›</button>
      </div>
      <span class="badge">${data.days.length} ${plural(data.days.length, 'день', 'дня', 'дней')} в календаре</span>
      ${!canWrite ? '<span class="hint" style="margin:0">Править может администратор или менеджер (данные из C&B)</span>' : ''}
    </div>

    ${canWrite ? `
    <div class="dp-form">
      <label class="field"><span>Для кого</span><select id="dp-scope">
        ${data.scopes.map(s => `<option value="${s.id}" ${s.id === 'all' ? 'selected' : ''}>${esc(s.title)}</option>`).join('')}
      </select></label>
      <label class="field"><span>Список дат (через запятую или пробел)</span>
        <input type="text" id="dp-dates" placeholder="01.01.${year}, 07.01.${year}, 23.02.${year}"></label>
      <div class="dp-or">или период</div>
      <label class="field"><span>С</span><input type="date" id="dp-start"></label>
      <label class="field"><span>По</span><input type="date" id="dp-end"></label>
      <div class="field"><span>Дни недели периода (пусто = все)</span>
        <div class="dp-wd">${DP_WD.map((w, i) => `<label><input type="checkbox" value="${i}">${w}</label>`).join('')}</div></div>
      <label class="field"><span>Примечание</span>
        <input type="text" id="dp-note" placeholder="Новогодние праздники · письмо C&B от …"></label>
      <button class="btn btn-primary btn-sm" id="dp-add">Добавить дни</button>
    </div>` : ''}

    ${Object.keys(byMonth).sort((a, b) => a - b).map(m => `
      <div class="opt-group-title">${DP_MONTHS[m - 1]}</div>
      <div class="dp-days">${byMonth[m].map(d => `
        <span class="dp-chip${d.is_weekend ? ' we' : ''}" title="${esc(d.scope_title)}${d.note ? ' · ' + esc(d.note) : ''}">
          <b>${esc(d.weekday)} ${String(d.day).padStart(2, '0')}.${String(d.month).padStart(2, '0')}</b>
          <i>${esc(scopeShort[d.scope] || d.scope)}</i>${d.note ? `<span>${esc(d.note)}</span>` : ''}
          ${canWrite ? `<button class="dp-del" data-day-del="${d.id}" title="Удалить день">×</button>` : ''}
        </span>`).join('')}</div>`).join('')
      || `<div class="empty" style="padding:10px 0">За ${year} год дней пока нет — добавьте из производственного календаря</div>`}

    <div class="opt-group-title" style="margin-top:14px">ВИП-гости: периоды двойных переработок</div>
    <p class="hint" style="margin-top:0">Сотрудник работает с ВИП-гостем — назначьте период, и его переработки в эти дни
      станут двойными (ДЯ2/ДН2), даже если по производственному календарю день обычный.
      Совпадение с календарём тариф не увеличивает — всегда ×2, не ×4.</p>
    ${canWrite ? `
    <div class="dp-form">
      <label class="field"><span>Сотрудник</span><select id="vip-emp">
        ${(state.employees || []).map(e => `<option value="${e.id}">${esc(e.full_name)}</option>`).join('')}
      </select></label>
      <label class="field"><span>С</span><input type="date" id="vip-start"></label>
      <label class="field"><span>По</span><input type="date" id="vip-end"></label>
      <label class="field"><span>Примечание</span><input type="text" id="vip-note" placeholder="ВИП-гость: фамилия / вилла"></label>
      <button class="btn btn-primary btn-sm" id="vip-add">Назначить ×2</button>
    </div>` : ''}
    ${data.vip.length ? data.vip.map(v => `
      <div class="rule-row">
        <div><div class="lbl">${esc(v.employee_full_name || v.employee_name)} ·
          ${dateRu(v.start_date)} – ${dateRu(v.end_date)}
          <span class="badge warn">${v.days} ${plural(v.days, 'день', 'дня', 'дней')}</span></div>
          <div class="desc">${esc(v.note || 'без примечания')}${v.author ? ' · добавил(а): ' + esc(v.author) : ''}</div></div>
        ${canWrite ? `<div class="rule-input"><button class="btn btn-sm btn-danger" data-vip-del="${v.id}">Удалить</button></div>` : ''}
      </div>`).join('') : '<div class="empty" style="padding:10px 0">Периодов нет</div>'}`;

  document.querySelector('#dp-prev').onclick = () => { state.dpYear = year - 1; refreshDoublePay(); };
  document.querySelector('#dp-next').onclick = () => { state.dpYear = year + 1; refreshDoublePay(); };
  if (canWrite) {
    document.querySelector('#dp-add').onclick = async () => {
      const weekdays = [...body.querySelectorAll('.dp-wd input:checked')].map(i => +i.value);
      const payload = {
        dates: document.querySelector('#dp-dates').value.trim(),
        start: document.querySelector('#dp-start').value || null,
        end: document.querySelector('#dp-end').value || null,
        weekdays: weekdays.length ? weekdays : null,
        scope: document.querySelector('#dp-scope').value,
        note: document.querySelector('#dp-note').value.trim(),
      };
      if (!payload.dates && !(payload.start && payload.end))
        return toast('Введите список дат или период', 'warn');
      try {
        const r = await api('/api/doublepay/days', { method: 'POST', body: payload });
        toast(`Добавлено: ${r.added}, обновлено: ${r.updated}. Переработки этих дней считаются двойными`, 'ok');
        refreshDoublePay();
      } catch (e) { toast(e.message, 'err'); }
    };
    const vipBtn = document.querySelector('#vip-add');
    if (vipBtn) vipBtn.onclick = async () => {
      const payload = {
        employee_id: +document.querySelector('#vip-emp').value,
        start_date: document.querySelector('#vip-start').value,
        end_date: document.querySelector('#vip-end').value,
        note: document.querySelector('#vip-note').value.trim(),
      };
      if (!payload.employee_id || !payload.start_date || !payload.end_date)
        return toast('Выберите сотрудника и укажите даты периода', 'warn');
      try {
        const r = await api('/api/doublepay/vip', { method: 'POST', body: payload });
        toast(`Назначены двойные переработки: ${r.item.days} ${plural(r.item.days, 'день', 'дня', 'дней')}`, 'ok');
        refreshDoublePay();
      } catch (e) { toast(e.message, 'err'); }
    };
  }
  body.querySelectorAll('[data-day-del]').forEach(b => b.onclick = () => {
    confirmDialog('Удалить день двойной оплаты?',
      'Переработки этого дня снова будут считаться одинарными (ДЯ/ДН). Расчёт подхватит изменение сразу.',
      async () => {
        try {
          await api(`/api/doublepay/days/${b.dataset.dayDel}`, { method: 'DELETE' });
          toast('День удалён. Переработки этого дня снова считаются одинарными', 'ok');
          refreshDoublePay();
        } catch (e) { toast(e.message, 'err'); }
      }, 'Удалить');
  });
  body.querySelectorAll('[data-vip-del]').forEach(b => b.onclick = () => {
    confirmDialog('Удалить ВИП-период?',
      'Переработки сотрудника в эти дни вернутся к обычному тарифу (если день не остался в календаре двойной оплаты).',
      async () => {
        try {
          await api(`/api/doublepay/vip/${b.dataset.vipDel}`, { method: 'DELETE' });
          toast('Период удалён. Переработки вернулись к обычному тарифу', 'ok');
          refreshDoublePay();
        } catch (e) { toast(e.message, 'err'); }
      }, 'Удалить');
  });
}

/* ── словарь смен: произвольные часы работы ── */
async function shiftModal(st) {
  /* «Код в табеле» — выбор из справочника CFG-DAY-CODES (T1); если словарь ещё не
     загружен, добираем его, иначе редактор предложит только «не задан». */
  if (!(state.tabelCodes || []).length) {
    try {
      state.tabelCodes = (await api('/api/shift-types/tabel-codes', { silent: true })).codes || [];
    } catch { state.tabelCodes = state.tabelCodes || []; }
  }
  const isNew = !st;
  openModal({
    title: isNew ? 'Новая смена' : st.name,
    subtitle: 'Любые часы работы: 08:00–17:00, 09:00–18:00, ночные и т.д.',
    body: `
      <div class="grid-2">
        <label class="field"><span>Код (латиницей)</span><input type="text" id="sh-code" value="${esc(st?.code || '')}" placeholder="DAY9_17"></label>
        <label class="field"><span>Название</span><input type="text" id="sh-name" value="${esc(st?.name || '')}" placeholder="08:00–17:00 (9 ч)"></label>
        <label class="field"><span>Начало</span><input type="time" id="sh-start" value="${esc(st?.start_time || '08:00')}"></label>
        <label class="field"><span>Конец</span><input type="time" id="sh-end" value="${esc(st?.end_time || '17:00')}"></label>
        <label class="field"><span>Тип</span><select id="sh-kind">
          <option value="work" ${st?.kind === 'work' ? 'selected' : ''}>рабочая смена</option>
          <option value="absence" ${st?.kind === 'absence' ? 'selected' : ''}>отсутствие / выходной</option>
        </select></label>
        <label class="field" id="sh-doc-wrap"><span>Заявление (печать из ячейки графика)</span><select id="sh-doc">
          <option value="">— не печатать —</option>
          ${(state.docKinds || []).filter(k => k.active !== false).map(k =>
            `<option value="${esc(k.code)}">${esc(k.name)}</option>`).join('')}
          ${st?.doc_type && !(state.docKinds || []).some(k => k.code === st.doc_type)
            ? `<option value="${esc(st.doc_type)}" selected>${esc(st.doc_type)} (вид удалён — выберите другой)</option>` : ''}
        </select></label>
        <label class="field"><span>Цвет</span><input type="color" id="sh-color" value="${esc(st?.color || '#34a862')}" style="height:44px;padding:4px"></label>
      </div>
      <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
        <input type="checkbox" id="sh-overnight" ${st?.overnight ? 'checked' : ''} style="width:17px;height:17px;accent-color:var(--primary)">
        Смена через полночь (ночная): конец принадлежит следующим суткам, часы — дате начала
      </label>
      <div id="sh-punch-wrap">
        <div class="opt-group-title" style="margin:12px 0 6px">Отметки во время этого отсутствия</div>
        <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
          <input type="checkbox" id="sh-punch-in" ${st?.punch_in_allowed !== false ? 'checked' : ''} style="width:17px;height:17px;accent-color:var(--primary)">
          Сотрудник может нажать «Пришёл на работу»
        </label>
        <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
          <input type="checkbox" id="sh-punch-out" ${st?.punch_out_allowed !== false ? 'checked' : ''} style="width:17px;height:17px;accent-color:var(--primary)">
          Сотрудник может нажать «Ушёл с работы»
        </label>
        <div class="hint" style="margin-top:4px">Если снять, кнопка в «Моих отметках» станет неактивной с подписью
          «сейчас статус: …». При назначении отсутствия на период или ячейку можно переопределить индивидуально.</div>
      </div>
      ${isNew ? '' : `<label class="field"><span>Изменения вступают в силу с даты</span>
        <input type="date" id="sh-eff" value="${todayISO()}">
        <div class="hint" style="margin-top:2px">Прошлые графики и табели останутся считаться по ПРЕЖНИМ значениям —
        история не ломается. Дату можно задать и в прошлом (тогда период пересчитается по-новому).</div></label>`}
      <p class="hint" id="sh-hours"></p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-save>${isNew ? 'Создать' : 'Сохранить'}</button>`,
    onMount(m) {
      $('#sh-doc').value = st?.doc_type || '';
      const kindToggle = () => {
        const isWork = $('#sh-kind').value === 'work';
        $('#sh-punch-wrap').style.display = isWork ? 'none' : '';
        /* заявление печатается только по отсутствию (пункт 6 задания 17.10.2026) */
        $('#sh-doc-wrap').style.display = isWork ? 'none' : '';
      };
      $('#sh-kind').onchange = kindToggle; kindToggle();
      const recalc = () => {
        const s = $('#sh-start').value, e = $('#sh-end').value;
        if (!s || !e) return;
        const [h1, m1] = s.split(':').map(Number), [h2, m2] = e.split(':').map(Number);
        let mins = (h2 * 60 + m2) - (h1 * 60 + m1);
        const over = mins <= 0;
        if (over) mins += 24 * 60;
        $('#sh-hours').textContent = `Длительность: ${Math.floor(mins / 60)} ч ${mins % 60 ? (mins % 60) + ' мин' : ''}${over ? ' · через полночь' : ''}`;
        if (over) $('#sh-overnight').checked = true;
      };
      $('#sh-start').onchange = recalc; $('#sh-end').onchange = recalc; recalc();

      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        const kindSel = $('#sh-kind').value;
        const body = {
          code: $('#sh-code').value.trim().toUpperCase(), name: $('#sh-name').value.trim(),
          kind: kindSel === 'work' ? 'work' : 'absence',
          start_time: $('#sh-start').value, end_time: $('#sh-end').value,
          overnight: $('#sh-overnight').checked, color: $('#sh-color').value,
          sort_order: st?.sort_order ?? 100,
          is_working: kindSel === 'work',
          counts_as_worked: kindSel === 'work',
          punch_in_allowed: kindSel === 'work' ? true : $('#sh-punch-in').checked,
          punch_out_allowed: kindSel === 'work' ? true : $('#sh-punch-out').checked,
          is_default_off: st?.is_default_off ?? false,
          doc_type: kindSel === 'work' ? '' : $('#sh-doc').value,
          effective_from: isNew ? null : ($('#sh-eff')?.value || todayISO()),
        };
        if (!body.code || !body.name) return toast('Заполните код и название', 'warn');
        try {
          isNew ? await api('/api/shift-types', { method: 'POST', body })
                : await api(`/api/shift-types/${st.id}`, { method: 'PUT', body });
          closeModal();
          await loadDirectory();
          toast('Словарь смен обновлён', 'ok');
          loadSettings();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}
