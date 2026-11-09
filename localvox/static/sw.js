'use strict';
// No CacheStorage or IndexedDB: shared audio lives only in volatile worker memory.
let pending = [];
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (url.origin === self.location.origin && url.pathname === '/share' && event.request.method === 'POST') {
    event.respondWith((async () => {
      const form = await event.request.formData();
      pending = form.getAll('files').filter(f => f instanceof File);
      setTimeout(() => { pending = []; }, 120000);
      return Response.redirect(new URL('/#shared', self.location.origin).href, 303);
    })());
  }
});
self.addEventListener('message', event => {
  if (event.data?.type === 'GET_SHARED' && event.source && new URL(event.source.url).pathname === '/') {
    event.source.postMessage({type:'SHARED_FILES', files:pending}); pending = [];
  }
});
