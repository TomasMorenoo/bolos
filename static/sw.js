const CACHE_NAME = 'bolos-cache-v1';
const urlsToCache = [
  '/',
  '/players',
  '/outings',
  '/manifest.json'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        return cache.addAll(urlsToCache);
      })
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        // Devuelve la versión en caché o hace la petición a la red
        return response || fetch(event.request);
      })
  );
});