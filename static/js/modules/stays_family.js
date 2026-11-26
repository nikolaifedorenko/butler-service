/* Визуальный редактор первичных семейных связей гостя. Сервер проверяет права,
   циклы и число родителей. Ребёнок и обе связи сохраняются одним запросом. */
'use strict';

import { can } from '../app.js';
import { $, api, loadGenerationFor, toast } from '../core.js';
import { guestPickContent } from '../ui/guest_picker.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { STAYS_GENDER } from './stays_forms.js';

const STAYS_FAMILY_ADD = { parent: '+ родитель', spouse: '+ супруг(а)', partner: '+ партнёр', child: '+ ребёнок' };
const STAYS_FAMILY_ADD_TITLE = { parent: 'Добавить родителя', spouse: 'Добавить супруга(у)',
  partner: 'Добавить партнёра', child: 'Добавить ребёнка' };

/* кто вокруг центра c: родители, дети, супруги и партнёры (со связями — для кнопок) и сиблинги */
function staysFamilyAround(fam, c) {
  const links = fam.links || [];
  const parents = links.filter(l => l.kind === 'parent' && l.b === c).map(l => ({ id: l.a, link: l }));
  const children = links.filter(l => l.kind === 'parent' && l.a === c).map(l => ({ id: l.b, link: l }));
  const spouses = links.filter(l => l.kind === 'spouse' && (l.a === c || l.b === c))
    .map(l => ({ id: l.a === c ? l.b : l.a, link: l }));
  const partners = links.filter(l => l.kind === 'partner' && (l.a === c || l.b === c))
    .map(l => ({ id: l.a === c ? l.b : l.a, link: l }));
  const up = new Set(parents.map(p => p.id));
  const siblings = [...new Set(links.filter(l => l.kind === 'parent' && up.has(l.a) && l.b !== c).map(l => l.b))];
  return { parents, children, spouses, partners, siblings };
}

export async function renderFamilyTree(host, guestId, { editable = false, onChange = null } = {}) {
  let centre = guestId;
  let fam = null;
  let panel = null;
  let moving = false;
  const changed = () => { if (onChange) onChange(); };
  const paint = () => render(treeView(), mount(host));
  const name = id => fam.people.find(person => person.id === id)?.name || '#' + id;
  const lookup = () => ({ query: '', results: null, request: 0, timer: null });

  const link = (kind, target, extra, source = centre) => api(`/api/stays/guests/${source}/links`, { method: 'POST', body: {
    ...target, kind: kind === 'parent' || kind === 'child' ? 'parent' : kind,
    other_is_parent: kind === 'parent', ...extra } });

  const openPanel = kind => {
    const around = staysFamilyAround(fam, centre);
    const current = around.spouses.find(s => !s.link.former);
    const blocked = (kind === 'parent' && around.parents.length >= 2 && 'У гостя уже два родителя — сначала удалите связь') || '';
    const related = [...around.spouses, ...around.partners].sort((a, b) => Number(a.link.former) - Number(b.link.former));
    const candidates = related.filter((item, index) => related.findIndex(other => other.id === item.id) === index);
    const canEditAll = can('stays.edit');
    panel = { kind, blocked, formerSpouse: kind === 'spouse' && current ? current : null, makeFormer: true,
      saving: false, first: lookup(), second: lookup(), mode: 'existing', child: null, secondParent: null,
      draft: { last_name: '', first_name: '', gender: '' }, candidates: canEditAll ? candidates : [] };
    const active = panel;
    if (kind === 'child' && !canEditAll) {
      // Карточка под тем же правом подтверждает, что батлер может выбрать этого гостя.
      Promise.all(candidates.slice(0, 6).map(async candidate => {
        try {
          await api(`/api/stays/guests/${candidate.id}`, { silent: true });
          return candidate;
        } catch { return null; }
      })).then(allowed => {
        if (panel !== active || !host.isConnected) return;
        active.candidates = allowed.filter(Boolean);
        paint();
      });
    }
    paint();
    $('[data-ft-q]', host)?.focus();
  };

  const moveCentre = id => {
    if (id === centre || moving || panel?.saving) return;
    panel = null;
    moving = true;
    paint();
    draw(id);
  };

  const done = async (kind, target, extra = {}, source = centre) => {
    const active = panel;
    if (!active || active.saving) return;
    if (kind === 'spouse' && active.formerSpouse && active.makeFormer) extra.also_former_id = active.formerSpouse.link.id;
    active.saving = true;
    paint();
    try {
      await link(kind, target, extra, source);
      toast('Связь добавлена');
      changed();
      if (panel === active) { panel = null; await draw(); }
    } catch (e) {
      toast(e.message, 'err');
      if (panel !== active) return;
      active.saving = false;
      if (e.status === 409 && extra.expected_parent_ids && active.child) await chooseChild(active.child.person);
      else paint();
    }
  };

  const search = (slot, e) => {
    const active = panel;
    const field = active[slot];
    field.query = e.target.value;
    clearTimeout(field.timer);
    field.results = null;
    const request = ++field.request;
    const needle = field.query.trim();
    paint();
    if (needle.length < 2) return;
    const fresh = () => host.isConnected && panel === active && field.request === request;
    field.timer = setTimeout(async () => {
      if (!fresh()) return;
      try {
        const list = await api(`/api/stays/guests?details=1&q=${encodeURIComponent(needle)}${can('stays.edit') ? '' : '&mine=1'}`, { silent: true });
        if (!fresh()) return;
        field.results = list.filter(person => person.id !== centre);
        paint();
      } catch (err) { if (fresh()) toast(err.message, 'err'); }
    }, 300);
  };

  const chooseChild = async person => {
    const active = panel;
    const picked = { person, parents: null, error: '' };
    active.child = picked;
    if (active.secondParent?.id === person.id) active.secondParent = null;
    paint();
    $('[data-ft-child-change]', host)?.focus();
    try {
      const family = await api(`/api/stays/guests/${person.id}/family`, { silent: true });
      const people = new Map(family.people.map(guest => [guest.id, guest]));
      picked.parents = family.parents.filter(([id]) => id === person.id).map(([, id]) => people.get(id) || { id, name: '#' + id });
    } catch (err) {
      picked.error = err.message;
    }
    if (panel === active && active.child === picked && host.isConnected) paint();
  };

  const draftFields = active => {
    const { draft } = active;
    const update = (key, e) => { draft[key] = e.target.value; paint(); };
    return html`<div class="sb-line ft-fields">
      <input data-ft-last aria-label="Фамилия" placeholder="Фамилия" .value=${draft.last_name} @input=${e => update('last_name', e)}>
      <input data-ft-first aria-label="Имя" placeholder="Имя" .value=${draft.first_name} @input=${e => update('first_name', e)}>
      <select data-ft-gender aria-label="Пол" @change=${e => update('gender', e)}>
        ${Object.entries(STAYS_GENDER).map(([value, title]) => html`<option value=${value} ?selected=${value === draft.gender}>${title}</option>`)}
      </select>
    </div>`;
  };
  const newGuest = draft => ({ ...draft, last_name: draft.last_name.trim(), first_name: draft.first_name.trim() });
  const searchHint = () => can('stays.guests') ? 'ФИО, телефон или дата рождения' : 'ФИО гостя';
  const resultsView = (people, view) => people === null ? nothing
    : people.length ? people.map(view) : html`<span class="muted">Гости не найдены</span>`;
  const cancel = () => { panel = null; paint(); };

  const childView = active => {
    const existing = active.mode === 'existing';
    const child = existing ? active.child : null;
    const known = child?.parents ?? [];
    const already = known.some(p => p.id === centre);
    const other = known.find(p => p.id !== centre);
    const full = known.length >= 2;
    const second = other ?? active.secondParent;
    const canChooseSecond = !full && !other && (!existing || !!child?.parents);
    const valid = (existing ? !!child?.parents : !!active.draft.last_name.trim()) && !full && (!already || !!second);
    const selectSecond = person => {
      active.secondParent = person;
      clearTimeout(active.second.timer);
      active.second.request++;
      active.second = lookup();
      paint();
      $('[data-ft-second-clear]', host)?.focus();
    };
    const clearSecond = () => { active.secondParent = null; paint(); $('[data-ft-second-q]', host)?.focus(); };
    const candidates = active.candidates;
    const picks = new Map(fam.people.map(person => [person.id, person]));
    const suggestion = ({ id, link: rel }) => {
      const person = picks.get(id);
      if (!person || id === child?.person.id) return nothing;
      const label = rel.kind === 'partner' ? (rel.former ? 'Бывший партнёр' : 'Партнёр')
        : (rel.former ? 'Бывший супруг или супруга' : 'Супруг или супруга');
      return html`<button type="button" class="btn btn-sm guest-pick-button" data-ft-second-pick=${id}
        @click=${() => selectSecond(person)}>${guestPickContent(person, '', label)}</button>`;
    };
    const save = () => {
      if (!valid) return;
      const target = existing ? { guest_id: child.person.id } : { new_guest: newGuest(active.draft) };
      const expected = existing ? { expected_parent_ids: known.map(parent => parent.id) } : {};
      if (already) done('child', target, expected, second.id);
      else done('child', target, other || !second ? expected : { ...expected, also_parent_id: second.id });
    };
    return html`<fieldset class="ft-add ft-child" ?disabled=${active.saving}>
      <legend><b>Добавить ребёнка</b></legend>
      <div class="sb-line" aria-label="Профиль ребёнка">
        ${[['existing', 'Из списка гостей'], ['new', 'Новый профиль']].map(([mode, label]) => html`
          <button type="button" class=${`btn btn-sm${active.mode === mode ? ' btn-primary' : ''}`} data-ft-child-mode=${mode}
            aria-pressed=${active.mode === mode} @click=${() => {
              active.mode = mode;
              if (mode === 'existing' && active.child?.person.id === active.secondParent?.id) active.secondParent = null;
              paint();
            }}>${label}</button>`)}
      </div>
      ${existing ? child ? html`<div class="ft-identity">
        ${guestPickContent(child.person)}
        <button type="button" class="btn btn-sm btn-ghost" data-ft-child-change @click=${() => {
          active.child = null; active.first = lookup(); paint(); $('[data-ft-q]', host)?.focus();
        }}>Выбрать другого ребёнка</button>
        ${child.error ? html`<span role="alert">${child.error}</span>` : !child.parents ? html`<span role="status">Проверяем родительские связи…</span>` : nothing}
      </div>` : html`<label class="ft-search">Найти ребёнка
        <input type="search" data-ft-q .value=${active.first.query} placeholder=${searchHint()} @input=${e => search('first', e)}>
      </label><div class="ft-picks" aria-live="polite">${resultsView(active.first.results, person => html`
        <button type="button" class="btn btn-sm guest-pick-button" data-ft-pick=${person.id}
          @click=${() => chooseChild(person)}>${guestPickContent(person)}</button>`)}</div>` : draftFields(active)}
      ${known.length ? html`<div class="muted">Уже указанное родство
        <ul>${known.map(person => html`<li>${guestPickContent(person)}</li>`)}</ul>
      </div>` : nothing}
      ${!full ? html`<div class="ft-parents">
        <div class="ft-identity"><strong>Первый родитель</strong><span>${name(centre)}</span></div>
        <div class="ft-identity"><strong>Второй родитель</strong>
          ${second ? guestPickContent(second) : html`<span class="muted">Не выбран</span>`}
          ${canChooseSecond && second ? html`<button type="button" class="btn btn-sm btn-ghost"
            data-ft-second-clear @click=${clearSecond}>Убрать второго родителя</button>` : nothing}
        </div>
      </div>` : nothing}
      ${canChooseSecond && !second ? html`<label class="ft-search">Найти второго родителя <span class="muted">(необязательно)</span>
        <input type="search" data-ft-second-q .value=${active.second.query} placeholder=${searchHint()}
          @input=${e => search('second', e)}>
      </label>
      <div class="ft-picks" aria-live="polite">${active.second.query.trim() ? resultsView(
        active.second.results?.filter(person => person.id !== child?.person.id) ?? null,
        person => html`<button type="button" class="btn btn-sm guest-pick-button" data-ft-second-pick=${person.id}
          @click=${() => selectSecond(person)}>${guestPickContent(person)}</button>`) : candidates.map(suggestion)}</div>` : nothing}
      ${full ? html`<span class="muted">У ребёнка уже указаны два родителя.</span>` : already && !second ? html`
        <span class="muted">Связь с первым родителем уже есть. Выберите второго, чтобы добавить связь.</span>` : nothing}
      <div class="sb-line">
        <button type="button" class="btn btn-sm btn-ghost" data-ft-cancel @click=${cancel}>Отмена</button>
        <button type="button" class="btn btn-sm btn-primary" data-ft-create ?disabled=${!valid} @click=${save}>
          Сохранить с ${second ? 'двумя родителями' : 'одним родителем'}
        </button>
      </div>
    </fieldset>`;
  };

  const person = (c, people, title, id, cls = '') => html`<button type="button" class="ft-person${cls}" data-ft-person=${id}
    title=${id === c ? 'В центре' : 'Показать в центре'} @click=${() => moveCentre(id)}>${people.get(id)?.name || '#' + id}${id !== c && title.get(id)
    ? html`<small>${title.get(id)}</small>` : nothing}</button>`;

  const treeView = () => {
    const c = centre;
    const people = new Map(fam.people.map(p => [p.id, p]));
    /* родня бывших браков/союзов помечена сервером — показываем происхождение */
    const title = new Map(fam.kin.map(k => [k.person_id, k.title + (k.via_former ? ' (бывший брак)' : '')]));
    const { parents, children, spouses, partners, siblings } = staysFamilyAround(fam, c);
    const name = id => people.get(id)?.name || '#' + id;
    const per = (id, cls) => person(c, people, title, id, cls);
    const del = l => (editable ? html`<button type="button" class="ft-del" data-ft-del=${l.id} title="Удалить связь"
      aria-label="Удалить связь" ?disabled=${moving || !!panel?.saving} @click=${e => removeLink(e, l)}>×</button>` : nothing);
    const vline = l => html`<span class="ft-link ft-v">│${del(l)}</span>`;
    const currentSpouse = spouses.find(s => !s.link.former);
    const currentPartners = partners.filter(p => !p.link.former);
    /* бывшие — отдельным приглушённым блоком, не в ряду с действующим супругом:
       раньше различались только ┄ против ═ — на экране их не отличить */
    const exes = [...spouses.filter(s => s.link.former).map(s => ({ ...s, kind: 'spouse' })),
                  ...partners.filter(p => p.link.former).map(p => ({ ...p, kind: 'partner' }))];
    const half = Math.ceil(siblings.length / 2);
    const sib = id => html`<span class="ft-node">${per(id, ' ft-sib')}</span>`;
    const toFormer = l => html`<button type="button" class="ft-del" data-ft-former=${l.id} title="Отметить «бывшие»" ?disabled=${moving || !!panel?.saving}
      @click=${() => setFormerValue(l, true)}>развод</button>`;
    const backCurrent = l => html`<button type="button" class="ft-del" data-ft-former-off=${l.id} title="Сделать действующим" ?disabled=${moving || !!panel?.saving}
      @click=${() => setFormerValue(l, false)}>вернуть</button>`;
    const exView = x => html`<div class="ft-ex-row">${per(x.id, ' ft-muted')}
        ${editable ? html`<span class="ft-actions">${backCurrent(x.link)}${del(x.link)}</span>` : nothing}</div>`;
    return html`<div class="ft-tree">
        ${parents.length ? html`<div class="ft-row">${parents.map(p => html`<span class="ft-node ft-col">${per(p.id)}${vline(p.link)}</span>`)}</div>` : nothing}
        <div class="ft-row">${siblings.slice(0, half).map(sib)}
          <span class="ft-node">${per(c, ' ft-centre')}</span>
          ${currentSpouse ? html`<span class="ft-node"><span class="ft-link ft-h">═</span>${per(currentSpouse.id)}
            ${editable ? html`<span class="ft-actions">${toFormer(currentSpouse.link)}${del(currentSpouse.link)}</span>` : nothing}</span>` : nothing}
          ${siblings.slice(half).map(sib)}</div>
        ${children.length ? html`<div class="ft-row">${children.map(ch => html`<span class="ft-node ft-col">${vline(ch.link)}${per(ch.id)}</span>`)}</div>` : nothing}
      </div>
      ${currentPartners.length ? html`<div class="ft-block"><h5>Партнёры</h5>${currentPartners.map(p =>
        html`<div class="ft-ex-row">${per(p.id)}${editable ? html`<span class="ft-actions">${toFormer(p.link)}${del(p.link)}</span>` : nothing}</div>`)}</div>` : nothing}
      ${exes.length ? html`<div class="ft-block ft-ex-block"><h5>Бывшие</h5>${exes.map(exView)}</div>` : nothing}
      <div class="sb-line">${c !== guestId ? html`<button type="button" class="btn btn-sm btn-ghost" data-ft-home
          @click=${() => moveCentre(guestId)}>← к ${name(guestId)}</button>` : nothing}
        ${editable ? Object.entries(STAYS_FAMILY_ADD).map(([k, t]) => html`<button type="button" class="btn btn-sm" data-ft-add=${k} ?disabled=${moving || !!panel?.saving} @click=${() => openPanel(k)}>${t}</button>`) : nothing}</div>
      <div data-ft-panel>${panelView()}</div>
      <h4>Все родственники</h4>
      <div class="ft-kin">${fam.kin.length ? fam.kin.map(k => html`<div><button type="button" class="ft-kin-name" data-ft-person=${k.person_id}
        @click=${() => moveCentre(k.person_id)}>${name(k.person_id)}</button>
        <span class="muted">— ${k.title}${k.via_former ? ' (бывший брак)' : ''}</span></div>`) : html`<span class="muted">родственников нет</span>`}</div>`;
  };

  const panelView = () => {
    const active = panel;
    if (!active) return nothing;
    if (active.kind === 'child') return childView(active);
    const { kind, blocked, formerSpouse } = active;
    return html`<fieldset class="ft-add" ?disabled=${active.saving}>
      <legend><b>${STAYS_FAMILY_ADD_TITLE[kind]}</b></legend>
      <label class="ft-search">Найти гостя
        <input type="search" data-ft-q .value=${active.first.query} placeholder=${searchHint()} @input=${e => search('first', e)}>
      </label>
      <div class="ft-picks" data-ft-found aria-live="polite">${resultsView(active.first.results, person => html`
        <button type="button" class="btn btn-sm guest-pick-button" data-ft-pick=${person.id}
          @click=${() => done(kind, { guest_id: person.id })}>${guestPickContent(person)}</button>`)}</div>
      <div class="sb-line"><span class="muted">Или новый профиль</span>
        ${draftFields(active)}
        <button type="button" class="btn btn-sm btn-primary" data-ft-create ?disabled=${!!blocked} @click=${() => {
          const guest = newGuest(active.draft);
          if (!guest.last_name) { toast('Укажите фамилию', 'warn'); return; }
          done(kind, { new_guest: guest });
        }}>Создать и связать</button></div>
      ${blocked ? html`<div class="muted" data-ft-blocked>${blocked}</div>` : nothing}
      ${formerSpouse ? html`<label class="chk"><input type="checkbox" data-ft-make-former .checked=${active.makeFormer}
        @change=${e => { active.makeFormer = e.target.checked; }}> Прежний брак (${name(formerSpouse.id)})
        станет бывшим</label>` : nothing}
      <div><button type="button" class="btn btn-sm btn-ghost" data-ft-cancel @click=${cancel}>Отмена</button></div>
    </fieldset>`;
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
  const setFormerValue = async (l, value) => {
    try {
      await api(`/api/stays/guest-links/${l.id}`, { method: 'PATCH', body: { former: value } });
      toast(value ? 'Отмечено «бывшие»' : 'Связь снова действующая');
      changed();
    } catch (err) { toast(err.message, 'err'); }
    await draw();
  };

  const draw = async (id = centre) => {
    const fresh = loadGenerationFor(host);
    let data;
    try {
      data = await api(`/api/stays/guests/${id}/family`, { silent: true });
    } catch (e) {
      if (fresh()) {
        if (moving) { moving = false; paint(); toast(e.message, 'err'); }
        else render(html`<p class="muted">${e.message}</p>`, mount(host));
      }
      return false;
    }
    if (!fresh()) return false;
    centre = id;
    moving = false;
    fam = data;
    paint();
    return true;
  };
  return draw();          // true — дерево нарисовано (false — ошибка: можно запросить снова)
}
