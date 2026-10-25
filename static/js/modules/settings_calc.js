/* Раздел «Настройки»: экран «Расчёт» (вынесено из settings.js, шаг 6.5 аудита).
   Оболочка, черновик версии справочников и общие помощники — в settings.js. */
'use strict';

registerModule({ screens: { calc: { render: settingsScreenCalc, icon: 'calc' } } });

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «РАСЧЁТ» — лимит опоздания, каркас, категории, веса, порядки
   Три блока с РАЗНОЙ механикой вступления в силу (план §3.2).
   ══════════════════════════════════════════════════════════════════════ */
const SETTINGS_STEPS = [15, 30, 60];

async function settingsScreenCalc(host) {
  const [engine, health] = await Promise.all([settingsEngine(), settingsHealth().catch(() => null)]);
  const p = settingsPayload();
  const d = settingsDraft();
  if (!p || !d) { host.innerHTML = '<div class="empty">Справочники не загружены</div>'; return; }
  const edit = can('settings.edit');
  const dayCat = (d.categories || []).find(c => c.code === 'ДЯ') || { start_minute: 360, end_minute: 1320 };
  const nightCat = (d.categories || []).find(c => c.code === 'ДН') || null;
  const applies = settingsAppliesFrom(todayISO(), d.period_granularity);

  host.innerHTML = `
    ${settingsHead('Расчёт',
      'Как считаются часы: лимит опоздания, период, шаг, часовояс, категории дня и ночи, веса кодов УТ и порядки каскада. Изменения публикуются версией справочников.',
      `<span class="chip">версия #${engine?.active?.id ?? '—'} · с ${esc(dateRu(engine?.active?.valid_from))}</span>`)}
    ${settingsPanel('А · Лимит опоздания', `
      <div style="display:flex;gap:14px;align-items:flex-end;flex-wrap:wrap">
        <label class="field" style="margin:0;width:170px"><span>Минут, после которых ставится флаг</span>
          <input type="number" id="cl-late" min="0" max="240" step="1" value="${Number(d.late_limit_minutes) || 0}" ${edit ? '' : 'disabled'}></label>
        <div class="hint" style="margin:0;flex:1;min-width:240px">До какой задержки флаг <code>LATE</code> не ставится;
          тот же лимит применяется к раннему уходу (<code>EARLY_DEPARTURE</code>). Норма: CFG-LIMITS, 6.6.</div>
      </div>
      <p class="hint">Сейчас лимит — поле версии справочников, поэтому меняется вместе с публикацией
        (применится к периодам с <b>${esc(dateRu(applies))}</b>). Значение «с сегодняшнего дня» для группы
        или сотрудника появится, когда лимит станет правилом CFG-MODIFIERS (R41, этап 1б плана) —
        версия справочников выбирается по дате <b>начала периода</b>, а не подневно.</p>`,
      '')}
    ${settingsPanel('Б · Каркас расчёта — публикуется версией', `
      <div class="grid-2">
        <label class="field"><span>Часовой пояс объекта</span>
          <input type="text" id="cl-tz" value="${esc(state.appTz || d.tz || '')}" disabled>
          <div class="hint">Пояс объекта задаётся при установке (<code>APP_TZ</code>) и здесь не меняется
            (решение владельца 21.10.2026). DST намеренно не поддерживается: локальные сутки = 1440 мин (R24)</div></label>
        <label class="field"><span>Период расчёта</span>
          <div class="seg" id="cl-gran" style="margin-top:4px">
            <button data-v="month" class="${d.period_granularity === 'month' ? 'active' : ''}" ${edit ? '' : 'disabled'}>месяц</button>
            <button data-v="half_month" class="${d.period_granularity === 'half_month' ? 'active' : ''}" ${edit ? '' : 'disabled'}>полмесяца</button></div>
          <div class="hint">Полмесяца = 1–15 / 16–конец. Определяет цепочку периодов и границу закрытия (R36)</div></label>
        <label class="field"><span>Шаг расчёта</span>
          <div class="seg" id="cl-step" style="margin-top:4px">${SETTINGS_STEPS.map(s =>
            `<button data-v="${s}" class="${Number(d.step_minutes) === s ? 'active' : ''}" ${edit ? '' : 'disabled'}>${s}</button>`).join('')}</div>
          <div class="hint">Округляются только моменты отметок и <code>now</code>; границы окон и категорий
            лежат на той же сетке (CHK-GRID)</div></label>
        <label class="field"><span>Лимит часов в дне</span>
          <input type="text" value="${Number(d.day_limit_minutes) || 1440} мин · фиксировано" readonly
            style="background:var(--panel-2)">
          <div class="hint">Ёмкость дня для переносов: лимит − длина окна − Σ размещённых кодов</div></label>
      </div>
      <div class="preview">
        <div class="row"><span class="k">Действующая версия</span><b>#${engine?.active?.id ?? '—'} · с ${esc(dateRu(engine?.active?.valid_from))}</b></div>
        <div class="row"><span class="k">Текущий период</span><b>${health?.periods?.current
          ? `${dateRu(health.periods.current.start)}–${dateRu(health.periods.current.end)}` : '—'}</b></div>
        <div class="row"><span class="k">Последний закрытый период</span><b>${esc(closedPeriodText(health?.periods?.last_closed))}</b></div>
        <div class="row"><span class="k">Черновик применится</span><b>к периодам, начинающимся с ${esc(dateRu(applies))} (или позже — по дате публикации)</b></div>
      </div>`) }
    ${settingsPanel('В · Категории времени · CFG-CATEGORIES', `
      <div class="grid-2">
        <label class="field" style="margin:0"><span>Начало дневных часов (ДЯ)</span>
          <input type="time" id="cl-cat-start" value="${settingsHm(dayCat.start_minute)}" step="${(Number(d.step_minutes) || 15) * 60}" ${edit ? '' : 'disabled'}></label>
        <label class="field" style="margin:0"><span>Конец дневных часов (ДЯ)</span>
          <input type="time" id="cl-cat-end" value="${settingsHm(dayCat.end_minute)}" step="${(Number(d.step_minutes) || 15) * 60}" ${edit ? '' : 'disabled'}></label>
      </div>
      <p class="hint" style="margin-top:10px">Ночные (ДН) — дополнение суток:
        <b id="cl-night-text">${nightCat ? `${settingsHm(nightCat.start_minute)}–${settingsHm(nightCat.end_minute)}` : '—'}</b>.
        Две категории покрывают сутки целиком и не пересекаются (CHK-CATEGORIES-COVER);
        границы лежат на сетке шага (CHK-GRID). Дневные на полосе — зелёным.</p>
      <div id="cl-cat-timeline">${settingsTimeline([
        { label: 'ДЯ (день)', start: dayCat.start_minute, end: dayCat.end_minute, color: 'var(--accent)' },
        { label: 'ДН (ночь)', start: nightCat?.start_minute ?? dayCat.end_minute, end: nightCat?.end_minute ?? dayCat.start_minute, color: 'var(--navy)' },
      ])}</div>`) }
    ${settingsPanel('Г · Веса кодов УТ · CFG-WEIGHTS', `
      <p class="hint" style="margin:-4px 0 10px">Вес — множитель перевода часа в банк («две валюты», спека 4.1),
        а не признак двойного дня: <code>ДН = 2</code> даст двойное начисление в банк за ночные часы.
        Движок порождает только коды с весом 1 и 2 (<code>weight_of_day</code>), поэтому вес 3+ — мёртвая
        конфигурация, пока не добавлено правило R42.</p>
      <div class="table-wrap"><table class="data"><thead><tr>
        <th>Код УТ</th><th>Категория</th><th class="num">Вес</th><th>Смысл</th></tr></thead>
      <tbody>${Object.entries(d.weights || {}).map(([code, w]) => `<tr>
        <td>${settingsCodePill(code, d.day_code_policy)}</td>
        <td>${esc(code.replace(/2$/, ''))}</td>
        <td class="num"><input type="number" min="1" max="9" step="1" value="${Number(w) || 1}"
          data-weight="${esc(code)}" style="max-width:90px;text-align:right" ${edit ? '' : 'disabled'}></td>
        <td class="hint" style="margin:0">${Number(w) === 2 ? 'двойной тариф (ДЯ2/ДН2)' : 'одинарный тариф'}</td>
      </tr>`).join('')}</tbody></table></div>`) }
    ${settingsPanel('Д · Порядки · CFG-CASCADE и CFG-PLACEMENT', `
      <div class="opt-group-title">Каскад гашения недостачи и долга</div>
      <p class="hint" style="margin:0 0 8px">Банк часов гасит долг первым, далее — коды в этом порядке
        (CHK-CASCADE-FULL: все коды весов 1 и 2 должны присутствовать).</p>
      ${settingsOrderList('cascade', d.cascade_order || [], edit)}
      <div class="opt-group-title" style="margin-top:16px">Порядок размещения переработки по кодам</div>
      <p class="hint" style="margin:0 0 8px">Куда сначала кладутся часы переработки дня (CHK-PLACEMENT-FULL).</p>
      ${settingsOrderList('placement', d.placement_order || [], edit)}`) }
    ${settingsDraftBarHtml()}`;

  if (!edit) return;
  const touch = () => settingsUpdateDraftBars();
  $('#cl-late').onchange = e => { d.late_limit_minutes = Math.max(0, Number(e.target.value) || 0); touch(); };
  const seg = (sel, key, isNum) => $$(sel, host).forEach(b => b.onclick = () => {
    d[key] = isNum ? Number(b.dataset.v) : b.dataset.v;
    $$(sel, host).forEach(x => x.classList.toggle('active', x === b));
    if (key === 'period_granularity') {
      const ap = $('.preview .row:last-child b', host);
      if (ap) ap.textContent = `к периодам, начинающимся с ${dateRu(settingsAppliesFrom(todayISO(), d.period_granularity))} (или позже — по дате публикации)`;
    }
    touch();
  });
  seg('#cl-gran button', 'period_granularity', false);
  seg('#cl-step button', 'step_minutes', true);
  const catChange = () => {
    const s = settingsMin($('#cl-cat-start').value), e = settingsMin($('#cl-cat-end').value);
    if (s === null || e === null) return;
    d.categories = [{ code: 'ДЯ', start_minute: s, end_minute: e }, { code: 'ДН', start_minute: e, end_minute: s }];
    $('#cl-night-text').textContent = `${settingsHm(e)}–${settingsHm(s)}`;
    $('#cl-cat-timeline').innerHTML = settingsTimeline([
      { label: 'ДЯ (день)', start: s, end: e, color: 'var(--accent)' },
      { label: 'ДН (ночь)', start: e, end: s, color: 'var(--navy)' }]);
    touch();
  };
  $('#cl-cat-start').onchange = catChange;
  $('#cl-cat-end').onchange = catChange;
  $$('[data-weight]', host).forEach(i => i.onchange = () => {
    const v = Math.max(1, Math.round(Number(i.value) || 1));
    i.value = v; d.weights[i.dataset.weight] = v; touch();
  });
  settingsBindOrderList(host, 'cascade', d, touch);
  settingsBindOrderList(host, 'placement', d, touch);
  settingsBindDraftBar(host);
}

/* Полоса суток 00–24: окно или категория как процентная полоса; переход через
   полночь рисуется двумя кусками (ДН 22:00–06:00). */
function settingsTimeline(rows) {
  const pct = m => ((Number(m) || 0) / 1440) * 100;
  return `<div class="timeline">
    <div class="tl-scale">${[0, 4, 8, 12, 16, 20, 24].map(h => `<span>${h}</span>`).join('')}</div>
    ${rows.map(r => {
      const s = Number(r.start) || 0, e = Number(r.end) || 0;
      const bars = s < e
        ? [{ a: s, b: e }]
        : [{ a: s, b: 1440 }, { a: 0, b: e }];
      return `<div class="tl-row"><span class="lbl" title="${esc(r.label)}">${esc(r.label)}</span>
        <div class="tl-track">${bars.map(x => `<div class="tl-bar" style="left:${pct(x.a)}%;width:${Math.max(pct(x.b) - pct(x.a), 0)}%;background:${cssColor(r.color)}">
          ${x.b - x.a >= 120 ? esc(`${settingsHm(x.a)}–${settingsHm(x.b)}`) : ''}</div>`).join('')}</div></div>`;
    }).join('')}
  </div>`;
}

function settingsOrderList(key, order, edit) {
  return `<div class="order-list" data-order="${key}">${order.map((code, i) => `
    <span class="item${code === 'ДН2' || code === 'ДЯ2' ? '' : ''}">
      <span class="n">${i + 1}</span>${esc(code)}
      ${edit ? `<button data-move="${esc(code)}" data-dir="-1" ${i === 0 ? 'disabled' : ''} title="Раньше">‹</button>
      <button data-move="${esc(code)}" data-dir="1" ${i === order.length - 1 ? 'disabled' : ''} title="Позже">›</button>` : ''}
    </span>${i < order.length - 1 ? '<span class="arrow">→</span>' : ''}`).join('')}</div>`;
}
function settingsBindOrderList(host, key, draft, touch) {
  const field = key === 'cascade' ? 'cascade_order' : 'placement_order';
  $$(`[data-order="${key}"] [data-move]`, host).forEach(b => b.onclick = () => {
    const list = draft[field] || [];
    const i = list.indexOf(b.dataset.move);
    const j = i + Number(b.dataset.dir);
    if (i < 0 || j < 0 || j >= list.length) return;
    [list[i], list[j]] = [list[j], list[i]];
    draft[field] = list;
    const wrap = $(`[data-order="${key}"]`, host);
    if (wrap) wrap.outerHTML = settingsOrderList(key, list, true);
    settingsBindOrderList(host, key, draft, touch);
    touch();
  });
}
