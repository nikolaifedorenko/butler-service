/* ══════════════════════════════════════════════════════════════════════
   Общее для экранов движка v7.1 (Отметки, Факт, Табель, Управленческий табель,
   Права доступа, Журнал аудита, справочники движка — по файлу на экран, 22.10.2026;
   раньше всё жило в timesheet_v4.js): цвета кодов Табеля, навигация по месяцу.
   Зависит от core.js (api, state, $, esc, openModal, toast …) и app.js (can, poll).
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

/* Цвета кодов Табеля — только подстраховка: основной источник — блок presentation
   версии справочников (payload.day_code_policy[code].color), если он заполнен.
   Кодов «С», «НВ» и «НБ» здесь нет: из справочника Табеля они исключены
   (нормативы 12.10.2026 и 16.10.2026) — суточная смена это явка «Я 10,75»
   в дне-якоре, выходной за часы — отсутствие в Графике, а «НБ»
   (неоплачиваемый больничный) — артефакт старого наполнения. */
const V4_CODE_COLORS = {
  'Я': '#34a862', 'К': '#2b8fb6', 'В': '#c3cdd9', 'ДО': '#d9822b',
  'ОТ': '#f0a500', 'ОВ': '#9b59b6', 'Б': '#e05d4b', 'НН': '#b03a48',
};
function v4CodeColor(code, fromPayload) {
  /* cssColor на выходе закрывает все стоки (пилюли, таймлайн, ячейки): цвета из
     payload настроек приходят из БД и не должны вырываться из style="…". */
  return cssColor((fromPayload && fromPayload[code]) || V4_CODE_COLORS[code]);
}
const V4_FLAG_CLASS = { LATE: 'warn', EARLY_DEPARTURE: 'warn', OFF_SHIFT_ATTENDANCE: 'info' };

function v4MonthNav(prefix, onShift) {
  return `<div class="month-nav"><button id="${prefix}-prev">‹</button>
    <div class="label" id="${prefix}-label">${MONTHS[state.month - 1]} ${state.year}</div>
    <button id="${prefix}-next">›</button></div>`;
}
function v4BindMonthNav(prefix, reload) {
  const shift = delta => {
    let m = state.month + delta, y = state.year;
    if (m < 1) { m = 12; y--; } if (m > 12) { m = 1; y++; }
    state.month = m; state.year = y; reload();
  };
  $(`#${prefix}-prev`).onclick = () => shift(-1);
  $(`#${prefix}-next`).onclick = () => shift(1);
}
function v4DayHead(iso) {
  const d = new Date(iso + 'T12:00:00');
  const wd = WD_SHORT[(d.getDay() + 6) % 7];
  const weekend = d.getDay() === 0 || d.getDay() === 6;
  return `<th class="v4-day${weekend ? ' we' : ''}${iso === todayISO() ? ' today' : ''}">${d.getDate()}<small>${wd}</small></th>`;
}
function v4Hours(v) { return v ? hours(v) : ''; }
function v4Contacts(e) {
  const tel = String(e.phone || '').trim();
  const tg = String(e.telegram || '').trim().replace(/^@+/, '');
  if (!tel && !tg) return '';
  return `<div class="contacts">${tel ? `<a href="tel:${esc(tel.replace(/[^0-9+]/g, ''))}">📞 ${esc(tel)}</a>` : ''}${
    tg ? `<a href="https://t.me/${esc(tg.replace(/[^A-Za-z0-9_]/g, ''))}" target="_blank" rel="noopener">✈️ @${esc(tg)}</a>` : ''}</div>`;
}
