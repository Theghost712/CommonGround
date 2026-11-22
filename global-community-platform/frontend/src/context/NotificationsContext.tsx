import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '../services/api'
import { useAuth } from './AuthContext'

export type NotificationItem = {
  id: number
  notification_type: string
  title: string
  body: string
  target_url: string
  data: Record<string, unknown>
  actor: number | null
  actor_username: string | null
  is_read: boolean
  read_at: string | null
  created_at: string
}

type NotificationsContextValue = {
  unreadCount: number
  setUnreadCount: (count: number) => void
  refreshUnreadCount: () => Promise<void>
}

const NotificationsContext = createContext<NotificationsContextValue | null>(null)

export function NotificationsProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [unreadCount, setUnreadCount] = useState(0)

  const refreshUnreadCount = useCallback(async () => {
    if (!user) {
      setUnreadCount(0)
      return
    }
    try {
      const response = await api.get<{ unread_count: number }>('/notifications/unread-count/')
      setUnreadCount(response.data.unread_count)
    } catch {
      // Keep the last known count if a temporary connection problem occurs.
    }
  }, [user])

  useEffect(() => {
    if (!user) {
      setUnreadCount(0)
      return
    }

    let stopped = false
    let socket: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let reconnectDelay = 1000

    const connect = () => {
      if (stopped) return
      void api.post<{ ticket: string }>('/auth/ws-ticket/', {}).then(({ data }) => {
      if (stopped) return
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const url = `${protocol}//${window.location.host}/ws/notifications/?ticket=${encodeURIComponent(data.ticket)}`
      socket = new WebSocket(url)

      // On every (re)connect, catch up on anything missed while offline.
      socket.onopen = () => { reconnectDelay = 1000; void refreshUnreadCount() }
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as { type?: string; notification?: NotificationItem; unread_count?: number }
          if (payload.type === 'notification.new' && payload.notification) {
            if (typeof payload.unread_count === 'number') setUnreadCount(payload.unread_count)
            else setUnreadCount((current) => current + 1)
            queryClient.invalidateQueries({ queryKey: ['notifications'] })
            window.dispatchEvent(new CustomEvent('commonground:notification', { detail: payload.notification }))
          }
        } catch {
          // Ignore malformed socket frames and keep the connection open.
        }
      }
      socket.onclose = () => {
        if (stopped) return
        reconnectTimer = setTimeout(connect, reconnectDelay)
        reconnectDelay = Math.min(reconnectDelay * 2, 30000)
      }
      socket.onerror = () => socket?.close()
      }).catch(() => {
        if (!stopped) {
          reconnectTimer = setTimeout(connect, reconnectDelay)
          reconnectDelay = Math.min(reconnectDelay * 2, 30000)
        }
      })
    }

    void refreshUnreadCount()
    // The socket pushes counts live; polling is only a safety net. (Every 45 s cost
    // ~22k requests/s at a million users; every 5 min costs ~3k.)
    const refreshTimer = setInterval(() => { void refreshUnreadCount() }, 5 * 60_000)
    connect()

    return () => {
      stopped = true
      clearInterval(refreshTimer)
      if (reconnectTimer) clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [user, refreshUnreadCount, queryClient])

  const value = useMemo(() => ({ unreadCount, setUnreadCount, refreshUnreadCount }), [unreadCount, refreshUnreadCount])
  return <NotificationsContext.Provider value={value}>{children}</NotificationsContext.Provider>
}

export function useNotifications() {
  const value = useContext(NotificationsContext)
  if (!value) throw new Error('useNotifications must be used inside NotificationsProvider')
  return value
}
