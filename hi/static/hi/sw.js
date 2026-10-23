const CACHE_NAME = 'media-app-v2';
const URLS = [
    '/app/',
    '/static/hi/app.css',
    '/static/hi/app.js',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(URLS))
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', (event) => {
    const req = event.request;
    if (req.method !== 'GET') return;

    // API — всегда из сети, без кэша
    if (req.url.includes('/api/')) return;

    event.respondWith(
        caches.match(req).then((cached) => {
            return cached || fetch(req).then((resp) => {
                if (resp.ok && req.url.startsWith(self.location.origin)) {
                    const clone = resp.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(req, clone));
                }
                return resp;
            });
        })
    );
});