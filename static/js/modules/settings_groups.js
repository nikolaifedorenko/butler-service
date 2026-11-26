/* Раздел «Настройки»: экран «Группы и графики».
   Оболочка, черновик версии справочников и общие помощники — в settings.js.
   Модуль на lit-html (ADR-0013, раздел 7). */
'use strict';

import { can, navigate, registerModule } from '../app.js';
import { $, api, confirmDialog, state, toast } from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import {
  settingsDraft, settingsDraftBarView, settingsEngine, settingsHeadView, settingsHealth, settingsHealthBannerView,
  settingsPanelView, settingsRefresh, settingsRenderScreen, settingsUI,
} from './settings.js';

registerModule({ screens: { groups: { render: settingsScreenGroups, icon: 'people' } } });

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «ГРУППЫ И ГРАФИКИ» — CFG-GROUPS + базовый цикл объекта
   ══════════════════════════════════════════════════════════════════════ */
async function settingsScreenGroups(host) {
  const [, health] = await Promise.all([settingsEngine(), settingsHealth().catch(() => null)]);
  const data = settingsUI.data || {};
  const d = settingsDraft();
  const edit = can('settings.edit');
  const emps = state.employees || [];
  const perGroup = {};
  emps.forEach(e => { const g = e.group || 'Другие смены'; perGroup[g] = (perGroup[g] || 0) + 1; });
  const base = data.base || {};
  const groupChecks = (health?.checks || []).filter(c => c.screen === 'groups');
  const custom = String(base.cycle || '').startsWith('custom');
  const syncCycle = () => $('#b-cycle-wrap', host)?.classList.toggle('hidden', $('#b-cycle', host).value !== 'custom');

  const dropGroup = g => confirmDialog('Исключить группу из реестра?',
    `Группа «${g}» перестанет существовать для расчёта. Перед удалением переведите сотрудников в другую группу.`,
    () => {
      d.groups = (d.groups || []).filter(x => x !== g);
      settingsRenderScreen();
    }, 'Исключить из черновика');
  const addGroup = () => {
    const name = $('#g-new', host).value.trim();
    if (!name) return toast('Введите название группы', 'warn');
    if ((d.groups || []).includes(name)) return toast('Такая группа уже есть', 'warn');
    d.groups = [...(d.groups || []), name];
    settingsRenderScreen();
  };
  const saveBase = async () => {
    const cycle = $('#b-cycle', host).value === 'custom' ? 'custom:' + $('#b-cycle-custom', host).value.trim() : $('#b-cycle', host).value;
    /* значения рабочего дня и выходные блоков сохраняются как есть: они правятся
       в карточках сотрудников, экран базового цикла их не редактирует */
    const keepGroups = {};
    for (const [name, gc] of Object.entries(base.groups || {})) {
      const keep = {};
      if (gc && gc.value) keep.value = gc.value;
      if (gc && gc.off_weekdays) keep.off_weekdays = gc.off_weekdays;
      keepGroups[name] = keep;
    }
    const body = { cycle, anchor: $('#b-anchor', host).value, groups: keepGroups };
    try {
      await api('/api/settings/base', { method: 'PUT', body });
      toast('Базовый цикл сохранён и действует на все месяцы', 'ok');
      await settingsRefresh();
    } catch (e) { toast(e.message, 'err'); }
  };
  const strays = Object.keys(perGroup).filter(g => !(d?.groups || []).includes(g));

  render(html`
    ${settingsHeadView('Группы и графики',
      'Настройте группы сотрудников и базовый цикл смен объекта.')}
    ${groupChecks.length ? settingsHealthBannerView({ ...health, checks: groupChecks }) : nothing}
    ${settingsPanelView('Группы сотрудников', html`
      <div class="table-wrap" tabindex="0"><table class="data"><thead><tr>
        <th>Группа</th><th class="num">Сотрудников</th><th>Шаблон графика</th><th>Правил оплаты</th><th></th>
      </tr></thead><tbody>${(d?.groups || []).map(g => html`<tr>
        <td><b>${g}</b></td>
        <td class="num">${perGroup[g] ?? 0}</td>
        <td>${g === 'Смена 1' || g === 'Смена 2' ? `базовый цикл ${base.cycle || '2/2'}${g === 'Смена 2' && base.groups?.['Смена 2']?.invert !== false ? ' (противофаза)' : ''}`
          : g === 'Пятидневка' ? '5/2, выходные у каждого свои' : 'индивидуальный цикл или вручную'}</td>
        <td><span class="badge muted">см. «Календарь правил»</span></td>
        <td class="num">${edit ? html`<button class="btn btn-sm btn-ghost" data-gdel=${g} title="Исключить из реестра" @click=${() => dropGroup(g)}>✕</button>` : nothing}</td>
      </tr>`)}</tbody></table></div>
      ${edit ? html`<div class="v4-filters" style="margin-top:10px">
        <label class="field"><span>Новая группа</span><input type="text" id="g-new" placeholder="например: Смена 3"></label>
        <button class="btn btn-sm" id="g-add" @click=${addGroup}>Добавить в черновик</button></div>` : nothing}
      <p class="hint">Изменения групп вступают в силу после публикации версии. Сотрудники, чьей группы нет в реестре:
        ${strays.length ? strays.map(g => html`<span class="badge danger">${g} · ${perGroup[g]}</span> `) : 'нет — реестр полный'}</p>`)}
    ${settingsPanelView('Базовый цикл объекта · «Смена 1» и «Смена 2»', html`
      <p class="hint" style="margin:-4px 0 12px">Задаётся один раз и действует на все месяцы вперёд и назад.
        Ручные ячейки Графика — исключения (отпуск, больничный, подмена) и перекрывают базовый цикл.
        Кнопка «Сохранить базовый цикл» применяет изменения этого блока сразу.</p>
      <div class="grid-2">
        <label class="field"><span>Цикл смен 1/2</span><select id="b-cycle" ?disabled=${!edit} @change=${syncCycle}>
          ${['2/2', '3/3', '4/2', '4/3', '1/3'].map(c => html`<option ?selected=${base.cycle === c}>${c}</option>`)}
          <option value="custom" ?selected=${custom}>произвольный…</option>
        </select></label>
        <label class="field"><span>Опорная дата (день, когда Смена 1 рабочая)</span>
          <input type="date" id="b-anchor" .value=${base.anchor || '2024-01-01'} ?disabled=${!edit}></label>
        <label class=${`field${custom ? '' : ' hidden'}`} id="b-cycle-wrap"><span>Произвольный цикл (Р/В)</span>
          <input type="text" id="b-cycle-custom" placeholder="РРВВВВРР"
            .value=${custom ? String(base.cycle).slice(7) : ''} ?disabled=${!edit}></label>
      </div>
      <p class="hint" style="margin:-4px 0 10px">Смена 2 работает в противофазе со Сменой 1 — системное
        правило. Значение рабочего дня (код и окно) задаётся в карточке
        сотрудника при приёме и переводе в блок.</p>
      ${edit ? html`<button class="btn btn-primary btn-sm" id="b-save" style="margin-top:10px" @click=${saveBase}>Сохранить базовый цикл</button>` : nothing}`)}
    ${settingsPanelView('Пятидневка и «Другие смены»', html`
      <p class="hint" style="margin:0">Здесь не настраиваются. У «Пятидневки» выходные задаются для
        КАЖДОГО сотрудника индивидуально (Сотрудники → карточка → «Перевод в блок»: например у начальника
        вс/пн, у бэк-специалиста сб/вс). «Другие смены» — контейнер индивидуальных графиков: 3/3, 1/3,
        сутки через трое, произвольный цикл «custom:РРВВ» или ручное заполнение ячеек.</p>
      <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
        <button class="btn btn-sm btn-ghost" data-nav="employees" @click=${() => navigate('employees')}>Карточки сотрудников ↗</button>
        <button class="btn btn-sm btn-ghost" data-nav="schedule" @click=${() => navigate('schedule')}>График ↗</button>
      </div>`)}
    ${settingsDraftBarView()}`, mount(host));
  syncCycle();
}
