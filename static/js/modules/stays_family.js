/* ══════════════════════════════════════════════════════════════════════
   «ШАХМАТКА» — семейное дерево гостя: визуальный редактор
   (спецификация docs/superpowers/specs/2026-10-28-stays-part1-addendum-design.md §4).
   renderFamilyTree(host, guestId, {editable}): гость в центре, родители сверху, супруги рядом,
   дети снизу, братья и сёстры по бокам — из GET /api/stays/guests/{id}/family; клик по человеку —
   он в центре (граф запрашивается заново: сервер отдаёт его вокруг центра). Редактор
   (editable — право stays.edit, им же защищены записи связей): «+ родитель / + супруг(а) /
   + ребёнок» — поиск гостя или новый (фамилия, имя, пол) → один POST /guests/{id}/links (новый
   гость и обе связи «и ребёнок супруги» — одной записью на сервере: отказ не оставит ни гостя,
   ни половины связей); крестик на
   линии → DELETE /guest-links/{id}; «бывшие» на линии супругов → PATCH /guest-links/{id};
   ошибка сервера (422 — третий родитель, свой предок…) — тост с её текстом.
   Под деревом — «Все родственники» (вычисленные сервером названия, kin).
   Рисование — HTML/CSS (flex с переносом): на ширине телефона ряды переносятся, а не вылезают.
   Использует хелперы app.js: $ $$ esc api toast loadGenerationFor.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

const STAYS_FAMILY_ADD = { parent: '+ родитель', spouse: '+ супруг(а)', child: '+ ребёнок' };
const STAYS_FAMILY_ADD_TITLE = { parent: 'Добавить родителя', spouse: 'Добавить супруга(у)', child: 'Добавить ребёнка' };

/* кто вокруг центра c: родители, дети, супруги (со связями — для крестика) и сиблинги */
function staysFamilyAround(fam, c) {
  const links = fam.links || [];
  const parents = links.filter(l => l.kind === 'parent' && l.b === c).map(l => ({ id: l.a, link: l }));
  const children = links.filter(l => l.kind === 'parent' && l.a === c).map(l => ({ id: l.b, link: l }));
  const spouses = links.filter(l => l.kind === 'spouse' && (l.a === c || l.b === c))
    .map(l => ({ id: l.a === c ? l.b : l.a, link: l }));
  const up = new Set(parents.map(p => p.id));
  const siblings = [...new Set(links.filter(l => l.kind === 'parent' && up.has(l.a) && l.b !== c).map(l => l.b))];
  return { parents, children, spouses, siblings };
}

function staysFamilyHtml(fam, c, editable, home) {
  const people = new Map(fam.people.map(p => [p.id, p]));
  const title = new Map(fam.kin.map(k => [k.person_id, k.title]));
  const { parents, children, spouses, siblings } = staysFamilyAround(fam, c);
  const name = id => people.get(id)?.name || '#' + id;
  const person = (id, cls = '') => `<button type="button" class="ft-person${cls}" data-ft-person="${id}"
    title="${id === c ? 'В центре' : 'Показать в центре'}">${esc(name(id))}${id !== c && title.get(id)
    ? `<small>${esc(title.get(id))}</small>` : ''}</button>`;
  const del = l => (editable ? `<button type="button" class="ft-del" data-ft-del="${l.id}" title="Удалить связь"
    aria-label="Удалить связь">×</button>` : '');
  const vline = l => `<span class="ft-link ft-v">│${del(l)}</span>`;
  const spouseLine = l => `<span class="ft-link ft-h">${editable
    ? `<label class="ft-former" title="Бывшие супруги"><input type="checkbox" data-ft-former="${l.id}"${l.former ? ' checked' : ''}> бывшие</label>`
    : (l.former ? 'бывшие' : '')}${l.former ? '┄' : '═'}${del(l)}</span>`;
  const half = Math.ceil(siblings.length / 2);
  const sib = id => `<span class="ft-node">${person(id, ' ft-sib')}</span>`;
  return `<div class="ft-tree">
      ${parents.length ? `<div class="ft-row">${parents.map(p => `<span class="ft-node ft-col">${person(p.id)}${vline(p.link)}</span>`).join('')}</div>` : ''}
      <div class="ft-row">${siblings.slice(0, half).map(sib).join('')}
        <span class="ft-node">${person(c, ' ft-centre')}</span>
        ${spouses.map(s => `<span class="ft-node">${spouseLine(s.link)}${person(s.id)}</span>`).join('')}
        ${siblings.slice(half).map(sib).join('')}</div>
      ${children.length ? `<div class="ft-row">${children.map(ch => `<span class="ft-node ft-col">${vline(ch.link)}${person(ch.id)}</span>`).join('')}</div>` : ''}
    </div>
    <div class="sb-line">${c !== home ? `<button type="button" class="btn btn-sm btn-ghost" data-ft-home>← к ${esc(name(home))}</button>` : ''}
      ${editable ? Object.entries(STAYS_FAMILY_ADD).map(([k, t]) => `<button type="button" class="btn btn-sm" data-ft-add="${k}">${esc(t)}</button>`).join('') : ''}</div>
    <div data-ft-panel></div>
    <h4>Все родственники</h4>
    <div class="ft-kin">${fam.kin.map(k => `<div><button type="button" class="ft-kin-name" data-ft-person="${k.person_id}">${esc(name(k.person_id))}</button>
      <span class="muted">— ${esc(k.title)}</span></div>`).join('') || '<span class="muted">родственников нет</span>'}</div>`;
}

function staysFamilyPanelHtml(kind, spouse, blocked) {
  return `<div class="ft-add">
    <b>${esc(STAYS_FAMILY_ADD_TITLE[kind])}</b>
    <div class="sb-line"><input type="search" data-ft-q placeholder="Найти гостя: фамилия"></div>
    <div class="sb-line" data-ft-found></div>
    <div class="sb-line"><span class="muted">или новый:</span>
      <input data-ft-last placeholder="Фамилия"><input data-ft-first placeholder="Имя">
      <select data-ft-gender title="Пол">${Object.entries(STAYS_GENDER).map(([v, t]) => `<option value="${v}">${esc(t)}</option>`).join('')}</select>
      <button type="button" class="btn btn-sm btn-primary" data-ft-create${blocked ? ' disabled' : ''}>Создать и связать</button></div>
    ${blocked ? `<div class="muted" data-ft-blocked>${esc(blocked)}</div>` : ''}
    ${spouse ? `<label class="chk"><input type="checkbox" data-ft-both checked> и ребёнок: ${esc(spouse.name)}</label>` : ''}
    <div><button type="button" class="btn btn-sm btn-ghost" data-ft-cancel>Отмена</button></div></div>`;
}

async function renderFamilyTree(host, guestId, { editable = false, onChange = null } = {}) {
  let centre = guestId;
  let fam = null;
  const changed = () => { if (onChange) onChange(); };

  /* связь центра со второй стороной (target: {guest_id} или {new_guest}) — один запрос:
     parent — она родитель центра; child — центр её родитель (и, если отмечено, действующий супруг) */
  const link = (kind, target, spouseId) => api(`/api/stays/guests/${centre}/links`, { method: 'POST', body: {
    ...target, kind: kind === 'spouse' ? 'spouse' : 'parent', other_is_parent: kind === 'parent',
    ...(kind === 'child' && spouseId ? { also_parent_id: spouseId } : {}) } });

  const openPanel = kind => {
    const panel = $('[data-ft-panel]', host);
    const around = staysFamilyAround(fam, centre);
    const current = around.spouses.find(s => !s.link.former);
    const spouse = kind === 'child' && current ? fam.people.find(p => p.id === current.id) : null;
    /* заранее видно, что сервер откажет: новый гость не создаётся (поиск — сервер ответит тостом) */
    const blocked = (kind === 'parent' && around.parents.length >= 2 && 'У гостя уже два родителя — сначала удалите связь')
      || (kind === 'spouse' && current && 'У гостя уже есть супруг(а) — отметьте прежний брак «бывшие»') || '';
    panel.innerHTML = staysFamilyPanelHtml(kind, spouse, blocked);
    const both = () => (spouse && $('[data-ft-both]', panel).checked ? spouse.id : null);
    const done = async target => {
      try {
        await link(kind, target, both());
        toast('Связь добавлена');
        changed();
        await draw();
      } catch (e) { toast(e.message, 'err'); await draw(); }
    };
    let timer = null;
    const q = $('[data-ft-q]', panel);
    q.oninput = () => {
      clearTimeout(timer);
      timer = setTimeout(async () => {
        const needle = q.value.trim();
        let found = [];
        try {
          found = needle.length < 2 ? [] : (await api('/api/stays/guests?q=' + encodeURIComponent(needle), { silent: true }))
            .filter(x => x.id !== centre);
        } catch (e) { toast(e.message, 'err'); }
        $('[data-ft-found]', panel).innerHTML = found.map(x => `<button type="button" class="btn btn-sm btn-ghost" data-ft-pick="${x.id}">${esc(x.short)}</button>`).join('')
          || (needle.length >= 2 ? '<span class="muted">не найдено</span>' : '');
      }, 300);
    };
    $('[data-ft-found]', panel).onclick = e => {
      const b = e.target.closest('[data-ft-pick]');
      if (b) { b.disabled = true; done({ guest_id: Number(b.dataset.ftPick) }); }
    };
    $('[data-ft-create]', panel).onclick = async e => {
      const last = $('[data-ft-last]', panel).value.trim();
      if (!last) { toast('Укажите фамилию', 'warn'); return; }
      e.target.disabled = true;
      done({ new_guest: { last_name: last, first_name: $('[data-ft-first]', panel).value.trim(),
        gender: $('[data-ft-gender]', panel).value } });
    };
    $('[data-ft-cancel]', panel).onclick = () => { panel.innerHTML = ''; };
    q.focus();
  };

  const draw = async () => {
    const fresh = loadGenerationFor(host);
    let data;
    try {
      data = await api(`/api/stays/guests/${centre}/family`, { silent: true });
    } catch (e) {
      if (fresh()) host.innerHTML = `<p class="muted">${esc(e.message)}</p>`;
      return false;
    }
    if (!fresh()) return false;
    fam = data;
    host.innerHTML = staysFamilyHtml(fam, centre, editable, guestId);
    return true;
  };

  host.onclick = async e => {
    const t = e.target;
    const del = t.closest('[data-ft-del]');
    if (del) {
      del.disabled = true;
      try {
        await api(`/api/stays/guest-links/${del.dataset.ftDel}`, { method: 'DELETE' });
        toast('Связь удалена');
        changed();
      } catch (err) { toast(err.message, 'err'); }
      await draw();
      return;
    }
    const add = t.closest('[data-ft-add]');
    if (add) { openPanel(add.dataset.ftAdd); return; }
    if (t.closest('[data-ft-home]')) { centre = guestId; await draw(); return; }
    const p = t.closest('[data-ft-person]');
    if (p && Number(p.dataset.ftPerson) !== centre) { centre = Number(p.dataset.ftPerson); await draw(); }
  };
  host.onchange = async e => {
    const box = e.target.closest('[data-ft-former]');
    if (!box) return;
    try {
      await api(`/api/stays/guest-links/${box.dataset.ftFormer}`, { method: 'PATCH', body: { former: box.checked } });
      changed();
    } catch (err) { toast(err.message, 'err'); }
    await draw();
  };
  return draw();          // true — дерево нарисовано (false — ошибка: можно запросить снова)
}
