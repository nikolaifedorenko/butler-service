/* Service Worker «Батлер Сервис».
   Статика (оболочка приложения) — из кэша, с фоновым обновлением; API — всегда сеть:
   отметки и табель никогда не берутся из кэша. Версию меняйте вместе с ?v= в index.html. */
const VERSION = 'tt-2026-10-31a';
// содержимое оболочки: b5cbc8fddbef4674
const SHELL = [
  '/',
  '/static/css/app.css?v=2026-10-31a',
  '/static/js/app.js?v=2026-10-31a',
  '/static/js/core.js?v=2026-10-31a',
  '/static/js/modules/access.js?v=2026-10-31a',
  '/static/js/modules/audit.js?v=2026-10-31a',
  '/static/js/modules/cars.js?v=2026-10-31a',
  '/static/js/modules/dicts.js?v=2026-10-31a',
  '/static/js/modules/docs.js?v=2026-10-31a',
  '/static/js/modules/employees.js?v=2026-10-31a',
  '/static/js/modules/engine_settings.js?v=2026-10-31a',
  '/static/js/modules/fact.js?v=2026-10-31a',
  '/static/js/modules/marks.js?v=2026-10-31a',
  '/static/js/modules/me.js?v=2026-10-31a',
  '/static/js/modules/mgmt.js?v=2026-10-31a',
  '/static/js/modules/night.js?v=2026-10-31a',
  '/static/js/modules/punches_journal.js?v=2026-10-31a',
  '/static/js/modules/settings.js?v=2026-10-31a',
  '/static/js/modules/settings_calc.js?v=2026-10-31a',
  '/static/js/modules/settings_calendar.js?v=2026-10-31a',
  '/static/js/modules/settings_codes.js?v=2026-10-31a',
  '/static/js/modules/settings_docs.js?v=2026-10-31a',
  '/static/js/modules/settings_groups.js?v=2026-10-31a',
  '/static/js/modules/settings_notify.js?v=2026-10-31a',
  '/static/js/modules/settings_overview.js?v=2026-10-31a',
  '/static/js/modules/settings_pay.js?v=2026-10-31a',
  '/static/js/modules/settings_shifts.js?v=2026-10-31a',
  '/static/js/modules/settings_system.js?v=2026-10-31a',
  '/static/js/modules/stays.js?v=2026-10-31a',
  '/static/js/modules/stays_board.js?v=2026-10-31a',
  '/static/js/modules/stays_bookings.js?v=2026-10-31a',
  '/static/js/modules/stays_family.js?v=2026-10-31a',
  '/static/js/modules/stays_filters.js?v=2026-10-31a',
  '/static/js/modules/stays_forms.js?v=2026-10-31a',
  '/static/js/modules/stays_fund.js?v=2026-10-31a',
  '/static/js/modules/stays_guests.js?v=2026-10-31a',
  '/static/js/modules/stays_settings.js?v=2026-10-31a',
  '/static/js/modules/tabel.js?v=2026-10-31a',
  '/static/js/modules/timesheet_common.js?v=2026-10-31a',
  '/static/js/modules/timesheet_layers.js?v=2026-10-31a',
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
