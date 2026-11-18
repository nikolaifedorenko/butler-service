/* Раздел «Настройки»: экран «Обзор» (вынесено из settings.js, шаг 6.5 аудита).
   Оболочка, черновик версии справочников и общие помощники — в settings.js.
   Модуль на lit-html (ADR-0013, раздел 7). */
'use strict';

import { can, registerModule } from '../app.js';
import { api, closeModal, dateRu, openModal, toast } from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { fmtGdValue } from './dicts.js';
import { settingsCodeModal, settingsWindowModal } from './settings_codes.js';
import { settingsResolverModal, settingsWizard } from './settings_pay.js';
import {
  SETTINGS_MODS, settingsDiffModal, settingsDraftBarView, settingsEngine, settingsGo, settingsHeadView,
  settingsHealth, settingsHealthBannerView, settingsPanelView, settingsUI,
} from './settings.js';

registerModule({ screens: { overview: { render: settingsScreenOverview, icon: 'home' } } });

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «ОБЗОР» — паспорт объекта: что действует, здорово ли, что вступит в силу
   ══════════════════════════════════════════════════════════════════════ */
async function settingsScreenOverview(host) {
  const [health, engine] = await Promise.all([settingsHealth(), settingsEngine()]);
  const v = health?.version || {};
  const s = health?.stats || {};
  const p = engine?.active?.payload || {};
  const upcoming = health?.upcoming || [];
  const recent = health?.recent || [];
  const go = id => () => settingsGo(id);
  const stamp = ts => (ts || '').replace('T', ' ').slice(0, 16);

  render(html`
    ${settingsHeadView('Обзор', 'Что действует сейчас, здорова ли конфигурация и что вступит в силу — одним экраном.',
      html`<button class="btn btn-sm" id="ov-versions" @click=${() => settingsVersionsModal()}>История версий</button>
       <button class="btn btn-sm" id="ov-compare" @click=${() => settingsCompareWithPrevious()}>Сравнить с предыдущей</button>
       <button class="btn btn-sm btn-primary" id="ov-expert" @click=${go('expert')}>Режим эксперта</button>`)}
    ${settingsPanelView('', html`
      <div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap">
        <div style="flex:1;min-width:260px">
          <div class="panel-title" style="margin-bottom:6px">Действующая версия справочников</div>
          <div style="font-family:var(--font-display);font-size:21px">
            ${v.id ? `#${v.id} · действует с ${dateRu(v.valid_from)}` : 'справочники по умолчанию (версий нет)'}</div>
          <div class="hint" style="margin-top:4px">${v.created_by || '—'}${v.created_at
            ? ` · ${stamp(v.created_at)}` : ''}${v.note ? ` · «${v.note}»` : ''}</div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn btn-sm" id="ov-calc" @click=${go('calc')}>Каркас расчёта</button>
          <button class="btn btn-sm" id="ov-system" @click=${go('system')}>Версии и откат</button>
        </div>
      </div>`)}
    ${settingsHealthBannerView(health)}
    <div class="stat-grid">
      <div class="stat"><div class="k">Шаг расчёта</div><div class="v">${s.step_minutes ?? '—'} <small>мин</small></div></div>
      <div class="stat info"><div class="k">Период</div><div class="v" style="font-size:19px">${s.period_granularity === 'half_month' ? 'полмесяца' : 'месяц'}</div></div>
      <div class="stat"><div class="k">Лимит опоздания</div><div class="v">${s.late_limit_minutes ?? '—'} <small>мин</small></div></div>
      <div class="stat"><div class="k">Кодов Табеля</div><div class="v">${s.codes ?? 0}</div></div>
      <div class="stat"><div class="k">Окон (значений)</div><div class="v">${s.windows ?? 0}</div></div>
      <div class=${`stat ${s.rules_active ? 'warn' : ''}`}><div class="k">Переопределений в месяце</div><div class="v">${s.rules_active ?? 0}</div></div>
    </div>
    <div class="grid-2">
      ${settingsPanelView('Вступит в силу', upcoming.length
        ? upcoming.map(u => html`<div class="kv"><span class="k">${dateRu(u.date)} · ${u.kind === 'version' ? 'версия' : 'правило'}</span>
            <span class="v" style="text-align:left;font-weight:600">${u.text}
              <button class="btn btn-sm btn-ghost" data-go=${u.screen} @click=${go(u.screen)}>открыть</button></span></div>`)
        : html`<p class="hint" style="margin:0">Правил и версий на будущее нет. Здесь видно всё, что вступит после сегодняшнего дня — «я не помню, что уже задал» больше не проблема.</p>`)}
      ${settingsPanelView('Изменения за 30 дней', recent.length
        ? html`${recent.map(r => html`<div class="kv"><span class="k">${stamp(r.ts)} · ${r.actor || '—'}</span>
            <span class="v" style="text-align:left;font-weight:600">${r.action} · ${r.target}</span></div>`)}
          <div style="margin-top:10px"><button class="btn btn-sm btn-ghost" data-go="audit" @click=${go('audit')}>Весь журнал аудита →</button></div>`
        : html`<p class="hint" style="margin:0">За последние 30 дней настройки не менялись.</p>`)}
    </div>
    ${settingsPanelView('Что включено сейчас', html`
      <div class="grid-2">
        <div>${SETTINGS_MODS.filter(m => m.name !== 'counts_in_ut').map(m => html`
          <div class="kv"><span class="k">${m.title}</span>
            <span class="v">${fmtGdValue(m.name, (s.global_defaults || {})[m.name])}
              <span class="badge muted">глобально</span></span></div>`)}
          <div class="kv"><span class="k">Учитываются ли часы в УТ</span>
            <span class="v">по коду дня <button class="btn btn-sm btn-ghost" data-go="codes" @click=${go('codes')}>коды →</button></span></div>
        </div>
        <div>
          <div class="kv"><span class="k">Часовой пояс</span><span class="v">${s.tz || p.tz || '—'}</span></div>
          <div class="kv"><span class="k">Каскад гашения</span><span class="v" style="font-weight:600">банк → ${(p.cascade_order || []).join(' → ')}</span></div>
          <div class="kv"><span class="k">Порядок размещения</span><span class="v" style="font-weight:600">${(p.placement_order || []).join(' → ')}</span></div>
          <div class="kv"><span class="k">Группы</span><span class="v" style="font-weight:600">${(p.groups || []).join(', ')}</span></div>
        </div>
      </div>`)}
    ${settingsPanelView('Быстрые действия', html`
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        ${can('settings.edit') ? html`<button class="btn btn-sm" id="ov-wizard" @click=${() => settingsWizard()}>+ Переопределение правила</button>` : nothing}
        <button class="btn btn-sm" id="ov-resolve" @click=${() => settingsResolverModal()}>Проверить значение для дня</button>
        ${can('settings.edit') ? html`<button class="btn btn-sm" id="ov-code" @click=${() => settingsCodeModal(null)}>+ Код Табеля</button>` : nothing}
        ${can('settings.edit') ? html`<button class="btn btn-sm" id="ov-window" @click=${() => settingsWindowModal(null)}>+ Значение и окно</button>` : nothing}
        <button class="btn btn-sm" data-go="calendar" @click=${go('calendar')}>Календарь правил</button>
        <button class="btn btn-sm btn-ghost" data-go="shifts" @click=${go('shifts')}>Словарь смен</button>
      </div>`)}
    ${settingsDraftBarView()}`, mount(host));
}

export async function settingsCompareWithPrevious() {
  const engine = await settingsEngine();
  const versions = engine?.versions || [];
  const current = versions.find(v => v.id === engine?.active?.id);
  const idx = versions.findIndex(v => v.id === current?.id);
  const prev = versions[idx + 1];
  if (!prev) return toast('Предыдущей версии нет — сравнивать не с чем', 'warn');
  try {
    const old = await api(`/api/engine-settings?on=${prev.valid_from}`, { silent: true });
    settingsDiffModal(old.active.payload, engine.active.payload,
      `Версия #${prev.id} → #${engine.active.id}`);
  } catch (e) { toast(e.message, 'err'); }
}

/* окно «payload версии»: общее для «Обзора» и «Системы» */
export async function settingsPayloadModal(v) {
  try {
    const d = await api(`/api/engine-settings?on=${v.valid_from}`, { silent: true });
    openModal({ title: `Версия #${v.id} · payload`, wide: true,
      subtitle: `действует с ${dateRu(v.valid_from)}${v.note ? ` · ${v.note}` : ''}`,
      body: html`<pre style="max-height:60vh;overflow:auto;background:#f8f5f1;border:1px solid var(--line);
        border-radius:6px;padding:12px;font-size:12px">${JSON.stringify(d.active.payload, null, 2)}</pre>`,
      footer: html`<button class="btn btn-primary" data-ok>Закрыть</button>`,
      onMount(mm) { mm.querySelector('[data-ok]').onclick = closeModal; } });
  } catch (e) { toast(e.message, 'err'); }
}

export function settingsVersionsModal() {
  const versions = settingsUI.engine?.versions || [];
  const activeId = settingsUI.engine?.active?.id;
  openModal({
    title: 'История версий справочников', wide: true,
    subtitle: 'Версия выбирается по дате начала периода; закрытые периоды читаются из хранилища',
    body: versions.length ? html`<div class="table-wrap"><table class="data"><thead><tr>
        <th>№</th><th>Действует с</th><th>Комментарий</th><th>Кто</th><th>Создана</th><th></th>
      </tr></thead><tbody>${versions.map(v => html`<tr style=${v.id === activeId ? 'background:#f7f1ea' : nothing}>
        <td><b>#${v.id}</b>${v.id === activeId ? html` <span class="badge ok">действует</span>` : nothing}</td>
        <td>${dateRu(v.valid_from)}</td><td>${v.note || '—'}</td>
        <td>${v.created_by || '—'}</td><td>${(v.created_at || '').replace('T', ' ').slice(0, 16)}</td>
        <td class="num"><button class="btn btn-sm btn-ghost" data-ver=${v.id} @click=${() => settingsPayloadModal(v)}>показать payload</button></td>
      </tr>`)}</tbody></table></div>`
      : html`<p class="hint">Версий нет: расчёт идёт по справочникам по умолчанию.</p>`,
    footer: html`<button class="btn btn-primary" data-ok>Закрыть</button>`,
    onMount(m) { m.querySelector('[data-ok]').onclick = closeModal; },
  });
}
