/* Сценарий модуля «Шахматка»: jsdom + РЕАЛЬНЫЙ сервер, без браузера (как settings_scenario).

Проходит пользовательские пути модуля (docs/superpowers/specs/2026-10-23-stays-chessboard-design.md):
  1. экраны Настроек: фонд и категории, сопровождение, настраиваемые поля, метки;
  2. шахматка объектов: бронь формой с предпросмотром, вытеснение чужой брони, 409, карточка;
  3. батлеры: назначение шаблоном → «вне смены» → «Добавить смену» → табло дня;
  2а. месяц: ◀ ▶ (гонка быстрой смены), общий с Табелем, «Сегодня» с подсветкой колонки;
  4. фильтры по дереву и флагам, разделы дерева, сортировка, «Загрузка» (8 строк узла, % / штуки),
     полный фонд на шахматке; под другими логинами — смоук вкладок и «Мои гости»;
  5. блок/OOO, совместное проживание, карточка гостя со связями, особые даты, сопровождающие, поля;
  6. сохранённые наборы фильтров (localStorage, без хранилища — пустой список);
  7. флаг и выбытие объекта с середины месяца: «вне фильтра» / «нет в фонде», полосы не скрыты;
  8. вкладка «Брони»: свой период, сортировка «Выезд ↓», «Показать ещё», карточка по клику,
     лимит 366 дней, экранирование; у уровня «занятость» вкладки нет;
  9. вкладка «Гости»: поиск, фильтр «день рождения», карточка по клику, объединение дублей
     с предпросмотром «что перенесётся»;
 10. семейное дерево: + ребёнок Ивану и Марии → «правнук» у бабушки Ивана, перецентровка,
     третий родитель — тост с текстом сервера, «бывшие», удаление связи; в карточке брони —
     дерево только для чтения (и под логином уровня «с фамилиями»).

Запуск: tools/run_stays_scenario.sh [порт] [логин]   (нужен jsdom: npm i)
Код возврата: 0 — сценарий пройден, 2 — есть проваленные проверки. */
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { fileURLToPath } from 'node:url';
import { JSDOM, VirtualConsole } from 'jsdom';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const BASE = process.argv[2] || 'http://127.0.0.1:8146';
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

let failed = 0, passed = 0;
function check(name, cond, extra = '') {
  if (cond) { passed++; console.log(`  ✓ ${name}`); }
  else { failed++; console.log(`  ❌ ${name}${extra ? ' — ' + extra : ''}`); }
}
async function waitFor(fn, ms = 12000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (fn()) return true; await sleep(150); }
  return false;
}
async function go(screen) {
  click($(`#st-nav [data-st="${screen}"]`));
  await waitFor(() => {
    const t = text('#st-body');
    return t && !t.includes('Загрузка…');
  });
}
async function apiJson(method, url, body) {
  const r = await proxy(method, url, { body: body ? JSON.stringify(body) : undefined,
    headers: body ? { 'Content-Type': 'application/json' } : {} });
  return { status: r.status, body: JSON.parse((await r.text()) || 'null') };
}
/* «Сегодня» в часовом поясе СЕРВЕРА (APP_TZ), а не раннера: иначе в CI (UTC) около 21–24 UTC дата
   сценария — вчера по Москве, и черновик фонда с valid_from в прошлом отклоняется */
const SERVER_TZ = process.env.APP_TZ || 'Europe/Moscow';
function serverToday() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: SERVER_TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
}
const uniq = Date.now().toString(36).slice(-5).toUpperCase();
const addDays = (iso, n) => new Date(Date.parse(iso + 'T00:00:00Z') + n * 86400000).toISOString().slice(0, 10);
const monthTitle = () => window.eval('MONTHS[state.month - 1] + " " + state.year');

/* Месяц видов — общий state.year / state.month (§6): открыть месяц даты iso на вкладке tab */
async function openMonth(iso, tab = 'units') {
  const [y, m] = iso.split('-').map(Number);
  window.eval(`state.year = ${y}; state.month = ${m};`);
  click($(`#view-stays [data-stab="${tab}"]`));
  return waitFor(() => !!$(`#stays-body .sb-head [data-day="${iso.slice(0, 8)}01"]`));
}
/* фильтр меняет разметку целиком: ждём новую (иначе следующий шаг уйдёт в старую панель) */
async function setCheck(sel, on) {
  const el = $(sel);
  if (!el) return false;
  el.checked = on;
  change(el);
  return waitFor(() => $(sel) && $(sel) !== el);
}
async function resetFilters() {
  const old = $('#sf-reset');
  click(old);
  return waitFor(() => $('#sf-reset') && $('#sf-reset') !== old);
}

/* Категория с объектами — черновиком фонда с сегодня и публикацией (старый CRUD /categories,
   /units заменён версиями фонда; экран фонда в Настройках — Task 3.1) */
async function fundCategory(code, labels, validFrom) {
  const today = serverToday();
  const d = await apiJson('POST', '/api/stays/fund/draft', { valid_from: validFrom || today });
  if (d.status !== 200) throw new Error(`черновик фонда (create): ${d.status} ${JSON.stringify(d.body)}`);
  let rev = d.body.rev;
  const step = async (path, body) => {
    const r = await apiJson('POST', '/api/stays/fund/draft/' + path, { rev, ...body });
    if (r.status !== 200) throw new Error(`черновик фонда ${path}: ${r.status} ${JSON.stringify(r.body)}`);
    rev = r.body.rev;
    return r.body;
  };
  const kinds = (await apiJson('GET', '/api/stays/fund/snapshot?date=' + today)).body.kinds;
  const villa = kinds.find(k => k.title === 'вилла');
  const cat = await step('categories', { code, title: code, kind_id: villa.id, escorted: true, weight: 4 });
  const units = [];
  for (const label of labels) units.push({ id: (await step('units', { label, category_id: cat.id })).id, label });
  await step('publish', {});
  return { cat, units };
}

async function settingsScreens() {
  console.log('\n1 · Настройки шахматки');
  window.navigate('settings');
  await waitFor(() => !!$('#st-nav'));
  const navIds = $$('#st-nav [data-st]').map(b => b.dataset.st);
  for (const id of ['stays_fund', 'stays_escort', 'stays_fields', 'stays_labels']) {
    check(`экран «${id}» в навигации`, navIds.includes(id));
  }

  await go('stays_fund');
  check('фонд: экран отрисован', /Категории/.test(text('#st-body')) && /Объекты/.test(text('#st-body')));
  await go('stays_escort');
  check('сопровождение: экран отрисован', /Сопровождают гостей/.test(text('#st-body')));
  click($('#se-seed'));
  check('«Заполнить по должности» добавило батлеров',
    await waitFor(() => $$('#st-body [data-escort]').some(cb => cb.checked)));
  input($('#se-limit'), '9');
  click($('#se-save'));
  await sleep(600);
  const st = (await apiJson('GET', '/api/stays/fund')).body.settings;
  check('лимит сохранён', st.daily_limit === 9, JSON.stringify(st));
  await apiJson('PUT', '/api/stays/settings', { ...st, daily_limit: 8 });

  await go('stays_fields');
  click($('#sfl-add'));
  check('форма поля открылась', await waitFor(() => !!$('#sfl-code')));
  input($('#sfl-code'), 'club' + uniq.toLowerCase()); input($('#sfl-title'), 'Клуб ' + uniq);
  change($('#sfl-kind'), 'choice'); input($('#sfl-choices'), 'Gold\nPlatinum');
  $('#sfl-searchable').checked = true;
  click($('[data-save]'));
  check('поле со списком сохранено', await waitFor(() => text('#st-body').includes('Клуб ' + uniq)));

  await go('stays_labels');
  click($('#slb-add'));
  check('форма метки открылась', await waitFor(() => !!$('#slb-title')));
  input($('#slb-title'), 'Метка ' + uniq);
  click($('[data-save]'));
  check('метка сохранена', await waitFor(() => text('#st-body').includes('Метка ' + uniq)));
  check('нет мусора в DOM', !/undefined|NaN|\[object Object\]/.test($('#st-body').innerHTML));
}

async function unitsBoard() {
  console.log('\n2 · Шахматка объектов');
  check('ordinal совпадает с Python date.toordinal()',
    [[2026, 9, 1, 739860], [2000, 2, 29, 730179], [1970, 1, 1, 719163], [2029, 12, 31, 741077]]
      .every(([y, m, d, o]) => window.staysOrdinal(y, m, d) === o));
  const code = 'SB' + uniq;
  const { cat, units: [u1, u2] } = await fundCategory(code, [code + '-1', code + '-2']);
  const guest = 'Сценарный' + uniq;
  await apiJson('POST', '/api/stays/guests', { last_name: guest });

  window.navigate('stays');
  check('вкладки шахматки', await waitFor(() => $$('#view-stays [data-stab]').length === 6));
  /* панель фильтров появляется после загрузки фонда и шахматки: в медленном CI сценарий
     менял фильтры раньше — change() уходил в пустоту (падало через раз, 25.10.2026) */
  check('шахматка отрисована (месяц и панель фильтров)', await waitFor(() => $('#sm-label') && $('.sf-panel')));
  check('выбор «7 / 14 / 31 дн.» и даты убран', !$('#sb-days') && !$('#sb-first'));
  check('месяц шахматки — общий месяц разделов', text('#sm-label') === monthTitle(), text('#sm-label'));
  /* гонка месяцев: ▶ ▶ подряд; ответ за февраль приходит ПОЗЖЕ мартовского — на экране
     должен остаться март (loadGenerationFor) */
  await openMonth('2030-01-01');
  const realApi = window.api;
  window.api = async (url, opts) => {
    if (url.startsWith('/api/stays/board/units') && url.includes('first=2030-02-01')) await sleep(1500);
    return realApi(url, opts);
  };
  window.eval('api = window.api');
  click($('#sm-next'));
  await sleep(150);                             // февраль ушёл и «висит»
  click($('#sm-next'));
  await sleep(2000);                            // запоздавший февраль тоже пришёл
  window.api = realApi;
  window.eval('api = window.api');
  check('быстрая смена месяцев: на экране последний выбранный', await waitFor(() => !!$('.sb-head [data-day="2030-03-01"]'))
    && !$('.sb-head [data-day="2030-02-01"]') && text('#sm-label') === 'март 2030', text('#sm-label'));
  check('месяц целиком — 31 колонка', $$('#stays-body .sb-head [data-day]').length === 31);
  click($('#sm-prev'));
  await waitFor(() => !!$('.sb-head [data-day="2030-02-01"]'));
  click($('#sm-prev'));
  check('◀ ◀ — снова январь', await waitFor(() => !!$('.sb-head [data-day="2030-01-01"]')));
  check('фильтр категории — галочкой', await setCheck(`[data-sf-cat="${cat.id}"]`, true));
  check('строки объектов категории', await waitFor(() => $$('#view-stays [data-unit-row]').length === 2));
  /* месяц общий с Табелем: ▶ здесь — Табель на том же месяце; ◀ в Табеле — шахматка тоже */
  click($('#sm-next'));
  await waitFor(() => text('#sm-label') === 'февраль 2030');
  window.navigate('timesheet');
  check('Табель открылся на месяце шахматки', await waitFor(() => text('#tb-label') === 'февраль 2030'), text('#tb-label'));
  click($('#tb-prev'));
  await waitFor(() => text('#tb-label') === 'январь 2030');
  window.navigate('stays');
  check('шахматка — на месяце Табеля', await waitFor(() => !!$('.sb-head [data-day="2030-01-01"]')) && text('#sm-label') === 'январь 2030');
  await waitFor(() => $$('#view-stays [data-unit-row]').length === 2);
  /* «Сегодня» — текущий месяц, колонка дня подсвечена */
  click($('#sm-today'));
  const today = serverToday();
  check('«Сегодня»: текущий месяц и подсветка колонки', await waitFor(() =>
    !!$(`.sb-head [data-day="${today}"].today.flash-today`)), text('#sm-label'));
  await openMonth('2030-01-01');

  click($('#sb-new'));
  check('форма брони открылась', await waitFor(() => !!$('#rf-check-in')));
  input($('#rf-number'), 'A' + uniq);
  change($('#rf-category'), String(cat.id));
  check('«Оплата за» — список категорий, следует за категорией брони', $('#rf-paid')?.tagName === 'SELECT'
    && $('#rf-paid').value === String(cat.id) && !$('#rf-purpose'));
  change($('#rf-check-in'), '2030-01-03');
  change($('#rf-check-out'), '2030-01-07');
  input($('#rf-guest-q'), guest);
  check('подбор гостя нашёл гостя', await waitFor(() => !!$('[data-pick-guest]')));
  click($('[data-pick-guest]'));
  check('гость в составе', await waitFor(() => text('#rf-occupants').includes(guest)));
  click($('#rf-preview'));
  check('предпросмотр показал объект', await waitFor(() => text('#rf-preview-out').includes(code + '-1')),
    text('#rf-preview-out'));
  click($('[data-save]'));
  check('полоса брони на шахматке', await waitFor(() =>
    $$('#view-stays [data-bar]').some(b => b.textContent.includes(guest))));

  const a = (await apiJson('GET', '/api/stays/board/units?first=2030-01-01&last=2030-01-14&category_ids=' + cat.id))
    .body.bars.find(b => b.number === 'A' + uniq);
  const b = (await apiJson('POST', '/api/stays/reservations', { number: 'B' + uniq, check_in: '2030-01-07',
    check_out: '2030-01-10', category_id: cat.id })).body.result;
  check('вторая бронь встала в тот же объект', b.segments[0].unit_id === u1.id);
  click($(`#view-stays [data-bar="${a.reservation_id}"]`));
  check('карточка брони открылась', await waitFor(() => /История изменений/.test(text('#modal'))));
  click($('#rc-edit'));
  check('форма правки открылась', await waitFor(() => $('#rf-check-out')?.value === '2030-01-07'));
  change($('#rf-check-out'), '2030-01-08');
  change($('#rf-unit-0'), String(u1.id));
  click($('#rf-preview'));
  check('предпросмотр: чужая бронь сдвигается', await waitFor(() =>
    text('#rf-preview-out').includes('B' + uniq) && text('#rf-preview-out').includes(code + '-2')),
  text('#rf-preview-out'));

  const cur = (await apiJson('GET', '/api/stays/reservations/' + a.reservation_id)).body;
  await apiJson('PUT', '/api/stays/reservations/' + a.reservation_id, { ...cur, note: 'параллельная правка',
    version: cur.version });
  click($('[data-save]'));
  check('устаревшая версия — понятное сообщение', await waitFor(() =>
    text('#toast-host').includes('Бронь изменилась — обновите')), text('#toast-host'));
  click($('[data-close]'));

  /* «Перенести» на полосе: выбор объекта → предпросмотр → сохранение (§6, §4.6) */
  window.navigate('stays');                       // бронь B создана через API — перерисовать шахматку
  await waitFor(() => !!$(`#view-stays [data-bar="${b.id}"]`));
  click($(`#view-stays [data-bar="${b.id}"]`));
  check('карточка второй брони', await waitFor(() => !!$('[data-move-seg="0"]')));
  click($('[data-move-seg="0"]'));
  check('диалог «Перенести» открылся', await waitFor(() => !!$('#tf-unit')));
  change($('#tf-unit'), String(u2.id));
  click($('#rf-preview'));
  check('предпросмотр переноса', await waitFor(() => text('#rf-preview-out').includes(code + '-2')), text('#rf-preview-out'));
  click($('[data-save]'));
  check('бронь перенесена в другой объект', await waitFor(() =>
    !!$(`#view-stays [data-unit-row="${u2.id}"] [data-bar="${b.id}"]`)));
  check('кнопки выгрузки на шахматке', !!$('#sb-xlsx-anon') && !!$('#sb-xlsx-full'));
  check('нет мусора в DOM', !/undefined|NaN|\[object Object\]/.test($('#view-stays').innerHTML));
}

async function butlersAndDay() {
  console.log('\n3 · Батлеры и табло дня');
  const iso = d => d.toISOString().slice(0, 10);
  const base = new Date(serverToday() + 'T00:00:00Z');
  const day = n => iso(new Date(base.getTime() + n * 86400000));
  const code = 'BT' + uniq;
  const { cat } = await fundCategory(code, [code + '-1']);
  const guest = 'Ведомый' + uniq;
  const g = (await apiJson('POST', '/api/stays/guests', { last_name: guest })).body;
  const res = (await apiJson('POST', '/api/stays/reservations', { number: 'C' + uniq, check_in: day(1), check_out: day(7),
    category_id: cat.id, occupants: [{ guest_id: g.id, role: 'main', date_from: day(1), date_to: day(7) }] })).body.result;
  const fund = (await apiJson('GET', '/api/stays/fund')).body;
  const ivanov = fund.escorts.find(e => e.name.startsWith('Иванов'));
  check('Иванов в «Сопровождают гостей»', !!ivanov);

  window.navigate('stays');
  await openMonth(day(1));
  await resetFilters();
  await setCheck(`[data-sf-cat="${cat.id}"]`, true);
  check('бронь на шахматке', await waitFor(() => !!$(`#view-stays [data-bar="${res.id}"]`)));
  click($(`#view-stays [data-bar="${res.id}"]`));
  check('кнопка «Назначить батлеров» в карточке', await waitFor(() => !!$('#rc-assign')));
  click($('#rc-assign'));
  check('форма назначения открылась', await waitFor(() => !!$('#cf-kind')));
  change($('#cf-kind'), 'single');
  change($('#cf-b1'), String(ivanov.employee_id));
  click($('#rf-preview'));
  check('предпросмотр: Иванов получает гостя', await waitFor(() => text('#rf-preview-out').includes(guest)), text('#rf-preview-out'));
  click($('[data-save]'));
  await sleep(500);

  check('шахматка батлеров открылась', await openMonth(day(1), 'butlers'));
  check('батлеры: селектора дней нет, месяц целиком', !$('#bb-days') && !$('#bb-first')
    && !!$(`#stays-body .sb-head [data-day="${day(1).slice(0, 8)}01"]`));
  /* ночи брони C — day(1)…day(6); вне их «вне смены» может давать демо-назначение.
     Ночи могут уйти в следующий месяц — тогда ищем там (▶) */
  const nights = [1, 2, 3, 4, 5, 6].map(day);
  const offCell = () => $$(`[data-bb-emp="${ivanov.employee_id}"][data-warn*="off_shift"]`).find(c => nights.includes(c.dataset.day));
  let offFound = await waitFor(() => !!offCell(), 6000);
  if (!offFound) { click($('#sm-next')); offFound = await waitFor(() => !!offCell()); }
  check('день «вне смены» подсвечен', offFound);
  const offDay = offCell()?.dataset.day;
  click(offCell());
  check('диалог дня батлера', await waitFor(() => !!$('#bb-add-shift')));
  click($('#bb-add-shift'));
  check('смена добавлена — «вне смены» в этот день исчез', await waitFor(() =>
    !!$(`[data-bb-emp="${ivanov.employee_id}"][data-day="${offDay}"]`)
    && !$(`[data-bb-emp="${ivanov.employee_id}"][data-day="${offDay}"]`).dataset.warn.includes('off_shift')));

  click($('[data-stab="day"]'));
  check('табло дня открылось', await waitFor(() => !!$('#db-date')));
  change($('#db-date'), offDay);
  await waitFor(() => $('#db-date')?.value === offDay && !!$('[data-dtab="in_house"]'));
  click($('[data-dtab="in_house"]'));
  check('табло: Иванов ведёт гостя', await waitFor(() =>
    $$('#view-stays [data-db-row]').some(r => r.textContent.includes(guest) && r.textContent.includes('Иванов'))));
  check('итоги табло отрисованы', /Заезды/.test(text('#view-stays')) && /Проживают/.test(text('#view-stays')));

  /* ручное назначение по дням: снять батлера с первой ночи (§6 «по дням») */
  click($(`#view-stays [data-db-row="${res.id}"]`));
  await waitFor(() => !!$('#rc-assign'));
  click($('#rc-assign'));
  await waitFor(() => !!$('#cf-kind'));
  change($('#cf-kind'), 'manual');
  check('таблица дней в ручном режиме', await waitFor(() => !!$(`[data-cf-day="${day(1)}"]`)));
  change($(`[data-cf-day="${day(1)}"]`), '');
  click($('#rf-preview'));
  check('предпросмотр ручной правки', await waitFor(() => text('#rf-preview-out').includes(guest)), text('#rf-preview-out'));
  click($('[data-save]'));
  await sleep(600);
  const card = (await apiJson('GET', `/api/stays/reservations/${res.id}/card`)).body;
  check('первая ночь без батлера', card.coverage.find(c => c.day === day(1))?.butlers.length === 0);

  /* день батлера: «Назначить» бронь на свободный день */
  await openMonth(day(1), 'butlers');
  await waitFor(() => !!$(`[data-bb-emp="${ivanov.employee_id}"][data-day="${day(1)}"]`));
  click($(`[data-bb-emp="${ivanov.employee_id}"][data-day="${day(1)}"]`));
  check('кнопка «Назначить» в дне батлера', await waitFor(() => !!$('#bb-assign')));
  click($('#bb-assign'));
  check('список броней дня без батлера', await waitFor(() => $$('#bb-res option').some(o => o.value === String(res.id))));
  change($('#bb-res'), String(res.id));
  click($('#bb-assign-save'));
  await sleep(600);
  const card2 = (await apiJson('GET', `/api/stays/reservations/${res.id}/card`)).body;
  check('Иванов снова ведёт первую ночь', card2.coverage.find(c => c.day === day(1))?.butlers[0]?.employee_id === ivanov.employee_id);
  check('нет мусора в DOM', !/undefined|NaN|\[object Object\]/.test($('#view-stays').innerHTML));
}

async function occupancyAndFund() {
  console.log('\n4 · Загрузка, фильтры, сортировка, полный фонд');
  const today = serverToday();
  const snap = (await apiJson('GET', '/api/stays/fund/snapshot?date=' + today)).body;
  const root = t => snap.groups.find(g => g.parent_id == null && g.title === t);
  const [korpus, villas, estate] = ['Корпус', 'Винные виллы', 'Имение'].map(root);
  const sea = snap.flags.find(f => f.title === 'Вид на море');
  check('демо-дерево: Корпус, Винные виллы, Имение, флаг «Вид на море»', !!(korpus && villas && estate && sea));
  await openMonth(today);

  /* Где: «Корпус» + «Винные виллы» — оба раздела (внутри измерения — «или») */
  await resetFilters();
  await setCheck(`[data-sf-group="${korpus.id}"]`, true);
  await setCheck(`[data-sf-group="${villas.id}"]`, true);
  check('«Корпус» + «Винные виллы» — оба раздела', !!$(`[data-sec="${korpus.id}"]`) && !!$(`[data-sec="${villas.id}"]`)
    && !$(`[data-sec="${estate.id}"]`));
  const rowsOf = gid => $$(`#view-stays [data-unit-row][data-root="${gid}"]`).length;
  check('по умолчанию виллы развёрнуты, корпус свёрнут (строки не в DOM)', rowsOf(villas.id) > 0 && rowsOf(korpus.id) === 0,
    `${rowsOf(villas.id)} / ${rowsOf(korpus.id)}`);
  click($(`[data-sec="${korpus.id}"]`));
  check('клик по разделу — корпус развёрнут', await waitFor(() => rowsOf(korpus.id) > 0));
  const n1 = rowsOf(korpus.id);
  await setCheck(`[data-sf-flag="${sea.id}"]`, true);
  const n2 = rowsOf(korpus.id);
  check('флаг «Вид на море» сужает', n2 > 0 && n2 < n1, `${n1} → ${n2}`);
  check('флаги — значками в строке', $$('#view-stays [data-unit-row] .sb-flag').length >= n2);

  /* раскрытие по умолчанию — из справочника видов (expanded): «номер» с «раскрывать» —
     корпус открыт сразу; вернуть как было */
  const room = snap.kinds.find(k => k.title === 'номер');
  const setRoom = expanded => apiJson('PUT', '/api/stays/fund/kinds/' + room.id,
    { title: room.title, sort_order: room.sort_order, expanded });
  check('вид «номер» по умолчанию не раскрывается', room && room.expanded === false, JSON.stringify(room));
  check('вид «номер»: «раскрывать» включено', (await setRoom(true)).status === 200);
  window.eval('staysState.fund = null; staysState.collapsed = {}');
  await openMonth(today);
  await resetFilters();
  await setCheck(`[data-sf-group="${korpus.id}"]`, true);
  check('expanded у вида — раздел «Корпус» развёрнут сразу', await waitFor(() => rowsOf(korpus.id) > 0),
    String(rowsOf(korpus.id)));
  await setRoom(false);
  window.eval('staysState.fund = null; staysState.collapsed = {}');
  await openMonth(today);
  await resetFilters();
  await setCheck(`[data-sf-group="${korpus.id}"]`, true);
  check('без expanded — «Корпус» снова свёрнут', await waitFor(() => !!$(`[data-sec="${korpus.id}"]`)) && rowsOf(korpus.id) === 0);
  /* фильтры и раскрытие — как до проверки (на них опираются шаги «Загрузки») */
  await setCheck(`[data-sf-group="${villas.id}"]`, true);
  await setCheck(`[data-sf-flag="${sea.id}"]`, true);
  window.eval(`staysState.collapsed[${JSON.stringify(String(korpus.id))}] = false`);

  check('«Загрузка» открылась', await openMonth(today, 'occupancy'));
  const [y, m] = today.split('-').map(Number);
  const dim = new Date(Date.UTC(y, m, 0)).getUTCDate();
  check('«Загрузка»: все дни месяца', $$('#stays-body .oc-head [data-day]').length === dim,
    String($$('#stays-body .oc-head [data-day]').length));
  const lines = key => $$(`[data-oc-group="${key}"] .oc-line`).length;
  check('«Итого по выбранному» развёрнут — восемь строк', lines('total') === 8, String(lines('total')));
  check('узел «Корпус» свёрнут — одна строка', lines(korpus.id) === 1, String(lines(korpus.id)));
  click($(`[data-oc-toggle="${korpus.id}"]`));
  check('клик по названию — узел развёрнут, восемь строк', await waitFor(() => lines(korpus.id) === 8));
  click($('[data-oc-toggle="total"]'));
  check('«Итого» свёрнут — одна строка', await waitFor(() => lines('total') === 1));
  check('свёрнутый узел — в процентах', /%|—/.test(text('[data-oc-group="total"] .oc-line')));
  click($('[data-oc-mode="count"]'));
  check('переключатель «штуки»', await waitFor(() => !/%/.test(text('[data-oc-group="total"] .oc-line'))
    && /\d+\/\d+/.test(text('[data-oc-group="total"] .oc-line'))));
  click($('[data-oc-mode="pct"]'));
  const cell = $(`[data-oc-group="${korpus.id}"] [data-oc-living]`);
  check('клетка «Проживают» узла', !!cell);
  const day = cell?.dataset.day;
  click(cell);
  check('клик — шахматка объектов узла', await waitFor(() => $(`[data-sf-group="${korpus.id}"]`)?.checked === true
    && $$('#view-stays [data-unit-row]').length > 0));
  check('… с этого дня (колонка подсвечена)', !!$(`.sb-head [data-day="${day}"]`));

  /* сортировка «по загрузке ↓» без группировки — первая строка с максимальной загрузкой */
  await resetFilters();
  change($('#sb-sort'), 'load');
  change($('#sb-dir'), 'desc');
  $('#sb-grouped').checked = false;
  change($('#sb-grouped'));
  await sleep(100);
  const params = window.eval('staysBoardParams().toString()');
  const board = (await apiJson('GET', '/api/stays/board/units?' + params)).body;
  const maxLoad = Math.max(...board.units.map(u => u.load));
  const first = $('#view-stays [data-unit-row]');
  check('по загрузке ↓ — первая строка с максимальной загрузкой', first && Number(first.dataset.load) === maxLoad
    && board.units.find(u => String(u.unit_id) === first.dataset.unitRow)?.load === maxLoad, `${first?.dataset.load} / ${maxLoad}`);
  check('без группировки — разделов нет', !$('#view-stays [data-sec]'));

  const t0 = Date.now();
  click($('#sm-next'));
  check('полный фонд на шахматке (≥ 440 объектов)', await waitFor(() => !!$(`.sb-head [data-day="${addDays(today.slice(0, 8) + '01', 40).slice(0, 8)}01"]`)
    && $$('#view-stays [data-unit-row]').length >= 440, 20000), String($$('#view-stays [data-unit-row]').length));
  const ms = Date.now() - t0;
  console.log(`  · отрисовка полного фонда за месяц: ${ms} мс`);
  check('полный фонд — быстрее 3 с (вместе с запросом)', ms < 3000, `${ms} мс`);
  change($('#sb-sort'), 'tree');
  change($('#sb-dir'), 'asc');
  $('#sb-grouped').checked = true;
  change($('#sb-grouped'));
}

/* Сохранённые наборы (§7): localStorage, каждый доступ в try/catch */
async function savedFilters() {
  console.log('\n6 · Сохранённые наборы фильтров');
  const snap = (await apiJson('GET', '/api/stays/fund/snapshot?date=' + serverToday())).body;
  const villas = snap.groups.find(g => g.parent_id == null && g.title === 'Винные виллы');
  window.navigate('stays');
  await openMonth(serverToday());
  await resetFilters();
  await setCheck(`[data-sf-group="${villas.id}"]`, true);
  /* поиск набирается — перерисовка после паузы не отнимает фокус у поля */
  const search = 'Лебедев';
  $('#sf-q').focus();
  input($('#sf-q'), search);
  const typed = $('#sf-q');
  await waitFor(() => $('#sf-q') && $('#sf-q') !== typed);
  check('поиск: после перерисовки фокус и текст в поле', window.document.activeElement?.id === 'sf-q'
    && $('#sf-q').value === search && window.eval('staysState.filters.q') === search);
  const name = 'Виллы ' + uniq;
  input($('#sf-save-name'), name);
  click($('#sf-save'));
  check('набор в списке', await waitFor(() => $$('#sf-saved option').some(o => o.value === name)));
  const me = (await apiJson('GET', '/api/auth/me')).body.user;
  const key = 'stays.filters.' + me.id;
  const stored = JSON.parse(window.localStorage.getItem(key) || '[]');
  check('набор в localStorage — под ключом пользователя', stored.some(x => x.name === name && x.filters.group_ids.includes(villas.id)));
  check('в наборе нет поиска и VIP (данные гостей не сохраняются)', stored.every(x => !('q' in x.filters) && !('vip' in x.filters))
    && !window.localStorage.getItem(key).includes(search) && window.localStorage.getItem('stays.filters') === null);
  /* смена пользователя устройства: ни наборов, ни поиска, ни фильтров прежнего */
  click($('#logout-btn'));
  check('выход выполнен', await waitFor(() => !$('#login-screen').classList.contains('hidden')));
  check('вход другим пользователем (sluzhba)', await relogin('sluzhba'));
  window.navigate('stays');
  check('другой пользователь: шахматка с панелью', await waitFor(() => !!$('.sf-panel')));
  check('другой пользователь: наборов прежнего нет', !$$('#sf-saved option').some(o => o.value === name));
  check('другой пользователь: поиск и фильтры пусты', ($('#sf-q')?.value ?? '') === ''
    && window.eval('staysState.filters.q') === '' && window.eval('staysState.filters.group_ids.length') === 0);
  click($('#logout-btn'));
  await waitFor(() => !$('#login-screen').classList.contains('hidden'));
  check('снова admin', await relogin(LOGIN));
  window.navigate('stays');
  await waitFor(() => !!$('.sf-panel') && $$('#sf-saved option').some(o => o.value === name));
  check('admin: свой набор на месте, поиск пуст', $$('#sf-saved option').some(o => o.value === name)
    && ($('#sf-q')?.value ?? '') === '');
  /* «перезагрузка»: память раздела сброшена, набор читается из хранилища */
  window.eval('staysState.filters = staysEmptyFilters(); staysState.fund = null;');
  const before = $('.sf-panel');
  window.navigate('stays');
  await waitFor(() => $('.sf-panel') && $('.sf-panel') !== before && $(`[data-sf-group="${villas.id}"]`));
  check('после перезагрузки набор — в списке', $$('#sf-saved option').some(o => o.value === name));
  check('после перезагрузки фильтр пуст', $(`[data-sf-group="${villas.id}"]`)?.checked === false);
  const old = $('#sf-saved');
  change(old, name);
  await waitFor(() => $('#sf-saved') && $('#sf-saved') !== old);
  check('выбранный набор применён (без поиска)', $(`[data-sf-group="${villas.id}"]`)?.checked === true
    && $('#sf-q').value === ''
    && $$('#view-stays [data-unit-row]').every(r => r.dataset.root === String(villas.id)));
  change($('#sf-saved'), name);
  click($('#sf-del'));
  check('набор удалён', await waitFor(() => !$$('#sf-saved option').some(o => o.value === name)));
  /* хранилище недоступно (приватный режим, запрет сайта) — пустой список, экран работает */
  window.eval(`Object.defineProperty(window, 'localStorage', { configurable: true, get() { throw new Error('denied'); } })`);
  check('без хранилища — пустой список наборов', window.eval('staysSavedFilters().length') === 0
    && window.eval('staysSaveFilter("x", staysEmptyFilters())') === false);
  const prev = $('.sf-panel');
  window.navigate('stays');
  check('без хранилища — панель фильтров на месте', await waitFor(() => $('.sf-panel') && $('.sf-panel') !== prev
    && !!$('#view-stays [data-unit-row]')));
  window.eval('delete window.localStorage');
}

/* Флаг с середины месяца (§7, фокус 4): строка показана, полосы до даты не скрыты,
   дни вне фильтра приглушены «вне фильтра», дни без объекта — серые «нет в фонде» */
async function flagMidMonth() {
  console.log('\n7 · Флаг и выбытие объекта с середины месяца');
  const code = 'FL' + uniq;
  const { cat, units: [u1, u2] } = await fundCategory(code, [code + '-1', code + '-2']);
  const flag = (await apiJson('POST', '/api/stays/fund/flags', { title: 'Флаг ' + uniq })).body;
  const d = await apiJson('POST', '/api/stays/fund/draft', { valid_from: '2035-03-15' });
  let rev = d.body.rev;
  rev = (await apiJson('PUT', '/api/stays/fund/draft/flags', { rev, flag_id: flag.id, unit_ids: [u1.id], value: true })).body.rev;
  rev = (await apiJson('DELETE', `/api/stays/fund/draft/units/${u2.id}?rev=${rev}`)).body.rev;
  const pub = await apiJson('POST', '/api/stays/fund/draft/publish', { rev });
  check('версия фонда с 15.03.2035 опубликована', pub.status === 200, JSON.stringify(pub.body));
  const res = (await apiJson('POST', '/api/stays/reservations', { number: 'FL' + uniq, check_in: '2035-03-10',
    check_out: '2035-03-20', category_id: cat.id })).body.result;
  window.navigate('stays');
  await openMonth('2035-03-01');
  await resetFilters();
  await setCheck(`[data-sf-flag="${flag.id}"]`, true);
  const row = `#view-stays [data-unit-row="${u1.id}"]`;
  check('объект с флагом с 15.03 — в фильтре', await waitFor(() => !!$(row)));
  check('дни до 15.03 — «вне фильтра»', !!$(`${row} .sb-off.filtered[data-from="2035-03-01"][data-to="2035-03-14"]`));
  check('полоса брони до 15.03 не скрыта', !!$(`${row} [data-bar="${res.id}"]`));
  await resetFilters();
  await setCheck(`[data-sf-cat="${cat.id}"]`, true);
  check('выбывший объект — серым «нет в фонде» с 15.03',
    await waitFor(() => !!$(`#view-stays [data-unit-row="${u2.id}"] .sb-off.absent[data-from="2035-03-15"][data-to="2035-03-31"]`)));
  check('нет мусора в DOM', !/undefined|NaN|\[object Object\]/.test($('#view-stays').innerHTML));
}

/* Форма брони берёт категории из фонда на дату заезда (§5): категория, которой сегодня нет,
   остаётся выбранной и не подменяется первой — иначе сохранение записало бы ложный «апгрейд» */
async function formFundOnCheckIn() {
  console.log('\n7а · Форма брони: фонд на дату заезда');
  const code = 'FU' + uniq;
  const { cat } = await fundCategory(code, [code + '-1'], '2038-06-01');
  const res = (await apiJson('POST', '/api/stays/reservations', { number: 'FU' + uniq, check_in: '2038-06-05',
    check_out: '2038-06-08', category_id: cat.id })).body.result;
  check('бронь в категории из будущей версии фонда создана', !!res?.id, JSON.stringify(res));
  window.navigate('stays');
  window.eval(`openReservationForm(${res.id})`);
  check('правка: «Оплата за» остаётся будущей категорией (не первой из списка)', await waitFor(() =>
    $('#rf-paid')?.value === String(cat.id) && $('#rf-category')?.value === String(cat.id)),
  `${$('#rf-paid')?.value} / ${$('#rf-category')?.value}`);
  click($('[data-close]'));
  window.eval('openReservationForm()');
  check('новая бронь: категории на сегодня — будущей нет', await waitFor(() => !!$('#rf-check-in'))
    && ![...$('#rf-paid').options].some(o => o.value === String(cat.id)));
  change($('#rf-check-in'), '2038-06-05');
  check('дата заезда введена — списки перечитаны по фонду на эту дату', await waitFor(() =>
    [...$('#rf-category').options].some(o => o.value === String(cat.id))
    && [...$('#rf-paid').options].some(o => o.value === String(cat.id))));
  change($('#rf-category'), String(cat.id));
  check('«Оплата за» следует за категорией из версии на дату', $('#rf-paid').value === String(cat.id));
  click($('[data-close]'));
}

const DEMO_SURNAMES = ['Лебедев', 'Фомина', 'Зайцев', 'Гусев', 'Кузьмин', 'Белова'];

async function roleSmoke() {
  console.log(`\nСмоук под логином ${LOGIN}`);
  const me = (await apiJson('GET', '/api/auth/me')).body;
  const menu = me.menu.map(m => m.id);
  if (menu.includes('stays')) {
    window.navigate('stays');
    await waitFor(() => $$('#view-stays [data-stab]').length > 0);
    for (const b of $$('#view-stays [data-stab]').map(x => x.dataset.stab)) {
      click($(`[data-stab="${b}"]`));
      const ok = await waitFor(() => !text('#stays-body').includes('Загрузка…') && text('#stays-body').length > 0);
      check(`вкладка «${b}» отрисована`, ok);
      if (me.permissions.includes('stays.occupancy') && !me.permissions.includes('stays.view')) {
        const leaked = DEMO_SURNAMES.filter(s => text('#view-stays').includes(s));
        check(`вкладка «${b}»: без фамилий гостей`, !leaked.length, leaked.join(', '));
      }
    }
    const names = me.permissions.includes('stays.view');
    check(names ? 'вкладка «Брони» есть (с фамилиями)' : 'вкладки «Брони» нет (занятость)',
      !!$('#view-stays [data-stab="bookings"]') === names);
    const full = names && me.permissions.includes('stays.guests');
    check(full ? 'вкладка «Гости» есть (полный уровень)' : 'вкладки «Гости» нет',
      !!$('#view-stays [data-stab="guests"]') === full);
    check('нет мусора в DOM', !/undefined|NaN|\[object Object\]/.test($('#view-stays').innerHTML));
    if (names && !me.permissions.includes('stays.edit')) await familyReadOnly();
  }
  if (menu.includes('mystays')) {
    window.navigate('mystays');
    check('«Мои гости» отрисованы', await waitFor(() => !!$('#mine-body') && !text('#mine-body').includes('Загрузка…')));
    const res = $('[data-mine-res]');
    if (res) {
      click(res);
      check('батлер: форма брони — даты заперты', await waitFor(() => $('#rf-check-in')?.disabled === true));
      check('батлер: общий поиск гостей скрыт', $('#rf-guest-q').closest('.sb-toolbar').style.display === 'none');
      check('батлер: сопровождающих добавить можно', !!$('#rf-comp-add'));
      input($('#rf-note'), 'дописал батлер ' + uniq);
      click($('[data-save]'));
      check('батлер сохранил примечание', await waitFor(() => text('#view-mystays').includes('дописал батлер ' + uniq)));
    }
  }
}

async function moreForms() {
  console.log('\n5 · Блоки, совместное проживание, гость, поля');
  /* все даты шага — в одном месяце (следующем): day(9) — 1-е число */
  const next = addDays(serverToday().slice(0, 8) + '01', 40).slice(0, 8) + '01';
  const day = n => addDays(next, n - 9);
  const code = 'FM' + uniq;
  const { cat, units: [u1, u2] } = await fundCategory(code, [code + '-1', code + '-2']);
  const rField = 'trip' + uniq.toLowerCase(), gField = 'pet' + uniq.toLowerCase();
  await apiJson('POST', '/api/stays/fields', { target: 'reservation', code: rField, title: 'Откуда', kind: 'text' });
  await apiJson('POST', '/api/stays/fields', { target: 'guest', code: gField, title: 'Питомец', kind: 'text' });
  const g = (await apiJson('POST', '/api/stays/guests', { last_name: 'Формин' + uniq })).body;
  const g2 = (await apiJson('POST', '/api/stays/guests', { last_name: 'Связанов' + uniq })).body;
  const ra = (await apiJson('POST', '/api/stays/reservations', { number: 'FA' + uniq, check_in: day(10), check_out: day(13),
    category_id: cat.id, occupants: [{ guest_id: g.id, role: 'main', date_from: day(10), date_to: day(13) }] })).body.result;
  const rb = (await apiJson('POST', '/api/stays/reservations', { number: 'FB' + uniq, check_in: day(10), check_out: day(13),
    category_id: cat.id })).body.result;

  window.navigate('stays');
  await openMonth(day(9));
  await resetFilters();
  await setCheck(`[data-sf-cat="${cat.id}"]`, true);
  check('объекты категории на шахматке', await waitFor(() => !!$(`[data-unit-row="${u2.id}"]`)));

  /* блок / OOO: клик по объекту → форма с предпросмотром */
  click($(`[data-unit-row="${u2.id}"] .sb-unit`));
  check('форма блока открылась', await waitFor(() => !!$('#hf-kind')));
  change($('#hf-kind'), 'ooo'); change($('#hf-start'), day(14)); change($('#hf-end'), day(15)); input($('#hf-title'), 'Ремонт');
  click($('#rf-preview'));
  check('предпросмотр блока', await waitFor(() => /Что изменится/.test(text('#rf-preview-out'))));
  click($('[data-save]'));
  check('OOO на шахматке', await waitFor(() => !!$(`[data-unit-row="${u2.id}"] [data-hold]`)));
  click($(`[data-unit-row="${u2.id}"] [data-hold]`));
  check('правка блока: название подставлено', await waitFor(() => $('#hf-title')?.value === 'Ремонт'));
  click($('#hf-delete'));
  check('удаление блока — с предпросмотром', await waitFor(() => /Что изменится/.test(text('#rf-preview-out'))));
  click($('[data-save]'));
  check('блок удалён', await waitFor(() => !$(`[data-unit-row="${u2.id}"] [data-hold]`)));

  /* совместное проживание из карточки брони */
  await waitFor(() => !!$(`#view-stays [data-bar="${ra.id}"]`));
  click($(`#view-stays [data-bar="${ra.id}"]`));
  check('кнопка «Совместное проживание»', await waitFor(() => !!$('#rc-group')));
  click($('#rc-group'));
  check('подходящая бронь в списке', await waitFor(() => !!$(`[data-cohabit="${rb.id}"]`)));
  $(`[data-cohabit="${rb.id}"]`).checked = true;
  click($('#rf-preview'));
  check('предпросмотр совместного проживания', await waitFor(() => /Что изменится/.test(text('#rf-preview-out'))));
  click($('[data-save]'));
  await sleep(600);
  const da = (await apiJson('GET', `/api/stays/reservations/${ra.id}`)).body;
  const db_ = (await apiJson('GET', `/api/stays/reservations/${rb.id}`)).body;
  check('брони в одной группе и одном объекте', da.group_id && da.group_id === db_.group_id
    && da.segments[0].unit_id === db_.segments[0].unit_id);

  /* сопровождающие и настраиваемые поля брони */
  click($(`#view-stays [data-bar="${ra.id}"]`));
  await waitFor(() => !!$('#rc-edit'));
  click($('#rc-edit'));
  check('форма брони: поле «Откуда»', await waitFor(() => !!$(`[data-rf-field="${rField}"]`)));
  input($(`[data-rf-field="${rField}"]`), 'Москва');
  click($('#rf-comp-add'));
  await waitFor(() => !!$('[data-cp-desc="0"]'));
  change($('[data-cp-kind="0"]'), 'security'); change($('[data-cp-desc="0"]'), 'Охрана 2 чел.');
  click($('[data-save]'));
  await sleep(600);
  const da2 = (await apiJson('GET', `/api/stays/reservations/${ra.id}`)).body;
  check('поле брони сохранено', da2.fields[rField] === 'Москва', JSON.stringify(da2.fields));
  check('сопровождающий сохранён', da2.companions.some(c => c.kind === 'security' && c.description === 'Охрана 2 чел.'));

  /* карточка гостя: история, связи, особые даты, поле */
  click($(`#view-stays [data-bar="${ra.id}"]`));
  await waitFor(() => !!$(`[data-guest-card="${g.id}"]`));
  click($(`[data-guest-card="${g.id}"]`));
  check('карточка гостя: история проживаний', await waitFor(() => text('#gc-history').includes('FA' + uniq)));
  input($('#gc-link-q'), 'Связанов' + uniq);
  check('поиск гостя для связи', await waitFor(() => !!$(`[data-link-pick="${g2.id}"]`)));
  click($(`[data-link-pick="${g2.id}"]`));
  check('семейных видов нет в «Прочих связях» — семья правится в дереве',
    !$$('#gc-link-kind option').some(o => ['spouse', 'spouse_former', 'parent'].includes(o.value)));
  change($('#gc-link-kind'), 'colleague');
  click($('#gc-link-add'));
  check('связь «коллега» в карточке', await waitFor(() => text('#gc-links').includes('Связанов' + uniq)
    && text('#gc-links').includes('коллега')));
  click($('#gc-edit'));
  check('форма гостя: особые даты', await waitFor(() => !!$('#gf-sd-add')));
  click($('#gf-sd-add'));
  await waitFor(() => !!$('[data-sd-what="0"]'));
  change($('[data-sd-date="0"]'), day(30)); change($('[data-sd-what="0"]'), 'юбилей');
  input($(`[data-gf-field="${gField}"]`), 'кот');
  click($('[data-save]'));
  await sleep(600);
  const gc = (await apiJson('GET', `/api/stays/guests/${g.id}`)).body;
  check('особая дата сохранена', gc.special_dates.some(x => x.what === 'юбилей' && x.date === day(30)), JSON.stringify(gc.special_dates));
  check('поле гостя сохранено', gc.fields[gField] === 'кот');
  check('связь видна в профиле', gc.links.some(l => l.guest_id === g2.id && l.label === 'коллега'));
  check('нет мусора в DOM', !/undefined|NaN|\[object Object\]/.test($('#view-stays').innerHTML + ($('#modal')?.innerHTML || '')));
  void u1;
}

/* 8 · вкладка «Брони»: 205 односуточных броней в далёком окне (больше одной страницы в 200) */
async function bookingsTab() {
  console.log('\n8 · Вкладка «Брони»');
  const day = n => addDays(serverToday(), n);
  const code = 'BK' + uniq;
  const { cat } = await fundCategory(code, [code + '-1']);
  const evil = `<i id="bk-xss">Зло${uniq}</i>`;
  const g = (await apiJson('POST', '/api/stays/guests', { last_name: evil })).body;
  const N = 205;
  const made = [];
  for (let i = 0; i < N; i += 10) {
    const batch = await Promise.all(Array.from({ length: Math.min(10, N - i) }, (_, k) => {
      const n = i + k;
      return apiJson('POST', '/api/stays/reservations', { number: `BK${uniq}-${n}`, check_in: day(30 + n), check_out: day(31 + n),
        category_id: cat.id, occupants: n === 0 ? [{ guest_id: g.id, role: 'main', date_from: day(30), date_to: day(31) }] : [] });
    }));
    made.push(...batch);
  }
  check(`создано ${N} броней`, made.every(r => r.status === 200), JSON.stringify(made.find(r => r.status !== 200)?.body));

  window.eval('staysState.filters = staysEmptyFilters(); Object.assign(staysBook, staysBookEmpty());');
  window.navigate('stays');
  await waitFor(() => $$('#view-stays [data-stab]').length > 0);
  check('вкладка «Брони» есть', !!$('#view-stays [data-stab="bookings"]'));
  click($('#view-stays [data-stab="bookings"]'));
  check('вкладка «Брони» отрисована', await waitFor(() => !!$('#bk-total')));
  const rerendered = async (sel, act) => { const old = $(sel); act(); return waitFor(() => $(sel) && $(sel) !== old); };
  check('свой период', await rerendered('#bk-period', () => change($('#bk-period'), 'custom')) && !!$('#bk-first'));
  await rerendered('#bk-first', () => change($('#bk-first'), day(30)));
  check('конец периода ограничен 366 днями', $('#bk-last').max === day(30 + 365));
  await rerendered('#bk-last', () => change($('#bk-last'), day(240)));
  await rerendered('#bk-mode', () => change($('#bk-mode'), 'check_in'));
  /* в окне могут быть и брони прежних шагов сценария: всего не меньше созданных */
  const total = Number(text('#bk-total').match(/Найдено броней: (\d+)/)?.[1]);
  check(`всего не меньше ${N} броней, показано 200`, total >= N && $$('[data-bk-row]').length === 200, text('#bk-total'));

  const thOut = () => $('[data-bk-sort="check_out"]');
  await rerendered('#bk-total', () => click(thOut()));
  check('сортировка по выезду ↑', thOut().textContent.includes('↑'));
  await rerendered('#bk-total', () => click(thOut()));
  check('повторный клик — «Выезд ↓»', thOut().textContent.includes('↓'));
  const firstOut = $('[data-bk-row] td:nth-child(4)')?.textContent.trim();
  check('первой идёт самая поздняя бронь', firstOut === window.eval(`dateRu('${day(30 + N)}')`), firstOut);

  click($('#bk-more'));
  check('«Показать ещё» добавляет строки', await waitFor(() => $$('[data-bk-row]').length === total), String($$('[data-bk-row]').length));
  check('кнопки «Показать ещё» больше нет', !$('#bk-more'));

  check('гость в списке экранирован (текстом, не разметкой)', !$('#bk-xss') && text('#bk-result').includes('<i id="bk-xss">'));
  const resRow = $$('[data-bk-row]').find(tr => tr.textContent.includes(`BK${uniq}-0`));
  click(resRow);
  check('клик по строке открывает карточку', await waitFor(() => text('#modal').includes(`Бронь BK${uniq}-0`)), text('#modal'));
  check('в карточке гость показан текстом', !$('#bk-xss') && text('#modal').includes('Зло' + uniq));
  click($('#modal [data-close]'));
  await sleep(200);

  const exp = await proxy('GET', `/api/stays/bookings/export?first=${day(30)}&last=${day(240)}&mode=check_in`);
  check('выгрузка xlsx отдаётся', exp.status === 200 && String(exp.headers['content-type']).includes('spreadsheetml'), String(exp.status));
  check('кнопка «Выгрузить» у менеджера', !!$('#bk-xlsx'));

  /* период длиннее 366 дней: сообщение сервера видно пользователю */
  window.eval(`staysBook.first = '${day(0)}'; staysBook.last = '${day(400)}'; staysBook.custom = true;`);
  click($('#view-stays [data-stab="units"]'));
  await waitFor(() => !!$('.sb-grid'));
  click($('#view-stays [data-stab="bookings"]'));
  check('период больше 366 дней: объяснение', await waitFor(() => text('#stays-body').includes('не больше 366')), text('#stays-body'));
  window.eval('Object.assign(staysBook, staysBookEmpty());');
  check('нет мусора в DOM', !/undefined|NaN|\[object Object\]/.test($('#view-stays').innerHTML));
}

/* 9 · вкладка «Гости»: справочник, поиск, «день рождения в ближайшие 30 дней», карточка, объединение */
async function guestsTab() {
  console.log('\n9 · Вкладка «Гости»');
  const today = serverToday();
  const soon = addDays(today, 10);
  const birth = `${Number(soon.slice(0, 4)) - 40}${soon.slice(4)}`.replace(/-02-29$/, '-02-28');
  const code = 'GS' + uniq;
  const { cat } = await fundCategory(code, [code + '-1']);
  const mk = body => apiJson('POST', '/api/stays/guests', body).then(r => r.body);
  const keep = await mk({ last_name: `Дублёв${uniq}`, first_name: 'Пётр', phone: '+7 916 400-11-22', birth_date: birth });
  const drop = await mk({ last_name: `Дублёв${uniq}`, first_name: 'Петя', preferences: { food: 'без лактозы' },
    special_dates: [{ date: '2020-06-01', what: 'годовщина' }] });
  const res = await apiJson('POST', '/api/stays/reservations', { number: `GS${uniq}`, check_in: addDays(today, 50),
    check_out: addDays(today, 52), category_id: cat.id, occupants: [{ guest_id: drop.id, role: 'main',
      date_from: addDays(today, 50), date_to: addDays(today, 52) }] });
  check('гости и бронь дубля созданы', !!keep.id && !!drop.id && res.status === 200, JSON.stringify(res.body));

  window.eval('Object.assign(staysGuests, staysGuestsEmpty());');
  window.navigate('stays');
  await waitFor(() => $$('#view-stays [data-stab]').length > 0);
  check('вкладка «Гости» есть', !!$('#view-stays [data-stab="guests"]'));
  click($('#view-stays [data-stab="guests"]'));
  check('вкладка «Гости» отрисована', await waitFor(() => !!$('#gl-total')));
  const rerendered = async (sel, act) => { const old = $(sel); act(); return waitFor(() => $(sel) && $(sel) !== old); };
  /* посимвольный ввод с паузой дольше задержки поиска: поле не перерисовывается, фокус и текст на месте */
  const q = $('#gl-q');
  q.focus();
  const typed = `дублёв${uniq}`.toLowerCase();
  const firstTotal = $('#gl-total');
  for (const [i, ch] of [...typed].entries()) {
    q.value += ch;
    q.dispatchEvent(new window.Event('input', { bubbles: true }));
    await sleep(i === 3 ? 700 : 40);           // на 4-м символе поиск успевает уйти и вернуться
  }
  check('поиск по фамилии', await waitFor(() => $('#gl-total') !== firstTotal && $$('[data-gl-row]').length === 2),
    text('#gl-total'));
  check('при вводе поле поиска не теряет фокус и текст', $('#gl-q') === q && window.document.activeElement === q
    && q.value === typed, `${window.document.activeElement?.id} «${q.value}»`);
  check('телефон виден полному уровню', text('#gl-result').includes('+7 916 400-11-22'));
  await rerendered('#gl-total', () => input($('#gl-q'), `GS${uniq}`));
  check('поиск по номеру брони — гость брони', $$('[data-gl-row]').map(tr => Number(tr.dataset.glRow)).join() === String(drop.id));
  await rerendered('#gl-total', () => input($('#gl-q'), `дублёв${uniq}`));
  await rerendered('#gl-total', () => { $('#gl-birthday').checked = true; change($('#gl-birthday')); });
  check('фильтр «день рождения в ближайшие 30 дней»', $$('[data-gl-row]').map(tr => Number(tr.dataset.glRow)).join() === String(keep.id),
    text('#gl-total'));
  await rerendered('#gl-total', () => { $('#gl-birthday').checked = false; change($('#gl-birthday')); });

  click($(`[data-gl-row="${drop.id}"] td:nth-child(2)`));
  check('клик по строке открывает карточку гостя', await waitFor(() => text('#modal').includes('История проживаний')
    && text('#modal').includes(`GS${uniq}`)), text('#modal'));
  click($('#modal [data-close]'));
  await sleep(200);

  for (const id of [keep.id, drop.id]) click($(`[data-gl-pick="${id}"]`));     // клик отмечает флажок
  check('«Объединить…» доступна для двух отмеченных', $('#gl-merge') && !$('#gl-merge').disabled);
  click($('#gl-merge'));
  check('окно объединения', await waitFor(() => !!$('#gm-preview')));
  click($('#gm-preview'));
  check('предпросмотр: что перенесётся', await waitFor(() => text('#gm-out').includes(`GS${uniq}`)
    && text('#gm-out').includes('food') && text('#gm-out').includes('годовщина')), text('#gm-out'));
  const still = (await apiJson('GET', `/api/stays/guests/${drop.id}`)).status;
  check('предпросмотр ничего не сохранил', still === 200, String(still));
  click($('#modal [data-save]'));
  check('после объединения в списке один гость', await waitFor(() => !$('#modal').innerHTML
    && $$('[data-gl-row]').length === 1 && !!$(`[data-gl-row="${keep.id}"]`)), text('#gl-total'));
  const card = (await apiJson('GET', `/api/stays/guests/${keep.id}/card`)).body;
  check('бронь и предпочтения перешли оставленному', card.stays.some(x => x.number === `GS${uniq}`)
    && card.preferences.food === 'без лактозы', JSON.stringify(card.stays));
  check('дубль удалён', (await apiJson('GET', `/api/stays/guests/${drop.id}`)).status === 404);
  window.eval('Object.assign(staysGuests, staysGuestsEmpty());');
  check('нет мусора в DOM', !/undefined|NaN|\[object Object\]/.test($('#view-stays').innerHTML));
}

/* 10 · семейное дерево: визуальный редактор в карточке гостя (addendum §4) */
async function familyEditor() {
  console.log('\n10 · Семейное дерево: визуальный редактор');
  const mk = (last, first, gender) => apiJson('POST', '/api/stays/guests', { last_name: last + uniq, first_name: first, gender })
    .then(r => r.body);
  const grandma = await mk('Бабушкина', 'Анна', 'f');
  const mother = await mk('Матвеева', 'Ольга', 'f');
  const ivan = await mk('Семьин', 'Иван', 'm');
  const maria = await mk('Семьина', 'Мария', 'f');
  const stranger = await mk('Чужов', '<i>Пётр</i>', 'm');
  const father = await mk('Отцов', 'Николай', 'm');
  const link = (a, b, kind) => apiJson('POST', `/api/stays/guests/${a.id}/links`, { guest_id: b.id, kind });
  for (const [a, b, kind] of [[grandma, mother, 'parent'], [mother, ivan, 'parent'], [ivan, maria, 'spouse']]) await link(a, b, kind);
  const fam = async id => (await apiJson('GET', `/api/stays/guests/${id}/family`)).body;
  const centre = () => Number($('#gc-family .ft-centre')?.dataset.ftPerson);
  const tree = () => text('#gc-family .ft-tree');
  const toastHas = s => waitFor(() => text('#toast-host').includes(s));

  window.navigate('stays');
  await waitFor(() => $$('#view-stays [data-stab]').length > 0);
  window.eval(`openGuestCard(${ivan.id})`);
  check('дерево в карточке гостя: Иван в центре', await waitFor(() => centre() === ivan.id));
  check('родитель сверху, супруга рядом', tree().includes('Матвеева' + uniq) && tree().includes('мать')
    && tree().includes('Семьина' + uniq) && !!$('#gc-family [data-ft-former]'));
  check('редактор: кнопки «+ родитель / + супруг(а) / + ребёнок»', ['parent', 'spouse', 'child']
    .every(k => !!$(`#gc-family [data-ft-add="${k}"]`)));

  /* пример владельца: Ивану и Марии — сын (новый гость, «и ребёнок супруги» отмечено) */
  click($('#gc-family [data-ft-add="child"]'));
  check('панель «Добавить ребёнка»', await waitFor(() => !!$('#gc-family [data-ft-last]')));
  check('«и ребёнок: Мария» отмечено', $('#gc-family [data-ft-both]')?.checked === true);
  $('#gc-family [data-ft-last]').value = 'Семьин' + uniq;
  $('#gc-family [data-ft-first]').value = 'Сын';
  change($('#gc-family [data-ft-gender]'), 'm');
  click($('#gc-family [data-ft-create]'));
  check('сын появился в дереве снизу', await waitFor(() => tree().includes('Сын') && tree().includes('сын')), tree());
  const son = (await fam(ivan.id)).people.find(p => p.name.includes('Сын'));
  const sonFam = son ? await fam(son.id) : { parents: [] };
  check('у сына оба родителя — Иван и Мария', son && [ivan.id, maria.id].every(p => sonFam.parents.some(([c, x]) => c === son.id && x === p)),
    JSON.stringify(sonFam.parents));

  click($(`#gc-family .ft-tree [data-ft-person="${mother.id}"]`));
  check('клик по матери — она в центре', await waitFor(() => centre() === mother.id));
  click($(`#gc-family .ft-tree [data-ft-person="${grandma.id}"]`));
  check('клик по бабушке — она в центре', await waitFor(() => centre() === grandma.id));
  const kin = text('#gc-family .ft-kin');
  check('у бабушки Ивана в «Все родственники» — правнук', kin.includes('Сын') && /правнук/.test(kin) && kin.includes('внук'), kin);
  click($('#gc-family [data-ft-home]'));
  check('«← к Ивану» возвращает в центр', await waitFor(() => centre() === ivan.id));

  /* запрет третьего родителя: тост с текстом сервера */
  click($(`#gc-family .ft-tree [data-ft-person="${son.id}"]`));
  await waitFor(() => centre() === son.id);
  click($('#gc-family [data-ft-add="parent"]'));
  await waitFor(() => !!$('#gc-family [data-ft-q]'));
  input($('#gc-family [data-ft-q]'), 'Чужов' + uniq);
  check('поиск гостя для связи', await waitFor(() => !!$(`#gc-family [data-ft-pick="${stranger.id}"]`)));
  check('имя в поиске экранировано', !$('#gc-family i'));
  click($(`#gc-family [data-ft-pick="${stranger.id}"]`));
  check('третий родитель — тост с текстом сервера', await toastHas('У ребёнка не больше двух родителей'), text('#toast-host'));
  check('третий родитель не добавлен', (await fam(son.id)).parents.filter(([c]) => c === son.id).length === 2);
  /* новый третий родитель: кнопка заперта с пояснением; в обход — сервер отказывает и гостя не создаёт */
  click($('#gc-family [data-ft-add="parent"]'));
  await waitFor(() => !!$('#gc-family [data-ft-create]'));
  check('два родителя: «Создать и связать» заперта с пояснением', $('#gc-family [data-ft-create]').disabled
    && text('#gc-family [data-ft-blocked]').includes('два родителя'));
  $('#gc-family [data-ft-last]').value = 'Лишний' + uniq;
  $('#gc-family [data-ft-create]').disabled = false;
  $('#toast-host').innerHTML = '';
  click($('#gc-family [data-ft-create]'));
  check('новый третий родитель — тост с текстом сервера', await toastHas('У ребёнка не больше двух родителей'), text('#toast-host'));
  check('новый третий родитель — гость не создан', !(await apiJson('GET', `/api/stays/guests?q=${encodeURIComponent('Лишний' + uniq)}`)).body.length);

  /* «бывшие» на линии супругов */
  click($('#gc-family [data-ft-home]'));
  await waitFor(() => centre() === ivan.id);
  const former = $('#gc-family [data-ft-former]');
  former.checked = true;
  change(former);
  check('«бывшие» сохранены', await waitFor(() => $('#gc-family [data-ft-former]') !== former
    && $('#gc-family [data-ft-former]').checked));
  check('API: брак бывший', (await fam(ivan.id)).links.some(l => l.kind === 'spouse' && l.former));
  const back = $('#gc-family [data-ft-former]');
  back.checked = false;
  change(back);
  await waitFor(() => $('#gc-family [data-ft-former]') !== back);
  check('«бывшие» сняты', (await fam(ivan.id)).links.some(l => l.kind === 'spouse' && !l.former));

  /* второй родитель Ивана через поиск — и удаление связи крестиком на линии */
  click($('#gc-family [data-ft-add="parent"]'));
  await waitFor(() => !!$('#gc-family [data-ft-q]'));
  input($('#gc-family [data-ft-q]'), 'Отцов' + uniq);
  await waitFor(() => !!$(`#gc-family [data-ft-pick="${father.id}"]`));
  click($(`#gc-family [data-ft-pick="${father.id}"]`));
  check('отец добавлен сверху', await waitFor(() => tree().includes('Отцов' + uniq) && tree().includes('отец')), tree());
  const fl = (await fam(ivan.id)).links.find(l => l.kind === 'parent' && l.a === father.id && l.b === ivan.id);
  click($(`#gc-family [data-ft-del="${fl?.id}"]`));
  check('связь удалена крестиком', await waitFor(() => !tree().includes('Отцов' + uniq)), tree());
  check('API: связи с отцом нет', !(await fam(ivan.id)).links.some(l => l.a === father.id));
  check('нет мусора в DOM', !/undefined|NaN|\[object Object\]/.test($('#modal').innerHTML));
  click($('#modal [data-close]'));
  await sleep(200);

  /* карточка брони: дерево только для чтения */
  const code = 'FT' + uniq;
  const { cat } = await fundCategory(code, [code + '-1']);
  const ci = addDays(serverToday(), 70);
  const res = (await apiJson('POST', '/api/stays/reservations', { number: code, check_in: ci, check_out: addDays(ci, 2),
    category_id: cat.id, occupants: [{ guest_id: ivan.id, role: 'main', date_from: ci, date_to: addDays(ci, 2) }] })).body.result;
  window.eval(`openReservationCard(${res.id})`);
  await waitFor(() => !!$(`#modal [data-family="${ivan.id}"]`));
  click($(`#modal [data-family="${ivan.id}"]`));
  const box = `#modal [data-family-box="${ivan.id}"]`;
  check('карточка брони: дерево семьи', await waitFor(() => !!$(`${box} .ft-centre`) && text(`${box} .ft-kin`).includes('сын')),
    text(box));
  check('карточка брони: только просмотр', !$(`${box} [data-ft-add]`) && !$(`${box} [data-ft-del]`) && !$(`${box} [data-ft-former]`));
  click($('#modal [data-close]'));
  await sleep(200);
}

/* уровень «с фамилиями» без права записи: дерево в карточке брони — без кнопок редактора */
async function familyReadOnly() {
  const day = (await apiJson('GET', `/api/stays/day?date=${serverToday()}`)).body;
  const row = (day.in_house || []).find(r => r.guests?.some(g => g.relatives?.length));
  if (!row) { check('табло дня: семья среди проживающих (демо)', false); return; }
  const gid = row.guests.find(g => g.relatives?.length).guest_id;
  window.eval(`openReservationCard(${row.reservation_id})`);
  await waitFor(() => !!$(`#modal [data-family="${gid}"]`));
  click($(`#modal [data-family="${gid}"]`));
  const box = `#modal [data-family-box="${gid}"]`;
  check('«с фамилиями»: семейное дерево в карточке брони', await waitFor(() => !!$(`${box} .ft-centre`)
    && text(`${box} .ft-kin`).length > 0), text(box));
  check('«с фамилиями» без права записи: дерево только для чтения', !$(`${box} [data-ft-add]`) && !$(`${box} [data-ft-del]`));
  click($('#modal [data-close]'));
  await sleep(200);
}

/* выход уже нажат: вход другим логином тем же путём, что в main (JSON-вход + bootApp) */
async function relogin(username) {
  await sleep(300);
  const r = await proxy('POST', '/api/auth/login', { body: JSON.stringify({ username, password: 'demo1234' }),
    headers: { 'Content-Type': 'application/json' } });
  if (!r.ok) return false;
  window.eval('bootApp()');
  const ok = await waitFor(() => !$('#app').classList.contains('hidden'), 30000);
  await sleep(500);
  return ok;
}

async function main() {
  await sleep(400);
  const loginRes = await proxy('POST', '/api/auth/login', {
    body: JSON.stringify({ username: LOGIN, password: 'demo1234' }),
    headers: { 'Content-Type': 'application/json' } });
  if (loginRes.ok) window.eval('bootApp()');
  await waitFor(() => !$('#app').classList.contains('hidden'), 30000);
  check('вход выполнен', !$('#app').classList.contains('hidden'), text('#login-error'));
  await sleep(500);
  if (LOGIN === 'admin') {
    await settingsScreens();
    await unitsBoard();
    await butlersAndDay();
    await occupancyAndFund();
    await moreForms();
    await savedFilters();
    await flagMidMonth();
    await formFundOnCheckIn();
    await bookingsTab();
    await guestsTab();
    await familyEditor();
  } else {
    await roleSmoke();
  }

  console.log(`\n=== ошибки консоли ===`);
  const errs = [...new Set(consoleErrors.map(e => e.slice(0, 240)))];
  errs.length ? errs.forEach(e => console.log('  ' + e)) : console.log('  нет');
  failed += errs.length;
  console.log(`\nИТОГ: проверок пройдено ${passed}, провалено ${failed}`);
  process.exit(failed ? 2 : 0);
}

main().catch(e => { console.error('сценарий:', e); process.exit(1); });
