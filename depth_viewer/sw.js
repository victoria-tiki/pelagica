/* ==== sw.js ============================================================= */
/* 0️⃣  Increment this to force-update all caches after you deploy new art */
const VERSION = 'v3';
const STATIC_CACHE = `parallax-${VERSION}`;

/* 1️⃣  Exact filenames or globs you want to treat as “static layers” */
const STATIC_LAYERS = [
  'layer7_top.webp','layer8_top.webp','layer9_top.webp','front_top.webp',
  'back.avif','back.webp','back.png',
  'layer3.avif','layer3.webp','layer3.png',
  'layer4.avif','layer4.webp','layer4.png',
  'layer5.avif','layer5.webp','layer5.png',
  'layer6.avif','layer6.webp','layer6.png',
  'layer7.png',
  'layer8.png',
  'layer9.png',
  'front.png'
];

/* 2️⃣  Pre-cache on install so the *very first* visit is fast */
self.addEventListener('install', event => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(STATIC_CACHE)
          .then(cache => cache.addAll(STATIC_LAYERS))
  );
});

/* 3️⃣  Claim control ASAP */
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys
        .filter(k => k.startsWith('parallax-') && k !== STATIC_CACHE)
        .map(k => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

/* 4️⃣  Fetch handler — pick ONE of the two paths   */
/* ---- 4a  CACHE-FIRST (fastest, simplest) -------- */
/*
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;

  const url = new URL(event.request.url);
  if (!STATIC_LAYERS.includes(url.pathname.replace(/^\//,''))) return;

  event.respondWith(
    caches.match(event.request).then(cached =>
      cached || fetch(event.request).then(resp => {
        // clone so we can put one copy in CacheStorage
        const copy = resp.clone();
        caches.open(STATIC_CACHE).then(c => c.put(event.request, copy));
        return resp;
      })
    )
  );
});
*/

/* ---- 4b  STALE-WHILE-REVALIDATE ------------------ */
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;

  const url = new URL(event.request.url);
  if (!STATIC_LAYERS.includes(url.pathname.replace(/^\//,''))) return;

  event.respondWith(
    caches.open(STATIC_CACHE).then(async cache => {
      const cached = await cache.match(event.request);
      const networkPromise = fetch(event.request).then(resp => {
        cache.put(event.request, resp.clone());
        return resp;
      });
      return cached || networkPromise;         // return fast, update later
    })
  );
});

