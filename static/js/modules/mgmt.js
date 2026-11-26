'use strict';

/* ══════════════════════════════════════════════════════════════════
   УПРАВЛЕНЧЕСКИЙ ТАБЕЛЬ (16.6) — единственная вкладка тяжёлого конвейера.
   Период: месяц либо половина месяца (настройка period_granularity, v7.1/R36).
   Открытие: незакрытый → живой расчёт (view, ничего не сохраняется); закрытый →
   сохранённые результат и снимок флагов без пересчёта. «Закрыть период» /
   «Пересчитать» — атомарные операции.
   Модуль на lit-html (ADR-0013, раздел 7): разметка — шаблоны, вставки экранируются сами.
   ══════════════════════════════════════════════════════════════════ */
import {
  $, api, closeModal, confirmDialog, dateRu, downloadBlob, hours, loadGeneration, MONTHS, openModal, state, todayISO, toast,
} from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { periodNav } from '../ui/period_nav.js';
import { dayHeadCell, V4_FLAG_CLASS, v4Hours } from './timesheet_common.js';

state.mgmtHalf = state.mgmtHalf || null;

/* что показывает слой: загрузка, текст ошибки либо ответ сервера */
const screen = { loading: true, error: '' };

export async function loadMgmt() {
  screen.loading = true; screen.error = '';
  draw();
  const fresh = loadGeneration('mgmt');
  let d;
  try { d = await api(`/api/mgmt?${query()}`); } catch (e) {
    if (fresh()) { screen.loading = false; screen.error = String(e.message); draw(); }
    return;
  }
  if (!fresh()) return;          // пока ждали ответ, перелистнули период
  state.mgmt = d;
  state.mgmtHalf = d.granularity === 'half_month' ? d.half || 1 : null;
  screen.loading = false;
  draw();
}

const query = () => `year=${state.year}&month=${state.month}` + (state.mgmtHalf ? `&half=${state.mgmtHalf}` : '');

function shiftPeriod(delta) {
  if (state.mgmtHalf) {
    if (delta > 0 && state.mgmtHalf === 1) { state.mgmtHalf = 2; return loadMgmt(); }
    if (delta < 0 && state.mgmtHalf === 2) { state.mgmtHalf = 1; return loadMgmt(); }
  }
  let m = state.month + delta, y = state.year;
  if (m < 1) { m = 12; y--; } if (m > 12) { m = 1; y++; }
  state.month = m; state.year = y;
  state.mgmtHalf = delta > 0 ? 1 : 2;
  return loadMgmt();
}

function draw() {
  const host = $('#view-mgmt');
  if (host) render(layerTemplate(), mount(host));
}

function periodLabel(d) {
  if (!d) return `${MONTHS[state.month - 1]} ${state.year}`;
  return d.granularity === 'half_month'
    ? `${MONTHS[d.month - 1]} ${d.year} · ${d.period.start.slice(8)}–${d.period.end.slice(8)}`
    : `${MONTHS[d.month - 1]} ${d.year}`;
}

function openPreviousPeriod(previous) {
  state.year = previous.year;
  state.month = previous.month;
  state.mgmtHalf = previous.half;
  loadMgmt();
  $('#ut-label')?.focus();
}

function blockingStatus(d) {
  if (!d?.blocking) return nothing;
  const { previous_period: previous, opening_bank_missing: openingBank } = d.blocking;
  if (!previous && !openingBank) return nothing;
  return html`<div class="alert warn mgmt-blocking" role="status">
    ${previous ? html`<div><strong>Не закрыт предыдущий период</strong>
      <div>${dateRu(previous.start)}–${dateRu(previous.end)}.</div>
      ${d.can_close ? nothing : html`<div>Обратитесь к руководителю, который закрывает табель.</div>`}</div>` : nothing}
    ${previous && d.can_close ? html`<button class="btn btn-sm" @click=${() => openPreviousPeriod(previous)}>
      Открыть предыдущий период</button>` : nothing}
    ${openingBank ? html`<div>У некоторых сотрудников не указан начальный остаток часов. Обратитесь к администратору.</div>` : nothing}
  </div>`;
}

function layerTemplate() {
  const d = screen.loading || screen.error ? null : state.mgmt;
  return html`
    <div class="page-head">
      <div><h2>Слой 3 · Управленческий Табель</h2><div class="sub">Коды УТ (ДЯ, ДН, ДЯ2, ДН2) по дням после
        размещения; недостача гасится банком и каскадом при закрытии периода</div></div>
      <div class="spacer"></div>
      ${periodNav('ut', periodLabel(d), shiftPeriod, 'период')}
      <button class="btn btn-sm btn-primary" id="ut-close" style=${d?.can_close ? '' : 'display:none'}
        @click=${() => mgmtAction('close')}>Закрыть период</button>
      <button class="btn btn-sm" id="ut-recalc" style=${d?.can_recalculate ? '' : 'display:none'}
        @click=${() => mgmtAction('recalculate')}>Пересчитать</button>
      <button class="btn btn-sm btn-ghost" id="ut-xlsx"
        @click=${() => downloadBlob(`/api/mgmt/xlsx?${query()}`, 'upr_tabel.xlsx')}>Excel</button>
      ${blockingStatus(d)}
    </div>
    <div id="ut-body">${bodyTemplate()}</div>`;
}

function bodyTemplate() {
  if (screen.loading) return html`<div class="skel-wrap"><div class="skel-line skel-lg"></div><div class="skel-line"></div><div class="skel-line"></div></div>`;
  if (screen.error) return html`<div class="panel"><div class="empty">${screen.error}</div></div>`;
  return mgmtTable(state.mgmt);
}

function mgmtCell(ut) {
  return Object.entries(ut || {}).map(([t, m]) =>
    html`<span class="v4-code ${m >= 120 ? 'x2' : ''} ${t.startsWith('ДН') ? 'n' : 'd'}">${t}&nbsp;${hours(m / 60)}</span>`);
}

function stateBadge(r) {
  if (r.error) return html`<span class="badge danger" title=${r.error}>ошибка</span>`;
  return r.state?.closed ? html`<span class="badge ok">закрыт</span>` : html`<span class="badge muted">view</span>`;
}

function dayCell(r, d, day, cardByDay, flagsByDay, outDays) {
  if (outDays.has(day)) {
    return html`<td class="v4-ut" title="День вне интервала трудоустройства"><span class="badge muted">не в штате</span></td>`;
  }
  const dv = cardByDay[day];
  const fl = flagsByDay[day] || [];
  const future = day > todayISO();
  const title = dv ? dv.timesheet_value + (future ? ' · прогноз: недостача = окно, если сотрудник не придёт' : '') : '';
  return html`<td class="v4-ut${future ? ' future' : ''}" title=${title}>${mgmtCell(r.ut[day])}${
    dv && dv.debt_minutes ? html`<span class="v4-debt" title="Недостача дня (от окна)">−${hours(dv.debt_minutes / 60)}</span>` : nothing}${
    fl.length ? html`<span class="v4-flag ${V4_FLAG_CLASS[fl[0].code] || ''}" title=${fl.map(f => f.title).join('\n')}>●</span>` : nothing}${
    dv && dv.plan_equals_fact ? html` <span class="badge info" title="Применён «План=Факт»: день освобождён от недостачи">П=Ф</span>` : nothing}</td>`;
}

function employeeRow(r, d) {
  if (r.error) {
    const message = r.error_code === 'PREVIOUS_PERIOD_NOT_CLOSED' && d.blocking?.previous_period
      ? 'Ожидает закрытия' : r.error;
    return html`<tr><td class="who">${r.employee.short_name}<small>${r.employee.group}</small></td>
      <td colspan=${d.days.length + d.tariffs.length + 3} style="color:var(--danger)">${message}</td>
      <td>${stateBadge(r)}</td></tr>`;
  }
  const flagsByDay = {};
  (r.days || []).forEach(dv => (dv.flags || []).forEach(f => {
    (flagsByDay[dv.day] = flagsByDay[dv.day] || []).push(f);
  }));
  const cardByDay = {};
  (r.days || []).forEach(dv => { cardByDay[dv.day] = dv; });
  const outDays = new Set(r.out_of_staff_days || []);
  return html`<tr data-emp=${r.employee.id} class="v4-click" @click=${() => mgmtDetail(r.employee.id)}>
    <td class="who">${r.employee.short_name}<small>${r.employee.group}</small></td>
    ${d.days.map(day => dayCell(r, d, day, cardByDay, flagsByDay, outDays))}
    ${d.tariffs.map(t => html`<td class="num">${v4Hours((r.totals[t] || 0) / 60)}</td>`)}
    <td class="num" title="Общий долг / остаток после погашения">${hours(r.debt.total_h)}${r.state?.closed ? ` / ${hours(r.debt.residual_h)}` : ''}</td>
    <td class="num"><b style=${`color:${r.bank.closed < 0 ? 'var(--danger)' : 'inherit'}`}>${r.bank.closed >= 0 ? '+' : ''}${hours(r.bank.closed_h)}</b></td>
    <td class="num">${r.deferred.length ? html`<span class="badge warn" title="Отложено на следующий период">${r.deferred.length}</span>` : nothing}</td>
    <td>${stateBadge(r)}</td></tr>`;
}

function mgmtTable(d) {
  const modeNote = 'Просмотр: недостача показана, коды не изымаются, банк — предварительный ' +
    '(входящий + корректировки + зачисленное). Ничего не сохраняется. Закрытие выполняет ' +
    'погашение банком и каскадом и сохраняет результат, снимок флагов и переносы.';
  return html`
    <div class="panel" style="padding:12px 16px"><span class="hint" style="margin:0">${modeNote}</span></div>
    <div class="table-wrap v4-grid-wrap" tabindex="0"><table class="data v4-grid">
      <thead><tr><th class="who">Сотрудник</th>${d.days.map(dayHeadCell)}
        ${d.tariffs.map(t => html`<th>${t}</th>`)}<th>Недостача</th><th>Банк</th><th title="Отложенные блоки">→</th><th>Статус</th></tr></thead>
      <tbody>${d.rows.length ? d.rows.map(r => employeeRow(r, d))
        : html`<tr><td class="empty" colspan="99">Нет сотрудников, трудоустроенных в периоде</td></tr>`}</tbody>
    </table></div>
    <p class="hint">Период ${dateRu(d.period.start)} – ${dateRu(d.period.end)} · шаг расчёта
      ${d.step_minutes} мин · версии настроек: ${d.settings_versions.join(', ')}.
      Клик по строке — карточки дней (расчётный и информационный планы), флаги, изъятия и трасса расчёта.</p>`;
}

/* Закрытие и пересчёт — «всё или ничего» по штату периода:
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
    body: html`<div class="table-wrap" tabindex="0"><table class="data"><thead><tr><th>Сотрудник</th><th>Что не так</th></tr></thead>
      <tbody>${r.errors.map(e => html`<tr data-emp=${e.employee_id} style="cursor:pointer"
        @click=${() => { closeModal(); mgmtDetail(e.employee_id); }}>
        <td class="who">${e.name}</td><td>${e.error}</td></tr>`)}</tbody></table></div>
      <p class="hint">Клик по строке — расчёт сотрудника за период.</p>`,
    footer: html`<button class="btn btn-primary" data-cancel>Понятно</button>`,
    onMount(m) { m.querySelector('[data-cancel]').onclick = closeModal; },
  });
}

function dayCardRow(r, dv) {
  return html`<tr>
    <td>${dateRu(dv.day).slice(0, 6)}</td>
    <td>${dv.timesheet_value}${dv.plan_equals_fact ? html` <span class="badge info">План=Факт</span>` : nothing}</td>
    <td class="num" title="Расчётный план = длина окна (R34)">${v4Hours(dv.plan_hours)}</td>
    <td class="num" title="Информационный (зарплатный) план строки Табеля">${v4Hours(dv.timesheet_plan_hours)}</td>
    <td class="num">${v4Hours(dv.fact_minutes / 60)}</td>
    <td class="num">${v4Hours(dv.work_minutes / 60)}</td>
    <td class="num">${v4Hours(dv.overtime_minutes / 60)}</td>
    <td class="num" style="color:var(--danger)">${dv.debt_minutes ? hours(dv.debt_minutes / 60) : ''}</td>
    <td>${mgmtCell(dv.codes)}${!dv.pays_overtime && dv.overtime_minutes ? html` <span class="badge muted">в банк</span>` : nothing}</td>
    <td>${mgmtCell(r.ut[dv.day])}</td>
    <td>${(dv.flags || []).map(f => html`<div class="v4-flagtext ${V4_FLAG_CLASS[f.code] || ''}">● ${f.title}${f.hint ? html` <small>${f.hint}</small>` : nothing}</div>`)}</td></tr>`;
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
  const outDays = (r.out_of_staff_days || []);
  openModal({
    title: r.employee.full_name,
    subtitle: `${dateRu(d.period.start)} – ${dateRu(d.period.end)} · ${r.state?.closed ? 'период закрыт (сохранённые данные)' : 'просмотр (живой расчёт)'}`,
    wide: true,
    body: html`
      <div class="stat-grid">
        <div class="stat"><div class="k">Недостача всего</div><div class="v">${hours(r.debt.total_h)}</div></div>
        <div class="stat"><div class="k">Погашено банком</div><div class="v">${hours(b.paid / 60)}</div></div>
        <div class="stat warn"><div class="k">Остаток долга</div><div class="v">${hours(r.debt.residual_h)}</div></div>
        <div class="stat accent"><div class="k">Банк на закрытие</div><div class="v">${b.closed >= 0 ? '+' : ''}${hours(b.closed_h)}</div></div>
      </div>
      <p class="hint" style="margin-top:-6px">Банк: входящий ${hours(b.open_h)}${b.open_normalized !== b.open ? ` (нормализован к шагу: ${hours(b.open_normalized / 60)})` : ''}
        + корректировки ${hours(b.adjustments_h)} + зачислено неоплачиваемых переработок ${hours(b.credited_h)}.
        Остаток недостачи всегда переносится минусом банка.</p>
      ${outDays.length ? html`<p class="hint">Дни вне трудоустройства («не в штате»): ${outDays.map(x => dateRu(x).slice(0, 6)).join(', ')}</p>` : nothing}
      <div class="table-wrap" tabindex="0" style="max-height:46vh"><table class="data">
        <thead><tr><th>День</th><th>Табель</th><th>План (окно)</th><th>План строки</th><th>Факт</th>
          <th>Рабочее</th><th>Перераб.</th><th>Недост.</th><th>Коды дня</th><th>Итог УТ</th><th>Флаги</th></tr></thead>
        <tbody>${(r.days || []).map(dv => dayCardRow(r, dv))}</tbody></table></div>
      ${r.deferred.length ? html`<div class="panel" style="margin-top:12px"><h3 class="panel-title">Отложено на следующий период</h3>
        ${r.deferred.map(x => html`<span class="badge warn">${x.tariff} ${hours(x.hours)} ч из ${dateRu(x.source_day)}</span> `)}</div>` : nothing}
      ${r.cuts && r.cuts.length ? html`<div class="panel" style="margin-top:12px"><h3 class="panel-title">Изъятия каскадом</h3>
        ${r.cuts.map(c => html`<div>${c.tariff} ${hours(c.taken_minutes / 60)} ч (${dateRu(c.source_day)}${c.placed_day ? ' → ' + dateRu(c.placed_day) : ''}) — погашено ${hours(c.paid_minutes / 60)} ч</div>`)}</div>` : nothing}
      ${r.exceptions.length ? html`<div class="panel" style="margin-top:12px"><h3 class="panel-title">Исключения</h3>${r.exceptions.map(x => html`<div>${x.text}</div>`)}</div>` : nothing}
      <details style="margin-top:12px"><summary>Трасса расчёта (${(r.trace || []).length})</summary>
        ${(r.trace || []).length ? r.trace.map(t => html`<div class="audit-item"><span class="ac">${t.step} · ${t.code}</span> ${t.text}</div>`)
          : html`<div class="empty">Пусто</div>`}</details>`,
    /* закрыть и пересчитать — только у всего штата, кнопками над таблицей */
    footer: html`<button class="btn btn-ghost" data-cancel>Закрыть окно</button>`,
    onMount(m) {
      m.classList.add('v4-xl');
      m.querySelector('[data-cancel]').onclick = closeModal;
    },
  });
}
