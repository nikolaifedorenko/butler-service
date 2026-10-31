/* ══════════════════════════════════════════════════════════════════════
   «ШАХМАТКА» — вкладка «Гости»: справочник гостей и объединение дублей
   (спецификация docs/superpowers/specs/2026-10-28-stays-part1-addendum-design.md §3).
   Поиск, фильтры, сортировка и срез страницы — на сервере (GET /api/stays/guests/list), по 200;
   клиент держит накопленные страницы («Показать ещё»). Карточка гостя — openGuestCard,
   новый гость — openGuestForm (stays_forms.js). Объединение: отметить двух гостей →
   «Объединить…» → кого оставить → «Проверить» (что перенесётся) → «Объединить».
   Вкладка — только полный уровень (stays.guests, см. staysTabAllowed в stays.js).
   Использует хелперы app.js: $ $$ esc api toast can dateRu openModal closeModal.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

/* колонки: ключ сортировки сервера (null — без сортировки) — заголовок */
const STAYS_GUEST_COLS = [['name', 'Гость'], ['level', 'Уровень'], [null, 'Телефон'], ['last_stay', 'Последний заезд'],
  ['stays', 'Проживаний']];
const STAYS_GUEST_LEVELS = [['', 'все уровни'], ['regular', 'обычный'], ['vip', 'VIP'], ['vvip', 'VVIP']];
const STAYS_GUEST_PAGE = 200;
const STAYS_BIRTHDAY_DAYS = 30;
const STAYS_MERGE_RESULT = { moved: 'перенесётся', duplicate: 'уже есть — дубль удалится', removed: 'связь между ними — удалится',
  current: 'бывший брак станет действующим' };
const STAYS_MERGE_KIND = { parent: 'родитель — ребёнок' };
const STAYS_MERGE_PROFILE = { first_name: 'имя', middle_name: 'отчество', phone: 'телефон', email: 'email',
  birth_date: 'дата рождения', gender: 'пол', external_id: 'внешний id', source: 'источник', level: 'уровень', note: 'примечание' };

function staysGuestsEmpty() {
  return { q: '', level: '', stayed_from: '', stayed_to: '', birthday: false, sort: 'name', dir: 'asc', picked: [] };
}
const staysGuests = staysGuestsEmpty();

function staysGuestsParams(offset) {
  const s = staysGuests;
  const p = new URLSearchParams({ sort: s.sort, dir: s.dir, offset, limit: STAYS_GUEST_PAGE });
  if (s.q.trim()) p.set('q', s.q.trim());
  if (s.level) p.set('level', s.level);
  if (s.stayed_from) p.set('stayed_from', s.stayed_from);
  if (s.stayed_to) p.set('stayed_to', s.stayed_to);
  if (s.birthday) p.set('birthday_days', STAYS_BIRTHDAY_DAYS);
  return p;
}

function staysGuestsToolbar() {
  const s = staysGuests;
  const edit = can('stays.edit');
  return `<div class="sb-toolbar">
    <input type="search" id="gl-q" value="${esc(s.q)}" placeholder="Фамилия, телефон, номер брони">
    <select id="gl-level" title="Уровень гостя">${STAYS_GUEST_LEVELS.map(([v, t]) =>
    `<option value="${v}"${v === s.level ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select>
    <label class="muted">был с <input type="date" id="gl-from" value="${esc(s.stayed_from)}"></label>
    <label class="muted">по <input type="date" id="gl-to" value="${esc(s.stayed_to)}"${s.stayed_from ? ` min="${esc(s.stayed_from)}"` : ''}></label>
    <label class="chk"><input type="checkbox" id="gl-birthday"${s.birthday ? ' checked' : ''}>
      день рождения в ближайшие ${STAYS_BIRTHDAY_DAYS} дней</label>
    ${edit ? `<button class="btn btn-sm" id="gl-merge" title="Отметьте двух гостей"${s.picked.length === 2 ? '' : ' disabled'}>Объединить…</button>
      <button class="btn btn-sm btn-primary" id="gl-new">Новый гость</button>` : ''}
  </div>`;
}

function staysGuestRowHtml(r, edit) {
  const mark = r.level !== 'regular' ? `<span class="sb-star">${esc(STAYS_LEVEL_MARK[r.level] || '')}</span>` : '';
  return `<tr class="bk-row" data-gl-row="${r.id}" tabindex="0">
    ${edit ? `<td><input type="checkbox" data-gl-pick="${r.id}"${staysGuests.picked.includes(r.id) ? ' checked' : ''} title="Для объединения"></td>` : ''}
    <td>${mark}${esc(r.name)}</td><td>${esc({ regular: 'обычный', vip: 'VIP', vvip: 'VVIP' }[r.level] || r.level)}</td>
    <td>${esc(r.phone || '—')}</td>
    <td>${r.last_stay ? esc(dateRu(r.last_stay)) : '<span class="muted">—</span>'}</td><td>${r.stays}</td></tr>`;
}

function staysGuestsTableHtml(rows, total) {
  const edit = can('stays.edit');
  const arrow = key => (staysGuests.sort === key ? (staysGuests.dir === 'asc' ? ' ↑' : ' ↓') : '');
  const cols = STAYS_GUEST_COLS.length + (edit ? 1 : 0);
  return `<div class="muted" id="gl-total">Найдено гостей: ${total}${rows.length < total ? ` · показано ${rows.length}` : ''}</div>
    <div class="sb-scroll"><table class="bk-table"><thead><tr>${edit ? '<th></th>' : ''}${STAYS_GUEST_COLS.map(([k, t]) => (k
    ? `<th data-gl-sort="${k}" title="Сортировать" style="cursor:pointer">${esc(t)}${arrow(k)}</th>` : `<th>${esc(t)}</th>`)).join('')}</tr></thead>
    <tbody>${rows.map(r => staysGuestRowHtml(r, edit)).join('') || `<tr><td colspan="${cols}" class="empty">Гостей по фильтру нет</td></tr>`}</tbody></table></div>
    ${rows.length < total ? `<button class="btn" id="gl-more">Показать ещё ${Math.min(STAYS_GUEST_PAGE, total - rows.length)}</button>` : ''}`;
}

/* панель фильтров рисуется один раз и не перерисовывается: поиск печатается без потери фокуса;
   смена фильтра или сортировки перегружает только список (#gl-result) */
function renderGuestsTab(body) {
  const s = staysGuests;
  body.innerHTML = `${staysGuestsToolbar()}<div id="gl-result"><div class="empty">Загрузка…</div></div>`;
  const result = $('#gl-result', body);
  const known = new Map();
  const mergeBtn = $('#gl-merge', body);
  const syncMerge = () => { if (mergeBtn) mergeBtn.disabled = s.picked.length !== 2; };
  let rows = [];
  let total = 0;
  let error = '';
  const page = offset => api('/api/stays/guests/list?' + staysGuestsParams(offset), { silent: true });
  const paint = fresh => {
    rows.forEach(r => known.set(r.id, r));
    result.innerHTML = error ? `<div class="panel"><p class="muted">${esc(error)}</p></div>` : staysGuestsTableHtml(rows, total);
    const more = $('#gl-more', result);
    if (more) more.onclick = async () => {
      more.disabled = true;
      try {
        const next = await page(rows.length);
        if (!fresh()) return;
        rows = rows.concat(next.rows);
        total = next.total;
      } catch (e) { toast(e.message, 'warn'); }
      paint(fresh);
    };
  };
  const reload = async () => {
    const fresh = loadGenerationFor(result);
    try {
      ({ rows, total } = await page(0));
      error = '';
    } catch (e) {
      rows = []; total = 0; error = e.message;
    }
    if (fresh()) paint(fresh);
  };

  result.onclick = e => {
    const th = e.target.closest('[data-gl-sort]');
    if (th) {
      const key = th.dataset.glSort;
      if (s.sort === key) s.dir = s.dir === 'asc' ? 'desc' : 'asc'; else { s.sort = key; s.dir = 'asc'; }
      reload();
      return;
    }
    const pick = e.target.closest('[data-gl-pick]');
    if (pick) {
      const id = Number(pick.dataset.glPick);
      s.picked = pick.checked ? [...s.picked.filter(x => x !== id), id].slice(-2) : s.picked.filter(x => x !== id);
      $$('[data-gl-pick]', result).forEach(cb => { cb.checked = s.picked.includes(Number(cb.dataset.glPick)); });
      syncMerge();
      return;
    }
    const tr = e.target.closest('[data-gl-row]');
    if (tr) openGuestCard(Number(tr.dataset.glRow), reload).catch(err => toast(err.message, 'warn'));
  };
  result.onkeydown = e => {
    const tr = e.target.closest?.('[data-gl-row]');
    if (tr && e.target === tr && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); tr.click(); }
  };

  let timer = null;
  $('#gl-q', body).oninput = e => {
    clearTimeout(timer);
    timer = setTimeout(() => { s.q = e.target.value; reload(); }, 300);
  };
  $('#gl-level', body).onchange = e => { s.level = e.target.value; reload(); };
  const from = $('#gl-from', body);
  const to = $('#gl-to', body);
  from.onchange = () => {
    s.stayed_from = from.value;
    to.min = from.value;
    if (s.stayed_to && s.stayed_from && s.stayed_to < s.stayed_from) { s.stayed_to = s.stayed_from; to.value = s.stayed_to; }
    reload();
  };
  to.onchange = () => { s.stayed_to = to.value; reload(); };
  $('#gl-birthday', body).onchange = e => { s.birthday = e.target.checked; reload(); };
  const add = $('#gl-new', body);
  if (add) add.onclick = () => openGuestForm(null, reload);
  if (mergeBtn) mergeBtn.onclick = () => {
    const [a, b] = s.picked.map(id => known.get(id) || { id, name: '#' + id });
    openGuestMerge(a, b, () => { s.picked = []; syncMerge(); reload(); });
  };
  return reload();
}

/* что перенесётся при объединении (ответ ?preview=1 и сохранения — одинаковые moves) */
function staysMergeMovesHtml(m) {
  const list = (title, items) => `<h4>${esc(title)}</h4>${items.length ? items.join('') : '<div class="muted">нет</div>'}`;
  return [
    list('Брони', m.reservations.map(r => `<div>${esc(r.number || '#' + r.id)}${r.shared ? ' <span class="muted">— оба в составе: останется один гость</span>' : ''}</div>`)),
    list('Связи', m.links.map(l => `<div>${esc(l.name)} · ${esc(l.former ? STAYS_LINK.spouse_former : STAYS_MERGE_KIND[l.kind] || STAYS_LINK[l.kind] || l.kind)} — ${esc(STAYS_MERGE_RESULT[l.result] || l.result)}</div>`)),
    list('Предпочтения', m.preferences.map(k => `<div>${esc(k)}</div>`)),
    list('Особые даты', m.special_dates.map(d => `<div>${esc(dateRu(d.date))} — ${esc(d.what)}</div>`)),
    list('Профиль: заполнится из дубля', m.profile.map(k => `<div>${esc(STAYS_MERGE_PROFILE[k] || k)}</div>`)),
    m.fields.length ? list('Настраиваемые поля', m.fields.map(k => `<div>${esc(k)}</div>`)) : '',
    m.coverage ? `<div class="muted">Строк покрытия с выбранным гостем: ${m.coverage}</div>` : '',
  ].join('');
}

function openGuestMerge(a, b, onDone) {
  openModal({
    title: 'Объединить гостей', wide: true,
    subtitle: 'Брони, связи, предпочтения и особые даты перейдут к оставленному гостю, второй профиль удалится',
    body: `<div class="sb-line"><label class="chk"><input type="radio" name="gm-keep" value="${a.id}" checked> оставить ${esc(a.name)}</label></div>
      <div class="sb-line"><label class="chk"><input type="radio" name="gm-keep" value="${b.id}"> оставить ${esc(b.name)}</label></div>
      <div id="gm-out" class="sp-out"></div>`,
    footer: `<button class="btn btn-ghost" data-close>Отмена</button>
      <button class="btn" id="gm-preview">Проверить</button><button class="btn btn-primary" data-save>Объединить</button>`,
    onMount(m) {
      const ids = () => {
        const keep = Number($$('[name="gm-keep"]', m).find(x => x.checked).value);
        return { keep_id: keep, drop_id: keep === a.id ? b.id : a.id };
      };
      $$('[name="gm-keep"]', m).forEach(x => { x.onchange = () => { $('#gm-out', m).innerHTML = ''; }; });
      $('[data-close]', m).onclick = closeModal;
      /* пока запрос идёт, обе кнопки заперты: двойной клик не отправит объединение дважды */
      const buttons = [$('#gm-preview', m), $('[data-save]', m)];
      const busy = on => buttons.forEach(x => { x.disabled = on; });
      $('#gm-preview', m).onclick = async () => {
        busy(true);
        try {
          const r = await api('/api/stays/guests/merge?preview=1', { method: 'POST', body: ids() });
          $('#gm-out', m).innerHTML = staysMergeMovesHtml(r.moves);
        } catch (e) { $('#gm-out', m).innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
        busy(false);
      };
      $('[data-save]', m).onclick = async () => {
        busy(true);
        try {
          await api('/api/stays/guests/merge', { method: 'POST', body: ids() });
          closeModal();
          toast('Гости объединены');
          if (onDone) onDone();
        } catch (e) { busy(false); toast(e.message, 'err'); }
      };
    },
  });
}
