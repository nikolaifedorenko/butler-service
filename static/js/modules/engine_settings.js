'use strict';

/* ══════════════════════════════════════════════════════════════════
   СПРАВОЧНИКИ ДВИЖКА v7.1 (в разделе «Настройки»): CFG-DAY-CODES, CFG-WINDOWS,
   CFG-CATEGORIES, CFG-WEIGHTS, CFG-CASCADE, CFG-PLACEMENT, CFG-GROUPS,
   CFG-LIMITS, гранулярность периода + модификаторы CFG-MODIFIERS
   Модуль на lit-html (ADR-0013, раздел 7).
   ══════════════════════════════════════════════════════════════════ */

import { can } from '../app.js';
import { $, api, dateRu, MONTHS, state, toast } from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';

const V4_MOD_TITLES = {
  double_overtime: 'Двойные переработки', pays_overtime: 'Оплачиваются ли переработки',
  plan_equals_fact: 'План=Факт', counts_in_ut: 'Учитываются ли часы в УТ',
};

export async function renderEngineSettings(host) {
  if (!host) return;
  let data, mods;
  try {
    [data, mods] = await Promise.all([api('/api/engine-settings'),
      api(`/api/engine-settings/modifiers?year=${state.year}&month=${state.month}`)]);
  } catch (e) { render(html`<div class="empty">${e.message}</div>`, mount(host)); return; }
  const p = data.active.payload;
  state.enginePayload = p;      // панель «Правила оплаты переработок» сохраняет новую версию отсюда
  const edit = can('settings.edit');
  const first = `${state.year}-${String(state.month).padStart(2, '0')}-01`;
  const empName = id => (state.employees.find(e => e.id === id) || {}).short_name || `#${id}`;
  const hm = m => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
  const winList = Object.entries(p.windows || {})
    .map(([k, w]) => `${k} = ${hm(w.start_minute)}–${hm(w.end_minute)}`).join('; ');
  const groups = Array.isArray(p.groups) ? p.groups : Object.keys(p.groups || {});
  const again = () => renderEngineSettings(host);

  const save = async () => {
    let payload;
    try { payload = JSON.parse($('#es-json', host).value); } catch (e) { toast('JSON с ошибкой: ' + e.message, 'err'); return; }
    try {
      await api('/api/engine-settings', { method: 'PUT', body: { valid_from: $('#es-from', host).value, payload,
        note: $('#es-note', host).value, base_version_id: data.latest_id ?? null } });
      toast('Новая версия справочников сохранена', 'ok'); again();
    } catch (e) { toast(e.message, 'err'); }
  };
  const addMod = async () => {
    const scope = $('#md-scope', host).value, day = $('#md-date', host).value;
    const body = { name: $('#md-name', host).value, value: $('#md-value', host).value, note: $('#md-note', host).value,
      date: day || null, period_start: day ? null : first,
      employee_id: scope.startsWith('e:') ? +scope.slice(2) : null, group: scope.startsWith('g:') ? scope.slice(2) : '' };
    try { await api('/api/engine-settings/modifiers', { method: 'POST', body }); toast('Модификатор добавлен', 'ok'); again(); }
    catch (e) { toast(e.message, 'err'); }
  };
  const delMod = async m => {
    try { await api(`/api/engine-settings/modifiers/${m.id}`, { method: 'DELETE' }); again(); }
    catch (e) { toast(e.message, 'err'); }
  };
  const groupName = g => (typeof g === 'string' ? g : g.name);

  render(html`
    <h3 class="panel-title">Справочники движка v7.1 (CFG-*)</h3>
    <div class="stat-grid">
      <div class="stat"><div class="k">Шаг расчёта</div><div class="v">${p.step_minutes} мин</div></div>
      <div class="stat"><div class="k">Лимит опоздания</div><div class="v">${p.late_limit_minutes} мин</div></div>
      <div class="stat"><div class="k">Период</div><div class="v" style="font-size:16px">${p.period_granularity === 'half_month' ? 'полмесяца' : 'месяц'}</div></div>
      <div class="stat"><div class="k">Действует с</div><div class="v" style="font-size:16px">${data.active.valid_from ? dateRu(data.active.valid_from) : 'по умолчанию'}</div></div>
    </div>
    <p class="hint" style="margin-top:-6px">Каскад (CFG-CASCADE): банк → ${p.cascade_order.join(' → ')}.
      Порядок размещения (CFG-PLACEMENT): ${p.placement_order.join(' → ')}.
      Веса (CFG-WEIGHTS): ${Object.entries(p.weights).map(([k, w]) => `${k}=${w}`).join(', ')}.
      Группы (CFG-GROUPS): ${groups.join(', ')}.</p>
    <p class="hint">Окна (CFG-WINDOWS): ${winList}. План карточки = длина окна; недостача и
      ёмкость переносов — от окна. Информационный план строки Табеля может быть меньше
      длины окна (зарплатная норма, например обед).</p>
    <details><summary>Редактировать справочники (JSON)</summary>
      <textarea id="es-json" style="width:100%;min-height:320px;font-family:monospace;font-size:12px" ?readonly=${!edit} .value=${JSON.stringify(p, null, 2)}></textarea>
      ${edit ? html`<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:end;margin-top:8px">
        <label class="field" style="margin:0"><span>Действует с (1 или 16 число)</span><input type="date" id="es-from" .value=${first}></label>
        <label class="field" style="margin:0;flex:1"><span>Комментарий</span><input type="text" id="es-note" placeholder="что и почему меняем"></label>
        <button class="btn btn-primary" id="es-save" @click=${save}>Сохранить новую версию</button></div>
        <p class="hint">Перед сохранением конфигурация проверяется правилами CHK-* уровня 1;
          все нарушения выводятся разом. Шаг и гранулярность меняются только с границы периода.
          Закрытые периоды не пересчитываются автоматически.</p>` : nothing}
    </details>
    <details style="margin-top:8px"><summary>История версий (${data.versions.length})</summary>
      ${data.versions.map(v => html`<div class="audit-item"><span class="ts">${dateRu(v.valid_from)}</span><span class="ac">#${v.id}</span>
        <span style="color:var(--muted)">${v.created_by} · ${v.note}</span></div>`)}</details>
    <h3 class="panel-title" style="margin-top:16px">Модификаторы дня (CFG-MODIFIERS) · ${MONTHS[state.month - 1]} ${state.year}</h3>
    <p class="hint" style="margin-top:-6px">Дни двойной оплаты и ВИП-гости тоже действуют как «Двойные переработки».
      Приоритет: сотрудник+день → сотрудник+период → группа+день → группа+период → все+день → все+период → глобальный дефолт.
      «План=Факт = Авто» разрешается в «Да» только колонкой кода (стартово — у «К»).
      Две записи одного уровня на один день — конфликт конфигурации.</p>
    <div class="table-wrap" tabindex="0"><table class="data"><thead><tr><th>Модификатор</th><th>Значение</th><th>Кому</th><th>Когда</th><th>Комментарий</th><th></th></tr></thead><tbody>
      ${mods.length ? mods.map(m => html`<tr><td>${V4_MOD_TITLES[m.name] || m.name}</td><td>${m.value === '1' ? 'Да' : (m.value === '0' ? 'Нет' : 'Авто')}</td>
        <td>${m.employee_id ? empName(m.employee_id) : (m.group ? 'группа «' + m.group + '»' : 'все')}</td>
        <td>${m.date ? dateRu(m.date) : 'весь период'}</td><td>${m.note}</td>
        <td>${edit ? html`<button class="btn btn-sm btn-ghost" data-mod-del=${m.id} @click=${() => delMod(m)}>✕</button>` : nothing}</td></tr>`)
        : html`<tr><td colspan="6" class="empty">Нет модификаторов в этом месяце</td></tr>`}
    </tbody></table></div>
    ${edit ? html`<div class="v4-filters" style="margin-top:8px">
      <label class="field"><span>Модификатор</span><select id="md-name">${data.modifier_names.map(n => html`<option value=${n.name}>${n.title}</option>`)}</select></label>
      <label class="field"><span>Значение</span><select id="md-value"><option value="1">Да</option><option value="0">Нет</option><option value="auto">Авто (План=Факт)</option></select></label>
      <label class="field"><span>Кому</span><select id="md-scope"><option value="all">все</option>
        ${groups.map(g => html`<option value=${`g:${groupName(g)}`}>группа «${groupName(g)}»</option>`)}
        ${state.employees.map(e => html`<option value=${`e:${e.id}`}>${e.short_name}</option>`)}</select></label>
      <label class="field"><span>День (пусто — весь период)</span><input type="date" id="md-date"></label>
      <label class="field"><span>Комментарий</span><input type="text" id="md-note"></label>
      <button class="btn" id="md-add" @click=${addMod}>Добавить</button></div>` : nothing}`, mount(host));
}
