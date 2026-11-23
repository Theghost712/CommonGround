import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, getErrorMessage } from '../services/api'
import { useAuth } from './AuthContext'

export type CallKind = 'audio' | 'video'
type CallPerson = { id: number; username: string; display_name: string }
export type CallInfo = {
  id: number
  conversation_id: number
  kind: CallKind
  status: 'ringing' | 'accepted' | 'declined' | 'missed' | 'cancelled' | 'ended' | 'failed'
  caller: CallPerson
  callee: CallPerson
  answered_device: string
}
export type CallPhase = 'idle' | 'outgoing' | 'incoming' | 'connecting' | 'active' | 'ended'
type Signal = { sdp?: RTCSessionDescriptionInit; candidate?: RTCIceCandidateInit }

export type CallState = {
  phase: CallPhase
  call: CallInfo | null
  /** Shown on the end screen: "Call ended", "Declined", "Couldn't connect"… */
  message: string
  startedAt: number | null
  localStream: MediaStream | null
  remoteStream: MediaStream | null
  muted: boolean
  cameraOff: boolean
}
type CallValue = CallState & {
  available: boolean
  startCall: (conversationId: number, kind: CallKind) => Promise<void>
  accept: () => Promise<void>
  decline: () => Promise<void>
  hangUp: () => Promise<void>
  toggleMute: () => void
  toggleCamera: () => void
  dismiss: () => void
  /** Group calls share this signalling socket. */
  sendRaw: (frame: Record<string, unknown>) => boolean
  subscribe: (listener: (event: SocketEvent) => void) => () => void
}
export type SocketEvent = { type?: string; [key: string]: unknown }

const RING_TIMEOUT_MS = 45_000
const idle: CallState = { phase: 'idle', call: null, message: '', startedAt: null, localStream: null, remoteStream: null, muted: false, cameraOff: false }
const END_MESSAGES: Record<string, string> = { declined: 'Call declined', missed: 'No answer', cancelled: 'Call cancelled', ended: 'Call ended', failed: "Couldn't connect" }
// Identifies this tab, so only the tab that answered handles the call.
export const deviceId = (typeof crypto !== 'undefined' && 'randomUUID' in crypto) ? crypto.randomUUID() : `tab-${Math.random().toString(36).slice(2)}`

export const callsSupported = () => typeof window !== 'undefined' && typeof RTCPeerConnection !== 'undefined' && Boolean(navigator.mediaDevices?.getUserMedia)

/** A gentle two-tone ring made with Web Audio (no audio files to load). */
export function createRinger() {
  let context: AudioContext | null = null
  let timer: ReturnType<typeof setInterval> | null = null
  const beep = () => {
    if (!context) return
    for (const [offset, freq] of [[0, 660], [0.25, 880]] as const) {
      const osc = context.createOscillator()
      const gain = context.createGain()
      osc.frequency.value = freq
      gain.gain.setValueAtTime(0.0001, context.currentTime + offset)
      gain.gain.exponentialRampToValueAtTime(0.12, context.currentTime + offset + 0.03)
      gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + offset + 0.22)
      osc.connect(gain).connect(context.destination)
      osc.start(context.currentTime + offset)
      osc.stop(context.currentTime + offset + 0.25)
    }
  }
  return {
    start() {
      if (timer) return
      try { context = new AudioContext(); void context.resume?.() } catch { context = null }
      beep()
      timer = setInterval(beep, 2000)
    },
    stop() {
      if (timer) clearInterval(timer)
      timer = null
      void context?.close().catch(() => {})
      context = null
    },
  }
}

export function mediaError(err: unknown, kind: CallKind): string {
  const name = (err as { name?: string })?.name
  if (name === 'NotAllowedError' || name === 'SecurityError') return `Allow ${kind === 'video' ? 'camera and microphone' : 'microphone'} access in your browser to call.`
  if (name === 'NotFoundError') return kind === 'video' ? 'No camera or microphone was found.' : 'No microphone was found.'
  if (!window.isSecureContext) return 'Calls need a secure (https) connection. Open the site over https or on localhost.'
  return getErrorMessage(err)
}

const CallContext = createContext<CallValue | null>(null)

export function CallProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const [state, setState] = useState<CallState>(idle)
  const stateRef = useRef(state)
  stateRef.current = state
  const socketRef = useRef<WebSocket | null>(null)
  const pcRef = useRef<RTCPeerConnection | null>(null)
  const localRef = useRef<MediaStream | null>(null)
  const iceRef = useRef<RTCIceServer[]>([])
  const pendingCandidates = useRef<RTCIceCandidateInit[]>([])
  const pendingSignals = useRef<Signal[]>([])
  const ringer = useRef(createRinger())
  const ringTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)
  const dismissTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const available = callsSupported()
  const listeners = useRef(new Set<(event: SocketEvent) => void>())

  const send = useCallback((callId: number, data: Signal) => {
    const socket = socketRef.current
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'signal', call_id: callId, data, device_id: deviceId }))
  }, [])

  const cleanup = useCallback(() => {
    ringer.current.stop()
    if (ringTimeout.current) clearTimeout(ringTimeout.current)
    pcRef.current?.close()
    pcRef.current = null
    localRef.current?.getTracks().forEach((track) => track.stop())
    localRef.current = null
    pendingCandidates.current = []
    pendingSignals.current = []
  }, [])

  const finishLocally = useCallback((message: string) => {
    cleanup()
    setState((current) => ({ ...idle, phase: 'ended', call: current.call, message }))
    if (dismissTimer.current) clearTimeout(dismissTimer.current)
    dismissTimer.current = setTimeout(() => setState((current) => current.phase === 'ended' ? idle : current), 2500)
  }, [cleanup])

  const hangUp = useCallback(async (failed = false) => {
    const call = stateRef.current.call
    finishLocally(failed ? END_MESSAGES.failed : stateRef.current.phase === 'outgoing' ? END_MESSAGES.cancelled : END_MESSAGES.ended)
    if (call) await api.post(`/calls/${call.id}/end/`, failed ? { failed: true } : {}).catch(() => {})
  }, [finishLocally])

  const handleSignal = useCallback(async (signal: Signal) => {
    const pc = pcRef.current
    const call = stateRef.current.call
    if (!pc || !call) { pendingSignals.current.push(signal); return }
    try {
      if (signal.sdp) {
        await pc.setRemoteDescription(signal.sdp)
        for (const candidate of pendingCandidates.current.splice(0)) await pc.addIceCandidate(candidate).catch(() => {})
        if (signal.sdp.type === 'offer') {
          const answer = await pc.createAnswer()
          await pc.setLocalDescription(answer)
          send(call.id, { sdp: { type: answer.type, sdp: answer.sdp } })
        }
      } else if (signal.candidate) {
        if (pc.remoteDescription) await pc.addIceCandidate(signal.candidate).catch(() => {})
        else pendingCandidates.current.push(signal.candidate)
      }
    } catch {
      void hangUp(true)
    }
  }, [send, hangUp])

  const createPeer = useCallback((call: CallInfo) => {
    const pc = new RTCPeerConnection({ iceServers: iceRef.current })
    pcRef.current = pc
    localRef.current?.getTracks().forEach((track) => pc.addTrack(track, localRef.current!))
    pc.onicecandidate = (event) => { if (event.candidate) send(call.id, { candidate: event.candidate.toJSON() }) }
    pc.ontrack = (event) => {
      const stream = event.streams[0] ?? new MediaStream([event.track])
      setState((current) => ({ ...current, remoteStream: stream }))
    }
    let dropTimer: ReturnType<typeof setTimeout> | null = null
    pc.onconnectionstatechange = () => {
      if (dropTimer) { clearTimeout(dropTimer); dropTimer = null }
      if (pc.connectionState === 'connected') setState((current) => current.phase === 'active' ? current : { ...current, phase: 'active', startedAt: Date.now() })
      if (pc.connectionState === 'failed') void hangUp(stateRef.current.phase !== 'active')
      // The other side closed their tab or lost the network: give it a moment to recover.
      if (pc.connectionState === 'disconnected') dropTimer = setTimeout(() => { if (pcRef.current === pc) void hangUp(false) }, 8000)
    }
    for (const signal of pendingSignals.current.splice(0)) void handleSignal(signal)
    return pc
  }, [send, hangUp, handleSignal])

  const getMedia = async (kind: CallKind) => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }, video: kind === 'video' ? { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' } : false })
    localRef.current = stream
    return stream
  }

  const startCall = useCallback(async (conversationId: number, kind: CallKind) => {
    if (stateRef.current.phase !== 'idle' && stateRef.current.phase !== 'ended') throw new Error("You're already in a call.")
    if (!available) throw new Error("This browser can't make calls.")
    let stream: MediaStream
    try { stream = await getMedia(kind) } catch (err) { throw new Error(mediaError(err, kind)) }
    try {
      const { data } = await api.post<{ call: CallInfo; ice_servers: RTCIceServer[] }>('/calls/', { conversation_id: conversationId, kind })
      iceRef.current = data.ice_servers
      setState({ ...idle, phase: 'outgoing', call: data.call, localStream: stream })
      ringer.current.start()
      ringTimeout.current = setTimeout(() => { if (stateRef.current.phase === 'outgoing') void hangUp() }, RING_TIMEOUT_MS)
    } catch (err) {
      stream.getTracks().forEach((track) => track.stop())
      localRef.current = null
      throw new Error(getErrorMessage(err))
    }
  }, [available, hangUp])

  const accept = useCallback(async () => {
    const call = stateRef.current.call
    if (!call || stateRef.current.phase !== 'incoming') return
    ringer.current.stop()
    let stream: MediaStream
    try { stream = await getMedia(call.kind) } catch (err) {
      finishLocally(mediaError(err, call.kind))
      await api.post(`/calls/${call.id}/decline/`).catch(() => {})
      return
    }
    setState((current) => ({ ...current, phase: 'connecting', localStream: stream }))
    try {
      const { data } = await api.post<{ call: CallInfo; ice_servers: RTCIceServer[] }>(`/calls/${call.id}/accept/`, { device_id: deviceId })
      iceRef.current = data.ice_servers
      setState((current) => ({ ...current, call: data.call }))
      createPeer(data.call) // the caller sends the offer once it hears we accepted
    } catch (err) {
      finishLocally(getErrorMessage(err))
    }
  }, [createPeer, finishLocally])

  const decline = useCallback(async () => {
    const call = stateRef.current.call
    cleanup()
    setState(idle)
    if (call) await api.post(`/calls/${call.id}/decline/`).catch(() => {})
  }, [cleanup])

  const onEvent = useCallback(async (payload: { type?: string; call?: CallInfo; call_id?: number; data?: Signal; device_id?: string }) => {
    const current = stateRef.current
    if (payload.type === 'call.incoming' && payload.call) {
      if (current.phase !== 'idle' && current.phase !== 'ended') return
      setState({ ...idle, phase: 'incoming', call: payload.call })
      ringer.current.start()
      // Stop ringing if the caller vanished without hanging up (closed tab, lost network).
      if (ringTimeout.current) clearTimeout(ringTimeout.current)
      ringTimeout.current = setTimeout(() => { if (stateRef.current.phase === 'incoming' && stateRef.current.call?.id === payload.call!.id) finishLocally(END_MESSAGES.missed) }, RING_TIMEOUT_MS + 5000)
      return
    }
    if (payload.type === 'call.update' && payload.call) {
      const call = payload.call
      if (!current.call || current.call.id !== call.id) return
      if (call.status === 'accepted') {
        const iAmCaller = user?.id === call.caller.id
        if (iAmCaller && current.phase === 'outgoing') {
          ringer.current.stop()
          if (ringTimeout.current) clearTimeout(ringTimeout.current)
          setState((s) => ({ ...s, phase: 'connecting', call }))
          const pc = createPeer(call)
          const offer = await pc.createOffer()
          await pc.setLocalDescription(offer)
          send(call.id, { sdp: { type: offer.type, sdp: offer.sdp } })
        } else if (!iAmCaller && call.answered_device !== deviceId) {
          cleanup() // answered on another device or tab
          setState(idle)
        }
        return
      }
      if (current.phase !== 'idle' && current.phase !== 'ended') finishLocally(END_MESSAGES[call.status] ?? 'Call ended')
      return
    }
    const active = current.call
    if (payload.type === 'call.signal' && payload.data && active && active.id === payload.call_id) {
      if (user?.id === active.callee.id && active.answered_device && active.answered_device !== deviceId) return
      await handleSignal(payload.data)
    }
  }, [user, createPeer, send, cleanup, finishLocally, handleSignal])
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  // Per-user signalling socket (ticket auth, reconnects with backoff like notifications).
  useEffect(() => {
    if (!user || !available) return
    let stopped = false
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let delay = 1000
    const connect = () => {
      if (stopped) return
      void api.post<{ ticket: string }>('/auth/ws-ticket/', {}).then(({ data }) => {
        if (stopped) return
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const socket = new WebSocket(`${protocol}//${window.location.host}/ws/calls/?ticket=${encodeURIComponent(data.ticket)}`)
        socketRef.current = socket
        socket.onopen = () => {
          delay = 1000
          // Pick a ringing call back up after a reload.
          void api.get<{ call: CallInfo | null }>('/calls/active/').then(({ data: active }) => {
            if (active.call?.status === 'ringing' && active.call.callee.id === user.id && stateRef.current.phase === 'idle') void onEventRef.current({ type: 'call.incoming', call: active.call })
          }).catch(() => {})
        }
        socket.onmessage = (event) => {
          let frame: SocketEvent
          try { frame = JSON.parse(event.data) } catch { return }
          if (typeof frame.type === 'string' && frame.type.startsWith('group_call.')) {
            listeners.current.forEach((listener) => { try { listener(frame) } catch { /* a broken listener must not stop the others */ } })
            return
          }
          void onEventRef.current(frame as Parameters<typeof onEvent>[0])
        }
        socket.onclose = () => {
          if (socketRef.current === socket) socketRef.current = null
          if (stopped) return
          reconnectTimer = setTimeout(connect, delay)
          delay = Math.min(delay * 2, 30000)
        }
        socket.onerror = () => socket.close()
      }).catch(() => { if (!stopped) { reconnectTimer = setTimeout(connect, delay); delay = Math.min(delay * 2, 30000) } })
    }
    connect()
    return () => { stopped = true; if (reconnectTimer) clearTimeout(reconnectTimer); socketRef.current?.close() }
  }, [user, available])

  useEffect(() => () => { cleanup(); if (dismissTimer.current) clearTimeout(dismissTimer.current) }, [cleanup])

  const toggleMute = useCallback(() => {
    const track = localRef.current?.getAudioTracks()[0]
    if (!track) return
    track.enabled = !track.enabled
    setState((current) => ({ ...current, muted: !track.enabled }))
  }, [])
  const toggleCamera = useCallback(() => {
    const track = localRef.current?.getVideoTracks()[0]
    if (!track) return
    track.enabled = !track.enabled
    setState((current) => ({ ...current, cameraOff: !track.enabled }))
  }, [])
  const dismiss = useCallback(() => setState((current) => current.phase === 'ended' ? idle : current), [])
  const sendRaw = useCallback((frame: Record<string, unknown>) => {
    const socket = socketRef.current
    if (socket?.readyState !== WebSocket.OPEN) return false
    socket.send(JSON.stringify(frame))
    return true
  }, [])
  const subscribe = useCallback((listener: (event: SocketEvent) => void) => {
    listeners.current.add(listener)
    return () => { listeners.current.delete(listener) }
  }, [])

  const value = useMemo<CallValue>(() => ({
    ...state, available, startCall, accept, decline, hangUp: () => hangUp(false), toggleMute, toggleCamera, dismiss, sendRaw, subscribe,
  }), [state, available, startCall, accept, decline, hangUp, toggleMute, toggleCamera, dismiss, sendRaw, subscribe])
  return <CallContext.Provider value={value}>{children}</CallContext.Provider>
}

export function useCall() {
  const value = useContext(CallContext)
  if (!value) throw new Error('useCall must be used inside CallProvider')
  return value
}
