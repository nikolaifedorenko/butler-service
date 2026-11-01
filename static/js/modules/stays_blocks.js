/* ══════════════════════════════════════════════════════════════════════
   «ШАХМАТКА» — вкладка «Блоки» и карточка блока с сеткой «категория × ночь»
   (спецификация docs/superpowers/specs/2026-10-27-stays-ooo-blocks-design.md §3.2, §6, §7).
   Список — как «Брони»: фильтры, сортировка и срез страницы на сервере (GET /api/stays/blocks).
   Карточка: строки сетки — категории, столбцы — ночи блока (прокрутка внутри карточки), в клетке
   остаток; клетки выделяются (клик + shift-клик или протяжка) и получают число; помощник
   «заполнить»; «разложено / нехватка» по клеткам — из ответа сервера. Правки копятся в карточке,
   «Проверить» показывает, кто останется без объекта и где блоку не хватит, «Сохранить» отправляет
   сетку целиком. Видят все уровни доступа, пишет только stays.edit.
   Здесь же — общие для списков блоков и OOO помощники периода, выбора из списка и поиска.
   Использует хелперы app.js: $ $$ esc api openModal closeModal toast can dateRu loadGenerationFor.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

/* колонки: ключ сортировки сервера (null — без сортировки) — заголовок */
const STAYS_BLOCK_COLS = [['title', 'Название'], ['start', 'С'], ['end', 'По'], ['nights', 'Ночей'],
  [null, 'Остаток по категориям'], ['placed', 'Разложено'], ['short', 'Нехватка']];
const STAYS_BLOCK_PAGE = 200;
const STAYS_BLOCK_MAX_NIGHTS = 366;       // как MAX_NIGHTS сервера: поля дат это ограничивают

function staysBlockEmpty() {
  return { mode: 'month', first: '', last: '', category_ids: [], short_only: false, q: '', focusQ: false,
    sort: 'start', dir: 'asc' };
}
const staysBlock = staysBlockEmpty();

/* ─────────────── Общие помощники списков блоков и OOO ─────────────── */
/* период: месяц разделов, свой диапазон или все даты; null — без ограничения */
function staysPeriodRange(st) {
  if (st.mode === 'all') return null;
  return st.mode === 'custom' && st.first && st.last ? { first: st.first, last: st.last } : staysMonthRange();
}
function staysPeriodBar(st) {
  const range = staysPeriodRange(st) || staysMonthRange();
  return `<select id="pd-mode" title="Период списка (пересечение с периодом)">
      <option value="month"${st.mode === 'month' ? ' selected' : ''}>Месяц разделов</option>
      <option value="custom"${st.mode === 'custom' ? ' selected' : ''}>Свой период</option>
      <option value="all"${st.mode === 'all' ? ' selected' : ''}>Все даты</option></select>
    ${st.mode === 'custom'
    ? `<input type="date" id="pd-first" value="${esc(range.first)}" max="${esc(range.last)}" title="Начало периода">
      <input type="date" id="pd-last" value="${esc(range.last)}" min="${esc(range.first)}" title="Конец периода">`
    : st.mode === 'month' ? staysMonthNav() : ''}`;
}
function staysPeriodBind(body, st, rerender) {
  if (st.mode === 'month') staysBindMonthNav(body, rerender);
  $('#pd-mode', body).onchange = e => {
    st.mode = e.target.value;
    if (st.mode === 'custom' && !(st.first && st.last)) ({ first: st.first, last: st.last } = staysMonthRange());
    rerender();
  };
  const first = $('#pd-first', body);
  if (!first) return;
  const last = $('#pd-last', body);
  first.onchange = () => {
    if (!first.value) return;
    st.first = first.value;
    if (st.last < st.first) st.last = st.first;
    rerender();
  };
  last.onchange = () => {
    if (!last.value) return;
    st.last = last.value;
    if (st.last < st.first) { toast('Конец периода раньше начала', 'warn'); st.last = st.first; }
    rerender();
  };
}
/* поиск: запрос уходит после паузы, фокус и курсор переживают перерисовку вкладки */
function staysSearchBind(input, st, rerender) {
  if (st.focusQ) {
    st.focusQ = false;
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  }
  let timer = null;
  input.oninput = () => {
    clearTimeout(timer);
    timer = setTimeout(() => { st.q = input.value; st.focusQ = true; rerender(); }, 350);
  };
}
/* выпадающий список флажков (как «Статусы» во вкладке «Брони»); состояние раскрытия — staysFilterOpen */
function staysPickHtml(key, title, items, chosen) {
  const picked = items.filter(([v]) => chosen.includes(v)).map(([, t]) => t);
  return `<details class="sf-dd" data-pk-dd="${key}"${staysFilterOpen.has('pk-' + key) ? ' open' : ''}>
    <summary>${esc(title)}: <b>${esc(picked.length ? picked.join(', ') : 'все')}</b></summary>
    <div class="sf-list">${items.map(([v, t]) => `<label class="chk">
      <input type="checkbox" data-pk-${key}="${esc(String(v))}"${chosen.includes(v) ? ' checked' : ''}> ${esc(t)}</label>`).join('')
      || '<span class="muted">нет</span>'}</div></details>`;
}
function staysPickBind(body, key, cast, onChange) {
  $$(`[data-pk-${key}]`, body).forEach(cb => {
    cb.onchange = () => onChange($$(`[data-pk-${key}]`, body).filter(x => x.checked).map(x => cast(x.getAttribute(`data-pk-${key}`))));
  });
  $$(`[data-pk-dd="${key}"]`, body).forEach(d => {
    d.addEventListener('toggle', () => { if (d.open) staysFilterOpen.add('pk-' + key); else staysFilterOpen.delete('pk-' + key); });
  });
}

/* ─────────────── Вкладка «Блоки» ─────────────── */
function staysBlockParams() {
  const b = staysBlock;
  const p = new URLSearchParams({ sort: b.sort, dir: b.dir });
  const range = staysPeriodRange(b);
  if (range) { p.set('first', range.first); p.set('last', range.last); }
  b.category_ids.forEach(v => p.append('category_ids', v));
  if (b.short_only) p.set('short_only', '1');
  if (b.q.trim()) p.set('q', b.q.trim());
  return p;
}

function staysBlockRowHtml(r) {
  const top = r.top.map(t => `${t.code} до ${t.max}`).join(', ');
  return `<tr class="bk-row" data-bl-row="${r.id}" tabindex="0">
    <td>${esc(r.title)}</td><td>${esc(dateRu(r.start))}</td><td>${esc(dateRu(r.end))}</td><td>${r.nights}</td>
    <td>${esc(top || '—')}</td><td>${r.placed}</td>
    <td>${r.short ? `<span class="sp-warn" title="Нехватка: клеток «категория × ночь» без объекта">нехватка ${r.missing}</span>` : '—'}</td></tr>`;
}

function staysBlockTableHtml(rows, total) {
  const arrow = key => (staysBlock.sort === key ? (staysBlock.dir === 'asc' ? ' ↑' : ' ↓') : '');
  return `<div class="muted" id="bl-total">Найдено блоков: ${total}${rows.length < total ? ` · показано ${rows.length}` : ''}</div>
    <div class="sb-scroll"><table class="bk-table"><thead><tr>${STAYS_BLOCK_COLS.map(([k, t]) => (k
    ? `<th data-bl-sort="${k}" title="Сортировать" style="cursor:pointer">${esc(t)}${arrow(k)}</th>` : `<th>${esc(t)}</th>`)).join('')}</tr></thead>
    <tbody>${rows.map(staysBlockRowHtml).join('')
    || `<tr><td colspan="${STAYS_BLOCK_COLS.length}" class="empty">Блоков по фильтру нет</td></tr>`}</tbody></table></div>
    ${rows.length < total ? `<button class="btn" id="bl-more">Показать ещё ${Math.min(STAYS_BLOCK_PAGE, total - rows.length)}</button>` : ''}`;
}

async function renderBlocksTab(body) {
  const fund = await staysFund();
  const fresh = loadGenerationFor(body);
  const b = staysBlock;
  let rows = [];
  let total = 0;
  let error = '';
  const page = offset => {
    const p = staysBlockParams();
    p.set('offset', offset);
    p.set('limit', STAYS_BLOCK_PAGE);
    return api('/api/stays/blocks?' + p, { silent: true });
  };
  try {
    ({ rows, total } = await page(0));
  } catch (e) {
    error = e.message;
    toast(error, 'warn');
  }
  if (!fresh()) return;
  body.innerHTML = `<div class="sb-toolbar">${staysPeriodBar(b)}
    ${staysPickHtml('cat', 'Категории', fund.categories.map(c => [c.id, c.code]), b.category_ids)}
    <label class="chk"><input type="checkbox" id="bl-short"${b.short_only ? ' checked' : ''}> с нехваткой</label>
    <input type="search" id="bl-q" placeholder="название блока" value="${esc(b.q)}">
    ${can('stays.edit') ? '<button class="btn btn-sm btn-primary" id="bl-new">+ Блок</button>' : ''}</div>
    <div id="bl-result"></div>`;
  const rerender = () => renderBlocksTab(body);
  staysPeriodBind(body, b, rerender);
  staysSearchBind($('#bl-q', body), b, rerender);
  staysPickBind(body, 'cat', Number, v => { b.category_ids = v; rerender(); });
  $('#bl-short', body).onchange = e => { b.short_only = e.target.checked; rerender(); };
  const result = $('#bl-result', body);
  const paint = () => {
    result.innerHTML = error ? `<div class="panel"><p class="muted">${esc(error)}</p></div>` : staysBlockTableHtml(rows, total);
    const more = $('#bl-more', result);
    if (more) more.onclick = async () => {
      more.disabled = true;
      try {
        const next = await page(rows.length);
        if (!fresh()) return;
        rows = rows.concat(next.rows);
        total = next.total;
      } catch (e) { toast(e.message, 'warn'); }
      paint();
    };
  };
  paint();
  result.onclick = e => {
    const th = e.target.closest('[data-bl-sort]');
    if (th) {
      const key = th.dataset.blSort;
      if (b.sort === key) b.dir = b.dir === 'asc' ? 'desc' : 'asc'; else { b.sort = key; b.dir = 'asc'; }
      rerender();
      return;
    }
    const tr = e.target.closest('[data-bl-row]');
    if (tr) openBlockCard(Number(tr.dataset.blRow), rerender).catch(err => toast(err.message, 'warn'));
  };
  result.onkeydown = e => {
    const tr = e.target.closest?.('[data-bl-row]');
    if (tr && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); tr.click(); }
  };
  const add = $('#bl-new', body);
  if (add) add.onclick = () => openBlockCard(null, rerender).catch(err => toast(err.message, 'warn'));
}

/* ─────────────── Карточка блока ─────────────── */
/* ночи блока [start, end): не больше STAYS_BLOCK_MAX_NIGHTS; пустой список при неверных датах */
function staysBlockNights(start, end) {
  const out = [];
  if (!start || !end) return out;
  for (let d = start; d < end && out.length < STAYS_BLOCK_MAX_NIGHTS; d = staysAddDays(d, 1)) out.push(d);
  return out;
}
const staysGridCopy = g => Object.fromEntries(Object.entries(g || {}).map(([c, by]) => [c, { ...by }]));

/* клетка сетки: остаток; если блок сохранён и клетка не менялась — «разложено / нехватка» сервера */
function staysBlockCellHtml(c, n, qty, missing, dirty) {
  const short = missing > 0 && !dirty;
  const title = short ? `разложено ${qty - missing} из ${qty}, не хватает ${missing}` : qty ? `остаток ${qty}` : '';
  return `<td class="bg-cell${short ? ' short' : ''}${dirty ? ' dirty' : ''}" data-bg-c="${c}" data-bg-n="${esc(n)}" title="${esc(title)}">${
    qty ? `${qty}${short ? `<small>−${missing}</small>` : ''}` : ''}</td>`;
}

/* шапка: месяцы с colspan, под ними числа и дни недели */
function staysBlockHeadHtml(nights) {
  const months = [];
  nights.forEach(n => {
    const key = n.slice(0, 7);
    if (months.length && months[months.length - 1].key === key) months[months.length - 1].span++;
    else months.push({ key, span: 1, title: `${MONTHS[Number(n.slice(5, 7)) - 1]} ${n.slice(0, 4)}` });
  });
  return `<tr><th class="bg-cat" rowspan="2">Категория</th>${months.map(m =>
    `<th class="bg-month" colspan="${m.span}">${esc(m.title)}</th>`).join('')}</tr>
    <tr>${nights.map(n => {
    const wd = new Date(n + 'T12:00:00Z').getUTCDay();
    return `<th class="bg-day${wd === 0 || wd === 6 ? ' we' : ''}" data-bg-h="${esc(n)}">${Number(n.slice(8))}<small>${esc(WD_SHORT[(wd + 6) % 7])}</small></th>`;
  }).join('')}</tr>`;
}

async function openBlockCard(id, onChanged) {
  const [fund, card] = await Promise.all([staysFund(), id ? api('/api/stays/blocks/' + id) : Promise.resolve(null)]);
  const edit = can('stays.edit');
  const st = { id: card ? card.id : null, version: card?.version, title: card?.title || '',
    start: card?.start || staysToday(), end: card?.end || staysAddDays(staysToday(), 3),
    grid: staysGridCopy(card?.grid), saved: staysGridCopy(card?.grid), short: card?.short || [],
    placed: card?.placed ?? 0, missing: card?.missing ?? 0,
    sel: null, anchor: null };
  /* строки: категории фонда + категории, оставшиеся в сетке (их уже нет в сегодняшнем фонде) */
  const rowsOf = () => {
    const rows = fund.categories.map(c => ({ id: String(c.id), code: c.code }));
    Object.keys(st.grid).forEach(cid => { if (!rows.some(r => r.id === cid)) rows.push({ id: cid, code: '#' + cid }); });
    return rows;
  };
  const codeOf = cid => rowsOf().find(r => r.id === String(cid))?.code || '#' + cid;
  /* нехватка сохранённого блока по клеткам: категория → ночь → не хватает */
  const missingMap = () => {
    const out = {};
    st.short.forEach(s => {
      for (let d = s.first; d <= s.last; d = staysAddDays(d, 1)) (out[s.category_id] ||= {})[d] = s.missing;
    });
    return out;
  };
  const title = () => (st.id ? `Блок · ${st.title}` : 'Новый блок');
  const gridBody = () => {
    const nights = staysBlockNights(st.start, st.end);
    const rows = rowsOf();
    const miss = missingMap();
    const sums = nights.map(n => rows.reduce((a, r) => a + (st.grid[r.id]?.[n] || 0), 0));
    return `<table class="bg-table" aria-label="Остатки блока по категориям и ночам">
      <thead>${staysBlockHeadHtml(nights)}</thead>
      <tbody>${rows.map(r => `<tr><th class="bg-cat" scope="row">${esc(r.code)}</th>${nights.map(n => {
    const q = st.grid[r.id]?.[n] || 0;
    const dirty = q !== (st.saved[r.id]?.[n] || 0);
    return staysBlockCellHtml(r.id, n, q, miss[r.id]?.[n] || 0, dirty);
  }).join('')}</tr>`).join('')}
      <tr class="bg-sum"><th class="bg-cat" scope="row">Всего</th>${sums.map(s => `<td>${s || ''}</td>`).join('')}</tr></tbody></table>`;
  };
  const summaryHtml = () => {
    if (!st.id) return '<span class="muted">Сохраните блок — сервер покажет, сколько разложено по объектам и где не хватает</span>';
    return `Разложено по объектам: <b>${st.placed}</b>${st.missing ? ` · <span class="sp-warn">нехватка: <b>${st.missing}</b></span>` : ''}
      ${st.short.map(x => `<div class="sp-warn" data-block-short>⚠ ${esc(codeOf(x.category_id))}: не хватает ${x.missing} с ${esc(dateRu(x.first))} по ${esc(dateRu(x.last))}</div>`).join('')}`;
  };
  const controls = () => `
    <div class="bg-tools">
      <div class="bg-tool"><b>Выделение</b> <span id="bg-sel-info" class="muted">клик по клетке, shift-клик или протяжка — диапазон</span>
        <input type="number" id="bg-qty" min="0" max="500" value="1" title="Остаток для выделенных клеток">
        <button class="btn btn-sm" id="bg-set">Задать число</button>
        <button class="btn btn-sm btn-ghost" id="bg-clear" title="Убрать остаток у выделенных клеток">Очистить</button></div>
      <div class="bg-tool"><b>Заполнить</b>
        <select id="bg-fill-cat" title="Категория">${rowsOf().map(r => `<option value="${esc(r.id)}">${esc(r.code)}</option>`).join('')}</select>
        <input type="date" id="bg-fill-from" title="Первая ночь"><input type="date" id="bg-fill-to" title="Последняя ночь">
        <input type="number" id="bg-fill-qty" min="0" max="500" value="1" title="Остаток">
        <button class="btn btn-sm" id="bg-fill">Заполнить</button></div></div>`;

  openModal({
    title: title(), wide: true,
    subtitle: edit ? 'Остаток по категориям на каждую ночь: блок держит объекты категории под группу. «Проверить» покажет, кто останется без объекта'
      : 'Остаток по категориям на каждую ночь',
    body: `<div class="grid-2">
        ${sfRow('Название', `<input id="bg-title" type="text" maxlength="120" value="${esc(st.title)}"${edit ? '' : ' disabled'}>`)}
        <div class="grid-2">${sfRow('С', sfInput('bg-start', st.start, 'date').replace('<input', `<input${edit ? '' : ' disabled'}`))}
          ${sfRow('По (выезд)', sfInput('bg-end', st.end, 'date').replace('<input', `<input${edit ? '' : ' disabled'}`))}</div>
      </div>
      <div id="bg-summary" class="bg-summary">${summaryHtml()}</div>
      ${edit ? controls() : ''}
      <div class="bg-wrap" id="bg-wrap"></div>
      <div id="bg-note" class="muted"></div>
      <div id="rf-preview-out" class="sp-out"></div>`,
    footer: `${edit && st.id ? '<button class="btn btn-danger" id="bg-delete">Удалить…</button>' : ''}
      ${edit ? staysFormFoot() : '<button class="btn btn-ghost" data-close>Закрыть</button>'}`,
    onMount(m) {
      m.classList.add('v4-xl');
      const wrap = $('#bg-wrap', m);
      const out = () => $('#rf-preview-out', m);
      let cells = [];
      let dragging = false;

      /* выделение — прямоугольник строк × ночей; индексы клетки лежат в data-r / data-i */
      const paintSel = () => {
        const s = st.sel;
        cells.forEach(td => {
          const r = Number(td.dataset.r), i = Number(td.dataset.i);
          td.classList.toggle('sel', !!s && r >= s.r0 && r <= s.r1 && i >= s.i0 && i <= s.i1);
        });
        const info = $('#bg-sel-info', m);
        if (info) {
          if (!s) { info.textContent = 'клик по клетке, shift-клик или протяжка — диапазон'; return; }
          const rows = rowsOf(), nights = staysBlockNights(st.start, st.end);
          info.textContent = `${rows[s.r0].code}${s.r1 > s.r0 ? '–' + rows[s.r1].code : ''} · ${dateRu(nights[s.i0])}${s.i1 > s.i0 ? '–' + dateRu(nights[s.i1]) : ''}`
            + ` · клеток: ${(s.r1 - s.r0 + 1) * (s.i1 - s.i0 + 1)}`;
        }
      };
      const paintGrid = () => {
        wrap.innerHTML = gridBody();
        cells = $$('.bg-table td[data-bg-c]', wrap);
        const rowIdx = Object.fromEntries(rowsOf().map((r, k) => [r.id, k]));
        const nightIdx = Object.fromEntries(staysBlockNights(st.start, st.end).map((n, k) => [n, k]));
        cells.forEach(td => { td.dataset.r = rowIdx[td.dataset.bgC]; td.dataset.i = nightIdx[td.dataset.bgN]; });
        const outside = Object.values(st.grid).reduce((a, by) => a + Object.keys(by).filter(n => !(n >= st.start && n < st.end)).length, 0);
        $('#bg-note', m).textContent = outside ? `Ночей вне дат блока: ${outside} — при сохранении они удалятся` : '';
        $('#bg-summary', m).innerHTML = summaryHtml();
        $('.modal-head h3', m).textContent = title();
        paintSel();
      };
      const rectTo = td => {
        const r = Number(td.dataset.r), i = Number(td.dataset.i);
        const a = st.anchor || { r, i };
        st.sel = { r0: Math.min(a.r, r), r1: Math.max(a.r, r), i0: Math.min(a.i, i), i1: Math.max(a.i, i) };
      };
      const touch = () => foot.reset();      // правка полей и сетки снимает запрет «не сохранится»
      /* число в выделенные клетки: 0 убирает остаток */
      const setCells = (cids, nights, qty) => {
        cids.forEach(cid => {
          nights.forEach(n => {
            if (qty > 0) (st.grid[cid] ||= {})[n] = qty;
            else if (st.grid[cid]) delete st.grid[cid][n];
          });
        });
        touch();
        paintGrid();
      };
      const readQty = id => {
        const q = Number($(id, m).value);
        if (!Number.isInteger(q) || q < 0 || q > 500) { toast('Остаток — целое число от 0 до 500', 'warn'); return null; }
        return q;
      };

      wrap.addEventListener('click', e => {
        const td = e.target.closest('td[data-bg-c]');
        if (!td) return;
        if (!e.shiftKey || !st.anchor) st.anchor = { r: Number(td.dataset.r), i: Number(td.dataset.i) };
        rectTo(td);
        paintSel();
      });
      wrap.addEventListener('mousedown', e => {
        const td = e.target.closest('td[data-bg-c]');
        if (!td || e.button !== 0) return;
        if (!e.shiftKey || !st.anchor) st.anchor = { r: Number(td.dataset.r), i: Number(td.dataset.i) };
        dragging = true;
        rectTo(td);
        paintSel();
      });
      wrap.addEventListener('mouseover', e => {
        const td = dragging && (e.buttons & 1) && e.target.closest('td[data-bg-c]');
        if (td) { rectTo(td); paintSel(); }
      });
      m.addEventListener('mouseup', () => { dragging = false; });

      const title$ = $('#bg-title', m);
      title$.oninput = () => { st.title = title$.value; };
      const dates = () => {
        st.start = $('#bg-start', m).value || st.start;
        st.end = $('#bg-end', m).value || st.end;
        st.sel = null; st.anchor = null;
        touch();
        paintGrid();
      };
      $('#bg-start', m).onchange = dates;
      $('#bg-end', m).onchange = dates;

      if (edit) {
        const syncFill = () => {
          const nights = staysBlockNights(st.start, st.end);
          $('#bg-fill-from', m).value = nights[0] || '';
          $('#bg-fill-to', m).value = nights[nights.length - 1] || '';
        };
        syncFill();
        $('#bg-start', m).addEventListener('change', syncFill);
        $('#bg-end', m).addEventListener('change', syncFill);
        $('#bg-set', m).onclick = () => {
          if (!st.sel) { toast('Выделите клетки сетки', 'warn'); return; }
          const q = readQty('#bg-qty');
          if (q === null) return;
          const rows = rowsOf(), nights = staysBlockNights(st.start, st.end);
          setCells(rows.slice(st.sel.r0, st.sel.r1 + 1).map(r => r.id), nights.slice(st.sel.i0, st.sel.i1 + 1), q);
        };
        $('#bg-clear', m).onclick = () => {
          if (!st.sel) { toast('Выделите клетки сетки', 'warn'); return; }
          const rows = rowsOf(), nights = staysBlockNights(st.start, st.end);
          setCells(rows.slice(st.sel.r0, st.sel.r1 + 1).map(r => r.id), nights.slice(st.sel.i0, st.sel.i1 + 1), 0);
        };
        $('#bg-fill', m).onclick = () => {
          const from = $('#bg-fill-from', m).value, to = $('#bg-fill-to', m).value;
          const q = readQty('#bg-fill-qty');
          if (q === null) return;
          if (!from || !to || to < from) { toast('Укажите ночи «с — по»: конец не раньше начала', 'warn'); return; }
          if (from < st.start || to >= st.end) {
            toast(`Ночи вне блока: можно с ${dateRu(st.start)} по ${dateRu(staysAddDays(st.end, -1))}`, 'warn');
            return;
          }
          setCells([$('#bg-fill-cat', m).value], staysBlockNights(from, staysAddDays(to, 1)), q);
        };
      }

      /* тело запроса: сетка целиком, только ночи внутри дат блока */
      const body = () => {
        const grid = {};
        Object.entries(st.grid).forEach(([cid, by]) => {
          const kept = Object.fromEntries(Object.entries(by).filter(([n, q]) => q > 0 && n >= st.start && n < st.end));
          if (Object.keys(kept).length) grid[cid] = kept;
        });
        return { title: st.title, start: st.start, end: st.end, grid, ...(st.id ? { version: st.version } : {}) };
      };
      const url = () => (st.id ? `/api/stays/blocks/${st.id}` : '/api/stays/blocks');
      const method = () => (st.id ? 'PUT' : 'POST');
      const editFlow = {
        async preview() {
          const r = await api(`${url()}?preview=1`, { method: method(), body: body() });
          renderPreview(r.diff, out(), r.overbook_refused);
          const dropped = r.result?.dropped?.length;
          if (dropped) out().insertAdjacentHTML('beforeend', `<div class="sp-warn">Уйдут ночи вне новых дат: ${dropped}</div>`);
          return r;
        },
        save: () => api(url(), { method: method(), body: body() }),
      };
      let mode = editFlow;
      /* после записи карточка остаётся открытой и показывает ответ сервера: разложено / нехватка */
      const reload = async result => {
        if (onChanged) onChanged();
        const fresh = await api('/api/stays/blocks/' + result.result.id);
        Object.assign(st, { id: fresh.id, version: fresh.version, title: fresh.title, start: fresh.start, end: fresh.end,
          grid: staysGridCopy(fresh.grid), saved: staysGridCopy(fresh.grid), short: fresh.short,
          placed: fresh.placed, missing: fresh.missing, sel: null, anchor: null });
        $('#bg-title', m).value = st.title; $('#bg-start', m).value = st.start; $('#bg-end', m).value = st.end;
        out().innerHTML = '';
        paintGrid();
        if (!$('#bg-delete', m)) m.querySelector('.modal-foot').insertAdjacentHTML('afterbegin', '<button class="btn btn-danger" id="bg-delete">Удалить…</button>');
        bindDelete();
      };
      let foot = { reset() {} };
      if (edit) {
        foot = staysBindGatedFoot(m, { preview: () => mode.preview(), save: () => mode.save() }, {
          okText: 'Блок сохранён', out,
          done: r => (mode === editFlow ? reload(r).catch(err => toast(err.message, 'warn')) : (closeModal(), onChanged && onChanged())),
        });
      } else {
        $('[data-close]', m).onclick = closeModal;
      }
      const bindDelete = () => {
        const del = $('#bg-delete', m);
        if (!del) return;
        del.onclick = async () => {
          const path = `/api/stays/blocks/${st.id}?version=${st.version}`;
          mode = {
            async preview() {
              const r = await api(`${path}&preview=1`, { method: 'DELETE' });
              renderPreview(r.diff, out(), r.overbook_refused);
              return r;
            },
            save: () => api(path, { method: 'DELETE' }),
          };
          $('[data-save]', m).textContent = 'Удалить';
          try { await mode.preview(); } catch (e) { toast(e.message, 'err'); }
        };
      };
      bindDelete();
      paintGrid();
    },
  });
}
