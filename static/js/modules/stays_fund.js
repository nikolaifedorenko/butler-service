/* ══════════════════════════════════════════════════════════════════════
   «ШАХМАТКА» — экран Настроек «Фонд и категории» (спецификация
   docs/superpowers/specs/2026-10-26-stays-fund-versions-design.md §4, §10).
   Фонд хранится версиями с даты: экран показывает действующую версию, черновик
   или любую версию из истории; менять можно только черновик «с даты D».
   Каждая запись черновика отправляет rev и получает новый; 409 «черновик изменён
   другим пользователем» — тост и перезагрузка снимка.
   Файл фонда (§9): «Выгрузить фонд» — Excel на дату экрана; «Загрузить фонд» — черновиком
   с даты или, администратору (stays.reset) и пока шахматка не «в эксплуатации», начальной
   загрузкой «заменить всё» с предпросмотром и словом «ЗАМЕНИТЬ».
   Модуль на lit-html (ADR-0013, раздел 7): обработчики — в шаблонах, экран перерисовывается
   на месте.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

import { can, registerModule } from '../app.js';
import { $, $$, api, closeModal, confirmDialog, dateRu, downloadBlob, getCookie, loadGenerationFor, loading, openModal, toast } from '../core.js';
import { html, mount, nothing, render } from '../ui/html.js';
import { checkField, fieldRow, optionView, selectField, textInput } from '../ui/form.js';
import { renderPreview, staysBindGatedFoot } from './stays_forms.js';
import { settingsHeadView, settingsPanelView } from './settings.js';
import { staysAddDays, staysToday } from './stays.js';

registerModule({ screens: { stays_fund: { render: renderStaysFund, icon: 'home' } } });

const FUND_STATUS = { draft: 'черновик', future: 'будущая', current: 'действует', archive: 'архив' };
const FUND_ENTITY = { unit: 'объект', group: 'узел', category: 'категория' };
const FUND_TABS = [['units', 'Объекты'], ['flags', 'Флаги объектов'], ['cats', 'Категории'], ['kinds', 'Виды']];
/* что открыто на экране: view — 'current' | 'draft' | id версии; node — узел дерева */
export const fundUI = { view: null, node: null, tab: 'units', picked: new Set(), rev: null, host: null, data: null, drag: null };

/* ─────────────── данные ─────────────── */
function fundVersionStatus(v, versions, today) {
  if (v.status === 'draft') return 'draft';
  if (v.valid_from > today) return 'future';
  const cur = versions.filter(x => x.status === 'published' && x.valid_from <= today).slice(-1)[0];
  return cur && cur.id === v.id ? 'current' : 'archive';
}

async function fundLoad() {
  const versions = await api('/api/stays/fund/versions', { silent: true });
  const draft = versions.find(v => v.status === 'draft') || null;
  if ((fundUI.view === 'draft' && !draft) || (typeof fundUI.view === 'number' && !versions.some(v => v.id === fundUI.view))) {
    fundUI.view = null;
  }
  if (fundUI.view == null) fundUI.view = draft ? 'draft' : 'current';
  const query = fundUI.view === 'current' ? 'date=' + staysToday()
    : 'version_id=' + (fundUI.view === 'draft' ? draft.id : fundUI.view);
  const [dicts, snap, draftSnap, diff] = await Promise.all([
    api('/api/stays/fund', { silent: true }),
    api('/api/stays/fund/snapshot?' + query, { silent: true }),
    /* rev черновика нужен плашке (публикация, дата), даже когда на экране другая версия */
    draft && fundUI.view !== 'draft' ? api('/api/stays/fund/snapshot?version_id=' + draft.id, { silent: true }) : null,
    draft ? api('/api/stays/fund/draft/diff', { silent: true }) : null,
  ]);
  return { versions, draft, dicts, snap, draftSnap: draftSnap || (draft ? snap : null), diff };
}

/* запись черновика: всегда с rev; ответ несёт новый rev */
async function fundWrite(method, url, body = {}) {
  try {
    const r = method === 'DELETE'
      ? await api(`${url}${url.includes('?') ? '&' : '?'}rev=${fundUI.rev}`, { method })
      : await api(url, { method, body: { ...body, rev: fundUI.rev } });
    if (r && r.rev != null) fundUI.rev = r.rev;
    return r;
  } catch (e) {
    if (/изменён другим пользователем/.test(e.message)) {
      closeModal();
      toast('Черновик изменил другой пользователь', 'err');
      e.handled = true;
      fundRerender();
    }
    throw e;
  }
}
function fundFail(e) { if (!e.handled) toast(e.message, 'err'); }
function fundRerender() { if (fundUI.host) renderStaysFund(fundUI.host); }

/* форма-модалка экрана: save(m) пишет; после записи — закрыть и onSaved */
function fundForm(title, body, save, onSaved, mountForm) {
  openModal({
    title, body,
    footer: html`<button class="btn btn-ghost" data-close @click=${closeModal}>Отмена</button><button class="btn btn-primary" data-save>Сохранить</button>`,
    onMount(m) {
      $('[data-save]', m).onclick = async () => {
        try { await save(m); closeModal(); if (onSaved) onSaved(); } catch (e) { fundFail(e); }
      };
      if (mountForm) mountForm(m);
    },
  });
}

/* ─────────────── подписи ─────────────── */
function fundGroupTitle(snapshot, gid) {
  const g = snapshot.groups.find(x => x.id === gid);
  if (!g) return '';
  const byId = Object.fromEntries(snapshot.groups.map(x => [x.id, x.title]));
  return g.path.map(id => byId[id] || '').join(' / ');
}
function fundGroupOptions(snapshot, exclude = null) {
  /* exclude — узел и его потомки (родителем узла их выбрать нельзя: цикл) */
  return [['', '— без узла'], ...snapshot.groups
    .filter(g => exclude == null || !g.path.includes(exclude))
    .map(g => [g.id, fundGroupTitle(snapshot, g.id)])
    .sort((a, b) => a[1].localeCompare(b[1], 'ru'))];
}
const fundKindTitle = (snapshot, id) => (snapshot.kinds || []).find(k => k.id === id)?.title || `#${id}`;
const fundCatOptions = snapshot => snapshot.categories.map(c => [c.id, `${c.code} · ${c.title}`]);
const fundId = id => html`<small class="muted">${`#${id}`}</small>`;
const fundSwatch = f => html`<span class="stays-swatch" style=${`background:${f.color}`} title=${f.title}></span>`;
const fundNum = v => (v === '' || v == null ? null : Number(v));
/* список вариантов [значение, подпись] для select с обработчиком */
const fundOptions = (options, value) => options.map(([v, t]) => optionView(v, t, value));

/* что изменилось в черновике — строками для плашки и предпросмотра */
function fundDiffLines(diff, snapshot) {
  if (!diff) return [];
  const cat = id => snapshot.categories.find(c => c.id === id)?.code || `#${id}`;
  const grp = id => (id == null ? 'без узла' : fundGroupTitle(snapshot, id) || `#${id}`);
  const unitLabel = id => snapshot.units.find(u => u.id === id)?.label || `#${id}`;
  const flagTitle = id => snapshot.flags.find(f => f.id === id)?.title || `#${id}`;
  const kind = id => fundKindTitle(snapshot, id);
  const show = { category_id: cat, group_id: grp, parent_id: grp, kind_id: kind };
  const names = { label: 'обозначение', category_id: 'категория', group_id: 'узел', floor: 'этаж', code: 'код',
    title: 'название', kind_id: 'вид', weight: 'вес', escorted: 'сопровождение', sort_order: 'порядок', parent_id: 'родитель' };
  const fields = e => Object.keys(e.after).filter(k => JSON.stringify(e.before[k]) !== JSON.stringify(e.after[k]))
    .map(k => `${names[k] || k}: ${(show[k] || String)(e.before[k])} → ${(show[k] || String)(e.after[k])}`).join(', ');
  const line = (what, name, e, female) => {
    if (e.kind === 'added') return `${what} ${name} — ${female ? 'новая' : 'новый'}${e.from?.length ? ` из ${e.from.join(', ')}` : ''}`;
    if (e.kind === 'retired') return `${what} ${name} — ${female ? 'выведена' : 'выведен'}`;
    return `${what} ${name}: ${fields(e)}`;
  };
  return [
    ...diff.units.map(e => line('Объект', (e.after.label || e.before.label), e)),
    ...diff.categories.map(e => line('Категория', (e.after.code || e.before.code), e, true)),
    ...diff.groups.map(e => line('Узел', (e.after.title || e.before.title), e)),
    ...diff.flags.map(e => {
      const on = e.after.flags.filter(f => !e.before.flags.includes(f)).map(f => '+' + flagTitle(f));
      const off = e.before.flags.filter(f => !e.after.flags.includes(f)).map(f => '−' + flagTitle(f));
      return `Флаги объекта ${unitLabel(e.id)}: ${[...on, ...off].join(', ')}`;
    }),
  ];
}

/* ─────────────── дерево ─────────────── */
/* перетаскивание: событие dragover/dragleave/drop для узла или щели; act(id) — что сделать с
   перетащенным узлом. Вне черновика (editable = false) не делает ничего. */
function fundDropEvents(editable, act, rerender) {
  return {
    over: e => { if (editable && fundUI.drag != null) { e.preventDefault(); e.currentTarget.classList.add('drop'); } },
    leave: e => e.currentTarget.classList.remove('drop'),
    drop: async e => {
      if (!editable) return;
      e.preventDefault();
      e.currentTarget.classList.remove('drop');
      const id = fundUI.drag;
      fundUI.drag = null;
      if (id == null) return;
      try { await act(id); toast('Дерево изменено'); rerender(); } catch (err) { fundFail(err); if (!err.handled) rerender(); }
    },
  };
}

/* editable — черновик: узлы перетаскиваются; на узел — стать его подузлом, в щель между
   соседями — встать на это место (data-fund-gap: родитель, data-fund-before: перед кем) */
function staysFundTree(snapshot, selectedId, editable, rerender) {
  const kids = {};
  snapshot.groups.forEach(g => { (kids[g.parent_id ?? 'root'] ||= []).push(g); });
  const count = id => snapshot.units.filter(u => u.path.includes(id)).length;
  const node = (id, title, n, depth, escorted = false) => {
    const target = id ?? null;
    const draggable = editable && id != null;
    const ev = fundDropEvents(editable, drag => (drag === target ? Promise.resolve() : fundMoveGroup(snapshot, drag, target, undefined)), rerender);
    return html`<button class=${`fund-node${target === (selectedId ?? null) ? ' active' : ''}`}
      data-fund-node=${id ?? ''} draggable=${draggable ? 'true' : nothing} style=${`padding-left:${8 + depth * 14}px`}
      @click=${() => { fundUI.node = target; fundUI.picked.clear(); rerender(); }}
      @dragstart=${e => {
        if (!draggable) return;
        fundUI.drag = id;
        if (e.dataTransfer) { e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', String(id)); }
      }}
      @dragend=${() => { fundUI.drag = null; }}
      @dragover=${ev.over} @dragleave=${ev.leave} @drop=${ev.drop}>${title} <small class="muted">${n}</small>${escorted
      ? html` <span class="badge ok" title="с сопровождением">с сопровождением</span>` : nothing}</button>`;
  };
  const gap = (pid, before, depth) => {
    if (!editable) return nothing;
    const parent = pid === 'root' ? null : pid;
    const ev = fundDropEvents(editable, drag => fundMoveGroup(snapshot, drag, parent, before ?? null), rerender);
    return html`<div class="fund-gap" data-fund-gap=${pid === 'root' ? '' : pid} data-fund-before=${before ?? ''}
      style=${`margin-left:${8 + depth * 14}px`} @dragover=${ev.over} @dragleave=${ev.leave} @drop=${ev.drop}></div>`;
  };
  const walk = (pid, depth) => [
    ...(kids[pid] || []).map(g => html`${gap(pid, g.id, depth)}${node(g.id, g.title, count(g.id), depth, g.escorted)}${walk(g.id, depth + 1)}`),
    (kids[pid] || []).length ? gap(pid, null, depth) : nothing,
  ];
  return html`<div class="fund-tree">${node(null, 'Весь фонд', snapshot.units.length, 0)}${walk('root', 0)}</div>`;
}

/* перенос узла перетаскиванием: parent — новый родитель (null — корень), before — перед каким
   узлом встать (null — в конец). Порядок соседей пересчитывается шагом 10; пишутся только
   изменившиеся узлы, каждый — записью черновика с rev. Цикл отклонит сервер (422 → тост). */
async function fundMoveGroup(snapshot, id, parent, before) {
  const g = snapshot.groups.find(x => x.id === id);
  if (!g || id === before) return;
  const siblings = snapshot.groups.filter(x => (x.parent_id ?? null) === parent && x.id !== id);
  const at = before == null ? siblings.length : Math.max(0, siblings.findIndex(x => x.id === before));
  const order = before === undefined ? null : [...siblings.slice(0, at), g, ...siblings.slice(at)];
  const writes = [];
  if (order) {
    order.forEach((x, i) => {
      const sort = (i + 1) * 10;
      if (x.id === id || x.sort_order !== sort) writes.push({ g: x, parent: x.id === id ? parent : x.parent_id ?? null, sort });
    });
  } else {
    const last = siblings.reduce((m, x) => Math.max(m, x.sort_order), 0);
    writes.push({ g, parent, sort: last + 10 });
  }
  /* сначала сам узел: если сервер отклонит (цикл), соседей не трогаем */
  writes.sort((a, b) => (b.g.id === id) - (a.g.id === id));
  for (const w of writes) {
    await fundWrite('PUT', `/api/stays/fund/draft/groups/${w.g.id}`, { title: w.g.title, parent_id: w.parent, sort_order: w.sort });
  }
}

/* ─────────────── экран ─────────────── */
export async function renderStaysFund(host) {
  fundUI.host = host;
  const fresh = loadGenerationFor(host);          // переключение версий подряд: запоздавший ответ не рисуем
  const data = await fundLoad();
  if (!fresh()) return;
  fundUI.data = data;
  const { versions, draft, snap, diff } = data;
  const editing = fundUI.view === 'draft';
  if (draft) fundUI.rev = data.draftSnap.version.rev;
  if (fundUI.node != null && !snap.groups.some(g => g.id === fundUI.node)) fundUI.node = null;
  const today = staysToday();
  const rerender = () => renderStaysFund(host);
  const status = v => FUND_STATUS[fundVersionStatus(v, versions, today)];
  const viewOpts = [['current', 'Действующая версия'], ...(draft ? [['draft', `Черновик с ${dateRu(draft.valid_from)}`]] : []),
    ...versions.filter(v => v.status === 'published').map(v => [`v:${v.id}`, `Версия с ${dateRu(v.valid_from)} · ${status(v)}`])];
  const viewValue = typeof fundUI.view === 'number' ? `v:${fundUI.view}` : fundUI.view;
  const lines = fundDiffLines(diff, data.draftSnap);
  const tabs = { units: fundUnitsTab, flags: fundFlagsTab, cats: fundCatsTab, kinds: fundKindsTab };

  const onView = e => {
    const v = e.target.value;
    fundUI.view = v.startsWith('v:') ? Number(v.slice(2)) : v;
    fundUI.picked.clear();
    rerender();
  };
  const openVersion = id => { fundUI.view = draft && draft.id === id ? 'draft' : id; rerender(); };
  const deleteVersion = v => (v && v.status === 'published' ? openFundVersionDelete(v, rerender)
    : confirmDialog('Удалить версию фонда?', 'Удалить можно черновик и версию, чья дата ещё не наступила.', async () => {
      try { await api(`/api/stays/fund/versions/${v.id}`, { method: 'DELETE' }); toast('Версия удалена'); fundUI.view = null; rerender(); }
      catch (e) { toast(e.message, 'err'); }
    }, 'Удалить'));
  const exportFund = () => {
    const v = typeof fundUI.view === 'number' ? versions.find(x => x.id === fundUI.view) : null;
    const day = v ? v.valid_from : staysToday();
    downloadBlob(`/api/stays/fund/export?date=${day}`, `fund-${day}.xlsx`);
  };
  const toggleProd = e => {
    const prod = e.target;
    const on = prod.checked;
    prod.checked = !on;                         // до подтверждения — прежнее положение
    confirmDialog(on ? 'Шахматка в эксплуатации?' : 'Снять «в эксплуатации»?',
      on ? 'Начальная загрузка («заменить всё») станет недоступна. Снять отметку может только администратор.'
        : 'Снова станет доступна начальная загрузка, которая удаляет все брони, гостей и фонд.',
      async () => {
        try {
          await api('/api/stays/fund/in-production', { method: 'PUT', body: { value: on } });
          toast(on ? 'Шахматка в эксплуатации' : 'Отметка «в эксплуатации» снята');
          rerender();
        } catch (err) { toast(err.message, 'err'); }
      }, on ? 'Включить' : 'Снять', !on);
  };
  const newDraft = () => fundForm('Изменить фонд с даты',
    html`${fieldRow('С даты', textInput('fd-date', staysAddDays(staysToday(), 1), 'date'))}${fieldRow('Примечание', textInput('fd-note'))}`,
    async m => {
      await api('/api/stays/fund/draft', { method: 'POST', body: { valid_from: $('#fd-date', m).value, note: $('#fd-note', m).value } });
      toast('Черновик открыт');
      fundUI.view = 'draft';
    }, rerender);
  const draftDate = () => fundForm('Дата черновика',
    fieldRow('С даты', textInput('fd-date', draft.valid_from, 'date')),
    async m => { await fundWrite('PATCH', '/api/stays/fund/draft', { valid_from: $('#fd-date', m).value }); toast('Дата черновика изменена'); },
    rerender);
  const deleteDraft = () => confirmDialog('Удалить черновик фонда?', 'Все изменения черновика пропадут.', async () => {
    try { await api(`/api/stays/fund/versions/${draft.id}`, { method: 'DELETE' }); toast('Черновик удалён'); fundUI.view = null; rerender(); }
    catch (e) { toast(e.message, 'err'); }
  }, 'Удалить');
  const retireNode = () => confirmDialog('Вывести узел из фонда?', 'Нельзя, пока в узле есть объекты или подузлы.', async () => {
    try { await fundWrite('DELETE', `/api/stays/fund/draft/groups/${fundUI.node}`); fundUI.node = null; toast('Узел выведен'); rerender(); }
    catch (e) { fundFail(e); }
  }, 'Вывести');

  render(html`
    ${settingsHeadView('Фонд и категории', 'Категории, дерево узлов, объекты и их флаги — версиями с даты. Менять фонд можно черновиком «с даты».',
    html`<label class="field fund-view"><span>Фонд на дату</span><select id="fund-view" @change=${onView}>${fundOptions(viewOpts, viewValue)}</select></label>
      <button class="btn btn-sm" id="fund-flags-dict" @click=${openFundFlagsDict}>Флаги объектов (справочник)</button>
      ${draft ? nothing : html`<button class="btn btn-sm btn-primary" id="fund-new-draft" @click=${newDraft}>Изменить с даты…</button>`}
      <button class="btn btn-sm" id="fund-export" @click=${exportFund}>Выгрузить фонд</button>
      <button class="btn btn-sm" id="fund-upload" @click=${() => openFundUpload(data, rerender)}>Загрузить фонд</button>
      ${can('stays.reset') ? html`<label class="chk"><input id="fund-in-prod" type="checkbox" .checked=${!!data.dicts.in_production} @change=${toggleProd}> Шахматка в эксплуатации</label>` : nothing}`)}
    ${draft ? html`<div class="dict-banner gold fund-draft-bar" id="fund-draft-bar"><span>✎</span>
      <div class="fund-draft-text">Черновик фонда с <b>${dateRu(draft.valid_from)}</b> · изменений: ${lines.length}
        ${lines.length ? html`<details><summary>список изменений</summary><ul>${lines.map(l => html`<li>${l}</li>`)}</ul></details>` : nothing}</div>
      <div class="fund-draft-actions">
        ${editing ? nothing : html`<button class="btn btn-sm" id="fund-draft-open" @click=${() => { fundUI.view = 'draft'; rerender(); }}>Открыть черновик</button>`}
        <button class="btn btn-sm btn-ghost" id="fund-draft-date" @click=${draftDate}>Сменить дату…</button>
        <button class="btn btn-sm" id="fund-preview" @click=${() => openFundPublish(rerender)}>Предпросмотр</button>
        <button class="btn btn-sm btn-primary" id="fund-publish" @click=${() => openFundPublish(rerender)}>Опубликовать</button>
        <button class="btn btn-sm btn-ghost" id="fund-draft-del" @click=${deleteDraft}>Удалить</button></div></div>`
    : html`<div class="dict-banner"><span>ℹ</span><span>Фонд только показывается; чтобы изменить его — «Изменить с даты…»</span></div>`}
    <div class="fund-layout">
      <div class="panel fund-side"><h3 class="panel-title">Дерево ${editing
        ? html`<button class="btn btn-sm btn-ghost" id="fund-node-add" title="Новый узел внутри выбранного" @click=${() => openFundGroupForm(null, snap, rerender)}>+</button>` : nothing}</h3>
        ${staysFundTree(snap, fundUI.node, editing, rerender)}
        ${editing ? html`<p class="hint">Перетащите узел на другой — станет его подузлом; между узлами — сменит порядок.</p>` : nothing}
        ${editing && fundUI.node != null ? html`<div class="sb-line fund-node-actions">
          <button class="btn btn-sm btn-ghost" id="fund-node-edit" @click=${() => openFundGroupForm(snap.groups.find(g => g.id === fundUI.node), snap, rerender)}>Изменить узел</button>
          <button class="btn btn-sm btn-ghost" id="fund-node-retire" @click=${retireNode}>Вывести узел</button></div>` : nothing}</div>
      <div class="fund-main">
        <div class="layer-tabs">${FUND_TABS.map(([id, t]) =>
          html`<button class=${`btn btn-sm${fundUI.tab === id ? ' btn-primary' : ''}`} data-fund-tab=${id} @click=${() => { fundUI.tab = id; rerender(); }}>${t}</button>`)}</div>
        <div id="fund-tab-body">${tabs[fundUI.tab](data, editing, rerender)}</div>
      </div>
    </div>
    ${settingsPanelView('История версий', html`<div class="table-wrap" id="fund-history"><table class="data">
      <thead><tr><th>С даты</th><th>Статус</th><th>Автор</th><th>Примечание</th><th></th></tr></thead>
      <tbody>${versions.slice().reverse().map(v => {
        const st = fundVersionStatus(v, versions, today);
        return html`<tr data-fund-ver=${v.id}><td><b>${dateRu(v.valid_from)}</b> ${fundId(v.id)}</td>
          <td><span class=${`badge ${st === 'current' ? 'ok' : st === 'archive' ? 'muted' : 'warn'}`}>${FUND_STATUS[st]}</span></td>
          <td>${v.author || '—'}</td><td>${v.note || ''}</td>
          <td class="num"><button class="btn btn-sm btn-ghost" data-fund-open=${v.id} @click=${() => openVersion(v.id)}>Открыть</button>
            ${st === 'draft' || st === 'future' ? html`<button class="btn btn-sm btn-ghost" data-fund-vdel=${v.id} @click=${() => deleteVersion(v)}>Удалить</button>` : nothing}</td></tr>`;
      })}</tbody></table></div>`)}`,
  mount(host));
  /* переключатель — по значению, а не по атрибуту selected: пользователь мог выбрать другой пункт */
  const sel = $('#fund-view', host);
  if (sel) sel.value = viewValue;
}

/* объекты выбранного узла (и всех его подузлов); в черновике — и выведенные из него */
function fundScopeUnits(data, editing) {
  const { snap, diff } = data;
  const inNode = path => fundUI.node == null || path.includes(fundUI.node);
  const units = snap.units.filter(u => inNode(u.path));
  if (!editing || !diff) return units;
  const pathOf = gid => snap.groups.find(g => g.id === gid)?.path || [];
  const gone = diff.units.filter(e => e.kind === 'retired')
    .map(e => ({ id: e.id, ...e.before, path: pathOf(e.before.group_id), retired: true }))
    .filter(u => inNode(u.path));
  return [...units, ...gone];
}
function fundUnitMarks(data) {
  const marks = {};
  if (!data.diff) return marks;
  data.diff.flags.forEach(e => { marks[e.id] = { kind: 'changed' }; });
  data.diff.units.forEach(e => { marks[e.id] = e; });
  return marks;
}
/* пометка черновика: e — запись diff ({kind, from}); female — «новая / выведена / изменена» */
function fundMark(e, since, female = false) {
  if (!e) return nothing;
  const [added, retired, changed] = female ? ['новая', 'выведена', 'изменена'] : ['новый', 'выведен', 'изменён'];
  const from = e.from?.length ? ` · из ${e.from.join(', ')}` : '';
  if (e.kind === 'added') return html`<span class="badge info">с ${since} · ${added}${from}</span>`;
  if (e.kind === 'retired') return html`<span class="badge muted">${retired} с ${since}</span>`;
  if (e.kind === 'changed') return html`<span class="badge warn">с ${since} · ${changed}</span>`;
  return nothing;
}

function fundUnitsTab(data, editing, rerender) {
  const { snap } = data;
  const cats = Object.fromEntries(snap.categories.map(c => [c.id, c.code]));
  const flags = Object.fromEntries(snap.flags.map(f => [f.id, f]));
  const units = fundScopeUnits(data, editing);
  const marks = editing ? fundUnitMarks(data) : {};
  const since = data.draft ? dateRu(data.draft.valid_from).slice(0, 5) : '';
  const picked = units.filter(u => fundUI.picked.has(u.id)).length;
  const unitOf = id => snap.units.find(u => u.id === id);
  const pick = (e, id) => { (e.target.checked ? fundUI.picked.add(id) : fundUI.picked.delete(id)); rerender(); };
  const retire = u => confirmDialog(`Вывести объект ${u.label || ''}?`, 'Объект уйдёт из фонда с даты черновика.', async () => {
    try { await fundWrite('DELETE', `/api/stays/fund/draft/units/${u.id}`); toast('Объект выведен'); rerender(); }
    catch (e) { fundFail(e); }
  }, 'Вывести');
  return html`${editing ? html`<div class="sb-toolbar">
      <button class="btn btn-sm btn-primary" id="fund-unit-add" @click=${() => openFundUnitForm(null, snap, rerender)}>+ Объект</button>
      <button class="btn btn-sm" id="fund-merge" ?disabled=${picked < 2}
        @click=${() => openFundMergeForm([...fundUI.picked].filter(id => unitOf(id)), snap, rerender)}>Объединить (${picked})</button>
      <button class="btn btn-sm" id="fund-move" ?disabled=${picked < 1}
        @click=${() => fundMoveForm([...fundUI.picked].map(unitOf).filter(Boolean), snap, rerender)}>Сменить узел…</button></div>` : nothing}
    <div class="table-wrap" style="max-height:520px"><table class="data">
      <thead><tr>${editing ? html`<th></th>` : nothing}<th>Объект</th><th>Категория</th><th>Узел</th><th>Этаж</th><th>Флаги</th><th></th></tr></thead>
      <tbody>${units.length ? units.map(u => html`<tr data-fund-unit=${u.id} class=${u.retired ? 'fund-retired' : ''}>
        ${editing ? html`<td>${u.retired ? nothing : html`<input type="checkbox" data-fund-pick=${u.id} .checked=${fundUI.picked.has(u.id)} @change=${e => pick(e, u.id)}>`}</td>` : nothing}
        <td><b>${u.label}</b> ${fundId(u.id)} ${fundMark(marks[u.id], since)}</td>
        <td>${cats[u.category_id] || '—'}</td>
        <td title=${fundGroupTitle(snap, u.group_id)}>${snap.groups.find(g => g.id === u.group_id)?.title || '—'}</td><td>${u.floor || ''}</td>
        <td>${(u.flags || []).map(id => (flags[id] ? html`${fundSwatch(flags[id])} ` : nothing))}</td>
        <td class="num fund-acts">${editing && !u.retired ? html`<button class="btn btn-sm btn-ghost" data-fund-edit=${u.id} @click=${() => openFundUnitForm(u, snap, rerender)}>Изменить</button>
          <button class="btn btn-sm btn-ghost" data-fund-relabel=${u.id} @click=${() => fundRelabelForm(u, rerender)}>Сменить номер</button>
          <button class="btn btn-sm btn-ghost" data-fund-split=${u.id} @click=${() => openFundSplitForm(u, snap, rerender)}>Разделить</button>
          <button class="btn btn-sm btn-ghost" data-fund-retire=${u.id} @click=${() => retire(u)}>Вывести</button>` : nothing}</td>
      </tr>`) : html`<tr><td colspan=${editing ? 7 : 6} class="empty">Объектов в узле нет</td></tr>`}</tbody></table></div>`;
}

function fundFlagsTab(data, editing, rerender) {
  const { snap } = data;
  const units = fundScopeUnits(data, false);
  const flags = snap.flags.filter(f => !f.archived);
  if (!flags.length) return html`<div class="empty">Флагов нет — добавьте их в справочнике</div>`;
  /* флаг: одна галочка или все объекты узла; при отказе сервера галочка возвращается */
  const setFlag = async (cb, flagId, unitIds) => {
    const value = cb.checked;
    try { await fundWrite('PUT', '/api/stays/fund/draft/flags', { flag_id: flagId, unit_ids: unitIds, value }); rerender(); }
    catch (e) { cb.checked = !value; fundFail(e); }
  };
  return html`<p class="hint">${editing ? '«Все в узле» отмечает флаг у всех объектов выбранного узла.' : 'Только просмотр — менять флаги можно в черновике.'}</p>
    <div class="table-wrap" style="max-height:520px"><table class="data">
      <thead><tr><th>Объект</th>${flags.map(f => html`<th>${fundSwatch(f)} ${f.title}${editing
        ? html`<br><label class="chk"><input type="checkbox" data-fund-flag-all=${f.id} .checked=${!!units.length && units.every(u => u.flags.includes(f.id))}
          @change=${e => setFlag(e.target, f.id, units.map(u => u.id))}> все в узле</label>` : nothing}</th>`)}</tr></thead>
      <tbody>${units.length ? units.map(u => html`<tr><td><b>${u.label}</b> ${fundId(u.id)}</td>${flags.map(f =>
        html`<td><input type="checkbox" data-fund-flag=${f.id} data-unit=${u.id} .checked=${u.flags.includes(f.id)} ?disabled=${!editing}
          @change=${e => setFlag(e.target, f.id, [u.id])}></td>`)}</tr>`)
        : html`<tr><td colspan=${flags.length + 1} class="empty">Объектов в узле нет</td></tr>`}</tbody></table></div>`;
}

function fundCatsTab(data, editing, rerender) {
  const { snap } = data;
  const marks = {};
  if (editing && data.diff) data.diff.categories.forEach(e => { marks[e.id] = e; });
  const since = data.draft ? dateRu(data.draft.valid_from).slice(0, 5) : '';
  const retire = c => confirmDialog('Вывести категорию?', 'Нельзя, пока в черновике есть её объекты.', async () => {
    try { await fundWrite('DELETE', `/api/stays/fund/draft/categories/${c.id}`); toast('Категория выведена'); rerender(); }
    catch (e) { fundFail(e); }
  }, 'Вывести');
  return html`${editing ? html`<div class="sb-toolbar"><button class="btn btn-sm btn-primary" id="fund-cat-add" @click=${() => fundCategoryForm(null, data, rerender)}>+ Категория</button></div>` : nothing}
    <div class="table-wrap"><table class="data">
      <thead><tr><th>Код</th><th>Название</th><th>Вид</th><th>Сопровождение</th><th class="num">Вес</th><th class="num">Объектов</th><th></th></tr></thead>
      <tbody>${snap.categories.length ? snap.categories.map(c => html`<tr data-fund-cat=${c.id}>
        <td><b>${c.code}</b> ${fundId(c.id)} ${fundMark(marks[c.id], since, true)}</td>
        <td>${c.title}</td><td>${fundKindTitle(snap, c.kind_id)}</td>
        <td>${c.escorted ? html`<span class="badge ok">с сопровождением</span>` : html`<span class="muted">нет</span>`}</td>
        <td class="num">${String(c.weight)}</td><td class="num">${snap.units.filter(u => u.category_id === c.id).length}</td>
        <td class="num">${editing ? html`<button class="btn btn-sm btn-ghost" data-fund-cat-edit=${c.id} @click=${() => fundCategoryForm(c, data, rerender)}>Изменить</button>
          <button class="btn btn-sm btn-ghost" data-fund-cat-retire=${c.id} @click=${() => retire(c)}>Вывести</button>` : nothing}</td></tr>`)
        : html`<tr><td colspan="7" class="empty">Категорий пока нет</td></tr>`}</tbody></table></div>`;
}

/* справочник видов — вне черновика, правится сразу (права stays.setup — у самого экрана) */
function fundKindsTab(data, _editing, rerender) {
  const { snap } = data;
  const used = new Set(snap.categories.map(c => c.kind_id));
  const archive = async k => {
    try { await api(`/api/stays/fund/kinds/${k.id}/archive`, { method: 'PUT', body: { archived: !k.archived } }); rerender(); }
    catch (e) { toast(e.message, 'err'); }
  };
  const remove = k => confirmDialog('Удалить вид?', 'Вид, который стоит у категории, удалить нельзя — только в архив.', async () => {
    try { await api(`/api/stays/fund/kinds/${k.id}`, { method: 'DELETE' }); toast('Вид удалён'); rerender(); }
    catch (e) { toast(e.message, 'err'); }
  }, 'Удалить');
  const kinds = snap.kinds || [];
  return html`<p class="hint">Справочник правится сразу, без черновика. «Раскрывать» — раздел дерева шахматки с категорией
      этого вида открыт по умолчанию. Использованный вид удалить нельзя — только в архив.</p>
    <div class="sb-toolbar"><button class="btn btn-sm btn-primary" id="fund-kind-add" @click=${() => fundKindForm(null, rerender)}>+ Вид</button></div>
    <div class="table-wrap"><table class="data">
      <thead><tr><th>Название</th><th class="num">Порядок</th><th>Раскрывать</th><th></th></tr></thead>
      <tbody>${kinds.length ? kinds.map(k => html`<tr data-fund-kind=${k.id} class=${k.archived ? 'fund-retired' : ''}>
        <td><b>${k.title}</b> ${fundId(k.id)}${k.archived ? html` <span class="badge muted">архив</span>` : nothing}${used.has(k.id) ? nothing : html` <span class="muted">не используется</span>`}</td>
        <td class="num">${String(k.sort_order)}</td><td>${k.expanded ? 'да' : html`<span class="muted">нет</span>`}</td>
        <td class="num"><button class="btn btn-sm btn-ghost" data-fund-kind-edit=${k.id} @click=${() => fundKindForm(k, rerender)}>Изменить</button>
          <button class="btn btn-sm btn-ghost" data-fund-kind-arch=${k.id} @click=${() => archive(k)}>${k.archived ? 'Из архива' : 'В архив'}</button>
          <button class="btn btn-sm btn-ghost" data-fund-kind-del=${k.id} @click=${() => remove(k)}>Удалить</button></td></tr>`)
        : html`<tr><td colspan="4" class="empty">Видов пока нет</td></tr>`}</tbody></table></div>`;
}

function fundKindForm(kind, onSaved) {
  fundForm(kind ? `Вид «${kind.title}»` : 'Новый вид', html`
    ${fieldRow('Название', textInput('fk-title', kind?.title))}
    ${fieldRow('Порядок', textInput('fk-sort', kind?.sort_order ?? 100, 'number'))}
    ${checkField('fk-expanded', 'Раскрывать раздел на шахматке', kind?.expanded)}`,
  async m => {
    const body = { title: $('#fk-title', m).value, sort_order: Number($('#fk-sort', m).value), expanded: $('#fk-expanded', m).checked };
    await api(kind ? `/api/stays/fund/kinds/${kind.id}` : '/api/stays/fund/kinds', { method: kind ? 'PUT' : 'POST', body });
    toast('Вид сохранён');
  }, onSaved);
}

/* ─────────────── формы черновика ─────────────── */
function fundUnitBody(u) {
  return { label: u.label, category_id: u.category_id, group_id: u.group_id, floor: u.floor || '', flags: u.flags || [] };
}

function openFundUnitForm(unit, snapshot, onSaved) {
  const flags = snapshot.flags.filter(f => !f.archived || unit?.flags.includes(f.id));
  fundForm(unit ? `Объект ${unit.label}` : 'Новый объект', html`
    <div class="grid-2">
      ${fieldRow('Обозначение', textInput('fu-label', unit?.label))}
      ${fieldRow('Категория', selectField('fu-cat', fundCatOptions(snapshot), unit?.category_id))}
      ${fieldRow('Узел', selectField('fu-group', fundGroupOptions(snapshot), unit ? unit.group_id ?? '' : fundUI.node ?? ''))}
      ${fieldRow('Этаж', textInput('fu-floor', unit?.floor))}
    </div>
    <div class="check-list">${flags.map(f => html`<label class="chk"><input type="checkbox" data-fu-flag=${f.id} .checked=${!!unit?.flags.includes(f.id)}>
      ${fundSwatch(f)} ${f.title}</label>`)}</div>`,
  async m => {
    const body = { label: $('#fu-label', m).value, category_id: Number($('#fu-cat', m).value),
      group_id: fundNum($('#fu-group', m).value), floor: $('#fu-floor', m).value,
      flags: $$('[data-fu-flag]', m).filter(cb => cb.checked).map(cb => Number(cb.dataset.fuFlag)) };
    await fundWrite(unit ? 'PUT' : 'POST', unit ? `/api/stays/fund/draft/units/${unit.id}` : '/api/stays/fund/draft/units', body);
    toast('Объект сохранён');
  }, onSaved);
}

function fundRelabelForm(unit, onSaved) {
  fundForm(`Сменить номер ${unit.label}`, fieldRow('Новое обозначение', textInput('fu-label', unit.label)), async m => {
    await fundWrite('PUT', `/api/stays/fund/draft/units/${unit.id}`, { ...fundUnitBody(unit), label: $('#fu-label', m).value });
    toast('Номер изменён');
  }, onSaved);
}

function fundMoveForm(units, snapshot, onSaved) {
  fundForm(`Сменить узел: ${units.length} объект.`, fieldRow('Новый узел', selectField('fu-group', fundGroupOptions(snapshot), fundUI.node ?? '')), async m => {
    const gid = fundNum($('#fu-group', m).value);
    for (const u of units) await fundWrite('PUT', `/api/stays/fund/draft/units/${u.id}`, { ...fundUnitBody(u), group_id: gid });
    fundUI.picked.clear();
    toast('Узел изменён');
  }, onSaved);
}

/* деление: N новых объектов; по умолчанию категория, узел и этаж исходного (флаги сервер наследует) */
function openFundSplitForm(unit, snapshot, onSaved) {
  const parts = [1, 2].map(n => ({ label: `${unit.label}-${n}`, category_id: unit.category_id, group_id: unit.group_id, floor: unit.floor || '' }));
  const draw = m => {
    const set = (i, key, cast = v => v) => e => { parts[i][key] = cast(e.target.value); };
    render(html`${parts.map((p, i) => html`<div class="fund-part">
      <div class="fund-part-head">Часть ${i + 1}${parts.length > 2
        ? html` <button class="btn btn-sm btn-ghost" data-sp-del=${i} @click=${() => { parts.splice(i, 1); draw(m); }}>×</button>` : nothing}</div>
      ${fieldRow('Обозначение', html`<input data-sp-label=${i} .value=${p.label} @input=${set(i, 'label')} @change=${set(i, 'label')}>`)}
      ${fieldRow('Этаж', html`<input data-sp-floor=${i} .value=${p.floor} @input=${set(i, 'floor')} @change=${set(i, 'floor')}>`)}
      ${fieldRow('Категория', html`<select id=${`sp-cat-${i}`} data-sp-cat=${i} @change=${set(i, 'category_id', Number)}>${fundOptions(fundCatOptions(snapshot), p.category_id)}</select>`)}
      ${fieldRow('Узел', html`<select id=${`sp-group-${i}`} data-sp-group=${i} @change=${set(i, 'group_id', fundNum)}>${fundOptions(fundGroupOptions(snapshot), p.group_id ?? '')}</select>`)}
    </div>`)}`, mount($('#sp-parts', m)));
  };
  fundForm(`Разделить ${unit.label}`, html`<p class="hint">Объект выводится из фонда с даты черновика, вместо него — новые.</p>
    <div id="sp-parts"></div><button class="btn btn-sm btn-ghost" id="sp-add">+ Часть</button>`,
  async () => {
    const r = await fundWrite('POST', `/api/stays/fund/draft/units/${unit.id}/split`, { parts });
    toast(`Разделено на ${r.ids.length}`);
  }, onSaved, m => {
    draw(m);
    $('#sp-add', m).onclick = () => { parts.push({ ...parts[parts.length - 1], label: `${unit.label}-${parts.length + 1}` }); draw(m); };
  });
}

/* объединение: у выбранных разные узел или категория — пользователь выбирает сам */
function openFundMergeForm(unitIds, snapshot, onSaved) {
  const units = unitIds.map(id => snapshot.units.find(u => u.id === id)).filter(Boolean);
  if (units.length < 2) { toast('Отметьте хотя бы два объекта', 'err'); return; }
  const same = key => units.every(u => u[key] === units[0][key]);
  const ask = [!same('category_id') && 'категория', !same('group_id') && 'узел'].filter(Boolean);
  fundForm(`Объединить ${units.map(u => u.label).join(' + ')}`, html`
    ${ask.length ? html`<div class="dict-banner gold"><span>⚠</span><span>У выбранных разные: ${ask.join(', ')} — выберите для нового объекта</span></div>` : nothing}
    <div class="grid-2">
      ${fieldRow('Обозначение', textInput('fm-label', units.map(u => u.label).join('')))}
      ${fieldRow('Категория', selectField('fm-cat', fundCatOptions(snapshot), units[0].category_id))}
      ${fieldRow('Узел', selectField('fm-group', fundGroupOptions(snapshot), units[0].group_id ?? ''))}
      ${fieldRow('Этаж', textInput('fm-floor', units[0].floor))}
    </div>`,
  async m => {
    await fundWrite('POST', '/api/stays/fund/draft/units/merge', { unit_ids: units.map(u => u.id), label: $('#fm-label', m).value,
      category_id: Number($('#fm-cat', m).value), group_id: fundNum($('#fm-group', m).value), floor: $('#fm-floor', m).value });
    fundUI.picked.clear();
    toast('Объекты объединены');
  }, onSaved);
}

function openFundGroupForm(group, snapshot, onSaved) {
  const parent = group ? group.parent_id : fundUI.node;
  fundForm(group ? `Узел «${group.title}»` : 'Новый узел', html`
    ${fieldRow('Название', textInput('fg-title', group?.title))}
    ${fieldRow('Родитель', selectField('fg-parent', fundGroupOptions(snapshot, group?.id ?? null).map(([v, t]) => [v, v === '' ? '— корень дерева' : t]), parent ?? ''))}
    ${fieldRow('Порядок', textInput('fg-sort', group?.sort_order ?? 100, 'number'))}
    ${checkField('fg-escorted', 'С сопровождением батлером (и вся ветка узла)', group?.escorted)}`,
  async m => {
    const body = { title: $('#fg-title', m).value, parent_id: fundNum($('#fg-parent', m).value), sort_order: Number($('#fg-sort', m).value),
      escorted: $('#fg-escorted', m).checked };
    await fundWrite(group ? 'PUT' : 'POST', group ? `/api/stays/fund/draft/groups/${group.id}` : '/api/stays/fund/draft/groups', body);
    toast('Узел сохранён');
  }, onSaved);
}

/* виды для формы категории: архивный — только тот, что уже стоит у этой категории */
function fundKindOptions(snapshot, cat) {
  const kinds = (snapshot.kinds || []).filter(k => !k.archived || k.id === cat?.kind_id);
  return [...(cat ? [] : [['', '— выберите вид']]), ...kinds.map(k => [k.id, k.archived ? `${k.title} (архив)` : k.title])];
}

function fundCategoryForm(cat, data, onSaved) {
  const noKinds = !(data.snap.kinds || []).some(k => !k.archived || k.id === cat?.kind_id);
  fundForm(cat ? `Категория ${cat.code}` : 'Новая категория', html`
    <div class="grid-2">
      ${fieldRow('Код', textInput('fc-code', cat?.code))}
      ${fieldRow('Название', textInput('fc-title', cat?.title))}
      ${fieldRow('Вид', selectField('fc-kind', fundKindOptions(data.snap, cat), cat?.kind_id ?? ''))}
      ${fieldRow('Вес нагрузки', textInput('fc-weight', cat?.weight ?? 1, 'number'))}
      ${fieldRow('Порядок', textInput('fc-sort', cat?.sort_order ?? 100, 'number'))}
    </div>
    ${noKinds ? html`<p class="hint">Сначала заведите вид на вкладке «Виды».</p>` : nothing}
    ${checkField('fc-escorted', 'С сопровождением батлером', cat?.escorted)}`,
  async m => {
    const body = { code: $('#fc-code', m).value, title: $('#fc-title', m).value, kind_id: fundNum($('#fc-kind', m).value),
      weight: Number($('#fc-weight', m).value), sort_order: Number($('#fc-sort', m).value), escorted: $('#fc-escorted', m).checked };
    await fundWrite(cat ? 'PUT' : 'POST', cat ? `/api/stays/fund/draft/categories/${cat.id}` : '/api/stays/fund/draft/categories', body);
    toast('Категория сохранена');
  }, onSaved);
}

/* ─────────────── предпросмотр и публикация (§4.3–§4.4) ─────────────── */
function fundPropagationLines(result) {
  const name = x => `${FUND_ENTITY[x.entity] || x.entity} ${x.name ?? '#' + x.id}${x.field ? ` (${x.field})` : ''}`;
  const at = x => `в версии с ${dateRu(x.valid_from)}`;
  return [
    ...result.propagated.map(x => html`<li>${at(x)}: ${name(x)} — перенесено</li>`),
    ...result.kept.map(x => html`<li>${at(x)}: ${name(x)} — оставлено её значение${x.reason ? ` (${x.reason})` : ''}</li>`),
    ...result.skipped.map(x => html`<li class="sp-warn">${at(x)}: ${name(x)} — не перенесено: ${x.reason}</li>`),
  ];
}

async function openFundPublish(onDone) {
  const { versions, draft, draftSnap } = fundUI.data;
  if (!draft) return;
  const later = versions.filter(v => v.status === 'published' && v.valid_from > draft.valid_from);
  /* брони без объекта и в категории без объектов — кандидаты на перевод; список копится
     между проверками: переведённая бронь из предупреждений уходит, но галочка остаётся */
  const candidates = new Map();
  const picks = {};
  const body = m => ({ propagate: later.length ? $('#fp-propagate', m).checked : true,
    transfers: Object.entries(picks).filter(([, p]) => p.on).map(([rid, p]) => ({ reservation_id: Number(rid), category_id: p.category_id })) });
  const draw = (m, r) => {
    const res = r.result;
    (res.affected.unassigned || []).concat(res.affected.category_missing || [])
      .filter(w => w.reservation_id != null).forEach(w => { if (!candidates.has(w.reservation_id)) candidates.set(w.reservation_id, w.text); });
    const lines = fundDiffLines(res.fund_diff && res.fund_diff.units ? res.fund_diff : null, draftSnap);
    const prop = fundPropagationLines(res);
    const opts = fundCatOptions(draftSnap);
    render(html`
      <div class="sp-head">Фонд с ${dateRu(draft.valid_from)}</div>
      ${lines.length ? html`<ul>${lines.map(l => html`<li>${l}</li>`)}</ul>` : html`<div class="muted">Фонд не меняется</div>`}
      ${prop.length ? html`<div class="sp-head">Поздние версии</div><ul>${prop}</ul>` : nothing}
      <div id="fp-alloc"></div>
      ${candidates.size ? html`<div class="sp-head">Перевести брони без объекта на категорию</div>${[...candidates].map(([rid, t]) => {
        const p = picks[rid] || (picks[rid] = { on: false, category_id: opts[0]?.[0] });
        return html`<div class="sb-line"><label class="chk"><input type="checkbox" data-fp-transfer=${rid} .checked=${p.on}
            @change=${e => { p.on = e.target.checked; }}> ${t}</label>
          → <select id=${`fp-cat-${rid}`} data-fp-transfer-cat=${rid} @change=${e => { p.category_id = Number(e.target.value); }}>${fundOptions(opts, p.category_id)}</select></div>`;
      })}<p class="hint">Перевод входит в публикацию; «Проверить» покажет размещение с переводом.</p>` : nothing}`, mount($('#fp-out', m)));
    renderPreview(r.diff, $('#fp-alloc', m), r.overbook_refused);
  };
  const check = async m => {
    try { draw(m, await fundWrite('POST', '/api/stays/fund/draft/publish?preview=1', body(m))); } catch (e) { fundFail(e); }
  };
  openModal({
    title: `Публикация фонда с ${dateRu(draft.valid_from)}`, wide: true,
    body: html`${later.length ? html`<label class="chk"><input id="fp-propagate" type="checkbox" checked
        @change=${e => check(e.target.closest('.modal'))}> Применить к поздним версиям (с ${later.map(v => dateRu(v.valid_from)).join(', ')})</label>` : nothing}
      <div id="fp-out" class="sp-out"><div class="muted">Проверяем…</div></div>`,
    footer: html`<button class="btn btn-ghost" data-close @click=${closeModal}>Отмена</button><button class="btn" id="fp-check">Проверить</button>
      <button class="btn btn-primary" id="fp-publish">Опубликовать</button>`,
    onMount(m) {
      $('#fp-check', m).onclick = () => check(m);
      $('#fp-publish', m).onclick = async () => {
        try {
          const r = await fundWrite('POST', '/api/stays/fund/draft/publish', body(m));
          closeModal();
          const moved = r.result.transfers.length;
          toast(`Фонд опубликован с ${dateRu(r.result.version.valid_from)}${moved ? ` · переведено броней: ${moved}` : ''}`);
          fundUI.view = null;
          if (onDone) onDone();
        } catch (e) { fundFail(e); }
      };
      check(m);
    },
  });
}

/* Удаление будущей опубликованной версии перераспределяет брони — как публикация: сначала
   предпросмотр (что изменится), «Удалить» недоступно, пока появляется овербукинг без права
   «Овербукинг» (сервер ответит 409 с тем же текстом) */
function openFundVersionDelete(v, onDone) {
  const url = `/api/stays/fund/versions/${v.id}`;
  const out = m => mount($('#fvd-out', m));
  openModal({
    title: `Удалить версию фонда с ${dateRu(v.valid_from)}`, wide: true,
    body: html`<p class="hint">Брони с этой даты распределятся по фонду предыдущей версии.</p><div id="fvd-out" class="sp-out"><div class="muted">Проверяем…</div></div>`,
    footer: html`<button class="btn btn-ghost" data-close>Отмена</button>
      <button class="btn" id="rf-preview">Проверить</button><button class="btn btn-primary" data-save>Удалить</button>`,
    onMount(m) {
      const flow = {
        async preview() {
          const r = await api(`${url}?preview=1`, { method: 'DELETE' });
          renderPreview(r.diff, out(m), r.overbook_refused);
          return r;
        },
        save: () => api(url, { method: 'DELETE' }),
      };
      staysBindGatedFoot(m, flow, { okText: 'Версия удалена', out: () => out(m),
        onSaved: () => { fundUI.view = null; if (onDone) onDone(); } });
      $('#rf-preview', m).click();
    },
  });
}

/* ─────────────── файл фонда (§9) ─────────────── */
/* multipart-запрос: api() шлёт только JSON. Ошибки файла — 422 {errors: [{sheet, row, message}]} */
async function fundPostFile(url, fields) {
  const fd = new FormData();
  Object.entries(fields).forEach(([k, v]) => fd.append(k, v));
  loading(true);
  try {
    const res = await fetch(url, { method: 'POST', credentials: 'same-origin', body: fd,
      headers: { 'X-CSRF-Token': getCookie('tt_csrf') } });
    const d = await res.json().catch(() => ({}));
    if (!res.ok) {
      const e = new Error(typeof d.detail === 'string' ? d.detail : d.errors ? 'В файле есть ошибки' : `Ошибка ${res.status}`);
      e.status = res.status;
      e.errors = d.errors || null;
      throw e;
    }
    return d;
  } finally { loading(false); }
}

const FUND_RESET_COUNTS = [['units', 'объектов'], ['reservations', 'броней'], ['guests', 'гостей'],
  ['coverage', 'назначений батлеров'], ['ooo', 'OOO'], ['blocks', 'блоков'], ['versions', 'версий фонда'],
  ['categories', 'категорий'], ['groups', 'узлов'], ['flags', 'флагов']];
const FUND_LOAD_COUNTS = [['categories', 'категорий'], ['groups', 'узлов'], ['flags', 'флагов'], ['units', 'объектов']];

function fundFileErrors(e) {
  if (!e.errors) return html`<div class="sp-warn">${e.message}</div>`;
  return html`<div class="sp-head">Файл не загружен — ошибки:</div><ul>${e.errors.map(x =>
    html`<li class="sp-warn">${x.sheet || 'файл'}${x.row ? `, строка ${x.row}` : ''}: ${x.message}</li>`)}</ul>`;
}

/* «Загрузить фонд»: черновиком с даты (stays.setup) или начальной загрузкой (stays.reset).
   Начальная загрузка: «Проверить» — предпросмотр и отпечаток; «Заменить всё» — только со словом
   ЗАМЕНИТЬ; после замены копия прежних данных сразу скачивается. */
function openFundUpload(data, onDone) {
  const resetOk = can('stays.reset') && !data.dicts.in_production;
  const modes = [['draft', 'Черновиком с даты'], ...(resetOk ? [['reset', 'Начальная загрузка (заменить всё)']] : [])];
  let checked = null;                              // предпросмотр замены для выбранного файла
  openModal({
    title: 'Загрузить фонд', subtitle: 'Файл — как «Выгрузить фонд»: листы «Категории», «Дерево», «Флаги», «Объекты»', wide: true,
    body: html`${fieldRow('Режим', selectField('fu-mode', modes, 'draft'))}
      <div id="fu-draft">${data.draft
        ? html`<div class="dict-banner gold"><span>✎</span><span>Черновик с ${dateRu(data.draft.valid_from)} уже есть — откройте или удалите его, черновик один</span></div>`
        : fieldRow('С даты', textInput('fu-date', staysAddDays(staysToday(), 1), 'date'))}</div>
      <div id="fu-reset" hidden><div class="dict-banner gold"><span>⚠</span><span>Все брони, гости, назначения батлеров,
        OOO и блоки и все версии фонда будут удалены; фонд — из файла. Метки, настраиваемые поля, сопровождение,
        надбавки и лимит остаются. Перед заменой сохраняется копия.</span></div></div>
      ${fieldRow('Файл Excel', html`<input id="fu-file" type="file" accept=".xlsx">`)}
      <div id="fu-out" class="sp-out"></div>`,
    footer: html`<button class="btn btn-ghost" data-close @click=${closeModal}>Отмена</button>
      <button class="btn btn-primary" id="fu-go">Загрузить</button>`,
    onMount(m) {
      const mode = () => $('#fu-mode', m).value;
      const file = () => $('#fu-file', m).files?.[0] || null;
      const out = () => mount($('#fu-out', m));
      const go = $('#fu-go', m);
      const sync = () => {
        const reset = mode() === 'reset';
        $('#fu-draft', m).hidden = reset;
        $('#fu-reset', m).hidden = !reset;
        go.textContent = reset ? (checked ? 'Заменить всё' : 'Проверить') : 'Загрузить';
        go.className = `btn ${reset && checked ? 'btn-danger' : 'btn-primary'}`;
        go.disabled = reset ? !!checked && $('#fu-word', m)?.value !== 'ЗАМЕНИТЬ' : !!data.draft;
      };
      const drop = () => { checked = null; render(nothing, out()); sync(); };
      $('#fu-mode', m).onchange = drop;
      $('#fu-file', m).onchange = drop;
      const preview = async () => {
        const p = await fundPostFile('/api/stays/fund/reset?preview=1', { file: file() });
        checked = p;
        const list = (pairs, counts) => pairs.map(([k, t]) => `${counts[k] ?? 0} ${t}`).join(', ');
        render(html`<div class="sp-head">Будет удалено</div><div>${list(FUND_RESET_COUNTS, p.counts)}</div>
          <div class="sp-head">Будет загружено</div><div>${list(FUND_LOAD_COUNTS, p.will_load)}</div>
          ${p.warnings.map(w => html`<div class="sp-warn">${w}</div>`)}
          ${fieldRow('Для замены введите слово ЗАМЕНИТЬ', textInput('fu-word'))}`, out());
        $('#fu-word', m).oninput = sync;
        sync();
      };
      const replace = async () => {
        const r = await fundPostFile('/api/stays/fund/reset', { file: file(), confirm: $('#fu-word', m).value, fingerprint: checked.fingerprint });
        closeModal();
        toast(`Фонд заменён: объектов ${r.loaded.units} · копия ${r.backup}`);
        downloadBlob(r.backup_url, r.backup);
        fundUI.view = null;
        if (onDone) onDone();
      };
      const draft = async () => {
        const r = await fundPostFile('/api/stays/fund/import', { file: file(), valid_from: $('#fu-date', m).value });
        closeModal();
        const n = ['units', 'categories', 'groups', 'flags'].reduce((s, k) => s + (r.diff[k]?.length || 0), 0);
        toast(`Черновик с ${dateRu(r.valid_from)} · изменений: ${n}${r.retired.length ? ` · будут выведены: ${r.retired.length}` : ''}`);
        fundUI.view = 'draft';
        if (onDone) onDone();
      };
      go.onclick = async () => {
        if (!file()) { toast('Выберите файл', 'err'); return; }
        try {
          if (mode() === 'draft') await draft();
          else if (checked) await replace();
          else await preview();
        } catch (e) {
          if (e.status === 409 && checked) checked = null;      // данные изменились — проверить заново
          render(fundFileErrors(e), out());
          sync();
        }
      };
      sync();
    },
  });
}

/* ─────────────── справочник флагов (вне черновика, сразу) ─────────────── */
function openFundFlagsDict() {
  const flags = fundUI.data.snap.flags;
  /* после правки — свежий снимок экрана, затем справочник заново */
  const reopen = async () => { await renderStaysFund(fundUI.host); openFundFlagsDict(); };
  const form = f => fundForm(f ? `Флаг «${f.title}»` : 'Новый флаг',
    html`${fieldRow('Название', textInput('ff-title', f?.title))}${fieldRow('Цвет', textInput('ff-color', f?.color || '#3b6fd8', 'color'))}
      ${fieldRow('Порядок', textInput('ff-sort', f?.sort_order ?? 100, 'number'))}`,
    async fm => {
      const body = { title: $('#ff-title', fm).value, color: $('#ff-color', fm).value, sort_order: Number($('#ff-sort', fm).value) };
      await api(f ? `/api/stays/fund/flags/${f.id}` : '/api/stays/fund/flags', { method: f ? 'PUT' : 'POST', body });
      toast('Флаг сохранён');
    }, reopen);
  const archive = async f => {
    try { await api(`/api/stays/fund/flags/${f.id}/archive`, { method: 'PUT', body: { archived: !f.archived } }); closeModal(); reopen(); }
    catch (e) { toast(e.message, 'err'); }
  };
  const remove = async f => {
    try { await api(`/api/stays/fund/flags/${f.id}`, { method: 'DELETE' }); toast('Флаг удалён'); closeModal(); reopen(); }
    catch (e) { toast(e.message, 'err'); }
  };
  openModal({
    title: 'Флаги объектов', subtitle: 'Справочник правится сразу, без черновика; использованный флаг — только в архив',
    body: html`<div class="check-list">${flags.length ? flags.map(f => html`<div class="rule-row" style="grid-template-columns:1fr auto">
        <div class="lbl">${fundSwatch(f)} ${f.title} ${fundId(f.id)}${f.archived ? html` <span class="badge muted">архив</span>` : nothing}</div>
        <div style="display:flex;gap:6px"><button class="btn btn-sm btn-ghost" data-ff-edit=${f.id} @click=${() => form(f)}>Изменить</button>
          <button class="btn btn-sm btn-ghost" data-ff-arch=${f.id} @click=${() => archive(f)}>${f.archived ? 'Из архива' : 'В архив'}</button>
          <button class="btn btn-sm btn-ghost" data-ff-del=${f.id} @click=${() => remove(f)}>Удалить</button></div></div>`)
      : html`<div class="empty">Флагов пока нет</div>`}</div>`,
    footer: html`<button class="btn btn-ghost" data-close @click=${closeModal}>Закрыть</button><button class="btn btn-primary" id="ff-add" @click=${() => form(null)}>+ Флаг</button>`,
  });
}

/* ── мост к общей области имён (генерируется tools/gen_js_globals.py; уйдёт вместе с переходом файла на import/export) ── */
Object.assign(globalThis, {
  fundUI,
  renderStaysFund,
});
/* ── конец моста ── */
