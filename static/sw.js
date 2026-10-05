const CACHE = 'nalam-shell-v2';
const SHELL = ['/', '/static/style.css', '/static/app.js', '/static/icon.svg', '/static/icon-192.png', '/static/icon-512.png'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)));
  self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('nalam-shell-') && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  // Never cache reports, API responses, generated audio, or any health information.
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;
  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).catch(() => caches.match('/')));
  } else if (SHELL.includes(url.pathname)) {
    event.respondWith(fetch(event.request).then(response => {
      if(response.ok) {const copy=response.clone();event.waitUntil(caches.open(CACHE).then(cache=>cache.put(url.pathname,copy)));}
      return response;
    }).catch(() => caches.match(url.pathname)));
  }
});
self.addEventListener('push', event => {
  let payload = {title:'நலம்',body:'ஒரு சிறிய நினைவூட்டல். திறந்து கேட்கலாம்.',url:'/',tag:'nalam'};
  try { payload = {...payload, ...event.data.json()}; } catch (_) {}
  // Only a same-origin path is allowed, even if the pushed payload is malformed.
  const safeUrl = typeof payload.url === 'string' && payload.url.startsWith('/') && !payload.url.startsWith('//') ? payload.url : '/';
  event.waitUntil(self.registration.showNotification(payload.title, {body:payload.body,tag:payload.tag,icon:'/static/icon-192.png',badge:'/static/icon-192.png',data:{url:safeUrl}}));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || '/', self.location.origin).href;
  event.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(async clients => {
    for (const client of clients) {
      if ('focus' in client) {await client.navigate(target);return client.focus();}
    }
    return self.clients.openWindow(target);
  }));
});
