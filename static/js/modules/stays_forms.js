/* ══════════════════════════════════════════════════════════════════════
   «ШАХМАТКА» — формы изменения с предпросмотром «что будет, если» (§4.6):
   кнопка «Проверить» отправляет то же тело с ?preview=1 и показывает, куда встанет
   бронь, какие чужие брони сдвинутся и какие предупреждения появятся или исчезнут;
   «Сохранить» отправляет то же тело без preview.
   Использует хелперы app.js: $ $$ esc api openModal closeModal toast dateRu.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

const STAYS_ROLE = { main: 'главный', guest: 'проживает' };
const STAYS_STATUS = { tentative: 'предварительная', confirmed: 'подтверждена', in_house: 'заселён',
  checked_out: 'выехал', cancelled: 'отменена', no_show: 'не заехал' };

const STAYS_COMPANION = { security: 'охрана', driver: 'водитель', nanny: 'няня', pet: 'животное', other: 'другое' };
/* кем выбранный гость приходится открытому; семейные связи — только «родитель» (parent) и «супруг»
   (spouse, former — бывшие): их подписи нужны предпросмотру объединения, правятся они в дереве
   (stays_family.js), остальное родство вычисляет сервер (§4) */
const STAYS_LINK = { spouse: 'супруг(а)', spouse_former: 'бывший(ая) супруг(а)', parent: 'ребёнок',
  relative: 'родственник', assistant: 'ассистент', security: 'охрана', driver: 'водитель', nanny: 'няня',
  colleague: 'коллега', other: 'другое' };
const STAYS_GENDER = { '': 'не указан', m: 'мужской', f: 'женский' };
/* семейные связи правятся в дереве (stays_family.js); в «Прочих связях» карточки — остальные виды */
const STAYS_FAMILY_LINK = new Set(['spouse', 'spouse_former', 'parent']);

/* родственники среди проживающих (§4): «мать — Петрова М.» */
function staysRelativesHtml(rel) {
  return rel?.length ? `<div class="muted">${rel.map(x => `${esc(x.title)} — ${esc(x.name)}`).join(', ')}</div>` : '';
}

/* настраиваемые поля (§3.5): элемент ввода по типу поля; attr — data-атрибут с кодом */
function staysFieldInputs(defs, values, attr) {
  return defs.map(f => {
    const v = values?.[f.code];
    let control;
    if (f.kind === 'choice') {
      control = `<select ${attr}="${esc(f.code)}"><option value="">—</option>${f.choices.map(c =>
        `<option value="${esc(c)}"${c === v ? ' selected' : ''}>${esc(c)}</option>`).join('')}</select>`;
    } else if (f.kind === 'bool') {
      control = `<input type="checkbox" ${attr}="${esc(f.code)}"${v ? ' checked' : ''}>`;
    } else {
      control = `<input type="${f.kind === 'date' ? 'date' : 'text'}" ${attr}="${esc(f.code)}" value="${esc(String(v ?? ''))}">`;
    }
    return sfRow(f.title, control);
  }).join('');
}
function staysFieldValues(m, attr) {
  const out = {};
  $$(`[${attr}]`, m).forEach(el => {
    const v = el.type === 'checkbox' ? el.checked : el.value;
    if (v !== '') out[el.getAttribute(attr)] = v;
  });
  return out;
}

function renderPreview(diff, el, refused) {
  const items = [];
  // новый овербукинг без права «Овербукинг»: сохранение будет отклонено (409)
  if (refused) items.push(`<li class="sp-warn"><b>Не сохранится:</b> ${esc(refused)}</li>`);
  (diff.moved || []).forEach(m => {
    const who = m.new ? 'Новая бронь' : `Бронь ${m.number || '#' + m.reservation_id}`;
    // seg_index — сегмент; since — дата части сегмента за границей версии фонда
    const seg = (m.seg_index ? ` (сегмент ${m.seg_index + 1})` : '') + (m.since ? ` с ${dateRu(m.since)}` : '');
    items.push(`<li>${esc(who)}${esc(seg)}: ${esc(m.from_label || 'без объекта')} → <b>${esc(m.to_label || 'без объекта')}</b></li>`);
  });
  (diff.warnings_added || []).forEach(w => items.push(`<li class="sp-warn">⚠ ${esc(w.text)}</li>`));
  (diff.warnings_removed || []).forEach(w => items.push(`<li class="sp-ok">✓ снято: ${esc(w.text)}</li>`));
  (diff.coverage_changes || []).forEach(c => items.push(`<li>${esc(dateRu(c.day))} · ${esc(c.employee || '')}: ${c.gained?.length ? `+${esc(c.gained.join(', '))}` : ''} ${c.lost?.length ? `−${esc(c.lost.join(', '))}` : ''}</li>`));
  (diff.load_changes || []).forEach(c => items.push(`<li class="${c.after > c.limit ? 'sp-warn' : ''}">${esc(dateRu(c.day))} · ${esc(c.employee || '')}: нагрузка ${esc(String(c.before))} → ${esc(String(c.after))} из ${esc(String(c.limit))}</li>`));
  el.innerHTML = `<div class="sp-head">Что изменится</div>${items.length ? `<ul>${items.join('')}</ul>`
    : '<div class="muted">Размещение и предупреждения не меняются</div>'}`;
}

/* одна точка для всех форм: preview → картина; save → то же тело без preview */
function previewThenSave({ url, method, body, out }) {
  return {
    async preview() {
      const r = await api(`${url}${url.includes('?') ? '&' : '?'}preview=1`, { method, body: body() });
      renderPreview(r.diff, out(), r.overbook_refused);
      return r;
    },
    async save() { return api(url, { method, body: body() }); },
  };
}

function staysFormFoot() {
  return `<button class="btn btn-ghost" data-close>Отмена</button>
    <button class="btn" id="rf-preview">Проверить</button><button class="btn btn-primary" data-save>Сохранить</button>`;
}
function staysBindFoot(m, flow, onSaved, okText) {
  $('[data-close]', m).onclick = closeModal;
  $('#rf-preview', m).onclick = async () => { try { await flow.preview(); } catch (e) { toast(e.message, 'err'); } };
  $('[data-save]', m).onclick = async () => {
    try { await flow.save(); closeModal(); toast(okText); if (onSaved) onSaved(); } catch (e) { toast(e.message, 'err'); }
  };
}

/* ─────────────── Бронь ─────────────── */
async function openReservationForm(id, opts = {}) {
  /* opts.mine — батлер дополняет свою бронь: даты, объект, категория, метка, заказчик и главный
     гость заперты (сервер всё равно проверяет, §7 stays.edit_mine) */
  const fund = await staysFund();
  const rFields = fund.fields.filter(f => f.target === 'reservation');
  const r = id ? await api(`/api/stays/reservations/${id}`) : null;
  const form = {
    occupants: (r?.occupants || []).map(o => ({ ...o })),
    moves: (r?.moves || []).map(mv => ({ ...mv })),
    logistics: (r?.logistics || []).map(l => ({ ...l })),
    companions: (r?.companions || []).map(c => ({ ...c })),
    pins: Object.fromEntries((r?.segments || []).filter(s => s.pinned).map(s => [s.index, s.unit_id])),
  };
  const opt = (v, t, cur) => `<option value="${esc(String(v ?? ''))}"${String(v ?? '') === String(cur ?? '') ? ' selected' : ''}>${esc(t)}</option>`;
  const catCode = cid => fund.categories.find(c => c.id === Number(cid))?.code || '?';
  /* категории фонда на дату заезда (§5); текущее значение, которого в фонде нет, остаётся выбранным —
     иначе браузер молча подставит первую категорию, и сохранение запишет ложный «апгрейд» */
  const catOptions = (cats, cur) => {
    const list = cur != null && cur !== '' && !cats.some(c => c.id === Number(cur))
      ? [...cats, { id: Number(cur), code: fund.categories.find(c => c.id === Number(cur))?.code || '#' + cur, title: 'нет в фонде на эту дату' }]
      : cats;
    return list.map(c => opt(c.id, `${c.code} · ${c.title}`, cur)).join('');
  };
  openModal({
    title: r ? `Бронь ${r.number || '#' + r.id}` : 'Новая бронь', wide: true,
    body: `
      <div class="grid-2">
        ${sfRow('Номер брони (Fidelio)', sfInput('rf-number', r?.number))}
        ${sfRow('Категория', `<select id="rf-category">${catOptions(fund.categories, r?.category_id)}</select>`)}
        ${sfRow('Заезд', sfInput('rf-check-in', r?.check_in, 'date'))}
        ${sfRow('Выезд', sfInput('rf-check-out', r?.check_out, 'date'))}
      </div>
      ${sfCheck('rf-early', 'Ранний заезд', r?.early)} ${sfCheck('rf-late', 'Поздний выезд', r?.late)}
      ${sfCheck('rf-declined', 'Гость отказался от батлера', r?.declined_butler)}
      <div class="grid-2">
        ${sfRow('Метка', `<select id="rf-label">${opt('', '—', r?.label_id)}${fund.labels.map(l => opt(l.id, l.title, r?.label_id)).join('')}</select>`)}
        ${sfRow('Заказчик', sfInput('rf-customer', r?.customer))}
        ${sfRow('Оплата за', `<select id="rf-paid">${catOptions(fund.categories, r?.paid_category_id ?? r?.category_id)}</select>`)}
      </div>
      ${sfRow('Примечание', `<textarea id="rf-note" rows="2">${esc(r?.note || '')}</textarea>`)}
      <h4>Гости</h4><div id="rf-occupants"></div>
      <div class="sb-toolbar"><input type="search" id="rf-guest-q" placeholder="Найти гостя: фамилия или телефон"></div>
      <div id="rf-guest-res"></div>
      <div class="sb-toolbar"><input id="rf-new-last" placeholder="Новый гость: фамилия">
        <select id="rf-new-level">${opt('regular', 'обычный')}${opt('vip', 'VIP')}${opt('vvip', 'VVIP')}</select>
        <button class="btn btn-sm" id="rf-new-add">+ Новый гость</button></div>
      <h4>Переезды</h4><div id="rf-moves"></div><button class="btn btn-sm btn-ghost" id="rf-move-add">+ Переезд</button>
      <h4>Объекты</h4><div id="rf-pins"></div>
      <div id="rf-linked-box"></div>
      <h4>Логистика</h4><div id="rf-logistics"></div><button class="btn btn-sm btn-ghost" id="rf-log-add">+ Рейс / трансфер / авто</button>
      <h4>Сопровождающие</h4><div id="rf-companions"></div><button class="btn btn-sm btn-ghost" id="rf-comp-add">+ Охрана / водитель / няня…</button>
      ${rFields.length ? `<h4>Дополнительно</h4><div class="grid-2">${staysFieldInputs(rFields, r?.fields, 'data-rf-field')}</div>` : ''}
      <div id="rf-preview-out" class="sp-out"></div>`,
    footer: staysFormFoot(),
    onMount(m) {
      const val = sel => $(sel, m).value;
      if (opts.mine) {
        ['#rf-number', '#rf-category', '#rf-check-in', '#rf-check-out', '#rf-early', '#rf-late', '#rf-declined',
          '#rf-label', '#rf-customer', '#rf-paid', '#rf-move-add', '#rf-new-add', '#rf-new-last']
          .forEach(sel => { const el = $(sel, m); if (el) el.disabled = true; });
        if (r) {
          $('#rf-category', m).innerHTML = `<option value="${r.category_id}">—</option>`;
          $('#rf-paid', m).innerHTML = `<option value="${r.paid_category_id ?? r.category_id}">—</option>`;
          $('#rf-label', m).innerHTML = `<option value="${r.label_id ?? ''}">—</option>`;
        }
      }
      const drawOcc = () => {
        $('#rf-occupants', m).innerHTML = form.occupants.map((o, i) => `<div class="sb-line">
          <b>${esc(o.name || '')}</b>
          <select data-occ-role="${i}">${opt('main', STAYS_ROLE.main, o.role)}${opt('guest', STAYS_ROLE.guest, o.role)}</select>
          <input type="date" data-occ-from="${i}" value="${esc(o.date_from || '')}"> –
          <input type="date" data-occ-to="${i}" value="${esc(o.date_to || '')}">
          <button class="btn btn-sm btn-ghost" data-occ-del="${i}">×</button></div>`).join('') || '<div class="muted">Гостей пока нет</div>';
        $$('[data-occ-role]', m).forEach(s => { s.onchange = () => { form.occupants[s.dataset.occRole].role = s.value; }; });
        $$('[data-occ-from]', m).forEach(s => { s.onchange = () => { form.occupants[s.dataset.occFrom].date_from = s.value; }; });
        $$('[data-occ-to]', m).forEach(s => { s.onchange = () => { form.occupants[s.dataset.occTo].date_to = s.value; }; });
        $$('[data-occ-del]', m).forEach(b => { b.onclick = () => { form.occupants.splice(Number(b.dataset.occDel), 1); drawOcc(); }; });
      };
      const addGuest = (gid, name) => {
        form.occupants.push({ guest_id: gid, name, role: form.occupants.some(o => o.role === 'main') ? 'guest' : 'main',
          date_from: val('#rf-check-in'), date_to: val('#rf-check-out') });
        drawOcc();
      };
      const drawMoves = () => {
        $('#rf-moves', m).innerHTML = form.moves.map((mv, i) => `<div class="sb-line">
          <input type="date" data-mv-date="${i}" value="${esc(mv.move_date || '')}">
          <select data-mv-cat="${i}">${fund.categories.map(c => opt(c.id, c.code, mv.category_id)).join('')}</select>
          <button class="btn btn-sm btn-ghost" data-mv-del="${i}">×</button></div>`).join('');
        $$('[data-mv-date]', m).forEach(s => { s.onchange = () => { form.moves[s.dataset.mvDate].move_date = s.value; }; });
        $$('[data-mv-cat]', m).forEach(s => { s.onchange = () => { form.moves[s.dataset.mvCat].category_id = Number(s.value); drawPins(); }; });
        $$('[data-mv-del]', m).forEach(b => { b.onclick = () => { form.moves.splice(Number(b.dataset.mvDel), 1); drawMoves(); drawPins(); }; });
      };
      const drawPins = () => {
        const cats = [Number(val('#rf-category')), ...form.moves.map(mv => mv.category_id)];
        $('#rf-pins', m).innerHTML = cats.map((cid, i) => `<div class="sb-line">Сегмент ${i + 1} (${esc(catCode(cid))}):
          <select id="rf-unit-${i}" data-pin="${i}">${opt('', 'Авто')}${fund.units.filter(u => u.category_id === cid && u.active)
            .map(u => opt(u.id, u.label, form.pins[i])).join('')}</select></div>`).join('');
        $$('[data-pin]', m).forEach(s => { s.onchange = () => { form.pins[s.dataset.pin] = s.value ? Number(s.value) : null; }; });
      };
      const drawLog = () => {
        $('#rf-logistics', m).innerHTML = form.logistics.map((l, i) => `<div class="sb-line">
          <select data-lg-kind="${i}">${opt('flight', 'рейс', l.kind)}${opt('transfer', 'трансфер', l.kind)}${opt('car', 'автомобиль', l.kind)}</select>
          <input type="date" data-lg-date="${i}" value="${esc(l.date || '')}"><input type="time" data-lg-time="${i}" value="${esc(l.time || '')}">
          <input data-lg-desc="${i}" value="${esc(l.description || '')}" placeholder="SU1234, Mercedes А123ВС…">
          <button class="btn btn-sm btn-ghost" data-lg-del="${i}">×</button></div>`).join('');
        [['kind', 'lgKind'], ['date', 'lgDate'], ['time', 'lgTime'], ['description', 'lgDesc']].forEach(([key, ds]) => {
          $$(`[data-lg-${ds.slice(2).toLowerCase()}]`, m).forEach(s => { s.onchange = () => { form.logistics[s.dataset[ds]][key] = s.value; }; });
        });
        $$('[data-lg-del]', m).forEach(b => { b.onclick = () => { form.logistics.splice(Number(b.dataset.lgDel), 1); drawLog(); }; });
      };
      const drawComp = () => {
        $('#rf-companions', m).innerHTML = form.companions.map((c, i) => `<div class="sb-line">
          <select data-cp-kind="${i}">${Object.entries(STAYS_COMPANION).map(([k, t]) => opt(k, t, c.kind)).join('')}</select>
          <input data-cp-desc="${i}" value="${esc(c.description || '')}" placeholder="Описание">
          <button class="btn btn-sm btn-ghost" data-cp-del="${i}">×</button></div>`).join('');
        $$('[data-cp-kind]', m).forEach(x => { x.onchange = () => { form.companions[x.dataset.cpKind].kind = x.value; }; });
        $$('[data-cp-desc]', m).forEach(x => { x.onchange = () => { form.companions[x.dataset.cpDesc].description = x.value; }; });
        $$('[data-cp-del]', m).forEach(b => { b.onclick = () => { form.companions.splice(Number(b.dataset.cpDel), 1); drawComp(); }; });
      };
      drawOcc(); drawMoves(); drawPins(); drawLog(); drawComp();
      $('#rf-comp-add', m).onclick = () => { form.companions.push({ kind: 'other', description: '' }); drawComp(); };

      /* даты брони меняются — гости «на весь срок» едут вместе с ними */
      let prev = { ci: val('#rf-check-in'), co: val('#rf-check-out') };
      const follow = () => {
        const ci = val('#rf-check-in'), co = val('#rf-check-out');
        form.occupants.forEach(o => {
          if (!o.date_from || o.date_from === prev.ci) o.date_from = ci;
          if (!o.date_to || o.date_to === prev.co) o.date_to = co;
        });
        prev = { ci, co }; drawOcc();
      };
      /* «Категория» и «Оплата за» — из фонда на дату заезда; пока даты нет — из фонда на сегодня */
      const snapCats = {};
      const reloadCats = async () => {
        const d = val('#rf-check-in');
        if (!/^\d{4}-\d\d-\d\d$/.test(d)) return;
        if (!snapCats[d]) {
          try { snapCats[d] = (await api('/api/stays/fund/snapshot?date=' + d, { silent: true })).categories; } catch (e) { return; }
        }
        if (val('#rf-check-in') !== d) return;            // дату успели сменить — этот ответ устарел
        const catSel = $('#rf-category', m), paidSel = $('#rf-paid', m);
        const [c, p] = [catSel.value, paidSel.value];
        catSel.innerHTML = catOptions(snapCats[d], c);
        paidSel.innerHTML = catOptions(snapCats[d], p);
      };
      $('#rf-check-in', m).onchange = () => { follow(); if (!opts.mine) reloadCats(); };
      if (r?.check_in && !opts.mine) reloadCats();
      $('#rf-check-out', m).onchange = follow;
      /* «оплата за» следует за категорией, пока её не выбрали отдельно */
      let paidTouched = !!r && (r.paid_category_id ?? r.category_id) !== r.category_id;
      $('#rf-paid', m).onchange = () => { paidTouched = true; };
      $('#rf-category', m).onchange = () => { if (!paidTouched) $('#rf-paid', m).value = val('#rf-category'); drawPins(); };
      $('#rf-move-add', m).onclick = () => { form.moves.push({ move_date: '', category_id: Number(val('#rf-category')) }); drawMoves(); drawPins(); };
      $('#rf-log-add', m).onclick = () => { form.logistics.push({ kind: 'transfer', date: val('#rf-check-in'), time: '', description: '' }); drawLog(); };
      let timer = null;
      $('#rf-guest-q', m).oninput = e => {
        clearTimeout(timer);
        timer = setTimeout(async () => {
          const q = e.target.value.trim();
          const found = q.length < 2 ? [] : await api('/api/stays/guests?q=' + encodeURIComponent(q), { silent: true });
          $('#rf-guest-res', m).innerHTML = found.map(g => `<button class="btn btn-sm btn-ghost" data-pick-guest="${g.id}" data-name="${esc(g.short)}">
            ${g.level !== 'regular' ? esc(STAYS_LEVEL_MARK[g.level]) : ''}${esc(g.last_name)} ${esc(g.first_name)} ${esc(g.middle_name)}</button>`).join('')
            || (q.length >= 2 ? '<span class="muted">не найдено</span>' : '');
          $$('[data-pick-guest]', m).forEach(b => { b.onclick = () => { addGuest(Number(b.dataset.pickGuest), b.dataset.name); $('#rf-guest-res', m).innerHTML = ''; }; });
        }, 300);
      };
      $('#rf-new-add', m).onclick = async () => {
        const last = val('#rf-new-last').trim();
        if (!last) { toast('Укажите фамилию гостя', 'err'); return; }
        try {
          const g = await api('/api/stays/guests', { method: 'POST', body: { last_name: last, level: val('#rf-new-level') } });
          addGuest(g.id, g.last_name); $('#rf-new-last', m).value = '';
        } catch (e) { toast(e.message, 'err'); }
      };
      const body = () => ({
        number: val('#rf-number'), category_id: Number(val('#rf-category')),
        check_in: val('#rf-check-in'), check_out: val('#rf-check-out'),
        early: $('#rf-early', m).checked, late: $('#rf-late', m).checked, declined_butler: $('#rf-declined', m).checked,
        label_id: opts.mine ? (r?.label_id ?? null) : (val('#rf-label') ? Number(val('#rf-label')) : null),
        customer: val('#rf-customer'), paid_category_id: Number(val('#rf-paid')), note: val('#rf-note'),
        group_id: r?.group_id ?? null, fields: { ...(r?.fields || {}), ...staysFieldValues(m, 'data-rf-field') },
        occupants: form.occupants.map(({ id: oid, guest_id, role, date_from, date_to }) => ({ id: oid, guest_id, role, date_from, date_to })),
        moves: form.moves.filter(mv => mv.move_date), logistics: form.logistics, companions: form.companions,
        pins: opts.mine ? null : Object.fromEntries([Number(val('#rf-category')), ...form.moves].map((_, i) => [i, form.pins[i] ?? null])),
        version: r?.version,
      });
      const flow = previewThenSave({ url: r ? `/api/stays/reservations/${r.id}` : '/api/stays/reservations',
        method: r ? 'PUT' : 'POST', body, out: () => $('#rf-preview-out', m) });
      staysBindFoot(m, flow, opts.onSaved, 'Бронь сохранена');
      /* связанных гостей батлера догружаем после привязки кнопок — иначе ранний клик «Сохранить» терялся */
      if (opts.mine) (async () => {
        /* батлер: вместо поиска по всем гостям — гости, связанные «кто кому» с проживающими брони */
        ['#rf-guest-q', '#rf-new-last', '#rf-new-level', '#rf-new-add'].forEach(sel => { $(sel, m).closest('.sb-toolbar').style.display = 'none'; });
        const have = new Set(form.occupants.map(o => o.guest_id));
        const cards = await Promise.all([...have].map(gid => api(`/api/stays/guests/${gid}`, { silent: true }).catch(() => null)));
        const linked = new Map();
        cards.filter(Boolean).forEach(c => c.links.forEach(l => { if (!have.has(l.guest_id)) linked.set(l.guest_id, l); }));
        $('#rf-linked-box', m).innerHTML = linked.size ? `<div class="sb-line"><select id="rf-linked">${[...linked.values()].map(l =>
          `<option value="${l.guest_id}">${esc(l.name)} · ${esc(l.label)}</option>`).join('')}</select>
          <button class="btn btn-sm" id="rf-linked-add">+ Добавить связанного гостя</button></div>` : '';
        const add = $('#rf-linked-add', m);
        if (add) add.onclick = () => { const l = linked.get(Number(val('#rf-linked'))); addGuest(l.guest_id, l.name); };
      })().catch(e => toast(e.message, 'err'));
    },
  });
}

/* ─────────────── «Перенести» сегмент брони в другой объект или категорию ─────────────── */
async function openTransferForm(rid, segIndex, onSaved) {
  const [fund, r] = await Promise.all([staysFund(), api(`/api/stays/reservations/${rid}`)]);
  const seg = r.segments[segIndex];
  const units = cid => fund.units.filter(u => u.category_id === Number(cid) && u.active);
  const unitOptions = cid => `<option value="">Авто</option>${units(cid).map(u =>
    `<option value="${u.id}"${u.id === seg.unit_id && seg.pinned ? ' selected' : ''}>${esc(u.label)}</option>`).join('')}`;
  openModal({
    title: `Перенести бронь ${r.number || '#' + r.id}`, subtitle: `${dateRu(seg.start)}–${dateRu(seg.end)}`,
    body: `${sfRow('Категория', `<select id="tf-cat">${fund.categories.map(c =>
        `<option value="${c.id}"${c.id === seg.category_id ? ' selected' : ''}>${esc(c.code)} · ${esc(c.title)}</option>`).join('')}</select>`)}
      ${sfRow('Объект', `<select id="tf-unit">${unitOptions(seg.category_id)}</select>`)}
      <div id="rf-preview-out" class="sp-out"></div>`,
    footer: staysFormFoot(),
    onMount(m) {
      $('#tf-cat', m).onchange = e => { $('#tf-unit', m).innerHTML = unitOptions(e.target.value); };
      const body = () => {
        const cat = Number($('#tf-cat', m).value);
        const moves = r.moves.map((mv, i) => (i === segIndex - 1 ? { ...mv, category_id: cat } : mv));
        return { ...r, category_id: segIndex === 0 ? cat : r.category_id, moves,
          occupants: r.occupants.map(({ id: oid, guest_id, role, date_from, date_to }) => ({ id: oid, guest_id, role, date_from, date_to })),
          pins: { [segIndex]: $('#tf-unit', m).value ? Number($('#tf-unit', m).value) : null } };
      };
      const flow = previewThenSave({ url: `/api/stays/reservations/${rid}`, method: 'PUT', body,
        out: () => $('#rf-preview-out', m) });
      staysBindFoot(m, flow, onSaved, 'Бронь перенесена');
    },
  });
}

/* ─────────────── Назначение батлеров: шаблон с предпросмотром дельты покрытия ─────────────── */
async function openCoverageForm(card, onSaved) {
  const fund = await staysFund(true);
  const escorts = fund.escorts.filter(e => e.active);
  const lastNight = staysAddDays(card.check_out, -1);
  const guests = [...new Map(card.occupants.map(o => [o.guest_id, o])).values()];
  const people = escorts.map(e => `<option value="${e.employee_id}">${esc(e.name)}</option>`).join('');
  openModal({
    title: `Батлеры брони ${card.number || '#' + card.id}`, wide: true,
    subtitle: 'Шаблон заполняет только пустые дни; ручные назначения остаются, пока не выбрано «заменить»',
    body: `<div class="grid-2">
        ${sfRow('Как назначить', `<select id="cf-kind"><option value="pair">пара посменно (по Графику)</option>
          <option value="single">один на весь срок</option><option value="manual">вручную по дням</option></select>`)}
        <div class="cf-tpl">${sfRow('Батлер A / X', `<select id="cf-b1">${people}</select>`)}</div>
        <div id="cf-b2-wrap">${sfRow('Батлер B', `<select id="cf-b2">${people}</select>`)}</div>
        <div class="cf-tpl">${sfRow('С', sfInput('cf-first', card.check_in, 'date'))}</div>
        <div class="cf-tpl">${sfRow('По (последняя ночь)', sfInput('cf-last', lastNight, 'date'))}</div>
      </div>
      <div id="cf-days" style="display:none">${card.coverage.map(d => {
        const cur = d.butlers.length === 1 ? d.butlers[0].employee_id : '';
        return `<div class="sb-line"><span style="width:90px">${esc(dateRu(d.day))}</span>
          <select data-cf-day="${esc(d.day)}" data-was="${cur}"><option value="">— нет</option>${escorts.map(e =>
            `<option value="${e.employee_id}"${e.employee_id === cur ? ' selected' : ''}>${esc(e.name)}</option>`).join('')}</select>
          ${d.butlers.length > 1 ? `<span class="muted">сейчас: ${esc(d.butlers.map(x => x.name).join(', '))}</span>` : ''}</div>`;
      }).join('')}</div>
      ${card.group_id ? sfCheck('cf-group', 'На всю группу совместного проживания', false) : ''}
      <div class="sb-line"><span class="muted">Только эти гости (пусто — все):</span>${guests.map(g =>
        `<label class="chk"><input type="checkbox" data-cf-guest="${g.guest_id}"> ${esc(g.guest)}</label>`).join('')}</div>
      ${sfCheck('cf-replace', 'Заменить уже назначенных', false)}
      <div class="sb-line"><button class="btn btn-sm btn-ghost" id="cf-cand">Подобрать на ${esc(dateRu(card.check_in))}</button><span id="cf-cand-out"></span></div>
      <div id="rf-preview-out" class="sp-out"></div>`,
    footer: staysFormFoot(),
    onMount(m) {
      const kind = $('#cf-kind', m);
      const sync = () => {
        const manual = kind.value === 'manual';
        $('#cf-b2-wrap', m).style.display = kind.value === 'pair' ? '' : 'none';
        $$('.cf-tpl', m).forEach(el => { el.style.display = manual ? 'none' : ''; });
        $('#cf-days', m).style.display = manual ? '' : 'none';
        $('#cf-replace', m).closest('label').style.display = manual ? 'none' : '';
      };
      kind.onchange = sync; sync();
      const scope = () => {
        const ids = $$('[data-cf-guest]', m).filter(c => c.checked).map(c => Number(c.dataset.cfGuest));
        const group = $('#cf-group', m)?.checked;
        return { reservation_id: group ? null : card.id, group_id: group ? card.group_id : null, guest_ids: ids };
      };
      $('#cf-cand', m).onclick = async () => {
        try {
          const sc = scope();
          const q = new URLSearchParams({ day: card.check_in, guest_ids: sc.guest_ids.join(',') });
          if (sc.group_id) q.set('group_id', sc.group_id); else q.set('reservation_id', sc.reservation_id);
          const got = await api('/api/stays/coverage/candidates?' + q);
          $('#cf-cand-out', m).innerHTML = got.map(c => `<button class="btn btn-sm btn-ghost" data-pick-emp="${c.employee_id}">
            ${esc(c.name)}${c.knows_guest ? ' · знает гостя' : ''} · ${esc(String(c.load_after))}</button>`).join('') || '<span class="muted">свободных на смене нет</span>';
          $$('[data-pick-emp]', m).forEach(b => { b.onclick = () => { $('#cf-b1', m).value = b.dataset.pickEmp; }; });
        } catch (e) { toast(e.message, 'err'); }
      };
      const out = () => $('#rf-preview-out', m);
      const template = previewThenSave({ url: '/api/stays/coverage/template', method: 'POST', out,
        body: () => ({ ...scope(), kind: kind.value, first: $('#cf-first', m).value, last: $('#cf-last', m).value,
          replace: $('#cf-replace', m).checked,
          butlers: kind.value === 'pair' ? [Number($('#cf-b1', m).value), Number($('#cf-b2', m).value)] : [Number($('#cf-b1', m).value)] }) });
      /* вручную: только изменённые дни, одной операцией с одним предпросмотром */
      const manual = previewThenSave({ url: '/api/stays/coverage/days', method: 'PUT', out,
        body: () => ({ ...scope(), days: $$('[data-cf-day]', m).filter(s => s.value !== s.dataset.was)
          .map(s => ({ day: s.dataset.cfDay, employee_id: s.value ? Number(s.value) : null })) }) });
      const flow = {
        preview: () => (kind.value === 'manual' ? manual : template).preview(),
        save: () => (kind.value === 'manual' ? manual : template).save(),
      };
      staysBindFoot(m, flow, onSaved, 'Батлеры назначены');
    },
  });
}

/* ─────────────── OOO (часть 2 §3.1, §7): создание, правка, удаление — с предпросмотром ─────────────── */
async function openHoldForm(hold, onSaved) {
  const fund = await staysFund();
  const isNew = !hold.id;
  const first = hold.start || staysToday();
  /* «с утра» (start_half = AM) и «до вечера» (end_half = PM) — сутки целиком; новое OOO — целые сутки */
  const wholeStart = isNew || hold.start_half === 'AM';
  const wholeEnd = isNew || hold.end_half === 'PM';
  openModal({
    title: isNew ? 'OOO — не в продаже' : `OOO · ${dateRu(hold.start)}–${dateRu(hold.end)}`,
    subtitle: 'Объект не в продаже: по умолчанию с вечера «с» до утра «по»; галочки — сутки целиком. Брони на эти дни перераспределятся. Блоки по категориям — на вкладке «Блоки»',
    body: `<div class="grid-2">
        ${sfRow('Объект', sfSelect('hf-unit', fund.units.filter(u => u.active).map(u => [u.id, u.label]), hold.unit_id))}
        <div></div>
        ${sfRow('С', sfInput('hf-start', first, 'date'))}
        ${sfRow('По', sfInput('hf-end', hold.end || first, 'date'))}
        ${sfCheck('hf-start-am', 'С утра', wholeStart)}
        ${sfCheck('hf-end-pm', 'До вечера', wholeEnd)}
      </div>
      ${sfRow('Причина', sfInput('hf-title', hold.title))}
      <div class="muted" data-hf-hint>без имён гостей — видно всем</div>
      <div id="rf-preview-out" class="sp-out"></div>`,
    footer: `${isNew ? '' : '<button class="btn btn-danger" id="hf-delete">Удалить…</button>'}${staysFormFoot()}`,
    onMount(m) {
      const out = () => $('#rf-preview-out', m);
      const body = () => ({ unit_id: Number($('#hf-unit', m).value),
        start: $('#hf-start', m).value, end: $('#hf-end', m).value,
        start_half: $('#hf-start-am', m).checked ? 'AM' : 'PM', end_half: $('#hf-end-pm', m).checked ? 'PM' : 'AM',
        reason: $('#hf-title', m).value, ...(isNew ? {} : { version: hold.version }) });
      const edit = previewThenSave({ url: isNew ? '/api/stays/ooo' : `/api/stays/ooo/${hold.id}`,
        method: isNew ? 'POST' : 'PUT', body, out });
      const del = `/api/stays/ooo/${hold.id}?version=${hold.version}`;
      const remove = {
        async preview() { renderPreview((await api(`${del}&preview=1`, { method: 'DELETE' })).diff, out()); },
        save: () => api(del, { method: 'DELETE' }),
      };
      let mode = edit;
      const delBtn = $('#hf-delete', m);
      if (delBtn) delBtn.onclick = async () => {
        mode = remove;
        $('[data-save]', m).textContent = 'Удалить';
        try { await remove.preview(); } catch (e) { toast(e.message, 'err'); }
      };
      staysBindFoot(m, { preview: () => mode.preview(), save: () => mode.save() }, onSaved, 'Готово');
    },
  });
}

/* ─────────────── Совместное проживание (§3.3): одна операция с предпросмотром ─────────────── */
async function openGroupForm(card, onSaved) {
  const cands = await api(`/api/stays/reservations/${card.id}/cohabit`);
  const mates = cands.filter(c => card.group_id && c.group_id === card.group_id);
  const free = cands.filter(c => !card.group_id || c.group_id !== card.group_id);
  const row = c => `${esc(c.number || '#' + c.reservation_id)} · ${esc(c.main_guest || 'без гостя')} · ${esc(dateRu(c.check_in))}–${esc(dateRu(c.check_out))}`;
  openModal({
    title: `Совместное проживание · ${card.number || '#' + card.id}`,
    subtitle: 'Брони одной категории в одном объекте, каждая на своего гостя; переезды у группы общие',
    body: `${mates.length ? `<h4>Уже вместе</h4>${mates.map(c => `<div>${row(c)}</div>`).join('')}
        ${sfCheck('gr-leave', 'Вывести эту бронь из группы', false)}` : ''}
      <h4>Проживать вместе с</h4>${free.map(c => `<label class="chk"><input type="checkbox" data-cohabit="${c.reservation_id}"> ${row(c)}
        ${c.group_id ? '<span class="muted">(в своей группе)</span>' : ''}</label>`).join('') || '<p class="muted">Подходящих броней нет</p>'}
      <div id="rf-preview-out" class="sp-out"></div>`,
    footer: staysFormFoot(),
    onMount(m) {
      const out = () => $('#rf-preview-out', m);
      const leave = () => $('#gr-leave', m)?.checked;
      const join = previewThenSave({ url: '/api/stays/groups/join', method: 'POST', out,
        body: () => ({ reservation_ids: [card.id, ...$$('[data-cohabit]', m).filter(c => c.checked).map(c => Number(c.dataset.cohabit))] }) });
      const quit = previewThenSave({ url: '/api/stays/groups/leave', method: 'POST', out, body: () => ({ reservation_id: card.id }) });
      staysBindFoot(m, { preview: () => (leave() ? quit : join).preview(), save: () => (leave() ? quit : join).save() },
        onSaved, 'Готово');
    },
  });
}

/* ─────────────── Карточка гостя (§6.5): профиль, семейное дерево, прочие связи, история ─────────────── */
async function openGuestCard(gid, onChanged) {
  const [g, fund, prefs0] = await Promise.all([api(`/api/stays/guests/${gid}/card`), staysFund(), api(`/api/stays/guests/${gid}/prefs`)]);
  const titles = Object.fromEntries(fund.fields.filter(f => f.target === 'guest').map(f => [f.code, f.title]));
  const edit = can('stays.edit');
  const role = { main: 'главный', guest: 'проживает' };
  const other = g.links.filter(l => !STAYS_FAMILY_LINK.has(l.kind));
  openModal({
    title: `${STAYS_LEVEL_MARK[g.level] || ''}${g.last_name} ${g.first_name} ${g.middle_name}`.trim(), wide: true,
    subtitle: [g.phone_display, g.email, g.birth_date ? 'др ' + dateRu(g.birth_date) : ''].filter(Boolean).join(' · '),
    body: `<div class="grid-2">
        <div><h4>Предпочтения</h4>${Object.entries(g.preferences).filter(([, v]) => v).map(([k, v]) => `<div>${esc(k)}: ${esc(v)}</div>`).join('') || '<span class="muted">нет</span>'}
          <h4>Предпочитает</h4><div id="gc-prefs"></div>
          ${g.special_dates.length ? `<h4>Особые даты</h4>${g.special_dates.map(d => `<div>${esc(dateRu(d.date))} — ${esc(d.what)}</div>`).join('')}` : ''}
          ${Object.keys(g.fields).length ? `<h4>Дополнительно</h4>${Object.entries(g.fields).map(([k, v]) => `<div>${esc(titles[k] || k)}: ${esc(String(v))}</div>`).join('')}` : ''}
          ${g.note ? `<h4>Примечание</h4><p>${esc(g.note)}</p>` : ''}</div>
        <div><h4>Прочие связи</h4><div id="gc-links">${other.map(l => `<div class="sb-line">${esc(l.name)} <span class="muted">${esc(l.label)}</span>
            ${edit ? `<button class="btn btn-sm btn-ghost" data-link-del="${l.id}">×</button>` : ''}</div>`).join('') || '<span class="muted">нет</span>'}</div>
          ${edit ? `<div class="sb-line"><input type="search" id="gc-link-q" placeholder="Связать с гостем: фамилия">
            <select id="gc-link-kind">${Object.entries(STAYS_LINK).filter(([k]) => !STAYS_FAMILY_LINK.has(k)).map(([k, t]) => `<option value="${k}">${esc(t)}</option>`).join('')}</select>
            <button class="btn btn-sm" id="gc-link-add" disabled>Связать</button></div><div id="gc-link-res"></div>` : ''}</div>
      </div>
      <h4>Семейное дерево</h4><div id="gc-family" class="ft"><div class="muted">Загрузка…</div></div>
      <h4>История проживаний</h4>
      <div id="gc-history" class="sb-history">${g.stays.map(x => `<div><b>${esc(x.number || '#' + x.reservation_id)}</b> · ${esc(x.units.join(' → ') || 'без объекта')}
        · ${esc(dateRu(x.date_from))}–${esc(dateRu(x.date_to))} · ${esc(role[x.role])} · ${esc(x.status_title)}
        ${x.butlers.length ? `<div class="muted">вели: ${esc(x.butlers.join(', '))}</div>` : ''}</div>`).join('') || '<span class="muted">проживаний нет</span>'}</div>`,
    footer: `<button class="btn btn-ghost" data-close>Закрыть</button>${edit ? '<button class="btn btn-primary" id="gc-edit">Изменить профиль</button>' : ''}`,
    onMount(m) {
      $('[data-close]', m).onclick = closeModal;
      const reopen = () => openGuestCard(gid, onChanged);
      renderFamilyTree($('#gc-family', m), gid, { editable: edit }).catch(e => toast(e.message, 'err'));
      renderGuestPrefs($('#gc-prefs', m), gid, prefs0, fund, edit, onChanged);
      const ed = $('#gc-edit', m);
      if (ed) ed.onclick = () => openGuestForm(gid, () => { reopen(); if (onChanged) onChanged(); });
      $$('[data-link-del]', m).forEach(b => {
        b.onclick = async () => {
          try { await api(`/api/stays/guest-links/${b.dataset.linkDel}`, { method: 'DELETE' }); reopen(); } catch (e) { toast(e.message, 'err'); }
        };
      });
      const q = $('#gc-link-q', m);
      if (!q) return;
      let picked = null;
      let timer = null;
      q.oninput = () => {
        clearTimeout(timer);
        timer = setTimeout(async () => {
          const found = q.value.trim().length < 2 ? [] : (await api('/api/stays/guests?q=' + encodeURIComponent(q.value.trim()), { silent: true }))
            .filter(x => x.id !== gid);
          $('#gc-link-res', m).innerHTML = found.map(x => `<button class="btn btn-sm btn-ghost" data-link-pick="${x.id}">${esc(x.short)}</button>`).join('');
          $$('[data-link-pick]', m).forEach(b => {
            b.onclick = () => { picked = Number(b.dataset.linkPick); q.value = b.textContent.trim(); $('#gc-link-add', m).disabled = false; };
          });
        }, 300);
      };
      $('#gc-link-add', m).onclick = async () => {
        try {
          await api(`/api/stays/guests/${gid}/links`, { method: 'POST', body: { guest_id: picked, kind: $('#gc-link-kind', m).value } });
          toast('Связь добавлена'); reopen();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* Пожелания гостя к объекту (часть 2 §5): порядок в списке — важность (первое главное); в запросе
   priority убывает с позицией. Каждая правка сохраняется сразу — список целиком, PUT /guests/{id}/prefs. */
const STAYS_PREF_KIND = { group: 'узел', flag: 'флаг', unit: 'объект' };
function renderGuestPrefs(host, gid, initial, fund, editable, onChanged) {
  let list = initial.map(p => ({ kind: p.kind, ref_id: p.ref_id, title: p.title }));
  const options = {
    group: fund.groups.map(x => [x.id, x.path.map(i => fund.groups.find(y => y.id === i)?.title || '').join(' / ')]),
    flag: fund.flags.filter(f => !f.archived).map(f => [f.id, f.title]),
    unit: fund.units.map(u => [u.id, u.label]),
  };
  /* правка пожеланий пересчитывает распределение: сначала предпросмотр (?preview=1) — если чьи-то брони
     переедут или сервер откажет в овербукинге, показываем разницу и ждём «Применить» */
  const body = next => ({ prefs: next.map((p, i) => ({ kind: p.kind, ref_id: p.ref_id, priority: next.length - i })) });
  const url = `/api/stays/guests/${gid}/prefs`;
  let pending = null;
  const apply = async next => {
    pending = null;
    try {
      const r = await api(url, { method: 'PUT', body: body(next) });
      list = r.result.map(p => ({ kind: p.kind, ref_id: p.ref_id, title: p.title }));
      if (onChanged) onChanged();
    } catch (e) { toast(e.message, 'err'); }
    draw();
  };
  const save = async next => {
    try {
      const r = await api(`${url}?preview=1`, { method: 'PUT', body: body(next) });
      if (!r.diff.moved.length && !r.diff.warnings_added.length && !r.overbook_refused) { await apply(next); return; }
      pending = { next, diff: r.diff, refused: r.overbook_refused };
    } catch (e) { toast(e.message, 'err'); }
    draw();
  };
  const draw = () => {
    const kind = host.querySelector('[data-pref-kind]')?.value || 'group';
    host.innerHTML = `${list.map((p, i) => `<div class="sb-line" data-pref-row="${i}"><b>${i + 1}.</b> ${esc(STAYS_PREF_KIND[p.kind])}: ${esc(p.title)}
        ${editable ? `<button class="btn btn-sm btn-ghost" data-pref-up="${i}"${i ? '' : ' disabled'} title="Важнее">↑</button>
          <button class="btn btn-sm btn-ghost" data-pref-del="${i}" title="Убрать">×</button>` : ''}</div>`).join('') || '<span class="muted">нет</span>'}
      ${editable ? `<div class="sb-line"><select data-pref-kind>${Object.entries(STAYS_PREF_KIND).map(([k, t]) => `<option value="${k}"${k === kind ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select>
        <select data-pref-ref>${options[kind].map(([id, t]) => `<option value="${id}">${esc(t)}</option>`).join('')}</select>
        <button class="btn btn-sm" data-pref-add${options[kind].length ? '' : ' disabled'}>Добавить</button>
        ${options[kind].length ? '' : '<span class="muted">в справочнике пока нет вариантов</span>'}</div>
        ${pending ? `<div class="sp-out" id="gc-pref-out"></div><div class="sb-line">
          <button class="btn btn-sm btn-primary" data-pref-apply${pending.refused ? ' disabled' : ''}>Применить</button>
          <button class="btn btn-sm btn-ghost" data-pref-cancel>Отмена</button></div>` : ''}` : ''}`;
    if (pending) {
      renderPreview(pending.diff, $('#gc-pref-out', host), pending.refused);
      $('[data-pref-apply]', host).onclick = () => apply(pending.next);
      $('[data-pref-cancel]', host).onclick = () => { pending = null; draw(); };
    }
    $$('[data-pref-up]', host).forEach(b => {
      b.onclick = () => { const i = Number(b.dataset.prefUp); const n = [...list]; [n[i - 1], n[i]] = [n[i], n[i - 1]]; save(n); };
    });
    $$('[data-pref-del]', host).forEach(b => { b.onclick = () => save(list.filter((_, i) => i !== Number(b.dataset.prefDel))); });
    const k = $('[data-pref-kind]', host);
    if (k) k.onchange = draw;
    const add = $('[data-pref-add]', host);
    if (add) {
      add.onclick = () => {
        const ref = Number($('[data-pref-ref]', host).value);
        if (!ref) return;
        if (list.some(p => p.kind === k.value && p.ref_id === ref)) { toast('Такое пожелание уже есть', 'warn'); return; }
        save([...list, { kind: k.value, ref_id: ref }]);
      };
    }
  };
  draw();
}

/* ─────────────── Статус брони ─────────────── */
function openStatusForm(card, onSaved) {
  const today = staysToday();
  openModal({
    title: `Статус брони ${card.number || '#' + card.id}`, subtitle: `Сейчас: ${card.status_title}`,
    body: `${sfRow('Новый статус', `<select id="rs-status">${Object.entries(STAYS_STATUS).filter(([k]) => k !== card.status)
      .map(([k, t]) => `<option value="${k}">${esc(t)}</option>`).join('')}</select>`)}
      <div id="rs-new-ci-wrap">${sfRow('Новая дата заезда (если гость приехал позже)', sfInput('rs-new-ci', card.status === 'no_show' ? today : '', 'date'))}</div>
      <div id="rf-preview-out" class="sp-out"></div>`,
    footer: staysFormFoot(),
    onMount(m) {
      $('#rs-new-ci-wrap', m).style.display = card.status === 'no_show' ? '' : 'none';
      const flow = previewThenSave({ url: `/api/stays/reservations/${card.id}/status`, method: 'POST',
        body: () => ({ status: $('#rs-status', m).value, version: card.version, new_check_in: $('#rs-new-ci', m).value || null }),
        out: () => $('#rf-preview-out', m) });
      staysBindFoot(m, flow, onSaved, 'Статус изменён');
    },
  });
}

/* ─────────────── Гость ─────────────── */
async function openGuestForm(id, onSaved, opts = {}) {
  const [g, fund] = await Promise.all([id ? api(`/api/stays/guests/${id}`) : null, staysFund()]);
  const gFields = fund.fields.filter(f => f.target === 'guest');
  const dates = (g?.special_dates || []).map(d => ({ ...d }));
  const level = { regular: 'обычный', vip: 'VIP', vvip: 'VVIP' };
  /* батлер (opts.mine): анкетные поля только для чтения — менять можно предпочтения и заметки */
  const lock = html => (opts.mine ? html.replace(/<(input|select)/, '<$1 disabled') : html);
  staysForm(g ? `Гость ${g.last_name}` : 'Новый гость', [
    sfRow('Фамилия', lock(sfInput('gf-last', g?.last_name))), sfRow('Имя', lock(sfInput('gf-first', g?.first_name))),
    sfRow('Отчество', lock(sfInput('gf-middle', g?.middle_name))), sfRow('Телефон', lock(sfInput('gf-phone', g?.phone_display))),
    sfRow('Email', lock(sfInput('gf-email', g?.email))), sfRow('Дата рождения', lock(sfInput('gf-birth', g?.birth_date, 'date'))),
    sfRow('Пол', lock(sfSelect('gf-gender', Object.entries(STAYS_GENDER), g?.gender || ''))),
    sfRow('Уровень', lock(sfSelect('gf-level', Object.entries(level), g?.level || 'regular'))),
    sfRow('Аллергии', sfInput('gf-allergy', g?.preferences?.allergy)), sfRow('Питание', sfInput('gf-food', g?.preferences?.food)),
    sfRow('Привычки', sfInput('gf-habits', g?.preferences?.habits)),
    sfRow('Примечание', `<textarea id="gf-note" rows="2">${esc(g?.note || '')}</textarea>`),
    `<h4>Особые даты</h4><div id="gf-dates"></div><button class="btn btn-sm btn-ghost" id="gf-sd-add" type="button">+ Дата</button>`,
    gFields.length ? `<h4>Дополнительно</h4>${staysFieldInputs(gFields, g?.fields, 'data-gf-field')}` : '',
  ], async m => {
    const v = sel => $(sel, m).value;
    const body = { last_name: v('#gf-last'), first_name: v('#gf-first'), middle_name: v('#gf-middle'),
      phone: v('#gf-phone'), email: v('#gf-email'), birth_date: v('#gf-birth') || null, gender: v('#gf-gender'), level: v('#gf-level'),
      preferences: { ...(g?.preferences || {}), allergy: v('#gf-allergy'), food: v('#gf-food'), habits: v('#gf-habits') },
      special_dates: dates.filter(d => d.date && d.what),
      fields: { ...(g?.fields || {}), ...staysFieldValues(m, 'data-gf-field') }, note: v('#gf-note') };
    const saved = await api(g ? `/api/stays/guests/${g.id}` : '/api/stays/guests', { method: g ? 'PUT' : 'POST', body });
    toast('Гость сохранён');
    if (onSaved) onSaved(saved);
  }, m => {
    const draw = () => {
      $('#gf-dates', m).innerHTML = dates.map((d, i) => `<div class="sb-line">
        <input type="date" data-sd-date="${i}" value="${esc(d.date || '')}">
        <input data-sd-what="${i}" value="${esc(d.what || '')}" placeholder="день рождения, годовщина…">
        <button class="btn btn-sm btn-ghost" type="button" data-sd-del="${i}">×</button></div>`).join('');
      $$('[data-sd-date]', m).forEach(x => { x.onchange = () => { dates[x.dataset.sdDate].date = x.value; }; });
      $$('[data-sd-what]', m).forEach(x => { x.onchange = () => { dates[x.dataset.sdWhat].what = x.value; }; });
      $$('[data-sd-del]', m).forEach(b => { b.onclick = () => { dates.splice(Number(b.dataset.sdDel), 1); draw(); }; });
    };
    draw();
    $('#gf-sd-add', m).onclick = () => { dates.push({ date: '', what: '' }); draw(); };
  });
}
