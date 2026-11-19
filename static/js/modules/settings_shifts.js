/* Раздел «Настройки»: экран «Смены и отсутствия».
   Оболочка, черновик версии справочников и общие помощники — в settings.js.
   Модуль на lit-html (ADR-0013, раздел 7). */
'use strict';

import { can, loadDirectory, registerModule } from '../app.js';
import { api, confirmDialog, cssColor, dateRu, hours, state, textOn, toast } from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { shiftModal } from './dicts.js';
import {
  settingsEngine, settingsGo, settingsHeadView, settingsPanelView, settingsRefresh, settingsRenderScreen, settingsUI,
} from './settings.js';

registerModule({ screens: { shifts: { render: settingsScreenShifts, icon: 'shift' } } });

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «СМЕНЫ И ОТСУТСТВИЯ» — словарь Графика (shift_types + ревизии).
   Это инструмент ввода, НЕ расчёт: норм расчёта здесь нет (план, ред. 3, §3.4б).
   ══════════════════════════════════════════════════════════════════════ */
async function settingsScreenShifts(host) {
  await settingsEngine();
  const edit = can('settings.edit');
  let shiftList = state.shiftTypes || [];
  if (settingsUI.showArchived) {
    try { shiftList = await api('/api/shift-types?include_archived=true', { silent: true }); }
    catch { shiftList = state.shiftTypes || []; }
  }
  const tab = settingsUI.shiftTab || 'work';
  const shown = shiftList.filter(s => (tab === 'archived' ? !!s.archived
    : !s.archived && (tab === 'work' ? s.kind === 'work' : s.kind !== 'work')));

  const archive = sh => confirmDialog('Архивировать смену?',
    `«${sh?.name || ''}» исчезнет из словаря для НОВЫХ назначений, но все прошлые графики и табели продолжат считаться по этой смене — история не сломается. Смену можно вернуть из архива.`,
    async () => {
      try {
        await api(`/api/shift-types/${sh.id}`, { method: 'DELETE' });
        toast('Смена перенесена в архив', 'ok');
        await loadDirectory(); await settingsRefresh();
      } catch (e) { toast(e.message, 'err'); }
    }, 'В архив');
  const restore = async s => {
    try {
      await api(`/api/shift-types/${s.id}/restore`, { method: 'POST' });
      toast('Смена возвращена в словарь', 'ok');
      await loadDirectory(); await settingsRefresh();
    } catch (e) { toast(e.message, 'err'); }
  };
  const toggleArchive = async () => {
    settingsUI.showArchived = !settingsUI.showArchived;
    if (settingsUI.showArchived) { await loadDirectory(); }
    settingsRenderScreen();
  };
  const setTab = t => () => { settingsUI.shiftTab = t; settingsRenderScreen(); };
  const row = s => {
    const color = cssColor(s.color, '#6b7280');
    return html`<tr style=${s.archived ? 'opacity:.62' : nothing}>
        <td data-label="Код"><span class="shift-pill" style=${`background:${color};color:${textOn(color)}`}>${s.code}</span></td>
        <td data-label="Название">${s.name}</td>
        <td class="num" data-label="Время">${s.kind === 'work'
          ? html`${s.start_time}–${s.end_time}${s.overnight ? html` <span class="badge info">через полночь</span>` : nothing}` : '—'}</td>
        <td class="num" data-label="Часов">${s.kind === 'work' ? hours(s.planned_hours) : '—'}</td>
        <td data-label="Признаки">${s.kind === 'work' ? html`<span class="badge ok">смена</span>` : html`<span class="badge muted">отсутствие</span>`}
          ${s.kind !== 'work' && s.doc_type ? html`<span class="badge info" title="Из ячейки Графика печатается заявление">заявление</span>` : nothing}
          ${s.kind !== 'work' && (s.punch_in_allowed === false || s.punch_out_allowed === false)
            ? html`<span class="badge warn" title="Отмечаться во время этого отсутствия нельзя">без отметок</span>` : nothing}
          ${s.archived ? html`<span class="badge muted" title=${`В архиве${s.archived_at ? ' с ' + dateRu(s.archived_at) : ''}`}>архив</span>` : nothing}
          ${s.revisions ? html`<span class="badge" title="Есть история значений: прошлые даты считаются по прежним часам">${s.revisions} изм.</span>` : nothing}</td>
        <td class="num" style="white-space:nowrap">
          ${edit ? html`<button class="btn btn-sm btn-ghost" data-shift=${s.id} @click=${() => shiftModal(s)}>Изменить</button>
          ${s.archived ? html`<button class="btn btn-sm" data-restore=${s.id} @click=${() => restore(s)}>Вернуть</button>`
            : html`<button class="btn btn-sm btn-ghost" data-archive=${s.id} title="Убрать из словаря: прошлые графики продолжат считаться по этой смене" @click=${() => archive(s)}>В архив</button>`}` : nothing}
        </td></tr>`;
  };
  render(html`
    ${settingsHeadView('Смены и отсутствия',
      'Словарь ячеек Графика: рабочие смены любого времени и виды отсутствий. На расчёт влияет косвенно — через код Табеля и флаги. Нормы расчёта — на экране «Коды Табеля».',
      html`<button class="btn btn-sm btn-ghost" data-go="codes" @click=${() => settingsGo('codes')}>Коды Табеля ↗</button>
       ${edit ? html`<button class="btn btn-sm btn-primary" id="sh-add" @click=${() => shiftModal(null)}>+ Новая смена / отсутствие</button>` : nothing}`)}
    <div class="tabs">
      <button data-stab="work" class=${tab === 'work' ? 'active' : ''} @click=${setTab('work')}>Смены · ${shiftList.filter(s => !s.archived && s.kind === 'work').length}</button>
      <button data-stab="absence" class=${tab === 'absence' ? 'active' : ''} @click=${setTab('absence')}>Отсутствия · ${shiftList.filter(s => !s.archived && s.kind !== 'work').length}</button>
      <button data-stab="archived" class=${tab === 'archived' ? 'active' : ''} @click=${setTab('archived')}>Архив · ${shiftList.filter(s => s.archived).length}</button>
    </div>
    ${settingsPanelView('', html`
      <div class="table-wrap" tabindex="0" style="max-height:none"><table class="data responsive"><thead><tr>
        <th>Код</th><th>Название</th><th>Время</th><th class="num">Часов</th><th>Признаки</th><th></th>
      </tr></thead><tbody>
      ${shown.length ? shown.map(row) : html`<tr><td colspan="7" class="empty">Пусто</td></tr>`}
      </tbody></table></div>
      <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">
        ${edit ? html`<button class="btn btn-sm" id="sh-new" @click=${() => shiftModal(null)}>+ Новая смена / часы (например 08:00–17:00)</button>` : nothing}
        <button class="btn btn-sm btn-ghost" id="sh-arch" @click=${toggleArchive}>${settingsUI.showArchived ? 'Скрыть архив' : 'Показать архив'}</button>
      </div>
      <p class="hint">«Удаление» смены = архив: она исчезает из новых назначений, но прошлые графики и табели
        продолжают считаться по ней. Изменение времени создаёт новую ревизию словаря: отработанные дни остаются
        посчитанными по ПРЕЖНИМ часам, дата вступления указывается в редакторе смены.</p>`)}
    ${settingsPanelView('Как связаны Табель и График', html`
      <p class="hint" style="margin:-4px 0 0">Справочники независимы: Табель заполняется
        из циклов значением рабочего дня сотрудника (окно берётся из CFG-WINDOWS), График
        по умолчанию копирует смены Табеля с цветом кода. Словарь смен отвечает только
        за добавляемые вручную смены и системное отсутствие «Отпросился (выходной за часы)».
        Ручная смена Графика не меняет часы Табеля: Табель — первичный документ.</p>`)}`, mount(host));
}
