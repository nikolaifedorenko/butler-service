/* Раздел «Настройки»: экран «Группы и графики» (вынесено из settings.js, шаг 6.5 аудита).
   Оболочка, черновик версии справочников и общие помощники — в settings.js. */
'use strict';

registerModule({ screens: { groups: { render: settingsScreenGroups, icon: 'people' } } });

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «ГРУППЫ И ГРАФИКИ» — CFG-GROUPS + базовый цикл объекта
   ══════════════════════════════════════════════════════════════════════ */
async function settingsScreenGroups(host) {
  const [engine, health] = await Promise.all([settingsEngine(), settingsHealth().catch(() => null)]);
  const data = settingsUI.data || {};
  const d = settingsDraft();
  const edit = can('settings.edit');
  const emps = state.employees || [];
  const perGroup = {};
  emps.forEach(e => { const g = e.group || 'Другие смены'; perGroup[g] = (perGroup[g] || 0) + 1; });
  const base = data.base || {};
  const groupChecks = (health?.checks || []).filter(c => c.screen === 'groups');

  host.innerHTML = `
    ${settingsHead('Группы и графики',
      'Реестр групп CFG-GROUPS, базовый цикл объекта и то, как группы связаны с блоками смен. Группа сотрудника обязана быть в реестре (CHK-GROUP-EXISTS).',
      `<span class="chip">версия #${engine?.active?.id ?? '—'}</span>`)}
    ${groupChecks.length ? settingsHealthBanner({ ...health, checks: groupChecks }) : ''}
    ${settingsPanel('Группы · единый источник (CFG-GROUPS)', `
      <div class="table-wrap"><table class="data"><thead><tr>
        <th>Группа</th><th class="num">Сотрудников</th><th>Шаблон графика</th><th>Правил оплаты</th><th></th>
      </tr></thead><tbody>${(d?.groups || []).map(g => `<tr>
        <td><b>${esc(g)}</b></td>
        <td class="num">${perGroup[g] ?? 0}</td>
        <td>${esc(g === 'Смена 1' || g === 'Смена 2' ? `базовый цикл ${base.cycle || '2/2'}${g === 'Смена 2' && base.groups?.['Смена 2']?.invert !== false ? ' (противофаза)' : ''}`
          : g === 'Пятидневка' ? '5/2, выходные у каждого свои' : 'индивидуальный цикл или вручную')}</td>
        <td><span class="badge muted">см. «Календарь правил»</span></td>
        <td class="num">${edit ? `<button class="btn btn-sm btn-ghost" data-gdel="${esc(g)}" title="Исключить из реестра">✕</button>` : ''}</td>
      </tr>`).join('')}</tbody></table></div>
      ${edit ? `<div class="v4-filters" style="margin-top:10px">
        <label class="field"><span>Новая группа</span><input type="text" id="g-new" placeholder="например: Смена 3"></label>
        <button class="btn btn-sm" id="g-add">Добавить в черновик</button></div>` : ''}
      <p class="hint">Сотрудники, чьей группы нет в реестре:
        ${Object.keys(perGroup).filter(g => !(d?.groups || []).includes(g)).map(g =>
          `<span class="badge danger">${esc(g)} · ${perGroup[g]}</span>`).join(' ') || 'нет — реестр полный'}</p>`)}
    ${settingsPanel('Базовый цикл объекта · «Смена 1» и «Смена 2»', `
      <p class="hint" style="margin:-4px 0 12px">Задаётся один раз и действует на все месяцы вперёд и назад.
        Ручные ячейки Графика — исключения (отпуск, больничный, подмена) и перекрывают базовый цикл.
        Это данные приложения (таблица настроек), а не версия справочников — сохраняются сразу.</p>
      <div class="grid-2">
        <label class="field"><span>Цикл смен 1/2</span><select id="b-cycle" ${edit ? '' : 'disabled'}>
          ${['2/2', '3/3', '4/2', '4/3', '1/3'].map(c => `<option ${base.cycle === c ? 'selected' : ''}>${c}</option>`).join('')}
          <option value="custom" ${String(base.cycle || '').startsWith('custom') ? 'selected' : ''}>произвольный…</option>
        </select></label>
        <label class="field"><span>Опорная дата (день, когда Смена 1 рабочая)</span>
          <input type="date" id="b-anchor" value="${esc(base.anchor || '2024-01-01')}" ${edit ? '' : 'disabled'}></label>
        <label class="field hidden" id="b-cycle-wrap"><span>Произвольный цикл (Р/В)</span>
          <input type="text" id="b-cycle-custom" placeholder="РРВВВВРР"
            value="${esc(String(base.cycle || '').startsWith('custom') ? String(base.cycle).slice(7) : '')}" ${edit ? '' : 'disabled'}></label>
      </div>
      <p class="hint" style="margin:-4px 0 10px">Смена 2 работает в противофазе со Сменой 1 — системное
        правило (18.10.2026). Значение рабочего дня (код и окно) задаётся в карточке
        сотрудника при приёме и переводе в блок.</p>
      ${edit ? '<button class="btn btn-primary btn-sm" id="b-save" style="margin-top:10px">Сохранить базовый цикл</button>' : ''}`)}
    ${settingsPanel('Пятидневка и «Другие смены»', `
      <p class="hint" style="margin:0">Здесь не настраиваются. У «Пятидневки» выходные задаются для
        КАЖДОГО сотрудника индивидуально (Сотрудники → карточка → «Перевод в блок»: например у начальника
        вс/пн, у бэк-специалиста сб/вс). «Другие смены» — контейнер индивидуальных графиков: 3/3, 1/3,
        сутки через трое, произвольный цикл «custom:РРВВ» или ручное заполнение ячеек.</p>
      <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
        <button class="btn btn-sm btn-ghost" data-nav="employees">Карточки сотрудников ↗</button>
        <button class="btn btn-sm btn-ghost" data-nav="schedule">График ↗</button>
      </div>`)}
    ${settingsDraftBarHtml()}`;

  settingsBindHealth(host);
  settingsBindDraftBar(host);
  $$('[data-nav]', host).forEach(b => b.onclick = () => navigate(b.dataset.nav));
  if (!edit) return;
  $$('[data-gdel]', host).forEach(b => b.onclick = () => confirmDialog('Исключить группу из реестра?',
    `Группа «${b.dataset.gdel}» перестанет существовать для расчёта. Если в ней остались сотрудники, расчёт остановится (CHK-GROUP-EXISTS) — сначала переведите их.`,
    () => {
      d.groups = (d.groups || []).filter(g => g !== b.dataset.gdel);
      settingsRenderScreen();
    }, 'Исключить из черновика'));
  const addG = $('#g-add');
  if (addG) addG.onclick = () => {
    const name = $('#g-new').value.trim();
    if (!name) return toast('Введите название группы', 'warn');
    if ((d.groups || []).includes(name)) return toast('Такая группа уже есть', 'warn');
    d.groups = [...(d.groups || []), name];
    settingsRenderScreen();
  };
  const syncCycle = () => $('#b-cycle-wrap').classList.toggle('hidden', $('#b-cycle').value !== 'custom');
  $('#b-cycle').onchange = syncCycle; syncCycle();
  $('#b-save').onclick = async () => {
    const cycle = $('#b-cycle').value === 'custom' ? 'custom:' + $('#b-cycle-custom').value.trim() : $('#b-cycle').value;
    /* значения рабочего дня и выходные блоков сохраняются как есть: они правятся
       в карточках сотрудников, экран базового цикла их не редактирует (18.10.2026) */
    const keepGroups = {};
    for (const [name, gc] of Object.entries(base.groups || {})) {
      const keep = {};
      if (gc && gc.value) keep.value = gc.value;
      if (gc && gc.off_weekdays) keep.off_weekdays = gc.off_weekdays;
      keepGroups[name] = keep;
    }
    const body = { cycle, anchor: $('#b-anchor').value, groups: keepGroups };
    try {
      await api('/api/settings/base', { method: 'PUT', body });
      toast('Базовый цикл сохранён и действует на все месяцы', 'ok');
      await settingsRefresh();
    } catch (e) { toast(e.message, 'err'); }
  };
}
