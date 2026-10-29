/* Service Worker «Батлер Сервис».
   Статика (оболочка приложения) — из кэша, с фоновым обновлением; API — всегда сеть:
   отметки и табель никогда не берутся из кэша. Версию меняйте вместе с ?v= в index.html. */
const VERSION = 'tt-tt-2026-10-29f';
// содержимое оболочки: ac425c17a62a94f3
const SHELL = [
  '/',
  '/static/css/app.css?v=tt-2026-10-29f',
  '/static/js/app.js?v=tt-2026-10-29f',
  '/static/js/core.js?v=tt-2026-10-29f',
  '/static/js/modules/access.js?v=tt-2026-10-29f',
  '/static/js/modules/audit.js?v=tt-2026-10-29f',
  '/static/js/modules/cars.js?v=tt-2026-10-29f',
  '/static/js/modules/dicts.js?v=tt-2026-10-29f',
  '/static/js/modules/docs.js?v=tt-2026-10-29f',
  '/static/js/modules/employees.js?v=tt-2026-10-29f',
  '/static/js/modules/engine_settings.js?v=tt-2026-10-29f',
  '/static/js/modules/fact.js?v=tt-2026-10-29f',
  '/static/js/modules/marks.js?v=tt-2026-10-29f',
  '/static/js/modules/me.js?v=tt-2026-10-29f',
  '/static/js/modules/mgmt.js?v=tt-2026-10-29f',
  '/static/js/modules/night.js?v=tt-2026-10-29f',
  '/static/js/modules/punches_journal.js?v=tt-2026-10-29f',
  '/static/js/modules/settings.js?v=tt-2026-10-29f',
  '/static/js/modules/settings_calc.js?v=tt-2026-10-29f',
  '/static/js/modules/settings_calendar.js?v=tt-2026-10-29f',
  '/static/js/modules/settings_codes.js?v=tt-2026-10-29f',
  '/static/js/modules/settings_docs.js?v=tt-2026-10-29f',
  '/static/js/modules/settings_groups.js?v=tt-2026-10-29f',
  '/static/js/modules/settings_notify.js?v=tt-2026-10-29f',
  '/static/js/modules/settings_overview.js?v=tt-2026-10-29f',
  '/static/js/modules/settings_pay.js?v=tt-2026-10-29f',
  '/static/js/modules/settings_shifts.js?v=tt-2026-10-29f',
  '/static/js/modules/settings_system.js?v=tt-2026-10-29f',
  '/static/js/modules/stays.js?v=tt-2026-10-29f',
  '/static/js/modules/stays_board.js?v=tt-2026-10-29f',
  '/static/js/modules/stays_bookings.js?v=tt-2026-10-29f',
  '/static/js/modules/stays_filters.js?v=tt-2026-10-29f',
  '/static/js/modules/stays_forms.js?v=tt-2026-10-29f',
  '/static/js/modules/stays_fund.js?v=tt-2026-10-29f',
  '/static/js/modules/stays_guests.js?v=tt-2026-10-29f',
  '/static/js/modules/stays_settings.js?v=tt-2026-10-29f',
  '/static/js/modules/tabel.js?v=tt-2026-10-29f',
  '/static/js/modules/timesheet_common.js?v=tt-2026-10-29f',
  '/static/js/modules/timesheet_layers.js?v=tt-2026-10-29f',
  '/manifest.webmanifest',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return;
  if (url.pathname.startsWith('/api/') || url.pathname === '/sw.js') return;   // только сеть

  // навигация (index.html): сначала сеть — чтобы сразу получать новую версию; офлайн — из кэша
  if (req.mode === 'navigate') {
    e.respondWith(fetch(req).then(res => {
      const copy = res.clone();
      caches.open(VERSION).then(c => c.put('/', copy));
      return res;
    }).catch(() => caches.match('/')));
    return;
  }

  // статика: из кэша, параллельно обновляем
  e.respondWith(caches.match(req).then(hit => {
    const net = fetch(req).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(VERSION).then(c => c.put(req, copy)); }
      return res;
    }).catch(() => hit);
    return hit || net;
  }));
});
