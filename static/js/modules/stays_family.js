/* ══════════════════════════════════════════════════════════════════════
   «ШАХМАТКА» — семейное дерево гостя: визуальный редактор
   (спецификация docs/superpowers/specs/2026-10-28-stays-part1-addendum-design.md §4).
   renderFamilyTree(host, guestId, {editable}): гость в центре, родители сверху, супруги рядом,
   дети снизу, братья и сёстры по бокам — из GET /api/stays/guests/{id}/family; клик по человеку —
   он в центре (граф запрашивается заново: сервер отдаёт его вокруг центра). Редактор
   (editable — право stays.edit или, батлеру у своего гостя, stays.mine_guest_edit; сервер проверяет
   принадлежность — у чужого гостя в центре ответ 403 придёт тостом; поиск второй стороны и «и ребёнок
   супруги» у батлера — только среди своих гостей): «+ родитель / + супруг(а) /
   + ребёнок» — поиск гостя или новый (фамилия, имя, пол) → один POST /guests/{id}/links (новый
   гость и обе связи «и ребёнок супруги» — одной записью на сервере: отказ не оставит ни гостя,
   ни половины связей); крестик на
   линии → DELETE /guest-links/{id}; «бывшие» на линии супругов → PATCH /guest-links/{id};
   ошибка сервера (422 — третий родитель, свой предок…) — тост с её текстом.
   Под деревом — «Все родственники» (вычисленные сервером названия, kin).
   Рисование — HTML/CSS (flex с переносом): на ширине телефона ряды переносятся, а не вылезают.
   Модуль на lit-html (ADR-0013, раздел 7).
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

import { can } from '../app.js';
import { $, api, loadGenerationFor, toast } from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { STAYS_GENDER } from './stays_forms.js';

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

export async function renderFamilyTree(host, guestId, { editable = false, onChange = null } = {}) {
  let centre = guestId;
  let fam = null;
  /* панель добавления: kind, spouse, blocked, own, найденные гости */
  let panel = null;
  let found = null;       // null — поиска не было; [] — ничего не нашли
  let needleLong = false;
  const changed = () => { if (onChange) onChange(); };
  const paint = () => render(treeView(), mount(host));

  /* связь центра со второй стороной (target: {guest_id} или {new_guest}) — один запрос:
     parent — она родитель центра; child — центр её родитель (и, если отмечено, действующий супруг) */
  const link = (kind, target, spouseId) => api(`/api/stays/guests/${centre}/links`, { method: 'POST', body: {
    ...target, kind: kind === 'spouse' ? 'spouse' : 'parent', other_is_parent: kind === 'parent',
    ...(kind === 'child' && spouseId ? { also_parent_id: spouseId } : {}) } });

  const openPanel = kind => {
    const around = staysFamilyAround(fam, centre);
    const current = around.spouses.find(s => !s.link.former);
    const spouse = kind === 'child' && current ? fam.people.find(p => p.id === current.id) : null;
    /* заранее видно, что сервер откажет: новый гость не создаётся (поиск — сервер ответит тостом) */
    const blocked = (kind === 'parent' && around.parents.length >= 2 && 'У гостя уже два родителя — сначала удалите связь')
      || (kind === 'spouse' && current && 'У гостя уже есть супруг(а) — отметьте прежний брак «бывшие»') || '';
    /* батлер: второй родитель — только свой гость (сервер иначе 403); пока не проверили — галочки нет */
    const full = can('stays.edit');
    panel = { kind, spouse, blocked, both: !!spouse && full, bothVisible: !!spouse && full };
    found = null; needleLong = false;
    paint();
    if (spouse && !full) {
      api(`/api/stays/guests/${spouse.id}`, { silent: true }).then(() => {
        if (panel) { panel.both = true; panel.bothVisible = true; paint(); }
      }).catch(() => {});
    }
    $('[data-ft-q]', host)?.focus();
  };

  const done = async (kind, target) => {
    const spouseId = panel?.spouse && panel.both ? panel.spouse.id : null;
    try {
      await link(kind, target, spouseId);
      toast('Связь добавлена');
      changed();
      panel = null;
      await draw();
    } catch (e) { toast(e.message, 'err'); await draw(); }
  };

  let timer = null;
  const search = e => {
    const q = e.target;
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const needle = q.value.trim();
      let list = [];
      try {
        /* батлер связывает только со своими гостями (или новым человеком) — поиск среди своих */
        list = needle.length < 2 ? [] : (await api(`/api/stays/guests?q=${encodeURIComponent(needle)}${can('stays.edit') ? '' : '&mine=1'}`, { silent: true }))
          .filter(x => x.id !== centre);
      } catch (err) { toast(err.message, 'err'); }
      found = list; needleLong = needle.length >= 2;
      paint();
    }, 300);
  };

  const person = (c, people, title, id, cls = '') => html`<button type="button" class="ft-person${cls}" data-ft-person=${id}
    title=${id === c ? 'В центре' : 'Показать в центре'} @click=${() => { if (id !== centre) { centre = id; draw(); } }}>${people.get(id)?.name || '#' + id}${id !== c && title.get(id)
    ? html`<small>${title.get(id)}</small>` : nothing}</button>`;

  const treeView = () => {
    const c = centre;
    const people = new Map(fam.people.map(p => [p.id, p]));
    const title = new Map(fam.kin.map(k => [k.person_id, k.title]));
    const { parents, children, spouses, siblings } = staysFamilyAround(fam, c);
    const name = id => people.get(id)?.name || '#' + id;
    const per = (id, cls) => person(c, people, title, id, cls);
    const del = l => (editable ? html`<button type="button" class="ft-del" data-ft-del=${l.id} title="Удалить связь"
      aria-label="Удалить связь" @click=${e => removeLink(e, l)}>×</button>` : nothing);
    const vline = l => html`<span class="ft-link ft-v">│${del(l)}</span>`;
    const spouseLine = l => html`<span class="ft-link ft-h">${editable
      ? html`<label class="ft-former" title="Бывшие супруги"><input type="checkbox" data-ft-former=${l.id} .checked=${!!l.former}
          @change=${e => setFormer(e, l)}> бывшие</label>`
      : (l.former ? 'бывшие' : '')}${l.former ? '┄' : '═'}${del(l)}</span>`;
    const half = Math.ceil(siblings.length / 2);
    const sib = id => html`<span class="ft-node">${per(id, ' ft-sib')}</span>`;
    return html`<div class="ft-tree">
        ${parents.length ? html`<div class="ft-row">${parents.map(p => html`<span class="ft-node ft-col">${per(p.id)}${vline(p.link)}</span>`)}</div>` : nothing}
        <div class="ft-row">${siblings.slice(0, half).map(sib)}
          <span class="ft-node">${per(c, ' ft-centre')}</span>
          ${spouses.map(s => html`<span class="ft-node">${spouseLine(s.link)}${per(s.id)}</span>`)}
          ${siblings.slice(half).map(sib)}</div>
        ${children.length ? html`<div class="ft-row">${children.map(ch => html`<span class="ft-node ft-col">${vline(ch.link)}${per(ch.id)}</span>`)}</div>` : nothing}
      </div>
      <div class="sb-line">${c !== guestId ? html`<button type="button" class="btn btn-sm btn-ghost" data-ft-home
          @click=${() => { centre = guestId; draw(); }}>← к ${name(guestId)}</button>` : nothing}
        ${editable ? Object.entries(STAYS_FAMILY_ADD).map(([k, t]) => html`<button type="button" class="btn btn-sm" data-ft-add=${k} @click=${() => openPanel(k)}>${t}</button>`) : nothing}</div>
      <div data-ft-panel>${panelView()}</div>
      <h4>Все родственники</h4>
      <div class="ft-kin">${fam.kin.length ? fam.kin.map(k => html`<div><button type="button" class="ft-kin-name" data-ft-person=${k.person_id}
        @click=${() => { if (k.person_id !== centre) { centre = k.person_id; draw(); } }}>${name(k.person_id)}</button>
        <span class="muted">— ${k.title}</span></div>`) : html`<span class="muted">родственников нет</span>`}</div>`;
  };

  const panelView = () => {
    if (!panel) return nothing;
    const { kind, spouse, blocked, both, bothVisible } = panel;
    return html`<div class="ft-add">
      <b>${STAYS_FAMILY_ADD_TITLE[kind]}</b>
      <div class="sb-line"><input type="search" data-ft-q placeholder="Найти гостя: фамилия" @input=${search}></div>
      <div class="sb-line" data-ft-found>${found === null ? nothing
        : found.length ? found.map(x => html`<button type="button" class="btn btn-sm btn-ghost" data-ft-pick=${x.id}
            @click=${e => { e.currentTarget.disabled = true; done(kind, { guest_id: x.id }); }}>${x.short}</button>`)
        : (needleLong ? html`<span class="muted">не найдено</span>` : nothing)}</div>
      <div class="sb-line"><span class="muted">или новый:</span>
        <input data-ft-last placeholder="Фамилия"><input data-ft-first placeholder="Имя">
        <select data-ft-gender title="Пол">${Object.entries(STAYS_GENDER).map(([v, t]) => html`<option value=${v}>${t}</option>`)}</select>
        <button type="button" class="btn btn-sm btn-primary" data-ft-create ?disabled=${!!blocked} @click=${e => {
          const last = $('[data-ft-last]', host).value.trim();
          if (!last) { toast('Укажите фамилию', 'warn'); return; }
          e.currentTarget.disabled = true;
          done(kind, { new_guest: { last_name: last, first_name: $('[data-ft-first]', host).value.trim(),
            gender: $('[data-ft-gender]', host).value } });
        }}>Создать и связать</button></div>
      ${blocked ? html`<div class="muted" data-ft-blocked>${blocked}</div>` : nothing}
      ${spouse ? html`<label class="chk" ?hidden=${!bothVisible}><input type="checkbox" data-ft-both .checked=${both}
        @change=${e => { panel.both = e.target.checked; }}> и ребёнок: ${spouse.name}</label>` : nothing}
      <div><button type="button" class="btn btn-sm btn-ghost" data-ft-cancel @click=${() => { panel = null; paint(); }}>Отмена</button></div></div>`;
  };

  const removeLink = async (e, l) => {
    e.currentTarget.disabled = true;
    try {
      await api(`/api/stays/guest-links/${l.id}`, { method: 'DELETE' });
      toast('Связь удалена');
      changed();
    } catch (err) { toast(err.message, 'err'); }
    await draw();
  };
  const setFormer = async (e, l) => {
    try {
      await api(`/api/stays/guest-links/${l.id}`, { method: 'PATCH', body: { former: e.target.checked } });
      changed();
    } catch (err) { toast(err.message, 'err'); }
    await draw();
  };

  const draw = async () => {
    const fresh = loadGenerationFor(host);
    let data;
    try {
      data = await api(`/api/stays/guests/${centre}/family`, { silent: true });
    } catch (e) {
      if (fresh()) render(html`<p class="muted">${e.message}</p>`, mount(host));
      return false;
    }
    if (!fresh()) return false;
    fam = data;
    paint();
    return true;
  };
  return draw();          // true — дерево нарисовано (false — ошибка: можно запросить снова)
}

/* ── мост к общей области имён (генерируется tools/gen_js_globals.py; уйдёт вместе с переходом файла на import/export) ── */
Object.assign(globalThis, {
  renderFamilyTree,
});
/* ── конец моста ── */
