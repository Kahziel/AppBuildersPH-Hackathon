const CACHE = 'torquedoc-ui-v8';
const FILES = ['./','./index.html','./app.js','./icons.js','./styles.css','./technical.js','./technical.css','./library.js','./library.css','./mvp.js','./mvp.css','./icon.svg','./manifest.webmanifest'];
const paths = new Set(FILES.map(file => new URL(file, self.location.href).pathname));
self.addEventListener('install', event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(FILES)).then(() => self.skipWaiting())));
self.addEventListener('activate', event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('torquedoc-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim())));
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  // Never cache API responses, answers, health, or original documents.
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || !paths.has(url.pathname)) return;
  event.respondWith(fetch(event.request).then(response => {
    if (response.ok) { const copy = response.clone(); event.waitUntil(caches.open(CACHE).then(cache => cache.put(event.request, copy))); }
    return response;
  }).catch(() => caches.match(event.request).then(cached => cached || new Response('Start the local TorqueDoc backend to load this file.', {status:503}))));
});
