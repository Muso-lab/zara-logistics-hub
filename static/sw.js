// Zara Logistics Hub Service Worker
const CACHE_NAME = 'zara-logistics-v1';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(clients.claim());
});

self.addEventListener('fetch', (event) => {
  // Pass-through to network with fallback
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
