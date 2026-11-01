/* ══════════════════════════════════════════════════════════════════════
   «ШАХМАТКА» — вкладка «OOO»: объекты не в продаже по половинкам суток
   (спецификация docs/superpowers/specs/2026-10-27-stays-ooo-blocks-design.md §3.1, §6, §7).
   Список видят все уровни доступа (имён гостей в OOO нет); запись — только stays.edit, всегда с
   предпросмотром «кто переедет». Фильтры и сортировка — на сервере (GET /api/stays/ooo), как
   во вкладке «Брони»; период и поиск — общие помощники из stays_blocks.js.
   Использует хелперы app.js: $ $$ esc api openModal closeModal toast can dateRu loadGenerationFor.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

/* колонки: ключ сортировки сервера — заголовок */
const STAYS_OOO_COLS = [['unit', 'Объект'], ['category', 'Категория'], ['start', 'С'], ['end', 'По'],
  ['reason', 'Причина'], ['author', 'Поставил'], ['created_at', 'Создано']];
const STAYS_OOO_PAGE = 200;

function staysOooEmpty() { return { mode: 'month', first: '', last: '', q: '', focusQ: false, sort: 'start', dir: 'asc' }; }
const staysOoo = staysOooEmpty();

function staysOooParams() {
  const o = staysOoo;
  const p = staysFundParams(new URLSearchParams({ sort: o.sort, dir: o.dir }));
  const range = staysPeriodRange(o);
  if (range) { p.set('first', range.first); p.set('last', range.last); }
  if (o.q.trim()) p.set('q', o.q.trim());
  return p;
}

/* «с вечера» / «с утра» и «до утра» / «до вечера»: половинки суток, как в форме */
const staysOooStart = r => `${dateRu(r.start)} ${r.start_half === 'AM' ? 'с утра' : 'с вечера'}`;
const staysOooEnd = r => `${dateRu(r.end)} ${r.end_half === 'PM' ? 'до вечера' : 'до утра'}`;

function staysOooRowHtml(r, editable) {
  return `<tr class="${editable ? 'bk-row' : ''}" data-oo-row="${r.id}"${editable ? ' tabindex="0"' : ''}>
    <td title="${esc(r.group)}">${esc(r.unit)}${r.group ? ` <span class="muted">${esc(r.group)}</span>` : ''}</td>
    <td>${esc(r.category || '—')}</td><td>${esc(staysOooStart(r))}</td><td>${esc(staysOooEnd(r))}</td>
    <td>${esc(r.reason || '—')}</td><td>${esc(r.author || '—')}</td>
    <td>${esc(r.created_at.slice(0, 16).replace('T', ' '))}</td></tr>`;
}

function staysOooTableHtml(rows, total) {
  const arrow = key => (staysOoo.sort === key ? (staysOoo.dir === 'asc' ? ' ↑' : ' ↓') : '');
  const editable = can('stays.edit');
  return `<div class="muted" id="oo-total">Найдено OOO: ${total}${rows.length < total ? ` · показано ${rows.length}` : ''}</div>
    <div class="sb-scroll"><table class="bk-table"><thead><tr>${STAYS_OOO_COLS.map(([k, t]) =>
    `<th data-oo-sort="${k}" title="Сортировать" style="cursor:pointer">${esc(t)}${arrow(k)}</th>`).join('')}</tr></thead>
    <tbody>${rows.map(r => staysOooRowHtml(r, editable)).join('')
    || `<tr><td colspan="${STAYS_OOO_COLS.length}" class="empty">OOO по фильтру нет</td></tr>`}</tbody></table></div>
    ${rows.length < total ? `<button class="btn" id="oo-more">Показать ещё ${Math.min(STAYS_OOO_PAGE, total - rows.length)}</button>` : ''}`;
}

async function renderOooTab(body) {
  const fund = await staysFund();
  const fresh = loadGenerationFor(body);
  const o = staysOoo;
  let rows = [];
  let total = 0;
  let error = '';
  const page = offset => {
    const p = staysOooParams();
    p.set('offset', offset);
    p.set('limit', STAYS_OOO_PAGE);
    return api('/api/stays/ooo?' + p, { silent: true });
  };
  try {
    ({ rows, total } = await page(0));
  } catch (e) {
    error = e.message;
    toast(error, 'warn');
  }
  if (!fresh()) return;
  body.innerHTML = `<div class="sb-toolbar">${staysPeriodBar(o)}
      <input type="search" id="oo-q" placeholder="причина или объект" value="${esc(o.q)}">
      ${can('stays.edit') ? '<button class="btn btn-sm btn-primary" id="oo-new">+ OOO</button>' : ''}</div>
    <div data-sf-slot></div><div id="oo-result"></div>`;
  const rerender = () => renderOooTab(body);
  staysPanelInto(body, fund, rerender, { people: false });
  staysPeriodBind(body, o, rerender);
  staysSearchBind($('#oo-q', body), o, rerender);
  const result = $('#oo-result', body);
  const paint = () => {
    result.innerHTML = error ? `<div class="panel"><p class="muted">${esc(error)}</p></div>` : staysOooTableHtml(rows, total);
    const more = $('#oo-more', result);
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
    const th = e.target.closest('[data-oo-sort]');
    if (th) {
      const key = th.dataset.ooSort;
      if (o.sort === key) o.dir = o.dir === 'asc' ? 'desc' : 'asc'; else { o.sort = key; o.dir = 'asc'; }
      rerender();
      return;
    }
    const tr = e.target.closest('[data-oo-row]');
    if (tr && can('stays.edit')) openOooForm(rows.find(r => r.id === Number(tr.dataset.ooRow)), rerender).catch(err => toast(err.message, 'warn'));
  };
  result.onkeydown = e => {
    const tr = e.target.closest?.('[data-oo-row]');
    if (tr && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); tr.click(); }
  };
  const add = $('#oo-new', body);
  if (add) add.onclick = () => openOooForm(null, rerender).catch(err => toast(err.message, 'warn'));
}

/* ─────────────── Форма OOO: создание, правка, удаление — с предпросмотром ─────────────── */
/* src — id, null (новое), либо уже загруженная запись (строка списка, полоса шахматки, табло дня:
   там причина лежит в title); onChanged — обновить вид после записи */
async function openOooForm(src, onChanged) {
  const fund = await staysFund();
  let hold = src || {};
  if (typeof src === 'number') {
    hold = (await api('/api/stays/ooo?limit=200', { silent: true })).rows.find(r => r.id === src);
    if (!hold) throw new Error('OOO не найден — обновите список');
  }
  const reason = hold.reason ?? hold.title ?? '';
  const isNew = !hold.id;
  const first = hold.start || staysToday();
  /* «с утра» (start_half = AM) и «до вечера» (end_half = PM) — сутки целиком; новое OOO — целые сутки */
  const wholeStart = isNew || hold.start_half === 'AM';
  const wholeEnd = isNew || hold.end_half === 'PM';
  const units = fund.units.filter(u => u.active).map(u => [u.id, u.label]);
  if (hold.unit_id && !units.some(([id]) => id === hold.unit_id)) units.push([hold.unit_id, hold.unit || '№' + hold.unit_id]);
  openModal({
    title: isNew ? 'OOO — не в продаже' : `OOO · ${dateRu(hold.start)}–${dateRu(hold.end)}`,
    subtitle: 'Объект не в продаже: по умолчанию с вечера «с» до утра «по»; галочки — сутки целиком. Брони на эти дни перераспределятся. Блоки по категориям — на вкладке «Блоки»',
    body: `<div class="grid-2">
        ${sfRow('Объект', sfSelect('hf-unit', units, hold.unit_id))}
        <div></div>
        ${sfRow('С', sfInput('hf-start', first, 'date'))}
        ${sfRow('По', sfInput('hf-end', hold.end || first, 'date'))}
        ${sfCheck('hf-start-am', 'С утра', wholeStart)}
        ${sfCheck('hf-end-pm', 'До вечера', wholeEnd)}
      </div>
      ${sfRow('Причина', `<input id="hf-title" type="text" maxlength="120" value="${esc(reason)}">`)}
      <div class="muted" data-hf-hint>без имён гостей — видно всем</div>
      <div id="rf-preview-out" class="sp-out"></div>`,
    footer: `${isNew ? '' : '<button class="btn btn-danger" id="hf-delete">Удалить…</button>'}${staysFormFoot()}`,
    onMount(m) {
      const out = () => $('#rf-preview-out', m);
      const body = () => ({ unit_id: Number($('#hf-unit', m).value),
        start: $('#hf-start', m).value, end: $('#hf-end', m).value,
        start_half: $('#hf-start-am', m).checked ? 'AM' : 'PM', end_half: $('#hf-end-pm', m).checked ? 'PM' : 'AM',
        reason: $('#hf-title', m).value, ...(isNew ? {} : { version: hold.version }) });
      const edit = previewThenSave({ url: isNew ? '/api/stays/ooo' : `/api/stays/ooo/${hold.id}`,
        method: isNew ? 'POST' : 'PUT', body, out });
      const del = `/api/stays/ooo/${hold.id}?version=${hold.version}`;
      const remove = {
        async preview() {
          const r = await api(`${del}&preview=1`, { method: 'DELETE' });
          renderPreview(r.diff, out(), r.overbook_refused);
          return r;
        },
        save: () => api(del, { method: 'DELETE' }),
      };
      let mode = edit;
      staysBindGatedFoot(m, { preview: () => mode.preview(), save: () => mode.save() },
        { onSaved: onChanged, okText: 'Готово', out });
      const delBtn = $('#hf-delete', m);
      if (delBtn) delBtn.onclick = async () => {
        mode = remove;
        $('[data-save]', m).textContent = 'Удалить';
        try {
          const r = await remove.preview();
          if (r.overbook_refused) $('[data-save]', m).disabled = true;
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}
