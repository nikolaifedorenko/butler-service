'use strict';

/* ══════════════════════════════════════════════════════════════════
   ОТМЕТКИ — доска «прямо сейчас» (16.2):
   (a) сколько на работе, (b) сколько ожидается по Графику,
   (c) карточки открытых сессий, (d) кто ещё должен прийти (ближайший подинтервал)
   ══════════════════════════════════════════════════════════════════ */
async function loadMarks() {
  const host = $('#view-marks');
  host.innerHTML = `
    <div class="page-head">
      <div><h2>Отметки</h2>
        <div class="sub">Кто сейчас на работе и кого ждём по Графику — по реальным отметкам.
          Обновляется каждые 30 секунд. Забытый уход виден как есть: счётчик растёт</div></div>
      <div class="spacer"></div>
      <span class="badge ok" id="mk-now" style="font-size:13px;padding:7px 12px">—</span>
      <button class="btn btn-sm" id="mk-refresh">Обновить</button>
    </div>
    <div id="mk-body"><div class="empty">Загрузка…</div></div>`;
  $('#mk-refresh').onclick = () => fetchMarks();
  await fetchMarks();
  poll('marks', () => fetchMarks(true));
}

async function fetchMarks(silent) {
  let d;
  try { d = await api('/api/presence/board', { silent: !!silent }); } catch (e) {
    const b = $('#mk-body');
    if (b) b.innerHTML = `<div class="panel"><div class="empty">${esc(e.message || e)}</div></div>`;
    return;
  }
  const body = $('#mk-body');
  if (!body) return;
  const nowEl = $('#mk-now');
  if (nowEl) nowEl.textContent = `Сейчас ${d.now.slice(11, 16)}`;
  const card = c => {
    const e = c.employee || {};
    /* shift_today_hm — готовые HH:MM в поясе объекта (UTC-моменты shift_today
       для показа не годятся: срез slice(11,16) дал бы часы UTC). */
    const shiftToday = (c.shift_today_hm || []).map(([a, b]) => `${a}–${b}`).join(', ');
    return `<div class="presence-card">
      <div class="nm"><span class="pulse"></span>${esc(e.short_name || c.employee_id)}</div>
      <div class="pos">${esc(e.position || '—')}${e.group ? ' · ' + esc(e.group) : ''}</div>
      ${v4Contacts(e)}
      <div class="row"><span style="color:var(--muted)">На работе с</span><b>${esc(c.open_since_hm)}</b></div>
      <div class="row"><span style="color:var(--muted)">Уже работает</span><b>${esc(durationRu(c.minutes_open))}</b></div>
      <div class="row"><span style="color:var(--muted)">По графику сегодня</span>
        <b>${c.expected_today ? esc(shiftToday || 'ожидается') : 'не ожидался'}</b></div>
    </div>`;
  };
  const arrival = a => {
    const e = a.employee || {};
    return `<div class="presence-card ${a.already_started ? 'late' : ''}">
      <div class="nm">${esc(e.short_name || a.employee_id)}</div>
      <div class="pos">${esc(e.position || '—')}${e.group ? ' · ' + esc(e.group) : ''}</div>
      ${v4Contacts(e)}
      <div class="row"><span style="color:var(--muted)">Ожидается к</span>
        <b style="${a.already_started ? 'color:var(--danger)' : ''}">${esc(a.expected_at_hm)}</b></div>
      ${a.already_started ? '<div class="row"><span></span><b style="color:var(--danger)">не пришёл вовремя</b></div>' : ''}
    </div>`;
  };
  body.innerHTML = `
    <div class="stat-grid">
      <div class="stat accent"><div class="k">Сейчас на работе</div><div class="v">${d.at_work_now}</div></div>
      <div class="stat"><div class="k">По графику в этот момент</div><div class="v">${d.expected_now}</div></div>
      <div class="stat"><div class="k">Ещё должны прийти</div><div class="v">${d.yet_to_come.length}</div></div>
    </div>
    <div class="panel"><h3 class="panel-title">На работе прямо сейчас · ${d.open_session_cards.length}</h3>
      ${d.open_session_cards.length
        ? `<div class="presence-grid">${d.open_session_cards.map(card).join('')}</div>`
        : '<div class="empty">Сейчас никто не отмечен на работе</div>'}</div>
    <div class="panel"><h3 class="panel-title">Кто ещё должен прийти · ${d.yet_to_come.length}</h3>
      ${d.yet_to_come.length
        ? `<div class="presence-grid">${d.yet_to_come.map(arrival).join('')}</div>`
        : '<div class="empty">Больше никого сегодня не ждём</div>'}</div>
    <p class="hint">(a) и (b) — независимые счётчики: «на работе» может превышать «по графику»
      (внеграфиковая работа) и наоборот (не пришли). Расхождение — не ошибка: Табель всегда прав.</p>`;
}
