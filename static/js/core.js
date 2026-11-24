/* ══════════════════════════════════════════════════════════════════════
   ЯДРО ИНТЕРФЕЙСА — общие хелперы, не зависящие от конкретного раздела.

   Файл вынесен из app.js (шаг 1 модульной разбивки): сюда переехали утилиты,
   транспорт (api/multipartApi/downloadBlob), общее состояние и модалки.
   Подключается в index.html ПЕРЕД app.js и файлами разделов.

   Файл — ES-модуль: общее ядро импортируют разделы (ADR-0013, раздел 7).
   Правила:
     * разделы могут использовать ядро, ядро разделы — НЕ знает
       (единственное исключение — api() при 401 вызывает обработчик входа,
       который app.js задаёт через setLoginHandler);
     * новое общее — сюда, специфичное для раздела — в modules/<раздел>.js.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

import { html, render } from './ui/html.js';

/* Показ формы входа при 401: ядро раздела не знает, app.js сообщает обработчик при запуске
   (прямой import app.js создал бы круг, в котором app.js выполнился бы раньше ядра). */
let showLogin = () => {};
export function setLoginHandler(fn) { showLogin = fn; }

const AUTH_EVENT_KEY = 'butler.auth-context.v1';
const SESSION_CHANGES = new Set(['/api/auth/login', '/api/auth/logout', '/api/auth/change-password',
  '/api/auth/impersonate', '/api/auth/impersonate/stop']);
const authListeners = new Set();
const rejectionListeners = new Set();
const pendingIssuers = new Set();

function readAuthEvent() {
  try {
    const value = JSON.parse(localStorage.getItem(AUTH_EVENT_KEY));
    if (typeof value?.eventId === 'string' && value.eventId &&
        (value.context === null || typeof value.context === 'string' && value.context)) return value;
  } catch { /* локальное состояние и проверка cookie работают и без хранилища */ }
  return null;
}

let storedEventId = readAuthEvent()?.eventId || '';
let auth = { context: null, eventId: storedEventId };
let suspended;
// Sessions opened before the companion cookie was introduced remain usable until their first rotation.
let legacyContext = null;

function notifyAuth(event, external) {
  for (const listener of authListeners) listener({ ...event, external });
}

export function adoptAuthContext(context = null) {
  legacyContext = getCookie('tt_auth_context') ? null : context;
  if (auth.context === context) return;
  auth = { context, eventId: auth.eventId };
  notifyAuth(auth, false);
}

export function publishAuthContext(context = null) {
  legacyContext = null;
  const id = Array.from(crypto.getRandomValues(new Uint32Array(4)), n => n.toString(16).padStart(8, '0')).join('');
  auth = { context, eventId: id };
  try {
    localStorage.setItem(AUTH_EVENT_KEY, JSON.stringify(auth));
    storedEventId = id;
  } catch { /* в текущей вкладке всё равно отменяем задания синхронно */ }
  notifyAuth(auth, false);
  if (context === null) showLogin();
}

// Читаем последнее сохранённое событие: очередь storage могла задержаться, пока вкладка спала.
function syncAuthEvent() {
  const event = readAuthEvent();
  if (!event || event.eventId === storedEventId) return;
  storedEventId = event.eventId;
  // Прежний экран не может печатать от нового пользователя, пока reload ожидает навигации.
  // Подписчики получают событие сейчас, а свою идентичность новая страница примет из /me.
  auth = { context: null, eventId: event.eventId };
  notifyAuth({ context: event.context, eventId: event.eventId }, true);
  if (event.context === null) showLogin();
  else location.reload();
}
window.addEventListener('storage', e => { if (e.key === AUTH_EVENT_KEY) syncAuthEvent(); });

export function authContextSnapshot() {
  syncAuthEvent();
  return { ...auth };
}

export function authContextIsCurrent(started) {
  const now = authContextSnapshot();
  if (!started.context || started.context !== now.context || started.eventId !== now.eventId || suspended?.owner === auth) {
    return false;
  }
  const marker = getCookie('tt_auth_context');
  if (marker === started.context || !marker && legacyContext === started.context) return true;
  void expireAuthContext(started);
  return false;
}

export function requireAuthOwnership(started = auth) {
  if (!authContextIsCurrent(started)) throw new Error('Сессия изменилась');
  return started;
}

export function subscribeAuthContext(listener) {
  authListeners.add(listener);
  return () => authListeners.delete(listener);
}

export function subscribeSessionRejection(listener) {
  rejectionListeners.add(listener);
  return () => rejectionListeners.delete(listener);
}

// Запоздалый 401 из предыдущей сессии не должен разлогинить уже вошедшего пользователя.
export async function expireAuthContext(started) {
  const current = authContextSnapshot();
  if (!started.context || started.eventId !== current.eventId || started.context !== current.context) return;
  const owner = auth;
  if (suspended?.owner === owner) return suspended.check;
  const hold = { owner };
  suspended = hold;
  for (const listener of rejectionListeners) listener();
  hold.check = (async () => {
    // Only an issuer already in flight for this owner can settle its own cookie change.
    // Rejection listeners above have already retired the UI and its print jobs.
    const pending = [...pendingIssuers].filter(issuer => issuer.owner === owner);
    if (pending.length) {
      await Promise.all(pending.map(issuer => issuer.done));
      syncAuthEvent();
      if (auth !== owner) return;
    }
    const marker = getCookie('tt_auth_context');
    try {
      const response = await fetch('/api/auth/context', { credentials: 'same-origin', cache: 'no-store',
        signal: AbortSignal.timeout(20_000) });
      const verified = response.ok ? (await response.json()).auth_context : null;
      syncAuthEvent();
      if (auth !== owner) return;
      if (marker === getCookie('tt_auth_context')) {
        if (response.status === 401 && (!marker || marker === 'signed-out' || marker === started.context)) {
          publishAuthContext(null);
          return;
        }
        if (verified && (!marker || marker === verified)) {
          location.reload();
          return;
        }
      }
    } catch { /* Неоднозначный ответ не должен разлогинить другие вкладки. */ }
    syncAuthEvent();
    if (auth === owner) showLogin();
  })();
  return hold.check;
}

/* ───────────────────────────── утилиты ───────────────────────────── */
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export function esc(v) {
  return String(v ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}
export function hhmm(iso) { return iso ? iso.slice(11, 16) : ''; }
export function dateRu(iso) { if (!iso) return ''; const [y, m, d] = iso.split('-'); return `${d}.${m}.${y}`; }
export function hours(v) { return (Math.round((Number(v) || 0) * 100) / 100).toString().replace('.', ','); }
/* Длительность «человеческими» единицами: 1370 мин → «22 ч 50 мин», 90 → «1 ч 30 мин».
   Для счётчиков на доске и в истории — там дробные сотые (22,83) не читаются. */
export function durationRu(minutes) {
  const m = Math.max(0, Math.round(Number(minutes) || 0));
  const h = Math.floor(m / 60), rest = m % 60;
  if (!h) return `${rest} ${plural(rest, 'минута', 'минуты', 'минут')}`;
  return rest ? `${h} ч ${rest} мин` : `${h} ${plural(h, 'час', 'часа', 'часов')}`;
}
export function plural(n, one, few, many) {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
  return many;
}
/* Цвет для атрибута style: только #rgb / #rrggbb, иначе fallback.
   Значения приходят из БД (цвет должности, типа смены); без проверки строка вида
   `red"><a href=…>` вырвалась бы из атрибута — HTML-инъекция. */
export function cssColor(v, fallback = '#8a94a6') {
  const s = String(v ?? '').trim();
  return /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(s) ? s : fallback;
}
export function withAlpha(hex, a) {
  const h = (hex || '#888').replace('#', '');
  const f = h.length === 3 ? h.split('').map(x => x + x).join('') : h;
  const n = parseInt(f, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}
/* тёмный или светлый текст на цветной ячейке */
export function textOn(hex) {
  const h = (hex || '#888').replace('#', '');
  const f = h.length === 3 ? h.split('').map(x => x + x).join('') : h;
  const n = parseInt(f, 16);
  /* относительная яркость по WCAG: выбираем тот из двух текстов, у которого контраст с фоном выше */
  const lin = c => { const v = c / 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  const bg = 0.2126 * lin((n >> 16) & 255) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255);
  const ratio = (a, b) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  /* белый, фирменный тёмно-синий и почти чёрный: на средних тонах (зелёный, оранжевый) только последний даёт 4,5 : 1 */
  const candidates = [['#ffffff', 1], ['#22304a', 0.0286], ['#0b1220', 0.0057]];
  return candidates.reduce((best, c) => (ratio(bg, c[1]) > ratio(bg, best[1]) ? c : best))[0];
}
export function initials(name) {
  const p = String(name || '').split(/\s+/);
  return ((p[0]?.[0] || '') + (p[1]?.[0] || '')).toUpperCase();
}
/* «Сегодня» — по часам объекта (APP_TZ на сервере), а не по часовому поясу телефона.
   serverShiftMs: насколько локальное время объекта опережает UTC-часы устройства
   (учитывает и часовой пояс, и сбитые часы телефона). Обновляется из /api/health и /status. */
export let serverShiftMs = -new Date().getTimezoneOffset() * 60000;   // до первого ответа — пояс устройства
export function syncServerClock(localIso) {
  if (!localIso) return;
  const asUtc = Date.parse(String(localIso).slice(0, 19) + 'Z');
  if (!Number.isNaN(asUtc)) serverShiftMs = asUtc - Date.now();
}
export function todayISO() { return new Date(Date.now() + serverShiftMs).toISOString().slice(0, 10); }
export const MONTHS = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
                'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'];
export const MONTHS_GEN = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
export const WD = ['воскресенье', 'понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота'];
export const WD_SHORT = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];

export function toast(message, type = 'ok', warnings = []) {
  const host = $('#toast-host');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  render(html`${message}${warnings.length
    ? html`<ul>${warnings.map(w => html`<li>${w}</li>`)}</ul>` : ''}`, el);
  host.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .3s'; }, 4600);
  setTimeout(() => el.remove(), 5100);
}
/* Поколения загрузок раздела: ответ устарел, если раздел успели перезагрузить (листание
   месяцев, смена даты). Без этого ответ за прошлый месяц, пришедший позже, рисовался
   поверх текущего: подпись — октябрь, сетка — сентябрь.
     const fresh = loadGeneration('tabel'); const d = await api(…); if (!fresh()) return; */
const loadGenerations = {};
export function loadGeneration(key) {
  const gen = (loadGenerations[key] = (loadGenerations[key] || 0) + 1);
  return () => gen === loadGenerations[key];
}

/* То же, но поколение — у контейнера, в который рисуем: подряд идущие перерисовки ОДНОГО
   контейнера (дата → категория в шахматке) отсекают запоздавший ответ, а разные контейнеры
   (новая вкладка — новый контейнер) друг другу не мешают. Глобальный ключ здесь не подходит:
   старая загрузка, дождавшись своего, брала бы поколение новее и «гасила» видимую вкладку. */
export function loadGenerationFor(el) {
  const gen = String((Number(el.dataset.loadGen) || 0) + 1);
  el.dataset.loadGen = gen;
  return () => el.dataset.loadGen === gen;
}

let pendingLoads = 0;   // спиннер скрывается только когда завершились ВСЕ видимые запросы
export function loading(on) {
  pendingLoads = Math.max(0, pendingLoads + (on ? 1 : -1));
  $('#loading').classList.toggle('hidden', pendingLoads === 0);
}

/* ───────────────────────────── API ───────────────────────────── */
export function getCookie(name) {
  const m = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
  return m ? decodeURIComponent(m[1]) : '';
}
/* Тело ответа: JSON, иначе текст. Ошибка без JSON — это страница прокси (nginx: 413, 502):
   вместо её разметки в тосте — понятный текст. */
function parseBody(text, status) {
  try { return text ? JSON.parse(text) : null; } catch {
    if (status < 400) return { detail: text };
    return { detail: status === 413 ? 'Файл слишком большой для загрузки' : `Ошибка ${status}` };
  }
}
/* Ошибка HTTP-ответа → Error с человеческим текстом.
   FastAPI на 422 (pydantic-валидация) отдаёт detail МАССИВОМ {loc, msg, type} —
   раньше он попадал в тост сырым JSON («[{"loc":["body","year"]…»). Теперь:
   «year: Input should be a valid integer» — поле и причина. Структурные 409
   ({message, …} — «перехват области», «всё равно закрыть?») сохраняют прежний
   контракт: e.message = msg.message, e.payload/e.status для логики вызывающего. */
function httpError(msg, status) {
  if (msg && typeof msg === 'object') {
    if (Array.isArray(msg)) {
      const parts = msg.map(p => {
        const field = Array.isArray(p && p.loc)
          ? p.loc.filter(x => x !== 'body').join('.') : '';
        const text = String((p && p.msg) || JSON.stringify(p));
        return field ? `${field}: ${text}` : text;
      });
      const e = new Error(parts.filter(Boolean).join('; ') || `Ошибка ${status}`);
      e.payload = msg; e.status = status;
      return e;
    }
    const e = new Error(msg.message || JSON.stringify(msg));
    e.payload = msg; e.status = status;
    return e;
  }
  return new Error(String(msg));
}
export async function api(path, opts = {}) {
  const started = auth;
  const method = (opts.method || 'GET').toUpperCase();
  const bootRead = method === 'GET' && opts.allow401 && (path === '/api/auth/me' || path === '/api/health');
  if (started.context || !(bootRead || method === 'POST' && path === '/api/auth/login')) requireAuthOwnership(started);
  const init = { method: opts.method || 'GET', credentials: 'same-origin', headers: {} };
  if (opts.body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(opts.body);
  }
  if (method !== 'GET' && method !== 'HEAD') init.headers['X-CSRF-Token'] = getCookie('tt_csrf');
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts.timeout || 20000);
  init.signal = ctrl.signal;
  if (!opts.silent) loading(true);
  let issuer, settle;
  if (started.context && method === 'POST' && SESSION_CHANGES.has(path)) {
    issuer = { owner: started, done: new Promise(resolve => { settle = resolve; }) };
    pendingIssuers.add(issuer);
  }
  const finishIssuer = () => { if (pendingIssuers.delete(issuer)) settle(); };
  try {
    let res;
    try {
      res = await fetch(path, init);
    } catch (e) {
      // UI-03: изменяющий запрос мог выполниться на сервере — слепой повтор дал бы дубль
      if (e.name === 'AbortError') throw new Error(method === 'GET' || method === 'HEAD'
        ? 'Сервер не ответил вовремя — проверьте связь и повторите'
        : 'Сервер не ответил вовремя — действие могло выполниться: обновите экран, прежде чем повторять');
      throw new Error(navigator.onLine === false
        ? 'Нет подключения к интернету — действие не выполнено'
        : 'Не удалось связаться с сервером — проверьте связь и повторите');
    }
    if (res.status === 401 && !opts.allow401) {
      finishIssuer();
      await expireAuthContext(started);
      throw new Error('Требуется вход');
    }
    const data = parseBody(await res.text(), res.status);
    if (!res.ok) {
      if (started.context) requireAuthOwnership(started);
      const msg = (data && (data.detail || data.message)) || `Ошибка ${res.status}`;
      // единый разбор ошибок (в т.ч. 422-массив pydantic и структурные 409) — httpError
      throw httpError(msg, res.status);
    }
    if (issuer) {
      syncAuthEvent();
      const expected = path === '/api/auth/logout' ? 'signed-out' : data?.auth_context;
      if (auth !== started || !expected || expected !== getCookie('tt_auth_context')) {
        // A retired issuer may have changed the cookie beneath the current shell.
        if (auth !== started) authContextIsCurrent(auth);
        else void expireAuthContext(started);
        throw new Error('Сессия изменилась');
      }
      // Commit while we still own both the initiating generation and the response cookie.
      publishAuthContext(path === '/api/auth/logout' ? null : expected);
    } else if (started.context && !authContextIsCurrent(started)) throw new Error('Сессия изменилась');
    return data;
  } finally {
    finishIssuer();
    clearTimeout(timer);
    if (!opts.silent) loading(false);
  }
}

/* multipart (фото): api() умеет только JSON — загрузка фото идёт через fetch напрямую */
export async function multipartApi(path, formData, { timeout = 60000 } = {}) {
  const started = requireAuthOwnership();
  loading(true);
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeout);
    let res;
    try {
      res = await fetch(path, { method: 'POST', credentials: 'same-origin', body: formData, signal: ctrl.signal,
        headers: { 'X-CSRF-Token': getCookie('tt_csrf') } });
    } catch (e) {
      if (e.name === 'AbortError') throw new Error('Загрузка не завершилась вовремя — проверьте связь');
      throw new Error('Не удалось связаться с сервером — проверьте связь и повторите');
    } finally { clearTimeout(timer); }
    if (res.status === 401) { await expireAuthContext(started); throw new Error('Требуется вход'); }
    const data = parseBody(await res.text(), res.status);
    if (!res.ok) {
      const msg = (data && (data.detail || data.message)) || `Ошибка ${res.status}`;
      throw httpError(msg, res.status);   // тот же разбор, что в api() (P1-fe-4)
    }
    requireAuthOwnership(started);
    return data;
  } finally { loading(false); }
}

/* ───────────────────────────── состояние ───────────────────────────── */
const now0 = new Date();
export const state = {
  user: null,
  perms: [],          // права пользователя (роль + группы + индивидуальные), см. /api/auth/me
  employees: [],
  shiftTypes: [],
  departments: [],
  subdivisions: [],
  docKinds: [],
  docPlaceholders: {},
  tabelCodes: [],     // словарь кодов Табеля (CFG-DAY-CODES): выбор «кода в табеле» у смены
  view: 'schedule',
  grafikLayer: 'schedule',  // активный слой «Графика» (T5): timesheet | schedule | fact | mgmt
  year: now0.getFullYear(),
  month: now0.getMonth() + 1,
  attDate: todayISO(),
  grid: null,
  timesheet: null,
  status: null,
  filterDept: 'all',
  filterText: '',
  expanded: new Set(),
  dpYear: new Date().getFullYear(),                              // календарь двойной оплаты: просматриваемый год
  timers: [],
  appTz: '',           // пояс объекта APP_TZ — из /api/health
  /* Лимиты медиа задаёт объект (Настройки → прочие правила): нужны подсказкам у кнопок
     загрузки фото/видео во всех разделах. Значения по умолчанию — как в app/photos.py. */
  mediaLimits: { photo_max_mb: 12, video_max_mb: 50,
                 photo_retention_days: 180, video_retention_days: 180 },
};

const ROLE_TITLES = { admin: 'Администратор', manager: 'Менеджер', supervisor: 'Супервайзер', employee: 'Сотрудник' };
/* название роли: свои роли приходят с сервера (/api/auth/me), встроенные — запасной вариант */
export function roleTitle(code) { return state.roleTitles?.[code] || ROLE_TITLES[code] || code || '—'; }
/* палитра цветов должностей */
export const POSITION_COLORS = [
  { c: '#8a94a6', t: 'Батлер (серый)' },
  { c: '#e8842c', t: 'Старший батлер (оранжевый)' },
  { c: '#d9a514', t: 'Менеджер / документооборот (жёлтый)' },
  { c: '#7c8db0', t: 'Ночная бригада (серо-синий)' },
  { c: '#4c9a6a', t: 'Зелёный' },
  { c: '#9b59b6', t: 'Фиолетовый' },
];

/* ───────────────────────────── МОДАЛКИ ───────────────────────────── */
/* Тело и подвал окна — шаблон lit-html; строка выводится текстом. */
const modalContent = x => x;

export function openModal({ title, subtitle, body, footer, wide = false, onMount }) {
  if (!state.user) return;
  const m = $('#modal');
  m.className = 'modal' + (wide ? ' wide' : '');
  m.replaceChildren();                       // каждое окно — новое дерево, без остатков прежнего
  const root = document.createElement('div');
  root.style.display = 'contents';           // обёртка не влияет на раскладку головы/тела/подвала
  m.appendChild(root);
  render(html`
    <div class="modal-head">
      <div><h3>${title}</h3>${subtitle ? html`<p>${subtitle}</p>` : ''}</div>
      <button class="icon-btn x" aria-label="Закрыть">
        <svg viewBox="0 0 24 24" width="20" height="20"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
      </button>
    </div>
    <div class="modal-body">${modalContent(body)}</div>
    ${footer ? html`<div class="modal-foot">${modalContent(footer)}</div>` : ''}`, root);
  $('#modal-backdrop').classList.remove('hidden');
  m.querySelector('.x').onclick = closeModal;
  if (onMount) onMount(m);
  return m;
}
export function closeModal() { $('#modal-backdrop').classList.add('hidden'); $('#modal').replaceChildren(); }

/* Боковая панель (ADR-0013, раздел 7: «карточка открывается боковой панелью»): строение как у
   модального окна — голова, прокручиваемое тело, подвал с действиями. Открытые поверх неё
   модальные окна (редакторы) закрываются по Esc первыми. */
export function openDrawer({ title, subtitle, body, footer, onMount }) {
  if (!state.user) return;
  const d = $('#drawer');
  d.replaceChildren();
  const root = document.createElement('div');
  root.style.display = 'contents';
  d.appendChild(root);
  render(html`
    <div class="drawer-head">
      <div><h3>${title}</h3>${subtitle ? html`<p>${subtitle}</p>` : ''}</div>
      <button class="icon-btn x" aria-label="Закрыть">
        <svg viewBox="0 0 24 24" width="20" height="20"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
      </button>
    </div>
    <div class="drawer-body">${modalContent(body)}</div>
    ${footer ? html`<div class="drawer-foot">${modalContent(footer)}</div>` : ''}`, root);
  $('#drawer-backdrop').classList.remove('hidden');
  d.querySelector('.x').onclick = closeDrawer;
  if (onMount) onMount(d);
  return d;
}
export function closeDrawer() { $('#drawer-backdrop').classList.add('hidden'); $('#drawer').replaceChildren(); }

export function confirmDialog(title, text, onYes, yesLabel = 'Подтвердить', danger = true) {
  openModal({
    title, body: html`<p style="margin:0;color:var(--muted)">${text}</p>`,
    footer: html`<button class="btn btn-ghost" data-no>Отмена</button>
             <button class=${`btn ${danger ? 'btn-danger' : 'btn-primary'}`} data-yes>${yesLabel}</button>`,
    onMount(m) {
      m.querySelector('[data-no]').onclick = closeModal;
      m.querySelector('[data-yes]').onclick = async () => { closeModal(); await onYes(); };
    },
  });
}

/* скачивание файлов без перехода по URL: не дёргает браузерные плашки (пароль и т.п.) */
/* Лимиты фото/видео: один запрос при входе, дальше подсказки берут их из state.
   Недоступны — остаются значения по умолчанию (интерфейс не ломается). */
export async function loadMediaLimits() {
  try {
    const lim = await api('/api/photos/limits', { silent: true });
    if (lim && typeof lim === 'object') state.mediaLimits = { ...state.mediaLimits, ...lim };
  } catch { /* подсказки со значениями по умолчанию */ }
  return state.mediaLimits;
}

/* Короткая подсказка про размеры загрузки: «фото до 12 МБ, видео до 50 МБ». */
export function mediaHint() {
  const l = state.mediaLimits || {};
  return `фото до ${l.photo_max_mb || 12} МБ, видео до ${l.video_max_mb || 50} МБ`;
}

export async function downloadBlob(path, fallbackName) {
  loading(true);
  try {
    const started = requireAuthOwnership();
    const res = await fetch(path, { credentials: 'same-origin' });
    if (res.status === 401) { await expireAuthContext(started); throw new Error('Требуется вход'); }
    if (!res.ok) {
      // в detail сервер отдаёт понятный текст (например, подсказку про PDF-движок)
      let msg = `Ошибка ${res.status}`;
      try { const j = JSON.parse(await res.text()); if (typeof j?.detail === 'string') msg = j.detail; } catch { /* не JSON */ }
      throw new Error(msg);
    }
    const blob = await res.blob();
    requireAuthOwnership(started);
    const name = (res.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/)?.[1] || fallbackName;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  } catch (e) { toast(e.message, 'err'); }
  finally { loading(false); }
}
$('#modal-backdrop').addEventListener('click', e => { if (e.target.id === 'modal-backdrop') closeModal(); });
$('#drawer-backdrop').addEventListener('click', e => { if (e.target.id === 'drawer-backdrop') closeDrawer(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') { closeModal();
  if ($('#modal-backdrop').classList.contains('hidden')) closeDrawer(); } });
