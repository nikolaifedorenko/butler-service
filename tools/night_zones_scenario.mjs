/* Сценарий ночного обхода v2: зоны → объекты → чек-лист + справочники.

Зачем: смоук (tools/ui_harness.mjs) проверяет, что разделы ОТРИСОВАНЫ, но не ходит
по уровням обхода и не открывает справочник. Ночной отчёт v2 (19.10.2026) — это
трёхуровневая навигация и чек-лист, заданный НА ЗОНУ: сценарий проходит путь батлера
и проверяет, что справочники реально влияют на обход.

  1. экран зон: карточки зон с прогрессом, шаг «Проверка электрокаров» — отдельно;
  2. объекты зоны: список, фильтры, поиск, «взять в работу» → чек-лист объекта;
  3. чек-лист = шаблон зоны; индивидуальные особенности объекта видны (своя
     формулировка, свой пункт, отключённый пункт);
  4. отметка «Не ОК» с комментарием меняет прогресс объекта и зоны;
  5. завершение объекта и возврат по хлебным крошкам;
  6. справочник «Зоны»: добавление зоны;
  7. справочник «Объекты»: серия однотипных объектов в зону;
  8. справочник «Чек-листы»: пункт шаблона зоны попадает во ВСЕ объекты зоны,
     индивидуальная правка — только в один объект;
  9. выгрузка DOCX содержит зоны и пункты.

Запуск: tools/run_night_zones_scenario.sh [порт] [логин]   (нужен jsdom: npm i)
Код возврата: 0 — сценарий пройден, 2 — есть проваленные проверки. */
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { fileURLToPath } from 'node:url';
import { JSDOM, VirtualConsole } from 'jsdom';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const BASE = process.argv[2] || 'http://127.0.0.1:8144';
const LOGIN = process.argv[3] || 'gromova';
const ZONE = 'Семейные виллы';

const consoleErrors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => consoleErrors.push('[jsdomError] ' + String(e.stack || e.message).split('\n')[0]));
vc.on('error', (...a) => consoleErrors.push('[console.error] ' + a.map(String).join(' ')));

const html = fs.readFileSync(path.join(ROOT, 'static/index.html'), 'utf8');
const jar = new Map();
const netLog = [];
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
        const buf = Buffer.concat(chunks);
        const text = buf.toString('utf8');
        netLog.push(`${method} ${u.pathname} → ${res.statusCode}`);
        resolve({ status: res.statusCode, ok: res.statusCode < 400, raw: buf,
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

const $ = (s, root) => (root || window.document).querySelector(s);
const $$ = (s, root) => [...(root || window.document).querySelectorAll(s)];
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
/* Ждём перерисовки: старый узел должен быть заменён новым. Просто «появился селектор»
   недостаточно — после change() модалка перерисовывается асинхронно, и waitFor
   срабатывает на ПРЕЖНЕЙ разметке, а клик уходит в устаревший обработчик
   (так правка объекта однажды уехала не тому объекту). */
async function rerendered(oldEl, sel, predicate) {
  return waitFor(() => {
    const el = $(sel);
    return !!el && el !== oldEl && (!predicate || predicate(el));
  });
}
async function waitFor(fn, ms = 15000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (fn()) return true; await sleep(150); }
  return false;
}
/* переход в раздел: navigate() перерисовывает асинхронно, поэтому ждём две фазы —
   снятие старой разметки и появление свежей (иначе клик уходит в отсоединённый узел) */
async function gotoNight() {
  window.navigate('night');
  await waitFor(() => !$('#night-body') || text('#night-body').includes('Загрузка'));
  return waitFor(() => !!$('#night-body') && !text('#night-body').includes('Загрузка'), 20000);
}
const api = async (method, url, body) => proxy(method, url, body
  ? { body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } } : {});

async function main() {
  await sleep(400);
  const login = await api('POST', '/api/auth/login', { username: LOGIN, password: 'demo1234' });
  if (login.ok) window.eval('bootApp()');
  await waitFor(() => !$('#app').classList.contains('hidden'), 30000);
  check('вход выполнен', !$('#app').classList.contains('hidden'), text('#login-error'));
  await sleep(500);

  const today = await (await api('GET', '/api/night/today')).json();
  check('ночная смена открыта', !!today.available && today.report.readonly === false,
    today.note || (today.report ? 'смена закрыта' : 'нет отчёта'));
  if (!today.available) return finish();
  const reportId = today.report.id;

  /* ── 1. Экран зон ── */
  console.log('\n1 · Зоны обхода');
  check('раздел открылся', await gotoNight());
  check('карточки зон отрисованы', $$('.night-zone').length >= 4, String($$('.night-zone').length));
  check('зона «Семейные виллы» с 12 объектами',
    /Семейные виллы/.test(text('#night-body')) && /12 объектов/.test(text('#night-body')));
  check('прогресс-бар зоны', !!$('.zone-bar'));
  check('шаг «Проверка электрокаров» — отдельно от зон', !!$('#night-cars-open')
    && !$$('.night-zone').some(z => /электрокар/i.test(z.textContent)));
  check('статистика смены', /Замечаний/.test(text('#night-body')) && /Объектов/.test(text('#night-body')));
  const zoneCard = $$('.night-zone').find(z => z.textContent.includes(ZONE));
  check('кнопка перехода в зону', !!$('[data-zone-open]', zoneCard));

  /* ── 2. Объекты зоны ── */
  console.log('\n2 · Объекты зоны');
  click($('[data-zone-open]', zoneCard));
  check('список объектов открылся', await waitFor(() => $$('.night-object').length === 12),
    String($$('.night-object').length));
  check('хлебные крошки', /Ночной отчёт/.test(text('.crumb')) && text('.crumb').includes(ZONE));
  check('Вилла 4001 … 4012', text('#night-body').includes('Вилла 4001')
    && text('#night-body').includes('Вилла 4012'));
  click($('[data-ofilter="done"]'));
  check('фильтр «Закрыты»', $$('.night-object').length === 0, String($$('.night-object').length));
  click($('[data-ofilter="all"]'));
  input($('#night-obj-q'), '4007');
  check('поиск по объектам', $$('.night-object').length === 1 && text('.night-object').includes('4007'),
    String($$('.night-object').length));
  input($('#night-obj-q'), '');
  check('сброс поиска', $$('.night-object').length === 12, String($$('.night-object').length));

  /* ── 3. Чек-лист объекта: шаблон зоны + индивидуальные особенности ── */
  console.log('\n3 · Чек-лист объекта');
  const row4003 = $$('.night-object').find(o => o.textContent.includes('Вилла 4003'));
  click($('[data-sec-open]', row4003));
  check('чек-лист открылся', await waitFor(() => $$('.night-item').length === 4),
    String($$('.night-item').length));
  check('пункты шаблона зоны', ['Витражи закрыты', 'Свет выключен', 'Вилла убрана',
    'Вилла укомплектована'].every(t => text('#night-body').includes(t)));
  check('объект взят в работу', /ведёте вы/.test(text('#night-body')), text('.night-area-head'));
  check('хлебные крошки до объекта', text('.crumb').includes('Вилла 4003'));

  click($('[data-crumb="zone"]'));
  await waitFor(() => $$('.night-object').length === 12);
  const row4001 = $$('.night-object').find(o => o.textContent.includes('Вилла 4001'));
  click($('[data-sec-open]', row4001));
  check('индивидуальный чек-лист объекта открылся', await waitFor(() => $$('.night-item').length === 5),
    String($$('.night-item').length));
  check('своя формулировка пункта', /Вилла убрана \(включая детскую комнату\)/.test(text('#night-body')));
  check('свой пункт объекта', /Детская кроватка установлена и исправна/.test(text('#night-body')));
  click($('[data-crumb="zone"]'));
  await waitFor(() => $$('.night-object').length === 12);
  const row4002 = $$('.night-object').find(o => o.textContent.includes('Вилла 4002'));
  click($('[data-sec-open]', row4002));
  check('отключённый у объекта пункт не показан', await waitFor(() => $$('.night-item').length === 3)
    && !/Вилла укомплектована/.test(text('#night-body')), String($$('.night-item').length));

  /* ── 4. Отметки и прогресс ── */
  console.log('\n4 · Отметка «Не ОК» и прогресс зоны');
  click($('[data-crumb="zone"]'));
  await waitFor(() => $$('.night-object').length === 12);
  click($('[data-sec-open]', $$('.night-object').find(o => o.textContent.includes('Вилла 4003'))));
  await waitFor(() => $$('.night-item').length === 4);
  const item = $$('.night-item')[0];
  click($('[data-ans="bad"]', item));
  check('пункт отмечен «Не ОК»', await waitFor(() => $$('.night-item.bad').length === 1));
  click($('[data-cmt]', $$('.night-item')[0]));
  check('окно комментария открылось', await waitFor(() => !!$('#ni-comment')));
  input($('#ni-comment'), 'сценарий: витраж открыт');
  click($('[data-ok]'));
  check('комментарий сохранён', await waitFor(() => /сценарий: витраж открыт/.test(text('#night-body'))));
  click($('[data-ans="ok"]', $$('.night-item')[1]));
  check('второй пункт отмечен «ОК»', await waitFor(() => $$('.night-item.ok').length === 1));

  click($('[data-crumb="zones"]'));
  await waitFor(() => $$('.night-zone').length >= 4);
  const zc = $$('.night-zone').find(z => z.textContent.includes(ZONE));
  check('замечание видно в зоне', /Не ОК: 1/.test(zc.textContent), zc.textContent.replace(/\s+/g, ' ').slice(0, 140));
  check('зона в работе', /в работе [1-9]/.test(zc.textContent),
    zc.textContent.replace(/\s+/g, ' ').slice(0, 140));

  /* ── 5. Завершение объекта ── */
  console.log('\n5 · Завершение объекта');
  click($('[data-zone-open]', zc));
  await waitFor(() => $$('.night-object').length === 12);
  const row3 = $$('.night-object').find(o => o.textContent.includes('Вилла 4003'));
  click($('[data-sec-close]', row3));
  check('закрытие с неотмеченными пунктами спрашивает', await waitFor(() => !!$('[data-yes]')),
    text('.modal-body').slice(0, 80));
  click($('[data-yes]'));
  check('объект закрыт', await waitFor(() => {
    const r = $$('.night-object').find(o => o.textContent.includes('Вилла 4003'));
    return !!r && /закрыт/.test(r.textContent);
  }));
  check('в зоне стало «закрыто 1»', /закрыто 1/.test(text('.crumb')) || /закрыто 1/.test(text('#night-body')));

  /* ── 6. Справочник: зоны ── */
  console.log('\n6 · Справочник — зоны');
  click($('#night-dict'));
  check('справочник открылся', await waitFor(() => !!$('[data-dtab="zones"]')));
  check('вкладки справочника', $$('[data-dtab]').length === 3);
  check('зоны в списке', $$('#dict-host .rule-row').length >= 4, String($$('#dict-host .rule-row').length));
  input($('#nz-name'), 'Сценарная зона');
  click($('#nz-add'));
  check('зона добавлена', await waitFor(() => /Сценарная зона/.test(text('#dict-host'))));

  /* ── 7. Справочник: серия объектов ── */
  console.log('\n7 · Справочник — объекты (серия)');
  click($('[data-dtab="areas"]'));
  check('вкладка «Объекты» открылась', await waitFor(() => !!$('#da-zone')));
  const zoneId = (await (await api('GET', '/api/night/zones')).json()).zones
    .find(z => z.name === ZONE).id;
  change($('#da-zone'), String(zoneId));
  check('фильтр по зоне', await waitFor(() => $$('#dict-host .rule-row').length === 12),
    String($$('#dict-host .rule-row').length));
  input($('#db-prefix'), 'Сценарная вилла ');
  input($('#db-start'), '9301');
  input($('#db-count'), '3');
  change($('#db-zone'), String(zoneId));
  click($('#db-add'));
  check('серия объектов создана', await waitFor(() => /Сценарная вилла 9303/.test(text('#dict-host'))));
  check('чек-лист зоны применился к новым объектам',
    /чек-лист объекта: 4/.test($$('#dict-host .rule-row').find(r => r.textContent.includes('9301'))?.textContent || ''),
    ($$('#dict-host .rule-row').find(r => r.textContent.includes('9301'))?.textContent || '').replace(/\s+/g, ' '));

  /* ── 8. Справочник: чек-лист зоны и индивидуальные правки ── */
  console.log('\n8 · Справочник — чек-листы');
  click($('[data-dtab="items"]'));
  check('вкладка «Чек-листы» открылась', await waitFor(() => !!$('#di-zone')));
  const zoneSel = $('#di-zone');
  change(zoneSel, String(zoneId));
  check('шаблон зоны показан', await rerendered(zoneSel, '#di-zone',
    el => el.value === String(zoneId)) && /Витражи закрыты/.test(text('#dict-host')));
  input($('#di-text'), 'Сценарный пункт зоны');
  click($('#di-add'));
  check('пункт добавлен в шаблон зоны', await waitFor(() => /Сценарный пункт зоны/.test(text('#dict-host'))));

  const rep2 = await (await api('GET', `/api/night/reports/${reportId}`)).json();
  const withItem = rep2.report.areas.filter(a => a.zone_name === ZONE
    && a.items.some(i => i.text === 'Сценарный пункт зоны'));
  const freeAreas = rep2.report.areas.filter(a => a.zone_name === ZONE && a.status === 'free');
  check('пункт в чек-листах ещё не начатых объектов', withItem.length === freeAreas.length
    && freeAreas.length > 0, `${withItem.length} из ${freeAreas.length}`);
  check('в начатом объекте чек-лист не перекроен',
    !rep2.report.areas.some(a => a.zone_name === ZONE && a.status !== 'free'
      && a.items.some(i => i.text === 'Сценарный пункт зоны'))
    || rep2.report.areas.filter(a => a.zone_name === ZONE && a.status !== 'free').length === 0);

  /* индивидуальная правка: своя формулировка у одного объекта */
  const areaId = (await (await api('GET', '/api/night/areas')).json()).areas
    .find(a => a.name === 'Вилла 4005').id;
  const areaSel = $('#di-area');
  change(areaSel, String(areaId));
  check('выбор объекта для правок', await rerendered(areaSel, '#di-area',
    el => el.value === String(areaId)) && $$('#dict-host [data-ov]').length >= 4,
    String($$('#dict-host [data-ov]').length));
  const ovBtn = $$('#dict-host [data-ov]')[0];
  click(ovBtn);
  check('окно индивидуальной правки', await waitFor(() => !!$('#ov-text')));
  input($('#ov-text'), 'Сценарная формулировка для 4005');
  click($('#modal .modal-foot [data-ok]'));
  await sleep(500);
  check('правка сохранена и видна в справочнике',
    await waitFor(() => /Сценарная формулировка для 4005/.test(text('#dict-host'))));
  check('правка применилась к незакрытой смене',
    (await (await api('GET', `/api/night/reports/${reportId}`)).json()).report.areas
      .some(a => a.name === 'Вилла 4005' && a.items.some(i => i.text === 'Сценарная формулировка для 4005')));
  const cl = await (await api('GET', `/api/night/areas/${areaId}/checklist`)).json();
  check('эффективный чек-лист учитывает правку',
    cl.effective.some(i => i.text === 'Сценарная формулировка для 4005'));
  check('у других объектов зоны текст прежний',
    !(await (await api('GET', '/api/night/areas/'
      + (await (await api('GET', '/api/night/areas')).json()).areas.find(a => a.name === 'Вилла 4006').id
      + '/checklist')).json()).effective.some(i => i.text === 'Сценарная формулировка для 4005'));
  click($('#modal-backdrop'));

  /* ── 9. Выгрузка DOCX ── */
  console.log('\n9 · Выгрузка DOCX');
  const docx = await api('GET', `/api/night/reports/${reportId}/export.docx`);
  check('DOCX отдаётся', docx.status === 200 && docx.raw.length > 5000,
    `${docx.status}, ${docx.raw.length} байт`);
  /* содержимое .docx — архив: текст проверяют тесты Python (tests/test_night_zones.py),
     здесь достаточно валидного OOXML-пакета */
  check('DOCX — валидный OOXML-пакет', docx.raw.subarray(0, 2).toString() === 'PK');

  return finish();
}

function finish() {
  console.log('\n=== уникальные ошибки консоли ===');
  const uniq = [...new Set(consoleErrors.map(e => e.slice(0, 240)))];
  uniq.length ? uniq.forEach(e => console.log('  ' + e)) : console.log('  нет');
  if (uniq.length) failed++;
  console.log(`\nИТОГ: проверок ${passed + failed}, пройдено ${passed}, провалено ${failed}`);
  console.log('сетевых запросов:', netLog.length);
  process.exit(failed ? 2 : 0);
}

main().catch(e => { console.error('сценарий упал:', e); process.exit(2); });
