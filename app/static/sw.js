/* =====================================================
   SecureVault Service Worker
   Provides offline support and caching
===================================================== */

const CACHE_NAME = 'securevault-v1';
const OFFLINE_URL = '/offline';

/* Assets to cache immediately on install */
const PRECACHE_ASSETS = [
  '/',
  '/login',
  '/dashboard',
  '/static/css/app.css',
  '/static/css/auth.css',
  '/static/js/app.js',
  '/static/manifest.json',
  '/static/img/icon-192.png',
  '/static/img/icon-512.png',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js',
];

/* ── Install ──────────────────────────────────────── */
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      console.log('[SW] Pre-caching assets');
      /* Cache what we can — ignore failures on CDN assets */
      return Promise.allSettled(
        PRECACHE_ASSETS.map(url =>
          cache.add(url).catch(() => console.warn('[SW] Failed to cache:', url))
        )
      );
    }).then(() => self.skipWaiting())
  );
});

/* ── Activate ─────────────────────────────────────── */
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(key => key !== CACHE_NAME)
          .map(key => {
            console.log('[SW] Deleting old cache:', key);
            return caches.delete(key);
          })
      )
    ).then(() => self.clients.claim())
  );
});

/* ── Fetch strategy ───────────────────────────────── */
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  /* Skip non-GET and non-http(s) requests */
  if (request.method !== 'GET') return;
  if (!url.protocol.startsWith('http')) return;

  /* Skip file uploads and API calls — always go to network */
  if (url.pathname.startsWith('/upload') ||
      url.pathname.startsWith('/api/') ||
      url.pathname.startsWith('/file/download') ||
      url.pathname.startsWith('/notifications/count')) {
    return;
  }

  /* Static assets — Cache First */
  if (url.pathname.startsWith('/static/') ||
      url.hostname.includes('cdn.jsdelivr.net') ||
      url.hostname.includes('fonts.googleapis.com') ||
      url.hostname.includes('fonts.gstatic.com')) {
    event.respondWith(
      caches.match(request).then(cached => {
        if (cached) return cached;
        return fetch(request).then(response => {
          if (response && response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
          }
          return response;
        }).catch(() => cached || new Response('', { status: 503 }));
      })
    );
    return;
  }

  /* HTML pages — Network First, fall back to cache */
  event.respondWith(
    fetch(request)
      .then(response => {
        /* Cache successful HTML responses */
        if (response && response.status === 200 &&
            response.headers.get('content-type')?.includes('text/html')) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
        }
        return response;
      })
      .catch(() => {
        /* Offline fallback: serve cached version */
        return caches.match(request).then(cached => {
          if (cached) return cached;
          /* Return offline page for navigation requests */
          if (request.mode === 'navigate') {
            return caches.match('/login') || new Response(
              `<!DOCTYPE html><html><head><meta charset="UTF-8">
               <meta name="viewport" content="width=device-width,initial-scale=1">
               <title>Offline — SecureVault</title>
               <style>body{margin:0;background:#060d1a;color:#fff;font-family:Inter,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;text-align:center;}
               .icon{font-size:3rem;margin-bottom:1rem;}
               h2{font-size:1.4rem;font-weight:800;color:#f1f5f9;margin-bottom:.5rem;}
               p{color:rgba(255,255,255,.5);font-size:.875rem;}
               button{margin-top:1.5rem;padding:.75rem 2rem;background:linear-gradient(135deg,#00c8c8,#4f46e5);border:none;border-radius:10px;color:#fff;font-weight:700;font-size:.9rem;cursor:pointer;}
               </style></head>
               <body><div>
               <div class="icon">📡</div>
               <h2>You're Offline</h2>
               <p>SecureVault needs a connection to load.<br>Check your internet and try again.</p>
               <button onclick="window.location.reload()">Try Again</button>
               </div></body></html>`,
              { headers: { 'Content-Type': 'text/html' } }
            );
          }
          return new Response('', { status: 503 });
        });
      })
  );
});

/* ── Push notifications (future) ─────────────────── */
self.addEventListener('push', event => {
  if (!event.data) return;
  const data = event.data.json();
  self.registration.showNotification(data.title || 'SecureVault', {
    body: data.body || 'You have a new notification',
    icon: '/static/img/icon-192.png',
    badge: '/static/img/icon-72.png',
    data: { url: data.url || '/notifications' }
  });
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    clients.openWindow(event.notification.data.url || '/')
  );
});
