'use strict';

/* ══════════════════════════════════════════════════════════════════
   УПРАВЛЕНЧЕСКИЙ ТАБЕЛЬ (16.6) — единственная вкладка тяжёлого конвейера.
   Период: месяц либо половина месяца (настройка period_granularity, v7.1/R36).
   Открытие: незакрытый → живой расчёт (view, ничего не сохраняется); закрытый →
   сохранённые результат и снимок флагов без пересчёта. «Закрыть период» /
   «Пересчитать» — атомарные операции.
   ══════════════════════════════════════════════════════════════════ */
state.mgmtHalf = state.mgmtHalf || null;

function v4PeriodNav(prefix) {
  return `<div class="month-nav"><button id="${prefix}-prev">‹</button>
    <div class="label" id="${prefix}-label">—</div>
    <button id="${prefix}-next">›</button></div>`;
}

async function loadMgmt() {
  const host = $('#view-mgmt');
  host.innerHTML = `
    <div class="page-head">
      <div><h2>Слой 3 · Управленческий Табель</h2><div class="sub">Коды УТ (ДЯ, ДН, ДЯ2, ДН2) по дням после
        размещения; недостача гасится банком и каскадом при закрытии периода</div></div>
      <div class="spacer"></div>
      ${v4PeriodNav('ut')}
      <button class="btn btn-sm btn-primary" id="ut-close">Закрыть период</button>
      <button class="btn btn-sm" id="ut-recalc">Пересчитать</button>
      <button class="btn btn-sm btn-ghost" id="ut-xlsx">Excel</button>
    </div>
    <div id="ut-body"><div class="empty">Загрузка…</div></div>`;
  const qs = () => `year=${state.year}&month=${state.month}` +
    (state.mgmtHalf ? `&half=${state.mgmtHalf}` : '');
  const reload = () => loadMgmt();
  const shiftPeriod = delta => {
    if (state.mgmtHalf) {
      if (delta > 0 && state.mgmtHalf === 1) { state.mgmtHalf = 2; return reload(); }
      if (delta < 0 && state.mgmtHalf === 2) { state.mgmtHalf = 1; return reload(); }
    }
    let m = state.month + delta, y = state.year;
    if (m < 1) { m = 12; y--; } if (m > 12) { m = 1; y++; }
    state.month = m; state.year = y;
    if (state.mgmtHalf) state.mgmtHalf = delta > 0 ? 1 : 2;
    reload();
  };
  $('#ut-prev').onclick = () => shiftPeriod(-1);
  $('#ut-next').onclick = () => shiftPeriod(1);
  let d;
  try { d = await api(`/api/mgmt?${qs()}`); } catch (e) {
    $('#ut-body').innerHTML = `<div class="panel"><div class="empty">${esc(e.message)}</div></div>`; return;
  }
  state.mgmt = d;
  if (d.granularity === 'half_month' && !state.mgmtHalf) state.mgmtHalf = d.half || 1;
  $('#ut-label').textContent = d.granularity === 'half_month'
    ? `${MONTHS[d.month - 1]} ${d.year} · ${d.period.start.slice(8)}–${d.period.end.slice(8)}`
    : `${MONTHS[d.month - 1]} ${d.year}`;
  $('#ut-close').style.display = d.can_close ? '' : 'none';
  $('#ut-recalc').style.display = d.can_recalculate ? '' : 'none';
  $('#ut-close').onclick = () => mgmtAction('close');
  $('#ut-recalc').onclick = () => mgmtAction('recalculate');
  $('#ut-xlsx').onclick = () => downloadBlob(`/api/mgmt/xlsx?${qs()}`, 'upr_tabel.xlsx');
  renderMgmt();
}

function mgmtCell(ut) {
  return Object.entries(ut || {}).map(([t, m]) =>
    `<span class="v4-code ${m >= 120 ? 'x2' : ''} ${t.startsWith('ДН') ? 'n' : 'd'}">${esc(t)}&nbsp;${hours(m / 60)}</span>`).join('');
}

function renderMgmt() {
  const d = state.mgmt;
  const modeNote = 'Просмотр: недостача показана, коды не изымаются, банк — предварительный ' +
    '(входящий + корректировки + зачисленное). Ничего не сохраняется. Закрытие выполняет ' +
    'погашение банком и каскадом и сохраняет результат, снимок флагов и переносы.';
  const stateBadge = r => r.error ? `<span class="badge danger" title="${esc(r.error)}">ошибка</span>`
    : (r.state?.closed ? '<span class="badge ok">закрыт</span>' : '<span class="badge muted">view</span>');
  const rows = d.rows.map(r => {
    if (r.error) {
      return `<tr><td class="who">${esc(r.employee.short_name)}<small>${esc(r.employee.group)}</small></td>
        <td colspan="${d.days.length + d.tariffs.length + 3}" style="color:var(--danger)">${esc(r.error)}</td>
        <td>${stateBadge(r)}</td></tr>`;
    }
    const flagsByDay = {};
    (r.days || []).forEach(dv => (dv.flags || []).forEach(f => {
      (flagsByDay[dv.day] = flagsByDay[dv.day] || []).push(f);
    }));
    const cardByDay = {};
    (r.days || []).forEach(dv => { cardByDay[dv.day] = dv; });
    const outDays = new Set(r.out_of_staff_days || []);
    return `<tr data-emp="${r.employee.id}" class="v4-click">
      <td class="who">${esc(r.employee.short_name)}<small>${esc(r.employee.group)}</small></td>
      ${d.days.map(day => {
        if (outDays.has(day)) {
          return `<td class="v4-ut" title="День вне интервала трудоустройства"><span class="badge muted">не в штате</span></td>`;
        }
        const dv = cardByDay[day];
        const fl = flagsByDay[day] || [];
        const debt = dv && dv.debt_minutes ? `<span class="v4-debt" title="Недостача дня (от окна)">−${hours(dv.debt_minutes / 60)}</span>` : '';
        const flag = fl.length ? `<span class="v4-flag ${V4_FLAG_CLASS[fl[0].code] || ''}" title="${esc(fl.map(f => f.title).join('\n'))}">●</span>` : '';
        const future = day > todayISO() ? ' future' : '';
        const pef = dv && dv.plan_equals_fact ? ' <span class="badge info" title="Применён «План=Факт»: день освобождён от недостачи">П=Ф</span>' : '';
        return `<td class="v4-ut${future}" title="${dv ? esc(dv.timesheet_value) + (future ? ' · прогноз: недостача = окно, если сотрудник не придёт' : '') : ''}">${mgmtCell(r.ut[day])}${debt}${flag}${pef}</td>`;
      }).join('')}
      ${d.tariffs.map(t => `<td class="num">${v4Hours((r.totals[t] || 0) / 60)}</td>`).join('')}
      <td class="num" title="Общий долг / остаток после погашения">${hours(r.debt.total_h)}${r.state?.closed ? ` / ${hours(r.debt.residual_h)}` : ''}</td>
      <td class="num"><b style="color:${r.bank.closed < 0 ? 'var(--danger)' : 'inherit'}">${r.bank.closed >= 0 ? '+' : ''}${hours(r.bank.closed_h)}</b></td>
      <td class="num">${r.deferred.length ? `<span class="badge warn" title="Отложено на следующий период">${r.deferred.length}</span>` : ''}</td>
      <td>${stateBadge(r)}</td></tr>`;
  }).join('');
  $('#ut-body').innerHTML = `
    <div class="panel" style="padding:12px 16px"><span class="hint" style="margin:0">${esc(modeNote)}</span></div>
    <div class="table-wrap v4-grid-wrap"><table class="data v4-grid">
      <thead><tr><th class="who">Сотрудник</th>${d.days.map(v4DayHead).join('')}
        ${d.tariffs.map(t => `<th>${esc(t)}</th>`).join('')}<th>Недостача</th><th>Банк</th><th title="Отложенные блоки">→</th><th>Статус</th></tr></thead>
      <tbody>${rows || '<tr><td class="empty" colspan="99">Нет сотрудников, трудоустроенных в периоде</td></tr>'}</tbody>
    </table></div>
    <p class="hint">Период ${dateRu(d.period.start)} – ${dateRu(d.period.end)} · шаг расчёта
      ${d.step_minutes} мин · версии настроек: ${d.settings_versions.map(esc).join(', ')}.
      Клик по строке — карточки дней (расчётный и информационный планы), флаги, изъятия и трасса расчёта.</p>`;
  $$('#ut-body tr[data-emp]').forEach(tr => tr.onclick = () => mgmtDetail(+tr.dataset.emp));
}

/* Закрытие и пересчёт — «всё или ничего» по штату периода (решение владельца 25.10.2026):
   сервер сначала проверяет всех; хоть одна ошибка — не трогает никого и возвращает
   полный список. Выбрать сотрудников нельзя — ни здесь, ни в карточке. */
async function mgmtAction(kind) {
  const d = state.mgmt;
  const title = kind === 'close' ? 'Закрыть период у всех?' : 'Пересчитать закрытый период у всех?';
  const text = kind === 'close'
    ? `${dateRu(d.period.start)} – ${dateRu(d.period.end)}: сначала проверяются все сотрудники; если хоть у ` +
      'кого-то ошибка, период не закрывается ни у кого — появится список, что исправить. ' +
      'Недостача будет погашена банком и кодами, результат, снимок флагов, банк и отложенные блоки ' +
      'сохранятся. Повторно закрыть нельзя; исправить можно только пересчётом последнего закрытого периода.'
    : 'Сначала проверяются все сотрудники; если хоть у кого-то пересчёт невозможен, не пересчитывается ' +
      'никто. Отметки, Табель и корректировки будут перечитаны свежими; расчёт повторится с исходных ' +
      'входящих остатков периода (ClosingInputs заморожены). Результат, банк, переносы и снимок ' +
      'флагов будут ЗАМЕНЕНЫ. Доступно только для последнего закрытого периода.';
  confirmDialog(title, text, async () => {
    try {
      const body = { year: d.year, month: d.month, half: d.half };
      // закрытие и пересчёт всего штата за период — дольше обычных 20 с (UI-03)
      const r = await api(`/api/mgmt/${kind}`, { method: 'POST', body, timeout: 300000 });
      closeModal();
      if (r.ok) {
        const n = r.done.length;
        const msg = kind === 'close'
          ? (n ? `Период закрыт у всех: ${n}` : 'Период уже закрыт у всех')
            + (r.skipped_closed && n ? ` (ещё ${r.skipped_closed} были закрыты раньше)` : '')
          : `Пересчитано у всех: ${n}`;
        toast(msg, 'ok');
      } else {
        mgmtProblems(kind, r);
      }
      loadMgmt();
    } catch (e) { toast(e.message, 'err'); }
  }, kind === 'close' ? 'Закрыть у всех' : 'Пересчитать у всех', false);
}

/* Полный список тех, из-за кого период не закрыт (не пересчитан), — чтобы исправить. */
function mgmtProblems(kind, r) {
  const what = kind === 'close' ? 'закрыт' : 'пересчитан';
  const title = r.stage === 'check' ? `Период не ${what} ни у кого` : `Период ${what} не у всех`;
  const sub = r.stage === 'check'
    ? `Исправьте ошибки у ${r.errors.length} из ${r.total} и повторите — период ${what === 'закрыт' ? 'закроется' : 'пересчитается'} у всех сразу`
    : `Готово у ${r.done.length}; у остальных данные изменились во время операции — повторите её`;
  openModal({
    title, subtitle: sub, wide: true,
    body: `<div class="table-wrap"><table class="data"><thead><tr><th>Сотрудник</th><th>Что не так</th></tr></thead>
      <tbody>${r.errors.map(e => `<tr data-emp="${e.employee_id}" style="cursor:pointer">
        <td class="who">${esc(e.name)}</td><td>${esc(e.error)}</td></tr>`).join('')}</tbody></table></div>
      <p class="hint">Клик по строке — расчёт сотрудника за период.</p>`,
    footer: '<button class="btn btn-primary" data-cancel>Понятно</button>',
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      $$('tr[data-emp]', m).forEach(tr => tr.onclick = () => { closeModal(); mgmtDetail(+tr.dataset.emp); });
    },
  });
}

async function mgmtDetail(empId) {
  const d = state.mgmt;
  let r;
  try {
    r = await api(`/api/mgmt?year=${d.year}&month=${d.month}${d.half ? `&half=${d.half}` : ''}&employee_id=${empId}&detail=true`);
    r = (r.rows || [])[0];
  } catch (e) { toast(e.message, 'err'); return; }
  if (!r || r.error) { toast(r ? r.error : 'Нет данных', 'err'); return; }
  const b = r.bank;
  const cardRows = (r.days || []).map(dv => {
    const flags = (dv.flags || []).map(f =>
      `<div class="v4-flagtext ${V4_FLAG_CLASS[f.code] || ''}">● ${esc(f.title)}${f.hint ? ` <small>${esc(f.hint)}</small>` : ''}</div>`).join('');
    return `<tr>
      <td>${dateRu(dv.day).slice(0, 6)}</td>
      <td>${esc(dv.timesheet_value)}${dv.plan_equals_fact ? ' <span class="badge info">План=Факт</span>' : ''}</td>
      <td class="num" title="Расчётный план = длина окна (R34)">${v4Hours(dv.plan_hours)}</td>
      <td class="num" title="Информационный (зарплатный) план строки Табеля">${v4Hours(dv.timesheet_plan_hours)}</td>
      <td class="num">${v4Hours(dv.fact_minutes / 60)}</td>
      <td class="num">${v4Hours(dv.work_minutes / 60)}</td>
      <td class="num">${v4Hours(dv.overtime_minutes / 60)}</td>
      <td class="num" style="color:var(--danger)">${dv.debt_minutes ? hours(dv.debt_minutes / 60) : ''}</td>
      <td>${mgmtCell(dv.codes)}${!dv.pays_overtime && dv.overtime_minutes ? ' <span class="badge muted">в банк</span>' : ''}</td>
      <td>${mgmtCell(r.ut[dv.day])}</td>
      <td>${flags}</td></tr>`;
  }).join('');
  const outDays = (r.out_of_staff_days || []);
  openModal({
    title: r.employee.full_name,
    subtitle: `${dateRu(d.period.start)} – ${dateRu(d.period.end)} · ${r.state?.closed ? 'период закрыт (сохранённые данные)' : 'просмотр (живой расчёт)'}`,
    wide: true,
    body: `
      <div class="stat-grid">
        <div class="stat"><div class="k">Недостача всего</div><div class="v">${hours(r.debt.total_h)}</div></div>
        <div class="stat"><div class="k">Погашено банком</div><div class="v">${hours(b.paid / 60)}</div></div>
        <div class="stat warn"><div class="k">Остаток долга</div><div class="v">${hours(r.debt.residual_h)}</div></div>
        <div class="stat accent"><div class="k">Банк на закрытие</div><div class="v">${b.closed >= 0 ? '+' : ''}${hours(b.closed_h)}</div></div>
      </div>
      <p class="hint" style="margin-top:-6px">Банк: входящий ${hours(b.open_h)}${b.open_normalized !== b.open ? ` (нормализован к шагу: ${hours(b.open_normalized / 60)})` : ''}
        + корректировки ${hours(b.adjustments_h)} + зачислено неоплачиваемых переработок ${hours(b.credited_h)}.
        Остаток недостачи всегда переносится минусом банка.</p>
      ${outDays.length ? `<p class="hint">Дни вне трудоустройства («не в штате»): ${outDays.map(x => dateRu(x).slice(0, 6)).join(', ')}</p>` : ''}
      <div class="table-wrap" style="max-height:46vh"><table class="data">
        <thead><tr><th>День</th><th>Табель</th><th>План (окно)</th><th>План строки</th><th>Факт</th>
          <th>Рабочее</th><th>Перераб.</th><th>Недост.</th><th>Коды дня</th><th>Итог УТ</th><th>Флаги</th></tr></thead>
        <tbody>${cardRows}</tbody></table></div>
      ${r.deferred.length ? `<div class="panel" style="margin-top:12px"><h3 class="panel-title">Отложено на следующий период</h3>
        ${r.deferred.map(x => `<span class="badge warn">${esc(x.tariff)} ${hours(x.hours)} ч из ${dateRu(x.source_day)}</span>`).join(' ')}</div>` : ''}
      ${r.cuts && r.cuts.length ? `<div class="panel" style="margin-top:12px"><h3 class="panel-title">Изъятия каскадом</h3>
        ${r.cuts.map(c => `<div>${esc(c.tariff)} ${hours(c.taken_minutes / 60)} ч (${dateRu(c.source_day)}${c.placed_day ? ' → ' + dateRu(c.placed_day) : ''}) — погашено ${hours(c.paid_minutes / 60)} ч</div>`).join('')}</div>` : ''}
      ${r.exceptions.length ? `<div class="panel" style="margin-top:12px"><h3 class="panel-title">Исключения</h3>${r.exceptions.map(x => `<div>${esc(x.text)}</div>`).join('')}</div>` : ''}
      <details style="margin-top:12px"><summary>Трасса расчёта (${(r.trace || []).length})</summary>
        ${(r.trace || []).map(t => `<div class="audit-item"><span class="ac">${esc(t.step)} · ${esc(t.code)}</span> ${esc(t.text)}</div>`).join('') || '<div class="empty">Пусто</div>'}</details>`,
    /* закрыть и пересчитать — только у всего штата, кнопками над таблицей */
    footer: '<button class="btn btn-ghost" data-cancel>Закрыть окно</button>',
    onMount(m) {
      m.classList.add('v4-xl');
      m.querySelector('[data-cancel]').onclick = closeModal;
    },
  });
}
