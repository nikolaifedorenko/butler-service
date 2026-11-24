'use strict';
/* ══ СОТРУДНИКИ: список → карточка → редактор ══
   Вынесено из app.js без изменения логики.
   Модуль на lit-html (ADR-0013, раздел 7). */

import { can, loadDirectory, navigate, registerModule, switchImpersonation } from '../app.js';
import {
  $, $$, POSITION_COLORS, WD_SHORT, api, closeModal, confirmDialog, cssColor, dateRu, hours, openModal, roleTitle, state,
  authContextIsCurrent, authContextSnapshot, todayISO, toast,
} from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';

/* ══════════════════════════════════════════════════════════════════
   СОТРУДНИКИ: список → карточка → редактор
   ══════════════════════════════════════════════════════════════════ */
registerModule({ views: { employees: loadEmployees } });

async function loadEmployees() {
  const started = authContextSnapshot();
  const host = $('#view-employees');
  await loadDirectory();
  if (!authContextIsCurrent(started)) return;
  render(html`
    <div class="page-head">
      <div><h2>Сотрудники</h2><div class="sub">Нажмите на строку, чтобы открыть карточку со всеми подробностями</div></div>
      <div class="spacer"></div>
      ${can('employees.edit') ? html`<button class="btn btn-primary btn-sm" id="e-add" @click=${() => employeeModal(null)}>+ Добавить сотрудника</button>` : nothing}
    </div>
    <div class="table-wrap" tabindex="0">
      <table class="data responsive"><thead><tr>
        <th>Сотрудник</th><th>Должность</th><th>Блок графика</th><th>Статус</th><th></th>
      </tr></thead><tbody>
      ${state.employees.map(e => html`<tr data-card=${e.id} class="row-card" @click=${() => employeeCard(e)}>
        <td class="who" data-label="Сотрудник">
          <span class="dot-pos" style=${`display:inline-block;width:9px;height:9px;border-radius:3px;background:${cssColor(e.group_color)};margin-right:7px`}></span>${e.full_name}
          ${e.telegram ? html`<small>tg: ${e.telegram}</small>` : nothing}</td>
        <td data-label="Должность">${e.position || '—'}</td>
        <td data-label="Блок">${e.schedule_group || '—'}</td>
        <td data-label="Статус">${e.deleted ? html`<span class="badge muted">удалён (в истории)</span>`
          : e.dismissed_at ? html`<span class="badge muted">уволен ${dateRu(e.dismissed_at)}</span>`
          : e.active ? html`<span class="badge ok">работает</span>` : html`<span class="badge muted">неактивен</span>`}</td>
        <td class="num row-go" aria-hidden="true">→</td>
      </tr>`)}
      </tbody></table>
    </div>
    <p class="hint">Удаление скрывает сотрудника из списков и графика, но вся история (табель, отметки, аудит) сохраняется.</p>`, mount(host));
}

/* Вход в карточку по id из других разделов («Слой 0 Табель», «Слой 1 План/График»):
   открывается ТА ЖЕ карточка, что и по строке раздела «Сотрудники», — правки
   доступны прямо из сетки, без перехода в другой раздел. Право — employees.view
   (как у самого раздела и у GET /api/employees/{id}/history); без права вызывающий
   код даже не делает имя кликабельным, но проверяем и здесь (защита в глубину).
   Если сотрудника нет в кеше справочника (не загружался для этой роли либо он
   удалён и виден только в строках истории), список дозагружается с сервера. */
export async function openEmployeeCard(empId) {
  const started = authContextSnapshot();
  if (!can('employees.view')) return;
  let emp = (state.employees || []).find(e => e.id === empId);
  if (!emp) {
    try {
      const all = await api('/api/employees?include_deleted=true', { silent: true });
      if (!authContextIsCurrent(started)) return;
      emp = all.find(e => e.id === empId);
    } catch (e) { toast(e.message, 'err'); return; }
  }
  if (!emp) return toast('Сотрудник не найден', 'err');
  await employeeCard(emp, started);
}

/* После изменений карточки освежаем справочник и ТЕКУЩИЙ раздел: карточка
   открывается не только из «Сотрудников», но и из Табеля/Графика — сетка за
   модалкой должна показать свежие ФИО, цвет и статус. */
async function refreshAfterEmployeeChange() {
  await loadDirectory();
  if (state.view === 'employees') loadEmployees();
  else navigate(state.view);
}

const bold = v => html`<div style="font-weight:600">${v}</div>`;

async function employeeCard(emp, started = authContextSnapshot()) {
  const history = await api(`/api/employees/${emp.id}/history`);
  if (!authContextIsCurrent(started)) return;
  const contacts = emp.contacts?.length ? emp.contacts
    : (emp.emergency_name ? [{ name: emp.emergency_name, phone: emp.emergency_phone, relation: '' }] : []);
  const canBank = can('employees.bank');   // право, а не роль: гранты и группы учитываются
  const canEdit = can('employees.edit');
  const bankNow = history.bank_now ?? 0;
  const gone = emp.dismissed_at || (!emp.active && !emp.deleted);
  openModal({
    title: emp.full_name,
    subtitle: `${emp.position || 'должность не указана'} · ${emp.schedule_group || 'без блока'}`,
    wide: true,
    body: html`
      <div class="grid-2">
        <div class="field"><span>Табельный номер</span>${bold(emp.tab_number || '—')}</div>
        <div class="field"><span>Дата приёма</span>${bold(emp.hired_at ? dateRu(emp.hired_at) : '—')}</div>
        <div class="field"><span>Гражданство</span>${bold(emp.nationality || '—')}</div>
        <div class="field"><span>Подразделение / служба (для документов)</span>${bold(emp.subdivision || '—')}</div>
        <div class="field"><span>Департамент</span>${bold(emp.department || '—')}</div>
        <div class="field" style="grid-column:1/-1"><span>ФИО в родительном падеже (для документов)</span>
          <div style="font-weight:600">${emp.full_name_genitive || emp.full_name_genitive_hint || '—'}${!emp.full_name_genitive && emp.full_name_genitive_hint ? html` <small class="muted">(подставляется автоматически)</small>` : nothing}</div></div>
        <div class="field"><span>Телефон</span>${bold(emp.phone || '—')}</div>
        <div class="field"><span>Рабочая почта</span>${bold(emp.email || '—')}</div>
        <div class="field"><span>Telegram</span>${bold(emp.telegram || '—')}</div>
        <div class="field"><span>Логин / роль</span><div style="font-weight:600"><code>${emp.username || '—'}</code> · ${roleTitle(emp.role)}</div></div>
        <div class="field"><span>Банк часов (сейчас)</span><div class=${bankNow >= 0 ? 'balance-pos' : 'balance-neg'} style="font-size:18px">${bankNow >= 0 ? '+' : ''}${hours(bankNow)} ч</div>
          <div class="hint" style="margin-top:2px">итог последнего закрытого периода ± корректировки</div></div>
        <div class="field"><span>Статус</span>${bold(emp.deleted ? 'удалён (хранится в истории)'
          : emp.dismissed_at ? `уволен (последний рабочий день ${dateRu(emp.dismissed_at)})` : emp.active ? 'работает' : 'неактивен')}</div>
      </div>
      <div class="opt-group-title">Периоды работы (приём → увольнение → повторный приём)</div>
      ${(history.employment || []).length ? history.employment.map(h => html`<div style="font-size:13.5px;padding:3px 0">
        ${dateRu(h.start)} — ${h.end ? dateRu(h.end) : 'настоящее время'}${h.current ? html` <span class="badge ok">работает</span>` : nothing}${h.note ? html` <small class="muted">· ${h.note}</small>` : nothing}</div>`) : html`<div class="hint">нет записей</div>`}
      <div class="opt-group-title">Контакты близких (экстренно)</div>
      ${contacts.length ? contacts.map(c => html`<div style="font-size:13.5px;padding:3px 0">
        <b>${c.name}</b> · ${c.phone || '—'}${c.relation ? ` · ${c.relation}` : ''}</div>`)
        : html`<div class="hint">не указаны</div>`}
      <div class="opt-group-title">История должностей</div>
      ${history.positions.length ? history.positions.map(h => html`<div style="font-size:13.5px;padding:3px 0">
        ${h.position} — с ${dateRu(h.start)}${h.end ? ` по ${dateRu(h.end)}` : ' — по настоящее время'}</div>`) : html`<div class="hint">нет записей</div>`}
      <div class="opt-group-title">Блок и значение рабочего дня</div>
      <div style="font-size:14px;margin-bottom:6px"><b>Блок:</b> ${emp.schedule_group || '—'} ·
        <b>значение:</b> ${history.current_value || 'значение блока по умолчанию'}</div>
      <div class="opt-group-title">Блоки графика (переходы между сменами)</div>
      ${history.blocks.length ? history.blocks.map(h => html`<div style="font-size:13.5px;padding:3px 0">
        «${h.group}» — с ${dateRu(h.start)}${h.end ? ` по ${dateRu(h.end)}` : ' — по настоящее время'}${h.pattern_label ? html` <small class="muted">· ${h.pattern_label}</small>` : nothing}</div>`) : html`<div class="hint">нет записей</div>`}
      <div class="opt-group-title">Ручные корректировки банка часов</div>
      ${(history.bank_adjustments || []).length ? history.bank_adjustments.map(a => html`<div style="font-size:13.5px;padding:3px 0">
        <b class=${a.hours >= 0 ? 'balance-pos' : 'balance-neg'}>${a.hours >= 0 ? '+' : ''}${hours(a.hours)} ч</b>
        с ${dateRu(a.date)} — ${a.note} <small class="muted">(${a.author})</small></div>`) : html`<div class="hint">корректировок не было</div>`}`,
    /* правки учётки — по праву employees.edit, как на сервере: без него кнопки вели к 403 */
    footer: html`
      ${canEdit ? html`<button class="btn btn-danger" data-delete>Удалить</button>` : nothing}
      ${!canEdit ? nothing : gone
        ? html`<button class="btn" data-rehire>Принять обратно</button>`
        : html`<button class="btn btn-ghost" data-dismiss>Уволить</button>`}
      <div style="flex:1"></div>
      ${canBank ? html`<button class="btn btn-ghost" data-bank>Корректировка банка</button>` : nothing}
      ${canEdit ? html`<button class="btn btn-ghost" data-block>Перевод в блок</button>` : nothing}
      ${canEdit ? html`<button class="btn btn-ghost" data-pos>Перевод на должность</button>` : nothing}
      ${can('employees.impersonate') ? html`<button class="btn btn-ghost" data-imp>Войти как сотрудник</button>` : nothing}
      ${canEdit ? html`<button class="btn btn-primary" data-edit>Изменить</button>` : nothing}`,
    onMount(m) {
      const on = (sel, fn) => { const b = m.querySelector(sel); if (b) b.onclick = fn; };
      on('[data-edit]', () => { closeModal(); employeeModal(emp); });
      on('[data-imp]', async () => {
        const session = await api('/api/auth/impersonate', { method: 'POST', body: { employee_id: emp.id } });
        if (await switchImpersonation(session, 'me')) toast('Вы смотрите интерфейс глазами сотрудника', 'warn');
      });
      on('[data-pos]', () => { closeModal(); datedActionModal(emp, 'position'); });
      on('[data-block]', () => { closeModal(); datedActionModal(emp, 'block'); });
      on('[data-dismiss]', () => { closeModal(); datedActionModal(emp, 'dismiss'); });
      on('[data-rehire]', () => { closeModal(); rehireModal(emp); });
      on('[data-bank]', () => { closeModal(); bankAdjustModal(emp, history); });
      on('[data-delete]', () => {
        closeModal();
        confirmDialog('Удалить сотрудника?',
          `${emp.full_name} исчезнет из списков и графика. Табель, отметки и аудит сохранятся в истории.`,
          async () => {
            await api(`/api/employees/${emp.id}/delete`, { method: 'POST' });
            toast('Сотрудник удалён из активных списков; история сохранена', 'ok');
            await refreshAfterEmployeeChange();
          }, 'Удалить');
      });
    },
  });
}

/* ── шаблоны блоков: пятидневка (свои выходные) или индивидуальный цикл (3/3, 1/3, custom:РРВВ) ── */
function patternFields(prefix, kind, values, today) {
  /* Значение рабочего дня: код и окно из CFG-WINDOWS; пусто — берётся
     значение блока из настроек объекта. Список значений — /api/tabel-values. */
  const valueField = html`
    <label class="field" style="margin-top:8px"><span>Значение рабочего дня</span>
      <select id=${`${prefix}-value`}>
        <option value="">— значение блока по умолчанию —</option>
        ${(values || []).map(v => html`<option value=${v.value}>${v.value} · ${v.title} · ${v.start_hm}–${v.end_hm}</option>`)}
      </select></label>`;
  if (kind === 'week5') return html`
    <div class="opt-group-title" style="margin-top:8px">Выходные дни этого сотрудника (пятидневка)</div>
    <div class="wd-picker" id=${`${prefix}-wd`}>
      ${WD_SHORT.map((w, i) => html`<label><input type="checkbox" value=${i} .checked=${i === 5 || i === 6}>${w}</label>`)}
    </div>
    ${valueField}
    <p class="hint" style="margin:2px 0 0">У каждого сотрудника пятидневки СВОИ выходные: например у начальника вс/пн —
      отметьте «вс» и «пн» (снимите «сб»). Значение рабочего дня — своё у каждого.</p>`;
  if (kind === 'cycle') return html`
    <div class="grid-2" style="margin-top:8px">
      <label class="field"><span>Цикл</span><input type="text" id=${`${prefix}-cycle`} .value=${'3/3'} placeholder="3/3, 1/3, 4/2 или custom:РРВВРВ"></label>
      <label class="field"><span>Опорная дата (начало цикла)</span><input type="date" id=${`${prefix}-anchor`} .value=${today}></label>
    </div>
    ${valueField}
    <p class="hint" style="margin:2px 0 0">«Другие смены»: 3/3, 1/3, сутки через трое (окно 08:00–20:00 с явкой
      «Я 12») или произвольный цикл «custom:РРВВРВ» (Р — рабочий, В — выходной).</p>`;
  if (kind === 'manual') return html`<p class="hint">График этого сотрудника заполняется вручную по ячейкам — автоматического шаблона нет.</p>`;
  return html`${valueField}
    <p class="hint" style="margin:2px 0 0">Блок считается базовым циклом объекта (Настройки → Базовый цикл);
      значение рабочего дня можно задать лично сотруднику.</p>`;
}

function collectPatternFields(m, prefix, kind, date) {
  const body = { kind };
  body.value = $(`#${prefix}-value`, m)?.value || '';
  if (kind === 'week5') {
    body.off_weekdays = $$(`#${prefix}-wd input:checked`, m).map(i => +i.value);
  } else if (kind === 'cycle') {
    body.cycle = $(`#${prefix}-cycle`, m)?.value.trim() || '3/3';
    body.anchor = $(`#${prefix}-anchor`, m)?.value || date;
  }
  return body;
}

async function datedActionModal(emp, kind) {
  const started = authContextSnapshot();
  const titles = {
    position: 'Перевод на должность',
    block: 'Перевод между блоками графика',
    dismiss: 'Увольнение (деактивация)',
  };
  const today = todayISO();
  let groups = [];
  if (kind === 'block') {
    try { groups = await api('/api/group-choices'); } catch { groups = []; }
    if (!groups.length) groups = ['Смена 1', 'Смена 2', 'Пятидневка', 'Другие смены'].map(name => ({ name, kind: 'base', title: name, hint: '' }));
  }
  let values = [];
  if (kind === 'block') {
    try { values = (await api('/api/tabel-values', { silent: true })).values || []; } catch { values = []; }
  }
  if (!authContextIsCurrent(started)) return;
  openModal({
    title: titles[kind],
    subtitle: emp.full_name,
    wide: kind === 'block',
    body: kind === 'position' ? html`
      <label class="field"><span>Новая должность</span><input type="text" id="da-position" .value=${emp.position || ''}></label>
      <label class="field"><span>Дата перевода</span><input type="date" id="da-date" .value=${today}></label>
      <p class="hint">В истории должностей текущая запись закроется этой датой, новая откроется.</p>`
    : kind === 'block' ? html`
      <label class="field"><span>Новый блок графика</span><select id="da-group">
        ${groups.map(g => html`<option value=${g.name} ?selected=${emp.schedule_group === g.name}>${g.title || g.name}</option>`)}
      </select></label>
      <p class="hint" id="da-group-hint" style="margin-top:-4px"></p>
      <div id="da-pattern"></div>
      <label class="field" style="margin-top:8px"><span>Дата перевода</span><input type="date" id="da-date" .value=${today}></label>
      <p class="hint">В графике сотрудник будет виден в обоих блоках: дни до даты — неактивные в новом блоке,
      дни после — неактивные в старом. «Пятидневка» — у каждого свои выходные;
      «Другие смены» — индивидуальный график (3/3, 1/3, сутки через трое, «РРВВ» или вручную).</p>`
    : html`
      <label class="field"><span>Дата увольнения (последний рабочий день)</span><input type="date" id="da-date" .value=${today}></label>
      <p class="hint">Сотрудник станет неактивным и не сможет войти; вся история (табель, отметки, документы) сохранится.
      В графике дни после этой даты станут неактивными. Принять обратно можно из карточки — «Принять обратно».</p>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Провести</button>`,
    onMount(m) {
      let blockKind = 'base';
      if (kind === 'block') {
        const sel = m.querySelector('#da-group');
        const hint = m.querySelector('#da-group-hint');
        const host = m.querySelector('#da-pattern');
        const drawPattern = () => {
          const g = groups.find(x => x.name === sel.value) || {};
          blockKind = g.kind || 'base';
          hint.textContent = g.hint || '';
          render(patternFields('da', blockKind, values, today), host);
        };
        sel.onchange = drawPattern;
        drawPattern();
      }
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        const date = $('#da-date', m).value || today;
        try {
          if (kind === 'position') {
            await api(`/api/employees/${emp.id}/position-change`, { method: 'POST',
              body: { position: $('#da-position', m).value.trim(), date } });
          } else if (kind === 'block') {
            const body = { group: $('#da-group', m).value, date, ...collectPatternFields(m, 'da', blockKind, date) };
            await api(`/api/employees/${emp.id}/block-change`, { method: 'POST', body });
          } else {
            await api(`/api/employees/${emp.id}/dismiss`, { method: 'POST', body: { date } });
          }
          closeModal();
          toast('Проведено: ' + titles[kind].toLowerCase() + ' с ' + dateRu(date), 'ok');
          await refreshAfterEmployeeChange();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ── повторный приём уволенного сотрудника с произвольной даты ── */
async function rehireModal(emp) {
  const started = authContextSnapshot();
  const today = todayISO();
  let groups = [];
  try { groups = await api('/api/group-choices'); } catch { groups = []; }
  /* «Значение рабочего дня» — из /api/tabel-values (код + окно CFG-WINDOWS,
     форма {value,title,start_hm,end_hm}), как в модалке перевода блока (da).
     Раньше сюда передавали workShifts (словарь типов смен) — селектор рисовал
     пустые option «undefined · undefined». */
  let values = [];
  try { values = (await api('/api/tabel-values', { silent: true })).values || []; } catch { values = []; }
  if (!authContextIsCurrent(started)) return;
  openModal({
    title: 'Принять обратно',
    subtitle: `${emp.full_name}${emp.dismissed_at ? ' · уволен(а), последний рабочий день ' + dateRu(emp.dismissed_at) : ''}`,
    wide: true,
    body: html`
      <label class="field"><span>Дата приёма (первый рабочий день)</span><input type="date" id="rh-date" .value=${today}></label>
      <label class="field"><span>Должность (пусто — оставить прежнюю)</span>
        <input type="text" id="rh-position" .value=${''} placeholder=${emp.position || ''}></label>
      ${groups.length ? html`
      <label class="field"><span>Блок графика (пусто — оставить прежний «${emp.schedule_group || '—'}»)</span>
        <select id="rh-group">
          <option value="">— оставить прежний —</option>
          ${groups.map(g => html`<option value=${g.name}>${g.title || g.name}</option>`)}
        </select></label>
      <div id="rh-pattern"></div>` : nothing}
      <p class="hint">В графике будут видны смены до увольнения, неактивные дни между периодами
      и активные дни после нового приёма. Вся прошлая история (табель, отметки, документы) сохраняется,
      банк часов продолжается с прежнего значения.</p>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Принять на работу</button>`,
    onMount(m) {
      const sel = m.querySelector('#rh-group');
      const host = m.querySelector('#rh-pattern');
      let kind = '';
      if (sel) sel.onchange = () => {
        const g = groups.find(x => x.name === sel.value) || {};
        kind = sel.value ? (g.kind || 'base') : '';
        render(sel.value ? patternFields('rh', kind, values, today) : nothing, host);
      };
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        const date = $('#rh-date', m).value || today;
        const body = { date, position: $('#rh-position', m).value.trim() };
        if (sel && sel.value) {
          body.group = sel.value;
          Object.assign(body, collectPatternFields(m, 'rh', kind || 'base', date));
        }
        try {
          await api(`/api/employees/${emp.id}/rehire`, { method: 'POST', body });
          closeModal();
          toast(`Сотрудник принят обратно с ${dateRu(date)}`, 'ok');
          await refreshAfterEmployeeChange();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* ── ручная корректировка банка часов (+/−) с причиной и историей ── */
async function bankAdjustModal(emp, history) {
  const today = todayISO();
  const bankNow = history?.bank_now ?? 0;
  openModal({
    title: 'Корректировка банка часов',
    subtitle: `${emp.full_name} · сейчас ${bankNow >= 0 ? '+' : ''}${hours(bankNow)} ч`,
    wide: true,
    body: html`
      <div class="grid-2">
        <label class="field"><span>Часы (+ добавить / − списать)</span>
          <input type="number" step="0.5" id="ba-hours" placeholder="например 4 или -8"></label>
        <label class="field"><span>Действует с даты</span><input type="date" id="ba-date" .value=${today}></label>
      </div>
      <label class="field"><span>Причина (обязательно — попадёт в историю)</span>
        <input type="text" id="ba-note" placeholder="Например: исправление потерянных отметок 12.09 по служебной записке №3"></label>
      <div class="opt-group-title">История корректировок</div>
      <div id="ba-list">${(history?.bank_adjustments || []).length ? history.bank_adjustments.map(a => html`<div style="font-size:13.5px;padding:3px 0;display:flex;gap:8px;align-items:center">
        <b class=${a.hours >= 0 ? 'balance-pos' : 'balance-neg'}>${a.hours >= 0 ? '+' : ''}${hours(a.hours)} ч</b>
        <span>с ${dateRu(a.date)} — ${a.note} <small class="muted">(${a.author})</small></span>
        <button class="btn btn-sm btn-ghost" data-del-adj=${a.id} title="Удалить корректировку" @click=${() => delAdjust(a)}>✕</button></div>`)
        : html`<div class="hint">пока не было</div>`}</div>
      <p class="hint">Корректировка — право «Корректировка банка часов» (по умолчанию администратор и менеджер);
      автор, причина и время сохраняются в журнале аудита. Банк = итог последнего закрытого периода ± корректировки.</p>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Закрыть</button>
             <button class="btn btn-primary" data-ok>Применить корректировку</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        const h = parseFloat($('#ba-hours', m).value);
        if (!h) return toast('Укажите часы — ненулевые, со знаком + или −', 'warn');
        const note = $('#ba-note', m).value.trim();
        if (!note) return toast('Укажите причину корректировки', 'warn');
        try {
          const r = await api(`/api/employees/${emp.id}/bank-adjust`, { method: 'POST',
            body: { hours: h, date: $('#ba-date', m).value || today, note } });
          toast(`Применено ${h >= 0 ? '+' : ''}${hours(h)} ч · банк теперь ${hours(r.bank_now)} ч`, 'ok');
          reopen();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
  async function reopen() {
    const h = await api(`/api/employees/${emp.id}/history`);
    closeModal(); bankAdjustModal(emp, h);
  }
  async function delAdjust(a) {
    if (!confirm('Удалить эту корректировку банка?')) return;
    try { await api(`/api/employees/${emp.id}/bank-adjustments/${a.id}`, { method: 'DELETE' });
      toast('Корректировка удалена', 'ok'); reopen();
    } catch (e) { toast(e.message, 'err'); }
  }
}

async function employeeModal(emp) {
  const started = authContextSnapshot();
  let groups = [];
  try { groups = await api('/api/group-choices'); } catch { groups = []; }
  const groupList = (groups.length ? groups : ['Смена 1', 'Смена 2', 'Пятидневка', 'Другие смены'].map(name => ({ name })))
    .map(g => typeof g === 'string' ? { name: g, title: g } : g);
  let departments = [];
  try { departments = await api('/api/departments'); } catch { departments = []; }
  try { state.subdivisions = await api('/api/subdivisions', { silent: true }); }
  catch { state.subdivisions = state.subdivisions || []; }
  if (!authContextIsCurrent(started)) return;
  const isNew = !emp;
  // Роли, которые текущий пользователь вправе назначать, — с сервера (иерархия ролей там же,
  // ADR-0011), от младшей к старшей; новому сотруднику по умолчанию — «Сотрудник».
  // Текущая роль сотрудника видна всегда: менять её запретит сервер, если нельзя.
  const roleOptions = [...new Set([...(state.assignableRoles || []).slice().reverse(),
                                   ...(emp?.role ? [emp.role] : [])])];
  /* контакты близких — список в памяти окна; строки рисуются из него */
  const rows = (emp?.contacts?.length ? emp.contacts
    : (emp?.emergency_name ? [{ name: emp.emergency_name, phone: emp.emergency_phone, relation: '' }] : []))
    .map(c => ({ name: c.name || '', phone: c.phone || '', relation: c.relation || '' }));
  const drawContacts = () => render(html`${rows.map((c, i) => html`
    <div class="grid-2 contact-row" style="grid-template-columns:1fr 1fr 1fr auto;gap:8px;margin-bottom:6px">
      <input class="c-name" type="text" placeholder="Имя, например Иванова М. И." .value=${c.name} @input=${e => { c.name = e.target.value; }}>
      <input class="c-phone" type="text" placeholder="+7 900 000-00-00" .value=${c.phone} @input=${e => { c.phone = e.target.value; }}>
      <input class="c-rel" type="text" placeholder="кем приходится (жена, мать…)" .value=${c.relation} @input=${e => { c.relation = e.target.value; }}>
      <button class="btn btn-sm btn-danger c-del" type="button" title="Убрать контакт" @click=${() => { rows.splice(i, 1); drawContacts(); }}>✕</button>
    </div>`)}`, mount($('#e-contacts')));
  openModal({
    title: isNew ? 'Новый сотрудник' : 'Изменить: ' + emp.full_name, wide: true,
    subtitle: isNew ? 'Логин создастся автоматически из ФИО' : 'Редактор карточки',
    body: html`
      <div class="grid-2">
        <label class="field"><span>ФИО *</span><input type="text" id="e-full" .value=${emp?.full_name || ''} placeholder="Иванов Иван Иванович"></label>
        <label class="field"><span>Кратко (для сетки)</span><input type="text" id="e-short" .value=${emp?.short_name || ''} placeholder="Иванов И.И."></label>
        <div class="field" style="grid-column:1/-1"><span>ФИО в родительном падеже — для документов («от …»)</span>
          <div style="display:flex;gap:8px;align-items:center">
            <input type="text" id="e-full-gen" .value=${emp?.full_name_genitive || ''}
              placeholder=${emp?.full_name_genitive_hint || 'Федоренко Николая Сергеевича'} style="flex:1">
            <button class="btn btn-sm" id="e-gen-suggest" type="button"
              title="Предложить вариант по ФИО (проверьте окончание фамилии)">Подсказать</button>
          </div>
          <div class="hint" style="margin-top:2px">Если поле пустое, система подставит сюда автоматический вариант (показан как подсказка в поле).</div>
        </div>
        <label class="field"><span>Должность</span><input type="text" id="e-pos" .value=${emp?.position || ''} placeholder="Батлер"></label>
        <label class="field"><span>Табельный номер</span><input type="text" id="e-tab" .value=${emp?.tab_number || ''} placeholder="017"></label>
        <label class="field"><span>Гражданство</span><input type="text" id="e-nat" .value=${emp?.nationality || ''} placeholder="Российская Федерация"></label>
        <label class="field"><span>Подразделение / служба (для документов)</span><select id="e-subdiv">
          <option value="">— не указано —</option>
          ${(state.subdivisions || []).map(s => html`<option value=${s.name} ?selected=${emp?.subdivision === s.name}>${s.name}</option>`)}
          ${emp?.subdivision && !(state.subdivisions || []).some(s => s.name === emp.subdivision)
            ? html`<option value=${emp.subdivision} selected>${emp.subdivision}</option>` : nothing}
        </select><div class="hint" style="margin-top:2px">Справочник — в «Настройки → Департаменты и службы».</div></label>
        <label class="field"><span>Департамент</span><select id="e-dep">
          <option value="">— не выбран —</option>
          ${departments.map(d => html`<option value=${d.id} ?selected=${emp?.department_id === d.id}>${d.name}</option>`)}
        </select></label>
        <label class="field"><span>Дата приёма на работу</span><input type="date" id="e-hired" .value=${emp?.hired_at || ''}></label>
        <label class="field"><span>Телефон</span><input type="text" id="e-phone" .value=${emp?.phone || ''}></label>
        <label class="field"><span>Рабочая почта</span><input type="email" id="e-email" .value=${emp?.email || ''} placeholder="i.ivanov@butler.service"></label>
        <label class="field"><span>Логин Telegram</span><input type="text" id="e-tg" .value=${emp?.telegram || ''} placeholder="@ivanov"></label>
        <label class="field"><span>Блок графика (в сетке)</span><select id="e-group">
          <option value="">— не задано —</option>
          ${groupList.map(g => html`<option value=${g.name} ?selected=${emp?.schedule_group === g.name}>${g.title || g.name}</option>`)}
        </select></label>
        <label class="field"><span>Роль в системе</span><select id="e-role">
          ${roleOptions.map(r => html`<option value=${r} ?selected=${(emp?.role || 'employee') === r}>${roleTitle(r)}</option>`)}
        </select></label>
        <label class="field"><span>Логин</span><input type="text" id="e-login" .value=${emp?.username || ''} placeholder="создастся автоматически"></label>
      </div>
      <div class="opt-group-title">Контакты близких (экстренно) — можно несколько</div>
      <div id="e-contacts"></div>
      <button class="btn btn-sm" id="e-add-contact" type="button">+ Добавить контакт</button>
      <div class="field" style="margin-top:14px"><span>Цвет должности (для сетки и строк табеля)</span>
        <div class="color-swatches" id="e-colors">
          ${POSITION_COLORS.map(pc => html`
            <label title=${pc.t} style=${`background:${pc.c}`}>
              <input type="radio" name="e-color" value=${pc.c} .checked=${(emp?.group_color || '#8a94a6') === pc.c}>
            </label>`)}
        </div>
      </div>
      <div class="grid-2">
        <label class="field"><span>${isNew ? 'Пароль (пусто — сгенерируется случайный)' : 'Новый пароль (оставьте пустым, чтобы не менять)'}</span>
          <input type="password" id="e-pass" placeholder="••••••••" autocomplete="new-password"></label>
        <label class="field"><span>Подтверждение пароля</span>
          <input type="password" id="e-pass2" placeholder="••••••••" autocomplete="new-password"></label>
      </div>`,
    footer: html`
      <div style="flex:1"></div>
      <button class="btn btn-ghost" data-cancel>Отмена</button>
      <button class="btn btn-primary" data-save>${isNew ? 'Создать' : 'Сохранить'}</button>`,
    onMount(m) {
      drawContacts();
      m.querySelector('#e-add-contact').onclick = () => { rows.push({ name: '', phone: '', relation: '' }); drawContacts(); };
      m.querySelector('#e-gen-suggest').onclick = async () => {
        const fio = $('#e-full', m).value.trim();
        if (!fio) return toast('Сначала заполните ФИО', 'warn');
        try {
          const r = await api('/api/employees/suggest-genitive', { method: 'POST', body: { full_name: fio } });
          $('#e-full-gen', m).value = r.genitive || '';
          toast('Проверьте окончание фамилии: автоподстановка может ошибаться', 'ok');
        } catch (e) { toast(e.message, 'err'); }
      };
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        const pass = m.querySelector('#e-pass').value;
        const pass2 = m.querySelector('#e-pass2').value;
        if (pass && pass !== pass2) return toast('Пароли не совпадают', 'warn');
        const color = m.querySelector('#e-colors input:checked')?.value || '#8a94a6';
        const contactList = rows.map(c => ({ name: c.name.trim(), phone: c.phone.trim(), relation: c.relation.trim() }))
          .filter(c => c.name);
        const body = {
          full_name: $('#e-full', m).value.trim(), short_name: $('#e-short', m).value.trim(),
          full_name_genitive: $('#e-full-gen', m).value.trim(),
          position: $('#e-pos', m).value.trim(), phone: $('#e-phone', m).value.trim(),
          tab_number: $('#e-tab', m).value.trim(), hired_at: $('#e-hired', m).value || null,
          nationality: $('#e-nat', m).value.trim(), subdivision: $('#e-subdiv', m).value.trim(),
          department_id: $('#e-dep', m).value ? +$('#e-dep', m).value : null,
          email: $('#e-email', m).value.trim(), telegram: $('#e-tg', m).value.trim(),
          emergency_name: contactList[0]?.name || '', emergency_phone: contactList[0]?.phone || '',
          contacts: contactList,
          schedule_group: $('#e-group', m).value, group_color: color,
          username: $('#e-login', m).value.trim() || null, password: pass || null,
          role: $('#e-role', m).value,
        };
        if (!body.full_name) return toast('Укажите ФИО', 'warn');
        try {
          const res = isNew
            ? await api('/api/employees', { method: 'POST', body })
            : await api(`/api/employees/${emp.id}`, { method: 'PUT', body });
          closeModal();
          if (isNew && res.initial_password) initialPasswordModal(res);
          else toast(isNew ? `Создан: ${res.full_name}, логин ${res.username}` : 'Изменения сохранены', 'ok');
          await refreshAfterEmployeeChange();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* Сгенерированный пароль новой учётки — один раз и до закрытия кнопкой: в БД только хеш,
   второй раз его не узнать (раньше — тост на 5 секунд). Введённый администратором пароль
   сервер не возвращает. */
export function initialPasswordModal(res) {
  openModal({
    title: 'Учётная запись создана',
    subtitle: 'Пароль показывается один раз — передайте его сотруднику',
    body: html`<div class="kv"><span class="k">Сотрудник</span><span class="v">${res.full_name}</span></div>
      <div class="kv"><span class="k">Логин</span><span class="v"><code>${res.username}</code></span></div>
      <div class="kv"><span class="k">Пароль</span><span class="v"><code id="ip-pass">${res.initial_password}</code></span></div>`,
    footer: html`<button class="btn btn-ghost" data-copy>Скопировать пароль</button>
      <button class="btn btn-primary" data-done>Готово, передал</button>`,
    onMount(m) {
      m.querySelector('[data-done]').onclick = closeModal;
      m.querySelector('[data-copy]').onclick = async () => {
        try { await navigator.clipboard.writeText(res.initial_password); toast('Пароль скопирован', 'ok'); }
        catch { toast('Не удалось скопировать — выделите пароль и скопируйте вручную', 'warn'); }
      };
    },
  });
}
