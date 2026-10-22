/* ══════════════════════════════════════════════════════════════════════
   ЯДРО ИНТЕРФЕЙСА — общие хелперы, не зависящие от конкретного раздела.

   Файл вынесен из app.js (шаг 1 модульной разбивки): сюда переехали утилиты,
   транспорт (api/multipartApi/downloadBlob), общее состояние и модалки.
   Подключается в index.html ПЕРЕД app.js и файлами разделов.

   Пока это обычный скрипт (не ES-модуль): объявления попадают в общую
   глобальную лексическую область, поэтому существующий код работает без правок.
   Правила:
     * разделы могут использовать ядро, ядро разделы — НЕ знает
       (единственное исключение — api() вызывает showLogin() при 401,
       это происходит в рантайме, когда все скрипты уже загружены);
     * новое общее — сюда, специфичное для раздела — в modules/<раздел>.js.
   ══════════════════════════════════════════════════════════════════════ */
'use strict';

/* ───────────────────────────── утилиты ───────────────────────────── */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function esc(v) {
  return String(v ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}
function hhmm(iso) { return iso ? iso.slice(11, 16) : ''; }
function dateRu(iso) { if (!iso) return ''; const [y, m, d] = iso.split('-'); return `${d}.${m}.${y}`; }
function hours(v) { return (Math.round((Number(v) || 0) * 100) / 100).toString().replace('.', ','); }
/* Длительность «человеческими» единицами: 1370 мин → «22 ч 50 мин», 90 → «1 ч 30 мин».
   Для счётчиков на доске и в истории — там дробные сотые (22,83) не читаются. */
function durationRu(minutes) {
  const m = Math.max(0, Math.round(Number(minutes) || 0));
  const h = Math.floor(m / 60), rest = m % 60;
  if (!h) return `${rest} ${plural(rest, 'минута', 'минуты', 'минут')}`;
  return rest ? `${h} ч ${rest} мин` : `${h} ${plural(h, 'час', 'часа', 'часов')}`;
}
function plural(n, one, few, many) {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
  return many;
}
/* Цвет для атрибута style: только #rgb / #rrggbb, иначе fallback.
   Значения приходят из БД (цвет должности, типа смены); без проверки строка вида
   `red"><a href=…>` вырвалась бы из атрибута — HTML-инъекция. */
function cssColor(v, fallback = '#8a94a6') {
  const s = String(v ?? '').trim();
  return /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(s) ? s : fallback;
}
function withAlpha(hex, a) {
  const h = (hex || '#888').replace('#', '');
  const f = h.length === 3 ? h.split('').map(x => x + x).join('') : h;
  const n = parseInt(f, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}
/* тёмный или светлый текст на цветной ячейке */
function textOn(hex) {
  const h = (hex || '#888').replace('#', '');
  const f = h.length === 3 ? h.split('').map(x => x + x).join('') : h;
  const n = parseInt(f, 16);
  const lum = (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
  return lum > 0.62 ? '#22304a' : '#ffffff';
}
function initials(name) {
  const p = String(name || '').split(/\s+/);
  return ((p[0]?.[0] || '') + (p[1]?.[0] || '')).toUpperCase();
}
/* «Сегодня» — по часам объекта (APP_TZ на сервере), а не по часовому поясу телефона.
   serverShiftMs: насколько локальное время объекта опережает UTC-часы устройства
   (учитывает и часовой пояс, и сбитые часы телефона). Обновляется из /api/health и /status. */
let serverShiftMs = -new Date().getTimezoneOffset() * 60000;   // до первого ответа — пояс устройства
function syncServerClock(localIso) {
  if (!localIso) return;
  const asUtc = Date.parse(String(localIso).slice(0, 19) + 'Z');
  if (!Number.isNaN(asUtc)) serverShiftMs = asUtc - Date.now();
}
function todayISO() { return new Date(Date.now() + serverShiftMs).toISOString().slice(0, 10); }
const MONTHS = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
                'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'];
const MONTHS_GEN = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const WD = ['воскресенье', 'понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота'];
const WD_SHORT = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];

function toast(message, type = 'ok', warnings = []) {
  const host = $('#toast-host');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = esc(message) + (warnings.length
    ? `<ul>${warnings.map(w => `<li>${esc(w)}</li>`).join('')}</ul>` : '');
  host.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .3s'; }, 4600);
  setTimeout(() => el.remove(), 5100);
}
let pendingLoads = 0;   // спиннер скрывается только когда завершились ВСЕ видимые запросы
function loading(on) {
  pendingLoads = Math.max(0, pendingLoads + (on ? 1 : -1));
  $('#loading').classList.toggle('hidden', pendingLoads === 0);
}

/* ───────────────────────────── API ───────────────────────────── */
function getCookie(name) {
  const m = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
  return m ? decodeURIComponent(m[1]) : '';
}
/* Тело ответа: JSON, иначе текст. Ошибка без JSON — это страница прокси (nginx: 413, 502):
   вместо её разметки в тосте — понятный текст (аудит 21.10.2026, OPS-01). */
function parseBody(text, status) {
  try { return text ? JSON.parse(text) : null; } catch {
    if (status < 400) return { detail: text };
    return { detail: status === 413 ? 'Файл слишком большой для загрузки' : `Ошибка ${status}` };
  }
}
/* Ошибка HTTP-ответа → Error с человеческим текстом (ревью 20.10.2026, P1-fe-4).
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
async function api(path, opts = {}) {
  const init = { method: opts.method || 'GET', credentials: 'same-origin', headers: {} };
  if (opts.body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(opts.body);
  }
  const method = (opts.method || 'GET').toUpperCase();
  if (method !== 'GET' && method !== 'HEAD') init.headers['X-CSRF-Token'] = getCookie('tt_csrf');
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts.timeout || 20000);
  init.signal = ctrl.signal;
  if (!opts.silent) loading(true);
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
    if (res.status === 401 && !opts.allow401) { showLogin(); throw new Error('Требуется вход'); }
    const data = parseBody(await res.text(), res.status);
    if (!res.ok) {
      const msg = (data && (data.detail || data.message)) || `Ошибка ${res.status}`;
      // единый разбор ошибок (в т.ч. 422-массив pydantic и структурные 409) — httpError
      throw httpError(msg, res.status);
    }
    return data;
  } finally {
    clearTimeout(timer);
    if (!opts.silent) loading(false);
  }
}

/* multipart (фото): api() умеет только JSON — загрузка фото идёт через fetch напрямую */
async function multipartApi(path, formData, { timeout = 60000 } = {}) {
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
    if (res.status === 401) { showLogin(); throw new Error('Требуется вход'); }
    const data = parseBody(await res.text(), res.status);
    if (!res.ok) {
      const msg = (data && (data.detail || data.message)) || `Ошибка ${res.status}`;
      throw httpError(msg, res.status);   // тот же разбор, что в api() (P1-fe-4)
    }
    return data;
  } finally { loading(false); }
}

/* ───────────────────────────── состояние ───────────────────────────── */
const now0 = new Date();
const state = {
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
function roleTitle(code) { return state.roleTitles?.[code] || ROLE_TITLES[code] || code || '—'; }
/* палитра цветов должностей */
const POSITION_COLORS = [
  { c: '#8a94a6', t: 'Батлер (серый)' },
  { c: '#e8842c', t: 'Старший батлер (оранжевый)' },
  { c: '#d9a514', t: 'Менеджер / документооборот (жёлтый)' },
  { c: '#7c8db0', t: 'Ночная бригада (серо-синий)' },
  { c: '#4c9a6a', t: 'Зелёный' },
  { c: '#9b59b6', t: 'Фиолетовый' },
];

/* ───────────────────────────── МОДАЛКИ ───────────────────────────── */
function openModal({ title, subtitle, body, footer, wide = false, onMount }) {
  const m = $('#modal');
  m.className = 'modal' + (wide ? ' wide' : '');
  m.innerHTML = `
    <div class="modal-head">
      <div><h3>${esc(title)}</h3>${subtitle ? `<p>${esc(subtitle)}</p>` : ''}</div>
      <button class="icon-btn x" aria-label="Закрыть">
        <svg viewBox="0 0 24 24" width="20" height="20"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
      </button>
    </div>
    <div class="modal-body">${body}</div>
    ${footer ? `<div class="modal-foot">${footer}</div>` : ''}`;
  $('#modal-backdrop').classList.remove('hidden');
  m.querySelector('.x').onclick = closeModal;
  if (onMount) onMount(m);
  return m;
}
function closeModal() { $('#modal-backdrop').classList.add('hidden'); $('#modal').innerHTML = ''; }

function confirmDialog(title, text, onYes, yesLabel = 'Подтвердить', danger = true) {
  openModal({
    title, body: `<p style="margin:0;color:var(--muted)">${esc(text)}</p>`,
    footer: `<button class="btn btn-ghost" data-no>Отмена</button>
             <button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" data-yes>${esc(yesLabel)}</button>`,
    onMount(m) {
      m.querySelector('[data-no]').onclick = closeModal;
      m.querySelector('[data-yes]').onclick = async () => { closeModal(); await onYes(); };
    },
  });
}

/* скачивание файлов без перехода по URL: не дёргает браузерные плашки (пароль и т.п.) */
/* Лимиты фото/видео: один запрос при входе, дальше подсказки берут их из state.
   Недоступны — остаются значения по умолчанию (интерфейс не ломается). */
async function loadMediaLimits() {
  try {
    const lim = await api('/api/photos/limits', { silent: true });
    if (lim && typeof lim === 'object') state.mediaLimits = { ...state.mediaLimits, ...lim };
  } catch { /* подсказки со значениями по умолчанию */ }
  return state.mediaLimits;
}

/* Короткая подсказка про размеры загрузки: «фото до 12 МБ, видео до 50 МБ». */
function mediaHint() {
  const l = state.mediaLimits || {};
  return `фото до ${l.photo_max_mb || 12} МБ, видео до ${l.video_max_mb || 50} МБ`;
}

async function downloadBlob(path, fallbackName) {
  loading(true);
  try {
    const res = await fetch(path, { credentials: 'same-origin' });
    if (!res.ok) {
      // в detail сервер отдаёт понятный текст (например, подсказку про PDF-движок)
      let msg = `Ошибка ${res.status}`;
      try { const j = JSON.parse(await res.text()); if (typeof j?.detail === 'string') msg = j.detail; } catch { /* не JSON */ }
      throw new Error(msg);
    }
    const blob = await res.blob();
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
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
