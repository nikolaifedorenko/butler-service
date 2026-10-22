/* Раздел «Настройки»: экран «Календарь правил» (вынесено из settings.js, шаг 6.5 аудита).
   Оболочка, черновик версии справочников и общие помощники — в settings.js. */
'use strict';

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
    const iso = x.date || x.period_start;
    if (x.date) add(x.date, 'rule', `${x.title} = ${settingsModValue(x.name, x.value)} · ${settingsWhoText(x)}`);
    else if (x.period_start) add(x.period_start, 'rule', `${x.title} = ${settingsModValue(x.name, x.value)} · ${settingsWhoText(x)} · весь период`);
    void iso;
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
  (engine?.versions || []).forEach(v => add(v.valid_from, 'ver', `вступает версия справочников #${v.id}${v.note ? ' · ' + v.note : ''}`));

  host.innerHTML = `
    ${settingsHead('Календарь правил',
      'Один экран: какие правила действуют в конкретный день, откуда они взялись и что вступит в силу. Слои не сливаются — каждый источник виден отдельно.',
      `<div class="month-nav"><button id="cl-prev" aria-label="Предыдущий месяц">‹</button>
         <div class="label">${MONTHS[m - 1]} ${y}</div><button id="cl-next" aria-label="Следующий месяц">›</button></div>
       ${can('settings.edit') ? '<button class="btn btn-sm btn-primary" id="cl-add">+ Правило</button>' : ''}`)}
    ${settingsPanel('', `
      <table class="cal"><thead><tr>${WD_SHORT.map(w => `<th>${w}</th>`).join('')}</tr></thead>
      <tbody>${settingsCalRows(y, m, marks, settingsUI.calDay)}</tbody></table>
      <div class="cal-legend">
        <span><i class="mk rule" style="width:8px;height:8px;border-radius:99px;display:inline-block;background:#2c5f70"></i> переопределение правила</span>
        <span><i style="width:8px;height:8px;border-radius:99px;display:inline-block;background:#c0562f"></i> день двойной оплаты</span>
        <span><i style="width:8px;height:8px;border-radius:99px;display:inline-block;background:#6b3fa0"></i> ВИП-период</span>
        <span><i style="width:8px;height:8px;border-radius:99px;display:inline-block;background:var(--gold)"></i> версия справочников</span>
      </div>`)}
    <div id="cl-day">${settingsDayPanel(settingsUI.calDay, marks, mods, y, m)}</div>
    ${settingsPanel('Производственный календарь и ВИП-гости',
      '<div id="dp-body"><div class="empty">Загрузка…</div></div>')}
    <p class="hint">Массовые назначения («все субботы года», список дат из письма C&amp;B) — в форме выше:
      дни двойной оплаты подмешиваются в правила автоматически, отдельной сущности нет.</p>`;

  settingsOn('#cl-prev', host, () => { settingsUI.calMonth = m - 1 || 12; settingsUI.calYear = m - 1 ? y : y - 1; settingsUI.calDay = null; settingsRenderScreen(); });
  settingsOn('#cl-next', host, () => { settingsUI.calMonth = m + 1 > 12 ? 1 : m + 1; settingsUI.calYear = m + 1 > 12 ? y + 1 : y; settingsUI.calDay = null; settingsRenderScreen(); });
  settingsOn('#cl-add', host, () => settingsWizard());
  $$('[data-day]', host).forEach(td => td.onclick = () => {
    settingsUI.calDay = td.dataset.day;
    $('#cl-day').innerHTML = settingsDayPanel(settingsUI.calDay, marks, mods, y, m);
    $$('[data-day]', host).forEach(x => x.classList.toggle('sel', x.dataset.day === settingsUI.calDay));
    settingsBindDayPanel($('#cl-day'));
  });
  settingsBindDayPanel($('#cl-day'));
  refreshDoublePay();
}

function settingsCalRows(year, month, marks, selected) {
  const total = new Date(year, month, 0).getDate();
  const startWd = (new Date(year, month - 1, 1).getDay() + 6) % 7;
  const weeks = Math.ceil((startWd + total) / 7);
  let out = '', day = 1;
  for (let w = 0; w < weeks; w++) {
    out += '<tr>';
    for (let i = 0; i < 7; i++) {
      const idx = w * 7 + i;
      if (idx < startWd || day > total) { out += '<td class="cell out"></td>'; continue; }
      const iso = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const mk = marks[iso] || {};
      const wd = new Date(year, month - 1, day).getDay();
      out += `<td class="cell${wd === 0 || wd === 6 ? ' we' : ''}${iso === todayISO() ? ' today' : ''}${iso === selected ? ' sel' : ''}"
        data-day="${iso}" title="${esc((mk.items || []).join(' · '))}">
        <div>${day}</div><div class="marks">${['rule', 'dbl', 'vip', 'ver'].filter(k => mk[k])
          .map(k => `<span class="mk ${k}"></span>`).join('')}</div></td>`;
      day++;
    }
    out += '</tr>';
  }
  return out;
}

function settingsDayPanel(iso, marks, mods, year, month) {
  if (!iso) {
    return settingsPanel('День не выбран',
      '<p class="hint" style="margin:0">Кликните по дню календаря: покажем все правила, двойные дни, ВИП-периоды и версии, действующие в этот день, и дадим добавить правило прямо на него.</p>');
  }
  const mk = marks[iso] || {};
  const dayMods = mods.filter(x => x.date === iso || (x.period_start && x.period_start <= iso
    && iso <= `${year}-${String(month).padStart(2, '0')}-${String(new Date(year, month, 0).getDate()).padStart(2, '0')}`));
  return settingsPanel(`День ${dateRu(iso)}`, `
    ${(mk.items || []).length ? mk.items.map(t => `<div class="kv"><span class="v" style="text-align:left;font-weight:600">${esc(t)}</span></div>`).join('')
      : '<p class="hint" style="margin:0">На этот день отдельных правил нет — действуют глобальные значения (уровень 7) и правила на весь период.</p>'}
    ${dayMods.length ? `<div class="opt-group-title" style="margin-top:12px">Правила периода, накрывающие день</div>
      ${dayMods.filter(x => !x.date).map(x => `<div class="kv"><span class="k">${esc(x.title)} · ${esc(settingsWhoText(x))}</span>
        <span class="v">${esc(settingsModValue(x.name, x.value))}</span></div>`).join('')}` : ''}
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px">
      ${can('settings.edit') ? `<button class="btn btn-sm" data-day-rule="${iso}">+ Правило на этот день</button>` : ''}
      <button class="btn btn-sm btn-ghost" data-day-check="${iso}">Проверитель для дня</button>
      <button class="btn btn-sm btn-ghost" data-day-tabel="${iso}">Открыть Табель ↗</button>
    </div>`);
}

function settingsBindDayPanel(panel) {
  if (!panel) return;
  $$('[data-day-rule]', panel).forEach(b => b.onclick = () => settingsWizard());
  $$('[data-day-check]', panel).forEach(b => b.onclick = () => settingsResolverModal());
  $$('[data-day-tabel]', panel).forEach(b => b.onclick = () => navigate('timesheet'));
}
