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
  window.printWindow = (t, h, css) => printed.push({ t, h, css: css || '' });

  await sleep(400);
  const loginRes = await jsend('POST', '/api/auth/login', { username: LOGIN, password: 'demo1234' });
  if (loginRes.ok) window.eval('bootApp()');
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
  check('модалка периода открылась', await waitFor(() => !!$('#rg-code')));
  check('заголовок — слой 0', /Назначить отсутствие \(код Табеля\)/.test(text('#modal')));
  const codesLoaded = await waitFor(() => $$('#rg-code option').some(o => o.value));
  const tabelCodes = $$('#rg-code option').map(o => o.textContent);
  check('отсутствия периодом — коды Табеля без часов (18.10.2026)',
    codesLoaded && tabelCodes.length > 0, tabelCodes.join(' | ').slice(0, 200));
  check('«отпросился» из Табеля НЕ назначается', !tabelCodes.some(t => /Отпросился/i.test(t)));
  check('отпуск в списке кодов', tabelCodes.some(t => /«ОТ»/.test(t)));
  click($('#modal [data-cancel]'));
  await waitFor(modalClosed);

  /* ── 5. T4: из Графика — только «за счёт часов», одна сущность ── */
  console.log('\n5 · T4: «Выходной за часы» из Графика');
  window.navigate('schedule');
  check('График отрисован', await waitFor(() => $$('#grid-host .cellbtn:not([disabled])').length > 0));
  check('в сетке нет итоговой колонки часов (16.10.2026)',
    !$$('#grid-host thead th').some(th => /Итого|Часов/.test(th.textContent)));
  check('кнопка панели — «Выходной за часы»',
    text('#btn-range') === 'Выходной за часы', text('#btn-range'));
  check('кнопка панели — «Сбросить месяц»', text('#btn-clear') === 'Сбросить месяц',
    text('#btn-clear'));
  click($('#btn-range'));
  check('модалка «Выходной за часы» открылась', await waitFor(() => !!$('#rg-from')));
  check('из Графика вид отсутствия НЕ выбирается — он один в словаре',
    !$('#rg-shift') && /Отпросился \(выходной за часы\)/.test(text('#modal')),
    text('#modal').slice(0, 140));
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
  const cellW = $(`#grid-host .cellbtn[data-emp="${row2.employee.id}"][data-date="${dayW}"]`);
  check('отсутствие на всю смену — плашка «Выходной за часы» на всю ячейку',
    !!cellW && /Выходной/.test(cellW.textContent) && /за часы/.test(cellW.textContent),
    cellW ? cellW.textContent.replace(/\s+/g, ' ').slice(0, 80) : 'ячейка не найдена');

  /* ── 6. T4: ячейка Графика — две точки ввода одной сущности ── */
  console.log('\n6 · T4: ячейка Графика, интервал и заявление');
  await waitFor(() => $$('#grid-host .cellbtn:not([disabled])').length > 0);
  click($(`#grid-host .cellbtn[data-emp="${row2.employee.id}"][data-date="${dayW}"]`));
  check('модалка дня открылась', await waitFor(() => !!$('#cell-abs-save')));
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
  check('вид отсутствия в ячейке НЕ выбирается — единственный «за счёт часов»',
    !$('#cell-abs-kind') && /Отпросился \(выходной за часы\)/.test(text('#modal')));
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
    const ivCell = (await jget(`/api/schedule?year=${Y}&month=${M}`)).rows
      .find(r => r.employee.id === ivanov.id)?.cells[ivanovDay] || {};
    const cellIv = $(`#grid-host .cellbtn[data-emp="${ivanov.id}"][data-date="${ivanovDay}"]`);
    if ((ivCell.segments || []).length) {
      check('ячейка — отрезки смены по строкам, без кода Табеля',
        !!cellIv && ivCell.segments.every(s => cellIv.textContent.includes(`${s[0]}–${s[1]}`))
        && !/Я/.test(cellIv.textContent),
        cellIv ? cellIv.textContent.replace(/\s+/g, ' ').slice(0, 90) : 'ячейка не найдена');
    } else {
      check('ячейка без смены показывает код Табеля', !!cellIv, cellIv?.textContent || '');
    }
    const ap3 = await jsend('GET', `/api/schedule/absence-period?employee_id=${ivanov.id}&date=${ivanovDay}`);
    check('интервал: та же сущность, документ — об отсутствии на рабочем месте',
      ap3.ok && ap3.json?.source === 'schedule_absence' && ap3.json?.whole_shift === false
      && ap3.json?.doc_type === 'time_off_request',
    JSON.stringify(ap3.json || ap3.status).slice(0, 200));
    click($(`#grid-host .cellbtn[data-emp="${ivanov.id}"][data-date="${ivanovDay}"]`));
    check('модалка дня с интервалом открылась', await waitFor(() => !!$('#cell-abs-save')));
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

  /* блок «Отпросился» — только при смене с часами (16.10.2026): день «В» — без блока */
  const rowV = (sched.rows || []).find(r => Object.values(r.cells || {})
    .some(cc => cc.tabel && cc.tabel.code === 'В' && !(cc.shifts || []).length));
  const dayV = rowV && Object.keys(rowV.cells)
    .find(d => rowV.cells[d].tabel && rowV.cells[d].tabel.code === 'В'
      && !(rowV.cells[d].shifts || []).length);
  check('найден день без смены (код «В»)', !!(rowV && dayV), dayV || '');
  if (rowV && dayV) {
    click($(`#grid-host .cellbtn[data-emp="${rowV.employee.id}"][data-date="${dayV}"]`));
    check('в дне без смены блок отсутствия скрыт, объяснение показано',
      await waitFor(() => modalOpen()) && !$('#cell-abs-save')
      && /Смены с часами в этот день нет/.test(text('#modal')),
      text('#modal').slice(0, 160));
    check('в дне без отсутствий кнопок печати заявления нет',
      !$('#doc-print') && !$('#doc-docx') && !$('#doc-pdf'));
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

  /* дефект 16.10.2026: ручная смена замещает генерацию дня ЦЕЛИКОМ — в ячейке
     только ручной интервал; удаление ручной возвращает день к генерации */
  click($(`#grid-host .cellbtn[data-emp="${empId}"][data-date="${dayA}"]`));
  check('редактор дня открылся для ручной смены', await waitFor(() => !!$('#cell-sh-chips')));
  const d9 = $$('#cell-sh-chips .tc-chip[data-sh]').find(b => /09:00–18:00/.test(b.textContent));
  check('в словаре есть плашка смены 09:00–18:00', !!d9);
  click(d9);
  click($('#cell-sh-save'));
  check('ручная смена вытеснила генерацию — в ячейке только 09:00–18:00',
    await waitFor(() => {
      const el = $(`#grid-host .cellbtn[data-emp="${empId}"][data-date="${dayA}"]`);
      return el && /09:00–18:00/.test(el.textContent) && !/08:00–20:00/.test(el.textContent);
    }, 15000),
    ($(`#grid-host .cellbtn[data-emp="${empId}"][data-date="${dayA}"]`) || {}).textContent || '');
  click($(`#grid-host .cellbtn[data-emp="${empId}"][data-date="${dayA}"]`));
  await waitFor(() => !!$('#cell-sh-drop'), 10000);
  click($('#cell-sh-drop'));
  check('удаление ручной смены — возврат к генерации из Табеля (08:00–20:00)',
    await waitFor(() => {
      const el = $(`#grid-host .cellbtn[data-emp="${empId}"][data-date="${dayA}"]`);
      return el && /08:00–20:00/.test(el.textContent) && !/09:00–18:00/.test(el.textContent);
    }, 15000));

  /* «Сбросить месяц» (16.10.2026): ручные смены И согласованные отсутствия —
     слой 1 возвращается к чистому плану из Табеля; Табель не трогается.
     К сид-интервалу Иванова добавляем «выходной за часы» у цели row2/dayW…
     (сид-интервал ещё на месте) — сброс убирает оба. */
  click($('#btn-clear'));
  check('сброс месяца — ручные смены и отсутствия, Табель не трогается',
    await waitFor(() => !!$('#modal [data-yes]'))
    && /Ручные смены/.test(text('#modal')) && /отсутствия/.test(text('#modal'))
    && /Табель НЕ трогается/.test(text('#modal')),
    text('#modal').slice(0, 220));
  click($('#modal [data-yes]'));
  check('сброс месяца выполнен (эндпоинт reset-month)',
    await waitFor(() => /Ручных смен удалено/.test(toasts())
      && /отсутствий: [1-9]/.test(toasts()), 15000), toasts().slice(0, 200));
  check('после сброса в Графике не осталось согласованных отсутствий месяца',
    await waitFor(async () => {
      const g = await jget(`/api/schedule?year=${Y}&month=${M}`);
      return (g.rows || []).every(r => Object.values(r.cells || {})
        .every(cc => !(cc.absences || []).length));
    }, 15000));

  /* печать (16.10.2026): та же геометрия и содержимое, что на экране; блоки смен
     разделены заголовками; месяц — двумя страницами-половинками с колонкой ФИО */
  const beforePrint = printed.length;
  click($('#btn-print'));
  const prOk = await waitFor(() => printed.length > beforePrint, 5000);
  const pr = prOk ? printed.at(-1) : { h: '', css: '' };
  check('печать: блоки смен разделены заголовками', /p-group/.test(pr.h));
  check('печать: месяц разбит на страницы, колонка ФИО на каждой',
    (pr.h.match(/<h1>/g) || []).length >= 2 && (pr.h.match(/Сотрудник/g) || []).length >= 2,
    `страниц: ${(pr.h.match(/<h1>/g) || []).length}`);
  check('печать: экранные размеры ячеек, единый масштаб под ширину листа',
    /gridprint/.test(pr.css) && /zoom: (0\.\d+|1)/.test(pr.css)
    && /width: 60px/.test(pr.css) && /height: 52px/.test(pr.css), (pr.css || '').slice(0, 120));
  check('печать: содержимое ячеек — время смен, как на экране',
    /p-cell/.test(pr.h) && /\d{2}:\d{2}–\d{2}:\d{2}/.test(pr.h), pr.h.slice(0, 120));
  check('печать: итоговой колонки часов нет', !/Часов/.test(pr.h));

  /* ── 7. Словарь смен 18.10.2026: независим от Табеля ── */
  console.log('\n7 · Словарь смен: независимость от Табеля и health');
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
    return t && !t.includes('Загрузка…') && /Как связаны Табель и График/.test(t);
  }));
  check('справочники независимы: правила поля tzh больше нет',
    !/только коды справочника или пустое значение/.test(text('#st-body')));
  check('в словаре — системное отсутствие «Отпросился»',
    /Отпросился \(выходной за часы\)/.test(text('#st-body')));

  click($('#sh-new'));
  check('редактор смены открылся', await waitFor(() => !!$('#sh-code'), 20000));
  check('связка с Табелём из редактора удалена', !$('#sh-tzh') && !$('#sh-short') && !$('#sh-deduct'));
  check('заявление скрыто у типа «рабочая смена»', $('#sh-doc-wrap').style.display === 'none');
  change($('#sh-kind'), 'absence');
  check('заявление показано у типа «отсутствие»', $('#sh-doc-wrap').style.display !== 'none');
  change($('#sh-kind'), 'work');
  input($('#sh-code'), 'NORM_UI');
  input($('#sh-name'), 'Сценарная смена (нормы)');
  change($('#sh-start'), '08:00'); change($('#sh-end'), '20:00');
  click($('#modal [data-save]'));
  check('смена создана без связки с Табелем', await waitFor(modalClosed, 15000)
    && await waitFor(() => /Словарь смен обновлён/.test(toasts()), 8000), toasts().slice(0, 160));
  const st1 = (await jget('/api/shift-types')).find(s => s.code === 'NORM_UI');
  check('поля связки удалены из API',
    st1 && !('tzh_code' in st1) && !('display_code' in st1) && !('deduct_from_bank' in st1),
    JSON.stringify(st1 || {}).slice(0, 200));
  check('новая смена видна в списке', await waitFor(() => !!$(`[data-shift="${st1.id}"]`), 15000));

  const bad = await jsend('POST', '/api/shift-types', { code: 'NORM_UI2', name: 'Плохая',
    tzh_code: '08-20', kind: 'work', start_time: '08:00', end_time: '20:00' });
  check('API игнорирует легаси-поле связки', bad.status === 200, `${bad.status}`);
  if (bad.json?.id) await jsend('DELETE', `/api/shift-types/${bad.json.id}`);

  const health = await jsend('GET', '/api/engine-settings/health');
  const linkChecks = (health.json?.checks || []).filter(c =>
    c.code === 'APP-SHIFT-CODE' || c.code === 'APP-CODE-NO-SHIFT');
  check('health без сверок связки справочников', health.ok && linkChecks.length === 0,
    JSON.stringify(linkChecks).slice(0, 200));

  console.log(`\n=== ошибки консоли ===`);
  const uniq = [...new Set(consoleErrors.map(e => e.slice(0, 240)))];
  uniq.length ? uniq.forEach(e => console.log('  ' + e)) : console.log('  нет');
  failed += uniq.length;
  console.log(`\nИТОГ: проверок пройдено ${passed}, провалено ${failed}`);
  process.exit(failed ? 2 : 0);
}

main().catch(e => { console.error('сценарий:', e); process.exit(1); });
