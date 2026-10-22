'use strict';
/* ══ СОТРУДНИКИ: список → карточка → редактор ══
   Вынесено из app.js (15.10.2026) без изменения логики: границы разделов —
   файлами (сборки намеренно нет, ADR-0008), общие функции — через глобальную
   область (реестр tools/js_globals.json, ESLint no-undef ловит пропуски). */

/* ══════════════════════════════════════════════════════════════════
   СОТРУДНИКИ: список → карточка → редактор
   ══════════════════════════════════════════════════════════════════ */
registerModule({ views: { employees: loadEmployees } });

async function loadEmployees() {
  const host = $('#view-employees');
  await loadDirectory();
  host.innerHTML = `
    <div class="page-head">
      <div><h2>Сотрудники</h2><div class="sub">Нажмите на строку, чтобы открыть карточку со всеми подробностями</div></div>
      <div class="spacer"></div>
      <button class="btn btn-primary btn-sm" id="e-add">+ Добавить сотрудника</button>
    </div>
    <div class="table-wrap">
      <table class="data responsive"><thead><tr>
        <th>Сотрудник</th><th>Должность</th><th>Блок графика</th><th>Статус</th><th></th>
      </tr></thead><tbody>
      ${state.employees.map(e => `<tr data-card="${e.id}" style="cursor:pointer">
        <td class="who" data-label="Сотрудник">
          <span class="dot-pos" style="display:inline-block;width:9px;height:9px;border-radius:3px;background:${cssColor(e.group_color)};margin-right:7px"></span>${esc(e.full_name)}
          ${e.telegram ? `<small>tg: ${esc(e.telegram)}</small>` : ''}</td>
        <td data-label="Должность">${esc(e.position || '—')}</td>
        <td data-label="Блок">${esc(e.schedule_group || '—')}</td>
        <td data-label="Статус">${e.deleted ? '<span class="badge muted">удалён (в истории)</span>'
          : e.dismissed_at ? `<span class="badge muted">уволен ${dateRu(e.dismissed_at)}</span>`
          : e.active ? '<span class="badge ok">работает</span>' : '<span class="badge muted">неактивен</span>'}</td>
        <td class="num"><span class="badge muted">карточка →</span></td>
      </tr>`).join('')}
      </tbody></table>
    </div>
    <p class="hint">Удаление скрывает сотрудника из списков и графика, но вся история (табель, отметки, аудит) сохраняется.</p>`;
  $('#e-add').onclick = () => employeeModal(null);
  $$('[data-card]', host).forEach(tr => tr.onclick = () =>
    employeeCard(state.employees.find(x => x.id === +tr.dataset.card)));
}

/* Вход в карточку по id из других разделов («Слой 0 Табель», «Слой 1 План/График»):
   открывается ТА ЖЕ карточка, что и по строке раздела «Сотрудники», — правки
   доступны прямо из сетки, без перехода в другой раздел. Право — employees.view
   (как у самого раздела и у GET /api/employees/{id}/history); без права вызывающий
   код даже не делает имя кликабельным, но проверяем и здесь (защита в глубину).
   Если сотрудника нет в кеше справочника (не загружался для этой роли либо он
   удалён и виден только в строках истории), список дозагружается с сервера. */
async function openEmployeeCard(empId) {
  if (!can('employees.view')) return;
  let emp = (state.employees || []).find(e => e.id === empId);
  if (!emp) {
    try {
      const all = await api('/api/employees?include_deleted=true', { silent: true });
      emp = all.find(e => e.id === empId);
    } catch (e) { toast(e.message, 'err'); return; }
  }
  if (!emp) return toast('Сотрудник не найден', 'err');
  await employeeCard(emp);
}

/* После изменений карточки освежаем справочник и ТЕКУЩИЙ раздел: карточка
   открывается не только из «Сотрудников», но и из Табеля/Графика — сетка за
   модалкой должна показать свежие ФИО, цвет и статус. */
async function refreshAfterEmployeeChange() {
  await loadDirectory();
  if (state.view === 'employees') loadEmployees();
  else navigate(state.view);
}

async function employeeCard(emp) {
  const history = await api(`/api/employees/${emp.id}/history`);
  const contacts = emp.contacts?.length ? emp.contacts
    : (emp.emergency_name ? [{ name: emp.emergency_name, phone: emp.emergency_phone, relation: '' }] : []);
  const canBank = can('employees.bank');   // право, а не роль: гранты и группы учитываются
  const bankNow = history.bank_now ?? 0;
  openModal({
    title: emp.full_name,
    subtitle: `${emp.position || 'должность не указана'} · ${emp.schedule_group || 'без блока'}`,
    wide: true,
    body: `
      <div class="grid-2">
        <div class="field"><span>Табельный номер</span><div style="font-weight:600">${esc(emp.tab_number || '—')}</div></div>
        <div class="field"><span>Дата приёма</span><div style="font-weight:600">${emp.hired_at ? dateRu(emp.hired_at) : '—'}</div></div>
        <div class="field"><span>Гражданство</span><div style="font-weight:600">${esc(emp.nationality || '—')}</div></div>
        <div class="field"><span>Подразделение / служба (для документов)</span><div style="font-weight:600">${esc(emp.subdivision || '—')}</div></div>
        <div class="field"><span>Департамент</span><div style="font-weight:600">${esc(emp.department || '—')}</div></div>
        <div class="field" style="grid-column:1/-1"><span>ФИО в родительном падеже (для документов)</span>
          <div style="font-weight:600">${esc(emp.full_name_genitive || emp.full_name_genitive_hint || '—')}${!emp.full_name_genitive && emp.full_name_genitive_hint ? ' <small class="muted">(подставляется автоматически)</small>' : ''}</div></div>
        <div class="field"><span>Телефон</span><div style="font-weight:600">${esc(emp.phone || '—')}</div></div>
        <div class="field"><span>Рабочая почта</span><div style="font-weight:600">${esc(emp.email || '—')}</div></div>
        <div class="field"><span>Telegram</span><div style="font-weight:600">${esc(emp.telegram || '—')}</div></div>
        <div class="field"><span>Логин / роль</span><div style="font-weight:600"><code>${esc(emp.username || '—')}</code> · ${esc(roleTitle(emp.role))}</div></div>
        <div class="field"><span>Банк часов (сейчас)</span><div class="${bankNow >= 0 ? 'balance-pos' : 'balance-neg'}" style="font-size:18px">${bankNow >= 0 ? '+' : ''}${hours(bankNow)} ч</div>
          <div class="hint" style="margin-top:2px">итог последнего закрытого периода ± корректировки</div></div>
        <div class="field"><span>Статус</span><div style="font-weight:600">${emp.deleted ? 'удалён (хранится в истории)'
          : emp.dismissed_at ? `уволен (последний рабочий день ${dateRu(emp.dismissed_at)})` : emp.active ? 'работает' : 'неактивен'}</div></div>
      </div>
      <div class="opt-group-title">Периоды работы (приём → увольнение → повторный приём)</div>
      ${(history.employment || []).map(h => `<div style="font-size:13.5px;padding:3px 0">
        ${dateRu(h.start)} — ${h.end ? dateRu(h.end) : 'настоящее время'}${h.current ? ' <span class="badge ok">работает</span>' : ''}${h.note ? ` <small class="muted">· ${esc(h.note)}</small>` : ''}</div>`).join('') || '<div class="hint">нет записей</div>'}
      <div class="opt-group-title">Контакты близких (экстренно)</div>
      ${contacts.length ? contacts.map(c => `<div style="font-size:13.5px;padding:3px 0">
        <b>${esc(c.name)}</b> · ${esc(c.phone || '—')}${c.relation ? ` · ${esc(c.relation)}` : ''}</div>`).join('')
        : '<div class="hint">не указаны</div>'}
      <div class="opt-group-title">История должностей</div>
      ${history.positions.map(h => `<div style="font-size:13.5px;padding:3px 0">
        ${esc(h.position)} — с ${dateRu(h.start)}${h.end ? ` по ${dateRu(h.end)}` : ' — по настоящее время'}</div>`).join('') || '<div class="hint">нет записей</div>'}
      <div class="opt-group-title">Блок и значение рабочего дня</div>
      <div style="font-size:14px;margin-bottom:6px"><b>Блок:</b> ${esc(emp.schedule_group || '—')} ·
        <b>значение:</b> ${esc(history.current_value || 'значение блока по умолчанию')}</div>
      <div class="opt-group-title">Блоки графика (переходы между сменами)</div>
      ${history.blocks.map(h => `<div style="font-size:13.5px;padding:3px 0">
        «${esc(h.group)}» — с ${dateRu(h.start)}${h.end ? ` по ${dateRu(h.end)}` : ' — по настоящее время'}${h.pattern_label ? ` <small class="muted">· ${esc(h.pattern_label)}</small>` : ''}</div>`).join('') || '<div class="hint">нет записей</div>'}
      <div class="opt-group-title">Ручные корректировки банка часов</div>
      ${(history.bank_adjustments || []).map(a => `<div style="font-size:13.5px;padding:3px 0">
        <b class="${a.hours >= 0 ? 'balance-pos' : 'balance-neg'}">${a.hours >= 0 ? '+' : ''}${hours(a.hours)} ч</b>
        с ${dateRu(a.date)} — ${esc(a.note)} <small class="muted">(${esc(a.author)})</small></div>`).join('') || '<div class="hint">корректировок не было</div>'}`,
    footer: `
      <button class="btn btn-danger" data-delete>Удалить</button>
      ${emp.dismissed_at || (!emp.active && !emp.deleted)
        ? '<button class="btn" data-rehire>Принять обратно</button>'
        : '<button class="btn btn-ghost" data-dismiss>Уволить</button>'}
      <div style="flex:1"></div>
      ${canBank ? '<button class="btn btn-ghost" data-bank>Корректировка банка</button>' : ''}
      <button class="btn btn-ghost" data-block>Перевод в блок</button>
      <button class="btn btn-ghost" data-pos>Перевод на должность</button>
      ${can('employees.impersonate') ? '<button class="btn btn-ghost" data-imp>Войти как сотрудник</button>' : ''}
      <button class="btn btn-primary" data-edit>Изменить</button>`,
    onMount(m) {
      m.querySelector('[data-edit]').onclick = () => { closeModal(); employeeModal(emp); };
      const impBtn = m.querySelector('[data-imp]');
      if (impBtn) impBtn.onclick = async () => {
        await api('/api/auth/impersonate', { method: 'POST', body: { employee_id: emp.id } });
        const me = await api('/api/auth/me');
        state.user = me.user; applyMe(me); renderUserChip(); closeModal();
        resetUserViewState(); navigate('me');
        toast('Вы смотрите интерфейс глазами сотрудника', 'warn');
      };
      m.querySelector('[data-pos]').onclick = () => { closeModal(); datedActionModal(emp, 'position'); };
      m.querySelector('[data-block]').onclick = () => { closeModal(); datedActionModal(emp, 'block'); };
      const dis = m.querySelector('[data-dismiss]');
      if (dis) dis.onclick = () => { closeModal(); datedActionModal(emp, 'dismiss'); };
      const reh = m.querySelector('[data-rehire]');
      if (reh) reh.onclick = () => { closeModal(); rehireModal(emp); };
      const bank = m.querySelector('[data-bank]');
      if (bank) bank.onclick = () => { closeModal(); bankAdjustModal(emp, history); };
      m.querySelector('[data-delete]').onclick = () => {
        closeModal();
        confirmDialog('Удалить сотрудника?',
          `${emp.full_name} исчезнет из списков и графика. Табель, отметки и аудит сохранятся в истории.`,
          async () => {
            await api(`/api/employees/${emp.id}/delete`, { method: 'POST' });
            toast('Сотрудник удалён из активных списков; история сохранена', 'ok');
            await refreshAfterEmployeeChange();
          }, 'Удалить');
      };
    },
  });
}

/* ── шаблоны блоков: пятидневка (свои выходные) или индивидуальный цикл (3/3, 1/3, custom:РРВВ) ── */
function patternFieldsHtml(prefix, kind, values, today) {
  /* Значение рабочего дня (18.10.2026): код и окно из CFG-WINDOWS; пусто — берётся
     значение блока из настроек объекта. Список значений — /api/tabel-values. */
  const valueField = `
    <label class="field" style="margin-top:8px"><span>Значение рабочего дня</span>
      <select id="${prefix}-value">
        <option value="">— значение блока по умолчанию —</option>
        ${(values || []).map(v => `<option value="${esc(v.value)}">${esc(v.value)} · ${esc(v.title)} · ${esc(v.start_hm)}–${esc(v.end_hm)}</option>`).join('')}
      </select></label>`;
  if (kind === 'week5') return `
    <div class="opt-group-title" style="margin-top:8px">Выходные дни этого сотрудника (пятидневка)</div>
    <div class="wd-picker" id="${prefix}-wd">
      ${WD_SHORT.map((w, i) => `<label><input type="checkbox" value="${i}" ${(i === 5 || i === 6) ? 'checked' : ''}>${w}</label>`).join('')}
    </div>
    ${valueField}
    <p class="hint" style="margin:2px 0 0">У каждого сотрудника пятидневки СВОИ выходные: например у начальника вс/пн —
      отметьте «вс» и «пн» (снимите «сб»). Значение рабочего дня — своё у каждого.</p>`;
  if (kind === 'cycle') return `
    <div class="grid-2" style="margin-top:8px">
      <label class="field"><span>Цикл</span><input type="text" id="${prefix}-cycle" value="3/3" placeholder="3/3, 1/3, 4/2 или custom:РРВВРВ"></label>
      <label class="field"><span>Опорная дата (начало цикла)</span><input type="date" id="${prefix}-anchor" value="${today}"></label>
    </div>
    ${valueField}
    <p class="hint" style="margin:2px 0 0">«Другие смены»: 3/3, 1/3, сутки через трое (окно 08:00–20:00 с явкой
      «Я 12») или произвольный цикл «custom:РРВВРВ» (Р — рабочий, В — выходной).</p>`;
  if (kind === 'manual') return '<p class="hint">График этого сотрудника заполняется вручную по ячейкам — автоматического шаблона нет.</p>';
  return `${valueField}
    <p class="hint" style="margin:2px 0 0">Блок считается базовым циклом объекта (Настройки → Базовый цикл);
      значение рабочего дня можно задать лично сотруднику.</p>`;
}

function collectPatternFields(prefix, kind, date) {
  const body = { kind };
  body.value = $(`#${prefix}-value`)?.value || '';
  if (kind === 'week5') {
    body.off_weekdays = $$(`#${prefix}-wd input:checked`).map(i => +i.value);
  } else if (kind === 'cycle') {
    body.cycle = $(`#${prefix}-cycle`)?.value.trim() || '3/3';
    body.anchor = $(`#${prefix}-anchor`)?.value || date;
  }
  return body;
}

async function datedActionModal(emp, kind) {
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
  openModal({
    title: titles[kind],
    subtitle: emp.full_name,
    wide: kind === 'block',
    body: kind === 'position' ? `
      <label class="field"><span>Новая должность</span><input type="text" id="da-position" value="${esc(emp.position || '')}"></label>
      <label class="field"><span>Дата перевода</span><input type="date" id="da-date" value="${today}"></label>
      <p class="hint">В истории должностей текущая запись закроется этой датой, новая откроется.</p>`
    : kind === 'block' ? `
      <label class="field"><span>Новый блок графика</span><select id="da-group">
        ${groups.map(g => `<option value="${esc(g.name)}" ${emp.schedule_group === g.name ? 'selected' : ''}>${esc(g.title || g.name)}</option>`).join('')}
      </select></label>
      <p class="hint" id="da-group-hint" style="margin-top:-4px"></p>
      <div id="da-pattern"></div>
      <label class="field" style="margin-top:8px"><span>Дата перевода</span><input type="date" id="da-date" value="${today}"></label>
      <p class="hint">В графике сотрудник будет виден в обоих блоках: дни до даты — неактивные в новом блоке,
      дни после — неактивные в старом. «Пятидневка» — у каждого свои выходные;
      «Другие смены» — индивидуальный график (3/3, 1/3, сутки через трое, «РРВВ» или вручную).</p>`
    : `
      <label class="field"><span>Дата увольнения (последний рабочий день)</span><input type="date" id="da-date" value="${today}"></label>
      <p class="hint">Сотрудник станет неактивным и не сможет войти; вся история (табель, отметки, документы) сохранится.
      В графике дни после этой даты станут неактивными. Принять обратно можно из карточки — «Принять обратно».</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Провести</button>`,
    onMount(m) {
      let blockKind = 'base';
      if (kind === 'block') {
        const sel = m.querySelector('#da-group');
        const hint = m.querySelector('#da-group-hint');
        const host = m.querySelector('#da-pattern');
        const renderPattern = () => {
          const g = groups.find(x => x.name === sel.value) || {};
          blockKind = g.kind || 'base';
          hint.textContent = g.hint || '';
          host.innerHTML = patternFieldsHtml('da', blockKind, values, today);
        };
        sel.onchange = renderPattern;
        renderPattern();
      }
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        const date = $('#da-date').value || today;
        try {
          if (kind === 'position') {
            await api(`/api/employees/${emp.id}/position-change`, { method: 'POST',
              body: { position: $('#da-position').value.trim(), date } });
          } else if (kind === 'block') {
            const body = { group: $('#da-group').value, date, ...collectPatternFields('da', blockKind, date) };
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
  const today = todayISO();
  let groups = [];
  try { groups = await api('/api/group-choices'); } catch { groups = []; }
  /* «Значение рабочего дня» — из /api/tabel-values (код + окно CFG-WINDOWS,
     форма {value,title,start_hm,end_hm}), как в модалке перевода блока (da):
     patternFieldsHtml ждёт именно их. Раньше сюда передавали workShifts
     (словарь типов смен) — селектор рисовал пустые option «undefined · undefined»
     (ревью 20.10.2026, P1-fe-2). */
  let values = [];
  try { values = (await api('/api/tabel-values', { silent: true })).values || []; } catch { values = []; }
  openModal({
    title: 'Принять обратно',
    subtitle: `${emp.full_name}${emp.dismissed_at ? ' · уволен(а), последний рабочий день ' + dateRu(emp.dismissed_at) : ''}`,
    wide: true,
    body: `
      <label class="field"><span>Дата приёма (первый рабочий день)</span><input type="date" id="rh-date" value="${today}"></label>
      <label class="field"><span>Должность (пусто — оставить прежнюю)</span>
        <input type="text" id="rh-position" value="" placeholder="${esc(emp.position || '')}"></label>
      ${groups.length ? `
      <label class="field"><span>Блок графика (пусто — оставить прежний «${esc(emp.schedule_group || '—')}»)</span>
        <select id="rh-group">
          <option value="">— оставить прежний —</option>
          ${groups.map(g => `<option value="${esc(g.name)}">${esc(g.title || g.name)}</option>`).join('')}
        </select></label>
      <div id="rh-pattern"></div>` : ''}
      <p class="hint">В графике будут видны смены до увольнения, неактивные дни между периодами
      и активные дни после нового приёма. Вся прошлая история (табель, отметки, документы) сохраняется,
      банк часов продолжается с прежнего значения.</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-primary" data-ok>Принять на работу</button>`,
    onMount(m) {
      const sel = m.querySelector('#rh-group');
      const host = m.querySelector('#rh-pattern');
      let kind = '';
      if (sel) sel.onchange = () => {
        const g = groups.find(x => x.name === sel.value) || {};
        kind = sel.value ? (g.kind || 'base') : '';
        host.innerHTML = sel.value ? patternFieldsHtml('rh', kind, values, today) : '';
      };
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = async () => {
        const date = $('#rh-date').value || today;
        const body = { date, position: $('#rh-position').value.trim() };
        if (sel && sel.value) {
          body.group = sel.value;
          Object.assign(body, collectPatternFields('rh', kind || 'base', date));
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
    body: `
      <div class="grid-2">
        <label class="field"><span>Часы (+ добавить / − списать)</span>
          <input type="number" step="0.5" id="ba-hours" placeholder="например 4 или -8"></label>
        <label class="field"><span>Действует с даты</span><input type="date" id="ba-date" value="${today}"></label>
      </div>
      <label class="field"><span>Причина (обязательно — попадёт в историю)</span>
        <input type="text" id="ba-note" placeholder="Например: исправление потерянных отметок 12.09 по служебной записке №3"></label>
      <div class="opt-group-title">История корректировок</div>
      <div id="ba-list">${(history?.bank_adjustments || []).map(a => `<div style="font-size:13.5px;padding:3px 0;display:flex;gap:8px;align-items:center">
        <b class="${a.hours >= 0 ? 'balance-pos' : 'balance-neg'}">${a.hours >= 0 ? '+' : ''}${hours(a.hours)} ч</b>
        <span>с ${dateRu(a.date)} — ${esc(a.note)} <small class="muted">(${esc(a.author)})</small></span>
        <button class="btn btn-sm btn-ghost" data-del-adj="${a.id}" title="Удалить корректировку">✕</button></div>`).join('') || '<div class="hint">пока не было</div>'}</div>
      <p class="hint">Корректировка — право «Корректировка банка часов» (по умолчанию администратор и менеджер);
      автор, причина и время сохраняются в журнале аудита. Банк = итог последнего закрытого периода ± корректировки.</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Закрыть</button>
             <button class="btn btn-primary" data-ok>Применить корректировку</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      const reopen = async () => {
        const h = await api(`/api/employees/${emp.id}/history`);
        closeModal(); bankAdjustModal(emp, h);
      };
      $$('[data-del-adj]', m).forEach(b => b.onclick = async () => {
        if (!confirm('Удалить эту корректировку банка?')) return;
        try { await api(`/api/employees/${emp.id}/bank-adjustments/${b.dataset.delAdj}`, { method: 'DELETE' });
          toast('Корректировка удалена', 'ok'); reopen();
        } catch (e) { toast(e.message, 'err'); }
      });
      m.querySelector('[data-ok]').onclick = async () => {
        const h = parseFloat($('#ba-hours').value);
        if (!h) return toast('Укажите часы — ненулевые, со знаком + или −', 'warn');
        const note = $('#ba-note').value.trim();
        if (!note) return toast('Укажите причину корректировки', 'warn');
        try {
          const r = await api(`/api/employees/${emp.id}/bank-adjust`, { method: 'POST',
            body: { hours: h, date: $('#ba-date').value || today, note } });
          toast(`Применено ${h >= 0 ? '+' : ''}${hours(h)} ч · банк теперь ${hours(r.bank_now)} ч`, 'ok');
          reopen();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

async function employeeModal(emp) {
  let groups = [];
  try { groups = await api('/api/group-choices'); } catch { groups = []; }
  const groupList = (groups.length ? groups : ['Смена 1', 'Смена 2', 'Пятидневка', 'Другие смены'].map(name => ({ name })))
    .map(g => typeof g === 'string' ? { name: g, title: g } : g);
  let departments = [];
  try { departments = await api('/api/departments'); } catch { departments = []; }
  try { state.subdivisions = await api('/api/subdivisions', { silent: true }); }
  catch { state.subdivisions = state.subdivisions || []; }
  const isNew = !emp;
  // Роли, которые текущий пользователь вправе назначать, — с сервера (иерархия ролей там же,
  // ADR-0011), от младшей к старшей; новому сотруднику по умолчанию — «Сотрудник».
  // Текущая роль сотрудника видна всегда: менять её запретит сервер, если нельзя.
  const roleOptions = [...new Set([...(state.assignableRoles || []).slice().reverse(),
                                   ...(emp?.role ? [emp.role] : [])])];
  const contacts = emp?.contacts?.length ? emp.contacts
    : (emp?.emergency_name ? [{ name: emp.emergency_name, phone: emp.emergency_phone, relation: '' }] : []);
  openModal({
    title: isNew ? 'Новый сотрудник' : 'Изменить: ' + emp.full_name, wide: true,
    subtitle: isNew ? 'Логин создастся автоматически из ФИО' : 'Редактор карточки',
    body: `
      <div class="grid-2">
        <label class="field"><span>ФИО *</span><input type="text" id="e-full" value="${esc(emp?.full_name || '')}" placeholder="Иванов Иван Иванович"></label>
        <label class="field"><span>Кратко (для сетки)</span><input type="text" id="e-short" value="${esc(emp?.short_name || '')}" placeholder="Иванов И.И."></label>
        <div class="field" style="grid-column:1/-1"><span>ФИО в родительном падеже — для документов («от …»)</span>
          <div style="display:flex;gap:8px;align-items:center">
            <input type="text" id="e-full-gen" value="${esc(emp?.full_name_genitive || '')}"
              placeholder="${esc(emp?.full_name_genitive_hint || 'Федоренко Николая Сергеевича')}" style="flex:1">
            <button class="btn btn-sm" id="e-gen-suggest" type="button"
              title="Предложить вариант по ФИО (проверьте окончание фамилии)">Подсказать</button>
          </div>
          <div class="hint" style="margin-top:2px">Если поле пустое, система подставит сюда автоматический вариант (показан как подсказка в поле).</div>
        </div>
        <label class="field"><span>Должность</span><input type="text" id="e-pos" value="${esc(emp?.position || '')}" placeholder="Батлер"></label>
        <label class="field"><span>Табельный номер</span><input type="text" id="e-tab" value="${esc(emp?.tab_number || '')}" placeholder="017"></label>
        <label class="field"><span>Гражданство</span><input type="text" id="e-nat" value="${esc(emp?.nationality || '')}" placeholder="Российская Федерация"></label>
        <label class="field"><span>Подразделение / служба (для документов)</span><select id="e-subdiv">
          <option value="">— не указано —</option>
          ${(state.subdivisions || []).map(s => `<option value="${esc(s.name)}" ${emp?.subdivision === s.name ? 'selected' : ''}>${esc(s.name)}</option>`).join('')}
          ${emp?.subdivision && !(state.subdivisions || []).some(s => s.name === emp.subdivision)
            ? `<option value="${esc(emp.subdivision)}" selected>${esc(emp.subdivision)}</option>` : ''}
        </select><div class="hint" style="margin-top:2px">Справочник — в «Настройки → Департаменты и службы».</div></label>
        <label class="field"><span>Департамент</span><select id="e-dep">
          <option value="">— не выбран —</option>
          ${departments.map(d => `<option value="${d.id}" ${emp?.department_id === d.id ? 'selected' : ''}>${esc(d.name)}</option>`).join('')}
        </select></label>
        <label class="field"><span>Дата приёма на работу</span><input type="date" id="e-hired" value="${esc(emp?.hired_at || '')}"></label>
        <label class="field"><span>Телефон</span><input type="text" id="e-phone" value="${esc(emp?.phone || '')}"></label>
        <label class="field"><span>Рабочая почта</span><input type="email" id="e-email" value="${esc(emp?.email || '')}" placeholder="i.ivanov@butler.service"></label>
        <label class="field"><span>Логин Telegram</span><input type="text" id="e-tg" value="${esc(emp?.telegram || '')}" placeholder="@ivanov"></label>
        <label class="field"><span>Блок графика (в сетке)</span><select id="e-group">
          <option value="">— не задано —</option>
          ${groupList.map(g => `<option value="${esc(g.name)}" ${emp?.schedule_group === g.name ? 'selected' : ''}>${esc(g.title || g.name)}</option>`).join('')}
        </select></label>
        <label class="field"><span>Роль в системе</span><select id="e-role">
          ${roleOptions.map(r => `<option value="${esc(r)}" ${(emp?.role || 'employee') === r ? 'selected' : ''}>${esc(roleTitle(r))}</option>`).join('')}
        </select></label>
        <label class="field"><span>Логин</span><input type="text" id="e-login" value="${esc(emp?.username || '')}" placeholder="создастся автоматически"></label>
      </div>
      <div class="opt-group-title">Контакты близких (экстренно) — можно несколько</div>
      <div id="e-contacts">
        ${contacts.map((c, i) => contactRow(c, i)).join('')}
      </div>
      <button class="btn btn-sm" id="e-add-contact" type="button">+ Добавить контакт</button>
      <div class="field" style="margin-top:14px"><span>Цвет должности (для сетки и строк табеля)</span>
        <div class="color-swatches" id="e-colors">
          ${POSITION_COLORS.map(pc => `
            <label title="${esc(pc.t)}" style="background:${pc.c}">
              <input type="radio" name="e-color" value="${pc.c}" ${(emp?.group_color || '#8a94a6') === pc.c ? 'checked' : ''}>
            </label>`).join('')}
        </div>
      </div>
      <div class="grid-2">
        <label class="field"><span>${isNew ? 'Пароль (пусто — сгенерируется случайный)' : 'Новый пароль (оставьте пустым, чтобы не менять)'}</span>
          <input type="password" id="e-pass" placeholder="••••••••" autocomplete="new-password"></label>
        <label class="field"><span>Подтверждение пароля</span>
          <input type="password" id="e-pass2" placeholder="••••••••" autocomplete="new-password"></label>
      </div>`,
    footer: `
      <div style="flex:1"></div>
      <button class="btn btn-ghost" data-cancel>Отмена</button>
      <button class="btn btn-primary" data-save>${isNew ? 'Создать' : 'Сохранить'}</button>`,
    onMount(m) {
      let ci = contacts.length;
      const host = m.querySelector('#e-contacts');
      m.querySelector('#e-add-contact').onclick = () => {
        host.insertAdjacentHTML('beforeend', contactRow(null, ci++));
        bindContactRemove(host);
      };
      bindContactRemove(host);
      m.querySelector('#e-gen-suggest').onclick = async () => {
        const fio = $('#e-full').value.trim();
        if (!fio) return toast('Сначала заполните ФИО', 'warn');
        try {
          const r = await api('/api/employees/suggest-genitive', { method: 'POST', body: { full_name: fio } });
          $('#e-full-gen').value = r.genitive || '';
          toast('Проверьте окончание фамилии: автоподстановка может ошибаться', 'ok');
        } catch (e) { toast(e.message, 'err'); }
      };
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        const pass = m.querySelector('#e-pass').value;
        const pass2 = m.querySelector('#e-pass2').value;
        if (pass && pass !== pass2) return toast('Пароли не совпадают', 'warn');
        const color = m.querySelector('#e-colors input:checked')?.value || '#8a94a6';
        const contactList = $$('#e-contacts .contact-row', m).map(row => ({
          name: row.querySelector('.c-name').value.trim(),
          phone: row.querySelector('.c-phone').value.trim(),
          relation: row.querySelector('.c-rel').value.trim(),
        })).filter(c => c.name);
        const body = {
          full_name: $('#e-full').value.trim(), short_name: $('#e-short').value.trim(),
          full_name_genitive: $('#e-full-gen').value.trim(),
          position: $('#e-pos').value.trim(), phone: $('#e-phone').value.trim(),
          tab_number: $('#e-tab').value.trim(), hired_at: $('#e-hired').value || null,
          nationality: $('#e-nat').value.trim(), subdivision: $('#e-subdiv').value.trim(),
          department_id: $('#e-dep').value ? +$('#e-dep').value : null,
          email: $('#e-email').value.trim(), telegram: $('#e-tg').value.trim(),
          emergency_name: contactList[0]?.name || '', emergency_phone: contactList[0]?.phone || '',
          contacts: contactList,
          schedule_group: $('#e-group').value, group_color: color,
          username: $('#e-login').value.trim() || null, password: pass || null,
          role: $('#e-role').value,
        };
        if (!body.full_name) return toast('Укажите ФИО', 'warn');
        try {
          const res = isNew
            ? await api('/api/employees', { method: 'POST', body })
            : await api(`/api/employees/${emp.id}`, { method: 'PUT', body });
          closeModal();
          toast(isNew ? `Создан: ${res.full_name}, логин ${res.username}, пароль ${res.initial_password}` : 'Изменения сохранены', 'ok');
          await refreshAfterEmployeeChange();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

function contactRow(c, i) {
  return `<div class="grid-2 contact-row" style="grid-template-columns:1fr 1fr 1fr auto;gap:8px;margin-bottom:6px">
    <input class="c-name" type="text" placeholder="Имя, например Иванова М. И." value="${esc(c?.name || '')}">
    <input class="c-phone" type="text" placeholder="+7 900 000-00-00" value="${esc(c?.phone || '')}">
    <input class="c-rel" type="text" placeholder="кем приходится (жена, мать…)" value="${esc(c?.relation || '')}">
    <button class="btn btn-sm btn-danger c-del" type="button" title="Убрать контакт">✕</button>
  </div>`;
}
function bindContactRemove(host) {
  host.querySelectorAll('.c-del').forEach(b => b.onclick = () => b.closest('.contact-row').remove());
}
