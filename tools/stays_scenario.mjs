/* Сценарий модуля «Шахматка»: jsdom + РЕАЛЬНЫЙ сервер, без браузера (как settings_scenario).

Проходит пользовательские пути модуля (docs/superpowers/specs/2026-10-23-stays-chessboard-design.md):
  1. экраны Настроек: фонд и категории, сопровождение, настраиваемые поля, метки;
  2. шахматка объектов: бронь формой с предпросмотром, вытеснение чужой брони, 409, карточка;
  3. батлеры: назначение шаблоном → «вне смены» → «Добавить смену» → табло дня;
  4. сводная загрузка, полный фонд на шахматке; под другими логинами — смоук вкладок и «Мои гости»;
  5. блок/OOO, совместное проживание, карточка гостя со связями, особые даты, сопровождающие, поля.

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
const uniq = Date.now().toString(36).slice(-5).toUpperCase();

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
  click($('#sf-cat-add'));
  check('форма категории открылась', await waitFor(() => !!$('#sf-code')));
  input($('#sf-code'), 'SC' + uniq); input($('#sf-title'), 'Сценарий ' + uniq);
  change($('#sf-kind'), 'villa'); input($('#sf-weight'), '4');
  $('#sf-escorted').checked = true;
  click($('[data-save]'));
  check('категория сохранена и видна', await waitFor(() => text('#st-body').includes('SC' + uniq)));
  click($('#sf-unit-add'));
  check('форма объекта открылась', await waitFor(() => !!$('#sf-label')));
  input($('#sf-label'), 'V' + uniq);
  change($('#sf-cat'), $$('#sf-cat option').find(o => o.textContent.includes('SC' + uniq))?.value);
  input($('#sf-building'), '1');
  click($('[data-save]'));
  check('объект сохранён и виден', await waitFor(() => text('#st-body').includes('V' + uniq)));
  const fund = (await apiJson('GET', '/api/stays/fund')).body;
  check('объект на сервере с категорией', fund.units.some(u => u.label === 'V' + uniq
    && fund.categories.find(c => c.id === u.category_id)?.code === 'SC' + uniq));

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
  const cat = (await apiJson('POST', '/api/stays/categories', { code, title: code, kind: 'villa', escorted: true, weight: 4 })).body;
  const u1 = (await apiJson('POST', '/api/stays/units', { label: code + '-1', category_id: cat.id })).body;
  const u2 = (await apiJson('POST', '/api/stays/units', { label: code + '-2', category_id: cat.id })).body;
  const guest = 'Сценарный' + uniq;
  await apiJson('POST', '/api/stays/guests', { last_name: guest });

  window.navigate('stays');
  check('вкладки шахматки', await waitFor(() => $$('#view-stays [data-stab]').length === 4));
  change($('#sb-first'), '2030-01-01');
  change($('#sb-cat'), String(cat.id));
  check('строки объектов категории', await waitFor(() => $$('#view-stays [data-unit-row]').length === 2));

  click($('#sb-new'));
  check('форма брони открылась', await waitFor(() => !!$('#rf-check-in')));
  input($('#rf-number'), 'A' + uniq);
  change($('#rf-category'), String(cat.id));
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

  const a = (await apiJson('GET', '/api/stays/board/units?first=2030-01-01&last=2030-01-14&category_id=' + cat.id))
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
  const base = new Date(Date.now() - new Date().getTimezoneOffset() * 60000);
  const day = n => iso(new Date(base.getTime() + n * 86400000));
  const code = 'BT' + uniq;
  const cat = (await apiJson('POST', '/api/stays/categories', { code, title: code, kind: 'villa', escorted: true, weight: 4 })).body;
  await apiJson('POST', '/api/stays/units', { label: code + '-1', category_id: cat.id });
  const guest = 'Ведомый' + uniq;
  const g = (await apiJson('POST', '/api/stays/guests', { last_name: guest })).body;
  const res = (await apiJson('POST', '/api/stays/reservations', { number: 'C' + uniq, check_in: day(1), check_out: day(7),
    category_id: cat.id, occupants: [{ guest_id: g.id, role: 'main', date_from: day(1), date_to: day(7) }] })).body.result;
  const fund = (await apiJson('GET', '/api/stays/fund')).body;
  const ivanov = fund.escorts.find(e => e.name.startsWith('Иванов'));
  check('Иванов в «Сопровождают гостей»', !!ivanov);

  window.navigate('stays');
  /* ждём свежую отрисовку: фильтры старой разметки ушли бы в гонку с перерисовкой */
  await waitFor(() => $$('#sb-cat option').some(o => o.value === String(cat.id)));
  change($('#sb-first'), day(1));
  await waitFor(() => text('#view-stays .sb-head').includes(day(1).slice(8, 10) + '.' + day(1).slice(5, 7)));
  change($('#sb-cat'), String(cat.id));
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

  click($('[data-stab="butlers"]'));
  check('шахматка батлеров открылась', await waitFor(() => !!$('#bb-first')));
  change($('#bb-first'), day(1));
  await waitFor(() => !$(`[data-bb-emp][data-day="${day(0)}"]`) && !!$(`[data-bb-emp][data-day="${day(1)}"]`));
  /* ночи брони C — day(1)…day(6); вне их «вне смены» может давать демо-назначение */
  const nights = [1, 2, 3, 4, 5, 6].map(day);
  const offCell = () => $$(`[data-bb-emp="${ivanov.employee_id}"][data-warn*="off_shift"]`).find(c => nights.includes(c.dataset.day));
  check('день «вне смены» подсвечен', await waitFor(() => !!offCell()));
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
  click($('[data-stab="butlers"]'));
  await waitFor(() => !!$('#bb-first'));
  change($('#bb-first'), day(1));
  await waitFor(() => !$(`[data-bb-emp][data-day="${day(0)}"]`) && !!$(`[data-bb-emp="${ivanov.employee_id}"][data-day="${day(1)}"]`));
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
  console.log('\n4 · Загрузка и полный фонд');
  click($('[data-stab="occupancy"]'));
  check('сводная загрузка отрисована', await waitFor(() => $$('[data-oc-cat]').length > 0));
  const cell = $('[data-oc-cat]');
  const cat = cell.dataset.ocCat;
  click(cell);
  check('клик — шахматка объектов категории', await waitFor(() => $('#sb-cat')?.value === cat));
  change($('#sb-cat'), '');
  const t0 = Date.now();
  check('полный фонд на шахматке (≥ 440 объектов)', await waitFor(() => $$('#view-stays [data-unit-row]').length >= 440, 20000),
    String($$('#view-stays [data-unit-row]').length));
  const ms = Date.now() - t0;
  console.log(`  · отрисовка полного фонда: ${ms} мс`);
  check('полный фонд — быстрее 3 с (вместе с запросом)', ms < 3000, `${ms} мс`);
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
    check('нет мусора в DOM', !/undefined|NaN|\[object Object\]/.test($('#view-stays').innerHTML));
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
  const iso = d => d.toISOString().slice(0, 10);
  const base = new Date(Date.now() - new Date().getTimezoneOffset() * 60000);
  const day = n => iso(new Date(base.getTime() + n * 86400000));
  const code = 'FM' + uniq;
  const cat = (await apiJson('POST', '/api/stays/categories', { code, title: code, kind: 'villa', escorted: true, weight: 4 })).body;
  const u1 = (await apiJson('POST', '/api/stays/units', { label: code + '-1', category_id: cat.id })).body;
  const u2 = (await apiJson('POST', '/api/stays/units', { label: code + '-2', category_id: cat.id })).body;
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
  await waitFor(() => $$('#sb-cat option').some(o => o.value === String(cat.id)));
  click($('[data-stab="units"]'));
  await waitFor(() => $$('#sb-cat option').some(o => o.value === String(cat.id)));
  change($('#sb-first'), day(9));
  await waitFor(() => !!$('#sb-cat') && text('#view-stays .sb-head').includes(day(9).slice(8, 10) + '.'));
  change($('#sb-cat'), String(cat.id));
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
  change($('#gc-link-kind'), 'spouse');
  click($('#gc-link-add'));
  check('связь «супруг(а)» в карточке', await waitFor(() => text('#gc-links').includes('Связанов' + uniq)
    && text('#gc-links').includes('супруг(а)')));
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
  check('связь видна в профиле', gc.links.some(l => l.guest_id === g2.id && l.label === 'супруг(а)'));
  check('нет мусора в DOM', !/undefined|NaN|\[object Object\]/.test($('#view-stays').innerHTML + ($('#modal')?.innerHTML || '')));
  void u1;
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
