'use strict';

/* ══════════════════════════════════════════════════════════════════
   ПРАВА ДОСТУПА — роли (базовые группы), группы доступа, индивидуальные права
   ══════════════════════════════════════════════════════════════════ */
state.accessTab = state.accessTab || 'roles';

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

function renderAccessRoles() {
  const a = state.access;
  $('#ac-body').innerHTML = a.roles.map(r => `
    <div class="panel"><h3 class="panel-title">${esc(r.title)} · ${r.effective.length} из ${a.permissions.length}</h3>
      <div class="v4-chips">${a.permissions.map(p => `<span class="badge ${r.effective.includes(p.key) ? 'ok' : 'muted'}">${esc(p.title)}</span>`).join(' ')}</div>
      <button class="btn btn-sm" data-role="${r.role}" style="margin-top:10px">Изменить права роли</button></div>`).join('')
    + '<p class="hint">Права роли — базовые для всех пользователей с этой ролью. Изменения применяются сразу.</p>';
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
          <input type="checkbox" value="${u.id}" ${g.members.includes(u.id) ? 'checked' : ''}> ${esc(u.name)} <small>${esc(u.username)} · ${esc(ROLE_TITLES[u.role] || u.role)}</small></label>`).join('')}</div>`,
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
      <td data-label="Роль">${esc(ROLE_TITLES[u.role] || u.role)}</td>
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
