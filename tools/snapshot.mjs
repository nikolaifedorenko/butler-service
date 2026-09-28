/* Снимки интерфейса БЕЗ браузера: разделы рендерятся настоящим app.js в jsdom против
   живого uvicorn, затем сериализуется DOM и собирается в одну самодостаточную галерею
   (стили встроены, внешних ресурсов нет — файл открывается где угодно).

   Использование: node snapshot.mjs <base-url> <out.html> */
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { fileURLToPath } from 'node:url';
import { JSDOM, VirtualConsole } from 'jsdom';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const BASE = process.argv[2] || 'http://127.0.0.1:8231';
const OUT = process.argv[3] || path.join(HERE, 'snapshot.html');

const html = fs.readFileSync(path.join(ROOT, 'static/index.html'), 'utf8');
const css = fs.readFileSync(path.join(ROOT, 'static/css/app.css'), 'utf8');
const scripts = [...html.matchAll(/<script src="([^"]+)"><\/script>/g)]
  .map(m => path.join(ROOT, m[1].split('?v=')[0].replace(/^\//, '')));

const jar = new Map();
function proxy(method, url, { body, headers } = {}) {
  return new Promise((resolve, reject) => {
    const u = new URL(url, BASE);
    const req = http.request({
      hostname: u.hostname, port: u.port, path: u.pathname + u.search, method,
      headers: { ...(headers || {}),
                 ...(jar.size ? { Cookie: [...jar].map(([k, v]) => `${k}=${v}`).join('; ') } : {}),
                 ...(body ? { 'Content-Length': Buffer.byteLength(body) } : {}) },
    }, res => {
      (res.headers['set-cookie'] || []).forEach(c => {
        const [kv] = c.split(';'); const i = kv.indexOf('='); jar.set(kv.slice(0, i), kv.slice(i + 1));
      });
      const chunks = [];
      res.on('data', d => chunks.push(d));
      res.on('end', () => {
        const text = Buffer.concat(chunks).toString('utf8');
        resolve({ status: res.statusCode, ok: res.statusCode < 400, headers: res.headers,
                  text: async () => text, json: async () => JSON.parse(text) });
      });
    });
    req.on('error', reject);
    if (body) req.write(body);
    req.end();
  });
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function newPage(viewport, mobile) {
  const vc = new VirtualConsole();                    // консоль приложения не шумит в отчёт
  vc.on('jsdomError', () => {});
  const dom = new JSDOM(html, { url: BASE + '/', runScripts: 'dangerously',
                                pretendToBeVisual: true, virtualConsole: vc });
  const w = dom.window;
  w.fetch = (url, init = {}) => proxy(init.method || 'GET', url,
    { body: typeof init.body === 'string' ? init.body : undefined, headers: init.headers });
  w.URL.createObjectURL = () => 'blob:stub';
  w.URL.revokeObjectURL = () => {};
  w.print = () => {}; w.alert = () => {}; w.confirm = () => true;
  w.Element.prototype.scrollTo = () => {};
  w.HTMLElement.prototype.scrollIntoView = () => {};
  w.matchMedia = w.matchMedia || (q => ({ matches: false, media: q }));
  for (const f of scripts) {
    const sc = w.document.createElement('script');
    sc.textContent = fs.readFileSync(f, 'utf8');
    w.document.body.appendChild(sc);
  }
  // «экран» нужного размера: jsdom не считает layout, поэтому размеры в CSS подменяем
  w.document.documentElement.style.width = viewport.width + 'px';
  return { w, dom, viewport, mobile };
}

async function login(page, user) {
  const { w } = page;
  w.document.querySelector('#login-username').value = user;
  w.document.querySelector('#login-password').value = 'demo1234';
  w.document.querySelector('#login-form')
    .dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
  for (let i = 0; i < 200 && w.document.querySelector('#app').classList.contains('hidden'); i++) await sleep(150);
  if (w.document.querySelector('#app').classList.contains('hidden')) throw new Error('вход не выполнен');
  await sleep(900);
}

async function goto(page, view) {
  const { w } = page;
  w.navigate(view);
  for (let i = 0; i < 80; i++) {
    await sleep(200);
    const t = (w.document.querySelector(`#view-${view}`)?.textContent || '').trim();
    if (t && !t.includes('Загрузка')) break;
  }
  await sleep(500);
}

function capture(page, label) {
  const { w } = page;
  const app = w.document.querySelector('#app').cloneNode(true);
  const modal = w.document.querySelector('#modal-backdrop')?.cloneNode(true);
  const wrap = w.document.createElement('div');
  wrap.appendChild(app);
  if (modal && !modal.classList.contains('hidden')) wrap.appendChild(modal);
  let out = wrap.innerHTML;
  out = out.replace(/<script[\s\S]*?<\/script>/g, '');
  return { label, html: out };
}

const TITLES = {
  schedule: 'График', onwork: 'Кто на работе', attendance: 'Посещения', timesheet: 'Табель',
  employees: 'Сотрудники', me: 'Мои отметки', night: 'Ночной отчёт', cars: 'Электрокары',
  settings: 'Настройки',
};

const shots = [];
async function main() {
  // ── менеджер (десктоп) ──
  const desk = await newPage({ width: 1440, height: 940 }, false);
  await login(desk, 'gromova');
  const who = desk.w.document.querySelector('#user-name').textContent;
  console.log('вход:', who);
  for (const v of ['schedule', 'onwork', 'attendance', 'timesheet', 'employees', 'me', 'night', 'cars', 'settings']) {
    await goto(desk, v);
    shots.push({ ...capture(desk, `${TITLES[v]} · менеджер (десктоп 1440px)`), h: 900 });
    console.log('  снят раздел:', v);
  }
  // модалка возврата кара
  await goto(desk, 'cars');
  const ret = desk.w.document.querySelector('[data-act="return"]');
  if (ret) { ret.click(); await sleep(1400); shots.push({ ...capture(desk, 'Электрокары → модалка «Возврат кара»'), h: 900 }); console.log('  снята модалка: возврат кара'); desk.w.closeModal?.(); }
  await goto(desk, 'night');
  const nightCars = desk.w.document.querySelector('#night-cars-open');
  if (nightCars) { nightCars.click(); await sleep(2000); shots.push({ ...capture(desk, 'Ночной отчёт → шаг «Проверка электрокаров»'), h: 900 }); console.log('  снята модалка: ночные кары'); desk.w.closeModal?.(); }
  const arch = desk.w.document.querySelector('#night-archive');
  if (arch) { arch.click(); await sleep(2000); shots.push({ ...capture(desk, 'Ночной отчёт → архив смен'), h: 900 }); console.log('  снята модалка: архив смен'); }

  // ── сотрудник (телефон) ──
  const mob = await newPage({ width: 390, height: 844 }, true);
  mob.w.document.documentElement.classList.add('mobile-shot');
  await login(mob, 'ivanov');
  console.log('вход (сотрудник):', mob.w.document.querySelector('#user-name').textContent);
  for (const v of ['me', 'night', 'cars', 'schedule']) {
    await goto(mob, v);
    shots.push({ ...capture(mob, `${TITLES[v]} · сотрудник (телефон 390px)`), h: 844, mobile: true });
    console.log('  снят раздел (телефон):', v);
  }

  const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const frames = shots.map((s, i) => `
    <figure class="shot ${s.mobile ? 'mobile' : ''}">
      <figcaption><span class="n">${i + 1}</span>${esc(s.label)}</figcaption>
      <div class="screen" style="height:${s.h}px"><div class="page">${s.html}</div></div>
    </figure>`).join('\n');

  const page = `<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Батлер Сервис — снимки интерфейса</title>
<style>
${css}
</style>
<style>
/* оформительская обёртка галереи (не относится к приложению) */
html,body{background:#e9edf3;margin:0}
body{font:15px/1.6 -apple-system,'Segoe UI',Roboto,Arial,sans-serif;color:#101828;padding:28px 18px 60px}
.gal-head{max-width:1500px;margin:0 auto 22px}
.gal-head h1{font-size:24px;margin:0 0 6px}
.gal-head p{margin:4px 0;color:#475467;font-size:14px}
.shot{max-width:1500px;margin:0 auto 30px;background:#fff;border:1px solid #d0d5dd;border-radius:14px;
  overflow:hidden;box-shadow:0 1px 3px rgba(16,24,40,.1)}
.shot figcaption{padding:11px 16px;border-bottom:1px solid #eaecf0;font-weight:650;font-size:14px;
  background:#f8fafc;display:flex;gap:10px;align-items:center}
.shot figcaption .n{display:inline-grid;place-items:center;width:22px;height:22px;border-radius:50%;
  background:#2f6feb;color:#fff;font-size:12px;flex:none}
.screen{overflow:auto;background:#f4f6fa}
.shot.mobile{max-width:440px}
.shot.mobile .screen{height:844px}
.shot.mobile .page{width:390px;margin:0 auto}
.page{min-width:100%}
/* приложение рассчитано на 100dvh — в снимке фиксируем высоту контейнером */
.page .app,.page .layout,.page .content{min-height:0}
.page .layout{height:auto}
.page .content{overflow:visible}
</style></head><body>
<div class="gal-head">
  <h1>Батлер Сервис — снимки интерфейса после исправлений</h1>
  <p>Разделы отрисованы <b>настоящим кодом приложения</b> (<code>static/js/app.js</code>,
     <code>section_night.js</code>, <code>section_cars.js</code>) против живого сервера
     с демо-данными, затем DOM сериализован вместе со штатными стилями <code>app.css</code>.</p>
  <p>Это не скриншоты и не макет: разметка и стили — те самые, что отдаёт сервер.
     Клики не работают (скрипты из снимка удалены), прокрутка внутри кадра — работает.</p>
  <p>Снято: 9 разделов под менеджером (десктоп 1440px), 3 модалки, 4 раздела под сотрудником
     (телефон 390px). Всего кадров: ${shots.length}.</p>
</div>
${frames}
</body></html>`;
  fs.writeFileSync(OUT, page, 'utf8');
  console.log('галерея:', OUT, (fs.statSync(OUT).size / 1024 / 1024).toFixed(2) + ' МБ');
}

main().catch(e => { console.error('snapshot:', e); process.exit(1); });
