/* Сценарий шага «Проверка электрокаров»: окно ночной отметки кара = окно возврата кара.

Зачем: смоук (tools/ui_harness.mjs) проверяет, что разделы ОТРИСОВАНЫ, но не открывает
модалки. Окно отметки кара в ночном обходе приведено к окну возврата кара
(«Электрокары» → «Вернул»): те же чекбоксы состояния, место — выпадающим списком из
справочника, заряд, комментарий и фото (камера/галерея) + чекбокс «Кар найден на месте».
Сценарий проходит путь батлера и сверяет оба окна между собой:

  1. шаг «Проверка электрокаров» открывается из ночного отчёта, в нём список парка;
  2. набор и порядок чекбоксов состояния совпадает с окном возврата кара;
  3. место — <select> из справочника (не свободный текст), заряд — <select>;
  4. фото: «Снять на камеру» (capture=environment) и «Выбрать из галереи»;
  5. «Кар найден на месте» снят → подсказка про замечания супервайзеру;
  6. сохранение формы с файлом уходит multipart'ом, отметка и снимок видны в обходе;
  7. повторное открытие показывает сохранённые значения и миниатюру фото;
  8. карточка кара в разделе «Электрокары» обновлена отметкой обхода.

Запуск: tools/run_night_cars_scenario.sh [порт] [логин]   (нужен jsdom: npm i)
Код возврата: 0 — сценарий пройден, 2 — есть проваленные проверки. */
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { fileURLToPath } from 'node:url';
import { JSDOM, VirtualConsole } from 'jsdom';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const BASE = process.argv[2] || 'http://127.0.0.1:8143';
const LOGIN = process.argv[3] || 'gromova';

/* 1×1 PNG — «снимок с камеры»: фото отметки хранится оригиналом, без перекодирования */
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==',
  'base64');

const consoleErrors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => consoleErrors.push('[jsdomError] ' + String(e.stack || e.message).split('\n')[0]));
vc.on('error', (...a) => consoleErrors.push('[console.error] ' + a.map(String).join(' ')));

const html = fs.readFileSync(path.join(ROOT, 'static/index.html'), 'utf8');
const jar = new Map();
const netLog = [];
const cookieHeader = () => [...jar].map(([k, v]) => `${k}=${v}`).join('; ');

function proxy(method, url, { body, headers } = {}) {
  return new Promise((resolve, reject) => {
    const u = new URL(url, BASE);
    const req = http.request({
      hostname: u.hostname, port: u.port, path: u.pathname + u.search, method,
      headers: {
        ...(headers || {}),
        ...(jar.size ? { Cookie: cookieHeader() } : {}),
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
        resolve({ status: res.statusCode, ok: res.statusCode < 400, headers: res.headers,
          raw: buf, text: async () => text, json: async () => JSON.parse(text) });
      });
    });
    req.on('error', e => { console.error('PROXY ERROR', method, u.pathname, e.code || e.message); reject(e); });
    if (body) req.write(body);
    req.end();
  });
}

/* FormData → multipart-тело. Прокси смоука умеет только строки, а отметка кара
   отправляется формой с файлом (как возврат кара) — иначе фото не доехало бы. */
async function multipart(fd) {
  const boundary = '----nightcars' + Date.now().toString(16);
  const chunks = [];
  for (const [key, val] of fd.entries()) {
    if (typeof val === 'string') {
      chunks.push(Buffer.from(
        `--${boundary}\r\nContent-Disposition: form-data; name="${key}"\r\n\r\n${val}\r\n`, 'utf8'));
    } else {
      const buf = Buffer.from(await val.arrayBuffer());
      chunks.push(Buffer.from(
        `--${boundary}\r\nContent-Disposition: form-data; name="${key}"; filename="${val.name || 'photo.jpg'}"\r\n`
        + `Content-Type: ${val.type || 'application/octet-stream'}\r\n\r\n`, 'utf8'), buf,
        Buffer.from('\r\n', 'utf8'));
    }
  }
  chunks.push(Buffer.from(`--${boundary}--\r\n`, 'utf8'));
  return { buf: Buffer.concat(chunks), contentType: `multipart/form-data; boundary=${boundary}` };
}

const dom = new JSDOM(html, { url: BASE + '/', runScripts: 'dangerously',
  pretendToBeVisual: true, virtualConsole: vc });
const { window } = dom;
window.fetch = async (url, init = {}) => {
  const headers = { ...(init.headers || {}) };
  let body;
  if (typeof init.body === 'string') body = Buffer.from(init.body);
  else if (init.body && typeof init.body.entries === 'function') {
    const m = await multipart(init.body);
    body = m.buf; headers['Content-Type'] = m.contentType;
  } else if (init.body && typeof init.body.arrayBuffer === 'function') {
    body = Buffer.from(await init.body.arrayBuffer());
  }
  return proxy(init.method || 'GET', url, { body, headers });
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
const labels = root => $$('.check-list .chk', root).map(l => l.textContent.replace(/\s+/g, ' ').trim());

let failed = 0, passed = 0;
function check(name, cond, extra = '') {
  if (cond) { passed++; console.log(`  ✓ ${name}`); }
  else { failed++; console.log(`  ❌ ${name}${extra ? ' — ' + extra : ''}`); }
}
async function waitFor(fn, ms = 15000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (fn()) return true; await sleep(150); }
  return false;
}

/* Переход в «Ночной отчёт». navigate() перерисовывает раздел асинхронно: если ждать
   просто появления кнопки, waitFor срабатывает на СТАРОЙ разметке, а клик уходит
   в уже отсоединённый узел (и ничего не происходит). Поэтому ждём две фазы. */
async function gotoNight() {
  window.navigate('night');
  await waitFor(() => !$('#night-cars-open'));
  return waitFor(() => !!$('#night-cars-open') && !text('#night-body').includes('Загрузка'));
}

/* запросы мимо jsdom (тем же cookie-джаром): сверка данных на сервере */
const api = async (method, url, body) => proxy(method, url, body
  ? { body: Buffer.from(JSON.stringify(body)), headers: { 'Content-Type': 'application/json' } } : {});

async function main() {
  await sleep(400);
  const loginRes = await proxy('POST', '/api/auth/login', {
    body: Buffer.from(JSON.stringify({ username: LOGIN, password: 'demo1234' })),
    headers: { 'Content-Type': 'application/json' } });
  if (loginRes.ok) window.eval('bootApp()');
  await waitFor(() => !$('#app').classList.contains('hidden'), 30000);
  check('вход выполнен', !$('#app').classList.contains('hidden'), text('#login-error'));
  await sleep(500);

  /* ── 0. Отчёт текущей смены доступен (его создаёт run_night_cars_scenario.sh) ── */
  const today = await (await api('GET', '/api/night/today')).json();
  check('ночная смена доступна', !!today.available, today.note || '');
  if (!today.available) return finish();
  const reportId = today.report.id;

  /* ── 1. Шаг «Проверка электрокаров» ── */
  console.log('\n1 · Ночной отчёт → шаг «Проверка электрокаров»');
  check('раздел «Ночной отчёт» открылся', await gotoNight());
  click($('#night-cars-open'));
  check('список обхода открылся', await waitFor(() => $$('[data-car-check]').length >= 1),
    text('#modal').slice(0, 120));
  const carBtn = $('[data-car-check]');
  const carId = Number(carBtn.dataset.carCheck);
  const rowText = carBtn.closest('.rule-row')?.textContent || '';
  console.log(`  кар в обходе: id=${carId} · ${rowText.replace(/\s+/g, ' ').trim().slice(0, 80)}`);

  /* ── 2. Эталон: окно возврата кара в разделе «Электрокары» ── */
  console.log('\n2 · Эталон — окно возврата кара');
  window.closeModal();
  window.navigate('cars');
  check('парк отрисован', await waitFor(() => !!$('[data-act="return"]')));
  click($('[data-act="return"]'));
  check('окно возврата открылось', await waitFor(() => !!$('#cr-ok')));
  const returnLabels = labels($('#cr-state'));
  console.log('  чекбоксы возврата:', returnLabels.join(' | '));
  check('в окне возврата есть чекбоксы состояния', returnLabels.length >= 5, String(returnLabels.length));
  const returnHasPhoto = !!$('#cr-cam') && !!$('#cr-file');
  check('в окне возврата есть съёмка фото', returnHasPhoto);
  window.closeModal();

  /* ── 3. Окно ночной отметки: тот же вид + «Кар найден на месте» ── */
  console.log('\n3 · Окно отметки кара в ночном обходе');
  check('вернулись в раздел', await gotoNight());
  click($('#night-cars-open'));
  check('список обхода открылся', await waitFor(() => !!$(`[data-car-check="${carId}"]`)));
  click($(`[data-car-check="${carId}"]`));
  const opened = await waitFor(() => !!$('#nc-found'));
  if (!opened) {
    console.log('  DEBUG toast:', text('#toast-host'));
    console.log('  DEBUG запросы:', netLog.slice(-8).join(' · '));
    console.log('  DEBUG модал:', ($('#modal')?.innerHTML || '').replace(/\s+/g, ' ').slice(0, 400));
  }
  check('окно отметки открылось', opened);
  if (!opened) return finish();
  const modal = $('#modal');

  check('чекбокс «Кар найден на месте»',
    /Кар найден на месте/.test($('#nc-found')?.closest('label')?.textContent || ''));
  check('«Кар найден на месте» — вне группы состояния',
    !!$('#nc-state') && !$('#nc-state').contains($('#nc-found')));
  check('найден — отмечен по умолчанию', $('#nc-found').checked);

  const nightLabels = labels($('#nc-state'));
  console.log('  чекбоксы обхода: ', nightLabels.join(' | '));
  check('набор чекбоксов как в окне возврата',
    returnLabels.every(l => nightLabels.includes(l)) && nightLabels.length === returnLabels.length,
    `возврат: ${returnLabels.join('|')} · обход: ${nightLabels.join('|')}`);
  check('порядок чекбоксов как в окне возврата',
    JSON.stringify(nightLabels) === JSON.stringify(returnLabels));

  const foundSel = $('#nc-found-location');
  const newSel = $('#nc-location');
  check('место «Где нашёл» — выпадающий список', foundSel?.tagName === 'SELECT',
    foundSel?.tagName || 'нет поля');
  check('место «Куда переставил» — выпадающий список', newSel?.tagName === 'SELECT');
  const locNames = (await (await api('GET', '/api/cars/locations')).json()).locations
    .filter(l => l.active).map(l => l.name);
  const optNames = $$('option', foundSel).map(o => o.value).filter(Boolean);
  check('в списке места из справочника', locNames.every(n => optNames.includes(n)),
    `справочник: ${locNames.join('|')} · опции: ${optNames.join('|')}`);
  check('в списке «Куда переставил» те же места',
    locNames.every(n => $$('option', newSel).map(o => o.value).includes(n)));
  check('чекбокс «Перепаркован на другое место»',
    /Перепаркован на другое место/.test($('#nc-moved')?.closest('label')?.textContent || ''));
  check('«Куда переставил» скрыто, пока перепарковка не отмечена',
    $('#nc-newloc-row').classList.contains('hidden'));
  check('заряд — выпадающий список', $('#nc-charge')?.tagName === 'SELECT');
  check('комментарий — textarea', $('#nc-comment')?.tagName === 'TEXTAREA');
  check('фото: съёмка на камеру (capture)', $('#nc-cam')?.getAttribute('capture') === 'environment');
  check('фото: выбор из галереи', $('#nc-file')?.getAttribute('accept') === 'image/*');
  check('нет мусора в DOM', !/undefined|NaN|\[object Object\]/.test(modal.innerHTML));

  /* ── 4. «Кар найден на месте» снят → подсказка про замечания ── */
  console.log('\n4 · Кар не найден');
  check('подсказка скрыта, пока кар найден', $('#nc-notfound').classList.contains('hidden'));
  $('#nc-found').checked = false; change($('#nc-found'));
  check('подсказка показана', !$('#nc-notfound').classList.contains('hidden'));
  check('в подсказке — про замечания супервайзеру', /замечани/i.test(text('#nc-notfound')));
  check('нет перепарковки, когда кар не найден', $('#nc-moved-row').classList.contains('hidden'));
  check('подпись места — «если известно»', text('#nc-found-loc-label') === 'Место (если известно)',
    text('#nc-found-loc-label'));
  $('#nc-found').checked = true; change($('#nc-found'));
  check('подсказка снова скрыта', $('#nc-notfound').classList.contains('hidden'));
  check('перепарковка снова доступна', !$('#nc-moved-row').classList.contains('hidden'));
  check('подпись места — «Где нашёл»', text('#nc-found-loc-label') === 'Где нашёл');

  /* ── 5. Заполнить и сохранить (с фото, как в окне возврата) ── */
  console.log('\n5 · Сохранение отметки с фото');
  const place = optNames.find(n => n !== (foundSel.value || '')) || optNames[0];
  change(foundSel, place);
  change($('#nc-charge'), 'half');
  $('#nc-clean').checked = false; change($('#nc-clean'));
  $('#nc-things').checked = true; change($('#nc-things'));
  $('#nc-canopy').checked = false; change($('#nc-canopy'));
  input($('#nc-comment'), 'сценарий: кар на месте, тент снят');
  const cam = $('#nc-cam');
  Object.defineProperty(cam, 'files', {
    value: [new window.File([new Uint8Array(PNG)], 'kar.png', { type: 'image/png' })],
    configurable: true });
  change(cam);
  check('имя выбранного файла показано', /kar\.png/.test(text('#nc-file-name')), text('#nc-file-name'));

  click($('[data-ok]'));
  check('отметка сохранена (вернулись к списку обхода)',
    await waitFor(() => !!$(`[data-car-check="${carId}"]`) && !$('#nc-found')));
  const row = $(`[data-car-check="${carId}"]`)?.closest('.rule-row');
  check('в списке — бейдж «проверен»', /проверен/.test(row?.textContent || ''));
  check('в списке — значок фото', /📷/.test(row?.textContent || ''));
  check('в списке — место и комментарий отметки',
    (row?.textContent || '').includes('сценарий: кар на месте'), (row?.textContent || '').slice(0, 140));

  /* ── 6. Повторное открытие: сохранённые значения и миниатюра ── */
  console.log('\n6 · Повторное открытие отметки');
  click($(`[data-car-check="${carId}"]`));
  check('окно отметки открылось снова', await waitFor(() => !!$('#nc-found')));
  check('место «где нашёл» подставлено', $('#nc-found-location').value === place,
    $('#nc-found-location').value);
  check('перепарковка не отмечена', !$('#nc-moved').checked
    && $('#nc-newloc-row').classList.contains('hidden'));
  check('заряд подставлен', $('#nc-charge').value === 'half', $('#nc-charge').value);
  check('«Чистый» снят, «В салоне вещи» отмечен, «Тент» снят',
    !$('#nc-clean').checked && $('#nc-things').checked && !$('#nc-canopy').checked);
  check('комментарий подставлен', $('#nc-comment').value === 'сценарий: кар на месте, тент снят');
  const thumb = $('.thumb img', $('#modal'));
  check('миниатюра фото показана', !!thumb && /^\/api\/photos\/\d+\/file$/.test(thumb.getAttribute('src') || ''),
    thumb?.getAttribute('src') || 'нет миниатюры');
  check('фото можно удалить (крестик)', !!$('[data-photo-del]', $('#modal')));
  window.closeModal();

  /* ── 7. Сервер: отметка, фото и карточка кара ── */
  console.log('\n7 · Данные на сервере');
  const state = await (await api('GET', `/api/night/reports/${reportId}/cars`)).json();
  const entry = state.list.find(e => e.car.id === carId);
  check('отметка в обходе', !!entry?.check && entry.check.found === true);
  check('фото привязано к отметке', entry?.check?.photos?.length === 1,
    JSON.stringify(entry?.check?.photos || []).slice(0, 120));
  check('место/заряд/состояние сохранены', entry.check.found_location === place
    && entry.check.moved === false
    && entry.check.charge === 'half' && entry.check.trash === true
    && entry.check.clean === false && entry.check.canopy === false);
  const photoRes = await api('GET', entry.check.photos[0].url);
  check('оригинал фото отдаётся', photoRes.status === 200 && photoRes.raw.equals(PNG),
    `${photoRes.status}, ${photoRes.raw.length} байт`);
  const park = await (await api('GET', '/api/cars')).json();
  const car = park.cars.find(c => c.id === carId);
  check('карточка кара обновлена отметкой', car.location === place && car.charge === 'half'
    && car.trash === true && car.clean === false && car.canopy === false,
    JSON.stringify({ location: car.location, charge: car.charge, trash: car.trash,
      clean: car.clean, canopy: car.canopy }));
  check('время проверки зафиксировано', !!car.last_checked_at);

  /* ── 8. Кар найден, но батлер переставил его на другое место ── */
  console.log('\n8 · Перепарковка');
  click($('#night-cars-open'));
  check('список обхода открылся', await waitFor(() => !!$(`[data-car-check="${carId}"]`)));
  click($(`[data-car-check="${carId}"]`));
  check('окно отметки открылось', await waitFor(() => !!$('#nc-moved')));
  $('#nc-moved').checked = true; change($('#nc-moved'));
  check('поле «Куда переставил» открылось', !$('#nc-newloc-row').classList.contains('hidden'));
  const otherPlace = optNames.find(n => n !== place) || place;
  click($('[data-ok]'));
  check('без нового места не сохраняет', await waitFor(() => /Укажите место/.test(text('#toast-host')))
    && !!$('#nc-moved'), text('#toast-host'));
  change($('#nc-location'), otherPlace);
  input($('#nc-comment'), 'сценарий: мешал проезду, переставил');
  click($('[data-ok]'));
  check('отметка сохранена', await waitFor(() => !!$(`[data-car-check="${carId}"]`) && !$('#nc-moved')));
  const movedRow = $(`[data-car-check="${carId}"]`)?.closest('.rule-row');
  check('в списке — бейдж «перепаркован»', /перепаркован/.test(movedRow?.textContent || ''));
  check('в списке — переход мест', (movedRow?.textContent || '').includes(`${place} → ${otherPlace}`),
    (movedRow?.textContent || '').replace(/\s+/g, ' ').slice(0, 160));

  const st2 = await (await api('GET', `/api/night/reports/${reportId}/cars`)).json();
  const e2 = st2.list.find(e => e.car.id === carId);
  check('отметка: найден и перепаркован', e2.check.found === true && e2.check.moved === true
    && e2.check.found_location === place && e2.check.location === otherPlace);
  check('перепарковка не считается замечанием', st2.problems === 0, String(st2.problems));
  check('место в карточке кара обновлено',
    (await (await api('GET', '/api/cars')).json()).cars.find(c => c.id === carId).location === otherPlace);
  check('фото отметки сохранилось после перепарковки', e2.check.photos?.length === 1);
  window.closeModal();

  /* ── 9. Завершение шага ── */
  console.log('\n9 · Завершение шага');
  click($('#night-cars-open'));
  check('список обхода открылся снова', await waitFor(() => !!$('[data-finish]')));
  click($('[data-finish]'));
  if (await waitFor(() => !!$('[data-yes]'), 5000)) {
    click($('[data-yes]'));          // «Не все кары проверены — завершить всё равно?»
  }
  const stepDone = async () => (await (await api('GET', `/api/night/reports/${reportId}/cars`)).json()).cars_step_done;
  let done = false;
  for (let i = 0; i < 40 && !done; i++) { done = await stepDone(); if (!done) await sleep(200); }
  check('шаг «Проверка электрокаров» завершён', done);
  check('в отчёте шаг помечен готовым', await waitFor(() => /готово/.test(text('#night-body'))));
  window.closeModal();

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
