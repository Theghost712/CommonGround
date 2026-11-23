/* CommonGround service worker: push notifications and an offline fallback page.
 * Kept small on purpose. It never caches API responses or the app itself, so a new
 * deploy is always picked up straight away. */
const OFFLINE_CACHE = 'cg-offline-v1'
const OFFLINE_URL = '/offline.html'

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(OFFLINE_CACHE).then((cache) => cache.addAll([OFFLINE_URL, '/icons/icon-192.png'])).then(() => self.skipWaiting()))
})

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) if (key !== OFFLINE_CACHE) await caches.delete(key)
    await self.clients.claim()
  })())
})

// Page loads go to the network; only when that fails (offline) show the offline page.
self.addEventListener('fetch', (event) => {
  if (event.request.mode !== 'navigate') return
  event.respondWith(fetch(event.request).catch(async () => (await caches.match(OFFLINE_URL)) || Response.error()))
})

self.addEventListener('push', (event) => {
  let message = {}
  try { message = event.data ? event.data.json() : {} } catch { message = { title: 'CommonGround', body: event.data ? event.data.text() : '' } }
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    // Someone looking at the app already gets the in-app alert and sound.
    const looking = windows.some((client) => client.focused && client.visibilityState === 'visible')
    if (looking && !message.force) return
    const isCall = message.kind === 'call'
    await self.registration.showNotification(message.title || 'CommonGround', {
      body: message.body || '',
      icon: '/icons/icon-192.png',
      badge: '/icons/badge-96.png',
      tag: message.tag || undefined,
      renotify: Boolean(message.tag),
      requireInteraction: Boolean(message.require_interaction),
      vibrate: isCall ? [400, 200, 400, 200, 400] : [120],
      data: { url: message.url || '/notifications' },
      actions: isCall ? [{ action: 'open', title: 'Answer' }] : [],
    })
  })())
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const path = (event.notification.data && event.notification.data.url) || '/notifications'
  const url = new URL(path.startsWith('/') ? path : '/notifications', self.location.origin).href
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    const existing = windows.find((client) => new URL(client.url).origin === self.location.origin)
    if (existing) {
      await existing.focus()
      // The app routes without a reload (keeps a call or a draft alive).
      existing.postMessage({ type: 'commonground:open', url: path })
      return
    }
    await self.clients.openWindow(url)
  })())
})

// The browser replaced the subscription (keys rotated): tell an open tab to register it again.
self.addEventListener('pushsubscriptionchange', (event) => {
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    for (const client of windows) client.postMessage({ type: 'commonground:resubscribe' })
  })())
})
