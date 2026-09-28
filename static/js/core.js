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
     * новое общее — сюда, специфичное для раздела — в sections/<раздел>.js.
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
function plural(n, one, few, many) {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
  return many;
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
async function api(path, opts = {}) {
  const init = { method: opts.method || 'GET', credentials: 'same-origin', headers: {} };
  if (opts.body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(opts.body);
  }
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts.timeout || 20000);
  init.signal = ctrl.signal;
  if (!opts.silent) loading(true);
  try {
    let res;
    try {
      res = await fetch(path, init);
    } catch (e) {
      if (e.name === 'AbortError') throw new Error('Сервер не ответил вовремя — проверьте связь и повторите');
      throw new Error(navigator.onLine === false
        ? 'Нет подключения к интернету — действие не выполнено'
        : 'Не удалось связаться с сервером — проверьте связь и повторите');
    }
    if (res.status === 401 && !opts.allow401) { showLogin(); throw new Error('Требуется вход'); }
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
    if (!res.ok) {
      const msg = (data && (data.detail || data.message)) || `Ошибка ${res.status}`;
      if (msg && typeof msg === 'object') {
        // структурированная ошибка: 409-предупреждения (перехват области, «всё равно закрыть?»)
        const e = new Error(msg.message || JSON.stringify(msg));
        e.payload = msg; e.status = res.status;
        throw e;
      }
      throw new Error(String(msg));
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
      res = await fetch(path, { method: 'POST', credentials: 'same-origin', body: formData, signal: ctrl.signal });
    } catch (e) {
      if (e.name === 'AbortError') throw new Error('Загрузка не завершилась вовремя — проверьте связь');
      throw new Error('Не удалось связаться с сервером — проверьте связь и повторите');
    } finally { clearTimeout(timer); }
    if (res.status === 401) { showLogin(); throw new Error('Требуется вход'); }
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
    if (!res.ok) {
      let msg = (data && (data.detail || data.message)) || `Ошибка ${res.status}`;
      if (msg && typeof msg === 'object') msg = msg.message || JSON.stringify(msg);
      throw new Error(String(msg));
    }
    return data;
  } finally { loading(false); }
}

/* ───────────────────────────── состояние ───────────────────────────── */
const now0 = new Date();
const state = {
  user: null,
  employees: [],
  shiftTypes: [],
  departments: [],
  subdivisions: [],
  docKinds: [],
  docPlaceholders: {},
  view: 'schedule',
  year: now0.getFullYear(),
  month: now0.getMonth() + 1,
  attDate: todayISO(),
  grid: null,
  timesheet: null,
  status: null,
  filterDept: 'all',
  filterText: '',
  expanded: new Set(),
  colorMode: localStorage.getItem('tt_color_mode') || 'shift',   // shift | position
  gridMode: localStorage.getItem('tt_grid_mode') || 'plan',      // plan | fact — вид сетки графика
  showArchived: false,                                           // словарь смен: показывать ли архив
  dpYear: new Date().getFullYear(),                              // календарь двойной оплаты: просматриваемый год
  timers: [],
};

const ROLE_TITLES = { admin: 'Администратор', manager: 'Менеджер', supervisor: 'Супервайзер', employee: 'Сотрудник' };
const STATUS_META = {
  ok:           { t: 'Без отклонений', c: 'ok' },
  late:         { t: 'Опоздание', c: 'warn' },
  early:        { t: 'Ранний уход', c: 'warn' },
  late_early:   { t: 'Опоздание + ранний уход', c: 'warn' },
  no_punch:     { t: 'Нет отметок', c: 'danger' },
  unclosed:     { t: 'Смена не закрыта', c: 'danger' },
  work_no_plan: { t: 'Работа вне графика', c: 'danger' },
  work_off:     { t: 'Работа в выходной', c: 'info' },
  absence:      { t: 'Отсутствие', c: 'muted' },
  off:          { t: 'Выходной', c: 'muted' },
  planned:      { t: 'Смена впереди', c: 'muted' },
  '':           { t: '—', c: 'muted' },
};
function statusBadge(st) {
  const m = STATUS_META[st] || { t: st || '—', c: 'muted' };
  return `<span class="badge ${m.c}">${esc(m.t)}</span>`;
}

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
