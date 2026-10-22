'use strict';

/* ══════════════════════════════════════════════════════════════════
   ПРАВА ДОСТУПА — роли (базовые группы), группы доступа, индивидуальные права
   ══════════════════════════════════════════════════════════════════ */
state.accessTab = state.accessTab || 'roles';

registerModule({ views: { access: loadAccess }, screens: { access: { icon: 'shield' } } });

async function loadAccess() {
  const host = $('#view-access');
  host.innerHTML = `
    <div class="page-head">
      <div><h2>Права доступа</h2><div class="sub">Итоговое право = права роли → группы (запрет сильнее разрешения) →
        индивидуальные права пользователя (решают окончательно)</div></div>
      <div class="spacer"></div>
      <div class="seg" id="ac-tabs">
        <button data-t="roles">Роли</button><button data-t="groups">Группы</button><button data-t="users">Пользователи</button>
      </div>
    </div>
    <div id="ac-body"><div class="empty">Загрузка…</div></div>`;
  $$('#ac-tabs button').forEach(b => {
    b.classList.toggle('active', b.dataset.t === state.accessTab);
    b.onclick = () => { state.accessTab = b.dataset.t; loadAccess(); };
  });
  try { state.access = await api('/api/access'); } catch (e) {
    $('#ac-body').innerHTML = `<div class="panel"><div class="empty">${esc(e.message)}</div></div>`; return;
  }
  ({ roles: renderAccessRoles, groups: renderAccessGroups, users: renderAccessUsers })[state.accessTab]();
}

function accessMatrix(grants, baseline, idPrefix) {
  /* grants — {perm: allow|deny}; baseline — множество прав «по умолчанию» (для подсказки) */
  const sections = {};
  state.access.permissions.forEach(p => { (sections[p.section] = sections[p.section] || []).push(p); });
  return Object.entries(sections).map(([sec, perms]) => `
    <div class="v4-perm-sec"><div class="lbl">${esc(sec)}</div>
      ${perms.map(p => {
        const v = grants[p.key] || 'default';
        const base = baseline ? (baseline.has(p.key) ? '✓' : '✗') : '—';
        return `<div class="v4-perm-row"><span>${esc(p.title)} <code>${esc(p.key)}</code></span>
          <select data-perm="${p.key}" id="${idPrefix}-${p.key.replace('.', '_')}">
            <option value="default" ${v === 'default' ? 'selected' : ''}>по умолчанию (${base})</option>
            <option value="allow" ${v === 'allow' ? 'selected' : ''}>разрешить</option>
            <option value="deny" ${v === 'deny' ? 'selected' : ''}>запретить</option>
          </select></div>`;
      }).join('')}</div>`).join('');
}
function collectMatrix(root) {
  const out = {};
  $$('select[data-perm]', root).forEach(s => { if (s.value !== 'default') out[s.dataset.perm] = s.value; });
  return out;
}

/* Свои роли (ADR-0011): уровень решает, кто управляет учётками с этой ролью, а «назначает» —
   с какими учётками может работать сама роль. Числа — уровни встроенных ролей. */
const ROLE_RANKS = [[10, 'как у сотрудника — учётками управляют супервайзер и выше'],
                    [60, 'как у супервайзера — учётками управляют менеджер и администратор'],
                    [80, 'как у менеджера — учётками управляет только администратор']];
const ROLE_ASSIGNS = [[-1, 'никем — учётками не управляет'], [10, 'сотрудниками'],
                      [60, 'сотрудниками и супервайзерами'], [80, 'всеми, кроме администраторов']];

function roleSettingsModal(r) {
  const opts = (list, cur) => list.map(([v, t]) => `<option value="${v}" ${v === cur ? 'selected' : ''}>${esc(t)}</option>`).join('');
  openModal({
    title: r ? `Настройки роли «${r.title}»` : 'Новая роль',
    body: `<label class="field"><span>Название</span><input type="text" id="rl-title" maxlength="80"
             value="${esc(r?.title || '')}" placeholder="Например: Ночной супервайзер"></label>
      <label class="field"><span>Уровень роли</span><select id="rl-rank">${opts(ROLE_RANKS, r ? r.rank : 10)}</select></label>
      <label class="field"><span>Управляет учётками</span><select id="rl-assign">${opts(ROLE_ASSIGNS, r ? r.max_assignable_rank : -1)}</select></label>
      <p class="hint">Права новой роли пустые — после создания нажмите «Изменить права роли».</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button><button class="btn btn-primary" data-save>Сохранить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        const body = { title: $('#rl-title').value.trim(), rank: +$('#rl-rank').value,
                       max_assignable_rank: +$('#rl-assign').value };
        try {
          await api(r ? `/api/access/roles/${r.role}/settings` : '/api/access/roles', { method: r ? 'PUT' : 'POST', body });
          closeModal(); toast(r ? 'Роль сохранена' : 'Роль создана', 'ok');
          await loadPerms(); loadAccess();   // названия и назначаемые роли — для формы сотрудника
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

function renderAccessRoles() {
  const a = state.access;
  $('#ac-body').innerHTML = `<div class="panel"><button class="btn btn-primary" id="rl-add">Новая роль</button>
      <span class="hint" style="margin-left:8px">своя роль — например «Ночной супервайзер» или «Бухгалтерия»</span></div>`
    + a.roles.map(r => `
    <div class="panel"><h3 class="panel-title">${esc(r.title)} · ${r.effective.length} из ${a.permissions.length}
      <span class="badge ${r.builtin ? 'muted' : 'info'}">${r.builtin ? 'встроенная' : 'своя'} · пользователей ${r.users}</span></h3>
      <div class="v4-chips">${a.permissions.map(p => `<span class="badge ${r.effective.includes(p.key) ? 'ok' : 'muted'}">${esc(p.title)}</span>`).join(' ')}</div>
      <div style="display:flex;gap:8px;margin-top:10px">
        <button class="btn btn-sm" data-role="${esc(r.role)}">Изменить права роли</button>
        ${r.builtin ? '' : `<button class="btn btn-sm" data-role-set="${esc(r.role)}">Настройки роли</button>
        <button class="btn btn-sm btn-ghost" data-role-del="${esc(r.role)}" style="color:var(--danger)">Удалить</button>`}</div></div>`).join('')
    + '<p class="hint">Права роли — базовые для всех пользователей с этой ролью. Изменения применяются сразу.</p>';
  $('#rl-add').onclick = () => roleSettingsModal(null);
  $$('#ac-body [data-role-set]').forEach(b => b.onclick = () => roleSettingsModal(a.roles.find(x => x.role === b.dataset.roleSet)));
  $$('#ac-body [data-role-del]').forEach(b => b.onclick = () => {
    const r = a.roles.find(x => x.role === b.dataset.roleDel);
    confirmDialog(`Удалить роль «${r.title}»?`, r.users ? `Роль назначена пользователям (${r.users}) — сначала смените им роль.`
        : 'Права роли тоже будут удалены.',
      async () => {
        try { await api(`/api/access/roles/${r.role}`, { method: 'DELETE' }); toast('Роль удалена', 'ok'); await loadPerms(); loadAccess(); }
        catch (e) { toast(e.message, 'err'); }
      }, 'Удалить', true);
  });
  $$('#ac-body [data-role]').forEach(b => b.onclick = () => {
    const r = a.roles.find(x => x.role === b.dataset.role);
    openModal({
      title: `Права роли «${r.title}»`, wide: true,
      body: accessMatrix(r.overrides, new Set(r.defaults), 'ar'),
      footer: `<button class="btn btn-ghost" data-cancel>Отмена</button><button class="btn btn-primary" data-save>Сохранить</button>`,
      onMount(m) {
        m.querySelector('[data-cancel]').onclick = closeModal;
        m.querySelector('[data-save]').onclick = async () => {
          try { await api(`/api/access/roles/${r.role}`, { method: 'PUT', body: { grants: collectMatrix(m) } });
            closeModal(); toast('Права роли сохранены', 'ok'); loadAccess(); } catch (e) { toast(e.message, 'err'); }
        };
      },
    });
  });
}

function renderAccessGroups() {
  const a = state.access;
  const userName = id => (a.users.find(u => u.id === id) || {}).name || id;
  $('#ac-body').innerHTML = `
    <div class="panel"><div style="display:flex;gap:8px;flex-wrap:wrap;align-items:end">
      <label class="field" style="margin:0;flex:1;min-width:200px"><span>Новая группа</span><input type="text" id="ag-name" placeholder="Например: Табельщики"></label>
      <label class="field" style="margin:0;flex:2;min-width:200px"><span>Описание</span><input type="text" id="ag-desc"></label>
      <button class="btn btn-primary" id="ag-add">Создать</button></div></div>
    ${a.groups.map(g => `<div class="panel">
      <h3 class="panel-title">${esc(g.name)} · участников ${g.members.length}</h3>
      ${g.description ? `<p class="hint" style="margin-top:-6px">${esc(g.description)}</p>` : ''}
      <div class="v4-chips">${Object.entries(g.grants).map(([k, v]) => `<span class="badge ${v === 'allow' ? 'ok' : 'danger'}">${v === 'allow' ? '+' : '−'} ${esc((a.permissions.find(p => p.key === k) || {}).title || k)}</span>`).join(' ') || '<span class="hint">прав не задано</span>'}</div>
      <div class="v4-chips" style="margin-top:6px">${g.members.map(id => `<span class="badge muted">${esc(userName(id))}</span>`).join(' ')}</div>
      <div style="display:flex;gap:8px;margin-top:10px">
        <button class="btn btn-sm" data-g-grants="${g.id}">Права группы</button>
        <button class="btn btn-sm" data-g-members="${g.id}">Состав</button>
        <button class="btn btn-sm btn-ghost" data-g-del="${g.id}" style="color:var(--danger)">Удалить</button></div></div>`).join('')
      || '<div class="panel"><div class="empty">Групп пока нет. Группа добавляет (или запрещает) права всем своим участникам.</div></div>'}`;
  $('#ag-add').onclick = async () => {
    try { await api('/api/access/groups', { method: 'POST', body: { name: $('#ag-name').value, description: $('#ag-desc').value } });
      toast('Группа создана', 'ok'); loadAccess(); } catch (e) { toast(e.message, 'err'); }
  };
  $$('[data-g-grants]').forEach(b => b.onclick = () => {
    const g = a.groups.find(x => x.id === +b.dataset.gGrants);
    openModal({ title: `Права группы «${g.name}»`, wide: true, body: accessMatrix(g.grants, null, 'ag'),
      footer: `<button class="btn btn-ghost" data-cancel>Отмена</button><button class="btn btn-primary" data-save>Сохранить</button>`,
      onMount(m) {
        m.querySelector('[data-cancel]').onclick = closeModal;
        m.querySelector('[data-save]').onclick = async () => {
          try { await api(`/api/access/groups/${g.id}/grants`, { method: 'PUT', body: { grants: collectMatrix(m) } });
            closeModal(); toast('Права группы сохранены', 'ok'); loadAccess(); } catch (e) { toast(e.message, 'err'); }
        };
      } });
  });
  $$('[data-g-members]').forEach(b => b.onclick = () => {
    const g = a.groups.find(x => x.id === +b.dataset.gMembers);
    openModal({ title: `Состав группы «${g.name}»`,
      body: `<input type="text" id="agm-q" placeholder="Поиск" style="width:100%;margin-bottom:8px">
        <div style="max-height:50vh;overflow:auto">${a.users.map(u => `<label class="v4-user-check" data-n="${esc((u.name + ' ' + u.username).toLowerCase())}">
          <input type="checkbox" value="${u.id}" ${g.members.includes(u.id) ? 'checked' : ''}> ${esc(u.name)} <small>${esc(u.username)} · ${esc(roleTitle(u.role))}</small></label>`).join('')}</div>`,
      footer: `<button class="btn btn-ghost" data-cancel>Отмена</button><button class="btn btn-primary" data-save>Сохранить</button>`,
      onMount(m) {
        $('#agm-q').oninput = e => $$('.v4-user-check', m).forEach(l => { l.style.display = l.dataset.n.includes(e.target.value.toLowerCase()) ? '' : 'none'; });
        m.querySelector('[data-cancel]').onclick = closeModal;
        m.querySelector('[data-save]').onclick = async () => {
          const ids = $$('.v4-user-check input:checked', m).map(i => +i.value);
          try { await api(`/api/access/groups/${g.id}/members`, { method: 'PUT', body: { user_ids: ids } });
            closeModal(); toast('Состав сохранён', 'ok'); loadAccess(); } catch (e) { toast(e.message, 'err'); }
        };
      } });
  });
  $$('[data-g-del]').forEach(b => b.onclick = () => confirmDialog('Удалить группу?', 'Права группы перестанут действовать для её участников.',
    async () => { try { await api(`/api/access/groups/${b.dataset.gDel}`, { method: 'DELETE' }); closeModal(); loadAccess(); } catch (e) { toast(e.message, 'err'); } }, 'Удалить'));
}

function renderAccessUsers() {
  const a = state.access;
  const gname = id => (a.groups.find(g => g.id === id) || {}).name || id;
  $('#ac-body').innerHTML = `<div class="panel"><input type="text" id="au-q" placeholder="Поиск по имени или логину" style="width:100%;max-width:360px"></div>
    <div class="table-wrap"><table class="data responsive"><thead><tr><th>Пользователь</th><th>Роль</th><th>Группы</th>
      <th>Индивидуально</th><th>Итого прав</th><th></th></tr></thead><tbody>
    ${a.users.map(u => `<tr data-n="${esc((u.name + ' ' + u.username).toLowerCase())}">
      <td class="who" data-label="Пользователь">${esc(u.name)}<small>${esc(u.username)}${u.active ? '' : ' · отключён'}</small></td>
      <td data-label="Роль">${esc(roleTitle(u.role))}</td>
      <td data-label="Группы">${u.groups.map(g => `<span class="badge muted">${esc(gname(g))}</span>`).join(' ')}</td>
      <td data-label="Индивидуально">${Object.entries(u.grants).map(([k, v]) => `<span class="badge ${v === 'allow' ? 'ok' : 'danger'}">${v === 'allow' ? '+' : '−'} ${esc(k)}</span>`).join(' ')}</td>
      <td class="num" data-label="Итого">${u.effective.length}</td>
      <td><button class="btn btn-sm" data-u="${u.id}">Права</button></td></tr>`).join('')}</tbody></table></div>`;
  $('#au-q').oninput = e => $$('#ac-body tr[data-n]').forEach(tr => { tr.style.display = tr.dataset.n.includes(e.target.value.toLowerCase()) ? '' : 'none'; });
  $$('[data-u]').forEach(b => b.onclick = () => {
    const u = a.users.find(x => x.id === +b.dataset.u);
    openModal({ title: `Индивидуальные права · ${u.name}`, subtitle: `Сейчас действует: ${u.effective.length} прав`, wide: true,
      body: accessMatrix(u.grants, new Set(u.effective), 'au') + '<p class="hint">«По умолчанию» — как получается из роли и групп (в скобках — текущее итоговое значение).</p>',
      footer: `<button class="btn btn-ghost" data-cancel>Отмена</button><button class="btn btn-primary" data-save>Сохранить</button>`,
      onMount(m) {
        m.querySelector('[data-cancel]').onclick = closeModal;
        m.querySelector('[data-save]').onclick = async () => {
          try { await api(`/api/access/users/${u.id}/grants`, { method: 'PUT', body: { grants: collectMatrix(m) } });
            closeModal(); toast('Права пользователя сохранены', 'ok'); loadAccess(); } catch (e) { toast(e.message, 'err'); }
        };
      } });
  });
}
