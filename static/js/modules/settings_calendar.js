/* Раздел «Настройки»: экран «Календарь правил».
   Оболочка, черновик версии справочников и общие помощники — в settings.js.
   Модуль на lit-html (ADR-0013, раздел 7). */
'use strict';

import { can, navigate, registerModule } from '../app.js';
import { api, dateRu, MONTHS, state, todayISO, WD_SHORT } from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { periodNav } from '../ui/period_nav.js';
import { settingsEngine, settingsHeadView, settingsPanelView, settingsRenderScreen, settingsUI } from './settings.js';
import { refreshDoublePay } from './dicts.js';
import { settingsModValue, settingsResolverModal, settingsWhoText, settingsWizard } from './settings_pay.js';

registerModule({ screens: { calendar: { render: settingsScreenCalendar, icon: 'cal' } } });

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «КАЛЕНДАРЬ ПРАВИЛ» — день × кто: слои переопределений, двойных дней,
   ВИП-периодов и версий справочников. Данные не сливаем — показываем слоями.
   ══════════════════════════════════════════════════════════════════════ */
async function settingsScreenCalendar(host) {
  const engine = await settingsEngine();
  const y = settingsUI.calYear || state.year, m = settingsUI.calMonth || state.month;
  const [mods, dp] = await Promise.all([
    api(`/api/engine-settings/modifiers?year=${y}&month=${m}`, { silent: true }).catch(() => []),
    api(`/api/doublepay?year=${y}`, { silent: true }).catch(() => ({ days: [], vip: [], scopes: [] })),
  ]);
  const marks = {};
  const add = (iso, key, text) => {
    if (!iso) return;
    marks[iso] = marks[iso] || { items: [] };
    marks[iso][key] = (marks[iso][key] || 0) + 1;
    marks[iso].items.push(text);
  };
  mods.forEach(x => {
    if (x.date) add(x.date, 'rule', `${x.title} = ${settingsModValue(x.name, x.value)} · ${settingsWhoText(x)}`);
    else if (x.period_start) add(x.period_start, 'rule', `${x.title} = ${settingsModValue(x.name, x.value)} · ${settingsWhoText(x)} · весь период`);
  });
  (dp.days || []).forEach(x => {
    const iso = `${y}-${String(x.month).padStart(2, '0')}-${String(x.day).padStart(2, '0')}`;
    add(iso, 'dbl', `день двойной оплаты (${x.scope_title || x.scope})${x.note ? ' · ' + x.note : ''}`);
  });
  (dp.vip || []).forEach(v => {
    const s = new Date(v.start_date + 'T12:00:00'), e = new Date(v.end_date + 'T12:00:00');
    for (let t = s; t <= e && t.getFullYear() === y; t.setDate(t.getDate() + 1)) {
      if (t.getMonth() + 1 !== m) continue;
      add(`${y}-${String(m).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`, 'vip',
        `ВИП: ${v.employee_full_name || v.employee_name}${v.note ? ' · ' + v.note : ''}`);
    }
  });
  (engine?.versions || []).forEach(v => add(v.valid_from, 'ver', `вступают в силу настройки${v.note ? ' · ' + v.note : ''}`));

  const dot = style => html`<i style=${`width:8px;height:8px;border-radius:99px;display:inline-block;${style}`}></i>`;
  const shift = delta => {
    const next = m + delta;
    settingsUI.calMonth = (next + 11) % 12 + 1;
    settingsUI.calYear = y + Math.floor((next - 1) / 12);
    settingsUI.calDay = null;
    settingsRenderScreen();
  };
  const draw = () => render(html`
    ${settingsHeadView('Календарь правил',
      'Один экран: какие правила действуют в конкретный день, откуда они взялись и что вступит в силу. Слои не сливаются — каждый источник виден отдельно.',
      html`${periodNav('cl', `${MONTHS[m - 1]} ${y}`, shift)}
       ${can('settings.edit') ? html`<button class="btn btn-sm btn-primary" id="cl-add" @click=${() => settingsWizard()}>+ Правило</button>` : nothing}`)}
    ${settingsPanelView('', html`
      <table class="cal"><thead><tr>${WD_SHORT.map(w => html`<th>${w}</th>`)}</tr></thead>
      <tbody>${calRows(y, m, marks, settingsUI.calDay, iso => { settingsUI.calDay = iso; draw(); })}</tbody></table>
      <div class="cal-legend">
        <span>${dot('background:#2c5f70')} переопределение правила</span>
        <span>${dot('background:#c0562f')} день двойной оплаты</span>
        <span>${dot('background:#6b3fa0')} ВИП-период</span>
        <span>${dot('background:var(--gold)')} изменение настроек</span>
      </div>`)}
    <div id="cl-day">${dayPanel(settingsUI.calDay, marks, mods, y, m)}</div>
    ${settingsPanelView('Производственный календарь и ВИП-гости',
      html`<div id="dp-body"><div class="skel-wrap"><div class="skel-line skel-lg"></div><div class="skel-line"></div><div class="skel-line"></div></div></div>`)}
    <p class="hint">Массовые назначения («все субботы года», список дат из письма C&amp;B) — в форме выше:
      дни двойной оплаты подмешиваются в правила автоматически, отдельной сущности нет.</p>`, mount(host));
  draw();
  refreshDoublePay();
}

function calRows(year, month, marks, selected, pick) {
  const total = new Date(year, month, 0).getDate();
  const startWd = (new Date(year, month - 1, 1).getDay() + 6) % 7;
  const weeks = Math.ceil((startWd + total) / 7);
  const rows = [];
  let day = 1;
  for (let w = 0; w < weeks; w++) {
    const cells = [];
    for (let i = 0; i < 7; i++) {
      const idx = w * 7 + i;
      if (idx < startWd || day > total) { cells.push(html`<td class="cell out"></td>`); continue; }
      const iso = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const mk = marks[iso] || {};
      const wd = new Date(year, month - 1, day).getDay();
      const d = day;
      cells.push(html`<td class=${`cell${wd === 0 || wd === 6 ? ' we' : ''}${iso === todayISO() ? ' today' : ''}${iso === selected ? ' sel' : ''}`}
        data-day=${iso} title=${(mk.items || []).join(' · ')} @click=${() => pick(iso)}>
        <div>${d}</div><div class="marks">${['rule', 'dbl', 'vip', 'ver'].filter(k => mk[k])
          .map(k => html`<span class=${`mk ${k}`}></span>`)}</div></td>`);
      day++;
    }
    rows.push(html`<tr>${cells}</tr>`);
  }
  return rows;
}

function dayPanel(iso, marks, mods, year, month) {
  if (!iso) {
    return settingsPanelView('День не выбран',
      html`<p class="hint" style="margin:0">Кликните по дню календаря: покажем все правила, двойные дни, ВИП-периоды и версии, действующие в этот день, и дадим добавить правило прямо на него.</p>`);
  }
  const mk = marks[iso] || {};
  const dayMods = mods.filter(x => x.date === iso || (x.period_start && x.period_start <= iso
    && iso <= `${year}-${String(month).padStart(2, '0')}-${String(new Date(year, month, 0).getDate()).padStart(2, '0')}`));
  return settingsPanelView(`День ${dateRu(iso)}`, html`
    ${(mk.items || []).length ? mk.items.map(t => html`<div class="kv"><span class="v" style="text-align:left;font-weight:600">${t}</span></div>`)
      : html`<p class="hint" style="margin:0">На этот день отдельных правил нет — действуют глобальные значения (уровень 7) и правила на весь период.</p>`}
    ${dayMods.length ? html`<div class="opt-group-title" style="margin-top:12px">Правила периода, накрывающие день</div>
      ${dayMods.filter(x => !x.date).map(x => html`<div class="kv"><span class="k">${x.title} · ${settingsWhoText(x)}</span>
        <span class="v">${settingsModValue(x.name, x.value)}</span></div>`)}` : nothing}
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px">
      ${can('settings.edit') ? html`<button class="btn btn-sm" data-day-rule=${iso} @click=${() => settingsWizard()}>+ Правило на этот день</button>` : nothing}
      <button class="btn btn-sm btn-ghost" data-day-check=${iso} @click=${() => settingsResolverModal()}>Проверитель для дня</button>
      <button class="btn btn-sm btn-ghost" data-day-tabel=${iso} @click=${() => navigate('timesheet')}>Открыть Табель ↗</button>
    </div>`);
}
