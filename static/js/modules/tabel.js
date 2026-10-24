'use strict';

/* ══════════════════════════════════════════════════════════════════
   ТАБЕЛЬ (16.5) — первичный документ: код дня + информационный план строки.
   Циклы графика — инструмент заполнения Табеля (решение владельца).
   ══════════════════════════════════════════════════════════════════ */
async function loadTabel() {
  const host = $('#view-timesheet');
  host.innerHTML = `
    <div class="page-head">
      <div><h2>Слой 0 · Табель</h2><div class="sub">Первичный документ: код дня и плановые часы.
        Окно рабочего времени, недостача и план карточки считаются от значения Табеля
        (CFG-WINDOWS); График генерируется из Табеля</div></div>
      <div class="spacer"></div>
      ${v4MonthNav('tb')}
      <button class="btn btn-sm" id="tb-today" title="Прокрутить сетку к колонке сегодняшнего дня">Сегодня</button>
      <button class="btn btn-sm" id="tb-absence" title="Слой 0 · Табель: отпуск, больничный, за свой счёт, оплачиваемый выходной — коды первичного документа">Назначить отсутствие</button>
      <button class="btn btn-sm" id="tb-fill">Заполнить из циклов</button>
      <button class="btn btn-sm" id="tb-reset" title="Убрать ручные коды периода и вернуть автозаполнение из циклов">Сбросить</button>
    </div>
    <div id="tb-body"><div class="empty">Загрузка…</div></div>`;
  v4BindMonthNav('tb', loadTabel);
  let data;
  try { data = await api(`/api/tabel?year=${state.year}&month=${state.month}`); } catch (e) {
    $('#tb-body').innerHTML = `<div class="panel"><div class="empty">${esc(e.message)}</div></div>`; return;
  }
  state.tabel = data;
  $('#tb-fill').style.display = data.can_edit ? '' : 'none';
  $('#tb-fill').onclick = () => tabelFillModal(data);
  /* T3 (Q5, 12.10.2026): «Сбросить» — убрать ручные коды и вернуть автозаполнение. */
  $('#tb-reset').style.display = data.can_edit ? '' : 'none';
  $('#tb-reset').onclick = () => tabelResetModal(data);
  /* Q4: отпуск/ДО/Б/ОВ назначаются кодом Табеля — из Табеля, а не из Графика. */
  $('#tb-absence').style.display = data.can_edit ? '' : 'none';
  $('#tb-absence').onclick = () => openRangeModal('tabel');
  /* «Сегодня» — как в Графике (18.10.2026): докрутка к колонке дня и подсветка */
  $('#tb-today').onclick = scrollTabelToToday;
  renderTabel();
  if (state.pendingTabelCell) {
    const { emp, date } = state.pendingTabelCell;
    state.pendingTabelCell = null;
    const row = data.rows.find(r => r.employee.id === emp);
    if (row && data.days.includes(date)) tabelCellModal(emp, date);
  }
}

function v4CellLabel(c) { return c ? c.value.replace(' ', '') : ''; }

function scrollTabelToToday() {
  const host = $('#tb-body .v4-grid-wrap');
  const th = host && host.querySelector('thead th.today');
  if (!host || !th) { toast('Сегодняшний день не входит в открытый период', 'warn'); return; }
  host.scrollTo({ left: Math.max(0, th.offsetLeft - host.clientWidth / 2 + th.clientWidth / 2),
                  behavior: 'smooth' });
  th.classList.add('flash-today');
  setTimeout(() => th.classList.remove('flash-today'), 1800);
}

function renderTabel() {
  const d = state.tabel;
  const lockBadge = l => l === 'locked'
    ? '<span class="badge muted" title="Период закрыт, следующий тоже закрыт — правка запрещена">закрыт</span>'
    : (l === 'last_closed'
      ? '<span class="badge warn" title="Последний закрытый период: правка разрешена, затем — пересчёт в УТ">закрыт · можно править</span>' : '');
  const missing = d.rows.reduce((n, r) => n + (r.missing_days || []).length, 0);
  /* ФИО строки — вход в карточку сотрудника (та же, что в разделе «Сотрудники»):
     правки доступны прямо из Табеля, без перехода в другой раздел.
     Без права employees.view — обычный текст. */
  const canCard = can('employees.view');
  const rows = d.rows.map(r => `<tr>
    <td class="who${canCard ? ' who-click' : ''}"${canCard ? ` data-emp="${r.employee.id}" title="Карточка сотрудника — открыть"` : ''}><span class="emp-nm">${esc(r.employee.short_name)}</span><small>${esc(r.employee.group)} ${lockBadge(r.lock)}</small></td>
    ${d.days.map(day => {
      const c = r.cells[day];
      const color = c ? v4CodeColor(c.code, d.colors) : 'transparent';
      const edit = d.can_edit && r.lock !== 'locked';
      const src = c ? (c.source === 'cycle' ? ' · из циклов' : ' · вручную') : '';
      return `<td class="v4-cell${edit ? ' edit' : ''}${c ? '' : ' empty'}" ${edit ? `data-e="${r.employee.id}" data-d="${day}"` : ''}
        title="${c ? esc(c.value + src + (c.note ? ' · ' + c.note : '')) : 'не заполнено — расчёт не запустится, пока Табель не покрывает период'}"
        style="${c ? `background:${withAlpha(color, .22)};border-left:3px solid ${color}` : ''}">${esc(v4CellLabel(c))}</td>`;
    }).join('')}
    <td class="num"><b>${hours(r.plan_hours)}</b></td></tr>`).join('');
  $('#tb-body').innerHTML = `
    ${missing ? `<div class="panel" style="border-color:#ecd9ae;background:#fffaf0"><b>${missing}</b> ${plural(missing, 'ячейка', 'ячейки', 'ячеек')} не заполнены.
      Табель обязан покрывать период: ровно одна строка на каждый день трудоустройства
      (RUL-TIMESHEET-COVERS-PERIOD) — иначе расчёт УТ не запустится. Заполните вручную или «Заполнить из циклов».</div>` : ''}
    <div class="table-wrap v4-grid-wrap"><table class="data v4-grid">
      <thead><tr><th class="who">Сотрудник</th>${d.days.map(v4DayHead).join('')}<th>План, ч</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="${d.days.length + 2}" class="empty">Нет сотрудников</td></tr>`}</tbody>
    </table></div>
    <p class="hint">${canCard ? 'Клик по ФИО — карточка сотрудника. ' : ''}Коды: ${d.codes.map(c => `<span class="badge" style="background:${withAlpha(v4CodeColor(c.code, d.colors), .22)}" title="${esc(c.title)}">${esc(c.code)}</span> ${esc(c.title)}`).join(' · ')}.
      Значения с окнами (CFG-WINDOWS): ${d.values.map(esc).join(', ')}. План строки — информационный
      (зарплатный) атрибут; план карточки УТ = длина окна.</p>`;
  $$('#tb-body td.v4-cell.edit').forEach(td => td.onclick = () => tabelCellModal(+td.dataset.e, td.dataset.d));
  $$('#tb-body td.who[data-emp]').forEach(td => td.onclick = () => openEmployeeCard(+td.dataset.emp));
}

function tabelCellModal(empId, day) {
  const d = state.tabel;
  const row = d.rows.find(r => r.employee.id === empId);
  const cur = row.cells[day] || null;
  const lastDay = d.days[d.days.length - 1].slice(8);
  /* Q4 (норматив 12.10.2026): отпуск, больничный, за свой счёт и оплачиваемый выходной —
     коды Табеля, и заявления по ним печатаются ОТСЮДА (из слоя 0). «Отпросился
     (выходной за часы)» — данные Графика, его заявление печатается из ячейки Графика. */
  /* 18.10.2026: шаблон заявления — атрибут КАРТОЧКИ кода Табеля (doc_type строки
     CFG-DAY-CODES); словарь смен в заявлениях слоя 0 больше не участвует. */
  const docOfCode = code => ((d.codes || []).find(x => x.code === code) || {}).doc_type || '';
  const statementNameByDoc = doc => (state.docKinds || []).find(x => x.code === doc)?.name || doc;
  /* Значение — только плашкой из справочников (решение владельца 16.10.2026): код без
     часов (CFG-DAY-CODES) — одна плашка, код с часами — по плашке на строку CFG-WINDOWS
     («Я 12», «Я 9»…). Плашка и есть значение, поэтому часы, которых нет в справочнике,
     ввести нельзя: сервер их и так отклонял (CHK-WINDOW-EXISTS, CHK-PLAN-CONSISTENT/
     FORMAT), но теперь невалидная комбинация даже не уходит в запрос. Код с часами без
     строк окон показан отключённой плашкой — значение нельзя задать, пока окно не добавлено
     в «Настройках». */
  const num = s => Number(String(s).replace(',', '.'));
  const winOf = v => (d.windows || {})[v] || null;
  const chipsHtml = d.codes.map(c => {
    const color = v4CodeColor(c.code, d.colors);
    const tip = c.title ? `${c.code} — ${c.title}` : c.code;
    const style = `background:${withAlpha(color, .22)};border-color:${color}`;
    if (!c.carries_hours) {
      return `<button type="button" class="tc-chip" data-code="${esc(c.code)}" data-hours="0" style="${style}" title="${esc(tip)}">${esc(c.code)}</button>`;
    }
    const vals = d.values.filter(v => v.startsWith(c.code + ' '))
      .sort((a, b) => num(a.split(' ')[1]) - num(b.split(' ')[1]));
    if (!vals.length) {
      return `<span class="tc-chip off" title="${esc(tip)}: нет строки в CFG-WINDOWS — значение нельзя задать, пока окно не добавлено в настройках">${esc(c.code)}</span>`;
    }
    return vals.map(v => {
      const w = winOf(v);
      return `<button type="button" class="tc-chip" data-code="${esc(c.code)}" data-hours="${esc(v.split(' ')[1])}" style="${style}" title="${esc(tip)}${w ? ` · окно ${w[0]}–${w[1]}` : ''}">${esc(v)}</button>`;
    }).join('');
  }).join('');
  openModal({
    title: `Табель · ${row.employee.short_name}`,
    subtitle: `${dateRu(day)}${row.lock === 'last_closed' ? ' · период закрыт: после правки нужен пересчёт в УТ' : ''}`,
    body: `
      <div class="opt-group-title" style="margin-top:0">Значение дня — код и плановые часы (CFG-DAY-CODES · CFG-WINDOWS)</div>
      <div class="tc-chips" id="tc-chips">
        <button type="button" class="tc-chip clear" data-code="" data-hours="0"
          title="Убрать значение ячейки — день станет незаполненным">✕ Очистить</button>
        ${chipsHtml}
      </div>
      <div class="hint" id="tc-sel" style="margin:4px 0 10px"></div>
      <label class="field"><span>Применить по число месяца (включительно)</span>
        <input id="tc-until" type="number" min="${+day.slice(8)}" max="${+lastDay}" value="${+day.slice(8)}"></label>
      <label class="field"><span>Примечание</span><input type="text" id="tc-note" value="${esc(cur?.note || '')}"></label>
      <p class="hint">На плашках — только значения, которые можно сохранить: коды без часов и
        значения с часами, у которых есть строка окна (${d.values.map(esc).join(', ') || 'окон в справочнике нет'}).
        План строки — информационный (зарплатный); план карточки УТ = длина окна.</p>
      <div id="tc-doc-wrap" style="display:none;margin-top:10px;border-top:1px solid var(--line);padding-top:10px">
        <div class="opt-group-title" style="margin-top:0">Заявление по коду Табеля</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          <button class="btn btn-sm" id="tc-print">Печать заявления</button>
          <button class="btn btn-sm" id="tc-docx">DOCX (шаблон компании)</button>
          <button class="btn btn-sm" id="tc-pdf">PDF (готов к печати)</button>
          <span class="hint" style="margin:0" id="tc-doc-name"></span>
        </div>
        <p class="hint" style="margin:6px 0 0">Печатается по СОХРАНЁННОМУ коду дня и находит весь
          период отсутствия, даже если он переходит границы месяца. Период берётся из Табеля.</p>
      </div>`,
    footer: `<button class="btn btn-ghost" data-cancel>Закрыть</button><button class="btn btn-primary" data-save>Сохранить</button>`,
    onMount(m) {
      const chipEls = $$('.tc-chip[data-code]', m);
      const chipValue = b => !b.dataset.code ? ''
        : (b.dataset.hours === '0' ? b.dataset.code : `${b.dataset.code} ${b.dataset.hours}`);
      /* Предвыбор — то, что уже в ячейке; старое значение вне справочника не совпадёт
         ни с одной плашкой — показываем его подсказкой и требуем явного выбора */
      let selChip = chipEls.find(b => b.dataset.code && cur && chipValue(b) === cur.value) || null;
      const applySel = () => {
        chipEls.forEach(b => b.classList.toggle('sel', b === selChip));
        const selLine = $('#tc-sel');
        if (!selChip) {
          selLine.innerHTML = cur
            ? `Сейчас в ячейке: <b>«${esc(cur.value)}»</b>${cur.source === 'cycle' ? ' (из циклов)' : ' (вручную)'} — выберите значение или «Очистить»`
            : 'Ячейка не заполнена — выберите значение';
        } else if (!selChip.dataset.code) {
          selLine.textContent = 'Ячейка будет очищена: день станет незаполненным (расчёт не запустится, пока Табель не покрывает период)';
        } else {
          const c = d.codes.find(x => x.code === selChip.dataset.code);
          const v = chipValue(selChip);
          const w = winOf(v);
          selLine.innerHTML = `Выбрано: <b>«${esc(v)}»</b>${c && c.title ? ' — ' + esc(c.title) : ''}${w ? ` · окно ${esc(w[0])}–${esc(w[1])}` : ''}`;
        }
        /* пустой код («Очистить») заявления не имеет: заявления «за счёт часов»
           печатаются из Графика, а слой 0 — по коду отсутствия и его карточке */
        const doc = selChip && selChip.dataset.code ? docOfCode(selChip.dataset.code) : '';
        $('#tc-doc-wrap').style.display = doc ? '' : 'none';
        if (doc) $('#tc-doc-name').textContent = statementNameByDoc(doc);
      };
      chipEls.forEach(b => b.onclick = () => { selChip = b; applySel(); });
      applySel();
      /* печать имеет смысл только по сохранённому дню: сервер читает код из Табеля */
      const ifSaved = fn => () => {
        if (!cur) return toast('Сначала сохраните код дня — тогда станет доступна печать', 'warn');
        fn();
      };
      $('#tc-print').onclick = ifSaved(() => printAbsenceRequest(empId, day, 'tabel_code'));
      $('#tc-docx').onclick = ifSaved(() => downloadAbsenceDoc(empId, day, 'docx', 'tabel_code'));
      $('#tc-pdf').onclick = ifSaved(() => downloadAbsenceDoc(empId, day, 'pdf', 'tabel_code'));
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        if (!selChip) return toast('Выберите значение дня или «Очистить»', 'warn');
        const code = selChip.dataset.code;
        /* часы — из плашки (строка CFG-WINDOWS), для кода без часов всегда 0:
           CHK-PLAN-CONSISTENT не сработает, план отправляется только с кодом */
        const h = code && selChip.dataset.hours !== '0' ? num(selChip.dataset.hours) : 0;
        const until = Math.max(+day.slice(8), Math.min(+lastDay, Number($('#tc-until').value) || +day.slice(8)));
        try {
          let res;
          if (until > +day.slice(8)) {
            const dates = d.days.filter(x => +x.slice(8) >= +day.slice(8) && +x.slice(8) <= until);
            res = await api('/api/tabel/bulk', { method: 'POST', body: { employee_ids: [empId], dates, code, hours: h, note: $('#tc-note').value } });
            (res.warnings || []).forEach(w => toast(w, 'warn'));
            (res.errors || []).slice(0, 5).forEach(e => toast(`${e.date}: ${e.detail}`, 'err'));
          } else {
            res = await api('/api/tabel/cell', { method: 'PUT', body: { employee_id: empId, date: day, code, hours: h, note: $('#tc-note').value } });
            if (res.warning) toast(res.warning, 'warn');
          }
          /* Модалка НЕ закрывается (решение владельца 16.10.2026): после сохранения
             заявление печатается сразу, а сетка за модалкой показывает новое значение.
             Перезагружаем Табель и пересобираем модалку по свежим данным. */
          toast('Табель сохранён', 'ok');
          await loadTabel();
          tabelCellModal(empId, day);
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

function tabelFillModal(d) {
  openModal({
    title: 'Заполнить Табель из циклов',
    subtitle: `${MONTHS[d.month - 1]} ${d.year}`,
    body: `
      <p>Циклы блоков (2/2, 3/3, пятидневка, произвольный цикл) раскладываются по дням и
        подбирают значение Табеля по окнам CFG-WINDOWS («Я 12» = 08:00–20:00). Смена через
        полночь оформляется <b>одной строкой в дне начала</b>: суточные 08:00–08:00 дают явку
        с окном 08:00–20:00, а присутствие после полуночи попадает в карточку следующего
        дня — рабочее время считается по окну своего дня, часы вне окна идут в переработку.
        Дни без работы получают код отсутствия из словаря. График будет перегенерирован
        из Табеля.</p>
      <label class="field"><span>Что перезаписывать</span><select id="tf-mode">
        <option value="keep">Только пустые и заполненные из циклов (ручные правки сохраняются)</option>
        <option value="all">Все ячейки, включая ручные правки</option>
      </select></label>
      <p class="hint">Закрытые периоды (кроме последнего закрытого) не меняются.</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button><button class="btn btn-primary" data-save>Заполнить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-save]').onclick = async () => {
        try {
          const r = await api('/api/tabel/fill-from-cycles', { method: 'POST',
            body: { year: d.year, month: d.month, overwrite: $('#tf-mode').value === 'all' } });
          closeModal();
          toast(`Заполнено ячеек: ${r.written}, пропущено: ${r.skipped}`,
            r.warnings.length ? 'warn' : 'ok', (r.warnings || []).slice(0, 8));
          loadTabel();
        } catch (e) { toast(e.message, 'err'); }
      };
    },
  });
}

/* «Сбросить» (T3, решение владельца Q5 от 12.10.2026): убирает введённые вручную коды
   периода и возвращает автозаполнение из циклов; закрытых периодов не касается. */
function tabelResetModal(d) {
  const rows = d.rows || [];
  const manual = rows.reduce((n, r) => n + Object.values(r.cells)
    .filter(c => c.source === 'manual').length, 0);
  openModal({
    title: 'Сбросить Табель',
    subtitle: `${MONTHS[d.month - 1]} ${d.year}${d.half ? ` · половина ${d.half}` : ''}`,
    body: `
      <p>Табель — первичный документ: он заполняется из настроек сотрудника (циклов блоков),
        а ручная правка ячейки запоминается и автозаполнением больше не перезаписывается.
        Сброс убирает <b>введённые вручную</b> коды периода и заново заполняет Табель из
        циклов; График перегенерируется из Табеля.</p>
      <div class="panel" style="border-color:#ecd9ae;background:#fffaf0;margin:10px 0">
        Сейчас вручную заполнено ячеек: <b>${manual}</b>. Закрытые периоды не трогаются
        (RUL-CLOSED-PERIOD-IMMUTABLE); дни вне трудоустройства не заполняются.</div>
      <label class="field"><span>Кому</span><select id="tr-emp">
        <option value="">Всем сотрудникам периода</option>
        ${rows.map(r => `<option value="${r.employee.id}">${esc(r.employee.short_name)} · ${esc(r.employee.group)}${r.lock === 'locked' ? ' · закрыт' : ''}</option>`).join('')}
      </select></label>
      <p class="hint">Если для дня цикл не даёт значения (нет строки CFG-WINDOWS либо отрезки
        дня одним значением непредставимы), ячейка останется пустой — список вернёт сервер,
        такие дни нужно заполнить вручную, иначе расчёт не запустится. Пересчёт часов не
        запускается: итоги обновятся при чтении «Управленческого Табеля».</p>`,
    footer: `<button class="btn btn-ghost" data-cancel>Отмена</button>
             <button class="btn btn-danger" data-ok>Сбросить</button>`,
    onMount(m) {
      m.querySelector('[data-cancel]').onclick = closeModal;
      m.querySelector('[data-ok]').onclick = () => {
        const empId = $('#tr-emp').value;      // значение читаем ДО подтверждающей модалки
        confirmDialog('Сбросить ручные коды Табеля?',
          'Ручные правки периода будут удалены, Табель снова заполнится из циклов, График перегенерируется. Вернуть удалённые коды можно только повторным вводом вручную.',
          async () => {
            try {
              const r = await api('/api/tabel/reset', { method: 'POST', body: {
                year: d.year, month: d.month, half: d.half || null,
                employee_ids: empId ? [+empId] : null } });
              const bits = [`очищено ручных ячеек: ${r.cleared}`,
                            `заполнено из циклов: ${r.written}`];
              if ((r.locked_skipped || []).length) bits.push(`пропущено закрытых: ${r.locked_skipped.length}`);
              if (r.uncovered_total) bits.push(`остались пустыми: ${r.uncovered_total} дн.`);
              toast(bits.join(', '),
                (r.uncovered_total || (r.warnings || []).length) ? 'warn' : 'ok',
                [...(r.warnings || []),
                 ...(r.uncovered || []).map(u => `${u.employee} ${dateRu(u.date)}: не заполнено`)].slice(0, 8));
              loadTabel();
            } catch (e) { toast(e.message, 'err'); }
          }, 'Сбросить');
      };
    },
  });
}
