/* Раздел «Настройки»: экран «Обзор» (вынесено из settings.js, шаг 6.5 аудита).
   Оболочка, черновик версии справочников и общие помощники — в settings.js. */
'use strict';

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

  host.innerHTML = `
    ${settingsHead('Обзор', 'Что действует сейчас, здорова ли конфигурация и что вступит в силу — одним экраном.',
      `<button class="btn btn-sm" id="ov-versions">История версий</button>
       <button class="btn btn-sm" id="ov-compare">Сравнить с предыдущей</button>
       <button class="btn btn-sm btn-primary" id="ov-expert">Режим эксперта</button>`)}
    ${settingsPanel('', `
      <div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap">
        <div style="flex:1;min-width:260px">
          <div class="panel-title" style="margin-bottom:6px">Действующая версия справочников</div>
          <div style="font-family:var(--font-display);font-size:21px">
            ${v.id ? `#${v.id} · действует с ${esc(dateRu(v.valid_from))}` : 'справочники по умолчанию (версий нет)'}</div>
          <div class="hint" style="margin-top:4px">${esc(v.created_by || '—')}${v.created_at
            ? ` · ${esc(v.created_at.replace('T', ' ').slice(0, 16))}` : ''}${v.note ? ` · «${esc(v.note)}»` : ''}</div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn btn-sm" id="ov-calc">Каркас расчёта</button>
          <button class="btn btn-sm" id="ov-system">Версии и откат</button>
        </div>
      </div>`)}
    ${settingsHealthBanner(health)}
    <div class="stat-grid">
      <div class="stat"><div class="k">Шаг расчёта</div><div class="v">${s.step_minutes ?? '—'} <small>мин</small></div></div>
      <div class="stat info"><div class="k">Период</div><div class="v" style="font-size:19px">${esc(s.period_granularity === 'half_month' ? 'полмесяца' : 'месяц')}</div></div>
      <div class="stat"><div class="k">Лимит опоздания</div><div class="v">${s.late_limit_minutes ?? '—'} <small>мин</small></div></div>
      <div class="stat"><div class="k">Кодов Табеля</div><div class="v">${s.codes ?? 0}</div></div>
      <div class="stat"><div class="k">Окон (значений)</div><div class="v">${s.windows ?? 0}</div></div>
      <div class="stat ${s.rules_active ? 'warn' : ''}"><div class="k">Переопределений в месяце</div><div class="v">${s.rules_active ?? 0}</div></div>
    </div>
    <div class="grid-2">
      ${settingsPanel('Вступит в силу', upcoming.length
        ? upcoming.map(u => `<div class="kv"><span class="k">${esc(dateRu(u.date))} · ${esc(u.kind === 'version' ? 'версия' : 'правило')}</span>
            <span class="v" style="text-align:left;font-weight:600">${esc(u.text)}
              <button class="btn btn-sm btn-ghost" data-go="${esc(u.screen)}">открыть</button></span></div>`).join('')
        : '<p class="hint" style="margin:0">Правил и версий на будущее нет. Здесь видно всё, что вступит после сегодняшнего дня — «я не помню, что уже задал» больше не проблема.</p>')}
      ${settingsPanel('Изменения за 30 дней', recent.length
        ? recent.map(r => `<div class="kv"><span class="k">${esc((r.ts || '').replace('T', ' ').slice(0, 16))} · ${esc(r.actor || '—')}</span>
            <span class="v" style="text-align:left;font-weight:600">${esc(r.action)} · ${esc(r.target)}</span></div>`).join('')
          + '<div style="margin-top:10px"><button class="btn btn-sm btn-ghost" data-go="audit">Весь журнал аудита →</button></div>'
        : '<p class="hint" style="margin:0">За последние 30 дней настройки не менялись.</p>')}
    </div>
    ${settingsPanel('Что включено сейчас', `
      <div class="grid-2">
        <div>${SETTINGS_MODS.filter(m => m.name !== 'counts_in_ut').map(m => `
          <div class="kv"><span class="k">${esc(m.title)}</span>
            <span class="v">${esc(fmtGdValue(m.name, (s.global_defaults || {})[m.name]))}
              <span class="badge muted">глобально</span></span></div>`).join('')}
          <div class="kv"><span class="k">Учитываются ли часы в УТ</span>
            <span class="v">по коду дня <button class="btn btn-sm btn-ghost" data-go="codes">коды →</button></span></div>
        </div>
        <div>
          <div class="kv"><span class="k">Часовой пояс</span><span class="v">${esc(s.tz || p.tz || '—')}</span></div>
          <div class="kv"><span class="k">Каскад гашения</span><span class="v" style="font-weight:600">банк → ${esc((p.cascade_order || []).join(' → '))}</span></div>
          <div class="kv"><span class="k">Порядок размещения</span><span class="v" style="font-weight:600">${esc((p.placement_order || []).join(' → '))}</span></div>
          <div class="kv"><span class="k">Группы</span><span class="v" style="font-weight:600">${esc((p.groups || []).join(', '))}</span></div>
        </div>
      </div>`)}
    ${settingsPanel('Быстрые действия', `
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        ${can('settings.edit') ? '<button class="btn btn-sm" id="ov-wizard">+ Переопределение правила</button>' : ''}
        <button class="btn btn-sm" id="ov-resolve">Проверить значение для дня</button>
        ${can('settings.edit') ? '<button class="btn btn-sm" id="ov-code">+ Код Табеля</button>' : ''}
        ${can('settings.edit') ? '<button class="btn btn-sm" id="ov-window">+ Значение и окно</button>' : ''}
        <button class="btn btn-sm" data-go="calendar">Календарь правил</button>
        <button class="btn btn-sm btn-ghost" data-go="shifts">Словарь смен</button>
      </div>`)}
    ${settingsDraftBarHtml()}`;

  settingsBindHealth(host);
  settingsBindDraftBar(host);
  settingsOn('#ov-versions', host, () => settingsVersionsModal());
  settingsOn('#ov-compare', host, () => settingsCompareWithPrevious());
  settingsOn('#ov-expert', host, () => settingsGo('expert'));
  settingsOn('#ov-calc', host, () => settingsGo('calc'));
  settingsOn('#ov-system', host, () => settingsGo('system'));
  settingsOn('#ov-wizard', host, () => settingsWizard());
  settingsOn('#ov-resolve', host, () => settingsResolverModal());
  settingsOn('#ov-code', host, () => settingsCodeModal(null));
  settingsOn('#ov-window', host, () => settingsWindowModal(null));
}

async function settingsCompareWithPrevious() {
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

function settingsVersionsModal() {
  const versions = settingsUI.engine?.versions || [];
  const activeId = settingsUI.engine?.active?.id;
  openModal({
    title: 'История версий справочников', wide: true,
    subtitle: 'Версия выбирается по дате начала периода; закрытые периоды читаются из хранилища',
    body: versions.length ? `<div class="table-wrap"><table class="data"><thead><tr>
        <th>№</th><th>Действует с</th><th>Комментарий</th><th>Кто</th><th>Создана</th><th></th>
      </tr></thead><tbody>${versions.map(v => `<tr${v.id === activeId ? ' style="background:#f7f1ea"' : ''}>
        <td><b>#${v.id}</b>${v.id === activeId ? ' <span class="badge ok">действует</span>' : ''}</td>
        <td>${esc(dateRu(v.valid_from))}</td><td>${esc(v.note || '—')}</td>
        <td>${esc(v.created_by || '—')}</td><td>${esc((v.created_at || '').replace('T', ' ').slice(0, 16))}</td>
        <td class="num"><button class="btn btn-sm btn-ghost" data-ver="${v.id}">показать payload</button></td>
      </tr>`).join('')}</tbody></table></div>`
      : '<p class="hint">Версий нет: расчёт идёт по справочникам по умолчанию.</p>',
    footer: '<button class="btn btn-primary" data-ok>Закрыть</button>',
    onMount(m) {
      m.querySelector('[data-ok]').onclick = closeModal;
      $$('[data-ver]', m).forEach(b => b.onclick = async () => {
        const v = versions.find(x => x.id === +b.dataset.ver);
        try {
          const d = await api(`/api/engine-settings?on=${v.valid_from}`, { silent: true });
          openModal({ title: `Версия #${v.id} · payload`, wide: true,
            subtitle: `действует с ${dateRu(v.valid_from)}${v.note ? ` · ${v.note}` : ''}`,
            body: `<pre style="max-height:60vh;overflow:auto;background:#f8f5f1;border:1px solid var(--line);
              border-radius:6px;padding:12px;font-size:12px">${esc(JSON.stringify(d.active.payload, null, 2))}</pre>`,
            footer: '<button class="btn btn-primary" data-ok>Закрыть</button>',
            onMount(mm) { mm.querySelector('[data-ok]').onclick = closeModal; } });
        } catch (e) { toast(e.message, 'err'); }
      });
    },
  });
}
