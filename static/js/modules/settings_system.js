/* Раздел «Настройки»: экраны «Система» и «Режим эксперта».
   Оболочка, черновик версии справочников и общие помощники — в settings.js.
   Модуль на lit-html (ADR-0013, раздел 7). */
'use strict';

import { can, navigate, registerModule } from '../app.js';
import { $, api, dateRu, toast } from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { renderEngineSettings } from './engine_settings.js';
import { settingsPayloadModal, settingsVersionsModal } from './settings_overview.js';
import {
  closedPeriodText, settingsDraftBarView, settingsEngine, settingsGo, settingsHeadView, settingsHealth,
  settingsPanelView, settingsRenderScreen, settingsUI, settingsUpdateDraftBars,
} from './settings.js';

registerModule({ screens: { system: { render: settingsScreenSystem, icon: 'gear' }, expert: { render: settingsScreenExpert, icon: 'code' } } });

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «СИСТЕМА» — данные, версии и откат, аудит настроек, диагностика, права
   ══════════════════════════════════════════════════════════════════════ */
async function settingsScreenSystem(host) {
  const [engine, health] = await Promise.all([settingsEngine(), settingsHealth().catch(() => null)]);
  const data = settingsUI.data || {};
  const c = data.counts || {};
  const versions = engine?.versions || [];
  const stamp = ts => (ts || '').replace('T', ' ').slice(0, 16);

  const rollback = async v => {
    if (v.id === engine?.active?.id) return toast('Эта версия и так действует', 'warn');
    try {
      const r = await api(`/api/engine-settings?on=${v.valid_from}`, { silent: true });
      settingsUI.draft = JSON.parse(JSON.stringify(r.active.payload));
      settingsUI.screen = 'calc';
      await settingsRenderScreen();
      settingsUpdateDraftBars();
      toast(`Payload версии #${v.id} загружен в черновик — проверьте diff и опубликуйте`, 'ok');
    } catch (e) { toast(e.message, 'err'); }
  };

  render(html`
    ${settingsHeadView('Система',
      'Данные объекта, версии справочников и откат, журнал изменений настроек, диагностика и права.',
      html`<button class="btn btn-sm" id="sy-versions" @click=${() => settingsVersionsModal()}>История версий</button>`)}
    ${settingsPanelView('Данные системы', html`
      <div class="stat-grid">
        <div class="stat"><div class="k">Сотрудников</div><div class="v">${c.employees ?? 0}</div></div>
        <div class="stat"><div class="k">Учётных записей</div><div class="v">${c.users ?? 0}</div></div>
        <div class="stat"><div class="k">Ячеек Графика</div><div class="v">${c.schedule_shifts ?? 0}</div></div>
        <div class="stat"><div class="k">Отметок</div><div class="v">${c.punches ?? 0}</div></div>
        <div class="stat"><div class="k">Ячеек Табеля</div><div class="v">${c.tabel_days ?? 0}</div></div>
        <div class="stat"><div class="k">Закрытий периодов</div><div class="v">${c.period_closings ?? 0}</div></div>
      </div>
      <p class="hint">Пересчёт «всего месяца» не нужен: управленческий табель считается при открытии (view),
        закрытые периоды меняются только явным пересчётом последнего закрытого.</p>`)}
    ${settingsPanelView('Версии справочников и откат', html`
      <div class="table-wrap"><table class="data"><thead><tr>
        <th>№</th><th>Действует с</th><th>Комментарий</th><th>Кто</th><th></th></tr></thead>
      <tbody>${versions.length ? versions.slice(0, 12).map(v => html`<tr style=${v.id === engine?.active?.id ? 'background:#f7f1ea' : nothing}>
        <td><b>#${v.id}</b>${v.id === engine?.active?.id ? html` <span class="badge ok">действует</span>` : nothing}</td>
        <td>${dateRu(v.valid_from)}</td><td>${v.note || '—'}</td><td>${v.created_by || '—'}</td>
        <td class="num" style="white-space:nowrap">
          <button class="btn btn-sm btn-ghost" data-show=${v.id} @click=${() => settingsPayloadModal(v)}>payload</button>
          ${can('settings.edit') ? html`<button class="btn btn-sm btn-ghost" data-rollback=${v.id}
            title="Скопировать payload этой версии в черновик и опубликовать новой датой" @click=${() => rollback(v)}>откатиться</button>` : nothing}
        </td></tr>`) : html`<tr><td colspan="5" class="empty">Версий нет</td></tr>`}</tbody></table></div>
      <p class="hint">Откат — не удаление истории: payload прежней версии копируется в черновик и
        публикуется новой версией с новой датой (история версий остаётся полной). Закрытые периоды
        не меняются (RUL-CLOSED-PERIOD-IMMUTABLE).</p>`)}
    ${settingsPanelView('Изменения настроек за 30 дней', health?.recent?.length
      ? html`${health.recent.map(r => html`<div class="kv"><span class="k">${stamp(r.ts)} · ${r.actor || '—'}</span>
          <span class="v" style="text-align:left;font-weight:600">${r.action} · ${r.target}</span></div>`)}
        <div style="margin-top:10px"><button class="btn btn-sm btn-ghost" data-nav="audit" @click=${() => navigate('audit')}>Весь журнал аудита →</button></div>`
      : html`<p class="hint" style="margin:0">Изменений не было.</p>`)}
    ${settingsPanelView('Диагностика и права', html`
      <div class="grid-2">
        <div>
          <div class="kv"><span class="k">Движок</span><span class="v">v7.1</span></div>
          <div class="kv"><span class="k">Действующая версия справочников</span><span class="v">#${engine?.active?.id ?? '—'}</span></div>
          <div class="kv"><span class="k">Замечаний конфигурации</span><span class="v">${(health?.checks || []).length}</span></div>
          <div class="kv"><span class="k">Последний закрытый период</span><span class="v">${closedPeriodText(health?.periods?.last_closed, { recalcNote: false })}</span></div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-content:flex-start">
          <button class="btn btn-sm" id="sy-selfcheck" @click=${() => window.open('/api/selfcheck', '_blank', 'noopener')}>Самопроверка схемы БД</button>
          ${can('access.manage') ? html`<button class="btn btn-sm" data-nav="access" @click=${() => navigate('access')}>Права доступа ↗</button>` : nothing}
          <button class="btn btn-sm btn-ghost" data-go="expert" @click=${() => settingsGo('expert')}>Режим эксперта (JSON)</button>
        </div>
      </div>`)}
    ${settingsDraftBarView()}`, mount(host));
}

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «РЕЖИМ ЭКСПЕРТА» — тот же черновик, но вторым видом: сырой JSON
   версии справочников и полный список модификаторов (renderEngineSettings).
   ══════════════════════════════════════════════════════════════════════ */
async function settingsScreenExpert(host) {
  render(html`
    ${settingsHeadView('Режим эксперта (JSON)',
      'Полный payload версии справочников и все модификаторы периода. Формы выше и этот экран правят ОДНУ конфигурацию: формы — два вида одного черновика, а не второй источник правды.',
      html`<button class="btn btn-sm" data-go="overview" @click=${() => settingsGo('overview')}>← Обзор</button>`)}
    <div class="panel" id="st-expert"></div>`, mount(host));
  await renderEngineSettings($('#st-expert', host));
}
