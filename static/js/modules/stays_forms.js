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

function renderPreview(diff, el) {
  const items = [];
  (diff.moved || []).forEach(m => {
    const who = m.new ? 'Новая бронь' : `Бронь ${m.number || '#' + m.reservation_id}`;
    const seg = m.seg_index ? ` (сегмент ${m.seg_index + 1})` : '';
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
      renderPreview(r.diff, out());
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
  const fund = opts.mine ? { categories: [], labels: [], units: [], kinds: [] } : await staysFund();
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
  openModal({
    title: r ? `Бронь ${r.number || '#' + r.id}` : 'Новая бронь', wide: true,
    body: `
      <div class="grid-2">
        ${sfRow('Номер брони (Fidelio)', sfInput('rf-number', r?.number))}
        ${sfRow('Категория', `<select id="rf-category">${fund.categories.map(c => opt(c.id, `${c.code} · ${c.title}`, r?.category_id)).join('')}</select>`)}
        ${sfRow('Заезд', sfInput('rf-check-in', r?.check_in, 'date'))}
        ${sfRow('Выезд', sfInput('rf-check-out', r?.check_out, 'date'))}
      </div>
      ${sfCheck('rf-early', 'Ранний заезд', r?.early)} ${sfCheck('rf-late', 'Поздний выезд', r?.late)}
      ${sfCheck('rf-declined', 'Гость отказался от батлера', r?.declined_butler)}
      <div class="grid-2">
        ${sfRow('Метка', `<select id="rf-label">${opt('', '—', r?.label_id)}${fund.labels.map(l => opt(l.id, l.title, r?.label_id)).join('')}</select>`)}
        ${sfRow('Заказчик', sfInput('rf-customer', r?.customer))}
        ${sfRow('Повод визита', sfInput('rf-purpose', r?.purpose))}
        ${sfRow('Оплата за', sfInput('rf-paid', r?.paid_by))}
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
      <h4>Логистика</h4><div id="rf-logistics"></div><button class="btn btn-sm btn-ghost" id="rf-log-add">+ Рейс / трансфер / авто</button>
      <div id="rf-preview-out" class="sp-out"></div>`,
    footer: staysFormFoot(),
    onMount(m) {
      const val = sel => $(sel, m).value;
      if (opts.mine) {
        ['#rf-number', '#rf-category', '#rf-check-in', '#rf-check-out', '#rf-early', '#rf-late', '#rf-declined',
          '#rf-label', '#rf-customer', '#rf-purpose', '#rf-paid', '#rf-move-add', '#rf-new-add', '#rf-new-last']
          .forEach(sel => { const el = $(sel, m); if (el) el.disabled = true; });
        if (r) {
          $('#rf-category', m).innerHTML = `<option value="${r.category_id}">—</option>`;
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
      drawOcc(); drawMoves(); drawPins(); drawLog();

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
      $('#rf-check-in', m).onchange = follow;
      $('#rf-check-out', m).onchange = follow;
      $('#rf-category', m).onchange = drawPins;
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
        customer: val('#rf-customer'), purpose: val('#rf-purpose'), paid_by: val('#rf-paid'), note: val('#rf-note'),
        group_id: r?.group_id ?? null, fields: r?.fields || {},
        occupants: form.occupants.map(({ id: oid, guest_id, role, date_from, date_to }) => ({ id: oid, guest_id, role, date_from, date_to })),
        moves: form.moves.filter(mv => mv.move_date), logistics: form.logistics, companions: form.companions,
        pins: opts.mine ? null : Object.fromEntries([Number(val('#rf-category')), ...form.moves].map((_, i) => [i, form.pins[i] ?? null])),
        version: r?.version,
      });
      const flow = previewThenSave({ url: r ? `/api/stays/reservations/${r.id}` : '/api/stays/reservations',
        method: r ? 'PUT' : 'POST', body, out: () => $('#rf-preview-out', m) });
      staysBindFoot(m, flow, opts.onSaved, 'Бронь сохранена');
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
  const g = id ? await api(`/api/stays/guests/${id}`) : null;
  const level = { regular: 'обычный', vip: 'VIP', vvip: 'VVIP' };
  /* батлер (opts.mine): анкетные поля только для чтения — менять можно предпочтения и заметки */
  const lock = html => (opts.mine ? html.replace(/<(input|select)/, '<$1 disabled') : html);
  staysForm(g ? `Гость ${g.last_name}` : 'Новый гость', [
    sfRow('Фамилия', lock(sfInput('gf-last', g?.last_name))), sfRow('Имя', lock(sfInput('gf-first', g?.first_name))),
    sfRow('Отчество', lock(sfInput('gf-middle', g?.middle_name))), sfRow('Телефон', lock(sfInput('gf-phone', g?.phone_display))),
    sfRow('Email', lock(sfInput('gf-email', g?.email))), sfRow('Дата рождения', lock(sfInput('gf-birth', g?.birth_date, 'date'))),
    sfRow('Уровень', lock(sfSelect('gf-level', Object.entries(level), g?.level || 'regular'))),
    sfRow('Аллергии', sfInput('gf-allergy', g?.preferences?.allergy)), sfRow('Питание', sfInput('gf-food', g?.preferences?.food)),
    sfRow('Привычки', sfInput('gf-habits', g?.preferences?.habits)),
    sfRow('Примечание', `<textarea id="gf-note" rows="2">${esc(g?.note || '')}</textarea>`),
  ], async m => {
    const v = sel => $(sel, m).value;
    const body = { last_name: v('#gf-last'), first_name: v('#gf-first'), middle_name: v('#gf-middle'),
      phone: v('#gf-phone'), email: v('#gf-email'), birth_date: v('#gf-birth') || null, level: v('#gf-level'),
      preferences: { allergy: v('#gf-allergy'), food: v('#gf-food'), habits: v('#gf-habits') },
      special_dates: g?.special_dates || [], fields: g?.fields || {}, note: v('#gf-note') };
    const saved = await api(g ? `/api/stays/guests/${g.id}` : '/api/stays/guests', { method: g ? 'PUT' : 'POST', body });
    toast('Гость сохранён');
    if (onSaved) onSaved(saved);
  });
}
