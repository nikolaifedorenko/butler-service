/* Service Worker «Батлер Сервис».
   Статика (оболочка приложения) — из кэша, с фоновым обновлением; API — всегда сеть:
   отметки и табель никогда не берутся из кэша. Версию меняйте вместе с ?v= в index.html. */
const VERSION = 'tt-2026-11-17d';
// содержимое оболочки: f0f5c645e2f4dc53
const SHELL = [
  '/',
  '/static/css/app.css?v=2026-11-17d',
  '/static/css/base.css?v=2026-11-17d',
  '/static/css/components.css?v=2026-11-17d',
  '/static/css/tokens.css?v=2026-11-17d',
  '/static/js/app.js',
  '/static/js/core.js',
  '/static/js/modules/access.js',
  '/static/js/modules/audit.js',
  '/static/js/modules/cars.js',
  '/static/js/modules/dicts.js',
  '/static/js/modules/docs.js',
  '/static/js/modules/employees.js',
  '/static/js/modules/engine_settings.js',
  '/static/js/modules/fact.js',
  '/static/js/modules/marks.js',
  '/static/js/modules/me.js',
  '/static/js/modules/mgmt.js',
  '/static/js/modules/night.js',
  '/static/js/modules/punches_journal.js',
  '/static/js/modules/settings.js',
  '/static/js/modules/settings_calc.js',
  '/static/js/modules/settings_calendar.js',
  '/static/js/modules/settings_codes.js',
  '/static/js/modules/settings_docs.js',
  '/static/js/modules/settings_groups.js',
  '/static/js/modules/settings_notify.js',
  '/static/js/modules/settings_overview.js',
  '/static/js/modules/settings_pay.js',
  '/static/js/modules/settings_shifts.js',
  '/static/js/modules/settings_system.js',
  '/static/js/modules/stays.js',
  '/static/js/modules/stays_blocks.js',
  '/static/js/modules/stays_board.js',
  '/static/js/modules/stays_bookings.js',
  '/static/js/modules/stays_family.js',
  '/static/js/modules/stays_filters.js',
  '/static/js/modules/stays_forms.js',
  '/static/js/modules/stays_fund.js',
  '/static/js/modules/stays_guests.js',
  '/static/js/modules/stays_mine.js',
  '/static/js/modules/stays_ooo.js',
  '/static/js/modules/stays_settings.js',
  '/static/js/modules/tabel.js',
  '/static/js/modules/timesheet_common.js',
  '/static/js/modules/timesheet_layers.js',
  '/static/js/ui/html.js',
  '/static/js/ui/theme.js?v=2026-11-17d',
  '/static/vendor/lit-html/directive.js',
  '/static/vendor/lit-html/directives/unsafe-html.js',
  '/static/vendor/lit-html/lit-html.js',
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
