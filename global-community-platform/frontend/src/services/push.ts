import { api } from './api'

/**
 * Web Push on this device: notifications that arrive even when CommonGround is closed.
 *
 * Support differs a lot: Chrome, Edge, Firefox and Samsung Internet on Android and
 * desktop work in the browser; on iPhone/iPad (iOS 16.4+) only after "Add to Home
 * Screen", opened from the home-screen icon.
 */
export type PushState = 'unsupported' | 'needs-install' | 'server-off' | 'denied' | 'off' | 'on'
type PushConfig = { enabled: boolean; public_key: string; devices: number }

const SW_URL = '/sw.js'
let pushOnThisDevice = false

/** True when this device gets server push, so the open tab shouldn't also pop up. */
export const isPushActiveHere = () => pushOnThisDevice

export const pushSupported = () =>
  typeof window !== 'undefined' && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window

export const isIos = () => typeof navigator !== 'undefined' && /iPad|iPhone|iPod/.test(navigator.userAgent)
export const isStandalone = () =>
  typeof window !== 'undefined' && (window.matchMedia?.('(display-mode: standalone)').matches || (navigator as { standalone?: boolean }).standalone === true)

/** Register the service worker once (also makes the app installable). Safe to call often. */
export async function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (typeof window === 'undefined' || !('serviceWorker' in navigator)) return null
  try {
    return await navigator.serviceWorker.register(SW_URL, { scope: '/' })
  } catch {
    return null
  }
}

function urlBase64ToUint8Array(base64: string) {
  const padded = (base64 + '='.repeat((4 - (base64.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(padded)
  return Uint8Array.from(raw, (char) => char.charCodeAt(0))
}

async function currentSubscription() {
  const registration = await registerServiceWorker()
  return registration ? { registration, subscription: await registration.pushManager.getSubscription() } : null
}

export async function getPushState(): Promise<PushState> {
  if (!pushSupported()) return isIos() && !isStandalone() ? 'needs-install' : 'unsupported'
  const { data } = await api.get<PushConfig>('/push/config/')
  if (!data.enabled) return 'server-off'
  if (Notification.permission === 'denied') return 'denied'
  const current = await currentSubscription()
  pushOnThisDevice = Boolean(current?.subscription) && Notification.permission === 'granted'
  return pushOnThisDevice ? 'on' : 'off'
}

/** Ask permission (must run from a click), subscribe, and register the device with the server. */
export async function enablePush(): Promise<PushState> {
  if (!pushSupported()) return isIos() && !isStandalone() ? 'needs-install' : 'unsupported'
  const { data } = await api.get<PushConfig>('/push/config/')
  if (!data.enabled) return 'server-off'
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') return permission === 'denied' ? 'denied' : 'off'
  const current = await currentSubscription()
  if (!current) return 'unsupported'
  await navigator.serviceWorker.ready
  const key = urlBase64ToUint8Array(data.public_key)
  let subscription = current.subscription
  // A subscription made with another server key can't be reused.
  const existingKey = subscription?.options.applicationServerKey
  if (subscription && existingKey && new Uint8Array(existingKey).toString() !== key.toString()) {
    await subscription.unsubscribe(); subscription = null
  }
  subscription ??= await current.registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key })
  await api.post('/push/subscriptions/', subscription.toJSON())
  pushOnThisDevice = true
  return 'on'
}

export async function disablePush(): Promise<PushState> {
  const current = await currentSubscription()
  const subscription = current?.subscription
  if (subscription) {
    try { await api.post('/push/subscriptions/remove/', { endpoint: subscription.endpoint }) } catch { /* still unsubscribe locally */ }
    await subscription.unsubscribe()
  }
  pushOnThisDevice = false
  return 'off'
}

/** On sign-out: stop this device getting the previous account's notifications. Never throws. */
export async function forgetPushOnSignOut() {
  if (!pushSupported()) return
  try {
    const registration = await navigator.serviceWorker.getRegistration(SW_URL)
    const subscription = await registration?.pushManager.getSubscription()
    if (!subscription) return
    try { await api.post('/push/subscriptions/remove/', { endpoint: subscription.endpoint }) } catch { /* signed out already */ }
    await subscription.unsubscribe()
  } catch { /* ignore */ }
  pushOnThisDevice = false
}

/** Re-send this device's subscription (after sign-in, or when the browser rotated it). */
export async function syncPushSubscription() {
  if (!pushSupported() || Notification.permission !== 'granted') return
  try {
    const current = await currentSubscription()
    if (!current?.subscription) return
    await api.post('/push/subscriptions/', current.subscription.toJSON())
    pushOnThisDevice = true
  } catch { /* push is optional */ }
}
