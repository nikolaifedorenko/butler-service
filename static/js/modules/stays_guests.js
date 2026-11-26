/* ══════════════════════════════════════════════════════════════════════
   РАЗДЕЛ «ГОСТИ» — справочник гостей и объединение дублей.
   Самостоятельный раздел (ревью UI 22.11.2026): раньше был вкладкой внутри Шахматки,
   микро-поиск гостя остался в шапке шахматки. Полный уровень (stays.guests) — поиск,
   фильтры, сортировка, дубли; батлер (stays.mine_guest_edit) — создание гостя, который
   сразу становится «своим» (список целиком без полного уровня недоступен — 403).
   Поиск, фильтры, сортировка и срез страницы — на сервере (GET /api/stays/guests/list), по 200;
   клиент держит накопленные страницы («Показать ещё»). Карточка гостя — openGuestCard,
   новый гость — openGuestForm (stays_forms.js). Объединение: отметить двух гостей →
   «Объединить…» → кого оставить → «Проверить» (что перенесётся) → «Объединить».
   Модуль на lit-html (ADR-0013, раздел 7): панель фильтров рисуется один раз, список — шаблоном.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

import { can, registerModule } from '../app.js';
import { $, $$, api, closeDrawer, closeModal, dateRu, loadGenerationFor, openModal, state, toast } from '../core.js';
import { registerPaletteProvider } from '../registry.js';
import { guestPickDetails, guestPickName } from '../ui/guest_picker.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { STAYS_LINK, openGuestCard, openGuestForm } from './stays_forms.js';
import { mountGuestFamily } from './stays_family_canvas.js';
import { STAYS_SPECIAL_MARK, staysGuestMarkView } from './stays.js';

/* колонки: ключ сортировки сервера (null — без сортировки) — заголовок */
const STAYS_GUEST_COLS = [['name', 'Гость'], ['special', 'VIP-код'], [null, 'Телефон'], ['last_stay', 'Последний заезд'],
  ['stays', 'Проживаний']];
const STAYS_GUEST_PAGE = 200;
const STAYS_BIRTHDAY_DAYS = 30;
const STAYS_MERGE_RESULT = { moved: 'перенесётся', duplicate: 'уже есть — дубль удалится', removed: 'связь между ними — удалится',
  current: 'бывший брак станет действующим' };
const STAYS_MERGE_KIND = { parent: 'родитель — ребёнок' };
const STAYS_MERGE_PROFILE = { first_name: 'имя', middle_name: 'отчество', phone: 'телефон', email: 'email',
  birth_date: 'дата рождения', gender: 'пол', external_id: 'внешний id', source: 'источник', special: '◆ Особый гость', vip_code_id: 'VIP-код', note: 'примечание' };

export function staysGuestsEmpty() {
  return { q: '', special: false, stayed_from: '', stayed_to: '', birthday: false, sort: 'name', dir: 'asc', picked: [] };
}
export const staysGuests = staysGuestsEmpty();
let staysGuestsSearchTimer = null;
let staysGuestsSearchGeneration = 0;
export function staysGuestsResetUserState() {
  ++staysGuestsSearchGeneration;
  clearTimeout(staysGuestsSearchTimer);
  staysGuestsSearchTimer = null;
  Object.assign(staysGuests, staysGuestsEmpty());
}

registerModule({ views: { guests: loadGuests } });
registerPaletteProvider({
  id: 'guests',
  icon: 'guests',
  hint: 'гость',
  async search(query, signal) {
    const guests = await api(`/api/stays/guests?details=1&q=${encodeURIComponent(query)}${can('stays.guests') ? '' : '&mine=1'}`,
      { silent: true, signal });
    return guests.map(guest => ({ ...guest, title: guestPickName(guest), detail: guestPickDetails(guest), hint: 'гость', icon: 'guests' }));
  },
  activate(guest) { openGuestCard(guest.id); },
});

/* раздел «Гости»: полный уровень — справочник; батлер — панель создания (гость сразу «свой») */
async function loadGuests() {
  const host = $('#view-guests');
  const generation = loadGenerationFor(host);
  const full = can('stays.guests');
  const managerCreate = can('stays.edit');
  const mineCreate = !managerCreate && can('stays.mine_guest_edit') && state.user?.employee_id != null;
  const create = managerCreate || mineCreate;
  if (!full) {
    if (!create) {
      render(html`<div class="panel"><p>Раздел недоступен.</p></div>`, mount(host));
      return;
    }
    render(html`<div class="page-head"><div><h2>Гости</h2><div class="sub">Создание профиля гостя</div></div></div>
      <div class="panel"><p>${mineCreate ? html`Заведённый вами гость сразу попадает в <b>«Мои гости»</b> — вы его ведёте по умолчанию.
        VIP-код и отметку «особый» задаёт менеджер.` : 'Создайте профиль гостя для последующего добавления в бронь.'}</p>
        <button class="btn btn-primary" id="gl-new">Новый гость</button></div>`, mount(host));
    $('#gl-new', host).onclick = () => openGuestForm(null, () => {}, { mine: !can('stays.edit') });
    return;
  }
  render(html`<div data-guests-list>
      <div class="page-head"><div><h2>Гости</h2><div class="sub">Справочник: поиск, фильтры, дубли</div></div></div>
      <div id="gl-body"></div>
    </div><div class="family-canvas hidden"></div>`, mount(host));
  const list = $('[data-guests-list]', host);
  const canvas = $('.family-canvas', host);
  list.classList.remove('hidden');
  canvas.classList.add('hidden');
  const isCurrent = () => generation() && state.view === 'guests';
  let cardRequest = 0;
  let familySession = 0;
  const openListCard = (id, reload) => {
    const request = ++cardRequest;
    const selected = () => isCurrent() && request === cardRequest;
    openGuestCard(id, reload, {
      isCurrent: selected,
      onFamilyChanged: reload,
      onOpenFamily(guest) {
        closeDrawer();
        list.classList.add('hidden');
        canvas.classList.remove('hidden');
        const session = ++familySession;
        const canvasActive = () => isCurrent() && session === familySession;
        mountGuestFamily(canvas, guest, {
          onChanged: reload,
          isCurrent: canvasActive,
          onBack() {
            ++familySession;
            canvas.classList.add('hidden');
            list.classList.remove('hidden');
            ($(`[data-gl-row="${guest.id}"]`, list) || $('#gl-q', list)).focus({ preventScroll: true });
          },
        });
      },
    }).catch(err => { if (selected()) toast(err.message, 'warn'); });
  };
  await renderGuestsTab($('#gl-body', host), openListCard);
}

function staysGuestsParams(offset) {
  const s = staysGuests;
  const p = new URLSearchParams({ sort: s.sort, dir: s.dir, offset, limit: STAYS_GUEST_PAGE });
  if (s.q.trim()) p.set('q', s.q.trim());
  if (s.special) p.set('special', 'true');
  if (s.stayed_from) p.set('stayed_from', s.stayed_from);
  if (s.stayed_to) p.set('stayed_to', s.stayed_to);
  if (s.birthday) p.set('birthday_days', STAYS_BIRTHDAY_DAYS);
  return p;
}

const staysGuestsToolbar = () => {
  const s = staysGuests;
  const edit = can('stays.edit');
  const create = edit || (can('stays.mine_guest_edit') && state.user?.employee_id != null);
  return html`<div class="sb-toolbar">
    <input type="search" id="gl-q" .value=${s.q} placeholder="Фамилия, телефон, номер брони">
    <label class="chk"><input type="checkbox" id="gl-special" .checked=${s.special}> ${STAYS_SPECIAL_MARK}Особые</label>
    <label class="muted">был с <input type="date" id="gl-from" .value=${s.stayed_from}></label>
    <label class="muted">по <input type="date" id="gl-to" .value=${s.stayed_to} min=${s.stayed_from || nothing}></label>
    <label class="chk"><input type="checkbox" id="gl-birthday" .checked=${s.birthday}>
      день рождения в ближайшие ${STAYS_BIRTHDAY_DAYS} дней</label>
    ${edit ? html`<button class="btn btn-sm" id="gl-merge" title="Отметьте двух гостей" ?disabled=${s.picked.length !== 2}>Объединить…</button>` : nothing}
    ${create ? html`<button class="btn btn-sm btn-primary" id="gl-new">Новый гость</button>` : nothing}
  </div>`;
};

const staysGuestRow = (r, edit) => html`<tr class="bk-row" data-gl-row=${r.id} tabindex="0">
    ${edit ? html`<td><input type="checkbox" data-gl-pick=${r.id} .checked=${staysGuests.picked.includes(r.id)} title="Для объединения"></td>` : nothing}
    <td>${staysGuestMarkView(r.special)}${r.name}</td><td data-gl-code>${r.vip_code
      ? html`${r.vip_code}${r.vip_code_archived ? html` <span class="muted">в архиве</span>` : nothing}` : html`<span class="muted">—</span>`}</td>
    <td>${r.phone || '—'}</td>
    <td>${r.last_stay ? dateRu(r.last_stay) : html`<span class="muted">—</span>`}</td><td>${r.stays}</td></tr>`;

const staysGuestsTable = (rows, total, onMore) => {
  const edit = can('stays.edit');
  const arrow = key => (staysGuests.sort === key ? (staysGuests.dir === 'asc' ? ' ↑' : ' ↓') : '');
  const cols = STAYS_GUEST_COLS.length + (edit ? 1 : 0);
  return html`<div class="muted" id="gl-total">Найдено гостей: ${total}${rows.length < total ? ` · показано ${rows.length}` : ''}</div>
    <div class="sb-scroll"><table class="bk-table"><thead><tr>${edit ? html`<th></th>` : nothing}${STAYS_GUEST_COLS.map(([k, t]) => (k
    ? html`<th data-gl-sort=${k} title="Сортировать" style="cursor:pointer">${t}${arrow(k)}</th>` : html`<th>${t}</th>`))}</tr></thead>
    <tbody>${rows.length ? rows.map(r => staysGuestRow(r, edit)) : html`<tr><td colspan=${cols} class="empty">Гостей по фильтру нет</td></tr>`}</tbody></table></div>
    ${rows.length < total ? html`<button class="btn" id="gl-more" @click=${onMore}>Показать ещё ${Math.min(STAYS_GUEST_PAGE, total - rows.length)}</button>` : nothing}`;
};

/* панель фильтров рисуется один раз и не перерисовывается: поиск печатается без потери фокуса;
   смена фильтра или сортировки перегружает только список (#gl-result) */
function renderGuestsTab(body, openCard) {
  const s = staysGuests;
  render(html`${staysGuestsToolbar()}<div id="gl-result"></div>`, mount(body));
  const result = $('#gl-result', body);
  render(html`<div class="skel-wrap"><div class="skel-line skel-lg"></div><div class="skel-line"></div><div class="skel-line"></div></div>`, result);
  const known = new Map();
  const mergeBtn = $('#gl-merge', body);
  const syncMerge = () => { if (mergeBtn) mergeBtn.disabled = s.picked.length !== 2; };
  let rows = [];
  let total = 0;
  let error = '';
  const page = offset => api('/api/stays/guests/list?' + staysGuestsParams(offset), { silent: true });
  const paint = fresh => {
    rows.forEach(r => known.set(r.id, r));
    const more = async e => {
      e.currentTarget.disabled = true;
      try {
        const next = await page(rows.length);
        if (!fresh()) return;
        rows = rows.concat(next.rows);
        total = next.total;
      } catch (err) { toast(err.message, 'warn'); }
      paint(fresh);
    };
    render(error ? html`<div class="panel"><p class="muted">${error}</p></div>` : staysGuestsTable(rows, total, more), result);
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
    if (tr) openCard(Number(tr.dataset.glRow), reload);
  };
  result.onkeydown = e => {
    const tr = e.target.closest?.('[data-gl-row]');
    if (tr && e.target === tr && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); tr.click(); }
  };

  $('#gl-q', body).oninput = e => {
    clearTimeout(staysGuestsSearchTimer);
    const input = e.currentTarget;
    const current = ++staysGuestsSearchGeneration;
    staysGuestsSearchTimer = setTimeout(() => {
      if (current !== staysGuestsSearchGeneration || !input.isConnected) return;
      s.q = input.value;
      reload();
    }, 300);
  };
  $('#gl-special', body).onchange = e => { s.special = e.target.checked; reload(); };
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
  if (add) add.onclick = () => openGuestForm(null, reload, { mine: !can('stays.edit') });
  if (mergeBtn) mergeBtn.onclick = () => {
    const [a, b] = s.picked.map(id => known.get(id) || { id, name: '#' + id });
    openGuestMerge(a, b, () => { s.picked = []; syncMerge(); reload(); });
  };
  return reload();
}

/* что перенесётся при объединении (ответ ?preview=1 и сохранения — одинаковые moves) */
function staysMergeMoves(m) {
  const list = (title, items) => html`<h4>${title}</h4>${items.length ? items : html`<div class="muted">нет</div>`}`;
  return html`
    ${list('Брони', m.reservations.map(r => html`<div>${r.number || '#' + r.id}${r.shared ? html` <span class="muted">— оба в составе: останется один гость</span>` : nothing}</div>`))}
    ${list('Связи', m.links.map(l => html`<div>${l.name} · ${l.former ? STAYS_LINK[`${l.kind}_former`] || STAYS_LINK.spouse_former : STAYS_MERGE_KIND[l.kind] || STAYS_LINK[l.kind] || l.kind} — ${STAYS_MERGE_RESULT[l.result] || l.result}</div>`))}
    ${list('Предпочтения', m.preferences.map(k => html`<div>${k}</div>`))}
    ${list('Особые даты', m.special_dates.map(d => html`<div>${dateRu(d.date)} — ${d.what}</div>`))}
    ${list('Профиль: заполнится из дубля', m.profile.map(k => html`<div>${STAYS_MERGE_PROFILE[k] || k}</div>`))}
    ${m.fields.length ? list('Настраиваемые поля', m.fields.map(k => html`<div>${k}</div>`)) : nothing}
    ${m.coverage ? html`<div class="muted">Строк покрытия с выбранным гостем: ${m.coverage}</div>` : nothing}`;
}

function openGuestMerge(a, b, onDone) {
  openModal({
    title: 'Объединить гостей', wide: true,
    subtitle: 'Брони, связи, предпочтения и особые даты перейдут к оставленному гостю, второй профиль удалится',
    body: html`<div class="sb-line"><label class="chk"><input type="radio" name="gm-keep" value=${a.id} checked> оставить ${a.name}</label></div>
      <div class="sb-line"><label class="chk"><input type="radio" name="gm-keep" value=${b.id}> оставить ${b.name}</label></div>
      <div id="gm-out" class="sp-out"></div>`,
    footer: html`<button class="btn btn-ghost" data-close>Отмена</button>
      <button class="btn" id="gm-preview">Проверить</button><button class="btn btn-primary" data-save>Объединить</button>`,
    onMount(m) {
      const out = $('#gm-out', m);
      const ids = () => {
        const keep = Number($$('[name="gm-keep"]', m).find(x => x.checked).value);
        return { keep_id: keep, drop_id: keep === a.id ? b.id : a.id };
      };
      $$('[name="gm-keep"]', m).forEach(x => { x.onchange = () => render(nothing, out); });
      $('[data-close]', m).onclick = closeModal;
      /* пока запрос идёт, обе кнопки заперты: двойной клик не отправит объединение дважды */
      const buttons = [$('#gm-preview', m), $('[data-save]', m)];
      const busy = on => buttons.forEach(x => { x.disabled = on; });
      $('#gm-preview', m).onclick = async () => {
        busy(true);
        try {
          const r = await api('/api/stays/guests/merge?preview=1', { method: 'POST', body: ids() });
          // новый овербукинг без права «Овербукинг» — объединение не сохранится (409)
          render(html`${r.overbook_refused ? html`<p class="sp-warn"><b>Не сохранится:</b> ${r.overbook_refused}</p>` : nothing}${staysMergeMoves(r.moves)}`, out);
        } catch (e) { render(html`<p class="muted">${e.message}</p>`, out); }
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
