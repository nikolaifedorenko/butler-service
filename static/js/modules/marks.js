'use strict';

/* ══════════════════════════════════════════════════════════════════
   ОТМЕТКИ — доска «прямо сейчас» (16.2):
   (a) сколько на работе, (b) сколько ожидается по Графику,
   (c) карточки открытых сессий, (d) кто ещё должен прийти (ближайший подинтервал)
   Модуль на lit-html: вся разметка — шаблоны, вставки экранируются сами (ADR-0013, раздел 7).
   ══════════════════════════════════════════════════════════════════ */
import { poll, registerModule } from '../app.js';
import { $, api, durationRu } from '../core.js';
import { html, mount, render } from '../ui/html.js';
import { loadPunchJournal } from './punches_journal.js';
import { contactsView } from './timesheet_common.js';

registerModule({ views: { marks: loadMarks } });

/* то, что показывает доска: последний ответ сервера либо текст ошибки */
const board = { nowHm: '—', data: null, error: '' };

export async function loadMarks() {
  board.data = null; board.error = '';
  draw();
  await fetchMarks();
  poll('marks', () => fetchMarks(true));
  await loadPunchJournal();          // журнал отметок для менеджера — не опрашивается
}

export async function fetchMarks(silent) {
  let d;
  try { d = await api('/api/presence/board', { silent: !!silent }); } catch (e) {
    board.error = String(e.message || e);
    draw();
    return;
  }
  board.error = '';
  board.data = d;
  board.nowHm = d.now.slice(11, 16);
  draw();
}

function draw() {
  const host = $('#view-marks');
  if (host) render(boardTemplate(), mount(host));
}

const fio = e => (e.position || '—') + (e.group ? ' · ' + e.group : '');

function openCard(c) {
  const e = c.employee || {};
  /* shift_today_hm — готовые HH:MM в поясе объекта (UTC-моменты shift_today
     для показа не годятся: срез slice(11,16) дал бы часы UTC). */
  const shiftToday = (c.shift_today_hm || []).map(([a, b]) => `${a}–${b}`).join(', ');
  return html`<div class="presence-card">
    <div class="nm"><span class="pulse"></span>${e.short_name || c.employee_id}</div>
    <div class="pos">${fio(e)}</div>
    ${contactsView(e)}
    <div class="row"><span style="color:var(--muted)">На работе с</span><b>${c.open_since_hm}</b></div>
    <div class="row"><span style="color:var(--muted)">Уже работает</span><b>${durationRu(c.minutes_open)}</b></div>
    <div class="row"><span style="color:var(--muted)">По графику сегодня</span>
      <b>${c.expected_today ? (shiftToday || 'ожидается') : 'не ожидался'}</b></div>
  </div>`;
}

function arrivalCard(a) {
  const e = a.employee || {};
  return html`<div class="presence-card ${a.already_started ? 'late' : ''}">
    <div class="nm">${e.short_name || a.employee_id}</div>
    <div class="pos">${fio(e)}</div>
    ${contactsView(e)}
    <div class="row"><span style="color:var(--muted)">Ожидается к</span>
      <b style=${a.already_started ? 'color:var(--danger)' : ''}>${a.expected_at_hm}</b></div>
    ${a.already_started
      ? html`<div class="row"><span></span><b style="color:var(--danger)">не пришёл вовремя</b></div>` : ''}
  </div>`;
}

function bodyTemplate() {
  if (board.error) return html`<div class="panel"><div class="empty">${board.error}</div></div>`;
  const d = board.data;
  if (!d) return html`<div class="empty">Загрузка…</div>`;
  return html`
    <div class="stat-grid">
      <div class="stat accent"><div class="k">Сейчас на работе</div><div class="v">${d.at_work_now}</div></div>
      <div class="stat"><div class="k">По графику в этот момент</div><div class="v">${d.expected_now}</div></div>
      <div class="stat"><div class="k">Ещё должны прийти</div><div class="v">${d.yet_to_come.length}</div></div>
    </div>
    <div class="panel"><h3 class="panel-title">На работе прямо сейчас · ${d.open_session_cards.length}</h3>
      ${d.open_session_cards.length
        ? html`<div class="presence-grid">${d.open_session_cards.map(openCard)}</div>`
        : html`<div class="empty">Сейчас никто не отмечен на работе</div>`}</div>
    <div class="panel"><h3 class="panel-title">Кто ещё должен прийти · ${d.yet_to_come.length}</h3>
      ${d.yet_to_come.length
        ? html`<div class="presence-grid">${d.yet_to_come.map(arrivalCard)}</div>`
        : html`<div class="empty">Больше никого сегодня не ждём</div>`}</div>
    <p class="hint">(a) и (b) — независимые счётчики: «на работе» может превышать «по графику»
      (внеграфиковая работа) и наоборот (не пришли). Расхождение — не ошибка: Табель всегда прав.</p>`;
}

/* #mk-journal — пустой контейнер: журнал отметок рисует punches_journal.js; lit его не трогает */
function boardTemplate() {
  return html`
    <div class="page-head">
      <div><h2>Отметки</h2>
        <div class="sub">Кто сейчас на работе и кого ждём по Графику — по реальным отметкам.
          Обновляется каждые 30 секунд. Забытый уход виден как есть: счётчик растёт</div></div>
      <div class="spacer"></div>
      <span class="badge ok" id="mk-now" style="font-size:13px;padding:7px 12px">${board.data ? `Сейчас ${board.nowHm}` : '—'}</span>
      <button class="btn btn-sm" id="mk-refresh" @click=${() => fetchMarks()}>Обновить</button>
    </div>
    <div id="mk-body">${bodyTemplate()}</div>
    <div id="mk-journal"></div>`;
}
