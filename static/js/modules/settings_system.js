/* Раздел «Настройки»: экраны «Система» и «Режим эксперта».
   Оболочка, черновик версии справочников и общие помощники — в settings.js.
   Модуль на lit-html (ADR-0013, раздел 7). */
'use strict';

import { can, navigate, registerModule } from '../app.js';
import { $, api, closeModal, dateRu, openModal, toast } from '../core.js';
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
      const r = await api(`/api/engine-settings?version_id=${v.id}`, { silent: true });
      settingsUI.draft = JSON.parse(JSON.stringify(r.active.payload));
      settingsUI.screen = 'calc';
      await settingsRenderScreen();
      settingsUpdateDraftBars();
      toast(`Настройки от ${dateRu(v.valid_from)} загружены в черновик. Проверьте изменения и опубликуйте.`, 'ok');
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
      <p class="hint">Чтобы обновить последний закрытый период, выберите «Пересчитать» в управленческом табеле.</p>`)}
    ${settingsPanelView('Версии справочников и откат', html`
      <div class="table-wrap" tabindex="0"><table class="data"><thead><tr>
        <th>Действует с</th><th>Комментарий</th><th>Кто</th><th>Опубликовано</th><th></th></tr></thead>
      <tbody>${versions.length ? versions.slice(0, 12).map(v => html`<tr style=${v.id === engine?.active?.id ? 'background:var(--surface-3)' : nothing}>
        <td>${dateRu(v.valid_from)}${v.id === engine?.active?.id ? html` <span class="badge ok">действует</span>` : nothing}</td><td>${v.note || '—'}</td><td>${v.created_by || '—'}</td><td>${(v.created_at || '').replace('T', ' ').slice(0, 19)}</td>
        <td class="num" style="white-space:nowrap">
          <button class="btn btn-sm btn-ghost" data-show=${v.id} @click=${() => settingsPayloadModal(v)}>Открыть справочники</button>
          ${can('settings.edit') ? html`<button class="btn btn-sm btn-ghost" data-rollback=${v.id}
            title="Восстановить настройки в черновике" @click=${() => rollback(v)}>Восстановить</button>` : nothing}
        </td></tr>`) : html`<tr><td colspan="5" class="empty">История пуста</td></tr>`}</tbody></table></div>
      <p class="hint">Восстановление копирует прежние настройки в черновик. Укажите дату и опубликуйте изменения.</p>`)}
    ${settingsPanelView('Изменения настроек за 30 дней', health?.recent?.length
      ? html`${health.recent.map(r => html`<div class="kv"><span class="k">${stamp(r.ts)} · ${r.actor || '—'}</span>
          <span class="v" style="text-align:left;font-weight:600">${r.title || "Изменение настроек"}</span></div>`)}
        <div style="margin-top:10px"><button class="btn btn-sm btn-ghost" data-nav="audit" @click=${() => navigate('audit')}>Весь журнал аудита →</button></div>`
      : html`<p class="hint" style="margin:0">Изменений не было.</p>`)}
    ${settingsPanelView('Диагностика и права', html`
      <div class="grid-2">
        <div>
          <div class="kv"><span class="k">Настройки действуют с</span><span class="v">${engine?.active?.valid_from ? dateRu(engine.active.valid_from) : 'По умолчанию'}</span></div>
          <div class="kv"><span class="k">Замечаний конфигурации</span><span class="v">${(health?.checks || []).length}</span></div>
          <div class="kv"><span class="k">Последний закрытый период</span><span class="v">${closedPeriodText(health?.periods?.last_closed, { recalcNote: false })}</span></div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-content:flex-start">
          <button class="btn btn-sm" id="sy-selfcheck" @click=${checkService}>Проверить состояние системы</button>
          ${can('access.manage') ? html`<button class="btn btn-sm" data-nav="access" @click=${() => navigate('access')}>Права доступа ↗</button>` : nothing}
          <button class="btn btn-sm btn-ghost" data-go="expert" @click=${() => settingsGo('expert')}>Режим эксперта (JSON)</button>
        </div>
      </div>`)}
    ${settingsDraftBarView()}`, mount(host));
}

async function checkService(event) {
  const source = event.currentTarget;
  const current = () => source.isConnected && !source.closest('[inert], .view:not(.active)');
  if (source.hasAttribute('aria-busy')) return;
  source.setAttribute('aria-busy', 'true');
  try {
    const status = await api('/api/selfcheck', { silent: true });
    if (!current()) return;
    openModal({
      title: 'Состояние системы',
      body: status.ok ? 'Система работает.' : 'Часть функций может быть недоступна. Обратитесь к администратору.',
      footer: html`<button class="btn btn-primary" @click=${closeModal}>Закрыть</button>`,
    });
  } catch {
    if (current()) toast('Не удалось проверить состояние системы. Попробуйте ещё раз.', 'err');
  } finally {
    source.removeAttribute('aria-busy');
  }
}

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «РЕЖИМ ЭКСПЕРТА» — тот же черновик, но вторым видом: сырой JSON
   версии справочников и полный список модификаторов (renderEngineSettings).
   ══════════════════════════════════════════════════════════════════════ */
async function settingsScreenExpert(host) {
  render(html`
    ${settingsHeadView('Режим эксперта (JSON)',
      'Откройте справочники расчёта и правила периода.',
      html`<button class="btn btn-sm" data-go="overview" @click=${() => settingsGo('overview')}>← Обзор</button>`)}
    <div class="panel" id="st-expert"></div>`, mount(host));
  await renderEngineSettings($('#st-expert', host));
}
