#!/usr/bin/env python3
"""Патч static/js/app.js: дни двойной оплаты (ДЯ2/ДН2), ВИП-периоды, панель в настройках.

Правило проекта: app.js правится только литеральными str.replace с проверкой количества
(инструмент edit_file ломает строки с `$$`). Скрипт идемпотентен: если маркер уже есть — выход.
"""
import sys

P = "static/js/app.js"
s = open(P, encoding="utf-8").read()
orig_dollardollar = s.count("$$(")

if "refreshDoublePay" in s:
    print("уже применено — выходим")
    sys.exit(0)

def rep(old: str, new: str, n: int = 1) -> None:
    global s
    c = s.count(old)
    assert c == n, f"ожидал {n} вхождений, нашёл {c}: {old[:90]!r}"
    s = s.replace(old, new)

# ── 1. state: год календаря двойной оплаты ──
rep("""  showArchived: false,                                           // словарь смен: показывать ли архив
""",
    """  showArchived: false,                                           // словарь смен: показывать ли архив
  dpYear: new Date().getFullYear(),                              // календарь двойной оплаты: просматриваемый год
""")

# ── 2. шапка сетки графика: маркер ×2 на днях двойной оплаты ──
rep("""    const head = `<tr><th class="corner">ФИО</th>${g.days.map(d =>
      `<th class="${d.is_weekend ? 'weekend' : ''} ${d.is_today ? 'today' : ''}" title="${dateRu(d.date)}">
        <span class="dow">${esc(d.weekday)}</span>${d.day}</th>`).join('')}<th>Итого</th></tr>`;""",
    """    const head = `<tr><th class="corner">ФИО</th>${g.days.map(d =>
      `<th class="${d.is_weekend ? 'weekend' : ''} ${d.is_today ? 'today' : ''}${d.double_scope ? ' double-day' : ''}"
        title="${dateRu(d.date)}${d.double_scope ? ' · день двойной оплаты (' + (d.double_title || '') + '): переработки идут кодами ДЯ2/ДН2' : ''}">
        <span class="dow">${esc(d.weekday)}</span>${d.day}${d.double_scope ? '<span class="dbl-mark">×2</span>' : ''}</th>`).join('')}<th>Итого</th></tr>`;""")

# ── 3. легенда сетки: чип «день двойной оплаты» ──
rep("""     <span class="chip" title="Дни относятся к другому блоку (переход между сменами)">
      <span class="swatch" style="background:${state.grid?.colors?.out_of_block || '#d8d3e8'}"></span><b>дни другой смены</b></span>`;""",
    """     <span class="chip" title="Дни относятся к другому блоку (переход между сменами)">
      <span class="swatch" style="background:${state.grid?.colors?.out_of_block || '#d8d3e8'}"></span><b>дни другой смены</b></span>
     <span class="chip" title="Производственный календарь / ВИП-гости: переработки в эти дни оплачиваются вдвое (коды ДЯ2/ДН2). Календарь — в разделе «Настройки»">
      <span class="dbl-mark legend-x2">×2</span><b>день двойной оплаты</b></span>`;""")

# ── 4. хелперы кодов к выплате — перед dayChip ──
rep("""function dayChip(day) {""",
    """/* Коды часов к выплате: ДЯ/ДН — одинарный тариф, ДЯ2/ДН2 — двойной
   (производственный календарь / ВИП-гости). prefix: 'credit_' | 'pay_' */
function payCodes(t, p) {
  const out = [];
  if (t[p + 'dya']) out.push(`<b>ДЯ ${hours(t[p + 'dya'])}</b>`);
  if (t[p + 'dn']) out.push(`<b style="color:#3d55c8">ДН ${hours(t[p + 'dn'])}</b>`);
  if (t[p + 'dya2']) out.push(`<b class="dbl">ДЯ2 ${hours(t[p + 'dya2'])}</b>`);
  if (t[p + 'dn2']) out.push(`<b class="dbl">ДН2 ${hours(t[p + 'dn2'])}</b>`);
  return out.join(' · ') || '—';
}
function creditLine(c) {
  const bits = [];
  if (c.dya) bits.push(`<b>ДЯ ${hours(c.dya)}</b>`);
  if (c.dn) bits.push(`<b style="color:#3d55c8">ДН ${hours(c.dn)}</b>`);
  if (c.dya2) bits.push(`<b class="dbl">ДЯ2 ${hours(c.dya2)}</b>`);
  if (c.dn2) bits.push(`<b class="dbl">ДН2 ${hours(c.dn2)}</b>`);
  return bits.join(', ') || '—';
}
function settleTotalLine(t) {
  const bits = [];
  if (t.pay_dya) bits.push(`ДЯ ${hours(t.pay_dya)}`);
  if (t.pay_dn) bits.push(`ДН ${hours(t.pay_dn)}`);
  if (t.pay_dya2) bits.push(`ДЯ2 ${hours(t.pay_dya2)}`);
  if (t.pay_dn2) bits.push(`ДН2 ${hours(t.pay_dn2)}`);
  const dbl = (t.pay_dya2 || 0) + (t.pay_dn2 || 0);
  return `${bits.join(' + ') || '0'} = ${hours(t.pay_total)} ч к оплате`
    + (dbl ? ' · ДЯ2/ДН2 учтены по двойному тарифу' : '');
}

function dayChip(day) {""")

# ── 5. day-chip: класс и подпись «×2» ──
rep("""  const cls = ['day-chip', bad ? 'bad' : '', issue ? 'issue' : '', off ? 'off' : '',
    day.status === 'work_off' ? 'issue' : ''].filter(Boolean).join(' ');""",
    """  const cls = ['day-chip', bad ? 'bad' : '', issue ? 'issue' : '', off ? 'off' : '',
    day.status === 'work_off' ? 'issue' : '', day.is_double ? 'double' : ''].filter(Boolean).join(' ');""")
rep("""  if (day.timeoff_hours) parts.push(`списано ${hours(day.timeoff_hours)} ч`);""",
    """  if (day.timeoff_hours) parts.push(`списано ${hours(day.timeoff_hours)} ч`);
  if (day.is_double) parts.push(`×2 ${day.double_reason === 'vip' ? 'ВИП-гость' : 'двойная оплата'}`);""")

# ── 6. панель «Переработки к выплате»: подсказка, колонки, фильтр, итоги ──
rep("""      <p class="hint" style="margin:-6px 0 10px">Начислено: ранние приходы, поздние уходы, работа в выходной (ДЯ/ДН).
      Списано: опоздания, ранние уходы, выходные за часы — вычитаются сначала из дневных часов ранних дней, затем из ночных.
      Итог («к выплате») — это то, что вносится в систему учёта зарплаты: кнопка «CSV (в учёт з/п)» или лист
      «В учёт зарплаты» в Excel; журнал зачёта — кнопка «зачёт».</p>""",
    """      <p class="hint" style="margin:-6px 0 10px">Начислено: ранние приходы, поздние уходы, работа в выходной (ДЯ/ДН).
      В дни двойной оплаты (производственный календарь, ВИП-гости) переработки идут кодами <b class="dbl">ДЯ2/ДН2</b> — двойной тариф.
      Списано: опоздания, ранние уходы, выходные за часы — вычитаются сначала из дневных часов ранних дней, затем из ночных;
      из двойных часов списание снимается вполовину (8 часов оплаты = 4 часа ДЯ2).
      «Всего» — в одинарных часах: час ДЯ2/ДН2 считается как два. Итог — это то, что вносится в систему учёта зарплаты:
      кнопка «CSV (в учёт з/п)» или лист «В учёт зарплаты» в Excel; журнал зачёта — кнопка «зачёт».</p>""")
rep("""          <th>Сотрудник</th><th>Начислено ДЯ</th><th>Начислено ДН</th><th>Списано</th>
          <th>К выплате ДЯ</th><th>К выплате ДН</th><th>Всего</th><th></th>""",
    """          <th>Сотрудник</th><th>Начислено</th><th>Списано</th>
          <th>К выплате</th><th title="ДЯ2/ДН2 учтены по двойному тарифу">Всего</th><th></th>""")
rep("""        ${state.overtime.rows.filter(r => r.totals.credit_dya || r.totals.credit_dn || r.totals.debit).map(r => `<tr>""",
    """        ${state.overtime.rows.filter(r => r.totals.credit_dya || r.totals.credit_dn || r.totals.credit_dya2 || r.totals.credit_dn2 || r.totals.debit).map(r => `<tr>""")
rep("""          <td class="num" data-label="Начислено ДЯ">${hours(r.totals.credit_dya)}</td>
          <td class="num" data-label="Начислено ДН">${hours(r.totals.credit_dn)}</td>""",
    """          <td class="num" data-label="Начислено">${payCodes(r.totals, 'credit_')}</td>""")
rep("""          <td class="num" data-label="К выплате ДЯ"><b>${hours(r.totals.pay_dya)}</b></td>
          <td class="num" data-label="К выплате ДН"><b style="color:#3d55c8">${hours(r.totals.pay_dn)}</b></td>
          <td class="num" data-label="Всего"><b>${hours(r.totals.pay_total)}</b></td>""",
    """          <td class="num" data-label="К выплате">${payCodes(r.totals, 'pay_')}</td>
          <td class="num" data-label="Всего"><b>${hours(r.totals.pay_total)}</b>${(r.totals.pay_dya2 || r.totals.pay_dn2) ? `<div class="dbl-hint">в т.ч. ×2: ${hours((r.totals.pay_dya2 || 0) + (r.totals.pay_dn2 || 0))} ч</div>` : ''}</td>""")
rep("""|| '<tr><td colspan="8" class="empty">За месяц не было переработок и списаний</td></tr>'}""",
    """|| '<tr><td colspan="6" class="empty">За месяц не было переработок и списаний</td></tr>'}""")

# ── 7. модалка зачёта: начислено/остаток с ДЯ2, журнал с «вполовину», итог ──
rep("""        ${r.credits.map(c => `<div style="font-size:13px;padding:2px 0">${dateRu(c.date)}:
          <b>ДЯ ${hours(c.dya)}</b>${c.dn ? `, <b style="color:#3d55c8">ДН ${hours(c.dn)}</b>` : ''}</div>`).join('') || '<div class="hint">нет</div>'}""",
    """        ${r.credits.map(c => `<div style="font-size:13px;padding:2px 0">${dateRu(c.date)}${(c.dya2 || c.dn2) ? ' <span class="badge warn" title="День двойной оплаты: переработки по двойному тарифу">×2</span>' : ''}: ${creditLine(c)}</div>`).join('') || '<div class="hint">нет</div>'}""")
rep("""        <div class="opt-group-title">Как зачлось (сначала дневные часы ранних дней)</div>
        ${r.log.map(l => `<div style="font-size:13px;padding:2px 0">${esc(l.kind)} ${dateRu(l.debit_date)}
          → ${l.credit_date ? dateRu(l.credit_date) + ' (' + l.from + ')' : 'не покрыто переработками'}: ${hours(l.hours)} ч</div>`).join('') || '<div class="hint">списаний не было</div>'}""",
    """        <div class="opt-group-title">Как зачлось (сначала дневные часы ранних дней; из двойных ДЯ2/ДН2 — вполовину)</div>
        ${r.log.map(l => `<div style="font-size:13px;padding:2px 0">${esc(l.kind)} ${dateRu(l.debit_date)}
          → ${l.credit_date ? dateRu(l.credit_date) + ' (' + l.from + ')' : 'не покрыто переработками'}:
          ${l.credit_date && String(l.from || '').endsWith('2')
            ? `−${hours(l.credit_hours)} ч ${esc(l.from)} <span class="dbl-hint">(= ${hours(l.hours)} ч оплаты)</span>`
            : hours(l.hours) + ' ч'}</div>`).join('') || '<div class="hint">списаний не было</div>'}""")
rep("""        ${r.remain.map(c => `<div style="font-size:13px;padding:2px 0">${dateRu(c.date)}:
          <b>ДЯ ${hours(c.dya)}</b>${c.dn ? `, <b style="color:#3d55c8">ДН ${hours(c.dn)}</b>` : ''}</div>`).join('') || '<div class="hint">всё покрыто списаниями</div>'}""",
    """        ${r.remain.map(c => `<div style="font-size:13px;padding:2px 0">${dateRu(c.date)}${(c.dya2 || c.dn2) ? ' <span class="badge warn">×2</span>' : ''}: ${creditLine(c)}</div>`).join('') || '<div class="hint">всё покрыто списаниями</div>'}""")
rep("""          <span class="v">ДЯ ${hours(r.totals.pay_dya)} + ДН ${hours(r.totals.pay_dn)} = ${hours(r.totals.pay_total)} ч</span></div>`,
      footer: `<button class="btn btn-primary" data-close>Закрыть</button>`,""",
    """          <span class="v">${settleTotalLine(r.totals)}</span></div>`,
      footer: `<button class="btn btn-primary" data-close>Закрыть</button>`,""")

# ── 8. панель настроек «Дни двойной оплаты» — после базового цикла ──
rep("""      <button class="btn btn-primary btn-sm" id="s-base-save" style="margin-top:4px">Сохранить базовый цикл</button>
    </div>

    <div class="panel">
      <h3 class="panel-title">Шаблоны документов (заявления)</h3>""",
    """      <button class="btn btn-primary btn-sm" id="s-base-save" style="margin-top:4px">Сохранить базовый цикл</button>
    </div>

    <div class="panel">
      <h3 class="panel-title">Дни двойной оплаты (производственный календарь) и ВИП-гости</h3>
      <p class="hint" style="margin:-6px 0 10px">В отмеченные дни переработки оплачиваются по двойному тарифу
        и попадают в реестр «Переработки к выплате» кодами <b class="dbl">ДЯ2</b>/<b class="dbl">ДН2</b>.
        Стоимость часов внутри смены не меняется — двойные только переработки; списания, ложащиеся на двойные
        часы, снимаются вполовину (8 часов оплаты = 4 часа ДЯ2). Календарь заполняется из производственного
        календаря / писем C&B — хоть на год вперёд; любая правка сразу пересчитывает затронутые дни табеля.</p>
      <div id="dp-body"><div class="empty">Загрузка…</div></div>
    </div>

    <div class="panel">
      <h3 class="panel-title">Шаблоны документов (заявления)</h3>""")

# ── 9. вызов refreshDoublePay в конце loadSettings + сама функция ──
rep("""  $$('[data-restore]', host).forEach(b => b.onclick = async () => {
    try {
      await api(`/api/shift-types/${b.dataset.restore}/restore`, { method: 'POST' });
      toast('Смена возвращена в словарь', 'ok');
      await loadDirectory(); loadSettings();
    } catch (e) { toast(e.message, 'err'); }
  });
}

/* ── словарь смен: произвольные часы работы ── */""",
    """  $$('[data-restore]', host).forEach(b => b.onclick = async () => {
    try {
      await api(`/api/shift-types/${b.dataset.restore}/restore`, { method: 'POST' });
      toast('Смена возвращена в словарь', 'ok');
      await loadDirectory(); loadSettings();
    } catch (e) { toast(e.message, 'err'); }
  });
  refreshDoublePay();
}

/* ══════════════════════════════════════════════════════════════════
   ДНИ ДВОЙНОЙ ОПЛАТЫ: производственный календарь + ВИП-гости
   ══════════════════════════════════════════════════════════════════ */
const DP_MONTHS = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
                   'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'];
const DP_WD = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];

async function refreshDoublePay() {
  const body = document.querySelector('#dp-body');
  if (!body) return;
  const year = state.dpYear || (state.dpYear = new Date().getFullYear());
  let data;
  try {
    data = await api(`/api/doublepay?year=${year}`, { silent: true });
  } catch (e) {
    body.innerHTML = `<div class="empty">Не загрузилось: ${esc(e.message || e)}</div>`;
    return;
  }
  const canWrite = ['admin', 'manager'].includes(state.user?.role);
  const scopeShort = { shift: 'сменщики', week5: 'пятидневка', all: 'все' };
  const byMonth = {};
  data.days.forEach(d => { (byMonth[d.month] ||= []).push(d); });

  body.innerHTML = `
    <div class="dp-head">
      <div class="month-nav">
        <button id="dp-prev">‹</button><div class="label">${year}</div><button id="dp-next">›</button>
      </div>
      <span class="badge">${data.days.length} ${plural(data.days.length, 'день', 'дня', 'дней')} в календаре</span>
      ${!canWrite ? '<span class="hint" style="margin:0">Править может администратор или менеджер (данные из C&B)</span>' : ''}
    </div>

    ${canWrite ? `
    <div class="dp-form">
      <label class="field"><span>Для кого</span><select id="dp-scope">
        ${data.scopes.map(s => `<option value="${s.id}" ${s.id === 'all' ? 'selected' : ''}>${esc(s.title)}</option>`).join('')}
      </select></label>
      <label class="field"><span>Список дат (через запятую или пробел)</span>
        <input type="text" id="dp-dates" placeholder="01.01.${year}, 07.01.${year}, 23.02.${year}"></label>
      <div class="dp-or">или период</div>
      <label class="field"><span>С</span><input type="date" id="dp-start"></label>
      <label class="field"><span>По</span><input type="date" id="dp-end"></label>
      <div class="field"><span>Дни недели периода (пусто = все)</span>
        <div class="dp-wd">${DP_WD.map((w, i) => `<label><input type="checkbox" value="${i}">${w}</label>`).join('')}</div></div>
      <label class="field"><span>Примечание</span>
        <input type="text" id="dp-note" placeholder="Новогодние праздники · письмо C&B от …"></label>
      <button class="btn btn-primary btn-sm" id="dp-add">Добавить дни</button>
    </div>` : ''}

    ${Object.keys(byMonth).sort((a, b) => a - b).map(m => `
      <div class="opt-group-title">${DP_MONTHS[m - 1]}</div>
      <div class="dp-days">${byMonth[m].map(d => `
        <span class="dp-chip${d.is_weekend ? ' we' : ''}" title="${esc(d.scope_title)}${d.note ? ' · ' + esc(d.note) : ''}">
          <b>${esc(d.weekday)} ${String(d.day).padStart(2, '0')}.${String(d.month).padStart(2, '0')}</b>
          <i>${esc(scopeShort[d.scope] || d.scope)}</i>${d.note ? `<span>${esc(d.note)}</span>` : ''}
          ${canWrite ? `<button class="dp-del" data-day-del="${d.id}" title="Удалить день">×</button>` : ''}
        </span>`).join('')}</div>`).join('')
      || `<div class="empty" style="padding:10px 0">За ${year} год дней пока нет — добавьте из производственного календаря</div>`}

    <div class="opt-group-title" style="margin-top:14px">ВИП-гости: периоды двойных переработок</div>
    <p class="hint" style="margin-top:0">Сотрудник работает с ВИП-гостем — назначьте период, и его переработки в эти дни
      станут двойными (ДЯ2/ДН2), даже если по производственному календарю день обычный.
      Совпадение с календарём тариф не увеличивает — всегда ×2, не ×4.</p>
    ${canWrite ? `
    <div class="dp-form">
      <label class="field"><span>Сотрудник</span><select id="vip-emp">
        ${(state.employees || []).map(e => `<option value="${e.id}">${esc(e.full_name)}</option>`).join('')}
      </select></label>
      <label class="field"><span>С</span><input type="date" id="vip-start"></label>
      <label class="field"><span>По</span><input type="date" id="vip-end"></label>
      <label class="field"><span>Примечание</span><input type="text" id="vip-note" placeholder="ВИП-гость: фамилия / вилла"></label>
      <button class="btn btn-primary btn-sm" id="vip-add">Назначить ×2</button>
    </div>` : ''}
    ${data.vip.length ? data.vip.map(v => `
      <div class="rule-row">
        <div><div class="lbl">${esc(v.employee_full_name || v.employee_name)} ·
          ${dateRu(v.start_date)} – ${dateRu(v.end_date)}
          <span class="badge warn">${v.days} ${plural(v.days, 'день', 'дня', 'дней')}</span></div>
          <div class="desc">${esc(v.note || 'без примечания')}${v.author ? ' · добавил(а): ' + esc(v.author) : ''}</div></div>
        ${canWrite ? `<div class="rule-input"><button class="btn btn-sm btn-danger" data-vip-del="${v.id}">Удалить</button></div>` : ''}
      </div>`).join('') : '<div class="empty" style="padding:10px 0">Периодов нет</div>'}`;

  document.querySelector('#dp-prev').onclick = () => { state.dpYear = year - 1; refreshDoublePay(); };
  document.querySelector('#dp-next').onclick = () => { state.dpYear = year + 1; refreshDoublePay(); };
  if (canWrite) {
    document.querySelector('#dp-add').onclick = async () => {
      const weekdays = [...body.querySelectorAll('.dp-wd input:checked')].map(i => +i.value);
      const payload = {
        dates: document.querySelector('#dp-dates').value.trim(),
        start: document.querySelector('#dp-start').value || null,
        end: document.querySelector('#dp-end').value || null,
        weekdays: weekdays.length ? weekdays : null,
        scope: document.querySelector('#dp-scope').value,
        note: document.querySelector('#dp-note').value.trim(),
      };
      if (!payload.dates && !(payload.start && payload.end))
        return toast('Введите список дат или период', 'warn');
      try {
        const r = await api('/api/doublepay/days', { method: 'POST', body: payload });
        toast(`Добавлено: ${r.added}, обновлено: ${r.updated}. Пересчитано строк табеля: ${r.recalculated}`, 'ok');
        refreshDoublePay();
      } catch (e) { toast(e.message, 'err'); }
    };
    const vipBtn = document.querySelector('#vip-add');
    if (vipBtn) vipBtn.onclick = async () => {
      const payload = {
        employee_id: +document.querySelector('#vip-emp').value,
        start_date: document.querySelector('#vip-start').value,
        end_date: document.querySelector('#vip-end').value,
        note: document.querySelector('#vip-note').value.trim(),
      };
      if (!payload.employee_id || !payload.start_date || !payload.end_date)
        return toast('Выберите сотрудника и укажите даты периода', 'warn');
      try {
        const r = await api('/api/doublepay/vip', { method: 'POST', body: payload });
        toast(`Назначены двойные переработки: ${r.item.days} ${plural(r.item.days, 'день', 'дня', 'дней')}. Пересчитано строк: ${r.recalculated}`, 'ok');
        refreshDoublePay();
      } catch (e) { toast(e.message, 'err'); }
    };
  }
  body.querySelectorAll('[data-day-del]').forEach(b => b.onclick = () => {
    confirmDialog('Удалить день двойной оплаты?',
      'Переработки этого дня снова будут считаться одинарными (ДЯ/ДН). Табель пересчитается автоматически.',
      async () => {
        try {
          const r = await api(`/api/doublepay/days/${b.dataset.dayDel}`, { method: 'DELETE' });
          toast(`День удалён. Пересчитано строк табеля: ${r.recalculated}`, 'ok');
          refreshDoublePay();
        } catch (e) { toast(e.message, 'err'); }
      }, 'Удалить');
  });
  body.querySelectorAll('[data-vip-del]').forEach(b => b.onclick = () => {
    confirmDialog('Удалить ВИП-период?',
      'Переработки сотрудника в эти дни вернутся к обычному тарифу (если день не остался в календаре двойной оплаты).',
      async () => {
        try {
          const r = await api(`/api/doublepay/vip/${b.dataset.vipDel}`, { method: 'DELETE' });
          toast(`Период удалён. Пересчитано строк табеля: ${r.recalculated}`, 'ok');
          refreshDoublePay();
        } catch (e) { toast(e.message, 'err'); }
      }, 'Удалить');
  });
}

/* ── словарь смен: произвольные часы работы ── */""")

assert s.count("$$(") == orig_dollardollar, "число `$$(` изменилось — патч сломал JS!"
open(P, "w", encoding="utf-8").write(s)
print("app.js пропатчен; `$$(` вхождений:", orig_dollardollar, "→", s.count("$$("))
