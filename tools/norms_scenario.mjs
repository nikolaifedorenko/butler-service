/* Сценарий норматива «График = 4 слоя» (решения владельца 12.10.2026): jsdom + РЕАЛЬНЫЙ
сервер, без браузера. Покрывает батч T1+T3+T4 из docs/REVIEW-GRAFIK-4-SLOYA-2026-10-12.md:

  T1 — редактор смены: «код в сетке» (подпись) и «код в табеле» (ТОЛЬКО выбор из
       справочника CFG-DAY-CODES или пусто); API отклоняет чужой код (422); health
       без APP-SHIFT-CODE;
  T3 — «Сбросить» в Табеле: ручной код уходит, день снова заполняется из циклов,
       закрытые периоды не трогаются, действие аудируется (см. audit «tabel_reset»);
  T4 — «Отпросился (выходной за часы)» — ОДНА сущность словаря с двумя точками ввода
       (интервал / вся смена); из Графика назначаются только виды «за счёт часов»,
       отпуск/ДО/Б/ОВ — коды Табеля из раздела «Табель»; заявления печатаются из своего
       слоя: вся смена → «выходной за ранее отработанные часы», интервал → «об отсутствии
       на рабочем месте», а кнопка не того слоя объясняет, куда идти (statementLayerOk).

Запуск: tools/run_norms_scenario.sh [порт] [логин]   (нужен jsdom: npm i)
Код возврата: 0 — сценарий пройден, 2 — есть проваленные проверки. */
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { fileURLToPath } from 'node:url';
import { JSDOM, VirtualConsole } from 'jsdom';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const BASE = process.argv[2] || 'http://127.0.0.1:8195';
const LOGIN = process.argv[3] || 'admin';

const consoleErrors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => consoleErrors.push('[jsdomError] ' + String(e.stack || e.message).split('\n')[0]));
vc.on('error', (...a) => consoleErrors.push('[console.error] ' + a.map(String).join(' ')));

const html = fs.readFileSync(path.join(ROOT, 'static/index.html'), 'utf8');
const jar = new Map();
function proxy(method, url, { body, headers } = {}) {
  return new Promise((resolve, reject) => {
    const u = new URL(url, BASE);
    const req = http.request({
      hostname: u.hostname, port: u.port, path: u.pathname + u.search, method,
      headers: {
        ...(headers || {}),
        ...(jar.size ? { Cookie: [...jar].map(([k, v]) => `${k}=${v}`).join('; ') } : {}),
        ...(body ? { 'Content-Length': Buffer.byteLength(body) } : {}),
      },
    }, res => {
      (res.headers['set-cookie'] || []).forEach(c => {
        const [kv] = c.split(';'); const i = kv.indexOf('=');
        jar.set(kv.slice(0, i), kv.slice(i + 1));
      });
      const chunks = [];
      res.on('data', d => chunks.push(d));
      res.on('end', () => {
        const text = Buffer.concat(chunks).toString('utf8');
        resolve({ status: res.statusCode, ok: res.statusCode < 400, headers: res.headers,
          text: async () => text, json: async () => JSON.parse(text) });
      });
    });
    req.on('error', e => { console.error('PROXY ERROR', method, u.pathname, e.code || e.message); reject(e); });
    if (body) req.write(body);
    req.end();
  });
}

const dom = new JSDOM(html, { url: BASE + '/', runScripts: 'dangerously',
  pretendToBeVisual: true, virtualConsole: vc });
const { window } = dom;
window.fetch = (url, init = {}) => proxy(init.method || 'GET', url,
  { body: typeof init.body === 'string' ? init.body : undefined, headers: init.headers });
window.URL.createObjectURL = () => 'blob:stub';
window.URL.revokeObjectURL = () => {};
window.print = () => {};
window.scrollTo = () => {};
window.alert = () => {};
window.confirm = () => true;
window.matchMedia = window.matchMedia || (q => ({ matches: false, media: q, addListener() {},
  removeListener() {}, addEventListener() {}, removeEventListener() {} }));
window.addEventListener('error', e => consoleErrors.push('[window.onerror] ' + String(e.error?.stack || e.message).split('\n')[0]));
window.addEventListener('unhandledrejection', e => consoleErrors.push('[unhandledrejection] ' + String(e.reason?.message || e.reason)));
window.Element.prototype.scrollTo = function () {};
window.HTMLElement.prototype.scrollIntoView = function () {};

for (const src of [...html.matchAll(/<script src="([^"]+)"><\/script>/g)].map(m => m[1])) {
  const file = path.join(ROOT, src.split('?v=')[0].replace(/^\//, ''));
  const sc = window.document.createElement('script');
  sc.textContent = fs.readFileSync(file, 'utf8');
  window.document.body.appendChild(sc);
}

const $ = s => window.document.querySelector(s);
const $$ = s => [...window.document.querySelectorAll(s)];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const text = s => ($(s)?.textContent || '').replace(/\s+/g, ' ').trim();
const click = el => el?.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
const change = (el, value) => { if (!el) return; if (value !== undefined) el.value = value;
  el.dispatchEvent(new window.Event('change', { bubbles: true })); };
const input = (el, value) => { if (!el) return; if (value !== undefined) el.value = value;
  el.dispatchEvent(new window.Event('input', { bubbles: true })); };

/* прямой доступ к API (та же сессионная кука, что у интерфейса) */
const jget = async p => (await proxy('GET', p)).json();
const jsend = async (method, p, obj) => {
  const r = await proxy(method, p, { body: JSON.stringify(obj),
    headers: { 'Content-Type': 'application/json' } });
  let j = null; try { j = JSON.parse(await r.text()); } catch { /* не JSON */ }
  return { status: r.status, ok: r.ok, json: j };
};

let failed = 0, passed = 0;
function check(name, cond, extra = '') {
  if (cond) { passed++; console.log(`  ✓ ${name}`); }
  else { failed++; console.log(`  ❌ ${name}${extra ? ' — ' + extra : ''}`); }
}
async function waitFor(fn, ms = 12000) {
  const t0 = Date.now();
  let last = '';
  while (Date.now() - t0 < ms) {
    try { if (await fn()) return true; } catch (e) { last = String(e.message || e); }
    await sleep(150);
  }
  if (last) console.log(`    (последняя ошибка ожидания: ${last.slice(0, 160)})`);
  return false;
}
const modalOpen = () => !$('#modal-backdrop').classList.contains('hidden') && $('#modal').innerHTML !== '';
/* Табель перерисовывается после каждого сохранения: кликать можно только по готовой
   таблице, иначе сценарий щёлкает по оболочке «Загрузка…» (гонка) */
const tabelReady = () => waitFor(() => $('#tb-body table') && $$('#tb-body td.v4-cell').length > 0, 15000);
const modalClosed = () => $('#modal-backdrop').classList.contains('hidden');
const toasts = () => text('#toast-host');

async function main() {
  /* печать заявлений проверяем по содержимому: перехватываем printWindow */
  const printed = [];
  window.printWindow = (t, h) => printed.push({ t, h });

  await sleep(400);
  $('#login-username').value = LOGIN;
  $('#login-password').value = 'demo1234';
  $('#login-form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await waitFor(() => !$('#app').classList.contains('hidden'), 30000);
  check('вход выполнен', !$('#app').classList.contains('hidden'), text('#login-error'));
  await sleep(500);

  const Y = window.eval('state.year'), M = window.eval('state.month');
  const tabel = await jget(`/api/tabel?year=${Y}&month=${M}`);
  check('Табель периода доступен', tabel.ok !== false && (tabel.rows || []).length > 0);

  /* целевой сотрудник: период открыт, дни заполнены из циклов */
  const row = tabel.rows.find(r => r.lock !== 'locked' && r.lock !== 'last_closed'
    && tabel.days.some(d => r.cells[d]?.source === 'cycle'));
  check('есть сотрудник с открытым периодом и автозаполнением', !!row);
  const daysWithCell = tabel.days.filter(d => row && row.cells[d]);
  const dayA = daysWithCell.find(d => row.cells[d].source === 'cycle') || daysWithCell[0];
  const dayB = daysWithCell.find(d => d > dayA);
  const empId = row.employee.id;

  /* ── 1. Табель: кнопки слоя 0 (T3 + Q4) ── */
  console.log('\n1 · Табель: «Сбросить» и «Назначить отсутствие»');
  window.navigate('timesheet');
  check('Табель отрисован', await waitFor(() => $('#tb-body table') && $$('#tb-body td.v4-cell').length > 0));
  check('кнопка «Сбросить» видна редактору', !!$('#tb-reset') && $('#tb-reset').style.display !== 'none');
  check('кнопка «Назначить отсутствие» видна', !!$('#tb-absence') && $('#tb-absence').style.display !== 'none');
  click($('#tb-reset'));
  check('модалка сброса открылась', await waitFor(() => !!$('#tr-emp')));
  check('сброс объясняет ручные коды и закрытые периоды',
    /введённые вручную/.test(text('#modal')) && /Закрытые периоды не трогаются/.test(text('#modal')));
  check('счётчик ручных ячеек показан', /Сейчас вручную заполнено ячеек/.test(text('#modal')));
  check('можно сбросить всех или одного', $$('#tr-emp option').length > 1);
  click($('#modal [data-cancel]'));
  await waitFor(modalClosed);

  /* ── 2. T3 E2E: ручной код → «Сбросить» → снова из циклов ── */
  console.log('\n2 · T3: ручной код и возврат автозаполнения');
  await tabelReady();
  click($(`#tb-body td.v4-cell.edit[data-e="${empId}"][data-d="${dayA}"]`));
  check('модалка ячейки Табеля открылась', await waitFor(() => !!$('#tc-chips')));
  check('значения — плашки справочников, ручного ввода часов нет',
    $$('#tc-chips .tc-chip[data-code]').length >= 5 && !$('#tc-code') && !$('#tc-hours'));
  check('текущее значение ячейки предвыбрано плашкой',
    $$('#tc-chips .tc-chip.sel').length === 1, text('#tc-sel').slice(0, 120));
  check('у плашки с часами в подсказке — окно CFG-WINDOWS',
    /окно \d{2}:\d{2}–\d{2}:\d{2}/.test($$('#tc-chips .tc-chip[data-code]')
      .find(b => b.dataset.hours !== '0')?.title || ''),
    $$('#tc-chips .tc-chip[data-code]').find(b => b.dataset.hours !== '0')?.title || '');
  click($('#tc-chips .tc-chip[data-code="НН"]'));
  check('выбранная плашка подсвечена и показана строкой',
    $('#tc-chips .tc-chip[data-code="НН"]').classList.contains('sel')
    && $$('#tc-chips .tc-chip.sel').length === 1 && /НН/.test(text('#tc-sel')), text('#tc-sel').slice(0, 120));
  click($('#modal [data-save]'));
  check('ручной код сохранён', await waitFor(async () =>
    (await jget(`/api/tabel?year=${Y}&month=${M}`)).rows
      .find(r => r.employee.id === empId).cells[dayA]?.source === 'manual'), 15000);
  check('после сохранения модалка ячейки осталась открытой (16.10.2026)',
    modalOpen() && await waitFor(() => /НН/.test(text('#tc-sel')), 10000), text('#tc-sel').slice(0, 100));
  click($('#modal [data-cancel]'));
  await waitFor(modalClosed);

  await tabelReady();
  click($('#tb-reset'));
  await waitFor(() => !!$('#tr-emp'));
  change($('#tr-emp'), String(empId));
  click($('#modal [data-ok]'));
  check('подтверждение сброса появилось', await waitFor(() => !!$('#modal [data-yes]')));
  click($('#modal [data-yes]'));
  check('ячейка снова заполнена из циклов', await waitFor(async () => {
    const c = (await jget(`/api/tabel?year=${Y}&month=${M}`)).rows
      .find(r => r.employee.id === empId).cells[dayA];
    return c && c.source !== 'manual';
  }), 15000);
  check('итог сброса показан тостом', await waitFor(() => /очищено ручных ячеек/.test(toasts())
    && /заполнено из циклов/.test(toasts()), 8000), toasts().slice(0, 160));

  /* ── 3. Q4: отпуск — код Табеля, заявление печатается ИЗ ТАБЕЛЯ ── */
  console.log('\n3 · Q4: заявление по коду Табеля печатается из Табеля');
  check('есть второй день для кода отсутствия', !!dayB);
  await tabelReady();
  click($(`#tb-body td.v4-cell.edit[data-e="${empId}"][data-d="${dayB}"]`));
  check('модалка второго дня открылась', await waitFor(() => !!$('#tc-chips')));
  check('блок заявления скрыт, пока не выбран код отсутствия',
    $('#tc-doc-wrap') && $('#tc-doc-wrap').style.display === 'none');
  click($('#tc-chips .tc-chip[data-code="ОТ"]'));
  check('для кода «ОТ» появился блок заявления', await waitFor(() => $('#tc-doc-wrap')
    && $('#tc-doc-wrap').style.display !== 'none' && /Отпуск/i.test(text('#tc-doc-name'))),
  text('#tc-doc-name'));
  click($('#modal [data-save]'));
  check('код «ОТ» сохранён', await waitFor(async () =>
    (await jget(`/api/tabel?year=${Y}&month=${M}`)).rows
      .find(r => r.employee.id === empId).cells[dayB]?.code === 'ОТ'), 15000);

  check('после сохранения модалка осталась открытой, заявление доступно сразу',
    modalOpen() && await waitFor(() => $('#tc-doc-wrap')
      && $('#tc-doc-wrap').style.display !== 'none' && !!$('#tc-print'), 15000));
  check('сохранённое значение «ОТ» предвыбрано плашкой', /ОТ/.test(text('#tc-sel')),
    text('#tc-sel').slice(0, 100));
  const before = printed.length;
  click($('#tc-print'));
  check('заявление на отпуск напечатано из Табеля', await waitFor(() => printed.length > before),
    `перехвачено ${printed.length - before}`);
  check('в заявлении — сотрудник и вид', /Отпуск/i.test(printed.at(-1)?.h || '')
    || (printed.at(-1)?.h || '').length > 100, (printed.at(-1)?.h || '').slice(0, 120));
  click($('#modal [data-cancel]'));
  await waitFor(modalClosed);

  const ap = await jsend('GET', `/api/schedule/absence-period?employee_id=${empId}&date=${dayB}`);
  check('absence-period: источник — код Табеля', ap.ok && ap.json?.source === 'tabel_code'
    && ap.json?.whole_shift === true && ap.json?.doc_type === 'vacation_paid',
  JSON.stringify(ap.json || ap.status).slice(0, 160));

  /* guard: кнопка чужого слоя не печатает, а объясняет (statementLayerOk) */
  check('statementLayerOk: чужой слой отклоняется',
    window.eval(`statementLayerOk({source:'tabel_code'},'schedule_absence')`) === false);
  check('пояснение, куда идти за заявлением', /из раздела «Табель»/.test(toasts()), toasts().slice(0, 200));
  check('statementLayerOk: свой слой проходит',
    window.eval(`statementLayerOk({source:'tabel_code'},'tabel_code')`) === true
    && window.eval(`statementLayerOk({source:'schedule_absence'},'schedule_absence')`) === true);

  /* ── 4. Q4: из Табеля назначаются только коды первичного документа ── */
  console.log('\n4 · Q4: «Назначить отсутствие» из Табеля — только виды с кодом');
  await tabelReady();
  click($('#tb-absence'));
  check('модалка периода открылась', await waitFor(() => !!$('#rg-shift')));
  check('заголовок — слой 0', /Назначить отсутствие \(код Табеля\)/.test(text('#modal')));
  const tabelKinds = $$('#rg-shift option').map(o => o.textContent);
  check('виды — только с кодом Табеля', tabelKinds.length > 0
    && tabelKinds.every(t => /код Табеля «.+»/.test(t)), tabelKinds.join(' | ').slice(0, 200));
  check('«отпросился» из Табеля НЕ назначается', !tabelKinds.some(t => /Отпросился/i.test(t)));
  check('отпуск и больничный в списке', tabelKinds.some(t => /Отпуск/.test(t))
    && tabelKinds.some(t => /Больничный/.test(t)));
  click($('#modal [data-cancel]'));
  await waitFor(modalClosed);

  /* ── 5. T4: из Графика — только «за счёт часов», одна сущность ── */
  console.log('\n5 · T4: «Отпросить (выходной за часы)» из Графика');
  window.navigate('schedule');
  check('График отрисован', await waitFor(() => $$('#grid-host .cellbtn:not([disabled])').length > 0));
  check('кнопка панели — «Отпросить (выходной за часы)»',
    text('#btn-range') === 'Отпросить (выходной за часы)', text('#btn-range'));
  click($('#btn-range'));
  check('модалка «Отпросить» открылась', await waitFor(() => !!$('#rg-shift')));
  const schedKinds = $$('#rg-shift option').map(o => o.textContent.trim());
  check('из Графика — ровно один вид «за счёт часов»', schedKinds.length === 1
    && /Отпросился \(выходной за часы\)/.test(schedKinds[0]), schedKinds.join(' | '));
  check('подсказка про единую сущность', /Единая сущность/.test(text('#rg-mode-hint')),
    text('#rg-mode-hint'));

  /* цель: другой сотрудник, рабочий день по Табелю (код несёт часы) */
  const row2 = tabel.rows.find(r => r.employee.id !== empId && r.lock !== 'locked'
    && tabel.days.some(d => (r.cells[d]?.hours || 0) > 0));
  const dayW = tabel.days.find(d => row2 && (row2.cells[d]?.hours || 0) > 0 && d >= dayA);
  check('цель для «на всю смену» найдена', !!(row2 && dayW));
  const cb = $(`#rg-emps input[value="${row2.employee.id}"]`);
  if (cb) cb.checked = true;
  input($('#rg-from'), dayW); input($('#rg-to'), dayW);
  click($('#modal [data-ok]'));
  check('назначение прошло', await waitFor(() => /Отсутствие назначено/.test(toasts()), 15000),
    toasts().slice(0, 200));
  const ap2 = await jsend('GET', `/api/schedule/absence-period?employee_id=${row2.employee.id}&date=${dayW}`);
  check('вся смена: источник График, документ — выходной за часы',
    ap2.ok && ap2.json?.source === 'schedule_absence' && ap2.json?.whole_shift === true
    && ap2.json?.doc_type === 'day_off_hours' && (ap2.json?.hours || 0) > 0,
  JSON.stringify(ap2.json || ap2.status).slice(0, 200));
  check('Табель остался явкой (часы не меняются — Q8)',
    (await jget(`/api/tabel?year=${Y}&month=${M}`)).rows
      .find(r => r.employee.id === row2.employee.id).cells[dayW]?.code !== 'ОТПР');

  /* ── 6. T4: ячейка Графика — две точки ввода одной сущности ── */
  console.log('\n6 · T4: ячейка Графика, интервал и заявление');
  await waitFor(() => $$('#grid-host .cellbtn:not([disabled])').length > 0);
  click($(`#grid-host .cellbtn[data-emp="${row2.employee.id}"][data-date="${dayW}"]`));
  check('модалка дня открылась', await waitFor(() => !!$('#cell-abs-kind')));
  check('блок — «Отпросился (выходной за часы)»',
    /Отпросился \(выходной за часы\)/.test(text('#modal')));
  check('ручная смена — плашки словаря, выпадающего списка нет',
    !!$('#cell-sh-chips') && !$('#cell-preset')
    && $$('#cell-sh-chips .tc-chip[data-sh]').length >= 3,
    `плашек: ${$$('#cell-sh-chips .tc-chip[data-sh]').length}`);
  const manChip = $('#cell-sh-chips .tc-chip[data-sh="manual"]');
  click(manChip);
  check('плашка «⚙ Вручную» раскрывает ввод времени',
    manChip.classList.contains('sel') && $('#cell-sh-manual').style.display !== 'none');
  const day12Chip = $$('#cell-sh-chips .tc-chip[data-sh]').find(b => /08:00–20:00/.test(b.textContent));
  click(day12Chip);
  check('плашка словарной смены выбирается и скрывает ручной ввод',
    !!day12Chip && day12Chip.classList.contains('sel')
    && $('#cell-sh-manual').style.display === 'none');
  check('«Отпросить на интервал» переименована в «На интервал»',
    text('#cell-abs-save') === 'На интервал', text('#cell-abs-save'));
  check('кнопки отсутствия — основного цвета, как «Сохранить ручную смену»',
    $('#cell-abs-save').classList.contains('btn-primary')
    && $('#cell-abs-shift').classList.contains('btn-primary')
    && $('#cell-sh-save').classList.contains('btn-primary'));
  check('назначенное отсутствие видно в списке', /Удалить/.test(text('#modal')));
  const cellKinds = $$('#cell-abs-kind option').map(o => o.textContent.trim());
  check('в ячейке только виды «за счёт часов»',
    cellKinds.some(t => /Отпросился/.test(t)) && !cellKinds.some(t => /Отпуск|Больничный/.test(t)),
  cellKinds.join(' | '));
  check('две точки ввода: интервал и вся смена', $('#cell-abs-save')
    && text('#cell-abs-save').includes('интервал')
    && $('#cell-abs-shift') && $('#cell-abs-shift').style.display !== 'none');
  check('подсказка про печать из своего слоя', /Из Графика печатается/.test(text('#doc-btns')));
  const before2 = printed.length;
  click($('#doc-print'));
  check('заявление «выходной за часы» напечатано из Графика',
    await waitFor(() => printed.length > before2, 8000));
  click($('#modal [data-cancel]') || $('#modal .x'));
  await waitFor(modalClosed);

  /* интервал (вторая точка ввода той же сущности) — на сидовом отсутствии Иванова */
  const sched = await jget(`/api/schedule?year=${Y}&month=${M}`);
  let ivanov = null, ivanovDay = null;
  for (const r of sched.rows || []) {
    for (const [d, c] of Object.entries(r.cells || {})) {
      /* ищем ИНТЕРВАЛЬНОЕ отсутствие (сид): своё же «на всю смену» из шага 5 — не оно */
      const isOwn = r.employee.id === row2.employee.id && d === dayW;
      if ((c.absences || []).length && !isOwn && !ivanov) { ivanov = r.employee; ivanovDay = d; }
    }
  }
  check('в Графике есть интервальное отсутствие (сид)', !!(ivanov && ivanovDay), ivanovDay || '');
  if (ivanov && ivanovDay) {
    const ap3 = await jsend('GET', `/api/schedule/absence-period?employee_id=${ivanov.id}&date=${ivanovDay}`);
    check('интервал: та же сущность, документ — об отсутствии на рабочем месте',
      ap3.ok && ap3.json?.source === 'schedule_absence' && ap3.json?.whole_shift === false
      && ap3.json?.doc_type === 'time_off_request',
    JSON.stringify(ap3.json || ap3.status).slice(0, 200));
    click($(`#grid-host .cellbtn[data-emp="${ivanov.id}"][data-date="${ivanovDay}"]`));
    check('модалка дня с интервалом открылась', await waitFor(() => !!$('#cell-abs-kind')));
    check('интервал виден в списке отсутствий', /✂/.test(text('#modal')));
    check('часы «выходного за часы» показывает сервер',
      await waitFor(() => /ч/.test(text('#cell-abs-hours')), 8000), text('#cell-abs-hours'));

    /* второй интервал в тот же день: «На интервал» НЕ закрывает модалку (16.10.2026),
       заявление печатается по каждому интервалу и одним — со списком */
    input($('#cell-abs-from'), '18:00');
    input($('#cell-abs-until'), '20:00');
    click($('#cell-abs-save'));
    check('после «На интервал» модалка осталась открытой и обновилась',
      await waitFor(() => /добавлено/i.test(toasts()), 10000)
      && await waitFor(() => $$('#modal [data-abs-del]').length === 2, 15000),
      `кнопок удаления: ${$$('#modal [data-abs-del]').length}`);
    check('у каждого интервала — своя кнопка печати',
      $$('#modal [data-abs-print]').length === 2);
    const apMulti = await jsend('GET', `/api/schedule/absence-period?employee_id=${ivanov.id}&date=${ivanovDay}`);
    check('absence-period: два интервала, сумма часов и перечень',
      apMulti.ok && (apMulti.json?.intervals || []).length === 2
      && apMulti.json?.hours === 4
      && /с 14:00 до 16:00 \(2 ч\) и с 18:00 до 20:00 \(2 ч\)/.test(apMulti.json?.intervals_text || ''),
      JSON.stringify(apMulti.json?.intervals_text || apMulti.status).slice(0, 160));
    const beforeMulti = printed.length;
    click($('#doc-print'));
    check('одно заявление печатает все интервалы списком',
      await waitFor(() => printed.length > beforeMulti, 8000)
      && /14:00/.test(printed.at(-1).h) && /18:00/.test(printed.at(-1).h),
      (printed.at(-1)?.h || '').replace(/<[^>]+>/g, '').slice(0, 220));
    const line18 = $$('#modal .status-line').find(el => /18:00/.test(el.textContent));
    const beforeOne = printed.length;
    click(line18?.querySelector('[data-abs-print]'));
    check('печать по интервалу — в заявлении только он',
      await waitFor(() => printed.length > beforeOne, 8000)
      && /18:00/.test(printed.at(-1).h) && !/14:00/.test(printed.at(-1).h),
      (printed.at(-1)?.h || '').replace(/<[^>]+>/g, '').slice(0, 220));
    click(line18?.querySelector('[data-abs-del]'));
    check('интервал удалён — модалка осталась открытой',
      await waitFor(() => modalOpen() && $$('#modal [data-abs-del]').length === 1, 15000),
      `кнопок удаления: ${$$('#modal [data-abs-del]').length}`);
    click($('#modal [data-cancel]') || $('#modal .x'));
    await waitFor(modalClosed);
  }

  /* удаление назначения из ячейки — сущность снимается целиком */
  click($(`#grid-host .cellbtn[data-emp="${row2.employee.id}"][data-date="${dayW}"]`));
  await waitFor(() => !!$$('#modal [data-abs-del]').length);
  click($('#modal [data-abs-del]'));
  /* структурное ожидание, не тост: текст «Отсутствие удалено» мог остаться в хосте
     от предыдущего удаления (тосты живут ~5 c) — проверка прошла бы до завершения DELETE */
  check('отсутствие удалено — модалка осталась открытой и обновилась',
    await waitFor(() => modalOpen() && $$('#modal [data-abs-del]').length === 0, 15000),
    `кнопок удаления: ${$$('#modal [data-abs-del]').length}, тосты: ${toasts().slice(0, 120)}`);
  click($('#modal [data-cancel]') || $('#modal .x'));
  await waitFor(modalClosed);
  const ap4 = await jsend('GET', `/api/schedule/absence-period?employee_id=${row2.employee.id}&date=${dayW}`);
  check('после удаления absence-period пуст', !ap4.ok || !ap4.json?.source,
    JSON.stringify(ap4.json || '').slice(0, 120));

  /* ── 7. T1: редактор смены — «код в сетке» отдельно, «код в табеле» из справочника ── */
  console.log('\n7 · T1: словарь смен и health');
  const tc = await jsend('GET', '/api/shift-types/tabel-codes');
  const codes = (tc.json?.codes || []).map(c => c.code);
  check('словарь кодов Табеля отдаётся', tc.ok && codes.includes('Я') && codes.includes('ОТ'),
    codes.join(',').slice(0, 120));
  check('код «Я» несёт часы', (tc.json?.codes || []).some(c => c.code === 'Я' && c.carries_hours));

  window.navigate('settings');
  check('Настройки открылись', await waitFor(() => !!$('#st-nav')));
  click($('#st-nav [data-st="shifts"]'));
  check('экран «Смены» отрисован', await waitFor(() => {
    const t = text('#st-body');
    return t && !t.includes('Загрузка…') && /Связь словарей/.test(t);
  }));
  check('правило поля объяснено на экране', /только коды справочника или пустое значение/.test(text('#st-body')));

  click($('#sh-new'));
  check('редактор смены открылся', await waitFor(() => !!$('#sh-tzh'), 20000));
  check('«код в сетке» — свободный текст', !!$('#sh-short'));
  const tzhOpts = $$('#sh-tzh option').map(o => o.value);
  check('«код в табеле» — только справочник или пусто', tzhOpts[0] === ''
    && tzhOpts.includes('Я') && tzhOpts.includes('ОТ') && !tzhOpts.some(v => /\d/.test(v)),
  tzhOpts.join(',').slice(0, 120));
  check('подсказка: пусто — не участвует в автозаполнении',
    /не участвует в автозаполнении/.test(text('#sh-tzh-hint')), text('#sh-tzh-hint'));
  input($('#sh-code'), 'NORM_UI');
  input($('#sh-name'), 'Сценарная смена (нормы)');
  input($('#sh-short'), '08–20');
  change($('#sh-start'), '08:00'); change($('#sh-end'), '20:00');
  change($('#sh-kind'), 'work');
  click($('#modal [data-save]'));
  check('смена без кода Табеля создана', await waitFor(modalClosed, 15000)
    && await waitFor(() => /Словарь смен обновлён/.test(toasts()), 8000), toasts().slice(0, 160));
  const st1 = (await jget('/api/shift-types')).find(s => s.code === 'NORM_UI');
  check('подпись сетки и пустой код Табеля сохранены отдельно',
    st1 && st1.display_code === '08–20' && st1.tzh_code === '',
  JSON.stringify({ d: st1?.display_code, t: st1?.tzh_code }));

  const bad = await jsend('POST', '/api/shift-types', { code: 'NORM_UI2', name: 'Плохая',
    tzh_code: '08-20', kind: 'work', start_time: '08:00', end_time: '20:00' });
  check('API отклоняет код не из справочника (422)', bad.status === 422
    && /CFG-DAY-CODES/.test(bad.json?.detail || ''), `${bad.status} ${bad.json?.detail || ''}`.slice(0, 160));

  check('новая смена видна в списке', await waitFor(() => !!$(`[data-shift="${st1.id}"]`), 15000));
  click($(`[data-shift="${st1.id}"]`));
  check('редактор существующей смены открылся', await waitFor(() => !!$('#sh-tzh'), 20000));
  change($('#sh-tzh'), 'Я');
  check('подсказка: код несёт часы — стандартное окно', /несёт часы/.test(text('#sh-tzh-hint')),
    text('#sh-tzh-hint'));
  click($('#modal [data-save]'));
  check('код Табеля сохранён', await waitFor(modalClosed, 15000)
    && await waitFor(async () => (await jget('/api/shift-types'))
      .find(s => s.code === 'NORM_UI')?.tzh_code === 'Я', 8000));

  const health = await jsend('GET', '/api/engine-settings/health');
  const shiftCodeErrors = (health.json?.checks || []).filter(c => c.code === 'APP-SHIFT-CODE');
  check('health без APP-SHIFT-CODE', health.ok && shiftCodeErrors.length === 0,
    JSON.stringify(shiftCodeErrors).slice(0, 200));

  console.log(`\n=== ошибки консоли ===`);
  const uniq = [...new Set(consoleErrors.map(e => e.slice(0, 240)))];
  uniq.length ? uniq.forEach(e => console.log('  ' + e)) : console.log('  нет');
  failed += uniq.length;
  console.log(`\nИТОГ: проверок пройдено ${passed}, провалено ${failed}`);
  process.exit(failed ? 2 : 0);
}

main().catch(e => { console.error('сценарий:', e); process.exit(1); });
