import { navigate, registerModule } from '../app.js';
import { $, api, closeDrawer, closeModal, loadGenerationFor, openModal, state, toast } from '../core.js';
import { html, mount, nothing, render, svg } from '../ui/html.js';
import { openGuestCard } from './stays_forms.js';
import { renderFamilyTree } from './stays_family.js';
import { FAMILY_CARD, FAMILY_UNIONS, familyLabels, familyLayout } from './stays_family_layout.js';

const ZOOMS = [60, 80, 100, 120, 140, 160];
const LEGEND = { parent: 'Родители и дети', ...FAMILY_UNIONS };

function initials(name) {
  return name.split(/\s+/).slice(0, 2).map(word => Array.from(word)[0] || '').join('').toUpperCase();
}

function bindRelationshipForm(modal, form, perform, onSaved) {
  const editor = $(`#${form}`, modal);
  const submit = $(`[type="submit"][form="${form}"]`, modal);
  const output = $('[data-family-error]', editor);
  editor.onsubmit = async event => {
    event.preventDefault();
    if (submit.disabled) return;
    output.textContent = '';
    submit.disabled = true;
    try {
      await perform(editor.elements);
      if (editor.isConnected) closeModal();
      onSaved();
    } catch (err) { output.textContent = err.message; }
    finally { submit.disabled = false; }
  };
}

function edgeEditor(link, names, returnFocusTo, onSaved) {
  const marriage = link.kind === 'spouse';
  const form = 'family-canvas-union-form';
  openModal({
    title: marriage ? 'Брак' : 'Партнёрство',
    subtitle: names.join(' и '), background: $('#app'), returnFocusTo,
    body: html`<form id=${form} class="family-canvas-editor">
      ${marriage ? html`<label>Начало брака <span class="muted">(необязательно)</span>
        <input name="marriage_start" type="date" .value=${link.marriage_start || ''}></label>` : nothing}
      <label class="chk"><input name="former" type="checkbox" .checked=${link.former}
        @change=${event => { const end = event.currentTarget.form.elements.marriage_end; if (end) end.closest('label').hidden = !event.target.checked; }}>
        ${marriage ? 'Брак завершён' : 'Партнёрство завершено'}</label>
      ${marriage ? html`<label ?hidden=${!link.former}>Окончание брака <span class="muted">(необязательно)</span>
        <input name="marriage_end" type="date" .value=${link.marriage_end || ''}></label>` : nothing}
      <p class="muted">Связи с детьми сохранятся.</p><p role="alert" data-family-error></p>
    </form>`,
    footer: html`<button type="button" class="btn btn-ghost" @click=${closeModal}>Отмена</button>
      <button class="btn btn-primary" type="submit" form=${form}>Сохранить</button>`,
    onMount(modal) {
      bindRelationshipForm(modal, form, fields => {
        const former = fields.former.checked;
        const patch = {};
        if (former !== link.former) patch.former = former;
        if (marriage) {
          const start = fields.marriage_start.value || null;
          const end = fields.marriage_end.value || null;
          if (start !== (link.marriage_start || null)) patch.marriage_start = start;
          if (former && end !== (link.marriage_end || null)) patch.marriage_end = end;
        }
        if (Object.keys(patch).length) {
          return api(`/api/stays/guest-links/${link.id}`, { method: 'PATCH', body: patch, silent: true });
        }
      }, onSaved);
    },
  });
}

function confirmRemoval(links, name, child, returnFocusTo, onSaved) {
  const shared = links.length > 1;
  const first = links[0];
  const form = 'family-canvas-delete-form';
  openModal({
    title: 'Удалить ошибочную связь',
    subtitle: child ? name(child) : [name(first.a), name(first.b)].join(' и '),
    background: $('#app'), returnFocusTo,
    body: html`<form id=${form} class="family-canvas-editor">
      ${shared ? html`<fieldset><legend>С каким родителем удалить связь?</legend>
        ${links.map(link => html`<label class="chk"><input type="radio" name="link" required value=${link.id}> ${name(link.a)}</label>`)}
      </fieldset>` : child ? html`<p>Родитель · ${name(first.a)}</p>` : nothing}
      <p class="muted">Карточки гостей и остальные связи сохранятся.</p><p role="alert" data-family-error></p>
    </form>`,
    footer: html`<button type="button" class="btn btn-ghost" @click=${closeModal}>Отмена</button>
      <button class="btn btn-danger" type="submit" form=${form}>Удалить связь</button>`,
    onMount(modal) {
      bindRelationshipForm(modal, form, fields => {
        const link = shared ? fields.link.value : first.id;
        return api(`/api/stays/guest-links/${link}`, { method: 'DELETE', silent: true });
      }, onSaved);
    },
  });
}

export function mountFamilyCanvas(host, guest, { onBack, onPerson, onChanged, isCurrent, backLabel = 'К списку гостей' }) {
  let zoomIndex = ZOOMS.indexOf(100);
  let diagram = null;
  let active = guest.id;
  let presented = guest.id;
  let labels = new Map();
  let stableLabels = labels;
  let focusLoading = false;
  let layoutDirty = true;
  let error = '';
  let request = 0;
  const zoom = () => ZOOMS[zoomIndex] / 100;
  const viewport = () => $('.family-canvas-scroll', host);
  const margin = (scroll, scale) => Math.max(0, (scroll.clientWidth - diagram.width * scale) / 2);

  const personById = id => diagram?.nodes.find(person => person.id === id);
  const nameOf = id => personById(id)?.name || String(id);
  const changed = () => { if (isCurrent()) refresh(); onChanged?.(); };
  const center = () => {
    const scroll = viewport();
    const origin = diagram?.nodes.find(person => person.id === guest.id);
    if (!scroll || !origin) return;
    scroll.scrollLeft = origin.x * zoom() + margin(scroll, zoom()) - scroll.clientWidth / 2;
    scroll.scrollTop = (origin.y + FAMILY_CARD.height / 2) * zoom() - scroll.clientHeight / 2;
  };

  const changeZoom = delta => {
    const scroll = viewport();
    const current = zoom();
    const x = (scroll.scrollLeft + scroll.clientWidth / 2 - margin(scroll, current)) / current;
    const y = (scroll.scrollTop + scroll.clientHeight / 2) / current;
    zoomIndex += delta;
    paint();
    scroll.scrollLeft = x * zoom() + margin(scroll, zoom()) - scroll.clientWidth / 2;
    scroll.scrollTop = y * zoom() - scroll.clientHeight / 2;
  };

  const returnTo = selector => () => $(selector, host) || $('[data-family-person="' + active + '"]', host) || $('h2', host);
  const control = (key, label, text, at, action, cls = '') => html`<button type="button"
    class="family-canvas-edge-action ${cls}" data-family-control=${key} aria-label=${label} title=${label}
    style=${`left:${at.x}px;top:${at.y}px`} @click=${() => action(returnTo(`[data-family-control="${key}"]`))}>${text}</button>`;

  const addRelationship = (source, initialAdd, returnFocusTo) => openModal({
    title: initialAdd.kind === 'child' && initialAdd.secondParentId ? 'Добавить общего ребёнка' : 'Добавить связь',
    subtitle: initialAdd.secondParentId ? [nameOf(source), nameOf(initialAdd.secondParentId)].join(' и ') : nameOf(source),
    wide: true, background: $('#app'), returnFocusTo,
    body: html`<div class="ft" data-family-canvas-editor><p class="muted" role="status">Загрузка семейных связей…</p></div>`,
    onMount(modal) {
      const editor = $('[data-family-canvas-editor]', modal);
      renderFamilyTree(editor, source, {
        editable: true, initialAdd, onCancel: closeModal,
        onChange: () => { if (editor.isConnected) closeModal(); changed(); },
      }).catch(err => { if (editor.isConnected) toast(err.message, 'err'); });
    },
  });

  const childAction = (parents, returnFocusTo) => {
    const available = parents.filter(id => personById(id)?.editable);
    if (!available.length) return;
    const [source, secondParentId] = available;
    addRelationship(source, { kind: 'child', secondParentId }, returnFocusTo);
  };

  const relationshipMenu = (title, subtitle, menu, returnFocusTo) => openModal({
    title, subtitle, background: $('#app'), returnFocusTo,
    body: html`<div class="family-canvas-action-list">${menu.map(([label, run]) => html`<button type="button"
      class="btn" @click=${() => { closeModal(); run(); }}>${label}</button>`)}</div>`,
  });

  const branchActions = (target, parents, returnFocusTo) => {
    const menu = [];
    if (parents.some(id => personById(id)?.editable)) {
      menu.push(['Ещё ребёнок в этой ветви', () => childAction(parents, returnFocusTo)]);
    }
    if (personById(target)?.editable) {
      menu.push([`Родитель для ${nameOf(target)}`, () => addRelationship(target, { kind: 'parent' }, returnFocusTo)]);
    }
    relationshipMenu('Добавить связь в ветви', nameOf(target), menu, returnFocusTo);
  };

  const nodeActions = (id, returnFocusTo) => {
    const parents = diagram.edges.flatMap(edge => edge.targets || [])
      .find(target => target.id === id)?.links.map(link => link.a) || [];
    const parental = parents.some(parent => personById(parent)?.editable);
    const menu = [
      ['Родитель', 'parent'], ['Ребёнок', 'child'], ['Супруг или супруга', 'spouse'],
      ['Бывший супруг или супруга', 'spouse', true], ['Партнёр', 'partner'],
    ].map(([title, kind, former]) => [title, () => addRelationship(id, { kind, former }, returnFocusTo)]);
    if (parental) menu.splice(2, 0, ['Брат или сестра', () => childAction(parents, returnFocusTo)]);
    relationshipMenu('Добавить связь', nameOf(id), menu, returnFocusTo);
  };

  const nodeView = person => {
    const current = person.id === active;
    const year = person.birth_date?.slice(0, 4);
    const label = current ? 'Активный гость' : labels.get(person.id);
    const x = person.x - FAMILY_CARD.width / 2;
    return html`<div class="family-canvas-node" data-family-node=${person.id} ?data-family-active=${current}
        style=${`left:${x}px;top:${person.y}px;width:${FAMILY_CARD.width}px;height:${FAMILY_CARD.height}px`}>
      <button type="button" class="family-canvas-person" data-family-person=${person.id} aria-pressed=${current}
        title=${[person.name, label, year].filter(Boolean).join(' · ')}
        @click=${() => choose(person.id)}>
        <span class="family-canvas-initials" aria-hidden="true">${initials(person.name)}</span>
        <span class="family-canvas-details">
          <span class="family-canvas-name">${person.name}</span>
          ${label ? html`<span class="family-canvas-relation">${label}</span>` : nothing}
          ${year ? html`<span class="family-canvas-year">${year}</span>` : nothing}
        </span>
      </button>
      ${current && person.can_open_card ? html`<button type="button" class="btn btn-ghost family-canvas-card"
        data-family-card=${person.id} @click=${() => onPerson(person.id, () => active === person.id)}>Карточка</button>` : nothing}
      </div>`;
  };

  const edgeControls = edge => {
    if (edge.link) {
      const { link, x, y } = edge;
      const parents = [link.a, link.b];
      const names = parents.map(nameOf);
      const pairName = names.join(' и ');
      const addChild = parents.some(id => personById(id)?.editable);
      return html`
        ${link.editable ? control(`union-${link.id}`, `Изменить ${link.kind === 'spouse' ? 'брак' : 'партнёрство'} · ${pairName}`,
          edge.label, { x, y }, restore => edgeEditor(link, names, restore, changed), 'family-canvas-union-label') : nothing}
        ${addChild ? control(`union-add-${link.id}`, `Добавить ребёнка · ${pairName}`, '+', { x: x - 88, y: y + 20 },
          restore => childAction(parents, restore)) : nothing}
        ${link.editable ? control(`union-remove-${link.id}`, `Удалить связь · ${pairName}`, '−', { x: x + 88, y: y + 20 },
          restore => confirmRemoval([link], nameOf, null, restore, changed), 'family-canvas-minus') : nothing}`;
    }
    return edge.targets.map(target => {
      const parents = target.links.map(link => link.a);
      const canAdd = [...parents, target.id].some(id => personById(id)?.editable);
      const removable = target.links.filter(link => link.editable);
      return html`
        ${canAdd ? control(`parent-add-${target.id}`, `Добавить связь в ветви · ${nameOf(target.id)}`, '+',
          { x: target.x - 22, y: target.y }, restore => branchActions(target.id, parents, restore)) : nothing}
        ${removable.length ? control(`parent-remove-${target.id}`, `Удалить родительскую связь · ${nameOf(target.id)}`, '−',
          { x: target.x + 22, y: target.y }, restore => confirmRemoval(removable, nameOf, target.id, restore, changed), 'family-canvas-minus') : nothing}`;
    });
  };

  const diagramView = () => {
    const { width, height, nodes, edges } = diagram;
    return html`<div class="family-canvas-scroll" tabindex="0" role="region" aria-label="Холст семейного дерева">
      <div class="family-canvas-size" style=${`width:${width * zoom()}px;height:${height * zoom()}px`}>
        <div class="family-canvas-stage" style=${`width:${width}px;height:${height}px;transform:scale(${zoom()})`}>
          <svg class="family-canvas-lines" width=${width} height=${height} aria-hidden="true">
            ${edges.map(edge => svg`<g>
              <title>${edge.title}</title>
              <path class="family-canvas-edge-gap" d=${edge.path}></path>
              <path class="family-canvas-edge" data-family-kind=${edge.kind} d=${edge.path}></path>
            </g>`)}
            ${edges.filter(edge => edge.label && !edge.link.editable).map(edge => svg`<text class="family-canvas-edge-label"
              data-family-kind=${edge.kind} x=${edge.x} y=${edge.y}>${edge.label}</text>`)}
          </svg>
          ${nodes.map(nodeView)}
          ${edges.map(edgeControls)}
          ${personById(active)?.editable ? control(`person-${active}`, `Добавить связь гостю · ${nameOf(active)}`, '+',
            { x: personById(active).x + FAMILY_CARD.width / 2 + 19, y: personById(active).y + FAMILY_CARD.height / 2 },
            restore => nodeActions(active, restore)) : nothing}
        </div>
      </div>
    </div>`;
  };

  const paint = () => render(html`
    <div class="family-canvas-top">
      <button type="button" class="btn btn-sm" @click=${onBack}>← ${backLabel}</button>
      ${diagram ? html`<div class="family-canvas-tools">
        <button type="button" class="btn btn-sm btn-ghost" @click=${() => { choose(guest.id); center(); }}>К исходному гостю</button>
        <div class="family-canvas-zoom">
          <button type="button" class="btn btn-sm btn-ghost" aria-label="Уменьшить масштаб" ?disabled=${zoomIndex === 0}
            @click=${() => changeZoom(-1)}>−</button>
          <output aria-label="Масштаб">${ZOOMS[zoomIndex]}%</output>
          <button type="button" class="btn btn-sm btn-ghost" aria-label="Увеличить масштаб" ?disabled=${zoomIndex === ZOOMS.length - 1}
            @click=${() => changeZoom(1)}>+</button>
        </div>
      </div>` : nothing}
    </div>
    <div class="page-head family-canvas-heading"><div>
      <h2 tabindex="-1">Семейное дерево</h2>
      <div class="sub" aria-live="polite" aria-busy=${focusLoading}>${diagram ? `Родство относительно гостя · ${nameOf(active)}` : guest.name}</div>
    </div></div>
    ${error ? html`<div class="panel" role="alert"><p>${error}</p>
      <button type="button" class="btn" @click=${refresh}>Повторить</button></div>` : nothing}
    ${diagram ? html`
      ${diagramView()}
      ${diagram.nodes.length === 1 ? html`<p class="muted family-canvas-hint">У гостя пока нет семейных связей.</p>`
        : html`<ul class="family-canvas-legend" aria-label="Обозначения">
          ${Object.entries(LEGEND).filter(([kind]) => diagram.edges.some(edge => edge.kind === kind))
            .map(([kind, label]) => html`<li><span data-family-kind=${kind}></span>${label}</li>`)}
        </ul>
        <details class="family-canvas-relationships">
          <summary>Связи списком</summary>
          <ul>${diagram.edges.map(edge => html`<li>${edge.title}</li>`)}</ul>
        </details>`}
    ` : error ? nothing : html`<p class="muted" role="status">Загрузка дерева…</p>`}`, host);

  function choose(id) {
    if (id === active) return;
    active = id;
    labels = new Map();
    focusLoading = true;
    refresh({ layout: false });
  }

  async function refresh({ layout = true } = {}) {
    // Новый выбор гостя может заменить запрос после правки, но должен получить и новую схему.
    if (layout) layoutDirty = true;
    const current = ++request;
    const base = `/api/stays/guests/${guest.id}/family`;
    const live = () => current === request && isCurrent();
    error = '';
    paint();
    try {
      let data;
      try {
        data = await api(base + (active === guest.id ? '' : `?focus_id=${active}`), { silent: true });
      } catch (err) {
        if (!live()) return;
        if (err.status !== 404 || active === guest.id || !layoutDirty) throw err;
        active = guest.id;      // удалённая связь могла отсоединить выбранного гостя
        data = await api(base, { silent: true });
      }
      if (!live()) return;
      const first = !diagram;
      if (layoutDirty) {
        diagram = familyLayout(data);
        layoutDirty = false;
      }
      labels = stableLabels = familyLabels(data, active);
      presented = active;
      focusLoading = false;
      paint();
      if (first) center();
    } catch (err) {
      if (!live()) return;
      if (diagram) {
        active = presented;
        labels = stableLabels;
        toast(err.message, 'err');
      } else error = err.message;
      focusLoading = false;
      paint();
    }
  }

  refresh();
  $('h2', host).focus({ preventScroll: true });
  return refresh;
}

export function mountGuestFamily(host, guest, { isCurrent, onBack, onChanged, backLabel }) {
  let selection = 0;
  const refresh = mountFamilyCanvas(host, guest, {
    isCurrent, onBack, onChanged, backLabel,
    onPerson(id, active) {
      const current = ++selection;
      const selected = () => isCurrent() && active() && current === selection;
      const changed = () => { if (isCurrent()) refresh(); onChanged?.(); };
      const returnFocusTo = () => $(`[data-family-card="${id}"]`, host) || $(`[data-family-person="${id}"]`, host) || $('h2', host);
      openGuestCard(id, changed, { isCurrent: selected, fromFamily: true, onFamilyChanged: changed, returnFocusTo })
        .catch(err => { if (selected()) toast(err.message, 'warn'); });
    },
  });
}

let boardGuest = null;
registerModule({ views: { guestfamily: loadBoardFamily } });

export function openBoardFamily(guest, { onBack = () => navigate('stays') } = {}) {
  closeDrawer();
  boardGuest = { guest, user: state.user, onBack };
  navigate('guestfamily');
}

function loadBoardFamily() {
  const view = $('#view-guestfamily');
  const current = loadGenerationFor(view);
  const entry = boardGuest;
  boardGuest = null;
  if (state.view !== 'guestfamily') return;
  if (!entry || state.user !== entry.user) { navigate('stays'); return; }
  render(html`<div class="family-canvas"></div>`, mount(view));
  mountGuestFamily($('.family-canvas', view), entry.guest, {
    isCurrent: () => current() && state.user === entry.user && state.view === 'guestfamily',
    onBack: entry.onBack,
    backLabel: 'К шахматке',
  });
}
