/* Смоук интерфейса: гоняет static/index.html + ВСЕ подключённые скрипты в jsdom
   против РЕАЛЬНОГО сервера uvicorn (без браузера — быстрее и стабильнее в CI).
   Использование: node harness.mjs <base-url> <login> [раздел1,раздел2,...]
   Печатывает: состояние разделов (пусто/не пусто, число узлов, кнопки), ошибки консоли.
   Запуск: tools/run_ui_check.sh [порт] [логин] [разделы]  (нужен jsdom: npm i jsdom)
   Код возврата: 0 — все разделы отрисованы и консоль чистая; 2 — есть пустые/ошибки. */
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { fileURLToPath } from 'node:url';
import { JSDOM, VirtualConsole } from 'jsdom';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const BASE = process.argv[2] || 'http://127.0.0.1:8141';
const LOGIN = process.argv[3] || 'gromova';
const VIEWS = (process.argv[4] || 'schedule,onwork,attendance,timesheet,employees,me,night,cars,settings').split(',');

const consoleErrors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => consoleErrors.push('[jsdomError] ' + String(e.stack || e.message).split('\n')[0]));
vc.on('error', (...a) => consoleErrors.push('[console.error] ' + a.map(String).join(' ')));

const html = fs.readFileSync(path.join(ROOT, 'static/index.html'), 'utf8');

/* fetch-прокси на реальный сервер (cookie-jar внутри) */
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
        const text = Buffer.concat(chunks).toString('utf8');
        netLog.push(`${method} ${u.pathname} → ${res.statusCode}`);
        resolve({
          status: res.statusCode, ok: res.statusCode < 400, headers: res.headers,
          text: async () => text, json: async () => JSON.parse(text),
        });
      });
    });
    req.on('error', e => { console.error('PROXY ERROR', method, u.pathname, e.code || e.message); reject(e); });
    if (body) req.write(body);
    req.end();
  });
}

const dom = new JSDOM(html, {
  url: BASE + '/', runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc,
});
const { window } = dom;
window.fetch = (url, init = {}) => proxy(init.method || 'GET', url, {
  body: typeof init.body === 'string' ? init.body : undefined, headers: init.headers,
});
window.URL.createObjectURL = () => 'blob:stub';
window.URL.revokeObjectURL = () => {};
window.print = () => {};
window.scrollTo = () => {};
window.alert = () => {};
window.confirm = () => true;
window.matchMedia = window.matchMedia || (q => ({
  matches: false, media: q, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {},
}));
window.addEventListener('error', e => consoleErrors.push('[window.onerror] ' + String(e.error?.stack || e.message).split('\n')[0]));
window.addEventListener('unhandledrejection', e => consoleErrors.push('[unhandledrejection] ' + String(e.reason?.message || e.reason)));

/* jsdom не реализует Element.scrollTo — в браузере он есть */
window.Element.prototype.scrollTo = function () {};
window.HTMLElement.prototype.scrollIntoView = function () {};

/* инжектим ВСЕ локальные скрипты из index.html по порядку — как это делает браузер */
window.matchMedia = window.matchMedia || (q => ({ matches: false, media: q }));
const srcs = [...html.matchAll(/<script src="([^"]+)"><\/script>/g)].map(m => m[1]);
if (!srcs.length) srcs.push('/static/js/app.js');
for (const src of srcs) {
  const rel = src.split('?v=')[0].replace(/^\//, '');
  const file = path.join(ROOT, rel);
  if (!fs.existsSync(file)) { console.log('❌ скрипт не найден:', rel); continue; }
  const sc = window.document.createElement('script');
  sc.textContent = fs.readFileSync(file, 'utf8');
  window.document.body.appendChild(sc);
  console.log('загружен скрипт:', rel);
}

const $ = s => window.document.querySelector(s);
const txt = s => ($(s)?.textContent || '').replace(/\s+/g, ' ').trim();
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  console.log('диагностика глобалов: navigate=' + typeof window.navigate +
              ' api=' + typeof window.api + ' loadNight=' + typeof window.loadNight +
              ' loadCars=' + typeof window.loadCars + ' CAR_BADGE=' + typeof window.CAR_BADGE);
  await sleep(400);
  $('#login-username').value = LOGIN;
  $('#login-password').value = 'demo1234';
  $('#login-form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  for (let i = 0; i < 150 && $('#app').classList.contains('hidden'); i++) await sleep(200);
  if ($('#app').classList.contains('hidden')) {
    console.log('❌ вход не выполнен; login-error=' + JSON.stringify($('#login-error')?.textContent));
    console.log('ошибки консоли:', consoleErrors.slice(0, 8));
    process.exit(1);
  }
  await sleep(700);
  console.log(`вход выполнен: ${txt('#user-name')} / ${txt('#user-role')}`);
  const nav = [...window.document.querySelectorAll('#sidenav .nav-item')]
    .map(b => b.dataset.view).filter(Boolean);
  console.log('навигация:', nav.join(', '));
  const views = VIEWS.filter(v => nav.includes(v));
  const skipped = VIEWS.filter(v => !nav.includes(v));
  if (skipped.length) console.log('пропущено (нет в навигации для этой роли):', skipped.join(', '));

  let empty = 0, failed = 0;
  for (const v of views) {
    const before = consoleErrors.length;
    const t0 = Date.now();
    let threw = null;
    try { window.navigate(v); } catch (e) { threw = e; }
    await sleep(2500);
    const el = $(`#view-${v}`);
    const visText = n => [...n.querySelectorAll('*')].filter(e => !e.closest('.hidden') && !e.classList.contains('hidden'))
      .map(e => e.childNodes.length && [...e.childNodes].some(c => c.nodeType === 3 && c.textContent.trim()) ? c0(e) : '').join(' ');
    const c0 = e => [...e.childNodes].filter(c => c.nodeType === 3).map(c => c.textContent).join('');
    const body = visText(el).replace(/\s+/g, ' ').trim();
    const btnVisible = el?.querySelectorAll('button:not(.hidden)').length || 0;
    const newErrs = consoleErrors.slice(before);
    if (threw) { failed++; console.log(`  ${v.padEnd(11)} ❌ navigate выбросил: ${threw.message}`); continue; }
    if (!body) empty++;
    console.log(`  ${v.padEnd(11)} ${String(body.length).padStart(5)} симв | узлов ${String(el?.querySelectorAll('*').length || 0).padStart(4)} | кнопок ${String(btnVisible).padStart(3)} | active=${el?.classList.contains('active')} | ${Date.now() - t0} мс${body ? '' : '   ← ПУСТО'}`);
    if (body) console.log(`              текст: ${body.slice(0, 140)}`);
    newErrs.slice(0, 4).forEach(e => console.log(`              ⚠ ${e.slice(0, 200)}`));
  }

  console.log('\n=== уникальные ошибки консоли ===');
  const uniq = [...new Set(consoleErrors.map(e => e.slice(0, 240)))];
  uniq.length ? uniq.forEach(e => console.log('  ' + e)) : console.log('  нет');
  console.log(`\nИТОГ: пустых разделов ${empty}, сбоев ${failed}, ошибок консоли ${uniq.length}`);
  console.log('сетевых запросов:', netLog.length);
  process.exit(empty + failed + uniq.length ? 2 : 0);
}
main().catch(e => { console.error('harness:', e); process.exit(1); });
