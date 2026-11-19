/* ══════════════════════════════════════════════════════════════════════
   Общее для экранов движка v7.1 (Отметки, Факт, Табель, Управленческий табель,
   Права доступа, Журнал аудита, справочники движка — по файлу на экран, 22.10.2026;
   раньше всё жило в timesheet_v4.js): цвета кодов Табеля, навигация по месяцу.
   Зависит от core.js (api, state, $, esc, openModal, toast …) и app.js (can, poll).
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

import { cssColor, hours, MONTHS, state, todayISO, WD_SHORT } from '../core.js';
import { html, nothing } from '../ui/html.js';

/* Цвета кодов Табеля — только подстраховка: основной источник — блок presentation
   версии справочников (payload.day_code_policy[code].color), если он заполнен.
   Кодов «С», «НВ» и «НБ» здесь нет: из справочника Табеля они исключены
 — суточная смена это явка «Я 10,75»
   в дне-якоре, выходной за часы — отсутствие в Графике, а «НБ»
   (неоплачиваемый больничный) — артефакт старого наполнения. */
export const V4_CODE_COLORS = {
  'Я': '#34a862', 'К': '#2b8fb6', 'В': '#c3cdd9', 'ДО': '#d9822b',
  'ОТ': '#f0a500', 'ОВ': '#9b59b6', 'Б': '#e05d4b', 'НН': '#b03a48',
};
export function v4CodeColor(code, fromPayload) {
  /* cssColor на выходе закрывает все стоки (пилюли, таймлайн, ячейки): цвета из
     payload настроек приходят из БД и не должны вырываться из style="…". */
  return cssColor((fromPayload && fromPayload[code]) || V4_CODE_COLORS[code]);
}
export const V4_FLAG_CLASS = { LATE: 'warn', EARLY_DEPARTURE: 'warn', OFF_SHIFT_ATTENDANCE: 'info' };

export function v4Hours(v) { return v ? hours(v) : ''; }

/* Шаблоны lit-html: ячейка заголовка дня, переход по месяцам. */
export function dayHeadCell(iso) {
  const d = new Date(iso + 'T12:00:00');
  const weekend = d.getDay() === 0 || d.getDay() === 6;
  return html`<th class="v4-day${weekend ? ' we' : ''}${iso === todayISO() ? ' today' : ''}">${d.getDate()}<small>${WD_SHORT[(d.getDay() + 6) % 7]}</small></th>`;
}

/* Переход по месяцам: шаблон с обработчиками. reload вызывается после смены state.year / state.month. */
export function monthNav(prefix, reload) {
  const shift = delta => {
    let m = state.month + delta, y = state.year;
    if (m < 1) { m = 12; y--; } if (m > 12) { m = 1; y++; }
    state.month = m; state.year = y; reload();
  };
  return html`<div class="month-nav"><button id=${prefix + '-prev'} @click=${() => shift(-1)}>‹</button>
    <div class="label" id=${prefix + '-label'}>${MONTHS[state.month - 1]} ${state.year}</div>
    <button id=${prefix + '-next'} @click=${() => shift(1)}>›</button></div>`;
}

export function contactsView(e) {
  const tel = String(e.phone || '').trim();
  const tg = String(e.telegram || '').trim().replace(/^@+/, '');
  if (!tel && !tg) return nothing;
  return html`<div class="contacts">${tel ? html`<a href=${'tel:' + tel.replace(/[^0-9+]/g, '')}>📞 ${tel}</a>` : nothing}${
    tg ? html`<a href=${'https://t.me/' + tg.replace(/[^A-Za-z0-9_]/g, '')} target="_blank" rel="noopener">✈️ @${tg}</a>` : nothing}</div>`;
}
