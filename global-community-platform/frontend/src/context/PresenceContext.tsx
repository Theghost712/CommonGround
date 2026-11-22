import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { useAuth } from './AuthContext'
import { api } from '../services/api'

export type PresenceEntry = {
  user_id: number
  username: string
  status: 'online' | 'offline'
  last_seen: string | null
}

type PresenceContextValue = {
  presences: Record<number, PresenceEntry>
  connected: boolean
  isOnline: (userId: number) => boolean
  getPresence: (userId: number) => PresenceEntry | undefined
}

const PresenceContext = createContext<PresenceContextValue | null>(null)

export function PresenceProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()

  const [presences, setPresences] = useState<Record<number, PresenceEntry>>({})
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    if (!user) {
      setPresences({})
      setConnected(false)
      return
    }

    let stopped = false
    let socket: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let pingTimer: ReturnType<typeof setInterval> | null = null
    let reconnectDelay = 1000

    const connect = () => {
      if (stopped) return
      void api.post<{ ticket: string }>('/auth/ws-ticket/', {}).then(({ data }) => {
      if (stopped) return
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const url = `${protocol}//${window.location.host}/ws/presence/?ticket=${encodeURIComponent(data.ticket)}`
      socket = new WebSocket(url)

      socket.onopen = () => {
        setConnected(true)
        reconnectDelay = 1000

        pingTimer = setInterval(() => {
          if (socket?.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'ping' }))
          }
        }, 25000)
      }

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data)

          if (
            payload.type === 'presence.connected' ||
            payload.type === 'presence.update'
          ) {
            const userId = Number(payload.user_id)

            if (!userId) return

            const status = payload.status === 'offline' ? 'offline' : 'online'

            setPresences((current) => ({
              ...current,
              [userId]: {
                user_id: userId,
                username: payload.username || current[userId]?.username || '',
                status,
                last_seen: payload.last_seen ?? current[userId]?.last_seen ?? null,
              },
            }))
          }

          if (
            payload.type === 'presence.snapshot' &&
            Array.isArray(payload.presences)
          ) {
            const snapshot: Record<number, PresenceEntry> = {}

            payload.presences.forEach((entry: PresenceEntry) => {
              snapshot[entry.user_id] = entry
            })

            setPresences((current) => ({ ...current, ...snapshot }))
          }
        } catch {
          // Ignore invalid WebSocket messages.
        }
      }

      socket.onclose = () => {
        setConnected(false)

        if (pingTimer) {
          clearInterval(pingTimer)
          pingTimer = null
        }

        if (stopped) return

        reconnectTimer = setTimeout(connect, reconnectDelay)
        reconnectDelay = Math.min(reconnectDelay * 2, 30000)
      }

      socket.onerror = () => {
        socket?.close()
      }
      }).catch(() => {
        if (stopped) return
        reconnectTimer = setTimeout(connect, reconnectDelay)
        reconnectDelay = Math.min(reconnectDelay * 2, 30000)
      })
    }

    connect()

    return () => {
      stopped = true

      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (pingTimer) clearInterval(pingTimer)

      socket?.close()
      setConnected(false)
    }
  }, [user])

  const value = useMemo<PresenceContextValue>(
    () => ({
      presences,
      connected,
      isOnline: (userId) => presences[userId]?.status === 'online',
      getPresence: (userId) => presences[userId],
    }),
    [presences, connected],
  )

  return (
    <PresenceContext.Provider value={value}>
      {children}
    </PresenceContext.Provider>
  )
}

export function usePresence() {
  const context = useContext(PresenceContext)

  if (!context) {
    throw new Error('usePresence must be used inside PresenceProvider')
  }

  return context
}
