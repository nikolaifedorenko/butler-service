'use strict';
/* ══ МОИ ОТМЕТКИ: личный кабинет сотрудника (PWA) ══
   Вынесено из app.js (15.10.2026) без изменения логики: границы разделов —
   файлами (сборки намеренно нет, ADR-0008), общие функции — через глобальную
   область (реестр tools/js_globals.json, ESLint no-undef ловит пропуски). */

/* ══════════════════════════════════════════════════════════════════
   МОИ ОТМЕТКИ
   ══════════════════════════════════════════════════════════════════ */
registerModule({ views: { me: loadMe } });

async function loadMe() {
  $('#view-me').innerHTML = '<div class="me-wrap"><div class="empty">Загрузка…</div></div>';
  try {
    const [status, me] = await Promise.all([api('/api/punches/status'), api('/api/auth/me')]);
    state.status = status;
    syncServerClock(status.now);
    renderMe(status, me);
    poll('me', loadMeSilently);
  } catch (e) {
    $('#view-me').innerHTML = `<div class="me-wrap"><div class="panel"><h3 class="panel-title">Мои отметки</h3>
      <p style="color:var(--muted);font-size:14px">К вашей учётной записи не привязан сотрудник — отметки недоступны.<br><br>${esc(e.message)}</p></div></div>`;
  }
}

function renderMe(s, me) {
  const d = new Date(s.today + 'T00:00:00');
  const shift = s.shift;
  const nowD = new Date(s.now);
  const inOk = s.punch_in_allowed !== false;
  const outOk = s.punch_out_allowed !== false;
  const hint = s.punch_status_hint || 'согласованное отсутствие';

  let mainBtn;
  if (s.on_shift && outOk) {
    mainBtn = `<button class="punch-btn out" id="punch-btn">Ушёл с работы
      <small>нажать в ${s.planned_end ? hhmm(s.planned_end) : '—'} · сейчас ${nowD.toTimeString().slice(0, 5)}</small></button>`;
  } else if (s.on_shift) {
    mainBtn = `<button class="punch-btn idle" id="punch-btn" disabled>Ушёл с работы
      <small>${esc(hint)} — отмечать уход запрещено</small></button>`;
  } else if (!inOk) {
    mainBtn = `<button class="punch-btn idle" id="punch-btn" disabled>Пришёл на работу
      <small>${esc(hint)} — отмечать приход запрещено</small></button>`;
  } else if (shift) {
    mainBtn = `<button class="punch-btn in" id="punch-btn">Пришёл на работу
      <small>смена ${esc(shift.start_hm)}–${esc(shift.end_hm)} · сейчас ${nowD.toTimeString().slice(0, 5)}</small></button>`;
  } else {
    mainBtn = `<button class="punch-btn in" id="punch-btn">Пришёл на работу
      <small>по Графику смены нет — часы будут учтены как переработка (коды ДЯ/ДН)</small></button>`;
  }

  $('#view-me').innerHTML = `
  <div class="me-wrap">
    <div class="me-date">${WD[d.getDay()]}, ${d.getDate()} ${MONTHS_GEN[d.getMonth()]} ${d.getFullYear()} · ${nowD.toTimeString().slice(0, 5)}</div>

    <div class="me-shift" style="--accent:#34a862">
      <div class="code">${shift ? (shift.source === 'manual' ? 'ручная смена' : 'смена из Табеля') : 'График'}</div>
      <div class="title">${shift ? `${esc(shift.start_hm)}–${esc(shift.end_hm)}` : 'смены нет'}</div>
      <div class="sub">${(s.expected || []).length
        ? 'ожидается: ' + s.expected.map(x => `${esc(x[0])}–${esc(x[1])}`).join(', ')
        : (shift ? 'ожидается вся смена' : 'сегодня не ожидались')}</div>
    </div>

    <div class="punch-zone">${mainBtn}</div>

    ${s.on_shift ? `
    <div class="status-line"><span class="k"><span class="pulse"></span>Вы на смене с ${hhmm(s.session_start)}</span>
      <span class="v">${s.elapsed_hours != null ? hours(s.elapsed_hours) + ' ч' : '—'}</span></div>` : ''}

    <div class="me-stats">
      <div class="me-stat"><div class="k">Часы сегодня (по отметкам)</div><div class="v">${hours(s.today_hours || 0)} ч</div></div>
      <div class="me-stat"><div class="k">Банк часов</div>
        <div class="v ${s.balance_hours >= 0 ? 'balance-pos' : 'balance-neg'}">${s.balance_hours >= 0 ? '+' : ''}${hours(s.balance_hours)}</div></div>
    </div>
    <p class="hint" style="margin-top:-4px">${esc(s.balance_note || '')}. Точные рабочее время,
      переработки и недостача — во вкладке «Управленческий табель» у менеджера.</p>

    <div class="history">
      <h3 class="panel-title">Мои отметки</h3>
      <div id="me-history"><div class="empty">Загрузка…</div></div>
    </div>

    ${carStripHtml()}

    ${state.user.impersonated ? `<div class="panel" style="margin-top:16px;border-color:#f0d9a8;background:#fffdf6">
      <p style="margin:0;font-size:13.5px;color:#8a5300">Демо-режим: вы смотрите интерфейс сотрудника
      <b>${esc(state.user.name)}</b>. Отметки, нажатые здесь, попадут в его табель.</p></div>` : ''}
  </div>`;

  const btn = $('#punch-btn');
  if (btn && !btn.disabled) btn.onclick = doPunch;
  /* История — с catch (ревью 20.10.2026, P1-fe-5): без него сбой запроса
     (/api/punches) уходил в unhandledrejection и пугал общим тостом «Ошибка
     интерфейса… обновите страницу»; причина показывается в самой панели. */
  loadMyHistory().catch(e => {
    const h = $('#me-history');
    if (h) h.innerHTML = `<div class="empty">Историю отметок не загрузить: ${esc(e && e.message || e)}</div>`;
  });
  bindCarStrip();   // свой try/catch внутри — «Раздел недоступен»
}

/* ── полоска «Мой электрокар» в «Моих отметках»: держу / закреплён / взять свободный ── */
function carStripHtml() {
  return `<div class="panel" id="car-strip"><h3 class="panel-title">Электрокар</h3>
    <div class="empty" style="padding:12px">Загрузка…</div></div>`;
}

async function bindCarStrip() {
  const host = $('#car-strip');
  if (!host) return;
  try {
    const data = await api('/api/cars', { silent: true });
    const cars = data.cars || [];
    const me = data.me || {};
    const held = cars.find(c => c.id === me.held);
    const assigned = cars.find(c => c.id === me.assigned);
    const freeRec = cars.find(c => c.id === me.free_recommended);
    let inner;
    if (held) {
      inner = `<div class="rule-row"><div>
          <div class="lbl">Вы держите кар №${esc(held.number)} <span class="badge ${CAR_BADGE[held.status] || 'muted'}">${esc(held.status_title)}</span></div>
          <div class="desc">место: ${esc(held.location || '—')} · заряд: ${esc(held.charge_title)}${held.has_key ? ' · ключ у вас' : ''}</div>
        </div><div class="rule-input" style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn btn-sm" id="cs-return">Вернул</button>
          <button class="btn btn-sm btn-ghost" id="cs-handover">Передать</button>
        </div></div>`;
    } else if (freeRec) {
      inner = `<div class="rule-row"><div>
          <div class="lbl">Свободный кар: №${esc(freeRec.number)} · ${esc(freeRec.location || 'место не указано')}</div>
          <div class="desc">${assigned ? `Закреплён за вами: №${esc(assigned.number)}. ` : ''}Взять кар можно, даже если он на зарядке.</div>
        </div><div class="rule-input"><button class="btn btn-sm btn-accent" id="cs-take">Взял кар №${esc(freeRec.number)}</button></div></div>`;
    } else {
      inner = `<div class="hint" style="margin:0">Свободных каров нет — вы ничего не держите. Актуальный парк: раздел «Электрокары».</div>`;
    }
    if (assigned && assigned.id !== me.held) {
      inner += `<div class="hint">Закреплённый за вами кар №${esc(assigned.number)} сейчас ${assigned.status === 'busy' ? `у ${esc(assigned.holder_name || 'другого')}` : assigned.status_title.toLowerCase()}</div>`;
    }
    host.innerHTML = `<h3 class="panel-title">Электрокар</h3>${inner}`;
    const take = $('#cs-take'), ret = $('#cs-return'), ho = $('#cs-handover');
    if (take) take.onclick = async () => {
      try {
        await api(`/api/cars/${freeRec.id}/take`, { method: 'POST', body: { ack_assigned: false } });
        toast(`Кар №${freeRec.number} взят — ключ по умолчанию у вас`, 'ok');
        loadMe();
      } catch (e) {
        if (e.payload?.interception) {
          confirmDialog('Кар закреплён за другим', e.payload.message, async () => {
            try {
              await api(`/api/cars/${freeRec.id}/take`, { method: 'POST', body: { ack_assigned: true } });
              toast(`Кар №${freeRec.number} взят, факт записан в историю`, 'ok');
              loadMe();
            } catch (e2) { toast(e2.message, 'err'); }
          }, 'Всё равно взять', false);
        } else toast(e.message, 'err');
      }
    };
    if (ret) ret.onclick = () => carReturnModal(held, () => loadMe());
    if (ho) ho.onclick = () => carHandoverModal(held, () => loadMe());
  } catch {
    host.innerHTML = `<h3 class="panel-title">Электрокар</h3><div class="hint" style="margin:0">Раздел недоступен</div>`;
  }
}

async function loadMeSilently() {
  try {
    if (punchInFlight) return;   // не перерисовываем кнопку, пока отметка отправляется
    const [s, me] = await Promise.all([api('/api/punches/status', { silent: true }),
                                       api('/api/auth/me', { silent: true })]);
    state.status = s;
    syncServerClock(s.now);
    if (state.view === 'me' && !punchInFlight) renderMe(s, me);
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
    const me = await api('/api/auth/me', { silent: true });
    punchInFlight = false;
    renderMe(res.status, me);
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

function openOtNoteModal(punchId, current, otHours) {
  openModal({
    title: 'Описание переработки',
    subtitle: otHours ? `Переработка ${hours(otHours)} ч — опишите, с кем работали и что делали` : 'Описание попадёт в табель и в выгрузку Excel',
    body: `<label class="field"><span>Текст</span>
      <textarea id="ot-note" rows="4" placeholder="Например: оставался с Ивановым, готовили зал к банкету; принимал доставку белья">${esc(current || '')}</textarea></label>`,
    footer: `<button class="btn btn-ghost" data-skip>Позже</button>
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
    host.innerHTML = '<div class="empty">К учётной записи не привязан сотрудник — своих отметок нет</div>';
    return;
  }
  const d = new Date();
  const items = await api(`/api/punches?year=${d.getFullYear()}&month=${d.getMonth() + 1}&employee_id=${state.user.employee_id}`);
  if (!items.length) { host.innerHTML = '<div class="empty">Отметок пока нет</div>'; return; }
  host.innerHTML = items.slice(0, 30).map(p => {
    const dt = new Date(p.ts);
    return `<div class="history-item">
      <div class="ic ${p.kind === 'IN' ? 'in' : 'out'}">${p.kind === 'IN' ? '→' : '←'}</div>
      <div class="meta">${p.kind === 'IN' ? 'Пришёл на работу' : 'Ушёл с работы'}
        <small>${dt.getDate()} ${MONTHS_GEN[dt.getMonth()]} · ${esc(p.source === 'manual' ? 'добавлено менеджером' : 'самостоятельно')}${p.note ? ' · ★ ' + esc(p.note) : ''}</small></div>
      ${p.kind === 'OUT' ? `<button class="btn btn-sm btn-ghost note-btn" data-note="${p.id}" data-cur="${esc(p.note || '')}">★ описание</button>` : ''}
      <div class="t">${dt.toTimeString().slice(0, 5)}</div>
    </div>`;
  }).join('');
  $$('[data-note]', host).forEach(b => b.onclick = () => openOtNoteModal(+b.dataset.note, b.dataset.cur, 0));
}
