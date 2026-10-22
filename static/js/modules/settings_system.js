/* Раздел «Настройки»: экраны «Система» и «Режим эксперта» (вынесено из settings.js, шаг 6.5 аудита).
   Оболочка, черновик версии справочников и общие помощники — в settings.js. */
'use strict';

registerModule({ screens: { system: { render: settingsScreenSystem, icon: 'gear' }, expert: { render: settingsScreenExpert, icon: 'code' } } });

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «СИСТЕМА» — данные, версии и откат, аудит настроек, диагностика, права
   ══════════════════════════════════════════════════════════════════════ */
async function settingsScreenSystem(host) {
  const [engine, health] = await Promise.all([settingsEngine(), settingsHealth().catch(() => null)]);
  const data = settingsUI.data || {};
  const c = data.counts || {};
  const versions = engine?.versions || [];

  host.innerHTML = `
    ${settingsHead('Система',
      'Данные объекта, версии справочников и откат, журнал изменений настроек, диагностика и права.',
      '<button class="btn btn-sm" id="sy-versions">История версий</button>')}
    ${settingsPanel('Данные системы', `
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
    ${settingsPanel('Версии справочников и откат', `
      <div class="table-wrap"><table class="data"><thead><tr>
        <th>№</th><th>Действует с</th><th>Комментарий</th><th>Кто</th><th></th></tr></thead>
      <tbody>${versions.slice(0, 12).map(v => `<tr${v.id === engine?.active?.id ? ' style="background:#f7f1ea"' : ''}>
        <td><b>#${v.id}</b>${v.id === engine?.active?.id ? ' <span class="badge ok">действует</span>' : ''}</td>
        <td>${esc(dateRu(v.valid_from))}</td><td>${esc(v.note || '—')}</td><td>${esc(v.created_by || '—')}</td>
        <td class="num" style="white-space:nowrap">
          <button class="btn btn-sm btn-ghost" data-show="${v.id}">payload</button>
          ${can('settings.edit') ? `<button class="btn btn-sm btn-ghost" data-rollback="${v.id}"
            title="Скопировать payload этой версии в черновик и опубликовать новой датой">откатиться</button>` : ''}
        </td></tr>`).join('') || '<tr><td colspan="5" class="empty">Версий нет</td></tr>'}</tbody></table></div>
      <p class="hint">Откат — не удаление истории: payload прежней версии копируется в черновик и
        публикуется новой версией с новой датой (история версий остаётся полной). Закрытые периоды
        не меняются (RUL-CLOSED-PERIOD-IMMUTABLE).</p>`)}
    ${settingsPanel('Изменения настроек за 30 дней', health?.recent?.length
      ? health.recent.map(r => `<div class="kv"><span class="k">${esc((r.ts || '').replace('T', ' ').slice(0, 16))} · ${esc(r.actor || '—')}</span>
          <span class="v" style="text-align:left;font-weight:600">${esc(r.action)} · ${esc(r.target)}</span></div>`).join('')
        + '<div style="margin-top:10px"><button class="btn btn-sm btn-ghost" data-nav="audit">Весь журнал аудита →</button></div>'
      : '<p class="hint" style="margin:0">Изменений не было.</p>')}
    ${settingsPanel('Диагностика и права', `
      <div class="grid-2">
        <div>
          <div class="kv"><span class="k">Движок</span><span class="v">v7.1</span></div>
          <div class="kv"><span class="k">Действующая версия справочников</span><span class="v">#${engine?.active?.id ?? '—'}</span></div>
          <div class="kv"><span class="k">Замечаний конфигурации</span><span class="v">${(health?.checks || []).length}</span></div>
          <div class="kv"><span class="k">Последний закрытый период</span><span class="v">${health?.periods?.last_closed_start
            ? esc(dateRu(health.periods.last_closed_start)) : 'нет'}</span></div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-content:flex-start">
          <button class="btn btn-sm" id="sy-selfcheck">Самопроверка схемы БД</button>
          ${can('access.manage') ? '<button class="btn btn-sm" data-nav="access">Права доступа ↗</button>' : ''}
          <button class="btn btn-sm btn-ghost" data-go="expert">Режим эксперта (JSON)</button>
        </div>
      </div>`)}
    ${settingsDraftBarHtml()}`;

  settingsBindHealth(host);
  settingsBindDraftBar(host);
  settingsOn('#sy-versions', host, () => settingsVersionsModal());
  settingsOn('#sy-selfcheck', host, () => window.open('/api/selfcheck', '_blank', 'noopener'));
  $$('[data-nav]', host).forEach(b => b.onclick = () => navigate(b.dataset.nav));
  $$('[data-show]', host).forEach(b => b.onclick = async () => {
    const v = versions.find(x => x.id === +b.dataset.show);
    try {
      const r = await api(`/api/engine-settings?on=${v.valid_from}`, { silent: true });
      openModal({ title: `Версия #${v.id} · payload`, wide: true,
        subtitle: `действует с ${dateRu(v.valid_from)}${v.note ? ` · ${v.note}` : ''}`,
        body: `<pre style="max-height:60vh;overflow:auto;background:#f8f5f1;border:1px solid var(--line);border-radius:6px;padding:12px;font-size:12px">${esc(JSON.stringify(r.active.payload, null, 2))}</pre>`,
        footer: '<button class="btn btn-primary" data-ok>Закрыть</button>',
        onMount(m) { m.querySelector('[data-ok]').onclick = closeModal; } });
    } catch (e) { toast(e.message, 'err'); }
  });
  $$('[data-rollback]', host).forEach(b => b.onclick = async () => {
    const v = versions.find(x => x.id === +b.dataset.rollback);
    if (v.id === engine?.active?.id) return toast('Эта версия и так действует', 'warn');
    try {
      const r = await api(`/api/engine-settings?on=${v.valid_from}`, { silent: true });
      settingsUI.draft = JSON.parse(JSON.stringify(r.active.payload));
      settingsUI.screen = 'calc';
      await settingsRenderScreen();
      settingsUpdateDraftBars();
      toast(`Payload версии #${v.id} загружен в черновик — проверьте diff и опубликуйте`, 'ok');
    } catch (e) { toast(e.message, 'err'); }
  });
}

/* ══════════════════════════════════════════════════════════════════════
   ЭКРАН «РЕЖИМ ЭКСПЕРТА» — тот же черновик, но вторым видом: сырой JSON
   версии справочников и полный список модификаторов (renderEngineSettings).
   ══════════════════════════════════════════════════════════════════════ */
async function settingsScreenExpert(host) {
  host.innerHTML = `
    ${settingsHead('Режим эксперта (JSON)',
      'Полный payload версии справочников и все модификаторы периода. Формы выше и этот экран правят ОДНУ конфигурацию: формы — два вида одного черновика, а не второй источник правды.',
      '<button class="btn btn-sm" data-go="overview">← Обзор</button>')}
    <div class="panel" id="st-expert"><div class="empty">Загрузка справочников движка…</div></div>`;
  settingsBindHealth(host);
  await renderEngineSettings($('#st-expert', host));
}
