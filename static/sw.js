/* Service Worker «Батлер Сервис».
   Статика (оболочка приложения) — из кэша, с фоновым обновлением; API — всегда сеть:
   отметки и табель никогда не берутся из кэша. Версию меняйте вместе с ?v= в index.html. */
const VERSION = 'tt-2026-09-28a';
const SHELL = [
  '/',
  '/static/css/app.css?v=2026-09-28a',
  '/static/js/app.js?v=2026-09-28a',
  '/static/js/section_cars.js?v=2026-09-28a',
  '/static/js/section_night.js?v=2026-09-28a',
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
