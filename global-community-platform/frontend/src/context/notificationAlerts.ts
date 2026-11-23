import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../services/api'
import { enablePush, isPushActiveHere, syncPushSubscription } from '../services/push'
import type { NotificationItem } from './NotificationsContext'

export type DeliveryPreferences = { sound_enabled: boolean; popup_enabled: boolean }

let audioContext: AudioContext | null = null

/** Browsers only allow audio after a user gesture; create/resume the context on the first one. */
function unlockAudio() {
  const Ctor = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!Ctor) return
  audioContext ??= new Ctor()
  if (audioContext.state === 'suspended') void audioContext.resume()
}

/** A short, soft two-note chime generated with Web Audio (no audio file to load). */
export function playNotificationSound(): boolean {
  if (!audioContext || audioContext.state !== 'running') return false
  const ctx = audioContext
  const start = ctx.currentTime + 0.01
  ;[[880, 0], [1318.5, 0.12]].forEach(([frequency, offset]) => {
    const oscillator = ctx.createOscillator()
    const gain = ctx.createGain()
    oscillator.type = 'sine'
    oscillator.frequency.value = frequency
    gain.gain.setValueAtTime(0.0001, start + offset)
    gain.gain.exponentialRampToValueAtTime(0.18, start + offset + 0.02)
    gain.gain.exponentialRampToValueAtTime(0.0001, start + offset + 0.35)
    oscillator.connect(gain).connect(ctx.destination)
    oscillator.start(start + offset)
    oscillator.stop(start + offset + 0.4)
  })
  return true
}

let unlockInstalled = false

/**
 * Listen for the first user gesture anywhere in the app (including the "Sign in" click)
 * so the chime can play later. Installed once at start-up, before any page renders.
 */
export function installAudioUnlock() {
  if (unlockInstalled || typeof window === 'undefined') return
  unlockInstalled = true
  for (const name of ['pointerdown', 'keydown', 'touchstart'] as const) window.addEventListener(name, unlockAudio, { passive: true, capture: true })
}

export const popupsSupported = () => typeof window !== 'undefined' && 'Notification' in window

export async function requestPopupPermission(): Promise<NotificationPermission | 'unsupported'> {
  if (!popupsSupported()) return 'unsupported'
  if (Notification.permission !== 'default') return Notification.permission
  return Notification.requestPermission()
}

export const deliveryPreferencesKey = ['notification-preferences'] as const

const BASE_TITLE = typeof document !== 'undefined' ? document.title : 'CommonGround'
const SOUND_GAP_MS = 1500

/**
 * Plays a chime and shows a system pop-up for each live notification, honouring the
 * user's sound/pop-up preferences, and keeps the unread count in the tab title.
 */
export function useNotificationAlerts(unreadCount: number) {
  const navigate = useNavigate()
  const location = useLocation()
  const pathRef = useRef(location.pathname)
  pathRef.current = location.pathname
  const lastSound = useRef(0)
  const { data: prefs } = useQuery({
    queryKey: deliveryPreferencesKey,
    queryFn: async () => (await api.get<DeliveryPreferences>('/notifications/preferences/')).data,
    staleTime: 60_000,
  })
  const prefsRef = useRef(prefs)
  prefsRef.current = prefs

  useEffect(() => { installAudioUnlock() }, [])

  useEffect(() => {
    document.title = unreadCount > 0 ? `(${unreadCount > 99 ? '99+' : unreadCount}) ${BASE_TITLE}` : BASE_TITLE
    return () => { document.title = BASE_TITLE }
  }, [unreadCount])

  useEffect(() => {
    const onNotification = (event: Event) => {
      const item = (event as CustomEvent<NotificationItem>).detail
      if (!item) return
      const current = prefsRef.current
      const visible = document.visibilityState === 'visible' && document.hasFocus()
      const alreadyLooking = visible && item.notification_type === 'message' && pathRef.current.startsWith('/messages')

      // Until the user's preferences have loaded we don't know they want alerts: stay quiet.
      if (current?.sound_enabled === true && !alreadyLooking && Date.now() - lastSound.current > SOUND_GAP_MS) {
        if (playNotificationSound()) lastSound.current = Date.now()
      }
      // With push on this device, the service worker shows the pop-up (once, even if the tab is closed).
      if (current?.popup_enabled === true && !visible && !isPushActiveHere() && popupsSupported() && Notification.permission === 'granted') {
        try {
          const popup = new Notification(item.title, { body: item.body || undefined, icon: '/favicon.svg', tag: `commonground-${item.id}` })
          popup.onclick = () => {
            window.focus()
            if (item.target_url?.startsWith('/')) navigate(item.target_url)
            popup.close()
          }
        } catch {
          // Some mobile browsers only allow notifications from a service worker; skip quietly.
        }
      }
    }
    window.addEventListener('commonground:notification', onNotification)
    return () => window.removeEventListener('commonground:notification', onNotification)
  }, [navigate])

  // Messages from the service worker: a tapped push notification, or a rotated subscription.
  useEffect(() => {
    void syncPushSubscription()
    if (typeof navigator === 'undefined' || !navigator.serviceWorker) return
    const onMessage = (event: MessageEvent) => {
      const message = event.data as { type?: string; url?: string } | null
      if (message?.type === 'commonground:open' && message.url?.startsWith('/')) navigate(message.url)
      if (message?.type === 'commonground:resubscribe') void enablePush().catch(() => undefined)
    }
    navigator.serviceWorker.addEventListener('message', onMessage)
    return () => navigator.serviceWorker.removeEventListener('message', onMessage)
  }, [navigate])
}
