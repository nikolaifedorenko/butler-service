'use strict';
/* ══ ПЕЧАТЬ И ЗАЯВЛЕНИЯ: чистое окно печати, шаблоны, скачивание DOCX/PDF ══
   Вынесено из app.js без изменения логики: границы разделов —
   файлами (сборки намеренно нет, ADR-0008). Модуль (ADR-0013, раздел 7). Окно печати —
   отдельный документ, который собирается строкой с esc(): в страницу приложения она не попадает. */

import { api, authContextIsCurrent, authContextSnapshot, dateRu, esc, expireAuthContext, getCookie, hours, loading, state,
  subscribeAuthContext, subscribeSessionRejection, todayISO, toast } from '../core.js';

/* ── печать отдельных документов (чистое окно: весь месяц, без служебных элементов) ──
   Страницу собирает сервер (POST /api/docs/print): прежний document.write в about:blank
   с inline-скриптом автопечати блокировался CSP (A1, аудит 25.10.2026). Документ
   показывается в скрытом фрейме; автопечать делает внешний скрипт страницы, после
   диалога фрейм удаляется по сообщению от него. */
const printJobs = new Set();
function cancelPrintJobs() {
  for (const cleanup of printJobs) cleanup();
}
subscribeAuthContext(cancelPrintJobs);
subscribeSessionRejection(cancelPrintJobs);

export async function printWindow(title, bodyHtml, extraCss = '', started = authContextSnapshot()) {
  if (!authContextIsCurrent(started)) return;
  const controller = new AbortController();
  const request = { credentials: 'same-origin', cache: 'no-store', signal: controller.signal };
  let frame, fallback, interval, requestTimeout;
  let validating = false;
  let foregroundPending = false;

  function cleanup() {
    if (!printJobs.delete(cleanup)) return;
    controller.abort();
    window.removeEventListener('message', onDone);
    window.removeEventListener('focus', onForeground);
    window.removeEventListener('pageshow', onForeground);
    document.removeEventListener('visibilitychange', onVisible);
    clearTimeout(fallback);
    clearTimeout(requestTimeout);
    clearInterval(interval);
    frame?.remove();
  }
  function onDone(e) {
    if (e.origin === location.origin && e.source === frame.contentWindow && e.data?.butler_print_done) cleanup();
  }
  function onVisible() {
    if (!document.hidden) onForeground();
  }
  function onForeground() {
    if (validating) foregroundPending = true;
    else void validateMounted();
  }
  function current() {
    return !controller.signal.aborted && authContextIsCurrent(started);
  }
  async function serverMatches() {
    const r = await fetch('/api/auth/context', request);
    if (r.status === 401 && !controller.signal.aborted) expireAuthContext(started);
    return r.ok && (await r.json()).auth_context === started.context;
  }
  async function validateMounted() {
    if (!current()) { cleanup(); return; }
    if (validating) return;
    validating = true;
    requestTimeout = setTimeout(cleanup, 20_000);
    try {
      if (!await serverMatches() || !current()) cleanup();
    } catch { cleanup(); }
    finally {
      clearTimeout(requestTimeout);
      validating = false;
      if (foregroundPending && !controller.signal.aborted) {
        foregroundPending = false;
        void validateMounted();
      }
    }
  }

  printJobs.add(cleanup);
  requestTimeout = setTimeout(cleanup, 20_000);
  try {
    const r = await fetch('/api/docs/print', {
      ...request, method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCookie('tt_csrf') },
      body: JSON.stringify({ title, body: bodyHtml, css: extraCss }),
    });
    if (r.status === 401 && !controller.signal.aborted) expireAuthContext(started);
    if (!r.ok) throw new Error(`Ошибка ${r.status}`);
    if (r.headers.get('X-Butler-Auth-Context') !== started.context || !current()) { cleanup(); return; }
    const html = await r.text();
    if (!await serverMatches() || !current()) { cleanup(); return; }
    clearTimeout(requestTimeout);

    frame = document.createElement('iframe');
    frame.setAttribute('aria-hidden', 'true');
    frame.title = title;
    Object.assign(frame.style, { position: 'fixed', top: '0', left: '-10000px', width: '1px', height: '1px',
      border: '0' });
    frame.srcdoc = html;
    window.addEventListener('message', onDone);
    window.addEventListener('focus', onForeground);
    window.addEventListener('pageshow', onForeground);
    document.addEventListener('visibilitychange', onVisible);
    fallback = setTimeout(cleanup, 5 * 60 * 1000);
    interval = setInterval(validateMounted, 5_000);
    if (!current()) { cleanup(); return; }
    document.body.appendChild(frame);
  } catch (e) {
    const cancelled = controller.signal.aborted;
    cleanup();
    if (!cancelled) toast(`Печать не подготовилась — ${e.message}`, 'warn');
  }
}


/* ── заявление на отпуск: печать по редактируемому шаблону, период подхватывается целиком ── */
async function getDocTemplates(started) {
  if (!state.doc) {
    const s = await api('/api/settings', { silent: true });
    if (!authContextIsCurrent(started)) return;
    state.doc = s.doc;
  }
  try {
    const kd = await api('/api/docs/kinds', { silent: true });
    if (!authContextIsCurrent(started)) return;
    state.docKinds = kd.kinds || []; state.docPlaceholders = kd.placeholders || {};
  } catch { /* печать продолжим с кешем */ }
  return state.doc;
}

function fillTemplate(tpl, values) {
  return (tpl || '').replace(/\{(\w+)\}/g, (m, k) => (values[k] ?? m));
}

/* Документы по отсутствию: период берётся с сервера ЦЕЛИКОМ — даже когда отпуск
   начинается в одном месяце, а заканчивается в следующем (исправление бага печати).
   absenceId — печать заявления по ОДНОМУ интервалу отлучки (без него сервер отдаёт
   все интервалы дня одним периодом: перечнем в `intervals_text`). */
async function absencePeriodInfo(empId, dateISO, absenceId = null) {
  return await api(`/api/schedule/absence-period?employee_id=${empId}&date=${dateISO}`
    + (absenceId ? `&absence_id=${absenceId}` : ''));
}

/* Заявление печатается из своего слоя: отпуск, больничный,
   за свой счёт и оплачиваемый выходной — коды Табеля (первичный документ, слой 0),
   а «отпросился (выходной за часы)» — данные Графика (слой 1). Сервер сообщает источник
   в `source`; кнопка не того слоя объясняет, куда идти, а не печатает чужой документ. */
export function statementLayerOk(p, layer) {
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
   PDF собирается на сервере встроенным рендером и открывается в новой
   вкладке — из неё сразу можно печатать. */
export async function downloadAbsenceDoc(empId, dateISO, fmt, layer = '', absenceId = null) {
  let p;
  try { p = await absencePeriodInfo(empId, dateISO, absenceId); }
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
        /* перечень интервалов одной строкой — для заявления «об отсутствии на рабочем
           месте»: сервер печатает несколько отлучек одним документом */
        intervals: p.intervals_text || '',
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
export async function printAbsenceRequest(empId, dateISO, layer = '', absenceId = null) {
  const started = authContextSnapshot();
  if (!authContextIsCurrent(started)) return;
  let p;
  try { p = await absencePeriodInfo(empId, dateISO, absenceId); }
  catch (e) {
    if (!authContextIsCurrent(started)) return;
    return toast(e.message.includes('нет назначенного')
      ? 'Сначала сохраните отсутствие в ячейке — тогда станет доступна печать заявления'
      : e.message, 'err');
  }
  if (!authContextIsCurrent(started) || !statementLayerOk(p, layer)) return;
  try {
    const docType = p.doc_type || p.shift?.doc_type;
    const doc = await getDocTemplates(started);
    if (!authContextIsCurrent(started)) return;
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
      /* перечень интервалов одной строкой («с 14:00 до 16:00 (2 ч) и с 18:00 до
         20:00 (2 ч)») — шаблон «об отсутствии» печатает несколько отлучек одним
         заявлением; для одиночных периодов сервер собирает строку из from/until */
      intervals: p.intervals_text || (p.partial && p.partial.from_time
        ? `с ${p.partial.from_time} до ${p.partial.until_time}${p.hours != null ? ` (${hours(p.hours)} ч)` : ''}`
        : ''),
      /* Часы отсутствия: сервер считает их по стандартному окну смен сотрудника
         (для «выходного за часы» — не длина записи, а норма его смены). */
      hours: p.hours != null ? hours(p.hours) : '',
      period: p.end === p.start ? dateRu(p.start) : `с ${dateRu(p.start)} по ${dateRu(p.end)}`,
      reason: p.partial?.reason?.name || p.shift?.name || '',
      note: (p.notes || []).join('; '),
      today: dateRu(todayISO()),
    };
    await printWindow('Заявление',
      `<div style="white-space:pre-wrap;font-size:13px;line-height:1.7;width:170mm;margin:0 auto">${esc(fillTemplate(tplText, vals))}</div>`, '', started);
  } catch (e) { toast(e.message, 'err'); }
}
