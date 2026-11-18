'use strict';
/* ══ МОИ ОТМЕТКИ: личный кабинет сотрудника (PWA) ══
   Модуль на lit-html (ADR-0013, раздел 7): разметка — шаблоны, вставки экранируются сами;
   границы — import/export, наружу (в мост) выходит только loadMe: его зовёт раздел «Электрокары». */
import { poll, registerModule } from '../app.js';
import { CAR_BADGE, carHandoverModal, carReturnModal } from './cars.js';
import {
  $, api, closeModal, confirmDialog, hhmm, hours, MONTHS_GEN, openModal, state, syncServerClock, toast, WD,
} from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';

registerModule({ views: { me: loadMe } });

export async function loadMe() {
  const host = mount($('#view-me'));
  render(html`<div class="me-wrap"><div class="empty">Загрузка…</div></div>`, host);
  try {
    const status = await api('/api/punches/status');
    state.status = status;
    syncServerClock(status.now);
    renderMe(status);
    poll('me', loadMeSilently);
  } catch (e) {
    render(html`<div class="me-wrap"><div class="panel"><h3 class="panel-title">Мои отметки</h3>
      <p style="color:var(--muted);font-size:14px">К вашей учётной записи не привязан сотрудник — отметки недоступны.<br><br>${e.message}</p></div></div>`, host);
  }
}

/* кнопка «пришёл / ушёл»: пять состояний — от разрешений и смены */
function punchButton(s, nowHm) {
  const inOk = s.punch_in_allowed !== false;
  const outOk = s.punch_out_allowed !== false;
  const hint = s.punch_status_hint || 'согласованное отсутствие';
  if (s.on_shift && outOk) {
    return html`<button class="punch-btn out" id="punch-btn" @click=${doPunch}>Ушёл с работы
      <small>нажать в ${s.planned_end ? hhmm(s.planned_end) : '—'} · сейчас ${nowHm}</small></button>`;
  }
  if (s.on_shift) {
    return html`<button class="punch-btn idle" id="punch-btn" disabled>Ушёл с работы
      <small>${hint} — отмечать уход запрещено</small></button>`;
  }
  if (!inOk) {
    return html`<button class="punch-btn idle" id="punch-btn" disabled>Пришёл на работу
      <small>${hint} — отмечать приход запрещено</small></button>`;
  }
  if (s.shift) {
    return html`<button class="punch-btn in" id="punch-btn" @click=${doPunch}>Пришёл на работу
      <small>смена ${s.shift.start_hm}–${s.shift.end_hm} · сейчас ${nowHm}</small></button>`;
  }
  return html`<button class="punch-btn in" id="punch-btn" @click=${doPunch}>Пришёл на работу
    <small>по Графику смены нет — часы будут учтены как переработка (коды ДЯ/ДН)</small></button>`;
}

function renderMe(s) {
  const d = new Date(s.today + 'T00:00:00');
  const shift = s.shift;
  const nowD = new Date(s.now);
  const nowHm = nowD.toTimeString().slice(0, 5);
  const expected = s.expected || [];
  /* #me-history и #car-strip — пустые контейнеры: их наполняют loadMyHistory и bindCarStrip
     своими render(); перерисовка страницы раз в 30 с их содержимое не стирает. */
  render(html`
  <div class="me-wrap">
    <div class="me-date">${WD[d.getDay()]}, ${d.getDate()} ${MONTHS_GEN[d.getMonth()]} ${d.getFullYear()} · ${nowHm}</div>

    <div class="me-shift">
      <div class="code">${shift ? (shift.source === 'manual' ? 'ручная смена' : 'смена из Табеля') : 'График'}</div>
      <div class="title">${shift ? `${shift.start_hm}–${shift.end_hm}` : 'смены нет'}</div>
      <div class="sub">${expected.length
        ? 'ожидается: ' + expected.map(x => `${x[0]}–${x[1]}`).join(', ')
        : (shift ? 'ожидается вся смена' : 'сегодня не ожидались')}</div>
    </div>

    <div class="punch-zone">${punchButton(s, nowHm)}</div>

    ${s.on_shift ? html`
    <div class="status-line"><span class="k"><span class="pulse"></span>Вы на смене с ${hhmm(s.session_start)}</span>
      <span class="v">${s.elapsed_hours != null ? hours(s.elapsed_hours) + ' ч' : '—'}</span></div>` : nothing}

    <div class="me-stats">
      <div class="me-stat"><div class="k">Часы сегодня (по отметкам)</div><div class="v">${hours(s.today_hours || 0)} ч</div></div>
      <div class="me-stat"><div class="k">Банк часов</div>
        <div class="v ${s.balance_hours >= 0 ? 'balance-pos' : 'balance-neg'}">${s.balance_hours >= 0 ? '+' : ''}${hours(s.balance_hours)}</div></div>
    </div>
    <p class="hint" style="margin-top:-4px">${s.balance_note || ''}. Точные рабочее время,
      переработки и недостача — во вкладке «Управленческий табель» у менеджера.</p>

    <div class="history">
      <h3 class="panel-title">Мои отметки</h3>
      <div id="me-history"></div>
    </div>

    <div class="panel" id="car-strip"></div>

    ${state.user.impersonated ? html`<div class="alert warn" style="margin-top:16px">
      <p style="margin:0">Демо-режим: вы смотрите интерфейс сотрудника
      <b>${state.user.name}</b>. Отметки, нажатые здесь, попадут в его табель.</p></div>` : nothing}
  </div>`, mount($('#view-me')));

  /* История — с catch (ревью 20.10.2026, P1-fe-5): без него сбой запроса
     (/api/punches) уходил в unhandledrejection и пугал общим тостом «Ошибка
     интерфейса… обновите страницу»; причина показывается в самой панели. */
  loadMyHistory().catch(e => {
    const h = $('#me-history');
    if (h) render(html`<div class="empty">Историю отметок не загрузить: ${e && e.message || e}</div>`, h);
  });
  bindCarStrip();   // свой try/catch внутри — «Раздел недоступен»
}

/* ── полоска «Мой электрокар» в «Моих отметках»: держу / закреплён / взять свободный ── */
const carTitle = html`<h3 class="panel-title">Электрокар</h3>`;

async function bindCarStrip() {
  const host = $('#car-strip');
  if (!host) return;
  if (!host.dataset.ready) render(html`${carTitle}<div class="empty" style="padding:12px">Загрузка…</div>`, host);
  try {
    const data = await api('/api/cars', { silent: true });
    const cars = data.cars || [];
    const me = data.me || {};
    const held = cars.find(c => c.id === me.held);
    const assigned = cars.find(c => c.id === me.assigned);
    const freeRec = cars.find(c => c.id === me.free_recommended);
    let body;
    if (held) {
      body = html`<div class="rule-row"><div>
          <div class="lbl">Вы держите кар №${held.number} <span class="badge ${CAR_BADGE[held.status] || 'muted'}">${held.status_title}</span></div>
          <div class="desc">место: ${held.location || '—'} · заряд: ${held.charge_title}${held.has_key ? ' · ключ у вас' : ''}</div>
        </div><div class="rule-input" style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn btn-sm" id="cs-return" @click=${() => carReturnModal(held, () => loadMe())}>Вернул</button>
          <button class="btn btn-sm btn-ghost" id="cs-handover" @click=${() => carHandoverModal(held, () => loadMe())}>Передать</button>
        </div></div>`;
    } else if (freeRec) {
      body = html`<div class="rule-row"><div>
          <div class="lbl">Свободный кар: №${freeRec.number} · ${freeRec.location || 'место не указано'}</div>
          <div class="desc">${assigned ? `Закреплён за вами: №${assigned.number}. ` : ''}Взять кар можно, даже если он на зарядке.</div>
        </div><div class="rule-input"><button class="btn btn-sm btn-accent" id="cs-take" @click=${() => takeCar(freeRec)}>Взял кар №${freeRec.number}</button></div></div>`;
    } else {
      body = html`<div class="hint" style="margin:0">Свободных каров нет — вы ничего не держите. Актуальный парк: раздел «Электрокары».</div>`;
    }
    const note = assigned && assigned.id !== me.held
      ? html`<div class="hint">Закреплённый за вами кар №${assigned.number} сейчас ${assigned.status === 'busy' ? `у ${assigned.holder_name || 'другого'}` : assigned.status_title.toLowerCase()}</div>`
      : nothing;
    render(html`${carTitle}${body}${note}`, host);
    host.dataset.ready = '1';
  } catch {
    render(html`${carTitle}<div class="hint" style="margin:0">Раздел недоступен</div>`, host);
  }
}

async function takeCar(car) {
  try {
    await api(`/api/cars/${car.id}/take`, { method: 'POST', body: { ack_assigned: false } });
    toast(`Кар №${car.number} взят — ключ по умолчанию у вас`, 'ok');
    loadMe();
  } catch (e) {
    if (e.payload?.interception) {
      confirmDialog('Кар закреплён за другим', e.payload.message, async () => {
        try {
          await api(`/api/cars/${car.id}/take`, { method: 'POST', body: { ack_assigned: true } });
          toast(`Кар №${car.number} взят, факт записан в историю`, 'ok');
          loadMe();
        } catch (e2) { toast(e2.message, 'err'); }
      }, 'Всё равно взять', false);
    } else toast(e.message, 'err');
  }
}

async function loadMeSilently() {
  try {
    if (punchInFlight) return;   // не перерисовываем кнопку, пока отметка отправляется
    const s = await api('/api/punches/status', { silent: true });
    state.status = s;
    syncServerClock(s.now);
    if (state.view === 'me' && !punchInFlight) renderMe(s);
  } catch { /* тихо */ }
}

let punchInFlight = false;
async function doPunch() {
  if (punchInFlight) return;               // двойной тап
  punchInFlight = true;
  const btn = $('#punch-btn');
  if (btn) btn.disabled = true;
  // направление — по тому, что видит пользователь на кнопке, а не «auto» на сервере:
  // иначе второй тап превращается в «Ушёл» через секунду после «Пришёл»
  const kind = state.status?.on_shift ? 'out' : 'in';
  try {
    const res = await api('/api/punches', { method: 'POST', body: { kind } });
    toast(res.message, 'ok', res.warnings || []);
    state.status = res.status;
    punchInFlight = false;
    renderMe(res.status);
    if (res.punch?.kind === 'OUT') {
      openOtNoteModal(res.punch.id, '', 0);
    }
  } catch (e) {
    toast(e.message, 'err');
    if (btn) btn.disabled = false;
  } finally {
    punchInFlight = false;
  }
}

export function openOtNoteModal(punchId, current, otHours) {
  openModal({
    title: 'Описание переработки',
    subtitle: otHours ? `Переработка ${hours(otHours)} ч — опишите, с кем работали и что делали` : 'Описание попадёт в табель и в выгрузку Excel',
    body: html`<label class="field"><span>Текст</span>
      <textarea id="ot-note" rows="4" maxlength="255" placeholder="Например: оставался с Ивановым, готовили зал к банкету; принимал доставку белья" .value=${current || ''}></textarea></label>`,
    footer: html`<button class="btn btn-ghost" data-skip>Позже</button>
             <button class="btn btn-primary" data-save>Сохранить</button>`,
    onMount(m) {
      m.querySelector('[data-skip]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        const note = m.querySelector('#ot-note').value.trim();
        try {
          await api(`/api/punches/${punchId}/note`, { method: 'PUT', body: { note } });
          closeModal();
          toast('Описание переработки сохранено', 'ok');
          if (state.view === 'me') loadMe();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

async function loadMyHistory() {
  const host = $('#me-history');
  if (!host) return;
  /* учётка без сотрудника (администратор): без фильтра API вернул бы отметки ВСЕХ
     сотрудников, и они показывались бы как свои (ревью 22.10.2026) */
  if (!state.user.employee_id) {
    render(html`<div class="empty">К учётной записи не привязан сотрудник — своих отметок нет</div>`, host);
    return;
  }
  if (!host.dataset.ready) render(html`<div class="empty">Загрузка…</div>`, host);
  const d = new Date();
  const items = await api(`/api/punches?year=${d.getFullYear()}&month=${d.getMonth() + 1}&employee_id=${state.user.employee_id}`);
  host.dataset.ready = '1';
  if (!items.length) { render(html`<div class="empty">Отметок пока нет</div>`, host); return; }
  render(html`${items.slice(0, 30).map(p => {
    const dt = new Date(p.ts);
    return html`<div class="history-item">
      <div class="ic ${p.kind === 'IN' ? 'in' : 'out'}">${p.kind === 'IN' ? '→' : '←'}</div>
      <div class="meta">${p.kind === 'IN' ? 'Пришёл на работу' : 'Ушёл с работы'}
        <small>${dt.getDate()} ${MONTHS_GEN[dt.getMonth()]} · ${p.source === 'manual' ? 'добавлено менеджером' : 'самостоятельно'}${p.note ? ' · ★ ' + p.note : ''}</small></div>
      ${p.kind === 'OUT'
        ? html`<button class="btn btn-sm btn-ghost note-btn" data-note=${p.id} @click=${() => openOtNoteModal(p.id, p.note || '', 0)}>★ описание</button>` : nothing}
      <div class="t">${dt.toTimeString().slice(0, 5)}</div>
    </div>`;
  })}`, host);
}

/* ── мост к общей области имён (генерируется tools/gen_js_globals.py; уйдёт вместе с переходом файла на import/export) ── */
Object.assign(globalThis, {
  loadMe,
  openOtNoteModal,
});
/* ── конец моста ── */
