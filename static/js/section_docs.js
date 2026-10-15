'use strict';
/* ══ ПЕЧАТЬ И ЗАЯВЛЕНИЯ: чистое окно печати, шаблоны, скачивание DOCX/PDF ══
   Вынесено из app.js (15.10.2026) без изменения логики: границы разделов —
   файлами (сборки намеренно нет, ADR-0008), общие функции — через глобальную
   область (реестр tools/js_globals.json, ESLint no-undef ловит пропуски). */

/* ── печать отдельных документов (чистое окно: весь месяц, без служебных элементов) ── */
function printWindow(title, bodyHtml) {
  const w = window.open('', '_blank', 'width=1200,height=800');
  if (!w) { toast('Браузер заблокировал окно печати — разрешите всплывающие окна', 'warn'); return; }
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${esc(title)}</title>
    <style>
      @page { size: A4 landscape; margin: 10mm; }
      body { font-family: -apple-system, 'Segoe UI', Roboto, Arial, sans-serif; color: #1a2438; font-size: 11px; }
      h1 { font-size: 16px; margin: 0 0 2mm; }
      table { border-collapse: collapse; width: 100%; }
      th, td { border: 1px solid #b9c2d0; padding: 1.2mm 1mm; text-align: center; font-size: 9px; }
      th.name, td.name { text-align: left; padding-left: 2mm; width: 52mm; font-size: 10px; }
      tr.group td { background: #eef2f8; font-weight: 700; text-align: left; padding-left: 2mm; font-size: 10px; }
      .muted { color: #8b98ad; }
    </style></head><body>${bodyHtml}<script>window.onload = () => { window.print(); };<\/script></body></html>`);
  w.document.close();
}


/* ── заявление на отпуск: печать по редактируемому шаблону, период подхватывается целиком ── */
async function getDocTemplates() {
  if (!state.doc) {
    const s = await api('/api/settings', { silent: true });
    state.doc = s.doc;
  }
  try {
    const kd = await api('/api/docs/kinds', { silent: true });
    state.docKinds = kd.kinds || []; state.docPlaceholders = kd.placeholders || {};
  } catch { /* печать продолжим с кешем */ }
  return state.doc;
}

function fillTemplate(tpl, values) {
  return (tpl || '').replace(/\{(\w+)\}/g, (m, k) => (values[k] ?? m));
}

/* Документы по отсутствию: период берётся с сервера ЦЕЛИКОМ — даже когда отпуск
   начинается в одном месяце, а заканчивается в следующем (исправление бага печати). */
async function absencePeriodInfo(empId, dateISO) {
  return await api(`/api/schedule/absence-period?employee_id=${empId}&date=${dateISO}`);
}

/* Заявление печатается из своего слоя (Q4, норматив 12.10.2026): отпуск, больничный,
   за свой счёт и оплачиваемый выходной — коды Табеля (первичный документ, слой 0),
   а «отпросился (выходной за часы)» — данные Графика (слой 1). Сервер сообщает источник
   в `source`; кнопка не того слоя объясняет, куда идти, а не печатает чужой документ. */
function statementLayerOk(p, layer) {
  if (!layer || !p.source || p.source === layer) return true;
  toast(p.source === 'tabel_code'
    ? 'Это отсутствие — код Табеля (отпуск, больничный, отгул): заявление печатается из раздела «Табель», из ячейки дня'
    : '«Отпросился (выходной за часы)» — данные Графика: заявление печатается из ячейки дня в разделе «График»',
    'warn');
  return false;
}

function triggerDownload(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

/* DOCX/PDF из корпоративного шаблона (Настройки → Шаблоны документов компании).
   PDF собирается на сервере (LibreOffice или встроенный рендер) и открывается в новой
   вкладке — из неё сразу можно печатать. */
async function downloadAbsenceDoc(empId, dateISO, fmt, layer = '') {
  let p;
  try { p = await absencePeriodInfo(empId, dateISO); }
  catch (e) {
    return toast(e.message.includes('нет назначенного')
      ? 'Сначала сохраните отсутствие в ячейке — тогда станет доступна печать заявления'
      : e.message, 'err');
  }
  if (!statementLayerOk(p, layer)) return;
  /* Вид заявления определяет сервер: у единого «отпросился (выходной за часы)» он
     зависит от точки ввода — вся смена или интервал (Q3). */
  const type = p.doc_type || p.shift?.doc_type;
  if (!type) return toast('К этому виду отсутствия не привязан шаблон заявления (Настройки → Словарь смен)', 'warn');
  loading(true);
  try {
    const res = await fetch('/api/docs/render', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCookie('tt_csrf') },
      body: JSON.stringify({
        type, employee_id: empId, date_from: p.start, date_to: p.end, format: fmt,
        from_time: p.partial?.from_time || '', until_time: p.partial?.until_time || '',
        hours: p.hours != null ? p.hours : null,
        reason: p.partial?.reason?.name || p.shift?.name || '',
        note: (p.notes || []).join('; '),
      }),
    });
    if (!res.ok) {
      let msg = `Ошибка ${res.status}`;
      try { msg = (await res.json()).detail || msg; } catch {}
      throw new Error(msg);
    }
    const blob = await res.blob();
    const name = (res.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/)?.[1]
      || `document_${empId}.${fmt}`;
    if (fmt === 'pdf') {
      const url = URL.createObjectURL(blob);
      const w = window.open(url, '_blank');
      if (!w) {
        toast('Браузер заблокировал новое окно — PDF скачан файлом; разрешите всплывающие окна для печати', 'warn');
        triggerDownload(blob, name);
      } else {
        setTimeout(() => URL.revokeObjectURL(url), 120000);
        toast('PDF готов — открыт в новой вкладке, можно печатать', 'ok');
      }
    } else {
      triggerDownload(blob, name);
      toast('Документ DOCX скачан — откройте его в Word и печатайте', 'ok');
    }
  } catch (e) { toast(e.message, 'err'); }
  finally { loading(false); }
}

/* Быстрая печать заявления окном браузера (по редактируемому шаблону из Настроек) */
async function printAbsenceRequest(empId, dateISO, layer = '') {
  let p;
  try { p = await absencePeriodInfo(empId, dateISO); }
  catch (e) {
    return toast(e.message.includes('нет назначенного')
      ? 'Сначала сохраните отсутствие в ячейке — тогда станет доступна печать заявления'
      : e.message, 'err');
  }
  if (!statementLayerOk(p, layer)) return;
  try {
    const docType = p.doc_type || p.shift?.doc_type;
    const doc = await getDocTemplates();
    const kind = (state.docKinds || []).find(k => k.code === docType);
    const tplKey = { vacation_paid: 'vacation', vacation_unpaid: 'vacation_unpaid',
                     day_off_hours: 'day_off_hours', time_off_request: 'time_off_request' }[docType]
      || 'vacation';
    const tplText = (kind?.text || '').trim() || doc[tplKey] || doc.vacation;
    const e = p.employee || {};
    const vals = {
      company: doc.company, director: doc.director,
      full_name: e.full_name || '', short_name: e.short_name || '',
      full_name_genitive: e.full_name_genitive || e.full_name || '',
      position: e.position || '—', tab_number: e.tab_number || '—',
      nationality: e.nationality || '', subdivision: e.subdivision || '', department: e.department || '',
      group: e.subdivision || '',
      date_from: dateRu(p.start), date_to: dateRu(p.end), days: p.days,
      from_time: p.partial?.from_time || '', until_time: p.partial?.until_time || '',
      /* Часы отсутствия: сервер считает их по стандартному окну смен сотрудника
         (для «выходного за часы» — не длина записи, а норма его смены). */
      hours: p.hours != null ? hours(p.hours) : '',
      period: p.end === p.start ? dateRu(p.start) : `с ${dateRu(p.start)} по ${dateRu(p.end)}`,
      reason: p.partial?.reason?.name || p.shift?.name || '',
      note: (p.notes || []).join('; '),
      today: dateRu(todayISO()),
    };
    printWindow('Заявление',
      `<div style="white-space:pre-wrap;font-size:13px;line-height:1.7;width:170mm;margin:0 auto">${esc(fillTemplate(tplText, vals))}</div>`);
  } catch (e) { toast(e.message, 'err'); }
}

