/* Сценарий экрана «Настройки → Фонд» шахматки: jsdom + РЕАЛЬНЫЙ сервер (как stays_scenario).

Путь менеджера по версиям фонда (docs/superpowers/specs/2026-10-26-stays-fund-versions-design.md §4, §10):
  1. экран: дерево, объекты, история версий; гонка переключения версий (loadGenerationFor);
  2. черновик с завтра; деление коннекта 12134 на два объекта категории DLX;
  3. 409 при устаревшем rev — тост и перезагрузка снимка; массовая отметка флага по узлу;
  4. предпросмотр: бронь коннекта без объекта → перевод галочкой в DLX → публикация;
     затем GET /fund/snapshot?date=<завтра> — новые объекты и флаг;
  5. файл фонда: «Выгрузить фонд» → тот же файл «Загрузить фонд» черновиком с сегодня (ноль
     изменений); под admin — предпросмотр начальной загрузки («будет удалено…», слово ЗАМЕНИТЬ)
     без подтверждения: ничего не удалено; переключатель «Шахматка в эксплуатации»;
  6. под rukovod экран недоступен.

Запуск: tools/run_stays_fund_scenario.sh [порт] [логин]   (нужен jsdom: npm i)
Код возврата: 0 — сценарий пройден, 2 — есть проваленные проверки. */
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { fileURLToPath } from 'node:url';
import { JSDOM, VirtualConsole } from 'jsdom';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const BASE = process.argv[2] || 'http://127.0.0.1:8147';
const LOGIN = process.argv[3] || 'admin';

const consoleErrors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => consoleErrors.push('[jsdomError] ' + String(e.stack || e.message).split('\n')[0]));
vc.on('error', (...a) => consoleErrors.push('[console.error] ' + a.map(String).join(' ')));

const html = fs.readFileSync(path.join(ROOT, 'static/index.html'), 'utf8');
const jar = new Map();
const requests = [];                    // [{method, path, status, buf}] — что слал интерфейс
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
        requests.push({ method, path: u.pathname + u.search, status: res.statusCode, buf });
        const hdrs = { get: k => res.headers[k.toLowerCase()] ?? null };
        resolve({ status: res.statusCode, ok: res.statusCode < 400, headers: hdrs,
          text: async () => text, json: async () => JSON.parse(text), blob: async () => new window.Blob([buf]) });
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
/* FormData (загрузка файла фонда) → multipart вручную: http.request не знает FormData jsdom */
async function multipart(fd) {
  const b = '----scenario' + Date.now().toString(16);
  const parts = [];
  for (const [k, v] of fd.entries()) {
    if (typeof v === 'string') {
      parts.push(Buffer.from(`--${b}\r\nContent-Disposition: form-data; name="${k}"\r\n\r\n${v}\r\n`));
    } else {
      parts.push(Buffer.from(`--${b}\r\nContent-Disposition: form-data; name="${k}"; filename="${v.name}"\r\n`
        + `Content-Type: ${v.type || 'application/octet-stream'}\r\n\r\n`), Buffer.from(await v.arrayBuffer()), Buffer.from('\r\n'));
    }
  }
  parts.push(Buffer.from(`--${b}--\r\n`));
  return { body: Buffer.concat(parts), type: `multipart/form-data; boundary=${b}` };
}
window.fetch = async (url, init = {}) => {
  if (init.body instanceof window.FormData) {
    const { body, type } = await multipart(init.body);
    return proxy(init.method || 'GET', url, { body, headers: { ...(init.headers || {}), 'Content-Type': type } });
  }
  return proxy(init.method || 'GET', url, { body: typeof init.body === 'string' ? init.body : undefined, headers: init.headers });
};
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
window.HTMLAnchorElement.prototype.click = function () {};   // скачивание (downloadBlob): навигации в jsdom нет

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

function addDays(iso, n) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}
const ru = iso => `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
const toastHas = s => text('#toast-host').includes(s);

async function fundFlow() {
  const today = serverToday();
  /* «с завтра»: до будущей версии демо (сегодня + 14) — черновик не пересекает её */
  const tomorrow = addDays(today, 1);
  const snap0 = (await apiJson('GET', '/api/stays/fund/snapshot?date=' + today)).body;
  const cnx = snap0.categories.find(c => c.code === 'CNX');
  const dlx = snap0.categories.find(c => c.code === 'DLX');
  const connect = snap0.units.find(u => u.label === '12134');
  const flag = snap0.flags.find(f => f.title === 'Для аллергиков');
  const versions0 = (await apiJson('GET', '/api/stays/fund/versions')).body;
  const future = versions0.find(v => v.status === 'published' && v.valid_from > today);
  if (!cnx || !dlx || !connect || !flag || !future) throw new Error('демо-фонд не тот: ' + JSON.stringify({ cnx, dlx, connect, flag, future }));
  const res = await apiJson('POST', '/api/stays/reservations', { number: 'CX' + uniq, check_in: addDays(today, 2),
    check_out: addDays(today, 4), category_id: cnx.id });
  const rid = res.body.result?.id;
  check('бронь коннекта встала в 12134', res.body.result?.segments?.[0]?.unit_id === connect.id, JSON.stringify(res.body).slice(0, 300));

  console.log('\n1 · Экран фонда');
  window.navigate('settings');
  await waitFor(() => !!$('#st-nav'));
  await go('stays_fund');
  check('дерево фонда отрисовано', await waitFor(() => $$('#st-body [data-fund-node]').length > 5
    && text('#st-body').includes('Винные виллы') && text('#st-body').includes('Корпус')));
  check('объекты справа, #id мелким', text('#st-body').includes('12134') && $('#st-body').innerHTML.includes(`#${connect.id}`));
  check('вкладки «Объекты / Флаги объектов / Категории / Виды»',
    ['units', 'flags', 'cats', 'kinds'].every(t => !!$(`#st-body [data-fund-tab="${t}"]`)));
  check('история версий: исходная, действующая и будущая', $$('#fund-history [data-fund-ver]').length >= 2
    && text('#fund-history').includes('будущая') && text('#fund-history').includes('действует'), text('#fund-history'));

  /* гонка: запросили будущую версию (ответ медленный), сразу вернулись к действующей —
     запоздавший ответ не должен перерисовать экран будущей версией */
  const realApi = window.api;
  window.api = async (url, opts) => {
    if (url.includes('version_id=' + future.id)) await sleep(1500);
    return realApi(url, opts);
  };
  window.eval('api = window.api');
  change($('#fund-view'), 'v:' + future.id);
  await sleep(150);
  change($('#fund-view'), 'current');
  await sleep(2000);
  window.api = realApi;
  window.eval('api = window.api');
  check('гонка версий: на экране действующая', $('#fund-view')?.value === 'current'
    && !!$(`#st-body [data-fund-unit="${connect.id}"]`), $('#fund-view')?.value);

  console.log('\n2 · Черновик с завтра и деление коннекта');
  click($('#fund-new-draft'));
  check('форма даты черновика', await waitFor(() => !!$('#fd-date')));
  input($('#fd-date'), tomorrow);
  click($('[data-save]'));
  check('плашка черновика с датой', await waitFor(() => text('#fund-draft-bar').includes(tomorrow.split('-').reverse().join('.'))),
    text('#fund-draft-bar'));
  check('режим «черновик» в переключателе', $('#fund-view')?.value === 'draft');
  click($(`[data-fund-split="${connect.id}"]`));
  check('форма деления', await waitFor(() => !!$('[data-sp-label="1"]')));
  input($('[data-sp-label="0"]'), '12134A'); input($('[data-sp-label="1"]'), '12134B');
  change($('[data-sp-cat="0"]'), String(dlx.id)); change($('[data-sp-cat="1"]'), String(dlx.id));
  click($('[data-save]'));
  check('новые объекты с пометкой «новый · из 12134»', await waitFor(() => text('#st-body').includes('12134A')
    && text('#st-body').includes('12134B') && [...text('#st-body').matchAll(/новый · из 12134/g)].length === 2), text('#st-body').slice(0, 400));
  check(`исходный объект — «выведен с ${ru(tomorrow)}»`,
    (($(`#st-body [data-fund-unit="${connect.id}"]`)?.textContent) || '').includes('выведен с ' + ru(tomorrow)));
  check('плашка: число изменений и список', /изменений: [1-9]/.test(text('#fund-draft-bar')) && text('#fund-draft-bar').includes('12134A'),
    text('#fund-draft-bar'));

  console.log('\n3 · 409 и флаг по узлу');
  click($(`[data-fund-node="${connect.group_id}"]`));
  await waitFor(() => $(`[data-fund-node="${connect.group_id}"]`)?.classList.contains('active'));
  click($('[data-fund-tab="flags"]'));
  check('матрица флагов', await waitFor(() => !!$(`[data-fund-flag-all="${flag.id}"]`)));
  /* экран уже загрузил rev — коллега меняет черновик после этого */
  const drafts = (await apiJson('GET', '/api/stays/fund/versions')).body.find(v => v.status === 'draft');
  const ds = (await apiJson('GET', '/api/stays/fund/snapshot?version_id=' + drafts.id)).body;
  const bump = await apiJson('PATCH', '/api/stays/fund/draft', { rev: ds.version.rev, valid_from: tomorrow });
  check('коллега изменил черновик (rev вырос)', bump.status === 200, JSON.stringify(bump.body));
  const all = $(`[data-fund-flag-all="${flag.id}"]`);
  all.checked = true; change(all);
  check('409: тост «Черновик изменил другой пользователь»', await waitFor(() => toastHas('Черновик изменил другой пользователь')),
    text('#toast-host'));
  await sleep(800);
  check('после 409 снимок перезагружен (вкладка и узел на месте)',
    await waitFor(() => !!$(`[data-fund-flag-all="${flag.id}"]`) && $(`[data-fund-flag-all="${flag.id}"]`).checked === false));
  const all2 = $(`[data-fund-flag-all="${flag.id}"]`);
  all2.checked = true; change(all2);
  check('флаг отмечен у всех объектов узла', await waitFor(() => {
    const boxes = $$(`[data-fund-flag="${flag.id}"]`);
    return boxes.length > 1 && boxes.every(b => b.checked);
  }));

  console.log('\n3a · Дерево: перетаскивание узлов');
  const grp = title => snap0.groups.find(g => g.title === title);
  const villas = grp('Винные виллы'), water = grp('У воды'), view = grp('С видом');
  const second = grp('Вторая линия'), first = grp('Первая линия');
  const drag = async (from, to) => {
    const src = $(`#st-body [data-fund-node="${from}"]`);
    src.dispatchEvent(new window.Event('dragstart', { bubbles: true }));
    const dst = typeof to === 'string' ? $(to) : $(`#st-body [data-fund-node="${to}"]`);
    dst.dispatchEvent(new window.Event('dragover', { bubbles: true, cancelable: true }));
    dst.dispatchEvent(new window.Event('drop', { bubbles: true, cancelable: true }));
  };
  const poll = async fn => {             // как waitFor, но условие — запрос к API
    for (let i = 0; i < 40; i++) { if (await fn()) return true; await sleep(250); }
    return false;
  };
  const draftGroups = async () => {
    const v = (await apiJson('GET', '/api/stays/fund/versions')).body.find(x => x.status === 'draft');
    return (await apiJson('GET', '/api/stays/fund/snapshot?version_id=' + v.id)).body.groups;
  };
  check('узлы перетаскиваются в черновике', $(`#st-body [data-fund-node="${second.id}"]`)?.getAttribute('draggable') === 'true');
  await drag(second.id, water.id);
  check('перенос на узел: «Вторая линия» — подузел «У воды»',
    await poll(async () => (await draftGroups()).find(g => g.id === second.id)?.parent_id === water.id));
  await waitFor(() => !!$(`#st-body [data-fund-gap="${villas.id}"][data-fund-before="${water.id}"]`));
  await drag(view.id, `#st-body [data-fund-gap="${villas.id}"][data-fund-before="${water.id}"]`);
  check('перенос между соседями: «С видом» перед «У воды»', await poll(async () => {
    const gs = (await draftGroups()).filter(g => g.parent_id === villas.id);
    return gs.findIndex(g => g.id === view.id) < gs.findIndex(g => g.id === water.id);
  }));
  await waitFor(() => !!$(`#st-body [data-fund-node="${first.id}"]`));
  await sleep(500);
  await drag(villas.id, first.id);
  check('цикл отклонён сервером — тост', await waitFor(() => toastHas('нельзя вложить')), text('#toast-host'));
  check('цикл: дерево не изменилось', (await draftGroups()).find(g => g.id === villas.id)?.parent_id == null);

  console.log('\n4 · Предпросмотр, перевод брони, публикация');
  click($('#fund-publish'));
  check('предпросмотр: бронь коннекта без объекта', await waitFor(() => !!$(`[data-fp-transfer="${rid}"]`)
    && text('#fp-out').includes('без объекта') && text('#fp-out').includes('CX' + uniq)), text('#fp-out'));
  check('предпросмотр: «Применить к поздним версиям»', $('#fp-propagate')?.checked === true);
  const tr = $(`[data-fp-transfer="${rid}"]`);
  tr.checked = true; change(tr);
  change($(`[data-fp-transfer-cat="${rid}"]`), String(dlx.id));
  click($('#fp-publish'));
  check('опубликовано', await waitFor(() => toastHas('Фонд опубликован')), text('#toast-host'));
  check('плашки черновика больше нет', await waitFor(() => !$('#fund-draft-bar') && !!$('#fund-history')));

  const after = (await apiJson('GET', '/api/stays/fund/snapshot?date=' + tomorrow)).body;
  const parts = after.units.filter(u => u.label === '12134A' || u.label === '12134B');
  check('снимок на завтра: два новых объекта DLX', parts.length === 2 && parts.every(u => u.category_id === dlx.id),
    JSON.stringify(parts));
  check('снимок на завтра: 12134 выведен', !after.units.some(u => u.label === '12134'));
  check('снимок на завтра: флаг у новых объектов', parts.length === 2 && parts.every(u => u.flags.includes(flag.id)));
  check('снимок на завтра: флаг у всего узла', after.units.filter(u => u.group_id === connect.group_id).every(u => u.flags.includes(flag.id)));
  const r = (await apiJson('GET', '/api/stays/reservations/' + rid)).body;
  check('бронь коннекта переведена в DLX', r.category_id === dlx.id, JSON.stringify({ category_id: r.category_id }));
  const later = (await apiJson('GET', '/api/stays/fund/snapshot?version_id=' + future.id)).body;
  check('поздняя версия получила новые объекты', ['12134A', '12134B'].every(l => later.units.some(u => u.label === l)));
  check('черновика больше нет', !(await apiJson('GET', '/api/stays/fund/versions')).body.some(v => v.status === 'draft'));
  check('нет мусора в DOM', !/undefined|NaN|\[object Object\]/.test($('#st-body').innerHTML));
}

const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
/* выбрать файл в <input type=file>: jsdom не даёт задать files — подменяем свойство */
function pickFile(el, buf, name) {
  const f = new window.File([buf], name, { type: XLSX });
  Object.defineProperty(el, 'files', { value: [f], configurable: true });
  change(el);
}

async function fundFileFlow() {
  console.log('\n5 · Файл фонда: выгрузка, загрузка черновиком, предпросмотр начальной загрузки');
  const today = serverToday();
  window.navigate('settings');
  await waitFor(() => !!$('#st-nav'));
  await go('stays_fund');
  await waitFor(() => !!$('#fund-export'));
  check('кнопки «Выгрузить фонд» и «Загрузить фонд»', !!$('#fund-export') && !!$('#fund-upload'));
  check('переключатель «Шахматка в эксплуатации» виден администратору (выключен)',
    !!$('#fund-in-prod') && $('#fund-in-prod').checked === false);
  const n0 = requests.length;
  click($('#fund-export'));
  await waitFor(() => requests.slice(n0).some(r => r.path.startsWith('/api/stays/fund/export')));
  const exp = requests.slice(n0).find(r => r.path.startsWith('/api/stays/fund/export'));
  check('выгрузка: файл фонда на сегодня', exp?.status === 200 && exp.path.includes('date=' + today)
    && exp.buf.subarray(0, 2).toString() === 'PK', exp && `${exp.status} ${exp.path}`);
  if (!exp || exp.status !== 200) return;

  click($('#fund-upload'));
  check('окно «Загрузить фонд»: режимы черновик и начальная загрузка', await waitFor(() => !!$('#fu-mode'))
    && [...$('#fu-mode').options].map(o => o.value).join() === 'draft,reset');
  input($('#fu-date'), today); change($('#fu-date'));
  pickFile($('#fu-file'), exp.buf, `fund-${today}.xlsx`);
  click($('#fu-go'));
  check('черновик из файла без правок: изменений 0', await waitFor(() => toastHas('изменений: 0')), text('#toast-host'));
  check('экран показывает черновик, плашка «изменений: 0»',
    await waitFor(() => $('#fund-view')?.value === 'draft' && text('#fund-draft-bar').includes('изменений: 0')), text('#fund-draft-bar'));
  const draft = (await apiJson('GET', '/api/stays/fund/versions')).body.find(v => v.status === 'draft');
  check('черновик с сегодня', draft?.valid_from === today, JSON.stringify(draft));
  if (draft) await apiJson('DELETE', '/api/stays/fund/versions/' + draft.id);
  window.navigate('settings');
  await waitFor(() => !!$('#st-nav'));
  await go('stays_fund');
  await waitFor(() => !!$('#fund-upload') && !$('#fund-draft-bar'));

  const resBefore = (await apiJson('GET', `/api/stays/board/units?first=${today}&last=${addDays(today, 30)}`)).body.bars.length;
  const verBefore = (await apiJson('GET', '/api/stays/fund/versions')).body.length;
  click($('#fund-upload'));
  await waitFor(() => !!$('#fu-mode'));
  change($('#fu-mode'), 'reset');
  check('режим «заменить всё»: предупреждение, кнопка «Проверить»', !$('#fu-reset').hidden && text('#fu-go') === 'Проверить');
  pickFile($('#fu-file'), exp.buf, 'real.xlsx');
  click($('#fu-go'));
  check('предпросмотр: «Будет удалено» и «Будет загружено»', await waitFor(() => text('#fu-out').includes('Будет удалено')
    && text('#fu-out').includes('Будет загружено') && /\d+ броней/.test(text('#fu-out'))), text('#fu-out'));
  check('предпросмотр: ID в файле будут проигнорированы', text('#fu-out').includes('ID в файле будут проигнорированы'));
  check('без слова ЗАМЕНИТЬ кнопка «Заменить всё» недоступна', text('#fu-go') === 'Заменить всё' && $('#fu-go').disabled === true);
  input($('#fu-word'), 'заменить');
  check('слово в другом регистре — кнопка недоступна', $('#fu-go').disabled === true);
  click($('[data-close]'));
  const resAfter = (await apiJson('GET', `/api/stays/board/units?first=${today}&last=${addDays(today, 30)}`)).body.bars.length;
  check('без подтверждения ничего не удалено', resAfter === resBefore && resBefore > 0
    && (await apiJson('GET', '/api/stays/fund/versions')).body.length === verBefore, `${resBefore} → ${resAfter}`);

  /* «в эксплуатации» убирает начальную загрузку; снять — снова доступна */
  const prod = $('#fund-in-prod');
  prod.checked = true; change(prod);
  await waitFor(() => !!$('[data-yes]'));
  click($('[data-yes]'));
  check('в эксплуатации: отметка сохранена', await waitFor(() => $('#fund-in-prod')?.checked === true));
  click($('#fund-upload'));
  await waitFor(() => !!$('#fu-mode'));
  check('в эксплуатации: режима «заменить всё» нет', [...$('#fu-mode').options].map(o => o.value).join() === 'draft');
  click($('[data-close]'));
  const prod2 = $('#fund-in-prod');
  prod2.checked = false; change(prod2);
  await waitFor(() => !!$('[data-yes]'));
  click($('[data-yes]'));
  check('отметка снята', await waitFor(() => $('#fund-in-prod')?.checked === false));
  check('нет мусора в DOM', !/undefined|NaN|\[object Object\]/.test($('#st-body').innerHTML));
}

async function kindsFlow() {
  console.log('\n6 · Справочник видов категорий');
  const kindsOf = async () => (await apiJson('GET', '/api/stays/fund/snapshot?date=' + serverToday())).body.kinds;
  await go('stays_fund');
  await waitFor(() => !!$('[data-fund-tab="kinds"]'));
  click($('[data-fund-tab="kinds"]'));
  check('вкладка «Виды»: четыре вида демо', await waitFor(() => ['вилла', 'имение', 'апартаменты', 'номер']
    .every(t => text('#st-body').includes(t))), text('#fund-tab-body'));
  click($('#fund-kind-add'));
  check('форма вида', await waitFor(() => !!$('#fk-title')));
  const title = 'Шале ' + uniq;
  input($('#fk-title'), title);
  $('#fk-expanded').checked = true;
  click($('[data-save]'));
  check('вид сохранён и в таблице', await waitFor(() => text('#fund-tab-body').includes(title)));
  const kind = (await kindsOf()).find(k => k.title === title);
  check('вид в снимке: «раскрывать» = да', kind?.expanded === true, JSON.stringify(kind));
  click($(`[data-fund-kind-arch="${kind.id}"]`));
  check('вид в архиве — пометка', await waitFor(() => ($(`[data-fund-kind="${kind.id}"]`)?.textContent || '').includes('архив')));

  /* форма категории в черновике: выбор вида из справочника, архивного вида нет */
  const today = serverToday();
  const opened = await apiJson('POST', '/api/stays/fund/draft', { valid_from: addDays(today, 1) });
  check('черновик открыт', opened.status === 200, JSON.stringify(opened.body));
  window.eval("fundUI.view = 'draft'");
  await go('stays_fund');
  await waitFor(() => !!$('[data-fund-tab="cats"]'));
  click($('[data-fund-tab="cats"]'));
  await waitFor(() => !!$('#fund-cat-add'));
  click($('#fund-cat-add'));
  check('форма категории: выбор вида', await waitFor(() => !!$('#fc-kind')));
  const opts = [...$('#fc-kind').options].map(o => o.textContent);
  check('в выборе — виды справочника, без архивного', opts.includes('вилла') && opts.includes('номер') && !opts.some(o => o.includes(title)),
    opts.join(', '));
  click($('[data-close]'));
  const draft = (await apiJson('GET', '/api/stays/fund/versions')).body.find(v => v.status === 'draft');
  if (draft) await apiJson('DELETE', '/api/stays/fund/versions/' + draft.id);

  await go('stays_fund');
  await waitFor(() => !!$('[data-fund-tab="kinds"]'));
  click($('[data-fund-tab="kinds"]'));
  await waitFor(() => !!$(`[data-fund-kind-del="${kind.id}"]`));
  click($(`[data-fund-kind-del="${kind.id}"]`));
  await waitFor(() => !!$('[data-yes]'));
  click($('[data-yes]'));
  check('неиспользуемый вид удалён', await waitFor(() => !text('#fund-tab-body').includes(title)));
  const villa = (await kindsOf()).find(k => k.title === 'вилла');
  const busy = await apiJson('DELETE', '/api/stays/fund/kinds/' + villa.id);
  check('использованный вид — 409', busy.status === 409, JSON.stringify(busy.body));
  check('нет мусора в DOM', !/undefined|NaN|\[object Object\]/.test($('#st-body').innerHTML));
}

async function noAccess() {
  console.log(`\nДоступ под логином ${LOGIN}`);
  const me = (await apiJson('GET', '/api/auth/me')).body;
  check('экрана «Фонд и категории» нет в Настройках', !(me.settings_screens || []).some(s => s.id === 'stays_fund'));
  if (me.menu.some(m => m.id === 'settings')) {        // Настройки видны — пункта фонда в них нет
    window.navigate('settings');
    await waitFor(() => !!$('#st-nav'));
    check('пункта фонда нет в навигации', !$('#st-nav [data-st="stays_fund"]'));
  }
  const r = await apiJson('POST', '/api/stays/fund/draft', { valid_from: addDays(serverToday(), 1) });
  check('черновик фонда открыть нельзя (403)', r.status === 403, String(r.status));
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
  if (LOGIN === 'admin') { await fundFlow(); await fundFileFlow(); await kindsFlow(); }
  else await noAccess();

  console.log(`\n=== ошибки консоли ===`);
  const errs = [...new Set(consoleErrors.map(e => e.slice(0, 240)))];
  errs.length ? errs.forEach(e => console.log('  ' + e)) : console.log('  нет');
  failed += errs.length;
  console.log(`\nИТОГ: проверок пройдено ${passed}, провалено ${failed}`);
  process.exit(failed ? 2 : 0);
}

main().catch(e => { console.error('сценарий:', e); process.exit(1); });
