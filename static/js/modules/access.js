'use strict';

/* ══════════════════════════════════════════════════════════════════
   ПРАВА ДОСТУПА — роли (базовые группы), группы доступа, индивидуальные права
   Модуль на lit-html (ADR-0013, раздел 7).
   ══════════════════════════════════════════════════════════════════ */
import { loadPerms, registerModule } from '../app.js';
import { $, $$, api, closeModal, confirmDialog, openModal, roleTitle, state, toast } from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';

state.accessTab = state.accessTab || 'roles';

registerModule({ views: { access: loadAccess }, screens: { access: { icon: 'shield' } } });

async function loadAccess() {
  const host = $('#view-access');
  const tab = state.accessTab;
  let error = '';
  try { state.access = await api('/api/access'); } catch (e) { error = e.message; }
  render(html`
    <div class="page-head">
      <div><h2>Права доступа</h2><div class="sub">Итоговое право = права роли → группы (запрет сильнее разрешения) →
        индивидуальные права пользователя (решают окончательно)</div></div>
      <div class="spacer"></div>
      <div class="seg" id="ac-tabs">${[['roles', 'Роли'], ['groups', 'Группы'], ['users', 'Пользователи']].map(([t, l]) =>
        html`<button data-t=${t} class=${tab === t ? 'active' : ''} @click=${() => { state.accessTab = t; loadAccess(); }}>${l}</button>`)}</div>
    </div>
    <div id="ac-body">${error ? html`<div class="panel"><div class="empty">${error}</div></div>`
      : ({ roles: accessRoles, groups: accessGroups, users: accessUsers })[tab]()}</div>`, mount(host));
}

/* grants — {perm: allow|deny}; baseline — множество прав «по умолчанию» (для подсказки) */
function accessMatrix(grants, baseline, idPrefix) {
  const sections = {};
  state.access.permissions.forEach(p => { (sections[p.section] = sections[p.section] || []).push(p); });
  return html`${Object.entries(sections).map(([sec, perms]) => html`
    <div class="v4-perm-sec"><div class="lbl">${sec}</div>
      ${perms.map(p => {
        const v = grants[p.key] || 'default';
        const base = baseline ? (baseline.has(p.key) ? '✓' : '✗') : '—';
        return html`<div class="v4-perm-row"><span>${p.title} <code>${p.key}</code></span>
          <select data-perm=${p.key} id=${`${idPrefix}-${p.key.replace('.', '_')}`}>
            <option value="default" ?selected=${v === 'default'}>по умолчанию (${base})</option>
            <option value="allow" ?selected=${v === 'allow'}>разрешить</option>
            <option value="deny" ?selected=${v === 'deny'}>запретить</option>
          </select></div>`;
      })}</div>`)}`;
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
  const opts = (list, cur) => list.map(([v, t]) => html`<option value=${v} ?selected=${v === cur}>${t}</option>`);
  openModal({
    title: r ? `Настройки роли «${r.title}»` : 'Новая роль',
    body: html`<label class="field"><span>Название</span><input type="text" id="rl-title" maxlength="80"
             .value=${r?.title || ''} placeholder="Например: Ночной супервайзер"></label>
      <label class="field"><span>Уровень роли</span><select id="rl-rank">${opts(ROLE_RANKS, r ? r.rank : 10)}</select></label>
      <label class="field"><span>Управляет учётками</span><select id="rl-assign">${opts(ROLE_ASSIGNS, r ? r.max_assignable_rank : -1)}</select></label>
      <p class="hint">Права новой роли пустые — после создания нажмите «Изменить права роли».</p>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button><button class="btn btn-primary" data-save>Сохранить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        const body = { title: $('#rl-title', m).value.trim(), rank: +$('#rl-rank', m).value,
                       max_assignable_rank: +$('#rl-assign', m).value };
        try {
          await api(r ? `/api/access/roles/${r.role}/settings` : '/api/access/roles', { method: r ? 'PUT' : 'POST', body });
          closeModal(); toast(r ? 'Роль сохранена' : 'Роль создана', 'ok');
          await loadPerms(); loadAccess();   // названия и назначаемые роли — для формы сотрудника
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* окно с матрицей прав: роль, группа или пользователь отличаются только адресом сохранения */
function matrixModal({ title, subtitle, grants, baseline, prefix, url, ok, hint }) {
  openModal({
    title, subtitle, wide: true,
    body: html`${accessMatrix(grants, baseline, prefix)}${hint ? html`<p class="hint">${hint}</p>` : nothing}`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button><button class="btn btn-primary" data-save>Сохранить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        try { await api(url, { method: 'PUT', body: { grants: collectMatrix(m) } });
          closeModal(); toast(ok, 'ok'); loadAccess(); } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

function accessRoles() {
  const a = state.access;
  const delRole = r => confirmDialog(`Удалить роль «${r.title}»?`, r.users ? `Роль назначена пользователям (${r.users}) — сначала смените им роль.`
      : 'Права роли тоже будут удалены.',
    async () => {
      try { await api(`/api/access/roles/${r.role}`, { method: 'DELETE' }); toast('Роль удалена', 'ok'); await loadPerms(); loadAccess(); }
      catch (e) { toast(e.message, 'err'); }
    }, 'Удалить', true);
  return html`<div class="panel"><button class="btn btn-primary" id="rl-add" @click=${() => roleSettingsModal(null)}>Новая роль</button>
      <span class="hint" style="margin-left:8px">своя роль — например «Ночной супервайзер» или «Бухгалтерия»</span></div>
    ${a.roles.map(r => html`
    <div class="panel"><h3 class="panel-title">${r.title} · ${r.effective.length} из ${a.permissions.length}
      <span class=${`badge ${r.builtin ? 'muted' : 'info'}`}>${r.builtin ? 'встроенная' : 'своя'} · пользователей ${r.users}</span></h3>
      <div class="v4-chips">${a.permissions.map(p => html`<span class=${`badge ${r.effective.includes(p.key) ? 'ok' : 'muted'}`}>${p.title}</span> `)}</div>
      <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:10px">
        <button class="btn btn-sm" data-role=${r.role} @click=${() => matrixModal({ title: `Права роли «${r.title}»`, grants: r.overrides,
          baseline: new Set(r.defaults), prefix: 'ar', url: `/api/access/roles/${r.role}`, ok: 'Права роли сохранены' })}>Изменить права роли</button>
        ${r.builtin ? nothing : html`<button class="btn btn-sm" data-role-set=${r.role} @click=${() => roleSettingsModal(r)}>Настройки роли</button>
        <button class="btn btn-sm btn-ghost" data-role-del=${r.role} style="color:var(--danger)" @click=${() => delRole(r)}>Удалить</button>`}</div></div>`)}
    <p class="hint">Права роли — базовые для всех пользователей с этой ролью. Изменения применяются сразу.</p>`;
}

function membersModal(g) {
  const a = state.access;
  openModal({ title: `Состав группы «${g.name}»`,
    body: html`<input type="text" id="agm-q" placeholder="Поиск" style="width:100%;margin-bottom:8px">
      <div style="max-height:50vh;overflow:auto">${a.users.map(u => html`<label class="v4-user-check" data-n=${(u.name + ' ' + u.username).toLowerCase()}>
        <input type="checkbox" value=${u.id} .checked=${g.members.includes(u.id)}> ${u.name} <small>${u.username} · ${roleTitle(u.role)}</small></label>`)}</div>`,
    footer: html`<button class="btn btn-ghost" data-cancel>Отмена</button><button class="btn btn-primary" data-save>Сохранить</button>`,
    onMount(m) {
      $('#agm-q', m).oninput = e => $$('.v4-user-check', m).forEach(l => { l.style.display = l.dataset.n.includes(e.target.value.toLowerCase()) ? '' : 'none'; });
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        const ids = $$('.v4-user-check input:checked', m).map(i => +i.value);
        try { await api(`/api/access/groups/${g.id}/members`, { method: 'PUT', body: { user_ids: ids } });
          closeModal(); toast('Состав сохранён', 'ok'); loadAccess(); } catch (e) { toast(e.message, 'err'); }
      };
    } });
}

function accessGroups() {
  const a = state.access;
  const userName = id => (a.users.find(u => u.id === id) || {}).name || id;
  const add = async () => {
    try { await api('/api/access/groups', { method: 'POST', body: { name: $('#ag-name').value, description: $('#ag-desc').value } });
      toast('Группа создана', 'ok'); loadAccess(); } catch (e) { toast(e.message, 'err'); }
  };
  const del = g => confirmDialog('Удалить группу?', 'Права группы перестанут действовать для её участников.',
    async () => { try { await api(`/api/access/groups/${g.id}`, { method: 'DELETE' }); closeModal(); loadAccess(); } catch (e) { toast(e.message, 'err'); } }, 'Удалить');
  return html`
    <div class="panel"><div style="display:flex;gap:8px;flex-wrap:wrap;align-items:end">
      <label class="field" style="margin:0;flex:1;min-width:200px"><span>Новая группа</span><input type="text" id="ag-name" placeholder="Например: Табельщики"></label>
      <label class="field" style="margin:0;flex:2;min-width:200px"><span>Описание</span><input type="text" id="ag-desc"></label>
      <button class="btn btn-primary" id="ag-add" @click=${add}>Создать</button></div></div>
    ${a.groups.length ? a.groups.map(g => html`<div class="panel">
      <h3 class="panel-title">${g.name} · участников ${g.members.length}</h3>
      ${g.description ? html`<p class="hint" style="margin-top:-6px">${g.description}</p>` : nothing}
      <div class="v4-chips">${Object.keys(g.grants).length ? Object.entries(g.grants).map(([k, v]) => html`<span class=${`badge ${v === 'allow' ? 'ok' : 'danger'}`}>${v === 'allow' ? '+' : '−'} ${(a.permissions.find(p => p.key === k) || {}).title || k}</span> `)
        : html`<span class="hint">прав не задано</span>`}</div>
      <div class="v4-chips" style="margin-top:6px">${g.members.map(id => html`<span class="badge muted">${userName(id)}</span> `)}</div>
      <div style="display:flex;gap:8px;margin-top:10px">
        <button class="btn btn-sm" data-g-grants=${g.id} @click=${() => matrixModal({ title: `Права группы «${g.name}»`, grants: g.grants,
          baseline: null, prefix: 'ag', url: `/api/access/groups/${g.id}/grants`, ok: 'Права группы сохранены' })}>Права группы</button>
        <button class="btn btn-sm" data-g-members=${g.id} @click=${() => membersModal(g)}>Состав</button>
        <button class="btn btn-sm btn-ghost" data-g-del=${g.id} style="color:var(--danger)" @click=${() => del(g)}>Удалить</button></div></div>`)
      : html`<div class="panel"><div class="empty">Групп пока нет. Группа добавляет (или запрещает) права всем своим участникам.</div></div>`}`;
}

function accessUsers() {
  const a = state.access;
  const gname = id => (a.groups.find(g => g.id === id) || {}).name || id;
  const filter = e => $$('#ac-body tr[data-n]').forEach(tr => { tr.style.display = tr.dataset.n.includes(e.target.value.toLowerCase()) ? '' : 'none'; });
  return html`<div class="panel"><input type="text" id="au-q" placeholder="Поиск по имени или логину" style="width:100%;max-width:360px" @input=${filter}></div>
    <div class="table-wrap"><table class="data responsive"><thead><tr><th>Пользователь</th><th>Роль</th><th>Группы</th>
      <th>Индивидуально</th><th>Итого прав</th><th></th></tr></thead><tbody>
    ${a.users.map(u => html`<tr data-n=${(u.name + ' ' + u.username).toLowerCase()}>
      <td class="who" data-label="Пользователь">${u.name}<small>${u.username}${u.active ? '' : ' · отключён'}</small></td>
      <td data-label="Роль">${roleTitle(u.role)}</td>
      <td data-label="Группы">${u.groups.map(g => html`<span class="badge muted">${gname(g)}</span> `)}</td>
      <td data-label="Индивидуально">${Object.entries(u.grants).map(([k, v]) => html`<span class=${`badge ${v === 'allow' ? 'ok' : 'danger'}`}>${v === 'allow' ? '+' : '−'} ${k}</span> `)}</td>
      <td class="num" data-label="Итого">${u.effective.length}</td>
      <td><button class="btn btn-sm" data-u=${u.id} @click=${() => matrixModal({ title: `Индивидуальные права · ${u.name}`,
        subtitle: `Сейчас действует: ${u.effective.length} прав`, grants: u.grants, baseline: new Set(u.effective), prefix: 'au',
        url: `/api/access/users/${u.id}/grants`, ok: 'Права пользователя сохранены',
        hint: '«По умолчанию» — как получается из роли и групп (в скобках — текущее итоговое значение).' })}>Права</button></td></tr>`)}</tbody></table></div>`;
}
