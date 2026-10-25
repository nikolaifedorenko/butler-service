/* Сценарий T5 «График = 4 слоя» (норматив владельца 12.10.2026, Q2/Q7): jsdom +
   РЕАЛЬНЫЙ сервер, без браузера. Проверяет навигацию и слои из
   docs/REVIEW-GRAFIK-4-SLOYA-2026-10-12.md (§9, PR-C):

  · ОДИН пункт меню «График» с четырьмя слоями: 0 Табель · 1 План/График ·
    2 Факт · 3 Управленческий Табель (Q2); доска «Отметки» — отдельный пункт (Q7);
  · слои — сборка существующих экранов: Табель с кнопками слоя 0, сетка Графика,
    УТ с «Закрыть период»; без права слой скрыт, алиасы navigate('timesheet')
    и др. продолжают работать;
  · слой 2 «Факт»: сетка «Номера» (GET /api/fact/day) — сырые отметки СКУД,
    округление до шага из настроек, окно из кода Табеля (Q1), план/отработано/
    недостача/переработка и флаги из Графика — всё числами движка; режим
    «Сессии» — прежняя история без округления;
  · роль сотрудника: только доступные слои, в «Номерах» — только своя строка.

Запуск: tools/run_layers_scenario.sh [порт] [логин]   (нужен jsdom: npm i)
Код возврата: 0 — сценарий пройден, 2 — есть проваленные проверки. */
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { fileURLToPath } from 'node:url';
import { JSDOM, VirtualConsole } from 'jsdom';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const BASE = process.argv[2] || 'http://127.0.0.1:8194';
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

const navIds = () => $$('#sidenav .nav-item').map(b => b.dataset.view).filter(Boolean);
const activeLayer = () => $('#grafik-tabs .layer-tab.active')?.dataset.layer || null;
const paneOn = () => $$('#view-grafik .layer-pane.on').map(p => p.id.replace('view-', ''));

async function login(username) {
  /* форма логина теперь отправляется нативно (менеджеры паролей): в jsdom
     воспроизводим тем же путём — JSON-вход (кука в «jar») + перезапуск SPA */
  const r = await jsend('POST', '/api/auth/login', { username, password: 'demo1234' });
  if (!r.ok) return false;
  window.eval('bootApp()');
  return waitFor(() => !$('#app').classList.contains('hidden'), 30000);
}

async function main() {
  await sleep(400);
  check('вход выполнен (admin)', await login(LOGIN));
  await sleep(500);

  /* ── посев: сотрудник, принятый в текущем месяце (первый период + OPENING_SEED,
        v7.1/R37), цикл 2/2 на месяц, целевой день — «Я 10,75» (окно 08:00–20:00)
        и отметки 07:35 → 19:25: шаг 60 даёт сессию 08:00–19:00, план 12ч,
        отработано 11ч, недостача 1ч, флаг «Ранний уход» ── */
  const today = window.eval('todayISO()');                 // «сегодня» в tz сервера
  const first = today.slice(0, 8) + '01';
  const d1 = new Date(today + 'T00:00:00Z');
  d1.setUTCDate(d1.getUTCDate() - 1);
  const yest = d1.toISOString().slice(0, 10);
  const day = yest >= first ? yest : today;                // 1-го числа вчера — прошлый месяц
  /* отметки видны движку, только если они уже в прошлом (до «сейчас» в tz сервера) */
  const mskNow = new Date().toLocaleTimeString('ru-RU', { timeZone: 'Europe/Moscow',
    hour: '2-digit', minute: '2-digit', hour12: false }).slice(0, 5);
  const punchesVisible = day < today || mskNow >= '19:30';

  const shifts = await jget('/api/shift-types');
  const day12 = shifts.find(s => s.code === 'DAY12');
  let emp = await jsend('POST', '/api/employees', {
    full_name: 'Сеточкин Сеть Сетевич', position: 'Батлер (слой 2)',
    hired_at: first, schedule_group: 'Смена 1',
    role: 'employee', username: 'layers_grid', password: 'demo1234' });
  check('сотрудник для сетки создан', emp.ok, JSON.stringify(emp.json).slice(0, 160));
  const empId = emp.json?.id;
  let r = await jsend('POST', `/api/employees/${empId}/bank-adjust`, {
    hours: 0, date: first, note: 'начальный банк (сценарий T5)', reason_code: 'OPENING_SEED' });
  check('посев OPENING_SEED принят', r.ok, JSON.stringify(r.json).slice(0, 160));
  /* цикл 2/2 на весь месяц — массовой правкой Табеля, как «Слой 0» в интерфейсе
     (прежний POST /api/schedule/fill-pattern удалён по решению владельца В-7) */
  const nDays = new Date(Date.UTC(+first.slice(0, 4), +first.slice(5, 7), 0)).getUTCDate();
  const monthDays = Array.from({ length: nDays }, (_, i) => first.slice(0, 8) + String(i + 1).padStart(2, '0'));
  for (const [code, hours, part] of [['Я', 12, monthDays.filter((_, i) => i % 4 < 2)],
                                     ['В', 0, monthDays.filter((_, i) => i % 4 >= 2)]]) {
    r = await jsend('POST', '/api/tabel/bulk', { employee_ids: [empId], dates: part, code, hours });
    check(`цикл 2/2 заполнил месяц: «${code}»`, r.ok && r.json?.ok, JSON.stringify(r.json).slice(0, 160));
  }
  r = await jsend('PUT', '/api/tabel/cell', { employee_id: empId, date: day,
    code: 'Я', hours: 10.75, note: '' });
  check('день переведён в «Я 10,75»', r.ok, JSON.stringify(r.json).slice(0, 160));
  for (const [ts, kind] of [[`${day}T07:35:00`, 'in'], [`${day}T19:25:00`, 'out']]) {
    r = await jsend('POST', '/api/punches', { employee_id: empId, ts, kind,
      source: 'manager', note: 'сценарий T5' });
    if (!r.ok && !(day === today && mskNow < ts.slice(11, 16))) {
      check(`отметка ${kind} принята`, false, JSON.stringify(r.json).slice(0, 160));
    }
  }
  if (punchesVisible) check('отметки дня уже в прошлом — сетка их покажет', true);

  /* ── 1. Навигация: один пункт «График», четыре слоя (Q2); «Отметки» отдельны (Q7) ── */
  console.log('\n1 · Навигация: «График» = 4 слоя');
  const nav = navIds();
  check('в меню один пункт «График»', nav.filter(v => v === 'grafik').length === 1, nav.join(','));
  check('прежние разделы не торчат отдельными пунктами',
    !nav.some(v => ['schedule', 'timesheet', 'fact', 'mgmt'].includes(v)), nav.join(','));
  check('доска «Отметки» — отдельный пункт меню (Q7)', nav.includes('marks'));
  check('пункт меню подписан «График» (Q2)',
    $$('#sidenav .nav-item').find(b => b.dataset.view === 'grafik')?.textContent.includes('График'));

  window.navigate('grafik');
  check('панель слоёв отрисована', await waitFor(() => $$('#grafik-tabs .layer-tab').length === 4));
  const tabs = $$('#grafik-tabs .layer-tab');
  check('слои пронумерованы 0–3', tabs.map(b => b.querySelector('.lnum')?.textContent).join('') === '0123');
  check('названия слоёв по нормативу',
    /Табель/.test(tabs[0].textContent) && /План \/ График/.test(tabs[1].textContent)
    && /Факт/.test(tabs[2].textContent) && /Управленческий Табель/.test(tabs[3].textContent),
    tabs.map(t => t.textContent).join(' | '));
  check('слой по умолчанию — 1 План/График (как прежний раздел «График»)',
    await waitFor(() => activeLayer() === 'schedule' && $('#grid-host table')));
  check('панель активного слоя видна, остальные скрыты',
    paneOn().join(',') === 'schedule', paneOn().join(','));
  check('обёртка «График» — активный раздел', $('#view-grafik').classList.contains('active'));

  /* ── 2. Слой 0 · Табель: сборка существующего экрана ── */
  console.log('\n2 · Слой 0 · Табель');
  click($('#grafik-tabs .layer-tab[data-layer="timesheet"]'));
  check('панель Табеля активна', await waitFor(() => activeLayer() === 'timesheet'
    && $('#tb-body table') && $$('#tb-body td.v4-cell').length > 0));
  check('переключение слоёв скрывает соседние панели', paneOn().join(',') === 'timesheet');
  check('кнопки слоя 0 на месте («Заполнить из циклов», «Сбросить», «Назначить отсутствие»)',
    !!$('#tb-fill') && !!$('#tb-reset') && !!$('#tb-absence'));
  /* карточка сотрудника из Табеля: клик по ФИО открывает ту же модалку, что и
     раздел «Сотрудники» — правки без перехода в другой раздел. Посеянный
     сотрудник создан ПОСЛЕ loadDirectory(), поэтому попутно проверяется
     дозагрузка справочника в openEmployeeCard(). */
  check('ФИО в строке Табеля кликабельно (data-emp)', !!$(`#tb-body td.who[data-emp="${empId}"]`));
  click($(`#tb-body td.who[data-emp="${empId}"]`));
  check('слой 0: клик по ФИО открыл карточку сотрудника',
    await waitFor(() => !$('#modal-backdrop').classList.contains('hidden')
      && /Сеточкин/.test(text('#modal h3')), 8000), text('#modal h3'));
  check('карточка та же, что в разделе «Сотрудники» (банк часов, действия)',
    /Банк часов/.test(text('#modal')) && !!$('#modal [data-edit]'));
  click($('#modal .x'));
  check('карточка закрылась', await waitFor(() => $('#modal-backdrop').classList.contains('hidden')));

  /* ── 3. Слой 3 · Управленческий Табель ── */
  console.log('\n3 · Слой 3 · Управленческий Табель');
  click($('#grafik-tabs .layer-tab[data-layer="mgmt"]'));
  check('панель УТ активна и отрисована', await waitFor(() => activeLayer() === 'mgmt'
    && $('#ut-body table')));
  check('«Закрыть период» видна админу', !!$('#ut-close') && $('#ut-close').style.display !== 'none');
  /* «всё или ничего» (25.10.2026): текущий месяц не завершён ни у кого — закрытие не трогает
     никого и показывает полный список; закрывать и пересчитывать по одному нельзя */
  click($('#ut-close'));
  check('подтверждение закрытия «у всех»',
    await waitFor(() => /у всех/.test(text('#modal h3')) && $('#modal [data-yes]')), text('#modal h3'));
  click($('#modal [data-yes]'));
  const opened = await waitFor(() => /не закрыт ни у кого/.test(text('#modal h3')), 20000);
  const [, bad, total] = (text('#modal').match(/у (\d+) из (\d+)/) || []).map(Number);
  check('ошибки — модалкой «не закрыт ни у кого» с полным списком',
    opened && bad > 0 && bad === total && $$('#modal tr[data-emp]').length === bad,
    `${text('#modal h3')} · строк ${$$('#modal tr[data-emp]').length}, в подзаголовке ${bad} из ${total}`);
  click($('#modal [data-cancel]'));
  check('модалка списка закрылась', await waitFor(() => $('#modal-backdrop').classList.contains('hidden')));
  click($('#ut-body tr[data-emp]'));
  check('карточка сотрудника УТ открылась',
    await waitFor(() => !$('#modal-backdrop').classList.contains('hidden') && $('#modal [data-cancel]'), 15000));
  check('в карточке нет закрытия и пересчёта по одному',
    !$('#modal [data-close]') && !$('#modal [data-recalc]'));
  click($('#modal [data-cancel]'));
  check('карточка УТ закрылась', await waitFor(() => $('#modal-backdrop').classList.contains('hidden')));

  /* ── 4. Слой 2 · Факт: сетка «Номера» (Q7) ── */
  console.log('\n4 · Слой 2 · Факт: сетка «Номера»');
  click($('#grafik-tabs .layer-tab[data-layer="fact"]'));
  check('панель Факта активна', await waitFor(() => activeLayer() === 'fact' && $('#fc-mode')));
  check('порядок вкладок владельца: Месяц, День, Сотрудник; по умолчанию Месяц',
    $$('#fc-mode button').map(b => b.dataset.mode).join(',') === 'month,numbers,sessions'
    && $('#fc-mode button[data-mode="month"]').classList.contains('active')
    && text('#fc-mode button[data-mode="month"]') === 'Месяц'
    && text('#fc-mode button[data-mode="numbers"]') === 'День'
    && text('#fc-mode button[data-mode="sessions"]') === 'Сотрудник',
    $$('#fc-mode button').map(b => b.textContent).join('|'));
  check('Месяц по умолчанию: гант отрисован без кликов',
    await waitFor(() => $('#fm-body svg') && $$('#fm-body svg rect').length > 10, 15000),
    `rect: ${$$('#fm-body svg rect').length}`);
  click($('#fc-mode button[data-mode="numbers"]'));
  check('шаг округления и период показаны (шаг — из настроек)',
    await waitFor(() => /Шаг округления/.test(text('#fd-meta')) && /период/.test(text('#fd-meta'))),
    text('#fd-meta'));
  change($('#fd-date'), day);
  check('строка сотрудника появилась', await waitFor(() => $(`#fd-body tr[data-emp="${empId}"]`), 15000));
  const rowSel = `#fd-body tr[data-emp="${empId}"]`;
  const rowText = text(rowSel);
  if (punchesVisible) {
    check('сырые отметки видны (07:35 / 19:25)',
      /07:35/.test(rowText) && /19:25/.test(rowText), rowText.slice(0, 200));
    check('округление до шага показано (→ 08:00 / → 19:00)',
      /08:00/.test(rowText) && /19:00/.test(rowText), rowText.slice(0, 200));
    check('сопряжённая сессия 08:00–19:00', /08:00–19:00/.test(rowText), rowText.slice(0, 200));
  } else {
    console.log('    (отметки ещё в будущем — проверяется только структура сетки)');
    check('сетка дня отрисована', /Сеточкин/.test(rowText), rowText.slice(0, 200));
  }
  check('окно из кода Табеля 08:00–20:00 и значение «Я 10,75» (Q1)',
    /08:00–20:00/.test(rowText) && /Я 10,75/.test(rowText), rowText.slice(0, 260));
  const td = sel => text(`${rowSel} td[data-label="${sel}"]`);
  check('план 12 ч (длина окна, R34)', td('План').startsWith('12'), td('План'));
  if (punchesVisible) {
    check('отработано 11 ч, факт 11 ч', /11/.test(td('Отработано')), td('Отработано'));
    check('недоработка −1 ч', /−1/.test(td('Недоработка')), td('Недоработка'));
    check('переработки нет (сессия внутри окна)', /—/.test(td('Переработка')), td('Переработка'));
    check('флаг «Ранний уход» из Графика', /Ранний уход/.test(td('Флаги')), td('Флаги'));
  }
  check('подсказка: оперативная доска — в «Отметках» (Q7)',
    /«Отметки»/.test(text('#fd-body')) || /Отметки/.test(text('#view-fact .hint')));

  /* ── 4б. вкладка «Месяц»: гант фактических присутствий ── */
  console.log('\n4б · Факт: вкладка «Месяц» (гант)');
  const dayRows = $$('#fd-body tr[data-emp]').length;
  click($('#fc-mode button[data-mode="month"]'));
  check('возврат на «Месяц» переключает на гант',
    await waitFor(() => $('#fm-body svg'), 10000));
  check('гант отрисован (SVG с полосами и штриховкой окон)',
    await waitFor(() => $('#fm-body svg') && $$('#fm-body svg rect').length > 10, 15000),
    `rect: ${$$('#fm-body svg rect').length}`);
  check('гант: строка на сотрудника, имена в левой колонке',
    $$('#fm-names .fg-row').length === dayRows && dayRows > 0,
    `имён: ${$$('#fm-names .fg-row').length}, строк дня: ${dayRows}`);
  check('гант: штриховка окна — SVG-паттерны по цветам словаря',
    $$('#fm-body svg pattern').length >= 1);
  const sessColor = window.eval(
    `((state.factMonth || {rows:[]}).rows.find(r => r.employee.id === ${empId}) || {days:{}}).days['${day}']?.color || ''`);
  check('гант: полоса сотрудника с отметками — цветом словарной смены',
    !!sessColor && !!$(`#fm-body svg rect[fill="${sessColor}"]`), sessColor || 'цвет не найден');
  check('гант: у полос есть подсказки с окном и Табелем',
    $$('#fm-body svg rect title').length > 0,
    `title: ${$$('#fm-body svg rect title').length}`);
  check('подсказка оси: непрерывное время, полночь одной полосой',
    /непрерывное время/.test(text('#fm-meta')), text('#fm-meta'));
  click($('#fc-mode button[data-mode="numbers"]'));
  check('возврат на вкладку «День»', await waitFor(() => $('#fd-body table')));

  /* ── 5. Режим «Сессии»: прежняя история без округления ── */
  console.log('\n5 · Факт: режим «Сессии»');
  window.eval('state.employees = null; state.factEmp = null;');   // список перечитается с сервера
  click($('#fc-mode button[data-mode="sessions"]'));
  check('переключилось на вкладку «Сотрудник» (история сессий)',
    await waitFor(() => $('#fc-emp') && $('#fc-body')));
  await waitFor(() => $(`#fc-emp option[value="${empId}"]`), 8000);
  change($('#fc-emp'), String(empId));
  check('сотрудник выбран в селекте', $('#fc-emp').value === String(empId), $('#fc-emp').value);
  change($('#fc-from'), day);
  change($('#fc-to'), day);
  click($('#fc-go'));
  check('таблица сессий отрисована',
    await waitFor(() => $('#fc-body table') && /Сеточкин/.test(text('#fc-body')), 10000),
    text('#fc-body').slice(0, 160));
  if (punchesVisible) {
    check('исходные моменты без округления (07:35, 19:25)',
      await waitFor(() => /07:35/.test(text('#fc-body')) && /19:25/.test(text('#fc-body')), 8000),
      text('#fc-body').slice(0, 200));
  }
  click($('#fc-mode button[data-mode="numbers"]'));
  check('возврат к «Дню»', await waitFor(() => $('#fd-body table')));

  /* ── 6. Алиасы старых разделов ── */
  console.log('\n6 · Алиасы: navigate("timesheet"/"mgmt"/"schedule")');
  window.navigate('timesheet');
  check('navigate("timesheet") открывает слой 0', await waitFor(() => activeLayer() === 'timesheet'
    && paneOn().join(',') === 'timesheet'));
  window.navigate('mgmt');
  check('navigate("mgmt") открывает слой 3', await waitFor(() => activeLayer() === 'mgmt'));
  window.navigate('schedule');
  check('navigate("schedule") открывает слой 1', await waitFor(() => activeLayer() === 'schedule'
    && $('#grid-host table')));
  /* карточка сотрудника из Графика (слой 1) — тот же короткий путь */
  check('ФИО в сетке Графика кликабельно (data-emp)',
    await waitFor(() => $(`#grid-host td.name-cell[data-emp="${empId}"]`), 10000));
  click($(`#grid-host td.name-cell[data-emp="${empId}"]`));
  check('слой 1: клик по ФИО открыл карточку сотрудника',
    await waitFor(() => !$('#modal-backdrop').classList.contains('hidden')
      && /Сеточкин/.test(text('#modal h3')), 8000), text('#modal h3'));
  click($('#modal .x'));
  check('карточка закрылась', await waitFor(() => $('#modal-backdrop').classList.contains('hidden')));

  /* ── 6b. Мелочи рецензии 22.10.2026 (P2): самодиагностика и права сотрудников ── */
  console.log('\n6b · Самодиагностика у не-админа; «Сотрудники» без employees.edit');
  check('предупреждение схемы без перечня (ответ не-админу) не падает',
    window.eval(`JSON.stringify(selfcheckDetails({ ok: false, hint: 'h', details: 'перечень — администратору' }))`)
      === JSON.stringify(['перечень — администратору']));
  const access = await jget('/api/access');
  const gromova = (access.users || []).find(u => u.username === 'gromova');
  check('админ запрещает gromova employees.edit',
    !!gromova && (await jsend('PUT', `/api/access/users/${gromova.id}/grants`,
      { grants: { 'employees.edit': 'deny' } })).ok);
  click($('#logout-btn'));
  check('выход выполнен', await waitFor(() => !$('#login-screen').classList.contains('hidden')));
  await sleep(300);
  check('вход выполнен (gromova без employees.edit)', await login('gromova'));
  await sleep(600);
  window.navigate('employees');
  check('список сотрудников отрисован', await waitFor(() => $$('#view-employees tr[data-card]').length > 0));
  check('без employees.edit нет «+ Добавить сотрудника»', !$('#e-add'));
  click($('#view-employees tr[data-card]'));
  check('карточка открылась', await waitFor(() => !$('#modal-backdrop').classList.contains('hidden')));
  const editBtns = ['data-edit', 'data-delete', 'data-dismiss', 'data-rehire', 'data-block', 'data-pos']
    .filter(a => $(`#modal [${a}]`));
  check('в карточке нет кнопок правки учётки', editBtns.length === 0, editBtns.join(', '));
  click($('#modal .x'));
  check('карточка закрылась', await waitFor(() => $('#modal-backdrop').classList.contains('hidden')));

  /* ── 7. Роль сотрудника: только свои слои и своя строка ── */
  console.log('\n7 · Сотрудник: слои по правам, в «Номерах» только себя');
  click($('#logout-btn'));
  check('выход выполнен', await waitFor(() => !$('#login-screen').classList.contains('hidden')));
  await sleep(300);
  check('вход выполнен (ivanov)', await login('ivanov'));
  await sleep(600);
  check('пункт «График» виден сотруднику', navIds().includes('grafik'));
  /* стартовый экран сотрудника — «Мои отметки» (19.10.2026), поэтому вкладки
     «Графика» перерисовываются при открытии раздела: заходим явно */
  window.navigate('grafik');
  check('слои без прав скрыты (остались План/График и Факт)',
    await waitFor(() => $$('#grafik-tabs .layer-tab').length === 2)
    && $$('#grafik-tabs .layer-tab').map(b => b.dataset.layer).join(',') === 'schedule,fact',
    $$('#grafik-tabs .layer-tab').map(b => b.dataset.layer).join(','));
  window.navigate('fact');
  const me = await jget('/api/auth/me');
  check('«Месяц» по умолчанию у сотрудника: в ганте только своя строка',
    await waitFor(() => $$('#fm-names .fg-row').length === 1, 15000),
    `строк: ${$$('#fm-names .fg-row').length}`);
  click($('#fc-mode button[data-mode="numbers"]'));
  check('«День» сотрудника: в сетке только своя строка',
    await waitFor(() => $$('#fd-body tr[data-emp]').length === 1
      && $$('#fd-body tr[data-emp]')[0].dataset.emp === String(me.user.employee_id), 10000),
    $$('#fd-body tr[data-emp]').map(t => t.dataset.emp).join(','));
  window.navigate('timesheet');
  check('алиас без права откатывается на доступный слой',
    await waitFor(() => activeLayer() === 'schedule'));
  check('без права employees.view имена в сетке не кликабельны (чужая карточка недоступна)',
    await waitFor(() => $('#grid-host table')) && $$('#grid-host td.name-cell[data-emp]').length === 0,
    `кликов по ФИО: ${$$('#grid-host td.name-cell[data-emp]').length}`);

  /* ── 8. Консоль ── */
  console.log('\n8 · Консоль');
  const unique = [...new Set(consoleErrors)];
  if (unique.length) unique.slice(0, 10).forEach(e => console.log('  ' + e));
  check('нет ошибок JS за весь прогон', unique.length === 0);

  console.log(`\nИТОГ: проверок пройдено ${passed}, провалено ${failed}`);
  process.exit(failed ? 2 : 0);
}

main().catch(e => { console.error('сценарий упал:', e && e.stack || e); process.exit(2); });
