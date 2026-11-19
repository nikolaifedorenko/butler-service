'use strict';
/* ══ НАСТРОЙКИ (продолжение): справочники, виды заявлений, двойные оплаты, словарь смен ══
   Вынесено из app.js без изменения логики.
   Модуль на lit-html (ADR-0013, раздел 7). */

import { can, loadDirectory } from '../app.js';
import {
  $, api, closeModal, confirmDialog, dateRu, downloadBlob, getCookie, loading, openModal, plural, state, todayISO, toast,
} from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { loadSettings } from './settings.js';

/* ══════════════════════════════════════════════════════════════════
   НАСТРОЙКИ: правила + словарь смен (произвольные часы)
   ══════════════════════════════════════════════════════════════════ */
/* ── справочники «Департаменты и службы» (панель настроек) ── */
export async function renderDicts() {
  const host = $('#dicts-body');
  if (!host) return;
  let deps = [], subs = [];
  try { deps = await api('/api/departments', { silent: true }); } catch { /* пустой список */ }
  try { subs = await api('/api/subdivisions', { silent: true }); } catch { /* пустой список */ }
  state.departments = deps; state.subdivisions = subs;

  const col = (items, kind, url, title, ph) => {
    const add = async () => {
      const name = $(`#${kind}-new`, host).value.trim();
      if (!name) return toast('Введите название', 'warn');
      try { await api(url, { method: 'POST', body: { name } }); toast('Добавлено', 'ok'); renderDicts(); }
      catch (e) { toast(e.message, 'err'); }
    };
    const del = item => confirmDialog(`Удалить «${item.name}»?`,
      'У сотрудников, где это значение выбрано, поле будет очищено. История документов не меняется.',
      async () => {
        try { await api(`${url}/${item.id}`, { method: 'DELETE' }); toast('Удалено', 'ok'); renderDicts(); }
        catch (e) { toast(e.message, 'err'); }
      }, 'Удалить');
    /* атрибуты data-dep-ren / data-sub-ren — по виду справочника: имя атрибута в шаблоне не собирается */
    const ren = d => (kind === 'dep'
      ? html`<button class="btn btn-sm btn-ghost" data-dep-ren=${d.id} @click=${() => renameDictModal(url, d)}>Переименовать</button>
        <button class="btn btn-sm btn-ghost" data-dep-del=${d.id} @click=${() => del(d)}>Удалить</button>`
      : html`<button class="btn btn-sm btn-ghost" data-sub-ren=${d.id} @click=${() => renameDictModal(url, d)}>Переименовать</button>
        <button class="btn btn-sm btn-ghost" data-sub-del=${d.id} @click=${() => del(d)}>Удалить</button>`);
    return html`<div>
      <div class="opt-group-title">${title}</div>
      <table class="data"><tbody>
        ${items.length ? items.map(d => html`<tr>
          <td>${d.name}</td>
          <td class="num" style="white-space:nowrap">${ren(d)}</td></tr>`) : html`<tr><td class="empty">Пока не созданы</td></tr>`}
      </tbody></table>
      <div style="display:flex;gap:8px;margin-top:8px">
        <input type="text" id=${`${kind}-new`} placeholder=${ph} style="flex:1" @keydown=${e => { if (e.key === 'Enter') add(); }}>
        <button class="btn btn-sm" id=${`${kind}-add`} @click=${add}>+ Добавить</button>
      </div>
    </div>`;
  };
  render(html`${col(deps, 'dep', '/api/departments', 'Департаменты', 'Новый департамент')}${
    col(subs, 'sub', '/api/subdivisions', 'Службы / подразделения', 'Новая служба')}`, mount(host));
}

function renameDictModal(url, item) {
  if (!item) return;
  openModal({
    title: 'Переименовать',
    body: html`<label class="field"><span>Название</span><input type="text" id="dict-name" .value=${item.name}></label>
           <p class="hint">Новое название автоматически обновится в карточках сотрудников.</p>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Сохранить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        const name = $('#dict-name', m).value.trim();
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
export function openKindModal(kind) {
  const isNew = !kind;
  openModal({
    title: isNew ? 'Новый вид заявления' : kind.name,
    subtitle: isNew ? 'Код — строчная латиница: по нему хранится фирменный бланк .docx'
                    : `Код: ${kind.code}${kind.builtin ? ' · встроенный вид' : ''}`,
    wide: true,
    body: html`
      <div class="grid-2">
        <label class="field"><span>Код (латиницей${isNew ? '' : ', неизменяемый'})</span>
          <input type="text" id="k-code" .value=${kind?.code || ''} placeholder="mat_aid" ?disabled=${!isNew}></label>
        <label class="field"><span>Название (как в списках)</span>
          <input type="text" id="k-name" .value=${kind?.name || ''} placeholder="Заявление на материальную помощь"></label>
      </div>
      <label class="field"><span>Текст заявления (плейсхолдеры в фигурных скобках)</span>
        <textarea id="k-text" rows="12" style="font-family:ui-monospace,monospace;font-size:12px"
          placeholder="{director} / {company} / от {full_name_genitive} … ЗАЯВЛЕНИЕ … Прошу … {today} / {short_name}" .value=${kind?.text || ''}></textarea></label>
      <label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
        <input type="checkbox" id="k-active" .checked=${kind?.active !== false} style="width:17px;height:17px;accent-color:var(--primary)">
        Показывать вид в списках выбора (снимите, чтобы скрыть устаревший, но оставить в истории)
      </label>
      ${kind ? html`<div class="rule-row" style="margin-top:10px;align-items:flex-start">
        <div><div class="lbl">Фирменный бланк компании (.docx)</div>
          <div class="desc">${kind.template?.uploaded
            ? `загружен: ${kind.template.filename || ''} · найдено плейсхолдеров: ${(kind.template?.placeholders || []).length}`
            : 'не загружен — документ печатается текстом выше; бланк перекрывает текст и сохраняет шрифты, логотип и колонтитулы Word'}</div></div>
        <div class="rule-input" style="gap:6px;display:flex">
          <button class="btn btn-sm" id="k-sample" type="button">Пример .docx</button>
          <label class="btn btn-sm" style="cursor:pointer">Загрузить .docx
            <input type="file" accept=".docx" id="k-file" style="display:none"></label>
          ${kind.template?.uploaded ? html`<button class="btn btn-sm btn-danger" id="k-tpl-del" type="button">Удалить бланк</button>` : nothing}
        </div></div>`
        : html`<p class="hint">После создания вида можно загрузить фирменный бланк .docx — он перекроет текст, сохранив оформление Word.</p>`}
      <details style="margin-top:8px"><summary class="hint" style="cursor:pointer">Доступные плейсхолдеры</summary>
        <table class="data" style="margin-top:8px">${Object.entries(state.docPlaceholders || {}).map(([k, v]) =>
          html`<tr><td><code>{${k}}</code></td><td>${v}</td></tr>`)}</table></details>`,
    footer: html`${isNew ? nothing : html`<button class="btn btn-danger" data-del>Удалить вид</button>`}
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
        const body = { name: $('#k-name', m).value.trim(), text: $('#k-text', m).value,
                       active: $('#k-active', m).checked, sort_order: kind?.sort_order ?? 100 };
        if (!body.name) return toast('Введите название', 'warn');
        try {
          if (isNew) {
            await api('/api/docs/kinds', { method: 'POST',
              body: { ...body, code: $('#k-code', m).value.trim() } });
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

export function fmtGdValue(name, v) {
  if (name === 'plan_equals_fact') return { yes: 'Да', no: 'Нет', auto: 'Авто' }[v] || String(v);
  return (v === true || v === 'true' || v === 1) ? 'Да' : 'Нет';
}

/* ══════════════════════════════════════════════════════════════════
   ДНИ ДВОЙНОЙ ОПЛАТЫ: производственный календарь + ВИП-гости
   ══════════════════════════════════════════════════════════════════ */
const DP_MONTHS = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
                   'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'];
const DP_WD = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];

export async function refreshDoublePay() {
  const host = $('#dp-body');
  if (!host) return;
  const year = state.dpYear || (state.dpYear = new Date().getFullYear());
  let data;
  try {
    data = await api(`/api/doublepay?year=${year}`, { silent: true });
  } catch (e) {
    render(html`<div class="empty">Не загрузилось: ${e.message || e}</div>`, mount(host));
    return;
  }
  const canWrite = can('settings.doublepay');   // право, а не роль: гранты и группы учитываются
  const scopeShort = { shift: 'сменщики', week5: 'пятидневка', all: 'все' };
  const byMonth = {};
  data.days.forEach(d => { (byMonth[d.month] ||= []).push(d); });
  const again = () => refreshDoublePay();
  const q = sel => host.querySelector(sel);

  const addDays = async () => {
    const weekdays = [...host.querySelectorAll('.dp-wd input:checked')].map(i => +i.value);
    const payload = {
      dates: q('#dp-dates').value.trim(),
      start: q('#dp-start').value || null,
      end: q('#dp-end').value || null,
      weekdays: weekdays.length ? weekdays : null,
      scope: q('#dp-scope').value,
      note: q('#dp-note').value.trim(),
    };
    if (!payload.dates && !(payload.start && payload.end))
      return toast('Введите список дат или период', 'warn');
    try {
      const r = await api('/api/doublepay/days', { method: 'POST', body: payload });
      toast(`Добавлено: ${r.added}, обновлено: ${r.updated}. Переработки этих дней считаются двойными`, 'ok');
      again();
    } catch (e) { toast(e.message, 'err'); }
  };
  const addVip = async () => {
    const payload = {
      employee_id: +q('#vip-emp').value,
      start_date: q('#vip-start').value,
      end_date: q('#vip-end').value,
      note: q('#vip-note').value.trim(),
    };
    if (!payload.employee_id || !payload.start_date || !payload.end_date)
      return toast('Выберите сотрудника и укажите даты периода', 'warn');
    try {
      const r = await api('/api/doublepay/vip', { method: 'POST', body: payload });
      toast(`Назначены двойные переработки: ${r.item.days} ${plural(r.item.days, 'день', 'дня', 'дней')}`, 'ok');
      again();
    } catch (e) { toast(e.message, 'err'); }
  };
  const delDay = d => confirmDialog('Удалить день двойной оплаты?',
    'Переработки этого дня снова будут считаться одинарными (ДЯ/ДН). Расчёт подхватит изменение сразу.',
    async () => {
      try {
        await api(`/api/doublepay/days/${d.id}`, { method: 'DELETE' });
        toast('День удалён. Переработки этого дня снова считаются одинарными', 'ok');
        again();
      } catch (e) { toast(e.message, 'err'); }
    }, 'Удалить');
  const delVip = v => confirmDialog('Удалить ВИП-период?',
    'Переработки сотрудника в эти дни вернутся к обычному тарифу (если день не остался в календаре двойной оплаты).',
    async () => {
      try {
        await api(`/api/doublepay/vip/${v.id}`, { method: 'DELETE' });
        toast('Период удалён. Переработки вернулись к обычному тарифу', 'ok');
        again();
      } catch (e) { toast(e.message, 'err'); }
    }, 'Удалить');
  const months = Object.keys(byMonth).sort((a, b) => a - b);

  render(html`
    <div class="dp-head">
      <div class="month-nav">
        <button id="dp-prev" @click=${() => { state.dpYear = year - 1; again(); }}>‹</button><div class="label">${year}</div><button id="dp-next" @click=${() => { state.dpYear = year + 1; again(); }}>›</button>
      </div>
      <span class="badge">${data.days.length} ${plural(data.days.length, 'день', 'дня', 'дней')} в календаре</span>
      ${!canWrite ? html`<span class="hint" style="margin:0">Править может администратор или менеджер (данные из C&B)</span>` : nothing}
    </div>

    ${canWrite ? html`
    <div class="dp-form">
      <label class="field"><span>Для кого</span><select id="dp-scope">
        ${data.scopes.map(s => html`<option value=${s.id} ?selected=${s.id === 'all'}>${s.title}</option>`)}
      </select></label>
      <label class="field"><span>Список дат (через запятую или пробел)</span>
        <input type="text" id="dp-dates" placeholder=${`01.01.${year}, 07.01.${year}, 23.02.${year}`}></label>
      <div class="dp-or">или период</div>
      <label class="field"><span>С</span><input type="date" id="dp-start"></label>
      <label class="field"><span>По</span><input type="date" id="dp-end"></label>
      <div class="field"><span>Дни недели периода (пусто = все)</span>
        <div class="dp-wd">${DP_WD.map((w, i) => html`<label><input type="checkbox" value=${i}>${w}</label>`)}</div></div>
      <label class="field"><span>Примечание</span>
        <input type="text" id="dp-note" placeholder="Новогодние праздники · письмо C&B от …"></label>
      <button class="btn btn-primary btn-sm" id="dp-add" @click=${addDays}>Добавить дни</button>
    </div>` : nothing}

    ${months.length ? months.map(m => html`
      <div class="opt-group-title">${DP_MONTHS[m - 1]}</div>
      <div class="dp-days">${byMonth[m].map(d => html`
        <span class=${`dp-chip${d.is_weekend ? ' we' : ''}`} title=${d.scope_title + (d.note ? ' · ' + d.note : '')}>
          <b>${d.weekday} ${String(d.day).padStart(2, '0')}.${String(d.month).padStart(2, '0')}</b>
          <i>${scopeShort[d.scope] || d.scope}</i>${d.note ? html`<span>${d.note}</span>` : nothing}
          ${canWrite ? html`<button class="dp-del" data-day-del=${d.id} title="Удалить день" @click=${() => delDay(d)}>×</button>` : nothing}
        </span>`)}</div>`)
      : html`<div class="empty" style="padding:10px 0">За ${year} год дней пока нет — добавьте из производственного календаря</div>`}

    <div class="opt-group-title" style="margin-top:14px">ВИП-гости: периоды двойных переработок</div>
    <p class="hint" style="margin-top:0">Сотрудник работает с ВИП-гостем — назначьте период, и его переработки в эти дни
      станут двойными (ДЯ2/ДН2), даже если по производственному календарю день обычный.
      Совпадение с календарём тариф не увеличивает — всегда ×2, не ×4.</p>
    ${canWrite ? html`
    <div class="dp-form">
      <label class="field"><span>Сотрудник</span><select id="vip-emp">
        ${(state.employees || []).map(e => html`<option value=${e.id}>${e.full_name}</option>`)}
      </select></label>
      <label class="field"><span>С</span><input type="date" id="vip-start"></label>
      <label class="field"><span>По</span><input type="date" id="vip-end"></label>
      <label class="field"><span>Примечание</span><input type="text" id="vip-note" placeholder="ВИП-гость: фамилия / вилла"></label>
      <button class="btn btn-primary btn-sm" id="vip-add" @click=${addVip}>Назначить ×2</button>
    </div>` : nothing}
    ${data.vip.length ? data.vip.map(v => html`
      <div class="rule-row">
        <div><div class="lbl">${v.employee_full_name || v.employee_name} ·
          ${dateRu(v.start_date)} – ${dateRu(v.end_date)}
          <span class="badge warn">${v.days} ${plural(v.days, 'день', 'дня', 'дней')}</span></div>
          <div class="desc">${v.note || 'без примечания'}${v.author ? ' · добавил(а): ' + v.author : ''}</div></div>
        ${canWrite ? html`<div class="rule-input"><button class="btn btn-sm btn-danger" data-vip-del=${v.id} @click=${() => delVip(v)}>Удалить</button></div>` : nothing}
      </div>`) : html`<div class="empty" style="padding:10px 0">Периодов нет</div>`}`, mount(host));
}

/* ── словарь смен: произвольные часы работы ── */
export async function shiftModal(st) {
  /* «Код в табеле» — выбор из справочника CFG-DAY-CODES (T1); если словарь ещё не
     загружен, добираем его, иначе редактор предложит только «не задан». */
  if (!(state.tabelCodes || []).length) {
    try {
      state.tabelCodes = (await api('/api/shift-types/tabel-codes', { silent: true })).codes || [];
    } catch { state.tabelCodes = state.tabelCodes || []; }
  }
  const isNew = !st;
  const kinds = (state.docKinds || []).filter(k => k.active !== false);
  const chk = (id, on, label) => html`<label style="display:flex;gap:9px;align-items:center;font-size:13.5px;color:var(--muted)">
    <input type="checkbox" id=${id} .checked=${on} style="width:17px;height:17px;accent-color:var(--primary)"> ${label}</label>`;
  openModal({
    title: isNew ? 'Новая смена' : st.name,
    subtitle: 'Любые часы работы: 08:00–17:00, 09:00–18:00, ночные и т.д.',
    body: html`
      <div class="grid-2">
        <label class="field"><span>Код (латиницей)</span><input type="text" id="sh-code" .value=${st?.code || ''} placeholder="DAY9_17"></label>
        <label class="field"><span>Название</span><input type="text" id="sh-name" .value=${st?.name || ''} placeholder="08:00–17:00 (9 ч)"></label>
        <label class="field"><span>Начало</span><input type="time" id="sh-start" .value=${st?.start_time || '08:00'}></label>
        <label class="field"><span>Конец</span><input type="time" id="sh-end" .value=${st?.end_time || '17:00'}></label>
        <label class="field"><span>Тип</span><select id="sh-kind">
          <option value="work" ?selected=${st?.kind === 'work'}>рабочая смена</option>
          <option value="absence" ?selected=${st?.kind === 'absence'}>отсутствие / выходной</option>
        </select></label>
        <label class="field" id="sh-doc-wrap"><span>Заявление (печать из ячейки графика)</span><select id="sh-doc">
          <option value="">— не печатать —</option>
          ${kinds.map(k => html`<option value=${k.code} ?selected=${st?.doc_type === k.code}>${k.name}</option>`)}
          ${st?.doc_type && !(state.docKinds || []).some(k => k.code === st.doc_type)
            ? html`<option value=${st.doc_type} selected>${st.doc_type} (вид удалён — выберите другой)</option>` : nothing}
        </select></label>
        <label class="field"><span>Цвет</span><input type="color" id="sh-color" .value=${st?.color || '#34a862'} style="height:44px;padding:4px"></label>
      </div>
      ${chk('sh-overnight', !!st?.overnight, 'Смена через полночь (ночная): конец принадлежит следующим суткам, часы — дате начала')}
      <div id="sh-punch-wrap">
        <div class="opt-group-title" style="margin:12px 0 6px">Отметки во время этого отсутствия</div>
        ${chk('sh-punch-in', st?.punch_in_allowed !== false, 'Сотрудник может нажать «Пришёл на работу»')}
        ${chk('sh-punch-out', st?.punch_out_allowed !== false, 'Сотрудник может нажать «Ушёл с работы»')}
        <div class="hint" style="margin-top:4px">Если снять, кнопка в «Моих отметках» станет неактивной с подписью
          «сейчас статус: …». При назначении отсутствия на период или ячейку можно переопределить индивидуально.</div>
      </div>
      ${isNew ? nothing : html`<label class="field"><span>Изменения вступают в силу с даты</span>
        <input type="date" id="sh-eff" .value=${todayISO()}>
        <div class="hint" style="margin-top:2px">Прошлые графики и табели останутся считаться по ПРЕЖНИМ значениям —
        история не ломается. Дату можно задать и в прошлом (тогда период пересчитается по-новому).</div></label>`}
      <p class="hint" id="sh-hours"></p>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-save>${isNew ? 'Создать' : 'Сохранить'}</button>`,
    onMount(m) {
      const q = sel => m.querySelector(sel);
      const kindToggle = () => {
        const isWork = q('#sh-kind').value === 'work';
        q('#sh-punch-wrap').style.display = isWork ? 'none' : '';
        /* заявление печатается только по отсутствию */
        q('#sh-doc-wrap').style.display = isWork ? 'none' : '';
      };
      q('#sh-kind').onchange = kindToggle; kindToggle();
      const recalc = () => {
        const s = q('#sh-start').value, e = q('#sh-end').value;
        if (!s || !e) return;
        const [h1, m1] = s.split(':').map(Number), [h2, m2] = e.split(':').map(Number);
        let mins = (h2 * 60 + m2) - (h1 * 60 + m1);
        const over = mins <= 0;
        if (over) mins += 24 * 60;
        q('#sh-hours').textContent = `Длительность: ${Math.floor(mins / 60)} ч ${mins % 60 ? (mins % 60) + ' мин' : ''}${over ? ' · через полночь' : ''}`;
        if (over) q('#sh-overnight').checked = true;
      };
      q('#sh-start').onchange = recalc; q('#sh-end').onchange = recalc; recalc();

      q('[data-cancel]').onclick = closeModal;
      q('[data-save]').onclick = async () => {
        const kindSel = q('#sh-kind').value;
        const body = {
          code: q('#sh-code').value.trim().toUpperCase(), name: q('#sh-name').value.trim(),
          kind: kindSel === 'work' ? 'work' : 'absence',
          start_time: q('#sh-start').value, end_time: q('#sh-end').value,
          overnight: q('#sh-overnight').checked, color: q('#sh-color').value,
          sort_order: st?.sort_order ?? 100,
          is_working: kindSel === 'work',
          counts_as_worked: kindSel === 'work',
          punch_in_allowed: kindSel === 'work' ? true : q('#sh-punch-in').checked,
          punch_out_allowed: kindSel === 'work' ? true : q('#sh-punch-out').checked,
          is_default_off: st?.is_default_off ?? false,
          doc_type: kindSel === 'work' ? '' : q('#sh-doc').value,
          effective_from: isNew ? null : (q('#sh-eff')?.value || todayISO()),
        };
        if (!body.code || !body.name) return toast('Заполните код и название', 'warn');
        try {
          if (isNew) await api('/api/shift-types', { method: 'POST', body });
          else await api(`/api/shift-types/${st.id}`, { method: 'PUT', body });
          closeModal();
          await loadDirectory();
          toast('Словарь смен обновлён', 'ok');
          loadSettings();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}
