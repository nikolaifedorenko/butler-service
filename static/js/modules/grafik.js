'use strict';
/* ══════════════════════════════════════════════════════════════════
   «ГРАФИК» = 4 слоя: обёртка и панель слоёв (T5, норматив 12.10.2026).
   Один пункт меню с четырьмя слоями внутри (Q2): 0 Табель · 1 План/График · 2 Факт ·
   3 Управленческий Табель. Пункт виден, если есть право хотя бы на один слой; сами слои
   фильтруются по правам в grafikLayers(). Доска «Отметки» — отдельный пункт меню (Q7).
   Старые имена разделов (timesheet, schedule, fact, mgmt) — алиасы слоёв: navigate() с ними
   открывает «График» на нужном слое (GRAFIK_ALIAS в app.js).
   Модуль на lit-html (ADR-0013, раздел 7): панели слоёв — постоянные контейнеры обёртки, их
   содержимое рисуют модули слоёв через mount().
   ══════════════════════════════════════════════════════════════════ */
import { can, navigate, registerModule } from '../app.js';
import { $, state } from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { loadFact } from './fact.js';
import { loadMgmt } from './mgmt.js';
import { loadSchedule } from './timesheet_layers.js';
import { loadTabel } from './tabel.js';

const GRAFIK_LAYERS = [
  { view: 'timesheet', num: '0', title: 'Табель', sub: 'первоисточник · бухгалтерия', perm: 'tabel.view' },
  { view: 'schedule', num: '1', title: 'План / График', sub: 'операционный план · флаги', perm: 'schedule.view' },
  { view: 'fact', num: '2', title: 'Факт', sub: 'отметки · округление до шага', perm: 'presence.view' },
  { view: 'mgmt', num: '3', title: 'Управленческий Табель', sub: 'результат · банк · закрытие', perm: 'mgmt.view' },
];

const LAYER_LOADERS = {
  timesheet: () => loadTabel(), schedule: () => loadSchedule(),
  fact: () => loadFact(), mgmt: () => loadMgmt(),
};

const grafikLayers = () => GRAFIK_LAYERS.filter(l => can(l.perm));

registerModule({ views: { grafik: loadGrafik } });

async function loadGrafik() {
  const layers = grafikLayers();
  if (!layers.some(l => l.view === state.grafikLayer)) {
    /* слой по умолчанию — План/График (как раньше открывался раздел «График»);
       без права на него — первый доступный слой цепочки */
    state.grafikLayer = (layers.find(l => l.view === 'schedule') || layers[0] || {}).view || null;
  }
  draw(layers);
  if (!state.grafikLayer) return;
  await LAYER_LOADERS[state.grafikLayer]();
}

/* Обёртка: панель слоёв и четыре панели-контейнера (содержимое рисуют loadTabel, loadSchedule, …).
   Панели существуют всегда — слой может заполняться в фоне, пока показан другой. */
function draw(layers) {
  const host = $('#view-grafik');
  if (!host) return;
  const pane = view => html`<section id=${'view-' + view} class="layer-pane${state.grafikLayer === view ? ' on' : ''}"></section>`;
  render(html`
    <div class="layer-tabs" id="grafik-tabs">${layers.map(l => html`
      <button class="layer-tab${l.view === state.grafikLayer ? ' active' : ''}" data-layer=${l.view}
        title=${`Слой ${l.num} · ${l.title}: ${l.sub}`} @click=${() => navigate(l.view)}>
        <span class="lnum">${l.num}</span>
        <span class="ltt">${l.title}<small>${l.sub}</small></span>
      </button>`)}</div>
    ${pane('timesheet')}${pane('schedule')}${pane('fact')}${pane('mgmt')}
    ${state.grafikLayer ? nothing : html`<div class="panel layer-noperm"><div class="empty">Нет прав ни на один слой «Графика»</div></div>`}`,
  mount(host));
}
