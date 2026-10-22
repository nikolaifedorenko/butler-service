/* Раздел «Настройки»: экран «Смены и отсутствия» (вынесено из settings.js, шаг 6.5 аудита).
   Оболочка, черновик версии справочников и общие помощники — в settings.js. */
'use strict';

registerModule({ screens: { shifts: { render: settingsScreenShifts, icon: 'shift' } } });

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «СМЕНЫ И ОТСУТСТВИЯ» — словарь Графика (shift_types + ревизии).
   Это инструмент ввода, НЕ расчёт: норм расчёта здесь нет (план, ред. 3, §3.4б).
   ══════════════════════════════════════════════════════════════════════ */
async function settingsScreenShifts(host) {
  await settingsEngine();
  const p = settingsPayload();
  const edit = can('settings.edit');
  let shiftList = state.shiftTypes || [];
  if (settingsUI.showArchived) {
    try { shiftList = await api('/api/shift-types?include_archived=true', { silent: true }); }
    catch { shiftList = state.shiftTypes || []; }
  }
  const tab = settingsUI.shiftTab || 'work';
  const shown = shiftList.filter(s => (tab === 'archived' ? !!s.archived
    : !s.archived && (tab === 'work' ? s.kind === 'work' : s.kind !== 'work')));
  const codes = p?.day_code_policy || {};

  host.innerHTML = `
    ${settingsHead('Смены и отсутствия',
      'Словарь ячеек Графика: рабочие смены любого времени и виды отсутствий. На расчёт влияет косвенно — через код Табеля и флаги. Нормы расчёта — на экране «Коды Табеля».',
      `<button class="btn btn-sm btn-ghost" data-go="codes">Коды Табеля ↗</button>
       ${edit ? '<button class="btn btn-sm btn-primary" id="sh-add">+ Новая смена / отсутствие</button>' : ''}`)}
    <div class="tabs">
      <button data-stab="work" class="${tab === 'work' ? 'active' : ''}">Смены · ${shiftList.filter(s => !s.archived && s.kind === 'work').length}</button>
      <button data-stab="absence" class="${tab === 'absence' ? 'active' : ''}">Отсутствия · ${shiftList.filter(s => !s.archived && s.kind !== 'work').length}</button>
      <button data-stab="archived" class="${tab === 'archived' ? 'active' : ''}">Архив · ${shiftList.filter(s => s.archived).length}</button>
    </div>
    ${settingsPanel('', `
      <div class="table-wrap" style="max-height:none"><table class="data responsive"><thead><tr>
        <th>Код</th><th>Название</th><th>Время</th><th class="num">Часов</th><th>Признаки</th><th></th>
      </tr></thead><tbody>
      ${shown.map(s => `<tr${s.archived ? ' style="opacity:.62"' : ''}>
        <td data-label="Код"><span class="shift-pill" style="background:${cssColor(s.color, '#6b7280')};color:${textOn(cssColor(s.color, '#6b7280'))}">${esc(s.code)}</span></td>
        <td data-label="Название">${esc(s.name)}</td>
        <td class="num" data-label="Время">${s.kind === 'work'
          ? `${esc(s.start_time)}–${esc(s.end_time)}${s.overnight ? ' <span class="badge info">через полночь</span>' : ''}` : '—'}</td>
        <td class="num" data-label="Часов">${s.kind === 'work' ? esc(hours(s.planned_hours)) : '—'}</td>
        <td data-label="Признаки">${s.kind === 'work' ? '<span class="badge ok">смена</span>' : '<span class="badge muted">отсутствие</span>'}
          ${s.kind !== 'work' && s.doc_type ? '<span class="badge info" title="Из ячейки Графика печатается заявление">заявление</span>' : ''}
          ${s.kind !== 'work' && (s.punch_in_allowed === false || s.punch_out_allowed === false)
            ? '<span class="badge warn" title="Отмечаться во время этого отсутствия нельзя">без отметок</span>' : ''}
          ${s.archived ? `<span class="badge muted" title="В архиве${s.archived_at ? ' с ' + dateRu(s.archived_at) : ''}">архив</span>` : ''}
          ${s.revisions ? `<span class="badge" title="Есть история значений: прошлые даты считаются по прежним часам">${s.revisions} изм.</span>` : ''}</td>
        <td class="num" style="white-space:nowrap">
          ${edit ? `<button class="btn btn-sm btn-ghost" data-shift="${s.id}">Изменить</button>
          ${s.archived ? `<button class="btn btn-sm" data-restore="${s.id}">Вернуть</button>`
            : `<button class="btn btn-sm btn-ghost" data-archive="${s.id}" title="Убрать из словаря: прошлые графики продолжат считаться по этой смене">В архив</button>`}` : ''}
        </td></tr>`).join('') || '<tr><td colspan="7" class="empty">Пусто</td></tr>'}
      </tbody></table></div>
      <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">
        ${edit ? '<button class="btn btn-sm" id="sh-new">+ Новая смена / часы (например 08:00–17:00)</button>' : ''}
        <button class="btn btn-sm btn-ghost" id="sh-arch">${settingsUI.showArchived ? 'Скрыть архив' : 'Показать архив'}</button>
      </div>
      <p class="hint">«Удаление» смены = архив: она исчезает из новых назначений, но прошлые графики и табели
        продолжают считаться по ней. Изменение времени создаёт новую ревизию словаря: отработанные дни остаются
        посчитанными по ПРЕЖНИМ часам, дата вступления указывается в редакторе смены.</p>`)}
    ${settingsPanel('Как связаны Табель и График', `
      <p class="hint" style="margin:-4px 0 0">Справочники независимы (18.10.2026): Табель заполняется
        из циклов значением рабочего дня сотрудника (окно берётся из CFG-WINDOWS), График
        по умолчанию копирует смены Табеля с цветом кода. Словарь смен отвечает только
        за добавляемые вручную смены и системное отсутствие «Отпросился (выходной за часы)».
        Ручная смена Графика не меняет часы Табеля: Табель — первичный документ.</p>`)}`;

  settingsBindHealth(host);
  $$('[data-stab]', host).forEach(b => b.onclick = () => { settingsUI.shiftTab = b.dataset.stab; settingsRenderScreen(); });
  settingsOn('#sh-arch', host, async () => {
    settingsUI.showArchived = !settingsUI.showArchived;
    if (settingsUI.showArchived) { await loadDirectory(); }
    settingsRenderScreen();
  });
  settingsOn('#sh-add', host, () => shiftModal(null));
  settingsOn('#sh-new', host, () => shiftModal(null));
  $$('[data-shift]', host).forEach(b => b.onclick = () =>
    shiftModal(shiftList.find(x => x.id === +b.dataset.shift)));
  /* «Исправить» у битой ссылки — тот же редактор смены: «код в табеле» в нём выбирается
     из справочника, а прежнее значение предложено очистить (T1). */
  $$('[data-fix-tzh]', host).forEach(b => b.onclick = () =>
    shiftModal(shiftList.find(x => x.id === +b.dataset.fixTzh)));
  $$('[data-archive]', host).forEach(b => b.onclick = () => {
    const sh = shiftList.find(x => x.id === +b.dataset.archive);
    confirmDialog('Архивировать смену?',
      `«${sh?.name || ''}» исчезнет из словаря для НОВЫХ назначений, но все прошлые графики и табели продолжат считаться по этой смене — история не сломается. Смену можно вернуть из архива.`,
      async () => {
        try {
          await api(`/api/shift-types/${sh.id}`, { method: 'DELETE' });
          toast('Смена перенесена в архив', 'ok');
          await loadDirectory(); await settingsRefresh();
        } catch (e) { toast(e.message, 'err'); }
      }, 'В архив');
  });
  $$('[data-restore]', host).forEach(b => b.onclick = async () => {
    try {
      await api(`/api/shift-types/${b.dataset.restore}/restore`, { method: 'POST' });
      toast('Смена возвращена в словарь', 'ok');
      await loadDirectory(); await settingsRefresh();
    } catch (e) { toast(e.message, 'err'); }
  });
}
