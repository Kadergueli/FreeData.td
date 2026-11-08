/**
 * FreeData.td — Progressive Web App Service Worker
 *
 * Uses a Network-First strategy with offline cache fallback:
 * - Online: every request goes straight to the network (live data, zero stale cache)
 *   and successful GET responses (shell assets + public API reads) are saved in CacheStorage.
 * - Offline: falls back to the cached response so the installed mobile/desktop app
 *   continues to open and browse previously loaded datasets without a connection.
 */

const CACHE_NAME = 'freedatatd-pwa-v1';

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  // Never cache authenticated admin endpoints or live export streams in the Service Worker
  if (url.pathname.startsWith('/api/v1/admin') || url.pathname.startsWith('/api/v1/export/')) {
    return;
  }

  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.status === 200 && res.type === 'basic') {
          const clone = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, clone)).catch(() => {});
        }
        return res;
      })
      .catch(async () => {
        const cached = await caches.match(req);
        if (cached) return cached;
        if (req.mode === 'navigate') {
          const shell = await caches.match('/');
          if (shell) return shell;
        }
        throw new Error('Offline and not in cache');
      })
  );
});

