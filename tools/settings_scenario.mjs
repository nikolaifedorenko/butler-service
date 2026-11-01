/* Сценарий раздела «Настройки»: jsdom + РЕАЛЬНЫЙ сервер, без браузера.

Зачем: смоук (tools/ui_harness.mjs) проверяет, что разделы ОТРИСОВАНЫ, но не нажимает
кнопки — а ломался интерфейс именно на действиях (конфликт правил сохранялся и ронял
вкладки в 500, «Оплачиваются ли переработки» не находилась). Сценарий проходит
пользовательские пути нового раздела настроек (docs/SETTINGS-UI-PROPOSAL-2026-10-12.md):

  1. правило оплаты находится за 1 клик и читается словами;
  2. мастер «что → кому → когда» сохраняет переопределение, оно видно в списке;
  3. «Проверитель» объясняет значение для (сотрудник, день) с уровнем приоритета;
  4. новое значение Табеля добавляется формой (без JSON) и публикуется версией;
  5. черновик справочников показывает diff и сбрасывается;
  6. календарь правил открывает панель дня;
  7. каждый под-экран содержит свои данные (нет «Загрузка…» и мусора в DOM).

Запуск: tools/run_settings_scenario.sh [порт] [логин]   (нужен jsdom: npm i)
Код возврата: 0 — сценарий пройден, 2 — есть проваленные проверки. */
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { fileURLToPath } from 'node:url';
import { JSDOM, VirtualConsole } from 'jsdom';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const BASE = process.argv[2] || 'http://127.0.0.1:8142';
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

async function main() {
  await sleep(400);
  const loginRes = await proxy('POST', '/api/auth/login', {
    body: JSON.stringify({ username: LOGIN, password: 'demo1234' }),
    headers: { 'Content-Type': 'application/json' } });
  if (loginRes.ok) window.eval('bootApp()');
  await waitFor(() => !$('#app').classList.contains('hidden'), 30000);
  check('вход выполнен', !$('#app').classList.contains('hidden'), text('#login-error'));
  /* «сегодня» — дата объекта (APP_TZ) с сервера, а не часы раннера CI (UTC) */
  const today = (await (await proxy('GET', '/api/health')).json()).server_time_local.slice(0, 10);
  const tomorrow = new Date(Date.parse(today + 'T00:00:00Z') + 86400000).toISOString().slice(0, 10);
  await sleep(500);

  window.navigate('settings');
  check('раздел «Настройки» открылся', await waitFor(() => !!$('#st-nav')));
  /* оболочка рисуется раньше содержимого экрана: ждём именно «Обзор», иначе
     проверки ниже срабатывают на плейсхолдере «Загрузка…» (ложный провал) */
  await waitFor(() => {
    const t = text('#st-body');
    return t && !t.includes('Загрузка…');
  });
  const navIds = $$('#st-nav [data-st]').map(b => b.dataset.st);
  console.log('  под-экраны:', navIds.join(', '));
  for (const id of ['overview', 'calc', 'pay', 'codes', 'groups', 'calendar', 'shifts', 'docs', 'system', 'expert']) {
    check(`в под-навигации есть «${id}»`, navIds.includes(id));
  }
  check('hash-адрес экрана', window.location.hash === '#/settings/overview', window.location.hash);

  /* ── 1. Обзор: паспорт, здоровье, «вступит в силу» ── */
  console.log('\n1 · Обзор');
  check('действующая версия справочников видна', /версия справочников|справочники по умолчанию/i.test(text('#st-body')));
  check('здоровье конфигурации отрисовано', !!$('.health', $('#st-body')) || /Конфигурация здорова/.test(text('#st-body')));
  check('счётчики паспорта', /Шаг расчёта/.test(text('#st-body')) && /Кодов Табеля/.test(text('#st-body')));
  check('нет мусора в DOM', !/undefined|NaN|\[object Object\]/.test($('#st-body').innerHTML));

  /* ── 2. Правила оплаты: «Оплачиваются ли переработки» за 1 клик ── */
  console.log('\n2 · Правила оплаты');
  await go('pay');
  check('карточка «Оплачиваются ли переработки»', /Оплачиваются ли переработки/.test(text('#st-body')));
  check('все четыре правила — карточками', $$('#st-body .rule-card').length >= 4,
    String($$('#st-body .rule-card').length));
  check('глобальное значение показано словами', /глобально/.test(text('#st-body')));
  check('цепочка приоритетов 1–7', /сотрудник \+ день/.test(text('#st-body')) && /глобальный дефолт/.test(text('#st-body')));
  check('переопределения видны списком', /переопределений в месяце/.test(text('#st-body')));

  /* ── 3. Мастер «что → кому → когда» ── */
  console.log('\n3 · Мастер переопределения');
  click($('#py-add'));
  check('мастер открылся', await waitFor(() => !!$('#wz-name')));
  change($('#wz-name'), 'pays_overtime');
  change($('#wz-value'), '0');
  change($('#wz-scope'), 'all');
  change($('#wz-when'), 'day');
  change($('#wz-date'), today);
  input($('#wz-note'), 'сценарий интерфейса');
  check('предпросмотр показывает уровень', /Уровень приоритета/.test(text('#wz-preview'))
    && /все \+ день/.test(text('#wz-preview')), text('#wz-preview'));
  click($('[data-save]'));
  check('переопределение сохранилось и видно в списке',
    await waitFor(() => text('#st-body').includes('сценарий интерфейса'), 15000),
    text('#st-body').slice(0, 200));

  /* ── 4. Проверитель ── */
  console.log('\n4 · Проверитель');
  click($('#py-resolve'));
  check('проверитель открылся', await waitFor(() => !!$('#rs-go')));
  check('ответ с сервера получен', await waitFor(() => /Уровень|глобальный дефолт|правило #/i.test(text('#rs-out'))),
    text('#rs-out').slice(0, 200));
  check('значение объяснено источником', /производственный календарь|глобальный дефолт|правило #|колонка/i.test(text('#rs-out')));
  click($('[data-close]'));
  await sleep(200);

  /* ── 5. Коды Табеля: карточки кодов, форма вместо JSON + публикация версии ── */
  console.log('\n5 · Коды Табеля');
  await go('codes');
  check('компактный список кодов: имя и действия', await waitFor(() => $$('#st-body .code-card').length > 0)
    && $$('#st-body [data-cedit]').length > 0 && $$('#st-body [data-cdel]').length > 0);
  check('флаги и отметки НЕ дублируются в списке (18.10.2026)', !$$('#st-body [data-flag]').length
    && !$$('#st-body [data-punch]').length && !$$('#st-body [data-doc]').length);
  check('словаря смен на экране кодов НЕТ', !/Новая смена/.test(text('#st-body')));
  check('код-артефакт «НБ» исключён из справочника', !$('[data-cdel="НБ"]') && !$('[data-cedit="НБ"]'));
  click($('[data-cedit="Я"]'));
  check('у кода с часами отметки «Пришёл/Ушёл» — в модалке «Изменить»',
    await waitFor(() => !!$('#nc-carries_hours')) && $('#nc-carries_hours').checked
    && $('#nc-punch-wrap').style.display !== 'none');
  click($('#modal [data-cancel]'));
  await sleep(200);
  click($('[data-cedit="ОТ"]'));
  check('у кода без часов выбор заявления — в модалке «Изменить»',
    await waitFor(() => !!$('#nc-carries_hours')) && !$('#nc-carries_hours').checked
    && $('#nc-doc-wrap').style.display !== 'none' && !!$('#nc-doc'));
  click($('#modal [data-cancel]'));
  await sleep(200);
  click($('#cd-add'));
  check('форма нового кода открылась', await waitFor(() => !!$('#nc-code')));
  check('окна по умолчанию в форме кода НЕТ', !$('#nc-window'));
  check('новый код без часов — предлагается заявление', $('#nc-punch-wrap').style.display === 'none'
    && $('#nc-doc-wrap').style.display !== 'none');
  $('#nc-carries_hours').checked = true;
  change($('#nc-carries_hours'));
  check('«несёт часы» переключает на отметки «Пришёл/Ушёл»',
    $('#nc-punch-wrap').style.display !== 'none' && $('#nc-doc-wrap').style.display === 'none');
  click($('#modal [data-cancel]'));
  await sleep(200);
  click($('[data-tab="windows"]'));
  check('окна и значения', await waitFor(() => /Окна и значения/.test(text('#st-body'))));
  check('полоса суток отрисована', !!$('#st-body .timeline .tl-bar'));
  const before = $$('#st-body tbody tr').length;
  click($('#cd-add'));
  check('форма нового значения открылась', await waitFor(() => !!$('#nw-hours')));
  const winCodes = $$('#nw-code option').map(o => o.value);
  check('окно — только коду, несущему часы', winCodes.includes('Я') && !winCodes.includes('В')
    && !winCodes.includes('ОТ'), winCodes.join(','));
  input($('#nw-hours'), '10,5');
  change($('#nw-start'), '08:00');
  change($('#nw-end'), '20:00');
  check('предпросмотр окна', /12 ч/.test(text('#nw-preview')), text('#nw-preview'));
  click($('[data-save]'));
  check('значение добавлено в черновик', await waitFor(() => $$('#st-body tbody tr').length > before));
  check('черновик непуст', !!$('[data-draft-bar]:not(.idle)'));
  click($('[data-draft-diff]'));
  check('diff черновика показан', await waitFor(() => /добавлено «Я 10,5»|Окна и значения/.test(text('#modal'))),
    text('#modal').slice(0, 160));
  click($('#modal [data-ok]'));
  await sleep(200);
  click($('[data-draft-publish]'));
  check('диалог публикации открылся', await waitFor(() => !!$('#pb-from')));
  check('честная дата применения', /Фактически применится/.test(text('#pb-preview')), text('#pb-preview'));
  /* по умолчанию «Действует с» — начало ближайшего периода не раньше сегодня; 1-го числа это
     сегодня, и версия законно вступает сразу. Завтра — следующий период при любом числе. */
  change($('#pb-from'), tomorrow);
  input($('#pb-note'), 'сценарий интерфейса: окно «Я 10,5»');
  click($('#modal [data-save]'));
  check('версия опубликована', await waitFor(() => /опубликована/i.test(text('#toast-host')), 15000),
    text('#toast-host'));
  check('публикация сообщила настоящую дату применения',
    /применится с \d\d\.\d\d\.\d{4}/.test(text('#toast-host')), text('#toast-host'));
  await go('codes');
  click($('[data-tab="windows"]'));
  await waitFor(() => /Окна и значения/.test(text('#st-body')));
  check('сегодня действует прежняя версия: новое значение вступит со следующего периода',
    !text('#st-body').includes('Я 10,5'), 'версия применяется по дате НАЧАЛА периода (D25)');
  await go('overview');
  check('новая версия видна в «Вступит в силу»',
    await waitFor(() => /Вступит в силу/.test(text('#st-body'))
      && text('#st-body').includes('сценарий интерфейса')), text('#st-body').slice(0, 200));

  /* ── 6. Расчёт: черновик, diff, сброс ── */
  console.log('\n6 · Расчёт');
  await go('calc');
  check('лимит опоздания — отдельный блок', /Лимит опоздания/.test(text('#st-body')));
  check('категории: два поля и производные ночные', /Начало дневных часов/.test(text('#st-body'))
    && /ДН \(ночь\)|дополнение суток/.test(text('#st-body')));
  check('веса редактируемые', $$('#st-body [data-weight]').length >= 4);
  check('порядки с кнопками', $$('#st-body [data-order="cascade"] [data-move]').length > 0);
  change($('#cl-step button[data-v="30"]') && $('#cl-late'), 7);
  click($('#cl-step button[data-v="30"]'));
  check('черновик появился после правки', !!$('[data-draft-bar]:not(.idle)'));
  click($('[data-draft-reset]'));
  click($('#modal [data-yes]'));
  check('черновик сброшен', await waitFor(() => !!$('[data-draft-bar].idle')));

  /* ── 7. Календарь правил ── */
  console.log('\n7 · Календарь правил');
  await go('calendar');
  check('сетка месяца', $$('#st-body .cal td.cell:not(.out)').length >= 28);
  check('легенда слоёв', /переопределение правила/.test(text('#st-body')) && /ВИП-период/.test(text('#st-body')));
  click($('#st-body .cal td.cell:not(.out)'));
  check('панель дня открылась', await waitFor(() => /День \d\d\.\d\d\.\d{4}/.test(text('#cl-day'))),
    text('#cl-day').slice(0, 120));
  check('производственный календарь на месте', await waitFor(() => !!$('#dp-body .dp-head, #dp-body .dp-form, #dp-body .empty')));

  /* ── 8. Остальные экраны ── */
  console.log('\n8 · Справочники объекта и служебные экраны');
  await go('shifts');
  check('словарь смен: добавляемые смены и «Отпросился»',
    /Отпросился/.test(text('#st-body')) && $$('#st-body tbody tr').length > 0);
  check('справочники независимы: колонки «Код Табеля» нет',
    !/Код Табеля/.test(text('#st-body thead')) && /Как связаны Табель и График/.test(text('#st-body')));
  await go('docs');
  check('реквизиты и виды заявлений', /Реквизиты организации/.test(text('#st-body')) && /Виды заявлений/.test(text('#st-body')));
  check('прочие правила объекта', /Прочие правила объекта/.test(text('#st-body')));
  /* группа «Объект» (19.10.2026): справочники, переехавшие из операционных разделов */
  await go('night');
  check('«Ночной обход»: зоны слева, словарь справа (master-detail)',
    await waitFor(() => $$('#st-body .dict-zone').length >= 4 && !!$('#dict-host')),
    String($$('#st-body .dict-zone').length));
  check('«Ночной обход»: вкладки Объекты/Чек-листы/Службы', $$('[data-dtab]').length === 3);
  check('«Ночной обход»: баннер про снимок смены', /ещё не начатым объектам/.test(text('#st-body')));
  await go('cars');
  check('«Электрокары»: парк и места стоянки', await waitFor(() =>
    /Места стоянки/.test(text('#st-body')) && $$('#st-body [data-cd-edit]').length > 0));
  check('«Электрокары»: кнопка возврата к операциям', !!$('#cd-to-cars'));
  await go('system');
  check('данные системы и версии', /Данные системы/.test(text('#st-body')) && /Версии справочников/.test(text('#st-body')));
  await go('expert');
  check('режим эксперта: JSON тот же конфигурации', await waitFor(() => !!$('#es-json')));

  /* ── 9. Поиск ⌘K ── */
  console.log('\n9 · Поиск по настройкам');
  await go('overview');
  click($('#st-search'));
  check('палитра открылась', await waitFor(() => !!$('#sp-q')));
  input($('#sp-q'), 'переработк');
  check('нашлось правило оплаты', /Оплачиваются ли переработки/.test(text('#sp-res')), text('#sp-res').slice(0, 120));
  click($('#sp-res [data-i="0"]'));
  check('переход на экран правила', await waitFor(() => window.location.hash === '#/settings/pay'),
    window.location.hash);

  console.log(`\n=== ошибки консоли ===`);
  const uniq = [...new Set(consoleErrors.map(e => e.slice(0, 240)))];
  uniq.length ? uniq.forEach(e => console.log('  ' + e)) : console.log('  нет');
  failed += uniq.length;
  console.log(`\nИТОГ: проверок пройдено ${passed}, провалено ${failed}`);
  process.exit(failed ? 2 : 0);
}

main().catch(e => { console.error('сценарий:', e); process.exit(1); });
