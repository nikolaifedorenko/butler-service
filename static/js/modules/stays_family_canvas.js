import { navigate, registerModule } from '../app.js';
import { $, api, closeDrawer, loadGenerationFor, state, toast } from '../core.js';
import { html, mount, nothing, render, svg } from '../ui/html.js';
import { openGuestCard } from './stays_forms.js';
import { FAMILY_CARD, FAMILY_UNIONS, familyLayout } from './stays_family_layout.js';

const ZOOMS = [60, 80, 100, 120, 140, 160];
const LEGEND = { parent: 'Родители и дети', ...FAMILY_UNIONS };

function initials(name) {
  return name.split(/\s+/).slice(0, 2).map(word => Array.from(word)[0] || '').join('').toUpperCase();
}

export function mountFamilyCanvas(host, guest, { onBack, onPerson, isCurrent, backLabel = 'К списку гостей' }) {
  let zoomIndex = ZOOMS.indexOf(100);
  let diagram = null;
  let error = '';
  let request = 0;
  const zoom = () => ZOOMS[zoomIndex] / 100;
  const viewport = () => $('.family-canvas-scroll', host);
  const margin = (scroll, scale) => Math.max(0, (scroll.clientWidth - diagram.width * scale) / 2);

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

  const nodeView = person => {
    const origin = person.id === guest.id;
    const year = person.birth_date?.slice(0, 4);
    return html`<button type="button" class="family-canvas-person" data-family-person=${person.id}
        ?data-family-origin=${origin} style=${`left:${person.x - FAMILY_CARD.width / 2}px;top:${person.y}px;width:${FAMILY_CARD.width}px;height:${FAMILY_CARD.height}px`}
        title=${[person.name, person.title, year].filter(Boolean).join(' · ')}
        @click=${event => onPerson(person.id, event.currentTarget)}>
      <span class="family-canvas-initials" aria-hidden="true">${initials(person.name)}</span>
      <span class="family-canvas-details">
        <span class="family-canvas-name">${person.name}</span>
        ${origin || person.title ? html`<span class="family-canvas-relation">${origin ? 'Исходный гость' : person.title}</span>` : nothing}
        ${year ? html`<span class="family-canvas-year">${year}</span>` : nothing}
      </span>
    </button>`;
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
            ${edges.filter(edge => edge.label).map(edge => svg`<text class="family-canvas-edge-label"
              data-family-kind=${edge.kind} x=${edge.x} y=${edge.y}>${edge.label}</text>`)}
          </svg>
          ${nodes.map(nodeView)}
        </div>
      </div>
    </div>`;
  };

  const paint = () => render(html`
    <div class="family-canvas-top">
      <button type="button" class="btn btn-sm" @click=${onBack}>← ${backLabel}</button>
      ${diagram ? html`<div class="family-canvas-tools">
        <button type="button" class="btn btn-sm btn-ghost" @click=${center}>К исходному гостю</button>
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
      <h2 tabindex="-1">Семейное дерево</h2><div class="sub">${guest.name}</div>
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

  async function refresh() {
    const current = ++request;
    error = '';
    paint();
    try {
      const data = await api(`/api/stays/guests/${guest.id}/family`, { silent: true });
      if (current !== request || !isCurrent()) return;
      const first = !diagram;
      diagram = familyLayout(data, guest.id);
      paint();
      if (first) center();
    } catch (err) {
      if (current !== request || !isCurrent()) return;
      if (diagram) toast(err.message, 'err');
      else { error = err.message; paint(); }
    }
  }

  refresh();
  $('h2', host).focus({ preventScroll: true });
  return refresh;
}

export function mountGuestFamily(host, guest, { isCurrent, onBack, onChanged, backLabel }) {
  let selection = 0;
  const refresh = mountFamilyCanvas(host, guest, {
    isCurrent, onBack, backLabel,
    onPerson(id, button) {
      const current = ++selection;
      button.focus({ preventScroll: true });
      const selected = () => isCurrent() && current === selection;
      const changed = () => { if (isCurrent()) refresh(); onChanged?.(); };
      const returnFocusTo = () => $(`[data-family-person="${id}"]`, host) || $('h2', host);
      openGuestCard(id, changed, { isCurrent: selected, fromFamily: true, onFamilyChanged: changed, returnFocusTo })
        .catch(err => { if (selected()) toast(err.message, 'warn'); });
    },
  });
}

let boardGuest = null;
registerModule({ views: { guestfamily: loadBoardFamily } });

export function openBoardFamily(guest) {
  closeDrawer();
  boardGuest = { guest, user: state.user };
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
    onBack: () => navigate('stays'),
    backLabel: 'К шахматке',
  });
}
