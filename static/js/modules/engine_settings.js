'use strict';

/* ══════════════════════════════════════════════════════════════════
   СПРАВОЧНИКИ ДВИЖКА v7.1 (в разделе «Настройки»): CFG-DAY-CODES, CFG-WINDOWS,
   CFG-CATEGORIES, CFG-WEIGHTS, CFG-CASCADE, CFG-PLACEMENT, CFG-GROUPS,
   CFG-LIMITS, гранулярность периода + модификаторы CFG-MODIFIERS
   ══════════════════════════════════════════════════════════════════ */
const V4_MOD_TITLES = {
  double_overtime: 'Двойные переработки', pays_overtime: 'Оплачиваются ли переработки',
  plan_equals_fact: 'План=Факт', counts_in_ut: 'Учитываются ли часы в УТ',
};

async function renderEngineSettings(host) {
  if (!host) return;
  let data, mods;
  try {
    [data, mods] = await Promise.all([api('/api/engine-settings'),
      api(`/api/engine-settings/modifiers?year=${state.year}&month=${state.month}`)]);
  } catch (e) { host.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  const p = data.active.payload;
  state.enginePayload = p;      // панель «Правила оплаты переработок» сохраняет новую версию отсюда

  const edit = can('settings.edit');
  const first = `${state.year}-${String(state.month).padStart(2, '0')}-01`;
  const empName = id => (state.employees.find(e => e.id === id) || {}).short_name || `#${id}`;
  const hm = m => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
  const winList = Object.entries(p.windows || {})
    .map(([k, w]) => `${esc(k)} = ${hm(w.start_minute)}–${hm(w.end_minute)}`).join('; ');
  const groups = Array.isArray(p.groups) ? p.groups : Object.keys(p.groups || {});
  host.innerHTML = `
    <h3 class="panel-title">Справочники движка v7.1 (CFG-*)</h3>
    <div class="stat-grid">
      <div class="stat"><div class="k">Шаг расчёта</div><div class="v">${p.step_minutes} мин</div></div>
      <div class="stat"><div class="k">Лимит опоздания</div><div class="v">${p.late_limit_minutes} мин</div></div>
      <div class="stat"><div class="k">Период</div><div class="v" style="font-size:16px">${p.period_granularity === 'half_month' ? 'полмесяца' : 'месяц'}</div></div>
      <div class="stat"><div class="k">Действует с</div><div class="v" style="font-size:16px">${data.active.valid_from ? dateRu(data.active.valid_from) : 'по умолчанию'}</div></div>
    </div>
    <p class="hint" style="margin-top:-6px">Каскад (CFG-CASCADE): банк → ${p.cascade_order.map(esc).join(' → ')}.
      Порядок размещения (CFG-PLACEMENT): ${p.placement_order.map(esc).join(' → ')}.
      Веса (CFG-WEIGHTS): ${Object.entries(p.weights).map(([k, w]) => `${esc(k)}=${w}`).join(', ')}.
      Группы (CFG-GROUPS): ${groups.map(esc).join(', ')}.</p>
    <p class="hint">Окна (CFG-WINDOWS): ${winList}. План карточки = длина окна; недостача и
      ёмкость переносов — от окна. Информационный план строки Табеля может быть меньше
      длины окна (зарплатная норма, например обед).</p>
    <details><summary>Редактировать справочники (JSON)</summary>
      <textarea id="es-json" style="width:100%;min-height:320px;font-family:monospace;font-size:12px" ${edit ? '' : 'readonly'}>${esc(JSON.stringify(p, null, 2))}</textarea>
      ${edit ? `<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:end;margin-top:8px">
        <label class="field" style="margin:0"><span>Действует с (1 или 16 число)</span><input type="date" id="es-from" value="${first}"></label>
        <!-- версия выбирается по дате НАЧАЛА периода: дата внутри месяца фактически
             означает «с первого числа следующего» (base_version(period.start)) -->
        <label class="field" style="margin:0;flex:1"><span>Комментарий</span><input type="text" id="es-note" placeholder="что и почему меняем"></label>
        <button class="btn btn-primary" id="es-save">Сохранить новую версию</button></div>
        <p class="hint">Перед сохранением конфигурация проверяется правилами CHK-* уровня 1;
          все нарушения выводятся разом. Шаг и гранулярность меняются только с границы периода.
          Закрытые периоды не пересчитываются автоматически.</p>` : ''}
    </details>
    <details style="margin-top:8px"><summary>История версий (${data.versions.length})</summary>
      ${data.versions.map(v => `<div class="audit-item"><span class="ts">${dateRu(v.valid_from)}</span><span class="ac">#${v.id}</span>
        <span style="color:var(--muted)">${esc(v.created_by)} · ${esc(v.note)}</span></div>`).join('')}</details>
    <h3 class="panel-title" style="margin-top:16px">Модификаторы дня (CFG-MODIFIERS) · ${MONTHS[state.month - 1]} ${state.year}</h3>
    <p class="hint" style="margin-top:-6px">Дни двойной оплаты и ВИП-гости тоже действуют как «Двойные переработки».
      Приоритет: сотрудник+день → сотрудник+период → группа+день → группа+период → все+день → все+период → глобальный дефолт.
      «План=Факт = Авто» разрешается в «Да» только колонкой кода (стартово — у «К»).
      Две записи одного уровня на один день — конфликт конфигурации.</p>
    <div class="table-wrap"><table class="data"><thead><tr><th>Модификатор</th><th>Значение</th><th>Кому</th><th>Когда</th><th>Комментарий</th><th></th></tr></thead><tbody>
      ${mods.map(m => `<tr><td>${esc(V4_MOD_TITLES[m.name] || m.name)}</td><td>${m.value === '1' ? 'Да' : (m.value === '0' ? 'Нет' : 'Авто')}</td>
        <td>${m.employee_id ? esc(empName(m.employee_id)) : (m.group ? 'группа «' + esc(m.group) + '»' : 'все')}</td>
        <td>${m.date ? dateRu(m.date) : 'весь период'}</td><td>${esc(m.note)}</td>
        <td>${edit ? `<button class="btn btn-sm btn-ghost" data-mod-del="${m.id}">✕</button>` : ''}</td></tr>`).join('') || '<tr><td colspan="6" class="empty">Нет модификаторов в этом месяце</td></tr>'}
    </tbody></table></div>
    ${edit ? `<div class="v4-filters" style="margin-top:8px">
      <label class="field"><span>Модификатор</span><select id="md-name">${data.modifier_names.map(n => `<option value="${n.name}">${esc(n.title)}</option>`).join('')}</select></label>
      <label class="field"><span>Значение</span><select id="md-value"><option value="1">Да</option><option value="0">Нет</option><option value="auto">Авто (План=Факт)</option></select></label>
      <label class="field"><span>Кому</span><select id="md-scope"><option value="all">все</option>
        ${groups.map(g => `<option value="g:${esc(typeof g === 'string' ? g : g.name)}">группа «${esc(typeof g === 'string' ? g : g.name)}»</option>`).join('')}
        ${state.employees.map(e => `<option value="e:${e.id}">${esc(e.short_name)}</option>`).join('')}</select></label>
      <label class="field"><span>День (пусто — весь период)</span><input type="date" id="md-date"></label>
      <label class="field"><span>Комментарий</span><input type="text" id="md-note"></label>
      <button class="btn" id="md-add">Добавить</button></div>` : ''}`;
  if (edit) {
    $('#es-save').onclick = async () => {
      let payload;
      try { payload = JSON.parse($('#es-json').value); } catch (e) { toast('JSON с ошибкой: ' + e.message, 'err'); return; }
      try { await api('/api/engine-settings', { method: 'PUT', body: { valid_from: $('#es-from').value, payload, note: $('#es-note').value, base_version_id: data.latest_id ?? null } });
        toast('Новая версия справочников сохранена', 'ok'); renderEngineSettings(host); } catch (e) { toast(e.message, 'err'); }
    };
    $('#md-add').onclick = async () => {
      const scope = $('#md-scope').value, day = $('#md-date').value;
      const body = { name: $('#md-name').value, value: $('#md-value').value, note: $('#md-note').value,
        date: day || null, period_start: day ? null : first,
        employee_id: scope.startsWith('e:') ? +scope.slice(2) : null, group: scope.startsWith('g:') ? scope.slice(2) : '' };
      try { await api('/api/engine-settings/modifiers', { method: 'POST', body }); toast('Модификатор добавлен', 'ok'); renderEngineSettings(host); }
      catch (e) { toast(e.message, 'err'); }
    };
    $$('[data-mod-del]', host).forEach(b => b.onclick = async () => {
      try { await api(`/api/engine-settings/modifiers/${b.dataset.modDel}`, { method: 'DELETE' }); renderEngineSettings(host); }
      catch (e) { toast(e.message, 'err'); }
    });
  }
}
